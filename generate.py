# Scan a folder and generate HTML files with links to the MP3 files in that folder recursively.

import os
import glob
import hashlib
import html
import re
import time
from collections import Counter
from datetime import datetime
from urllib.parse import quote


def url_path(path):
    """Percent-encode a path for safe use in an href (e.g. ``%`` -> ``%25``,
    spaces -> ``%20``), preserving ``/`` separators."""
    return html.escape(quote(path, safe='/'))


def page_href(file_name):
    """Href for an internal page link. The root page (``index.html``) links to
    ``/`` so the home URL stays clean and the server auto-serves index.html;
    other pages keep their (percent-encoded) filename."""
    if file_name == 'index.html':
        return '/'
    return url_path(file_name)

import config

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow only needed for thumbnails
    Image = None


COVERS_SUBDIR = os.path.join('files', 'covers')

# Longest-edge size (px) for generated cover thumbnails. Matches the largest
# the cover ever renders (the grid "big image" view) scaled for HiDPI displays.
THUMB_MAX_PX = 480

# Standalone cover image extensions, in preference order.
_IMAGE_EXTS = ('jpg', 'jpeg', 'png', 'webp', 'gif')

# Substrings that mark an image as a non-cover scan; never auto-picked as a
# last-resort cover.
_NON_COVER_HINTS = ('back', 'inside', 'booklet', 'spek', 'spectrum',
                    'disc', 'cd', 'tray', 'matrix', 'inlay', 'sticker',
                    'obi', 'rear')

# Audio file extensions to include (lowercase, matched case-insensitively).
# Limited to formats an HTML5 <audio> element can actually play in modern
# browsers, so every listed track is playable rather than a broken link.
AUDIO_EXTS = (
    '.mp3',                              # MPEG audio
    '.m4a', '.m4b', '.aac',             # AAC / ALAC (MP4 container, audiobooks, raw ADTS)
    '.flac',                             # FLAC
    '.ogg', '.oga', '.opus',            # Ogg Vorbis / Opus
    '.wav', '.wave',                     # PCM WAVE
    '.aiff', '.aif', '.aifc',           # AIFF
    '.webm', '.weba',                    # WebM / Matroska audio
)


def count_mp3_files(path):
    total = 0
    for _root, _dirs, files in os.walk(path):
        total += sum(1 for f in files if f.lower().endswith(AUDIO_EXTS))
    return total


def get_mp3_files(local_path):
    mp3_files = sorted([f for f in os.listdir(local_path) if f.lower().endswith(AUDIO_EXTS)])
    return mp3_files


def folder_has_audio(local_path):
    """True if this folder or any descendant contains an audio file."""
    for _root, _dirs, files in os.walk(local_path):
        if any(f.lower().endswith(AUDIO_EXTS) for f in files):
            return True
    return False


def get_folders(local_path):
    """List subfolders that contain audio (recursively).

    Art-only folders (e.g. a ``Cover`` folder holding just images) are skipped
    so they are never rendered or linked; their art is still reused via
    :func:`find_folder_cover`.
    """
    folders = sorted([f for f in os.listdir(local_path) if os.path.isdir(os.path.join(local_path, f))])
    return [f for f in folders if folder_has_audio(os.path.join(local_path, f))]


def clean_title_from_filename(filename):
    name = os.path.splitext(filename)[0]
    name = name.replace('_', ' ').replace('-', ' ')
    return ' '.join(name.split()).strip() or filename


def slugify(name):
    """Turn a folder name into a clean, URL-friendly slug.

    Lowercases, replaces every run of non-alphanumeric characters (spaces,
    punctuation, etc.) with a single ``-``, and trims leading/trailing dashes so
    the resulting ``.html`` filenames don't need ugly percent-encoding.
    """
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return slug or 'untitled'


def reserve_html_name(slug, generated):
    """Return a unique ``<slug>.html`` name and record it in ``generated``.

    Pages are written flat in one folder, so distinct source folders can slug to
    the same name (e.g. ``Album 1`` and ``Album-1``, or same-named folders under
    different parents). Collisions get a ``-2``, ``-3``, … suffix; ``index.html``
    is reserved for the root page.
    """
    i = 2
    name = f'{slug}.html'
    while name in generated or name == 'index.html':
        name = f'{slug}-{i}.html'
        i += 1
    generated.add(name)
    return name


