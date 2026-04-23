#!/usr/bin/env bash
# Creates a timestamped backup of everything git doesn't track.
# Usage: bash backup.sh
# Keeps the 10 most recent backups, deletes older ones.

set -euo pipefail

BACKUP_DIR="/home/adminos/backups/email-processor"
STAMP=$(date '+%Y-%m-%d_%H-%M-%S')
ARCHIVE="$BACKUP_DIR/backup_$STAMP.tar.gz"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$BACKUP_DIR"

tar -czf "$ARCHIVE" \
    --exclude='.git' \
    --exclude='temp' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    -C "$(dirname "$SRC_DIR")" \
    "$(basename "$SRC_DIR")"

echo "Backup saved: $ARCHIVE ($(du -sh "$ARCHIVE" | cut -f1))"

# Keep only the 10 most recent backups
ls -t "$BACKUP_DIR"/backup_*.tar.gz | tail -n +11 | xargs -r rm --
REMAINING=$(ls "$BACKUP_DIR"/backup_*.tar.gz | wc -l)
echo "Backups kept: $REMAINING"
