#!/bin/bash
# Stop and remove the eClass launchd agents (data and code stay untouched).
for name in sync notify web; do
  launchctl bootout "gui/$(id -u)/com.eclass.$name" 2>/dev/null && echo "stopped com.eclass.$name"
  rm -f "$HOME/Library/LaunchAgents/com.eclass.$name.plist"
done
