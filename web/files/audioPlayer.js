// audioPlayer.js — custom sticky player, search, shuffle/repeat, theme, resume.
(function () {
    'use strict';

    var THEME_KEY = 'mp3gallery:theme';
    var RESUME_KEY = 'mp3gallery:resume';

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

    var current = -1;
    var shuffle = false;
    var repeatMode = 'off'; // off | all | one
    var seeking = false;

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
        current = index;
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

    function playIndex(index) { loadTrack(index, true); }

    function nextIndex() {
        if (shuffle && tracks.length > 1) {
            var n;
            do { n = Math.floor(Math.random() * tracks.length); } while (n === current);
            return n;
        }
        return (current + 1) % tracks.length;
    }

    function prevIndex() {
        if (shuffle && tracks.length > 1) {
            var n;
            do { n = Math.floor(Math.random() * tracks.length); } while (n === current);
            return n;
        }
        return (current - 1 + tracks.length) % tracks.length;
    }

    tracks.forEach(function (el, i) {
        el.addEventListener('click', function (e) {
            if (e.target.closest('.track-download')) return; // let downloads through
            if (i === current && !player.paused) { player.pause(); return; }
            if (i === current && player.paused && player.src) { player.play(); return; }
            playIndex(i);
        });
    });

    if (playBtn) playBtn.addEventListener('click', function () {
        if (current === -1) { playIndex(0); return; }
        if (player.paused) player.play(); else player.pause();
    });
    if (nextBtn) nextBtn.addEventListener('click', function () { playIndex(nextIndex()); });
    if (prevBtn) prevBtn.addEventListener('click', function () {
        if (player.currentTime > 3) { player.currentTime = 0; return; }
        playIndex(prevIndex());
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
        if (repeatMode === 'one') { playIndex(current); return; }
        if (repeatMode === 'off' && !shuffle && current === tracks.length - 1) {
            // stop at the end of the list
            playBtn && (playBtn.textContent = '▶');
            return;
        }
        playIndex(nextIndex());
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

    /* ---------- Resume ---------- */
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

    (function restore() {
        var data = null;
        try { data = JSON.parse(localStorage.getItem(RESUME_KEY) || 'null'); } catch (e) {}
        if (!data || !data.src) return;
        for (var i = 0; i < tracks.length; i++) {
            // Compare against the absolute src the browser would resolve to.
            var a = document.createElement('a');
            a.href = tracks[i].getAttribute('data-src');
            if (a.href === data.src) {
                loadTrack(i, false); // paused so autoplay policy doesn't block
                player.addEventListener('loadedmetadata', function seekOnce() {
                    if (data.time && data.time < player.duration) player.currentTime = data.time;
                    player.removeEventListener('loadedmetadata', seekOnce);
                });
                return;
            }
        }
    })();
})();
