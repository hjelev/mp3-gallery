# Scan a folder and generate HTML files with links to the MP3 files in that folder recursively.

import os
import glob
import hashlib
import html
import re
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
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3
except ImportError:  # pragma: no cover - mutagen is a declared dependency
    MutagenFile = None
    ID3 = None


COVERS_SUBDIR = os.path.join('files', 'covers')

# Map embedded picture mime types to file extensions.
_MIME_EXT = {
    'image/jpeg': 'jpg',
    'image/jpg': 'jpg',
    'image/png': 'png',
    'image/gif': 'gif',
    'image/webp': 'webp',
}

# Standalone cover image extensions, in preference order.
_IMAGE_EXTS = ('jpg', 'jpeg', 'png', 'webp', 'gif')

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


def format_duration(seconds):
    if not seconds or seconds <= 0:
        return ''
    seconds = int(round(seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{secs:02d}'
    return f'{minutes}:{secs:02d}'


def _save_cover(data, mime, local_file_path, covers_dir):
    """Write embedded cover bytes to the covers dir, return relative web path or None."""
    ext = _MIME_EXT.get((mime or '').lower(), 'jpg')
    digest = hashlib.sha1(os.path.abspath(local_file_path).encode('utf-8')).hexdigest()[:16]
    fname = f'{digest}.{ext}'
    dest = os.path.join(covers_dir, fname)
    if not os.path.exists(dest):
        with open(dest, 'wb') as fh:
            fh.write(data)
    return f'{COVERS_SUBDIR.replace(os.sep, "/")}/{fname}'


def _save_cover_file(src_path, covers_dir):
    """Copy a standalone image file into covers_dir, return its web path or None."""
    if not src_path:
        return None
    ext = os.path.splitext(src_path)[1].lstrip('.').lower() or 'jpg'
    digest = hashlib.sha1(os.path.abspath(src_path).encode('utf-8')).hexdigest()[:16]
    fname = f'{digest}.{ext}'
    dest = os.path.join(covers_dir, fname)
    if not os.path.exists(dest):
        try:
            with open(src_path, 'rb') as src, open(dest, 'wb') as fh:
                fh.write(src.read())
        except OSError:
            return None
    return f'{COVERS_SUBDIR.replace(os.sep, "/")}/{fname}'


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


def _extract_cover(audio, local_file_path, covers_dir):
    # ID3 (mp3) embedded art lives in APIC frames.
    try:
        tags = getattr(audio, 'tags', None)
        if tags is not None:
            for key in tags.keys():
                if key.startswith('APIC'):
                    apic = tags[key]
                    return _save_cover(apic.data, apic.mime, local_file_path, covers_dir)
    except Exception:
        pass
    # MP4/M4A embedded art lives in the `covr` atom (list of MP4Cover bytes).
    try:
        if tags is not None and 'covr' in tags:
            covers = tags['covr']
            if covers:
                cover = covers[0]
                fmt = getattr(cover, 'imageformat', None)
                mime = 'image/png' if fmt == getattr(cover, 'FORMAT_PNG', object()) else 'image/jpeg'
                return _save_cover(bytes(cover), mime, local_file_path, covers_dir)
    except Exception:
        pass
    # FLAC (and some others) expose parsed picture blocks directly.
    try:
        pictures = getattr(audio, 'pictures', None)
        if pictures:
            pic = pictures[0]
            return _save_cover(pic.data, pic.mime, local_file_path, covers_dir)
    except Exception:
        pass
    # Ogg Vorbis/Opus store art as a base64 FLAC Picture in a Vorbis comment.
    try:
        if tags is not None:
            import base64
            from mutagen.flac import Picture
            for key in ('metadata_block_picture', 'METADATA_BLOCK_PICTURE'):
                values = tags.get(key)
                if values:
                    pic = Picture(base64.b64decode(values[0]))
                    return _save_cover(pic.data, pic.mime, local_file_path, covers_dir)
    except Exception:
        pass
    return None


def extract_metadata(local_file_path, filename, covers_dir, folder_cover_url=None):
    """Return a dict of display metadata, degrading gracefully to filename-only.

    A standalone folder cover (``folder_cover_url``) takes priority over embedded
    ID3 art; embedded art is only extracted when no folder cover exists.
    """
    meta = {
        'title': clean_title_from_filename(filename),
        'artist': '',
        'album': '',
        'duration': '',
        'cover_url': folder_cover_url,
    }
    if MutagenFile is None:
        return meta
    try:
        audio = MutagenFile(local_file_path)
        if audio is None:
            return meta
        if getattr(audio, 'info', None) is not None:
            meta['duration'] = format_duration(getattr(audio.info, 'length', 0))

        def first(tag):
            try:
                value = audio.get(tag)
            except Exception:
                value = None
            if not value:
                return ''
            if isinstance(value, list):
                value = value[0]
            return str(value).strip()

        title = first('TIT2') or first('title') or first('\xa9nam')
        artist = first('TPE1') or first('artist') or first('\xa9ART')
        album = first('TALB') or first('album') or first('\xa9alb')
        if title:
            meta['title'] = title
        meta['artist'] = artist
        meta['album'] = album
        if folder_cover_url:
            meta['cover_url'] = folder_cover_url
        else:
            meta['cover_url'] = _extract_cover(audio, local_file_path, covers_dir)
    except Exception:
        # Corrupt/odd file: keep the filename-derived defaults.
        pass
    return meta


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
      2. Embedded art from the first audio track directly in this folder.
      3. Recurse into the first (sorted) subfolder that contains audio, so a
         folder holding only subfolders inherits art from the first one — even
         when it lives several levels deep.
    """
    cover_url = _save_cover_file(find_folder_cover(folder_path), covers_dir)
    if cover_url:
        return cover_url

    mp3_files = get_mp3_files(folder_path)
    if mp3_files:
        first = mp3_files[0]
        meta = extract_metadata(os.path.join(folder_path, first), first, covers_dir, None)
        if meta['cover_url']:
            return meta['cover_url']

    for sub in get_folders(folder_path):  # sorted, already filtered to audio-bearing
        cover_url = resolve_folder_cover(os.path.join(folder_path, sub), covers_dir)
        if cover_url:
            return cover_url
    return None


def folder_card_meta(folder_path, covers_dir):
    """Return (cover_url, artist) for a folder's album-style card.

    Cover reuses :func:`resolve_folder_cover` (which descends into subfolders
    when needed); artist is taken from the first audio track directly in the
    folder (blank when there is none).
    """
    cover_url = resolve_folder_cover(folder_path, covers_dir)
    artist = ''
    mp3_files = get_mp3_files(folder_path)
    if mp3_files:
        first = mp3_files[0]
        meta = extract_metadata(os.path.join(folder_path, first), first, covers_dir, cover_url)
        artist = meta['artist']
    return cover_url, artist


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


def generate_mp3_html(public_path, mp3_files, local_path, covers_dir, folder_cover_url=None):
    mp3_html = ''
    for index, mp3_file in enumerate(mp3_files, start=1):
        mp3_public_path = os.path.join(public_path, mp3_file)
        local_file_path = os.path.join(local_path, mp3_file)
        meta = extract_metadata(local_file_path, mp3_file, covers_dir, folder_cover_url)

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

    footer += """
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
        """

    footer += """
        <script src="files/audioPlayer.js"></script>
    </body>
    </html>
    """
    return footer


def save_html(html_text, html_folder, file_name='index.html'):
    with open(os.path.join(html_folder, file_name), 'w') as f:
        f.write(html_text)


def process_collection(local_path, public_path, html_folder, file_name, covers_dir, generated=None, parent_file_name=None, display_name=None):
    if generated is None:
        generated = set()
    generated.add(file_name)

    total_mp3_count = count_mp3_files(local_path)
    folders = get_folders(local_path)
    mp3_files = get_mp3_files(local_path)
    folder_cover_url = _save_cover_file(find_folder_cover(local_path), covers_dir)

    # Reserve a unique slugified page name per child folder up front, so the
    # folder-card links and the recursive page writes agree on the filename.
    folder_files = {f: reserve_html_name(slugify(f), generated) for f in folders}

    page = header_html(file_name, mp3_files, parent_file_name, display_name)
    page += generate_folders_html(folders, local_path, covers_dir, folder_files)
    page += generate_mp3_html(public_path, mp3_files, local_path, covers_dir, folder_cover_url)
    page += footer_html(file_name, mp3_files, folders, total_mp3_count)
    save_html(page, html_folder, file_name)

    for folder in folders:
        folder_path = os.path.join(local_path, folder)
        folder_public_path = os.path.join(public_path, folder)
        process_collection(folder_path, folder_public_path, html_folder, folder_files[folder], covers_dir, generated, parent_file_name=file_name, display_name=folder)

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
    generated = process_collection(config.local_path, config.public_path, config.html_folder, 'index.html', covers_dir)
    removed = prune_orphaned_html(config.html_folder, generated)
    if removed:
        print(f'Removed {len(removed)} orphaned HTML file(s): ' + ', '.join(sorted(removed)))
