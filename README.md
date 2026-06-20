# mp3-gallery

Easiest way to host your mp3 collection online — generate a modern static HTML gallery.

## Features

- 🎨 Clean, responsive design with light/dark themes (no Bootstrap dependency)
- 🏷️ Reads ID3 metadata — title, artist, album and track duration
- 🖼️ Extracts embedded cover art (falls back to a music glyph when none)
- 🔍 Instant client-side search/filter of tracks and folders
- ▶️ Sticky bottom player bar with scrubber, time, volume, prev/next
- 🔀 Shuffle and 🔁 repeat (off / all / one) playback modes
- ☰ Editable play queue — "play next" / "add to queue" per track, with a slide-out
  drawer to reorder (drag), remove or clear; persists in the browser
- 🌙 Theme toggle and resume of the last track + position (saved in the browser)
- 📁 Recursive folder navigation

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
