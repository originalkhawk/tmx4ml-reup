#!/usr/bin/env python3

import argparse
from datetime import datetime
import logging
from typing import Any
import sys
import asyncio

import aiohttp
from aiohttp import web
import aiohttp.log
from aiohttp.typedefs import Handler
from aiohttp.web_request import Request
import aiohttp_jinja2
import jinja2
import yarl

import bbcode_tmx
import routes as rt
import records as rc
import tmx
from login import run_cli_loop, perform_exchange_login


async def client_session_ctx(app: web.Application):
    connector = aiohttp.TCPConnector(
        resolver=aiohttp.ThreadedResolver()
    )

    cookie_jar = aiohttp.CookieJar(unsafe=True)
    cookies_data = app.get("cookies_data")
    if cookies_data:
        for k, v in cookies_data.items():
            cookie_jar._cookies[k] = v

    session = aiohttp.ClientSession(connector=connector, cookie_jar=cookie_jar)

    app["client_session"] = session
    app["cookie_jar"] = cookie_jar

    # Dynamic session verification and auto-renewal
    from login import verify_account_links, load_config, save_config, decrypt_password, get_system_key, perform_exchange_login
    
    config = load_config()
    logged_in_username = app.get("logged_in_username")
    site_access = app.get("site_access", {"tmnf": False, "tmuf": False})
    
    session_valid = False
    if cookies_data:
        print("Checking active session validity...")
        status = await verify_account_links(session)
        if status.get("username") or status.get("tmnf") or status.get("tmuf"):
            session_valid = True
            logged_in_username = status.get("username") or logged_in_username
            site_access = {
                "tmnf": bool(status.get("tmnf", False)),
                "tmuf": bool(status.get("tmuf", False)),
            }
            app["logged_in_username"] = logged_in_username
            app["site_access"] = site_access
            print(f"✔️ Active session verified for user: {logged_in_username}")
        else:
            print("⚠️ Saved session cookies have expired or are invalid.")

    # Try to auto-renew if not valid and saved credentials exist
    if not session_valid and "saved_username" in config and "saved_password_encrypted" in config:
        saved_username = config["saved_username"]
        encrypted_pw = config["saved_password_encrypted"]
        secret_key = config.get("secret_key", "")
        system_key = get_system_key()
        final_key = system_key + secret_key
        
        decrypted_pw = decrypt_password(encrypted_pw, final_key)
        if decrypted_pw:
            print(f"🔄 Auto-renewing session for user: {saved_username}...")
            try:
                login_results = await perform_exchange_login(session, {"username": saved_username, "password": decrypted_pw})
                tmnf_ok = bool(login_results.get("tmnf", False))
                tmuf_ok = bool(login_results.get("tmuf", False))
                account_name = login_results.get("username") or saved_username
                
                if tmnf_ok or tmuf_ok:
                    logged_in_username = account_name
                    site_access = {"tmnf": tmnf_ok, "tmuf": tmuf_ok}
                    
                    app["logged_in_username"] = logged_in_username
                    app["site_access"] = site_access
                    
                    # Refresh cookies in config
                    config["cookies_data"] = serialize_cookies(cookie_jar._cookies)
                    config["logged_in_username"] = logged_in_username
                    config["site_access"] = site_access
                    save_config(config)
                    print(f"✔️ Session successfully renewed. User: {logged_in_username}")
                    session_valid = True
                else:
                    print("⚠️ Auto-renewal failed: Linked exchange status check failed.")
            except Exception as e:
                print(f"⚠️ Session auto-renewal failed: {e}")
        else:
            print("⚠️ Could not decrypt saved password. Auto-renewal skipped.")

    # If no session is active and no renewal occurred, check if we had cookies loaded (clear them if they are expired)
    if not session_valid and cookies_data:
        print("Starting in unauthenticated mode (session expired).")
        app["logged_in_username"] = None
        app["site_access"] = {"tmnf": False, "tmuf": False}

    for subapp in app._subapps:
        subapp["client_session"] = session
        subapp["logged_in_username"] = app.get("logged_in_username")
        subapp["site_access"] = app.get("site_access")

    yield

    await session.close()