def format_elapsed(seconds):
    """Human-readable elapsed run time, e.g. ``3.2 s`` or ``1 min 05 s``."""
    seconds = max(0.0, float(seconds or 0))
    if seconds < 60:
        return f'{seconds:.1f} s'
    minutes, secs = divmod(int(round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours} h {minutes:02d} min'
    return f'{minutes} min {secs:02d} s'


def format_filesize(num_bytes):
    """Human-readable byte size, e.g. ``48.3 GB``."""
    size = float(num_bytes or 0)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            if unit == 'B':
                return f'{int(size)} {unit}'
            return f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} TB'


def _thumb_path(dest_path):
    """Path of the downsized ``<name>_cover_art<ext>`` sibling for a cover."""
    base, ext = os.path.splitext(dest_path)
    return f'{base}_cover_art{ext}'


def _make_thumbnail(dest_path):
    """Create a downsized ``<name>_cover_art<ext>`` sibling of a saved cover.

    Resizes to at most ``THUMB_MAX_PX`` on the longest edge (aspect preserved,
    never upscaled) and returns the thumbnail's basename, or ``None`` if Pillow
    is unavailable or the image can't be processed. An existing thumbnail is
    left untouched (not regenerated).
    """
    base, ext = os.path.splitext(dest_path)
    thumb_path = _thumb_path(dest_path)
    if os.path.exists(thumb_path):
        return os.path.basename(thumb_path)
    if Image is None:
        return None
    try:
        with Image.open(dest_path) as im:
            im.thumbnail((THUMB_MAX_PX, THUMB_MAX_PX))
            if ext.lower() in ('.jpg', '.jpeg') and im.mode in ('RGBA', 'LA', 'P'):
                im = im.convert('RGB')
            im.save(thumb_path)
    except Exception:
        return None
    return os.path.basename(thumb_path)


def _cover_web_path(dest):
    """Web path for a saved cover ``dest``. When ``generate_thumbnails`` is
    enabled, generate (once) a downsized ``_cover_art`` thumbnail, drop the
    full-size original, and publish only the thumbnail."""
    fname = os.path.basename(dest)
    if getattr(config, 'generate_thumbnails', False):
        thumb = _make_thumbnail(dest)
        if thumb and thumb != fname:
            fname = thumb
            # The full-size original is only needed as a thumbnail source.
            try:
                os.remove(dest)
            except OSError:
                pass
    return f'{COVERS_SUBDIR.replace(os.sep, "/")}/{fname}'


def _thumbnail_only():
    """True when thumbnails are generated and full-size covers are not kept."""
    return getattr(config, 'generate_thumbnails', False) and Image is not None


def _save_cover_file(src_path, covers_dir):
    """Copy a standalone image file into covers_dir, return its web path or None."""
    if not src_path:
        return None
    ext = os.path.splitext(src_path)[1].lstrip('.').lower() or 'jpg'
    digest = hashlib.sha1(os.path.abspath(src_path).encode('utf-8')).hexdigest()[:16]
    fname = f'{digest}.{ext}'
    dest = os.path.join(covers_dir, fname)
    if _thumbnail_only() and os.path.exists(_thumb_path(dest)):
        return _cover_web_path(dest)
    if not os.path.exists(dest):
        try:
            with open(src_path, 'rb') as src, open(dest, 'wb') as fh:
                fh.write(src.read())
        except OSError:
            return None
    return _cover_web_path(dest)


