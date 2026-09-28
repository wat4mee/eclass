#!/bin/bash
# Install the launchd agents for this checkout (macOS):
#   com.eclass.sync    sync.py --all every 3 hours
#   com.eclass.notify  notify.py every 30 minutes (deadline reminders)
#   com.eclass.web     dashboard on http://127.0.0.1:5050, always on
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTS" "$ROOT/data/logs"
for name in sync notify web; do
  dst="$AGENTS/com.eclass.$name.plist"
  sed "s#__ROOT__#$ROOT#g" "$ROOT/deploy/com.eclass.$name.plist" > "$dst"
  plutil -lint "$dst" > /dev/null
  launchctl bootout "gui/$(id -u)/com.eclass.$name" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$dst"
  echo "installed com.eclass.$name"
done
