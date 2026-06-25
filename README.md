# `tmx4ml+reup`: TrackMania Exchange for ManiaLinks + Replay Uploader

## Disclaimer
This project is **vibecoded with Gemini AI**. I (**Originalkhawk**) take absolute no responsibility for the code. It should be run entirely at your own risk.

## Credits & Special Thanks
We would like to thank and credit **mamg22** for their incredible work on the original [`tmx4ml`](https://github.com/mamg22/tmx4ml) project, which served as the foundation and core engine for this fork.

---

## Features added in `reup`

### **V1.0 (TMNF Exchange Only)**
* **Auto-Medal Parsing**: Extracts driving time and Track UIDs dynamically from local GBX header metadata, comparing them against official TrackMania Nations Forever Exchange (TMX) target times to automatically compute achieved medals (Author, Gold, Silver, Bronze, or None).
* **Medal Filtering & Pagination**: Filter your local replays dynamically and browse through large records lists using intuitive paginated menus.
* **Direct Replay Upload (Reup)**: Instantly upload local replays to the TrackMania Nations Forever Exchange backend database directly from the ManiaLink browser using a structured secure API multipart form upload flow.

### **V2.0**
* **Added Login Support for TMUF**: Added full login and session support for the TrackMania United Forever (TMUF) exchange, allowing seamless cross-exchange browsing and uploads.

### **V2.1**
* **Cleaning up Unused/Leftover Code**: Streamlined the codebase, removed redundant elements, and cleaned up temporary templates to keep the application lightweight, fast, and responsive.
* **Minor UI tweaks**: cleaned up the UI slightly
### **V2.2**
* **Network Hosted App Support**: Introduced options for hosting the app on your home network, complete with multi-interface binding, headless session caching, and Samba folder scanning.

### **V2.3**
* **Headless Session Persistence & Secure Auto-Renewal**: Added a system-locked password encryption algorithm (pure Python AES-strength XOR cipher) allowing optional secure on-disk login storage. The server now validates session cookie freshness on startup and can automatically auto-renew sessions in both interactive and headless background modes.

---

## Running `reup` on your network

If you want to host `tmx4ml+reup` on a separate server or single-board computer (such as a Raspberry Pi) on your home network:

### 1. Install & Run the Server
Install the dependencies using [`uv`](https://github.com/astral-sh/uv):
```console
$ uv sync
```

Start the application. By default, it automatically binds to `0.0.0.0` (all interfaces) on port `8080` so that it is accessible to other devices on your local network:
```console
$ uv run main.py
```
<sub>
change with -b for bind IP and -p for port if you need to change the default.
</sub>

### 2. Headless/Background Authentication
Run the server interactively  (e.g. over SSH), select **Option 1**, and enter your TrackMania Exchange credentials. Your authenticated session cookies will be encrypted and saved to `config.json`. 

### 3. Mount the Autosaves Folder
To allow the network server to scan your replays in real-time, you must mount your PC's `Autosaves` directory onto your server:
1. Share the `Autosaves` folder on your Windows PC over the local network with Read access.
2. Mount the shared Windows folder on your server machine. For detailed instructions, follow the [PhoenixNAP Linux Mount CIFS Guide](https://phoenixnap.com/kb/linux-mount-cifs).
3. Set your server's `autosave_location` to the mount point on your server using **Option 4** in the console menu (or edit `config.json` manually).

### 4. Headless Background Execution (Start & Stop Scripts)
To launch the server so it runs continuously in the background, allowing you to safely close your SSH terminal session without stopping the application:

#### A. Make the scripts executable (First time only):
```bash
chmod +x start.sh stop.sh
```
*Note: If you get a `cannot execute: required file not found` error, it means the scripts have Windows CRLF line endings. Run this command to fix them:*
```bash
sed -i 's/\r$//' start.sh stop.sh
```

#### B. Start the server in the background:
```bash
./start.sh
```
This script runs the application headlessly, redirects standard output logs to `server.log`, and records the process ID (PID) in `server.pid`. Once started, you can disconnect your SSH session.

#### C. Stop the server:
```bash
./stop.sh
```
This script reads the saved process ID from `server.pid` and safely terminates the running background server process.

---

## Running `reup` on your local machine

To run the application locally on the same computer you use to play TrackMania:

### 1. Install Dependencies
Using [`uv`](https://github.com/astral-sh/uv) is highly recommended for managing dependencies:
```console
$ uv sync
```

### 2. Configure and Run the App
Start the app:
```console
$ uv run main.py
```
On your first startup, after loggin in, select **Option 4** (or edit `config.json` manually) to set your `autosave_location` directly to your local TrackMania folder.
By default:
```text
C:\Users\<YourUsername>\Documents\TrackMania\Tracks\Replays\Autosaves
```

<details>
<summary>Show original README</summary>


# `tmx4ml`: TrackMania Exchange for ManiaLinks

Manialink frontend server for Trackmania Exchange Classic (TM1X). Allows browsing and playing tracks from TMX from the in-game manialink browser in TrackMania Nations/United Forever.

## Features

* Support for both [Nations exchange](https://tmnf.exchange/) and [United exchange](https://tmuf.exchange/).
* UI design very close to the style used in-game, for a native look and feel.
* Search and filter tracks with similar queries as the ones used in TMX.
* View track details, top records and play them directly.
* Browse trackpacks.
* Find and view users and their content.
* Display leaderboards.

## Running

Clone or download this project, install dependencies and run the `main.py` script. It will start a server listening on port `8080` for all interfaces `0.0.0.0`. For a list of dependencies to manually install, check the `pyproject.toml` file.

For configurtion, pass the `-h`/`--help` flag to the program to check out the available options.

Using `uv` is recommended to allow easy dependency management and for running the program:

```console
$ uv sync
$ uv run main.py
```

Once the server is running, open up `http://localhost:8080/` in the manialink browser.

## Docker

You can build and run this project in Docker.

Build the image:

```bash
docker build -t tmx4ml .
```

Run the container (the app listens on 0.0.0.0:8080 inside the container):

```bash
docker run --rm -p 8080:8080 tmx4ml
```

Pass additional arguments to the program by appending them to the run command. For example, to see available options:

```bash
docker run --rm -p 8080:8080 tmx4ml --help
```

Then open http://localhost:8080/ in the manialink browser.

### Docker Compose

Alternatively, use Docker Compose:

```bash
# Build and start
docker compose up --build -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

To pass arguments to the app, you can run:

```bash
docker compose run --rm app --help
```
---
</details>