@web.middleware
async def handle_redirects(request: Request, handler: Handler):
    try:
        response = await handler(request)
        return response
    except (
        web.HTTPMultipleChoices,
        web.HTTPMovedPermanently,
        web.HTTPFound,
        web.HTTPSeeOther,
        web.HTTPUseProxy,
        web.HTTPTemporaryRedirect,
    ) as redir:
        location = yarl.URL(redir.location)

        if location.scheme != "tmtp":
            target = request.url.origin().join(yarl.URL(redir.location))
        else:
            target = redir.location

        return rt.render_manialink("redirect.xml", request, {"target": target})


common_routes = [
    web.get("/", rt.make_simple_handler("home.xml"), name="home"),
    web.get("/track/", rt.track_list, name="track-list"),
    web.get("/track/random", rt.random_track, name="track-random"),
    web.get("/track/{trackid}", rt.track_details, name="track-details"),
    web.get("/image/{trackid}.jpg", rt.track_image, name="track-image"),
    web.get("/play/{trackid}", rt.play_track, name="track-play"),
    web.get("/replay/{replayid}", rt.view_replay, name="replay-view"),
    web.get("/trackpack/", rt.trackpack_list, name="trackpack-list"),
    web.get("/trackpack/{packid}", rt.trackpack_details, name="trackpack-details"),
    web.get("/trackpack/random", rt.random_trackpack, name="trackpack-random"),
    web.get("/user/", rt.user_list, name="user-list"),
    web.get("/user/{userid}", rt.user_details, name="user-details"),
    web.get("/user/random", rt.random_user, name="user-random"),
    web.get("/leaderboards/", rt.leaderboards, name="leaderboards"),
    web.get("/record", rc.records_list, name="records-list"),
    web.get("/record/play", rc.play_record, name="records-play"),
    web.get("/record/download", rc.download_record, name="records-download"),
    web.get("/record/upload", rc.upload_record, name="records-upload"),
    web.get("/record/{trackid}", rc.record_details, name="records-details"),
]

root_routes = [
    web.get("/", rt.make_simple_handler("index.xml"), name="index"),
    web.get("/about", rt.make_simple_handler("about.xml"), name="about"),
]


import json
from http.cookies import SimpleCookie

def serialize_cookies(cookies_dict):
    if not cookies_dict:
        return None
    serialized = {}
    for key, cookie in cookies_dict.items():
        if isinstance(key, (tuple, list)):
            key_str = json.dumps(key)
        else:
            key_str = str(key)
        serialized[key_str] = {}
        for cookie_key, morsel in cookie.items():
            serialized[key_str][cookie_key] = morsel.value
    return serialized


def deserialize_cookies(serialized_dict):
    if not serialized_dict:
        return None
    deserialized = {}
    for key_str, cookies in serialized_dict.items():
        simple_cookie = SimpleCookie()
        for key, val in cookies.items():
            simple_cookie[key] = val
        try:
            parsed_key = json.loads(key_str)
            if isinstance(parsed_key, list):
                m_key = tuple(parsed_key)
            else:
                m_key = parsed_key
        except Exception:
            m_key = key_str
        deserialized[m_key] = simple_cookie
    return deserialized


@jinja2.pass_context
def format_user(
    context: jinja2.runtime.Context, user: dict[str, Any], link: bool = False
) -> str:
    name = user["Name"]

    if link:
        origin = context["origin"]
        app = context["app"]
        uid = user["UserId"]

        target = origin.join(app.router["user-details"].url_for(userid=str(uid)))
        return f"$h[{target}]{name}$h"
    else:
        return name


@jinja2.pass_context
def format_bbcode(context: jinja2.runtime.Context, text: str) -> str:
    app = context["app"]
    request = context["request"]

    return bbcode_tmx.format_bbcode(text, request.url.origin(), app["site"])


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%F %H:%M:%S%:z")


