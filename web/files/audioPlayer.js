// audioPlayer.js — custom sticky player, search, shuffle/repeat, theme, resume.
(function () {
    'use strict';

    var THEME_KEY = 'mp3gallery:theme';
    var LAYOUT_KEY = 'mp3gallery:layout';
    var RESUME_KEY = 'mp3gallery:resume';
    var QUEUE_KEY = 'mp3gallery:queue';

    /* ---------- Theme (runs immediately so there's no flash) ---------- */
    var root = document.documentElement;
    var themeToggle = document.getElementById('themeToggle');

    function applyTheme(theme) {
        root.setAttribute('data-theme', theme);
        if (themeToggle) themeToggle.textContent = theme === 'dark' ? '☀️' : '🌙';
    }

    var savedTheme = null;
    try { savedTheme = localStorage.getItem(THEME_KEY); } catch (e) {}
    if (savedTheme === 'dark' || savedTheme === 'light') {
        applyTheme(savedTheme);
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        applyTheme('dark');
    } else {
        applyTheme('light');
    }

    if (themeToggle) {
        themeToggle.addEventListener('click', function () {
            var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            applyTheme(next);
            try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
        });
    }

    /* ---------- Layout (grid is the default applied server-side) ---------- */
    var layoutToggle = document.getElementById('layoutToggle');
    var trackList = document.getElementById('audioFiles');

    function applyLayout(layout) {
        if (trackList) trackList.classList.toggle('grid-view', layout !== 'list');
        if (layoutToggle) layoutToggle.textContent = layout === 'list' ? '▦' : '☰';
    }

    var savedLayout = null;
    try { savedLayout = localStorage.getItem(LAYOUT_KEY); } catch (e) {}
    applyLayout(savedLayout === 'list' ? 'list' : 'grid');

    if (layoutToggle) {
        layoutToggle.addEventListener('click', function () {
            var next = (trackList && trackList.classList.contains('grid-view')) ? 'list' : 'grid';
            applyLayout(next);
            try { localStorage.setItem(LAYOUT_KEY, next); } catch (e) {}
        });
    }

    /* ---------- Search (works even with no tracks) ---------- */
    var search = document.getElementById('search');
    var rows = Array.prototype.slice.call(document.querySelectorAll('.track, .folder-row'));
    if (search) {
        search.addEventListener('input', function () {
            var q = search.value.trim().toLowerCase();
            rows.forEach(function (row) {
                var hay;
                if (row.classList.contains('track')) {
                    hay = (row.getAttribute('data-title') || '') + ' ' +
                          (row.getAttribute('data-artist') || '') + ' ' +
                          (row.getAttribute('data-album') || '') + ' ' +
                          (row.getAttribute('data-src') || '');
                } else {
                    hay = row.textContent || '';
                }
                row.style.display = (!q || hay.toLowerCase().indexOf(q) !== -1) ? '' : 'none';
            });
        });
    }

    /* ---------- Player ---------- */
    var tracks = Array.prototype.slice.call(document.querySelectorAll('.track'));
    var player = document.getElementById('player');
    if (!player) return; // no player bar on this page
    // Note: `tracks` may be empty on folder-only pages. The player still
    // initialises so the bar stays visible and a restored queue keeps playing.

    var bar = document.getElementById('playerBar');
    var playBtn = document.getElementById('playButton');
    var prevBtn = document.getElementById('prevButton');
    var nextBtn = document.getElementById('nextButton');
    var shuffleBtn = document.getElementById('shuffleButton');
    var repeatBtn = document.getElementById('repeatButton');
    var seek = document.getElementById('seek');
    var volume = document.getElementById('volume');
    var pbCover = document.getElementById('pbCover');
    var pbTitle = document.getElementById('pbTitle');
    var pbArtist = document.getElementById('pbArtist');
    var pbCurrent = document.getElementById('pbCurrent');
    var pbDuration = document.getElementById('pbDuration');

    var queueButton = document.getElementById('queueButton');
    var queuePanel = document.getElementById('queuePanel');
    var queueBackdrop = document.getElementById('queueBackdrop');
    var queueList = document.getElementById('queueList');
    var queueClose = document.getElementById('queueClose');
    var queueClear = document.getElementById('queueClear');
    var addFolderButton = document.getElementById('addFolderButton');

    var queueDialog = document.getElementById('queueDialog');
    var queueDialogBackdrop = document.getElementById('queueDialogBackdrop');

    // The queue holds self-contained track descriptors ({src,title,artist,
    // album,duration,cover}) rather than DOM indices, so it survives navigation
    // between folder pages. It starts empty and is filled from the saved queue
    // or by the user's actions. `queuePos` is the position within `queue` of the
    // track that's playing (-1 = none). `src` is an absolute URL for reliable
    // matching across pages.
    var queue = [];
    var queuePos = -1;
    var shuffle = false;
    var repeatMode = 'off'; // off | all | one
    var seeking = false;

    function currentDescriptor() {
        return (queuePos >= 0 && queuePos < queue.length) ? queue[queuePos] : null;
    }

    function absUrl(src) {
        var a = document.createElement('a');
        a.href = src || '';
        return a.href;
    }

    function descriptorFromEl(el) {
        return {
            src: absUrl(el.getAttribute('data-src')),
            title: el.getAttribute('data-title') || '',
            artist: el.getAttribute('data-artist') || '',
            album: el.getAttribute('data-album') || '',
            duration: el.getAttribute('data-duration') || '',
            cover: el.getAttribute('data-cover') || ''
        };
    }

    function folderDescriptors() { return tracks.map(descriptorFromEl); }

    function queueIndexOfSrc(src) {
        for (var i = 0; i < queue.length; i++) {
            if (queue[i].src === src) return i;
        }
        return -1;
    }

    function elForSrc(src) {
        for (var i = 0; i < tracks.length; i++) {
            if (absUrl(tracks[i].getAttribute('data-src')) === src) return tracks[i];
        }
        return null;
    }

    function fmt(s) {
        if (!isFinite(s) || s < 0) s = 0;
        s = Math.floor(s);
        var m = Math.floor(s / 60);
        var sec = s % 60;
        return m + ':' + (sec < 10 ? '0' : '') + sec;
    }

    function setActive(src) {
        tracks.forEach(function (t) { t.classList.remove('playing'); });
        var el = elForSrc(src);
        if (el) el.classList.add('playing');
    }

    function loadDescriptor(d, autoplay) {
        if (!d) return;
        player.src = d.src;
        if (bar) bar.hidden = false;
        setActive(d.src);

        if (d.cover) { pbCover.src = d.cover; pbCover.style.visibility = 'visible'; }
        else { pbCover.removeAttribute('src'); pbCover.style.visibility = 'hidden'; }

        pbTitle.textContent = d.title || '';
        pbArtist.textContent = [d.artist, d.album].filter(Boolean).join(' · ');

        if (autoplay) {
            var p = player.play();
            if (p && p.catch) p.catch(function () {});
        }
    }

    /* ---------- Queue navigation ---------- */
    function nextPos() {
        if (shuffle && queue.length > 1) {
            var n;
            do { n = Math.floor(Math.random() * queue.length); } while (n === queuePos);
            return n;
        }
        return (queuePos + 1) % queue.length;
    }

    function prevPos() {
        if (shuffle && queue.length > 1) {
            var n;
            do { n = Math.floor(Math.random() * queue.length); } while (n === queuePos);
            return n;
        }
        return (queuePos - 1 + queue.length) % queue.length;
    }

    function playQueuePos(pos) {
        if (pos < 0 || pos >= queue.length) return;
        queuePos = pos;
        loadDescriptor(queue[pos], true);
        renderQueue();
        saveQueue();
    }

    /* ---------- Queue mutation ---------- */
    // Drop a track from the queue (but never the one playing), keeping queuePos valid.
    function removeFromQueue(src) {
        var idx = queueIndexOfSrc(src);
        if (idx === -1 || idx === queuePos) return;
        queue.splice(idx, 1);
        if (idx < queuePos) queuePos--;
    }

    function playNextDesc(d) {
        removeFromQueue(d.src);
        var at = queuePos >= 0 ? queuePos + 1 : 0;
        queue.splice(at, 0, d);
        renderQueue();
        saveQueue();
    }

    function addToQueueDesc(d) {
        removeFromQueue(d.src);
        queue.push(d);
        renderQueue();
        saveQueue();
    }

    // Append every track on the current page that isn't already queued.
    function appendFolder() {
        folderDescriptors().forEach(function (fd) {
            if (queueIndexOfSrc(fd.src) === -1) queue.push(fd);
        });
    }

    function addFolderToQueue() {
        appendFolder();
        renderQueue();
        saveQueue();
        openQueue();
    }

    function removeAt(pos) {
        if (pos < 0 || pos >= queue.length || pos === queuePos) return;
        queue.splice(pos, 1);
        if (pos < queuePos) queuePos--;
        renderQueue();
        saveQueue();
    }

    function moveItem(from, to) {
        if (from === to || from < 0 || to < 0 || from >= queue.length || to >= queue.length) return;
        var cur = currentDescriptor();
        var item = queue.splice(from, 1)[0];
        queue.splice(to, 0, item);
        if (cur) queuePos = queue.indexOf(cur);
        renderQueue();
        saveQueue();
    }

    function clearQueue() {
        if (queuePos >= 0) { queue = [queue[queuePos]]; queuePos = 0; }
        else { queue = []; }
        renderQueue();
        saveQueue();
    }

    /* ---------- Queue drawer rendering ---------- */
    function renderQueue() {
        if (!queueList) return;
        queueList.textContent = '';
        if (!queue.length) {
            var empty = document.createElement('li');
            empty.className = 'queue-empty';
            empty.textContent = 'Queue is empty';
            queueList.appendChild(empty);
            return;
        }
        queue.forEach(function (d, pos) {
            var li = document.createElement('li');
            li.className = 'queue-item' + (pos === queuePos ? ' current' : '');
            li.setAttribute('draggable', 'true');
            li.dataset.pos = pos;

            var coverWrap = document.createElement('span');
            coverWrap.className = 'queue-cover';
            if (d.cover) {
                var img = document.createElement('img');
                img.src = d.cover;
                img.alt = '';
                coverWrap.appendChild(img);
            } else {
                coverWrap.textContent = '🎵';
            }

            var meta = document.createElement('span');
            meta.className = 'queue-item-meta';
            var title = document.createElement('span');
            title.className = 'queue-item-title';
            title.textContent = d.title || '';
            var sub = document.createElement('span');
            sub.className = 'queue-item-sub';
            sub.textContent = [d.artist, d.album].filter(Boolean).join(' · ');
            meta.appendChild(title);
            meta.appendChild(sub);

            li.appendChild(coverWrap);
            li.appendChild(meta);
            if (pos !== queuePos) {
                var rm = document.createElement('button');
                rm.className = 'queue-remove';
                rm.title = 'Remove';
                rm.setAttribute('aria-label', 'Remove');
                rm.textContent = '✕';
                li.appendChild(rm);
            }
            queueList.appendChild(li);
        });
    }

    /* ---------- "Keep current queue?" dialog ---------- */
    var pendingChoice = null;

    function hideDialog() {
        if (queueDialog) queueDialog.hidden = true;
        if (queueDialogBackdrop) queueDialogBackdrop.hidden = true;
    }

    function resolveChoice(choice) {
        var cb = pendingChoice;
        pendingChoice = null;
        hideDialog();
        if (cb) cb(choice);
    }

    // Ask what to do with the existing queue, then run cb('replace'|'song'|'folder'|'cancel').
    function askQueueChoice(cb) {
        if (!queueDialog) { cb('replace'); return; } // graceful fallback if markup is missing
        pendingChoice = cb;
        queueDialog.hidden = false;
        if (queueDialogBackdrop) queueDialogBackdrop.hidden = false;
    }

    // Click on a track row: decide how it joins the queue, then play it.
    function playFromRow(el) {
        var d = descriptorFromEl(el);
        var pos = queueIndexOfSrc(d.src);
        if (pos !== -1) { playQueuePos(pos); return; } // already queued — just play it

        if (!queue.length) { // nothing to preserve — queue the whole folder
            queue = folderDescriptors();
            playQueuePos(queueIndexOfSrc(d.src));
            return;
        }

        askQueueChoice(function (choice) {
            if (choice === 'cancel') return;
            if (choice === 'replace') {
                queue = folderDescriptors();
                playQueuePos(queueIndexOfSrc(d.src));
            } else if (choice === 'song') {
                queue.push(d);
                playQueuePos(queue.length - 1);
            } else if (choice === 'folder') {
                appendFolder();
                playQueuePos(queueIndexOfSrc(d.src));
            }
        });
    }

    /* ---------- Track row interactions ---------- */
    tracks.forEach(function (el) {
        el.addEventListener('click', function (e) {
            if (e.target.closest('.track-download')) return; // let downloads through
            if (e.target.closest('.play-next')) { e.stopPropagation(); playNextDesc(descriptorFromEl(el)); return; }
            if (e.target.closest('.add-queue')) { e.stopPropagation(); addToQueueDesc(descriptorFromEl(el)); return; }
            var cur = currentDescriptor();
            var src = absUrl(el.getAttribute('data-src'));
            if (cur && cur.src === src && !player.paused) { player.pause(); return; }
            if (cur && cur.src === src && player.paused && player.src) { player.play(); return; }
            playFromRow(el);
        });
    });

    if (addFolderButton) addFolderButton.addEventListener('click', addFolderToQueue);

    if (playBtn) playBtn.addEventListener('click', function () {
        if (queuePos === -1) { if (queue.length) playQueuePos(0); return; }
        if (player.paused) player.play(); else player.pause();
    });
    if (nextBtn) nextBtn.addEventListener('click', function () { playQueuePos(nextPos()); });
    if (prevBtn) prevBtn.addEventListener('click', function () {
        if (player.currentTime > 3) { player.currentTime = 0; return; }
        playQueuePos(prevPos());
    });

    if (shuffleBtn) shuffleBtn.addEventListener('click', function () {
        shuffle = !shuffle;
        shuffleBtn.classList.toggle('active', shuffle);
    });

    if (repeatBtn) repeatBtn.addEventListener('click', function () {
        repeatMode = repeatMode === 'off' ? 'all' : (repeatMode === 'all' ? 'one' : 'off');
        repeatBtn.classList.toggle('active', repeatMode !== 'off');
        repeatBtn.textContent = repeatMode === 'one' ? '🔂' : '🔁';
        repeatBtn.title = 'Repeat: ' + repeatMode;
    });

    /* ---------- Queue drawer controls ---------- */
    function openQueue() {
        if (queuePanel) queuePanel.hidden = false;
        if (queueBackdrop) queueBackdrop.hidden = false;
        if (queueButton) queueButton.classList.add('active');
    }
    function closeQueue() {
        if (queuePanel) queuePanel.hidden = true;
        if (queueBackdrop) queueBackdrop.hidden = true;
        if (queueButton) queueButton.classList.remove('active');
    }
    if (queueButton) queueButton.addEventListener('click', function () {
        if (queuePanel && queuePanel.hidden) openQueue(); else closeQueue();
    });
    if (queueClose) queueClose.addEventListener('click', closeQueue);
    if (queueBackdrop) queueBackdrop.addEventListener('click', closeQueue);
    if (queueClear) queueClear.addEventListener('click', clearQueue);

    /* ---------- Dialog controls ---------- */
    var qdReplace = document.getElementById('qdReplace');
    var qdAddSong = document.getElementById('qdAddSong');
    var qdAddFolder = document.getElementById('qdAddFolder');
    var qdCancel = document.getElementById('qdCancel');
    if (qdReplace) qdReplace.addEventListener('click', function () { resolveChoice('replace'); });
    if (qdAddSong) qdAddSong.addEventListener('click', function () { resolveChoice('song'); });
    if (qdAddFolder) qdAddFolder.addEventListener('click', function () { resolveChoice('folder'); });
    if (qdCancel) qdCancel.addEventListener('click', function () { resolveChoice('cancel'); });
    if (queueDialogBackdrop) queueDialogBackdrop.addEventListener('click', function () { resolveChoice('cancel'); });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && queueDialog && !queueDialog.hidden) resolveChoice('cancel');
    });

    if (queueList) {
        queueList.addEventListener('click', function (e) {
            var li = e.target.closest('.queue-item');
            if (!li) return;
            var pos = parseInt(li.dataset.pos, 10);
            if (e.target.closest('.queue-remove')) { removeAt(pos); return; }
            playQueuePos(pos);
        });

        var dragFrom = null;
        function clearDragOver() {
            var marked = queueList.querySelectorAll('.drag-over');
            Array.prototype.forEach.call(marked, function (n) { n.classList.remove('drag-over'); });
        }
        queueList.addEventListener('dragstart', function (e) {
            var li = e.target.closest('.queue-item');
            if (!li) return;
            dragFrom = parseInt(li.dataset.pos, 10);
            li.classList.add('dragging');
            if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
        });
        queueList.addEventListener('dragend', function (e) {
            var li = e.target.closest('.queue-item');
            if (li) li.classList.remove('dragging');
            clearDragOver();
            dragFrom = null;
        });
        queueList.addEventListener('dragover', function (e) {
            if (dragFrom === null) return;
            e.preventDefault();
            var li = e.target.closest('.queue-item');
            if (!li) return;
            clearDragOver();
            li.classList.add('drag-over');
        });
        queueList.addEventListener('drop', function (e) {
            if (dragFrom === null) return;
            e.preventDefault();
            var li = e.target.closest('.queue-item');
            clearDragOver();
            if (!li) return;
            moveItem(dragFrom, parseInt(li.dataset.pos, 10));
            dragFrom = null;
        });
    }

    player.addEventListener('play', function () { if (playBtn) playBtn.textContent = '⏸'; });
    player.addEventListener('pause', function () {
        if (playBtn) playBtn.textContent = '▶';
        saveResume(true);
    });

    // Capture the exact position/playing state before the page goes away, so the
    // next page can resume from the right spot (timeupdate only fires ~4x/sec
    // and is throttled, so it can lag a navigation by a few seconds).
    window.addEventListener('pagehide', function () { saveResume(true); });
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') saveResume(true);
    });

    player.addEventListener('loadedmetadata', function () {
        if (pbDuration) pbDuration.textContent = fmt(player.duration);
    });

    player.addEventListener('timeupdate', function () {
        if (!seeking && seek) {
            seek.value = player.duration ? (player.currentTime / player.duration) * 100 : 0;
        }
        if (pbCurrent) pbCurrent.textContent = fmt(player.currentTime);
        saveResume();
    });

    player.addEventListener('ended', function () {
        if (repeatMode === 'one') { playQueuePos(queuePos); return; }
        if (repeatMode === 'off' && !shuffle && queuePos === queue.length - 1) {
            // stop at the end of the queue
            playBtn && (playBtn.textContent = '▶');
            return;
        }
        playQueuePos(nextPos());
    });

    if (seek) {
        seek.addEventListener('input', function () { seeking = true; });
        seek.addEventListener('change', function () {
            if (player.duration) player.currentTime = (seek.value / 100) * player.duration;
            seeking = false;
        });
    }

    if (volume) {
        volume.addEventListener('input', function () { player.volume = parseFloat(volume.value); });
    }

    /* ---------- Persistence ---------- */
    var lastSave = 0;
    function writeResume() {
        if (!player.src) return;
        try {
            localStorage.setItem(RESUME_KEY, JSON.stringify({
                src: player.src,
                time: player.currentTime,
                playing: !player.paused
            }));
        } catch (e) {}
    }
    // Throttled during playback; force=true bypasses the throttle so we capture
    // the exact position on pause and right before navigating away.
    function saveResume(force) {
        var now = Date.now();
        if (!force && now - lastSave < 3000) return;
        lastSave = now;
        writeResume();
    }

    function saveQueue() {
        try {
            localStorage.setItem(QUEUE_KEY, JSON.stringify({ queue: queue, pos: queuePos }));
        } catch (e) {}
    }

    // The queue is self-contained, so it restores regardless of which folder
    // page we're on. Items from an older index-based format are ignored.
    function restoreQueue() {
        var data = null;
        try { data = JSON.parse(localStorage.getItem(QUEUE_KEY) || 'null'); } catch (e) {}
        if (!data || !Array.isArray(data.queue)) return;
        var clean = [];
        var seen = {};
        for (var i = 0; i < data.queue.length; i++) {
            var d = data.queue[i];
            if (!d || typeof d !== 'object' || typeof d.src !== 'string' || !d.src || seen[d.src]) continue;
            seen[d.src] = 1;
            clean.push({
                src: d.src,
                title: d.title || '',
                artist: d.artist || '',
                album: d.album || '',
                duration: d.duration || '',
                cover: d.cover || ''
            });
        }
        queue = clean;
        queuePos = (typeof data.pos === 'number' && data.pos >= 0 && data.pos < queue.length) ? data.pos : -1;
    }

    // Resume playback on the first user gesture when the browser's autoplay
    // policy blocked an automatic play() (common right after a page reload).
    function resumeOnGesture() {
        function go() {
            document.removeEventListener('pointerdown', go);
            document.removeEventListener('keydown', go);
            document.removeEventListener('touchstart', go);
            var p = player.play();
            if (p && p.catch) p.catch(function () {});
        }
        document.addEventListener('pointerdown', go);
        document.addEventListener('keydown', go);
        document.addEventListener('touchstart', go);
    }

    /* ---------- Init: restore queue, then resume the last track ---------- */
    restoreQueue();

    (function restore() {
        var resume = null;
        try { resume = JSON.parse(localStorage.getItem(RESUME_KEY) || 'null'); } catch (e) {}
        var d = currentDescriptor();
        if (d) {
            loadDescriptor(d, false); // load paused; we seek then (auto)play below
            if (resume && resume.src === d.src) {
                player.addEventListener('loadedmetadata', function seekOnce() {
                    player.removeEventListener('loadedmetadata', seekOnce);
                    // Seek first so playback continues from the saved spot with no
                    // audible blip from 0:00.
                    if (resume.time && resume.time < player.duration) {
                        player.currentTime = resume.time;
                    }
                    // Keep playing across navigation. The browser's autoplay policy
                    // often blocks this on a fresh page (e.g. after a reload); when
                    // it does, arm a one-time listener so playback resumes the moment
                    // the user clicks/taps/presses a key anywhere on the page.
                    if (resume.playing) {
                        var p = player.play();
                        if (p && p.catch) p.catch(function () { resumeOnGesture(); });
                    }
                });
            }
        } else {
            // Empty state: nothing to play yet, so hide the placeholder cover.
            if (pbCover) pbCover.style.visibility = 'hidden';
        }
        renderQueue();
    })();
})();
