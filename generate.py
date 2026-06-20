# Scan a folder and generate HTML files with links to the MP3 files in that folder recursively.

import os
import glob
import hashlib
import html

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


def count_mp3_files(path):
    return len(glob.glob(os.path.join(glob.escape(path), '**', '*.mp3'), recursive=True))


def get_mp3_files(local_path):
    mp3_files = sorted([f for f in os.listdir(local_path) if f.endswith('.mp3')])
    return mp3_files


def get_folders(local_path):
    folders = sorted([f for f in os.listdir(local_path) if os.path.isdir(os.path.join(local_path, f))])
    return folders


def clean_title_from_filename(filename):
    name = os.path.splitext(filename)[0]
    name = name.replace('_', ' ').replace('-', ' ')
    return ' '.join(name.split()).strip() or filename


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
    # Generic fallback (some formats expose `pictures`).
    try:
        pictures = getattr(audio, 'pictures', None)
        if pictures:
            pic = pictures[0]
            return _save_cover(pic.data, pic.mime, local_file_path, covers_dir)
    except Exception:
        pass
    return None


def extract_metadata(local_file_path, filename, covers_dir):
    """Return a dict of display metadata, degrading gracefully to filename-only."""
    meta = {
        'title': clean_title_from_filename(filename),
        'artist': '',
        'album': '',
        'duration': '',
        'cover_url': None,
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

        title = first('TIT2') or first('title')
        artist = first('TPE1') or first('artist')
        album = first('TALB') or first('album')
        if title:
            meta['title'] = title
        meta['artist'] = artist
        meta['album'] = album
        meta['cover_url'] = _extract_cover(audio, local_file_path, covers_dir)
    except Exception:
        # Corrupt/odd file: keep the filename-derived defaults.
        pass
    return meta


def header_html(file_name, mp3_files):
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
                <button id="backButton" type="button" class="icon-btn" title="Back" aria-label="Back">‹</button>
                <h1 class="site-title"><span class="folder-glyph">📁</span> {name}</h1>
        """.format(name=html.escape(file_name.replace('.html', '')))
    else:
        head += """
                <h1 class="site-title"><span class="site-logo">{logo}</span> {name}</h1>
        """.format(logo=html.escape(config.site_logo), name=title)

    head += """
                <div class="topbar-actions">
                    <input id="search" type="search" class="search-input" placeholder="Search tracks…" aria-label="Search tracks" autocomplete="off">
                    <button id="themeToggle" type="button" class="icon-btn" title="Toggle theme" aria-label="Toggle theme">🌙</button>
                </div>
            </div>
        </header>
        <main class="container">
            <ul id="audioFiles" class="track-list">
    """
    return head


def generate_folders_html(folders):
    folders_html = ''
    for folder in folders:
        safe = html.escape(folder)
        folders_html += (
            '<li class="folder-row">'
            f'<a href="{html.escape(folder)}.html">'
            '<span class="folder-glyph">📁</span>'
            f'<span class="folder-name">{safe}</span>'
            '<span class="chevron">›</span>'
            '</a></li>\n'
        )
    return folders_html


def generate_mp3_html(public_path, mp3_files, local_path, covers_dir):
    mp3_html = ''
    for index, mp3_file in enumerate(mp3_files, start=1):
        mp3_public_path = os.path.join(public_path, mp3_file)
        local_file_path = os.path.join(local_path, mp3_file)
        meta = extract_metadata(local_file_path, mp3_file, covers_dir)

        title = html.escape(meta['title'])
        artist = html.escape(meta['artist'])
        album = html.escape(meta['album'])
        duration = html.escape(meta['duration'])
        cover = meta['cover_url']

        sub_parts = [p for p in (artist, album) if p]
        sub = ' · '.join(sub_parts)

        if cover:
            cover_html = f'<img src="{html.escape(cover)}" alt="" loading="lazy">'
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
            <a class="track-download" href="{src}" download title="Download" aria-label="Download">{download_icon}</a>
        </li>
        """.format(
            src=html.escape(mp3_public_path),
            title=title,
            artist=artist,
            album=album,
            duration=duration,
            cover=html.escape(cover or ''),
            cover_html=cover_html,
            index=index,
            sub=sub,
            download_icon=html.escape(config.download_icon),
        )
    return mp3_html


def footer_html(file_name, mp3_files, folders, total_mp3_count):
    stats = []
    if file_name == 'index.html':
        stats.append(f'{total_mp3_count} mp3 files in {len(folders)} folders')
    if len(mp3_files) > 0:
        stats.append(f'{len(mp3_files)} mp3 files in this folder')
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

    if len(mp3_files) > 0:
        footer += """
        <div id="playerBar" class="player-bar" hidden>
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


def process_collection(local_path, public_path, html_folder, file_name, covers_dir):
    total_mp3_count = count_mp3_files(local_path)
    folders = get_folders(local_path)
    mp3_files = get_mp3_files(local_path)

    page = header_html(file_name, mp3_files)
    page += generate_folders_html(folders)
    page += generate_mp3_html(public_path, mp3_files, local_path, covers_dir)
    page += footer_html(file_name, mp3_files, folders, total_mp3_count)
    save_html(page, html_folder, file_name)

    for folder in folders:
        folder_path = os.path.join(local_path, folder)
        folder_public_path = os.path.join(public_path, folder)
        process_collection(folder_path, folder_public_path, html_folder, folder + '.html', covers_dir)


if __name__ == '__main__':
    covers_dir = os.path.join(config.html_folder, COVERS_SUBDIR)
    os.makedirs(covers_dir, exist_ok=True)
    process_collection(config.local_path, config.public_path, config.html_folder, 'index.html', covers_dir)
