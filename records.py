import os
import urllib.parse
import json
import asyncio
import re
from datetime import datetime

from aiohttp import web, FormData
from aiohttp.web_request import Request

import maniacode as mc
import tmx
from routes import render_manialink, json_loader


async def records_list(request: Request):
    if request.app.get("site") != "tmnf":
        msg = mc.render_maniacode([mc.ShowMessage("Local autosave replays are only supported on TrackMania Nations Forever (TMNF).")])
        return web.Response(text=msg, content_type="application/xml")

    logged_in_username = request.app.get("logged_in_username")
    if not logged_in_username:
        msg = mc.render_maniacode([mc.ShowMessage("You must be logged in to view your local autosave replays.")])
        return web.Response(text=msg, content_type="application/xml")

    from login import load_config
    config = load_config()
    autosave_location = config.get("autosave_location")

    if not autosave_location:
        msg = mc.render_maniacode([mc.ShowMessage("Local autosave path is not configured. Please use Option 4 in the console before starting the server.")])
        return web.Response(text=msg, content_type="application/xml")

    if not os.path.exists(autosave_location) or not os.path.isdir(autosave_location):
        msg = mc.render_maniacode([mc.ShowMessage(f"Autosave path is invalid or does not exist:\n{autosave_location}")])
        return web.Response(text=msg, content_type="application/xml")

    records = []
    try:
        for entry in os.scandir(autosave_location):
            if entry.is_file() and entry.name.lower().endswith(".gbx"):
                stat = entry.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime)
                size_kb = stat.st_size / 1024
                
                # Format modified date
                mod_str = mtime.strftime("%F %H:%M:%S")
                # Format size
                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{(size_kb/1024):.2f} MB"
                
                # Clean name: remove suffix `.replay.gbx` or `.gbx` case-insensitively
                clean_name = entry.name
                for suffix in [".replay.gbx", ".gbx"]:
                    if clean_name.lower().endswith(suffix):
                        clean_name = clean_name[:-len(suffix)]
                        break
                
                records.append({
                    "name": clean_name,
                    "filename": entry.name,
                    "filename_encoded": urllib.parse.quote(entry.name),
                    "modified": mod_str,
                    "raw_mtime": stat.st_mtime,
                    "size": size_str
                })
        
        # Sort by mtime descending (newest first)
        records.sort(key=lambda r: r["raw_mtime"], reverse=True)
    except Exception as e:
        msg = mc.render_maniacode([mc.ShowMessage(f"Failed to scan autosave location: {e}")])
        return web.Response(text=msg, content_type="application/xml")

    # Filter toggle states (default: "0" / inactive initially)
    show_author = request.query.get("show_author", "0") == "1"
    show_gold = request.query.get("show_gold", "0") == "1"
    show_silver = request.query.get("show_silver", "0") == "1"
    show_bronze = request.query.get("show_bronze", "0") == "1"
    show_none = request.query.get("show_none", "0") == "1"

    def make_toggle_url(param_name):
        return str(request.url.update_query({
            "show_author": "1" if show_author != (param_name == "show_author") else "0",
            "show_gold": "1" if show_gold != (param_name == "show_gold") else "0",
            "show_silver": "1" if show_silver != (param_name == "show_silver") else "0",
            "show_bronze": "1" if show_bronze != (param_name == "show_bronze") else "0",
            "show_none": "1" if show_none != (param_name == "show_none") else "0",
            "page": "1"
        }))

    filters = {
        "author": {"active": show_author, "url": make_toggle_url("show_author")},
        "gold": {"active": show_gold, "url": make_toggle_url("show_gold")},
        "silver": {"active": show_silver, "url": make_toggle_url("show_silver")},
        "bronze": {"active": show_bronze, "url": make_toggle_url("show_bronze")},
        "none": {"active": show_none, "url": make_toggle_url("show_none")},
    }

    # Ensure in-memory track details cache exists on the app
    cache = request.app.setdefault("track_info_cache", {})

    # Parse GBX file headers for ALL files to extract driving time & Track UID
    uids_to_fetch = set()
    best_time_re1 = re.compile(r'<times[^>]+best=["\'](\d+)["\']')
    best_time_re2 = re.compile(r'best=["\'](\d+)["\']')
    uid_re1 = re.compile(r'<ident[^>]+uid=["\']([^"\']+)["\']')
    uid_re2 = re.compile(r'uid=["\']([^"\']+)["\']')

    for r in records:
        r["time_str"] = "N/A"
        r["medal"] = "None"
        r["track_uid"] = None
        r["track_name"] = None
        r["track_id"] = None
        
        file_path = os.path.join(autosave_location, r["filename"])
        try:
            with open(file_path, "rb") as f:
                header_data = f.read(128 * 1024)
            start = header_data.find(b"<header")
            if start != -1:
                end = header_data.find(b"</header>", start)
                if end != -1:
                    xml_str = header_data[start:end+9].decode("utf-8", errors="ignore")
                    
                    time_match = best_time_re1.search(xml_str) or best_time_re2.search(xml_str)
                    if time_match:
                        time_ms = int(time_match.group(1))
                        r["time_ms"] = time_ms
                        r["time_str"] = tmx.format_time(time_ms)
                    
                    uid_match = uid_re1.search(xml_str) or uid_re2.search(xml_str)
                    if uid_match:
                        track_uid = uid_match.group(1)
                        r["track_uid"] = track_uid
                        if track_uid not in cache:
                            uids_to_fetch.add(track_uid)
        except Exception:
            pass

    # Batch/Parallel fetch track data from TMX for all non-cached track UIDs
    if uids_to_fetch:
        session = request.app["client_session"]
        api_url = request.app["api_url"]
        
        async def fetch_track_info(uid):
            try:
                params = {
                    "uid": uid,
                    "fields": "TrackId,TrackName,AuthorTime,GoldTarget,SilverTarget,BronzeTarget",
                    "count": 1
                }
                url = (api_url / "tracks").with_query(params)
                async with session.get(url) as res:
                    if res.status == 200:
                        data = await res.json(loads=json_loader)
                        if data.get("Results"):
                            return uid, data["Results"][0]
            except Exception:
                pass
            return uid, None

        tasks = [fetch_track_info(uid) for uid in uids_to_fetch if uid]
        fetched_results = await asyncio.gather(*tasks)
        for uid, track_info in fetched_results:
            if track_info:
                cache[uid] = track_info
            else:
                cache[uid] = None  # Cache negative results too to avoid spamming the API

    # Map cached info and determine medals for all records
    for r in records:
        uid = r.get("track_uid")
        time_ms = r.get("time_ms")
        if uid and uid in cache:
            track_info = cache[uid]
            if track_info:
                r["track_name"] = track_info.get("TrackName")
                r["track_id"] = track_info.get("TrackId")
                
                try:
                    author_time = int(track_info.get("AuthorTime")) if track_info.get("AuthorTime") is not None else None
                    gold_time = int(track_info.get("GoldTarget")) if track_info.get("GoldTarget") is not None else None
                    silver_time = int(track_info.get("SilverTarget")) if track_info.get("SilverTarget") is not None else None
                    bronze_time = int(track_info.get("BronzeTarget")) if track_info.get("BronzeTarget") is not None else None
                except (ValueError, TypeError):
                    author_time, gold_time, silver_time, bronze_time = None, None, None, None
                
                if time_ms is not None:
                    if author_time is not None and time_ms <= author_time:
                        r["medal"] = "Author"
                    elif gold_time is not None and time_ms <= gold_time:
                        r["medal"] = "Gold"
                    elif silver_time is not None and time_ms <= silver_time:
                        r["medal"] = "Silver"
                    elif bronze_time is not None and time_ms <= bronze_time:
                        r["medal"] = "Bronze"

    # Filter records based on selected options. If no filters are selected, show all by default.
    any_active = show_author or show_gold or show_silver or show_bronze or show_none
    filtered_records = []
    for r in records:
        medal = r.get("medal", "None")
        if any_active:
            if medal == "Author" and not show_author:
                continue
            if medal == "Gold" and not show_gold:
                continue
            if medal == "Silver" and not show_silver:
                continue
            if medal == "Bronze" and not show_bronze:
                continue
            if medal == "None" and not show_none:
                continue
        filtered_records.append(r)

    # Pagination
    try:
        page = int(request.query.get("page", 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    pagesize = 10
    start_idx = (page - 1) * pagesize
    end_idx = start_idx + pagesize
    page_records = filtered_records[start_idx:end_idx]
    has_next = len(filtered_records) > end_idx

    return render_manialink("records.xml", request, {
        "records": page_records,
        "page": page,
        "has_next": has_next,
        "filters": filters
    })


async def play_record(request: Request):
    logged_in_username = request.app.get("logged_in_username")
    if not logged_in_username:
        msg = mc.render_maniacode([mc.ShowMessage("You must be logged in to play replays.")])
        return web.Response(text=msg, content_type="application/xml")

    filename = request.query.get("filename")
    if not filename:
        msg = mc.render_maniacode([mc.ShowMessage("Filename parameter is missing.")])
        return web.Response(text=msg, content_type="application/xml")

    origin = request.url.origin()
    # Construct exact link to records-download
    download_url = str(origin.join(request.app.router["records-download"].url_for().with_query(filename=filename)))
    
    clean_name = filename
    for suffix in [".replay.gbx", ".gbx"]:
        if clean_name.lower().endswith(suffix):
            clean_name = clean_name[:-len(suffix)]
            break

    text = mc.render_maniacode([mc.ViewReplay(clean_name, download_url)])
    return web.Response(text=text, content_type="application/xml")


async def download_record(request: Request):
    logged_in_username = request.app.get("logged_in_username")
    if not logged_in_username:
        raise web.HTTPForbidden(reason="Must be logged in")

    filename = request.query.get("filename")
    if not filename:
        raise web.HTTPBadRequest(reason="Filename parameter is missing")

    from login import load_config
    config = load_config()
    autosave_location = config.get("autosave_location")

    if not autosave_location:
         raise web.HTTPBadRequest(reason="Autosave location is not configured")

    safe_filename = os.path.basename(filename)
    file_path = os.path.join(autosave_location, safe_filename)

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise web.HTTPNotFound(reason="File not found")

    response = web.FileResponse(file_path)
    response.content_type = "application/octet-stream"
    response.headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    return response


async def upload_record(request: Request):
    logged_in_username = request.app.get("logged_in_username")
    if not logged_in_username:
        msg = mc.render_maniacode([mc.ShowMessage("You must be logged in to upload replays.")])
        return web.Response(text=msg, content_type="application/xml")

    filename = request.query.get("filename")
    if not filename:
        msg = mc.render_maniacode([mc.ShowMessage("Filename parameter is missing.")])
        return web.Response(text=msg, content_type="application/xml")

    from login import load_config
    config = load_config()
    autosave_location = config.get("autosave_location")

    if not autosave_location:
         msg = mc.render_maniacode([mc.ShowMessage("Autosave location is not configured.")])
         return web.Response(text=msg, content_type="application/xml")

    safe_filename = os.path.basename(filename)
    file_path = os.path.join(autosave_location, safe_filename)

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        msg = mc.render_maniacode([mc.ShowMessage(f"Replay file '{safe_filename}' not found on disk.")])
        return web.Response(text=msg, content_type="application/xml")

    session = request.app["client_session"]
    base_url = request.app["base_url"]

    # 1. Access the upload page to grab the antiforgery token
    upload_page_url = base_url / "replayupload"
    try:
        async with session.get(upload_page_url) as resp:
            if resp.status != 200:
                msg = mc.render_maniacode([mc.ShowMessage(f"Failed to access the upload page (HTTP Status {resp.status}).")])
                return web.Response(text=msg, content_type="application/xml")
            html = await resp.text()
    except Exception as e:
        msg = mc.render_maniacode([mc.ShowMessage(f"Error accessing exchange server:\n{e}")])
        return web.Response(text=msg, content_type="application/xml")

    af_match = re.search(r'data-antiforgery="([^"]+)"', html)
    if not af_match:
        # fallback search
        af_match = re.search(r'__RequestVerificationToken[^>]+value="([^"]+)"', html)

    if not af_match:
        msg = mc.render_maniacode([mc.ShowMessage("Verification token could not be obtained from exchange server. Please re-authenticate.")])
        return web.Response(text=msg, content_type="application/xml")

    antiforgery_token = af_match.group(1)

    # 2. Upload the replay file via API multipart POST
    api_upload_url = base_url / "api/replays/upload"
    
    data = FormData()
    data.add_field("__RequestVerificationToken", antiforgery_token)
    
    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
            
        data.add_field("file", file_bytes, filename=safe_filename, content_type="application/octet-stream")
        
        async with session.post(api_upload_url, data=data) as upload_resp:
            upload_status = upload_resp.status
            upload_text = await upload_resp.text()
    except Exception as e:
        msg = mc.render_maniacode([mc.ShowMessage(f"Error uploading to the exchange server:\n{e}")])
        return web.Response(text=msg, content_type="application/xml")

    # 3. Present the user with a popup in manialinks reporting upload success or failure
    try:
        upload_result = json.loads(upload_text)
        if "Track" in upload_result:
            track_name = upload_result["Track"].get("TrackName", "Track")
            msg_text = f"Upload Success!\n\nSuccessfully uploaded replay for track:\n{track_name}"
        elif "detail" in upload_result:
            msg_text = f"Upload failed.\n\nReason: {upload_result['detail']}"
        elif "status" in upload_result and upload_result["status"] >= 400:
            detail = upload_result.get("title") or "Validation error"
            msg_text = f"Upload failed.\n\nStatus: {upload_result['status']} - {detail}"
        else:
            msg_text = "Upload finished!"
    except Exception:
        # Fallback for non-JSON status checks
        if upload_status == 200:
            msg_text = "Upload finished successfully!"
        else:
            msg_text = f"Upload failed.\n\nHTTP Server Status Code: {upload_status}"

    msg = mc.render_maniacode([mc.ShowMessage(msg_text)])
    return web.Response(text=msg, content_type="application/xml")
