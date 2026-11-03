#!/bin/sh
# Invoked by the desktop session; systemd owns Chromium restart/recovery.
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
xset s off -dpms 2>/dev/null || true
xset s noblank 2>/dev/null || true
systemctl --user import-environment DISPLAY XAUTHORITY
exec systemctl --user start home-monitor-kiosk.service
