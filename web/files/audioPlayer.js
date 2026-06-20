// audioPlayer.js — custom sticky player, search, shuffle/repeat, theme, resume.
(function () {
    'use strict';

    var THEME_KEY = 'mp3gallery:theme';
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

    /* ---------- Back button ---------- */
    var backButton = document.getElementById('backButton');
    if (backButton) {
        backButton.addEventListener('click', function () { window.history.back(); });
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
    if (!tracks.length || !player) return; // folder-only page

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

    // The queue holds DOM-track indices (into `tracks`). It starts as the full
    // list in order, so default playback behaviour is unchanged. `queuePos` is
    // the position within `queue` of the track that's playing (-1 = none).
    var queue = tracks.map(function (_, i) { return i; });
    var queuePos = -1;
    var shuffle = false;
    var repeatMode = 'off'; // off | all | one
    var seeking = false;

    function currentTrackIndex() { return queuePos >= 0 ? queue[queuePos] : -1; }

    function fmt(s) {
        if (!isFinite(s) || s < 0) s = 0;
        s = Math.floor(s);
        var m = Math.floor(s / 60);
        var sec = s % 60;
        return m + ':' + (sec < 10 ? '0' : '') + sec;
    }

    function setActive(index) {
        tracks.forEach(function (t) { t.classList.remove('playing'); });
        var el = tracks[index];
        if (el) el.classList.add('playing');
    }

    function loadTrack(index, autoplay) {
        if (index < 0 || index >= tracks.length) return;
        var el = tracks[index];
        player.src = el.getAttribute('data-src');
        if (bar) bar.hidden = false;
        setActive(index);

        var cover = el.getAttribute('data-cover');
        if (cover) { pbCover.src = cover; pbCover.style.visibility = 'visible'; }
        else { pbCover.removeAttribute('src'); pbCover.style.visibility = 'hidden'; }

        pbTitle.textContent = el.getAttribute('data-title') || '';
        var artist = el.getAttribute('data-artist') || '';
        var album = el.getAttribute('data-album') || '';
        pbArtist.textContent = [artist, album].filter(Boolean).join(' · ');

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
        loadTrack(queue[pos], true);
        renderQueue();
        saveQueue();
    }

    function playTrack(trackIndex) {
        var pos = queue.indexOf(trackIndex);
        if (pos === -1) { // was removed from the queue — re-insert after current
            pos = queuePos >= 0 ? queuePos + 1 : queue.length;
            queue.splice(pos, 0, trackIndex);
        }
        playQueuePos(pos);
    }

    /* ---------- Queue mutation ---------- */
    // Drop a track from the queue (but never the one playing), keeping queuePos valid.
    function removeFromQueue(trackIndex) {
        var idx = queue.indexOf(trackIndex);
        if (idx === -1 || idx === queuePos) return;
        queue.splice(idx, 1);
        if (idx < queuePos) queuePos--;
    }

    function playNext(trackIndex) {
        removeFromQueue(trackIndex);
        var at = queuePos >= 0 ? queuePos + 1 : 0;
        queue.splice(at, 0, trackIndex);
        renderQueue();
        saveQueue();
    }

    function addToQueue(trackIndex) {
        removeFromQueue(trackIndex);
        queue.push(trackIndex);
        renderQueue();
        saveQueue();
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
        var curDom = currentTrackIndex();
        var item = queue.splice(from, 1)[0];
        queue.splice(to, 0, item);
        if (curDom >= 0) queuePos = queue.indexOf(curDom);
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
        queue.forEach(function (trackIndex, pos) {
            var t = tracks[trackIndex];
            var li = document.createElement('li');
            li.className = 'queue-item' + (pos === queuePos ? ' current' : '');
            li.setAttribute('draggable', 'true');
            li.dataset.pos = pos;

            var coverWrap = document.createElement('span');
            coverWrap.className = 'queue-cover';
            var coverSrc = t.getAttribute('data-cover');
            if (coverSrc) {
                var img = document.createElement('img');
                img.src = coverSrc;
                img.alt = '';
                coverWrap.appendChild(img);
            } else {
                coverWrap.textContent = '🎵';
            }

            var meta = document.createElement('span');
            meta.className = 'queue-item-meta';
            var title = document.createElement('span');
            title.className = 'queue-item-title';
            title.textContent = t.getAttribute('data-title') || '';
            var sub = document.createElement('span');
            sub.className = 'queue-item-sub';
            var artist = t.getAttribute('data-artist') || '';
            var album = t.getAttribute('data-album') || '';
            sub.textContent = [artist, album].filter(Boolean).join(' · ');
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

    /* ---------- Track row interactions ---------- */
    tracks.forEach(function (el, i) {
        el.addEventListener('click', function (e) {
            if (e.target.closest('.track-download')) return; // let downloads through
            if (e.target.closest('.play-next')) { e.stopPropagation(); playNext(i); return; }
            if (e.target.closest('.add-queue')) { e.stopPropagation(); addToQueue(i); return; }
            if (i === currentTrackIndex() && !player.paused) { player.pause(); return; }
            if (i === currentTrackIndex() && player.paused && player.src) { player.play(); return; }
            playTrack(i);
        });
    });

    if (playBtn) playBtn.addEventListener('click', function () {
        if (queuePos === -1) { playQueuePos(0); return; }
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
    player.addEventListener('pause', function () { if (playBtn) playBtn.textContent = '▶'; });

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
    function saveResume() {
        var now = Date.now();
        if (now - lastSave < 3000) return;
        lastSave = now;
        try {
            localStorage.setItem(RESUME_KEY, JSON.stringify({
                src: player.src,
                time: player.currentTime
            }));
        } catch (e) {}
    }

    function saveQueue() {
        try {
            localStorage.setItem(QUEUE_KEY, JSON.stringify({
                n: tracks.length, queue: queue, pos: queuePos
            }));
        } catch (e) {}
    }

    function restoreQueue() {
        var data = null;
        try { data = JSON.parse(localStorage.getItem(QUEUE_KEY) || 'null'); } catch (e) {}
        // Only trust a saved queue if the track list looks unchanged.
        if (!data || data.n !== tracks.length || !Array.isArray(data.queue) || !data.queue.length) return;
        var seen = {};
        for (var i = 0; i < data.queue.length; i++) {
            var v = data.queue[i];
            if (typeof v !== 'number' || v < 0 || v >= tracks.length || seen[v]) return;
            seen[v] = 1;
        }
        queue = data.queue.slice();
        queuePos = (typeof data.pos === 'number' && data.pos >= -1 && data.pos < queue.length) ? data.pos : -1;
    }

    /* ---------- Init: restore queue, then resume the last track ---------- */
    restoreQueue();

    (function restore() {
        var data = null;
        try { data = JSON.parse(localStorage.getItem(RESUME_KEY) || 'null'); } catch (e) {}
        if (data && data.src) {
            for (var i = 0; i < tracks.length; i++) {
                // Compare against the absolute src the browser would resolve to.
                var a = document.createElement('a');
                a.href = tracks[i].getAttribute('data-src');
                if (a.href === data.src) {
                    var pos = queue.indexOf(i);
                    if (pos === -1) { queue.push(i); pos = queue.length - 1; }
                    queuePos = pos;
                    loadTrack(i, false); // paused so autoplay policy doesn't block
                    player.addEventListener('loadedmetadata', function seekOnce() {
                        if (data.time && data.time < player.duration) player.currentTime = data.time;
                        player.removeEventListener('loadedmetadata', seekOnce);
                    });
                    renderQueue();
                    return;
                }
            }
        }
        // No resume match — still show the last queue position if we have one.
        if (queuePos >= 0) loadTrack(queue[queuePos], false);
        renderQueue();
    })();
})();
