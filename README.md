# `tmx4ml+reup`: TrackMania Exchange for ManiaLinks + Replay Uploader

## Disclaimer
This project is **vibecoded with Gemini AI**. I (**Originalkhawk**) take absolute no responsibility for the code. It should be run entirely at your own risk.

## Credits & Special Thanks
We would like to thank and credit **mamg22** for their incredible work on the original [`tmx4ml`](https://github.com/mamg22/tmx4ml) project, which served as the foundation and core engine for this fork.

---

## Features (added in `+reup`)

* **Auto-Medal Parsing**: Extracts driving time and Track UIDs dynamically from local GBX header metadata, comparing them against official TrackMania Exchange (TMX) target times to automatically compute achieved medals (Author, Gold, Silver, Bronze, or None).
* **Medal Filtering & Pagination**: Filter your local replays dynamically and browse through large records lists using intuitive paginated menus.
* **Direct Replay Upload (Reup)**: Instantly upload local replays to the TrackMania Exchange backend database directly from the ManiaLink browser using a structured secure API multipart form upload flow.

---

## Original `tmx4ml` Features

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
