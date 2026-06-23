# mp3-gallery

Easiest way to host your mp3 collection online — generate a modern static HTML gallery.

## Features

- Clean, responsive design with light/dark themes (no Bootstrap dependency)
- Reads ID3 metadata — title, artist, album and track duration
- Extracts embedded cover art (falls back to a music glyph when none)
- Optional cover-art thumbnails (`generate_thumbnails`) — serves downsized
  480px covers for faster loads while keeping the full-res originals
- Instant client-side search/filter of tracks and folders
- Sticky bottom player bar with scrubber, time, volume, prev/next
- Shuffle and repeat (off / all / one) playback modes
- Editable play queue — "play next" / "add to queue" per track, with a slide-out
  drawer to reorder (drag), remove or clear; persists in the browser
- Theme toggle and resume of the last track + position (saved in the browser)
- Recursive folder navigation

## Requirements

- Python 3
- Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

1. Copy the example config and edit the paths:

```bash
cp config.py.example config.py
```

2. Generate the site:

```bash
python generate.py
```

The generator writes `index.html` (plus one page per subfolder) and the shared
assets in `files/` into your configured `html_folder`. Serve that folder with any
static web server and point `public_path` at where the MP3 files are served from.

## Run with Docker Compose

The Docker setup runs two services defined in `docker-compose.yml`:

- `generator` — builds the image from the `Dockerfile`, reads your MP3
  collection (mounted read-only) to extract tags and cover art, and writes the
  generated gallery into a shared `site` volume. It regenerates on an interval
  so new music is picked up automatically.
- `web` — an `nginx:alpine` container that serves the generated gallery from
  the shared `site` volume.

The MP3 files themselves are not served by these containers — they stay hosted
on your own server. `PUBLIC_PATH` is the external URL the browser uses to fetch
them.

### 1. Configure

Copy the example environment file and edit it:

```bash
cp .env.example .env
```

Settings in `.env`:

| Variable | Required | Description |
| --- | --- | --- |
| `MP3_DIR` | yes | Path on the host to your MP3 collection. Mounted read-only into the generator. |
| `PUBLIC_PATH` | yes | External URL where those MP3 files are already served (e.g. `https://music.example.com/mp3/`). Folder and file names are appended to it. |
| `PORT` | no | Host port the gallery is exposed on (default `8080`). |
| `REFRESH_INTERVAL` | no | Seconds between regenerations to pick up new music (default `3600`). Use `0` to generate once and exit. |
| `SITE_NAME` | no | Title shown in the browser tab and page header. |
| `SITE_LOGO` | no | Logo/emoji shown before the site name. |
| `DOWNLOAD_ICON` | no | Icon/text used for the per-track download link. |
| `GENERATE_THUMBNAILS` | no | `true`/`false` — generate downsized 480px cover thumbnails. |

### 2. Start it

```bash
docker compose up -d --build
```

Open `http://localhost:8080` (or whatever `PORT` you set).

### 3. Operating it

- Regenerate immediately after adding music (instead of waiting for the
  interval):

  ```bash
  docker compose restart generator
  ```

- Follow the generator logs:

  ```bash
  docker compose logs -f generator
  ```

- Stop everything:

  ```bash
  docker compose down
  ```

  Add `-v` to also remove the generated `site` volume.