def setup_jinja2(app: web.Application):
    aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader("templates"),
        context_processors=(aiohttp_jinja2.request_processor,),
    )

    jinja_env = aiohttp_jinja2.get_env(app)
    jinja_env.globals["tmx"] = tmx

    jinja_env.filters["format_user"] = format_user
    jinja_env.filters["format_bbcode"] = format_bbcode
    jinja_env.filters["format_datetime"] = format_datetime


def init_app():
    app = web.Application(middlewares=[handle_redirects])
    app["site"] = ""
    app["base_url"] = ""

    app.add_routes(root_routes)

    app.cleanup_ctx.append(client_session_ctx)

    setup_jinja2(app)

    for site in ("tmnf", "tmuf"):
        subapp = web.Application()
        subapp.add_routes(common_routes)
        subapp["site"] = site

        base_url = yarl.URL(f"https://{site}.exchange")
        subapp["base_url"] = base_url
        subapp["api_url"] = base_url / "api"

        setup_jinja2(subapp)

        app.add_subapp("/" + site, subapp)
        app[site] = subapp

    return app


def main():
    parser = argparse.ArgumentParser(
        description="ManiaLink frontend server for browsing TrackMania Exchange"
    )
    parser.add_argument("-p", "--port", type=int, default=8080, help="Port to bind to. Default: 8080")
    parser.add_argument("-b", "--bind", default="0.0.0.0", help="Host to bind to. Default: 0.0.0.0")
    parser.add_argument("-s", "--socket", help="Path to a Unix socket to listen on")
    parser.add_argument("-L", "--no-request-logging", dest="request_logging", action="store_false", help="Disable request logging")

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)

    access_log = aiohttp.log.access_logger if args.request_logging else None

    from login import load_config, save_config
    config = load_config()

    cookies_data = None
    logged_in_username = None
    site_access = {"tmnf": False, "tmuf": False}
    start_mode = "start_unauth"

    is_tty = sys.stdin.isatty()

    if is_tty:
        try:
            start_mode, cookies_data, logged_in_username, site_access = asyncio.run(run_cli_loop())
            if start_mode == "start_auth" and cookies_data:
                # Reload config to get the latest settings (like autosave_location) set during the loop
                config = load_config()
                # Save authenticated session to config for future headless runs
                config["cookies_data"] = serialize_cookies(cookies_data)
                config["logged_in_username"] = logged_in_username
                config["site_access"] = site_access
                save_config(config)
                print("Session successfully saved to config.json.")
        except (KeyboardInterrupt, SystemExit):
            print("\nExiting...")
            sys.exit(0)
    else:
        print("Non-interactive terminal detected. Attempting to load saved session from config.json...")
        if "cookies_data" in config and "logged_in_username" in config:
            cookies_data = deserialize_cookies(config["cookies_data"])
            logged_in_username = config["logged_in_username"]
            site_access = config.get("site_access", {"tmnf": True, "tmuf": True})
            print(f"✔️ Loaded saved session for user: {logged_in_username}")
        elif "saved_username" in config:
            logged_in_username = config["saved_username"]
            site_access = {"tmnf": False, "tmuf": False}
            print(f"✔️ Loaded saved credentials for user: {logged_in_username}. Will authenticate on startup.")
        else:
            print("No saved session or credentials found in config.json. Starting server in unauthenticated mode.")

    app = init_app()
    app["cookies_data"] = cookies_data
    app["logged_in_username"] = logged_in_username
    app["site_access"] = site_access

    import socket
    try:
        hostname = socket.gethostname()
        local_ip = "127.0.0.1"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass
        
        print("\n" + "="*60)
        print(" 🚀 TrackMania Exchange ManiaLink server is starting!")
        print(f"    - Hostname URL:       http://{hostname}:{args.port}/")
        if local_ip != "127.0.0.1":
            print(f"    - Local Network URL:  http://{local_ip}:{args.port}/")
        print(f"    - Localhost URL:      http://127.0.0.1:{args.port}/")
        print("="*60 + "\n")
    except Exception:
        pass

    web.run_app(app, port=args.port, host=args.bind, path=args.socket, access_log=access_log)


if __name__ == "__main__":
    main()
