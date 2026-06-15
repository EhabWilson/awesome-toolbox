#!/bin/bash
# Bidirectional newer-wins rclone sync of a OneDrive folder <-> a local folder.
# Usage: onedrive_sync.sh <remote> <local>
#   e.g. onedrive_sync.sh "onedrive:<remote-folder>" "$HOME/<local-folder>"
# Concrete remote/local paths live in the per-sync launchd agents (not in this repo).
# See onedrive_sync.README.md for setup and cautions.

REMOTE="$1"
LOCAL="$2"
if [ -z "$REMOTE" ] || [ -z "$LOCAL" ]; then
    echo "usage: $0 <remote> <local>" >&2
    exit 2
fi

# Lock keyed to the local path so independent syncs don't block each other.
LOCKDIR="/tmp/onedrive_sync.$(printf '%s' "$LOCAL" | md5 -q).lock"
mkdir "$LOCKDIR" 2>/dev/null || exit 0
trap 'rmdir "$LOCKDIR"' EXIT

R=/opt/homebrew/bin/rclone
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting sync: $REMOTE <-> $LOCAL"
"$R" copy --update "$REMOTE" "$LOCAL"
"$R" copy --update "$LOCAL" "$REMOTE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sync finished: $REMOTE <-> $LOCAL"
