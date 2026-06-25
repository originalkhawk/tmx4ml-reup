import sys
import re
import urllib.parse
import asyncio
from html.parser import HTMLParser
import aiohttp
import json
import os
import socket
import uuid
import hashlib
import base64


def load_config():
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(config):
    try:
        with open("config.json", "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")


def get_system_key() -> str:
    try:
        hostname = socket.gethostname()
        node = str(uuid.getnode())
        return f"{hostname}-{node}"
    except Exception:
        return "fallback-tmx4ml-key"


def _get_key_stream(key: bytes, length: int, salt: bytes) -> bytes:
    stream = b""
    counter = 0
    while len(stream) < length:
        h = hashlib.sha256(key + salt + str(counter).encode()).digest()
        stream += h
        counter += 1
    return stream[:length]


def encrypt_password(password: str, key_str: str) -> str:
    password_bytes = password.encode('utf-8')
    salt = os.urandom(16)
    key_bytes = key_str.encode('utf-8')
    keystream = _get_key_stream(key_bytes, len(password_bytes), salt)
    ciphertext = bytes(p ^ k for p, k in zip(password_bytes, keystream))
    combined = salt + ciphertext
    return base64.b64encode(combined).decode('utf-8')


def decrypt_password(encrypted_str: str, key_str: str) -> str:
    try:
        combined = base64.b64decode(encrypted_str.encode('utf-8'))
        if len(combined) < 16:
            return ""
        salt = combined[:16]
        ciphertext = combined[16:]
        key_bytes = key_str.encode('utf-8')
        keystream = _get_key_stream(key_bytes, len(ciphertext), salt)
        password_bytes = bytes(c ^ k for c, k in zip(ciphertext, keystream))
        return password_bytes.decode('utf-8')
    except Exception:
        return ""


def get_secret_key():
    config = load_config()
    if "secret_key" not in config:
        config["secret_key"] = uuid.uuid4().hex
        save_config(config)
    return config["secret_key"]



class LoginFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current_form = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "form":
            action = attrs_dict.get("action")
            method = attrs_dict.get("method", "post").lower()
            self.current_form = {
                "action": action,
                "method": method,
                "inputs": {}
            }
            self.forms.append(self.current_form)
        elif tag in ("input", "button") and self.current_form is not None:
            name = attrs_dict.get("name")
            val = attrs_dict.get("value", "")
            input_type = attrs_dict.get("type", "text").lower()
            if name:
                self.current_form["inputs"][name] = {
                    "value": val,
                    "type": input_type
                }

    def handle_endtag(self, tag):
        if tag == "form":
            self.current_form = None

    def get_login_form(self):
        # 1. Search for a form that has a password field and is not fidologin
        for form in self.forms:
            has_password = False
            for name, inp in form["inputs"].items():
                if inp["type"] == "password" or "password" in name.lower():
                    has_password = True
                    break
            
            action = form["action"] or ""
            if has_password and "fidologin" not in action.lower():
                return form

        # Fallback 1: any form with "password" in input names
        for form in self.forms:
            for name in form["inputs"].keys():
                if "password" in name.lower():
                    return form

        # Fallback 2: first form found
        if self.forms:
            return self.forms[0]
        
        return None

    @property
    def action(self):
        form = self.get_login_form()
        return form["action"] if form else None

    @property
    def inputs(self):
        form = self.get_login_form()
        if not form:
            return {}
        return {name: inp["value"] for name, inp in form["inputs"].items()}


