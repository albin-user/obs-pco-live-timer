#!/usr/bin/env bash
# Restart wrapper for gui.py — restarts on crash, exits on clean shutdown.
#
# Used by the autostart .desktop entry so the timer recovers automatically
# if it crashes mid-service. Gives up after too many rapid restarts to
# avoid an infinite crash loop.

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_TAG="pco-timer-restart"

MAX_RAPID_RESTARTS=5
RAPID_WINDOW=60  # seconds

# On first boot, wait for XFCE panel and OBS to initialize
if [ -z "$PCO_TIMER_RESTARTED" ]; then
    sleep 5
fi
export PCO_TIMER_RESTARTED=1

restarts=0
window_start=$(date +%s)

while true; do
    "$DIR/.venv/bin/python" "$DIR/gui.py"
    exit_code=$?

    # Clean exit (user clicked Quit) — don't restart
    if [ $exit_code -eq 0 ]; then
        logger -t "$LOG_TAG" "gui.py exited cleanly, not restarting"
        break
    fi

    # Permanent failure (missing GTK, bad environment) — don't restart
    if [ $exit_code -eq 2 ]; then
        logger -t "$LOG_TAG" "gui.py exited with permanent error (code 2), not restarting"
        break
    fi

    now=$(date +%s)
    elapsed=$((now - window_start))

    if [ $elapsed -lt $RAPID_WINDOW ]; then
        restarts=$((restarts + 1))
        if [ $restarts -ge $MAX_RAPID_RESTARTS ]; then
            logger -t "$LOG_TAG" "Too many rapid restarts ($restarts in ${elapsed}s), giving up"
            break
        fi
    else
        restarts=1
        window_start=$now
    fi

    logger -t "$LOG_TAG" "gui.py crashed (exit code $exit_code), restarting in 3s (restart $restarts/$MAX_RAPID_RESTARTS)"
    sleep 3
done
