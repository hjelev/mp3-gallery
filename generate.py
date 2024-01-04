# Scan a folder and generate a HTML files with links to the MP3 files in that folder recursively.

import os
import config
import glob

def count_mp3_files(path):
    return len(glob.glob(os.path.join(path, '**', '*.mp3'), recursive=True))


def get_mp3_files(local_path):
    mp3_files = sorted([f for f in os.listdir(local_path) if f.endswith('.mp3')])
    return mp3_files


def header_html(file_name, mp3_files):
    header_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{}</title>
        <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/css/bootstrap.min.css">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.1/font/bootstrap-icons.css">
        <link rel="stylesheet" href="files/style.css">
        <link rel="icon" type="image/x-icon" href="https://icons.iconarchive.com/icons/icondesigner.net/hyperion/32/Sidebar-Music-icon.png">
    </head>
    <body>
        <div class="container">

    """.format(config.site_name)

    if file_name != 'index.html':
        header_html += """
                        <h1 class="mt-4 mb-4"><button id="backButton1" type="button" class="btn btn-secondary">Back</button> 📁{}</h1>
        """.format(file_name.replace('.html',''))
    else :
        header_html += """
                        <h1 class="mt-4 mb-4">{} {}</h1>
        """.format(config.site_logo, config.site_name)

    if len(mp3_files) > 0:
        header_html += """
        <div class="player-controls">
                <audio id="player" controls class="mb-4">
                    Your browser does not support the audio element.
                </audio>
                <button id="prevButton" class="btn btn-secondary" ><<</button>
                <button id="nextButton" class="btn btn-secondary">>></button>
            </div>
        """
    
    header_html += """
            <ul id="audioFiles" class="list-group">
    """
    return header_html


def generate_mp3_html(public_path, mp3_files):
    # Add each MP3 file to the HTML code
    mp3_html = ''
    for mp3_file in mp3_files:
        mp3_public_path = os.path.join(public_path, mp3_file)
        mp3_html += """
        <li class="audio-list list-group-item mp3" data-src="{}">
            🎵 {}
            <a href="{}" download>{}</a>
        </li>\n
        """.format(mp3_public_path, mp3_file, mp3_public_path, config.download_icon)
    return mp3_html


def footer_html(file_name, mp3_files, folders):
    footer_html = """
            </ul>
        </div>
        <footer class="footer mt-auto py-3 bg-light">
            <div class="container">
            """
    if file_name != 'index.html':
        footer_html += """
            <button id="backButton2" type="button" class="btn btn-secondary">Back</button>
            """
        if (len(mp3_files) > 0):
            footer_html += """
                    <span class="text-muted">{} mp3 files in this folder</span>  
                    """.format(len(mp3_files))
        if (len(folders) > 0):
            footer_html += """
            <span class="text-muted">{} folders</span>  
            """.format(len(folders))

    footer_html +="""
            </div>
        </footer>
        <script src="files/audioPlayer.js"></script>
                <script>
            document.getElementById('backButton1').addEventListener('click', function() {{
                window.history.back();
            }});
            document.getElementById('backButton2').addEventListener('click', function() {{
                window.history.back();
            }});
        </script>
    </body>
    </html>
    """.format(len(mp3_files))
    return footer_html


def save_html(html, html_folder, file_name='index.html'):
    with open(os.path.join(html_folder, file_name), 'w') as f:
        f.write(html)


def get_folders(local_path):
    folders = sorted([f for f in os.listdir(local_path) if os.path.isdir(os.path.join(local_path, f))])
    return folders


def generate_folders_html(folders):
    folders_html = ''
    for folder in folders:
        folders_html += f'<li class="audio-list list-group-item folder"><a href="{folder}.html">📁 {folder}</a></li>\n'

    return folders_html


def process_collection(local_path, public_path, html_folder, file_name, parent_folder=None):
    folders = get_folders(local_path)
    mp3_files = get_mp3_files(local_path)
    html = header_html(file_name, mp3_files)
    html += generate_folders_html(folders)
    html += generate_mp3_html(public_path, mp3_files)
    html += footer_html(file_name, mp3_files, folders)
    save_html(html, html_folder, file_name)

    for folder in folders:
        folder_name = folder
        folder_path = os.path.join(local_path, folder)
        folder_public_path = os.path.join(public_path, folder)
        process_collection(folder_path, folder_public_path, html_folder, folder_name + '.html')


if __name__ == '__main__':
    process_collection(config.local_path, config.public_path, config.html_folder, 'index.html')