def _best_cover_in_dir(local_path):
    """Return the abs path to the best standalone cover image directly in a
    single folder, or None.

    Only known cover-style filenames are considered so that incidental images
    (back/inside/booklet/spectrum scans) are never picked.
    """
    try:
        entries = [f for f in os.listdir(local_path)
                   if os.path.isfile(os.path.join(local_path, f))]
    except OSError:
        return None

    # Index images by (lowercase stem, lowercase ext) for quick lookup.
    images = []
    for name in entries:
        stem, ext = os.path.splitext(name)
        ext = ext.lstrip('.').lower()
        if ext in _IMAGE_EXTS:
            images.append((stem.lower(), ext, name))

    if not images:
        return None

    folder_stem = os.path.basename(os.path.normpath(local_path)).lower()

    # Predicates in priority order; first matching group wins.
    matchers = [
        lambda s: s == 'cover',
        lambda s: s == 'folder',
        lambda s: s == 'front',
        lambda s: s.startswith('albumart') and 'large' in s,
        lambda s: s.startswith('albumart'),
        lambda s: s == 'album',
        lambda s: s == folder_stem,
    ]

    for matches in matchers:
        candidates = [img for img in images if matches(img[0])]
        if candidates:
            # Tie-break by extension preference order.
            candidates.sort(key=lambda img: _IMAGE_EXTS.index(img[1]))
            return os.path.join(local_path, candidates[0][2])

    # Last resort: any image whose name isn't an obvious non-cover scan, so art
    # is found regardless of how it's named.
    leftovers = [img for img in images
                 if not any(h in img[0] for h in _NON_COVER_HINTS)]
    if leftovers:
        leftovers.sort(key=lambda img: (_IMAGE_EXTS.index(img[1]), img[0]))
        return os.path.join(local_path, leftovers[0][2])
    return None


def find_folder_cover(local_path):
    """Return the abs path to the best cover image for this folder, or None.

    Looks in the folder itself first, then falls back to any art-only
    subfolder (e.g. a ``Cover`` folder that holds only images and no audio),
    so cover art is reused even though such folders are not listed.
    """
    cover = _best_cover_in_dir(local_path)
    if cover:
        return cover

    try:
        subdirs = sorted(f for f in os.listdir(local_path)
                         if os.path.isdir(os.path.join(local_path, f)))
    except OSError:
        return None

    for sub in subdirs:
        sub_path = os.path.join(local_path, sub)
        if folder_has_audio(sub_path):
            continue
        cover = _best_cover_in_dir(sub_path)
        if cover:
            return cover
    return None


def extract_metadata(local_file_path, filename, covers_dir, folder_cover_url=None):
    """Return display metadata derived without opening the audio file.

    Reading ID3/tag metadata and embedded cover art meant opening every file —
    the dominant cost of generation, especially over a network share — so it is
    intentionally not done. Titles come from the filename and cover art from
    standalone folder images (``folder_cover_url``) only.
    """
    return {
        'title': clean_title_from_filename(filename),
        'artist': '',
        'album': '',
        'duration': '',
        'cover_url': folder_cover_url,
    }


