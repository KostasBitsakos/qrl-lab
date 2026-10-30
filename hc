#!/bin/sh
# short alias so the host check can be typed on a phone
exec python3 "$(dirname "$0")/.lab/j236/host_check.py" "$@"
