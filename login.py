import sys
import re
import urllib.parse
import asyncio
from html.parser import HTMLParser
import aiohttp
import json
import os


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


def extract_username_from_usershow(html: str) -> str | None:
    # 1. Match "<div class="dropdown-header">Hi, <b>...</b>!"
    m = re.search(r'Hi,\s*<b>([^<]+)</b>!', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    
    # 2. Match "<title>User Profile: ... | TMNF-X</title>"
    m = re.search(r'<title>User Profile:\s*([^|]+?)\s*\|\s*TMNF-X</title>', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
        
    # 3. Match "<h3 style="display:inline;"><i class="fas fa-user" title=""></i>&nbsp;..."
    m = re.search(r'<i class="fas fa-user"[^>]*></i>\s*&nbsp;\s*([^<\s]+)', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
        
    return None


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
            # Use allow_redirects=True to follow login redirects, establishing
            # state cookies on tmnf.exchange before hitting account.mania.exchange
            async with session.get(trigger, allow_redirects=True) as resp:
                final_url = str(resp.url)
                if "account.mania.exchange" in final_url:
                    login_url = final_url
                    break
                else:
                    # Failover: check headers in intermediate redirect history
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
        current_status = resp.status

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
                
                cookies = [c.key for c in session.cookie_jar]
                if any("Antiforgery" in c or "Session" in c or "Identity" in c or "Cookie" in c for c in cookies) or len(cookies) > 0:
                    # Verification Step: Attempt to load the user's profile verified session
                    try:
                        async with session.get("https://tmnf.exchange/usershow", allow_redirects=True) as verify_resp:
                            verify_html = await verify_resp.text()
                            verify_url = str(verify_resp.url)
                            
                            is_logged_in = False
                            # A successful login response from usershow must return HTTP 200
                            if verify_resp.status == 200:
                                # If we get redirected to a login page, we are not logged in
                                if "login" not in verify_url.lower() and "signin" not in verify_url.lower() and "challenge" not in verify_url.lower():
                                    login_indicators = ("log out", "logout", "sign out", "signout", "hi, <b>")
                                    username_clean = credentials["username"].split("@")[0].lower()
                                    if any(ind in verify_html.lower() for ind in login_indicators) or username_clean in verify_html.lower():
                                        is_logged_in = True
                            
                            if is_logged_in:
                                extracted_name = extract_username_from_usershow(verify_html)
                                if extracted_name:
                                    return extracted_name
                                return credentials["username"].split("@")[0]
                            else:
                                raise ValueError("Session verification failed. Profile page suggests login did not succeed.")
                    except Exception as e:
                        raise ValueError(f"Session verification check failed: {e}")
                else:
                    return
        elif parser_callback.action:
            # Check if this form has any password input. If so, it's the login form itself (failed login or returned)
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
                current_status = resp.status
        else:
            # No form to follow
            break

    if "Invalid login attempt" in redirected_html or "invalid" in redirected_html.lower() or email_key in parser_callback.inputs:
        raise ValueError("Invalid email or password. Please check your credentials.")
    else:
        raise ValueError("OIDC redirection failed. Please verify your credentials and try again.")


async def run_cli_loop():
    cookie_jar = aiohttp.CookieJar(unsafe=True)
    while True:
        print("\n=============================================")
        print("           TrackMania Exchange tmx4ml")
        print("=============================================")
        print("Please select an option:")
        print("  1) Log in to tmnf.exchange")
        print("  2) Start the server without logging in")
        print("  3) Exit")
        print("---------------------------------------------")
        try:
            choice = input("Option [1-3]: ").strip().lower()
        except EOFError:
            print("\nNon-interactive or EOF detected. Starting server without logging in...")
            return "start_unauth", None, None

        if choice == "1":
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
                    extracted_username = await perform_exchange_login(session, {"username": username, "password": password})
                    if not extracted_username:
                        extracted_username = username.split("@")[0]
                    logged_in = True
                except Exception as e:
                    print(f"\n⚠️ Login failed: {e}")
                    continue

            if logged_in:
                print("\n=============================================")
                print(f"Welcome {extracted_username}!")
                print("=============================================")
                
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
                        return "start_auth", cookie_jar._cookies, extracted_username
                    elif auth_choice == "2":
                        cookie_jar.clear()
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

        elif choice == "2":
            print("Starting server without logging in...")
            return "start_unauth", None, None
        elif choice == "3":
            print("Exiting...")
            sys.exit(0)
        else:
            print("Invalid option. Please choose 1, 2, or 3.")