def extract_account_username(html: str) -> str | None:
    # Match the login/account page header content
    m = re.search(r'Hi,\s*<b>([^<]+)</b>!', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    m = re.search(r'<h3>\s*Hello\s+([^<]+)!', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return None


async def verify_account_links(session: aiohttp.ClientSession) -> dict[str, bool | str | None]:
    account_url = "https://account.mania.exchange/account"
    try:
        async with session.get(account_url, allow_redirects=True) as resp:
            html = await resp.text()
            final_url = str(resp.url)
            status = resp.status

        if status != 200:
            return {"tmnf": False, "tmuf": False, "username": None}

        if any(part in final_url.lower() for part in ("login", "signin", "challenge")):
            return {"tmnf": False, "tmuf": False, "username": None}

        html_lower = html.lower()
        has_tmnf = "tmnf-x" in html_lower and "trackmania nations forever exchange" in html_lower
        has_tmuf = "tmuf-x" in html_lower and "trackmania united forever exchange" in html_lower

        username = extract_account_username(html)
        return {
            "tmnf": has_tmnf,
            "tmuf": has_tmuf,
            "username": username,
        }
    except Exception:
        return {"tmnf": False, "tmuf": False, "username": None}


async def perform_exchange_login(session: aiohttp.ClientSession, credentials: dict[str, str]):
    base_login_url = "https://account.mania.exchange/login?ReturnUrl=%2Fconnect%2Fauthorize%2Fcallback%3Fclient_id%3Dfirstparty%26redirect_uri%3Dhttps%253A%252F%252Ftmnf.exchange%252Fsignin-oidc%26response_type%3Dcode%26scope%3Dopenid%2520profile%26code_challenge%3DfD1HagwlZYhlLTUf3HK-_lqBc3h2q3xf92FWROSc0Ic%26code_challenge_method%3DS256%26response_mode%3Dform_post%26nonce%3D639163700039728978.YmFjYTU5MDktNjE0OS00NGIyLTkxMWEtMTkyMWNmNWFiMGFkNzdjMTkwNjUtNTJhOC00OWM3LWIxZWBe5fMTkwNjUtNTJhOC00OWM3LWIxZWItNTBlYzZjYTA2MTc4%26state%3DCfDJ8L8oiDAKgJRNk-l5Ph_C6BoX7oelN-wl9i3oRKgNvVTGb875sth5Ck3sgOzrGj2Qdic_898FjEm2zphlQH9NnBtLoIDVVQuHBOs7ghpgoR1m80BL2WSLxwf94d3W4_DXTy5AQUvQ5fwSdODlDXsIKhEriK9MrctabznyvbIzoeLxiIeUEsFYfRZeOWxvPfCzYt1n84MrKIfb4Zl4z22PjM-kQTubc8fs1ITG0hQdc9C1vXpkNIfDrK8N5XrtvUAKMGoqSf0fY90MZujYqCP-wmU6B8X0l3ryK9ZdGGr7fZpSR8KvUTxGGbTWnNGD-Zo9NTxOhviLk5vQygEqskqMR69qt1ofnTnk9hi534Qj9wvw5S_0vxkx43ILEG_jY37bW1swmcZn35EdElzC7RuZRbPYjsNz7RZi7noYuW8SJKfLfqOellU1jmxBv4Onk3YREyUXDxWoQN5OdSPXH6qAY%26x-client-SKU%3DID_NET8_0%26x-client-ver%3D7.1.2.0"

    login_url = None
    triggers = [
        "https://tmnf.exchange/trackupload",
        "https://tmnf.exchange/replayupload",
        "https://tmnf.exchange/Account/Challenge",
        "https://tmnf.exchange/login",
        "https://tmnf.exchange/Challenge",
        "https://tmnf.exchange/Account/Login",
        "https://tmnf.exchange/main/login",
        "https://tmnf.exchange/signin",
    ]
    for trigger in triggers:
        try:
            async with session.get(trigger, allow_redirects=True) as resp:
                final_url = str(resp.url)
                if "account.mania.exchange" in final_url:
                    login_url = final_url
                    break
                else:
                    for h in resp.history:
                        loc = h.headers.get("Location")
                        if loc and "account.mania.exchange" in loc:
                            login_url = urllib.parse.urljoin(str(h.url), loc)
                            break
                    if login_url:
                        break
        except Exception:
            pass

    if not login_url:
        login_url = base_login_url

    print("Authenticating with TrackMania Exchange...")
    async with session.get(login_url) as resp:
        html = await resp.text()

    parser = LoginFormParser()
    parser.feed(html)

    email_key = None
    pass_key = None
    for k in parser.inputs.keys():
        if "email" in k.lower() or "username" in k.lower():
            email_key = k
        elif "password" in k.lower():
            pass_key = k

    if not email_key:
        email_key = "Input.Email"
    if not pass_key:
        pass_key = "Input.Password"

    post_data = dict(parser.inputs)
    post_data[email_key] = credentials["username"]
    post_data[pass_key] = credentials["password"]
    if "Input.RememberMe" in post_data:
        post_data["Input.RememberMe"] = "true"

    post_url = urllib.parse.urljoin(login_url, parser.action or "/login")

    async with session.post(post_url, data=post_data, allow_redirects=True) as resp:
        redirected_html = await resp.text()
        current_url = str(resp.url)

    max_redirects = 15
    redirects_followed = 0
    parser_callback = LoginFormParser()

    while redirects_followed < max_redirects:
        parser_callback = LoginFormParser()
        parser_callback.feed(redirected_html)

        if parser_callback.action and "signin-oidc" in parser_callback.action:
            callback_url = urllib.parse.urljoin(current_url, parser_callback.action)
            async with session.post(callback_url, data=parser_callback.inputs, allow_redirects=True) as tmnf_resp:
                await tmnf_resp.text()

            account_status = await verify_account_links(session)
            if account_status.get("username") or account_status.get("tmnf") or account_status.get("tmuf"):
                return {
                    "tmnf": account_status.get("tmnf", False),
                    "tmuf": account_status.get("tmuf", False),
                    "username": account_status.get("username") or credentials["username"],
                }
            raise ValueError("Session verification failed for both TMNF and TMUF.")
        elif parser_callback.action:
            selected_form = parser_callback.get_login_form()
            has_password = False
            if selected_form:
                for name, inp in selected_form["inputs"].items():
                    if inp["type"] == "password" or "password" in name.lower():
                        has_password = True
                        break

            if has_password:
                break

            intermediate_url = urllib.parse.urljoin(current_url, parser_callback.action)
            redirects_followed += 1

            async with session.post(intermediate_url, data=parser_callback.inputs, allow_redirects=True) as resp:
                redirected_html = await resp.text()
                current_url = str(resp.url)
        else:
            break

    if "Invalid login attempt" in redirected_html or "invalid" in redirected_html.lower() or email_key in parser_callback.inputs:
        raise ValueError("Invalid email or password. Please check your credentials.")
    else:
        raise ValueError("OIDC redirection failed. Please verify your credentials and try again.")


async def run_cli_loop():
    cookie_jar = aiohttp.CookieJar(unsafe=True)
    while True:
        config = load_config()
        saved_username = config.get("saved_username") or config.get("logged_in_username")
        has_saved = bool(saved_username)

        print("\n=============================================")
        print("           TrackMania Exchange tmx4ml")
        print("=============================================")
        print("Please select an option:")
        if has_saved:
            print(f"  1) Start the server with saved session ({saved_username})")
            print("  2) Log in with a different account")
            print("  3) Start the server without logging in")
            print("  4) Exit")
        else:
            print("  1) Log in to tmnf.exchange")
            print("  2) Start the server without logging in")
            print("  3) Exit")
        print("---------------------------------------------")
        try:
            prompt_range = "[1-4]" if has_saved else "[1-3]"
            choice = input(f"Option {prompt_range}: ").strip().lower()
        except EOFError:
            print("\nNon-interactive or EOF detected. Starting server...")
            return "start_unauth", None, None, {"tmnf": False, "tmuf": False}

        # Normalize choices based on whether saved option is active
        if has_saved:
            if choice == "1":
                # Load the saved session from config
                from main import deserialize_cookies
                saved_cookies = deserialize_cookies(config.get("cookies_data"))
                saved_site_access = config.get("site_access", {"tmnf": False, "tmuf": False})
                return "start_auth", saved_cookies, saved_username, saved_site_access
            elif choice == "2":
                # Go to login flow
                pass
            elif choice == "3":
                print("Starting server without logging in...")
                return "start_unauth", None, None, {"tmnf": False, "tmuf": False}
            elif choice == "4":
                print("Exiting...")
                sys.exit(0)
            else:
                print("Invalid option. Please select 1, 2, 3, or 4.")
                continue
        else:
            if choice == "1":
                # Go to login flow
                pass
            elif choice == "2":
                print("Starting server without logging in...")
                return "start_unauth", None, None, {"tmnf": False, "tmuf": False}
            elif choice == "3":
                print("Exiting...")
                sys.exit(0)
            else:
                print("Invalid option. Please select 1, 2, or 3.")
                continue

        # If we reached here, we are doing a new login
        try:
            username = input("Username/Email: ").strip()
            import getpass
            password = getpass.getpass("Password (hidden): ")
        except EOFError:
            print("\nError: EOF reading input. Returning to main menu.")
            continue

        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        async with aiohttp.ClientSession(connector=connector, cookie_jar=cookie_jar) as session:
            try:
                login_results = await perform_exchange_login(session, {"username": username, "password": password})

                tmnf_ok = bool(login_results.get("tmnf", False))
                tmuf_ok = bool(login_results.get("tmuf", False))
                account_name = login_results.get("username") or username.split("@")[0]

                if tmnf_ok or tmuf_ok:
                    if tmnf_ok and tmuf_ok:
                        print(f"✔️ {account_name} (TMNF) | ✔️ {account_name} (TMUF)")
                        site_access = {"tmnf": True, "tmuf": True}
                    elif tmnf_ok:
                        print(f"✔️ {account_name} (TMNF) | ❌ TMUF - please link your account on TMUF.Exchange")
                        site_access = {"tmnf": True, "tmuf": False}
                    else:
                        print(f"❌ TMNF - please link your account on TMNF.Exchange | ✔️ {account_name} (TMUF)")
                        site_access = {"tmnf": False, "tmuf": True}
                    display_username = account_name
                    return_username = account_name
                    logged_in = True
                else:
                    print("❌ TMNF | ❌ TMUF | FAILED TO LOG IN ⚠️")
                    cookie_jar.clear()
                    continue
            except Exception as e:
                print(f"\n⚠️ Login failed: {e}")
                cookie_jar.clear()
                continue

        if logged_in:
            print("\n=============================================")
            print(f"Welcome {display_username}!")
            print("=============================================")

            # Optional choice to save credentials
            try:
                save_creds = input("Would you like to save your encrypted credentials to auto-renew your session? [y/N]: ").strip().lower()
                if save_creds in ("y", "yes"):
                    secret_key = get_secret_key()
                    system_key = get_system_key()
                    final_key = system_key + secret_key
                    encrypted_pw = encrypt_password(password, final_key)
                    
                    config = load_config()
                    config["saved_username"] = username
                    config["saved_password_encrypted"] = encrypted_pw
                    save_config(config)
                    print("Credentials encrypted and saved successfully.")
                else:
                    config = load_config()
                    config.pop("saved_username", None)
                    config.pop("saved_password_encrypted", None)
                    save_config(config)
            except EOFError:
                pass

            # Authenticated menu helper loop
            while True:
                config = load_config()
                has_autosave = bool(config.get("autosave_location"))
                print("Please select an option:")
                print("  1) Start the server")
                print("  2) Log out")
                print("  3) Exit")
                if not has_autosave:
                    print("  4) Set Autosave Location")
                print("---------------------------------------------")
                try:
                    prompt = "Option [1-4]: " if not has_autosave else "Option [1-3]: "
                    auth_choice = input(prompt).strip().lower()
                except EOFError:
                    print("\nNon-interactive or EOF detected. Shuts down.")
                    sys.exit(0)

                if auth_choice == "1":
                    return "start_auth", cookie_jar._cookies, return_username, site_access
                elif auth_choice == "2":
                    cookie_jar.clear()
                    config = load_config()
                    config.pop("cookies_data", None)
                    config.pop("logged_in_username", None)
                    config.pop("site_access", None)
                    config.pop("saved_username", None)
                    config.pop("saved_password_encrypted", None)
                    save_config(config)
                    print("\nLogged out successfully.")
                    break # breaks auth loop, goes back to main menu
                elif auth_choice == "3":
                    print("Exiting...")
                    sys.exit(0)
                elif auth_choice == "4" and not has_autosave:
                    try:
                        path_input = input("Enter TrackMania autosave folder path: ").strip()
                        if path_input:
                            config["autosave_location"] = path_input
                            save_config(config)
                            print("Autosave location saved successfully!")
                        else:
                            print("Autosave location cannot be empty.")
                    except EOFError:
                        print("\nError: EOF reading input.")
                    continue
                else:
                    if not has_autosave:
                        print("Invalid option. Please choose 1, 2, 3, or 4.")
                    else:
                        print("Invalid option. Please choose 1, 2, or 3.")
