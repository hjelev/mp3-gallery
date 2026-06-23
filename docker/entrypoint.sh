#!/bin/sh
# Seed the shared front-end assets into the output folder (generate.py writes
# pages + covers there but does not copy style.css / audioPlayer.js), then run
# the generator. With REFRESH_INTERVAL > 0 the generator re-runs on that
# interval to pick up new music; 0 (or empty) means generate once and exit.
set -e

: "${HTML_FOLDER:=/site}"
: "${REFRESH_INTERVAL:=0}"

mkdir -p "$HTML_FOLDER/files"
cp -f web/files/style.css web/files/audioPlayer.js "$HTML_FOLDER/files/"

while true; do
    echo "[entrypoint] generating gallery into $HTML_FOLDER ..."
    python generate.py
    echo "[entrypoint] done."

    if [ -z "$REFRESH_INTERVAL" ] || [ "$REFRESH_INTERVAL" = "0" ]; then
        break
    fi
    echo "[entrypoint] sleeping ${REFRESH_INTERVAL}s before next refresh ..."
    sleep "$REFRESH_INTERVAL"
done
