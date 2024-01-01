// audioPlayer.js
var audioList = document.querySelectorAll('.audio-list.mp3');
var player = document.getElementById('player');
var prevButton = document.getElementById('prevButton');
var nextButton = document.getElementById('nextButton');
var current = null;

window.onload = function() {
    if (audioList.length > 0) {
        player.src = audioList[0].getAttribute('data-src');
        audioList[0].classList.add('playing');
        current = audioList[0];
    }
};

for (var i = 0; i < audioList.length; i++) {
    audioList[i].addEventListener('click', function() {
        if (current) {
            current.classList.remove('playing');
        }
        if (!player.paused) {
            player.pause();
        }
        player.src = this.getAttribute('data-src');
        player.play();
        this.classList.add('playing');
        current = this;
    });
}

player.addEventListener('ended', function() {
    nextButton.click();
});

prevButton.addEventListener('click', function() {
    var currentIndex = Array.from(audioList).indexOf(current);
    var prevIndex = (currentIndex - 1 + audioList.length) % audioList.length;
    var prevAudio = audioList[prevIndex];
    prevAudio.click();
});

nextButton.addEventListener('click', function() {
    var currentIndex = Array.from(audioList).indexOf(current);
    var nextIndex = (currentIndex + 1) % audioList.length;
    var nextAudio = audioList[nextIndex];
    nextAudio.click();
});