# Environment-driven config used by the Docker image (copied to config.py at
# build time). Mirrors config.py.example but sources every value from the
# environment so the gallery can be configured entirely via docker-compose.
import os

# Directory containing the MP3 files (read inside the container to scan +
# extract metadata/cover art). Bind-mount your collection here, read-only.
local_path = os.environ.get('LOCAL_PATH', '/mp3')

# Where the generated HTML + assets are written (served by nginx).
html_folder = os.environ.get('HTML_FOLDER', '/site')

# External path/URL the browser uses to fetch the MP3 files. The audio itself
# is served by your own server, not this container.
public_path = os.environ.get('PUBLIC_PATH', 'http://localhost/mp3/')

# Title shown in the browser tab and the page header.
site_name = os.environ.get('SITE_NAME', 'MP3 Gallery')

# Logo/emoji shown before the site name in the header.
site_logo = os.environ.get('SITE_LOGO', '\U0001F3B5')

# Icon/text used for the per-track download link.
download_icon = os.environ.get('DOWNLOAD_ICON', '⬇')

# Generate downsized cover-art thumbnails (max 480px on the longest edge).
generate_thumbnails = os.environ.get(
    'GENERATE_THUMBNAILS', 'true').lower() in ('1', 'true', 'yes', 'on')