def header_html(file_name, mp3_files, parent_file_name=None, display_name=None):
    title = html.escape(config.site_name)
    head = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{title}</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
        <link rel="stylesheet" href="files/style.css">
        <link rel="icon" type="image/x-icon" href="https://icons.iconarchive.com/icons/icondesigner.net/hyperion/32/Sidebar-Music-icon.png">
    </head>
    <body>
        <header class="topbar">
            <div class="topbar-inner">
    """.format(title=title)

    if file_name != 'index.html':
        head += """
                <a id="backButton" href="{href}" class="icon-btn" title="Back" aria-label="Back">‹</a>
                <h1 class="site-title"><span class="folder-glyph">📁</span> {name}</h1>
        """.format(href=page_href(parent_file_name or 'index.html'),
                   name=html.escape(display_name if display_name is not None
                                    else file_name.replace('.html', '')))
    else:
        head += """
                <h1 class="site-title"><span class="site-logo">{logo}</span> {name}</h1>
        """.format(logo=html.escape(config.site_logo), name=title)

    add_folder_btn = ''
    if mp3_files:
        add_folder_btn = (
            '<button id="addFolderButton" type="button" class="icon-btn" '
            'title="Add this folder to the queue" aria-label="Add this folder to the queue">'
            '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            'aria-hidden="true">'
            '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v3"/>'
            '<path d="M3 7v10a2 2 0 0 0 2 2h7"/>'
            '<line x1="18" y1="14" x2="18" y2="20"/>'
            '<line x1="15" y1="17" x2="21" y2="17"/>'
            '</svg></button>'
        )

    head += """
                <div class="topbar-actions">
                    <input id="search" type="search" class="search-input" placeholder="Search tracks…" aria-label="Search tracks" autocomplete="off">
                    {add_folder_btn}
                    <button id="layoutToggle" type="button" class="icon-btn" title="Toggle layout" aria-label="Toggle layout">☰</button>
                    <button id="themeToggle" type="button" class="icon-btn" title="Toggle theme" aria-label="Toggle theme">🌙</button>
                </div>
            </div>
        </header>""".format(add_folder_btn=add_folder_btn) + """
        <main class="container">
            <ul id="audioFiles" class="track-list grid-view">
    """
    return head


def resolve_folder_cover(folder_path, covers_dir):
    """Return the best cover web URL for a folder, or None.

    Resolution order:
      1. A standalone cover image in this folder (or an art-only subfolder),
         via :func:`find_folder_cover`.
      2. Recurse into the first (sorted) subfolder that contains audio, so a
         folder holding only subfolders inherits art from the first one — even
         when it lives several levels deep.

    Embedded track art is intentionally not read (see :func:`extract_metadata`).
    """
    cover_url = _save_cover_file(find_folder_cover(folder_path), covers_dir)
    if cover_url:
        return cover_url

    for sub in get_folders(folder_path):  # sorted, already filtered to audio-bearing
        cover_url = resolve_folder_cover(os.path.join(folder_path, sub), covers_dir)
        if cover_url:
            return cover_url
    return None


def folder_card_meta(folder_path, covers_dir):
    """Return (cover_url, artist) for a folder's album-style card.

    Cover reuses :func:`resolve_folder_cover` (which descends into subfolders
    when needed). Artist is always blank — track tags are no longer read.
    """
    return resolve_folder_cover(folder_path, covers_dir), ''


def generate_folders_html(folders, local_path, covers_dir, folder_files):
    folders_html = ''
    for folder in folders:
        safe = html.escape(folder)
        cover_url, artist = folder_card_meta(os.path.join(local_path, folder), covers_dir)
        artist_safe = html.escape(artist)
        if cover_url:
            cover_html = f'<img src="{url_path(cover_url)}" alt="" loading="lazy">'
        else:
            cover_html = '<span class="cover-fallback">📁</span>'
        folders_html += (
            f'<li class="folder-row" data-title="{safe}" data-artist="{artist_safe}">'
            f'<a href="{page_href(folder_files[folder])}">'
            f'<span class="folder-cover">{cover_html}</span>'
            '<span class="folder-meta">'
            f'<span class="folder-name">{safe}</span>'
            f'<span class="folder-sub">{artist_safe}</span>'
            '</span>'
            '<span class="chevron">›</span>'
            '</a></li>\n'
        )
    return folders_html


def new_stats():
    """Fresh accumulator for collection-wide statistics (see statistics_page_html).

    Only filesystem-derived facts are tracked, so the stats page is populated
    even when MP3 tag metadata isn't available.
    """
    return {
        'tracks': 0,
        'albums': 0,            # folders directly containing audio
        'total_bytes': 0,
        'formats': Counter(),   # by file extension
    }


def accumulate_stats(stats, local_file_path, filename):
    """Fold one track into the running ``stats`` accumulator (no tag reads)."""
    stats['tracks'] += 1

    try:
        stats['total_bytes'] += os.path.getsize(local_file_path)
    except OSError:
        pass

    ext = os.path.splitext(filename)[1].lstrip('.').lower()
    if ext:
        stats['formats'][ext] += 1


def generate_mp3_html(public_path, mp3_files, local_path, covers_dir, folder_cover_url=None, stats=None):
    mp3_html = ''
    for index, mp3_file in enumerate(mp3_files, start=1):
        mp3_public_path = os.path.join(public_path, mp3_file)
        local_file_path = os.path.join(local_path, mp3_file)
        meta = extract_metadata(local_file_path, mp3_file, covers_dir, folder_cover_url)

        if stats is not None:
            accumulate_stats(stats, local_file_path, mp3_file)

        title = html.escape(meta['title'])
        artist = html.escape(meta['artist'])
        album = html.escape(meta['album'])
        duration = html.escape(meta['duration'])
        cover = meta['cover_url']

        sub_parts = [p for p in (artist, album) if p]
        sub = ' · '.join(sub_parts)

        if cover:
            cover_html = f'<img src="{url_path(cover)}" alt="" loading="lazy">'
        else:
            cover_html = '<span class="cover-fallback">🎵</span>'

        mp3_html += """
        <li class="track" data-src="{src}" data-title="{title}" data-artist="{artist}" data-album="{album}" data-duration="{duration}" data-cover="{cover}">
            <span class="track-cover">{cover_html}</span>
            <span class="track-index">{index}</span>
            <span class="track-meta">
                <span class="track-title">{title}</span>
                <span class="track-sub">{sub}</span>
            </span>
            <span class="track-duration">{duration}</span>
            <span class="track-actions">
                <button class="track-action play-next" title="Play next" aria-label="Play next">⏭</button>
                <button class="track-action add-queue" title="Add to queue" aria-label="Add to queue">＋</button>
                <a class="track-download" href="{src}" download title="Download" aria-label="Download">{download_icon}</a>
            </span>
        </li>
        """.format(
            src=url_path(mp3_public_path),
            title=title,
            artist=artist,
            album=album,
            duration=duration,
            cover=url_path(cover or ''),
            cover_html=cover_html,
            index=index,
            sub=sub,
            download_icon=html.escape(config.download_icon),
        )
    return mp3_html


def player_bar_html():
    """The sticky player bar, queue panel and dialogs, plus the player script.

    Shared by every page (folder pages via :func:`footer_html` and the
    statistics page) so the player stays present and ``audioPlayer.js`` can
    restore the saved queue/resume position after navigating between pages.
    """
    return """
        <div id="playerBar" class="player-bar">
            <audio id="player" preload="metadata"></audio>
            <div class="pb-now">
                <span class="pb-cover"><img id="pbCover" src="" alt=""></span>
                <span class="pb-meta">
                    <span id="pbTitle" class="pb-title">—</span>
                    <span id="pbArtist" class="pb-artist"></span>
                </span>
            </div>
            <div class="pb-controls">
                <button id="shuffleButton" class="icon-btn" title="Shuffle" aria-label="Shuffle">🔀</button>
                <button id="prevButton" class="icon-btn" title="Previous" aria-label="Previous">⏮</button>
                <button id="playButton" class="icon-btn play" title="Play/Pause" aria-label="Play/Pause">▶</button>
                <button id="nextButton" class="icon-btn" title="Next" aria-label="Next">⏭</button>
                <button id="repeatButton" class="icon-btn" title="Repeat" aria-label="Repeat">🔁</button>
                <button id="queueButton" class="icon-btn" title="Queue" aria-label="Queue">☰</button>
            </div>
            <div class="pb-progress">
                <span id="pbCurrent" class="pb-time">0:00</span>
                <input id="seek" class="seek" type="range" min="0" max="100" value="0" step="0.1" aria-label="Seek">
                <span id="pbDuration" class="pb-time">0:00</span>
            </div>
            <div class="pb-volume">
                <span class="vol-icon">🔊</span>
                <input id="volume" class="volume" type="range" min="0" max="1" value="1" step="0.01" aria-label="Volume">
            </div>
        </div>
        <div id="queueBackdrop" class="queue-backdrop" hidden></div>
        <aside id="queuePanel" class="queue-panel" hidden aria-label="Play queue">
            <div class="queue-head">
                <span class="queue-title">Up Next</span>
                <button id="queueClear" class="queue-clear" title="Clear queue">Clear</button>
                <button id="queueClose" class="icon-btn" title="Close" aria-label="Close queue">✕</button>
            </div>
            <ul id="queueList" class="queue-list"></ul>
        </aside>
        <div id="queueDialogBackdrop" class="modal-backdrop" hidden></div>
        <div id="queueDialog" class="modal" role="dialog" aria-modal="true" aria-labelledby="queueDialogTitle" hidden>
            <p id="queueDialogTitle" class="modal-title">A queue is already playing</p>
            <p class="modal-text">Keep the current queue, or replace it?</p>
            <div class="modal-actions">
                <button id="qdAddSong" class="modal-btn">Keep queue · add this song</button>
                <button id="qdAddFolder" class="modal-btn">Keep queue · add whole folder</button>
                <button id="qdReplace" class="modal-btn">Replace queue with this folder</button>
                <button id="qdCancel" class="modal-btn modal-btn-ghost">Cancel</button>
            </div>
        </div>
        <script src="files/audioPlayer.js"></script>
    """


def footer_html(file_name, mp3_files, folders, total_mp3_count):
    stats = []
    if file_name == 'index.html':
        stats.append(f'{total_mp3_count} audio files in {len(folders)} folders')
    if len(mp3_files) > 0:
        stats.append(f'{len(mp3_files)} audio files in this folder')
    if len(folders) > 0 and file_name != 'index.html':
        stats.append(f'{len(folders)} folders')
    stats_html = ' · '.join(html.escape(s) for s in stats)

    footer = """
            </ul>
        </main>
        <footer class="footer">
            <span class="muted">{stats}</span>
        </footer>
    """.format(stats=stats_html)

    footer += player_bar_html()
    footer += """
    </body>
    </html>
    """
    return footer


def _stat_card(value, label):
    return (
        '<div class="stat-card">'
        f'<span class="stat-value">{html.escape(str(value))}</span>'
        f'<span class="stat-label">{html.escape(label)}</span>'
        '</div>'
    )


def _bar_chart(counter, limit=10, value_fmt=None):
    """Render a pure-CSS horizontal bar chart from a Counter (top ``limit``)."""
    items = counter.most_common(limit)
    if not items:
        return '<p class="stat-empty muted">No data available.</p>'
    top = items[0][1] or 1
    rows = ''
    for label, count in items:
        pct = max(2, round(count / top * 100))
        shown = value_fmt(count) if value_fmt else str(count)
        rows += (
            '<div class="bar-row">'
            f'<span class="bar-label" title="{html.escape(str(label))}">{html.escape(str(label))}</span>'
            '<span class="bar-track">'
            f'<span class="bar-fill" style="width:{pct}%"></span>'
            '</span>'
            f'<span class="bar-value">{html.escape(shown)}</span>'
            '</div>\n'
        )
    return f'<div class="stat-bars">{rows}</div>'


def statistics_page_html(stats, generated_at=None, elapsed_seconds=0):
    """Build the standalone Statistics page from a collected ``stats`` dict.

    ``generated_at`` is a ``datetime`` for when the site was built and
    ``elapsed_seconds`` how long the build took. Reuses ``style.css`` and
    ``audioPlayer.js`` (theme toggle works; the player block self-disables when
    there's no ``#player`` element on the page).
    """
    title = html.escape(config.site_name)
    logo = html.escape(config.site_logo)

    tracks = stats['tracks']

    cards = ''.join([
        _stat_card(f'{tracks:,}', 'Tracks'),
        _stat_card(f"{stats['albums']:,}", 'Albums'),
        _stat_card(format_filesize(stats['total_bytes']), 'Total size'),
        _stat_card(f"{len(stats['formats']):,}", 'Formats'),
    ])

    timestamp = generated_at.strftime('%Y-%m-%d %H:%M:%S') if generated_at else '—'

    sections = f"""
                <section class="stat-section">
                    <div class="stat-grid">{cards}</div>
                </section>
                <section class="stat-section">
                    <h2 class="stat-heading">Formats</h2>
                    {_bar_chart(stats['formats'], limit=12)}
                </section>
                <section class="stat-section">
                    <h2 class="stat-heading">Generated</h2>
                    <div class="stat-bars">
                        <div class="bar-row"><span class="bar-label">Generated at</span>
                            <span class="bar-extreme">{html.escape(timestamp)}</span></div>
                        <div class="bar-row"><span class="bar-label">Generation time</span>
                            <span class="bar-extreme">{html.escape(format_elapsed(elapsed_seconds))}</span></div>
                    </div>
                </section>
    """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Statistics · {title}</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
        <link rel="stylesheet" href="files/style.css">
        <link rel="icon" type="image/x-icon" href="https://icons.iconarchive.com/icons/icondesigner.net/hyperion/32/Sidebar-Music-icon.png">
    </head>
    <body>
        <header class="topbar">
            <div class="topbar-inner">
                <a id="backButton" href="{page_href('index.html')}" class="icon-btn" title="Back" aria-label="Back">‹</a>
                <h1 class="site-title"><span class="site-logo">{logo}</span> Statistics</h1>
                <div class="topbar-actions">
                    <button id="themeToggle" type="button" class="icon-btn" title="Toggle theme" aria-label="Toggle theme">🌙</button>
                </div>
            </div>
        </header>
        <main class="container">
            <div class="stats">{sections}</div>
        </main>
        <footer class="footer">
            <span class="muted">{tracks:,} tracks · {format_filesize(stats['total_bytes'])}</span>
        </footer>
        {player_bar_html()}
    </body>
    </html>
    """


def save_html(html_text, html_folder, file_name='index.html'):
    with open(os.path.join(html_folder, file_name), 'w') as f:
        f.write(html_text)


def statistics_link_html():
    """Special home-page entry (last in the list) linking to the stats page."""
    return (
        '<li class="folder-row stat-link" data-title="Statistics">'
        f'<a href="{page_href("statistics.html")}">'
        '<span class="folder-cover"><span class="cover-fallback">📊</span></span>'
        '<span class="folder-meta">'
        '<span class="folder-name">Statistics</span>'
        '<span class="folder-sub">Collection overview</span>'
        '</span>'
        '<span class="chevron">›</span>'
        '</a></li>\n'
    )


def process_collection(local_path, public_path, html_folder, file_name, covers_dir, generated=None, parent_file_name=None, display_name=None, stats=None):
    if generated is None:
        generated = set()
    generated.add(file_name)
    # statistics.html is generated separately after the walk; reserve its name
    # up front so a user folder can never slug to it.
    generated.add('statistics.html')

    total_mp3_count = count_mp3_files(local_path)
    folders = get_folders(local_path)
    mp3_files = get_mp3_files(local_path)
    folder_cover_url = _save_cover_file(find_folder_cover(local_path), covers_dir)

    if stats is not None and mp3_files:
        stats['albums'] += 1

    # Reserve a unique slugified page name per child folder up front, so the
    # folder-card links and the recursive page writes agree on the filename.
    folder_files = {f: reserve_html_name(slugify(f), generated) for f in folders}

    page = header_html(file_name, mp3_files, parent_file_name, display_name)
    page += generate_folders_html(folders, local_path, covers_dir, folder_files)
    page += generate_mp3_html(public_path, mp3_files, local_path, covers_dir, folder_cover_url, stats)
    if file_name == 'index.html':
        page += statistics_link_html()
    page += footer_html(file_name, mp3_files, folders, total_mp3_count)
    save_html(page, html_folder, file_name)

    for folder in folders:
        folder_path = os.path.join(local_path, folder)
        folder_public_path = os.path.join(public_path, folder)
        process_collection(folder_path, folder_public_path, html_folder, folder_files[folder], covers_dir, generated, parent_file_name=file_name, display_name=folder, stats=stats)

    return generated


def prune_orphaned_html(html_folder, generated):
    """Delete top-level .html files in html_folder that this run didn't write.

    Folders renamed or removed from the source leave stale pages behind (each
    folder maps to ``<folder>.html``); without this they'd accumulate forever.
    Only the flat html files written by :func:`save_html` are considered, so the
    ``files/`` assets and cover images are untouched.
    """
    removed = []
    for name in os.listdir(html_folder):
        if not name.endswith('.html') or name in generated:
            continue
        path = os.path.join(html_folder, name)
        if os.path.isfile(path):
            os.remove(path)
            removed.append(name)
    return removed


if __name__ == '__main__':
    covers_dir = os.path.join(config.html_folder, COVERS_SUBDIR)
    os.makedirs(covers_dir, exist_ok=True)
    stats = new_stats()
    start = time.monotonic()
    generated = process_collection(config.local_path, config.public_path, config.html_folder, 'index.html', covers_dir, stats=stats)
    elapsed = time.monotonic() - start
    save_html(statistics_page_html(stats, datetime.now(), elapsed), config.html_folder, 'statistics.html')
    removed = prune_orphaned_html(config.html_folder, generated)
    if removed:
        print(f'Removed {len(removed)} orphaned HTML file(s): ' + ', '.join(sorted(removed)))
