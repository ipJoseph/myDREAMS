#!/bin/bash
# clip-image.sh: Save clipboard image to file and print the path
# Usage: clip-image.sh [optional-name]
#
# After taking a screenshot (or copying an image), run this script.
# It saves the clipboard image to ~/Pictures/Screenshots/ and prints the path
# so you can paste it into Claude Code.
#
# Requires: wl-clipboard (sudo apt install wl-clipboard)

set -euo pipefail

SCREENSHOT_DIR="$HOME/Pictures/Screenshots"
mkdir -p "$SCREENSHOT_DIR"

# Check if wl-paste is available
if ! command -v wl-paste &>/dev/null; then
    echo "Error: wl-paste not found. Install with: sudo apt install wl-clipboard" >&2
    exit 1
fi

# Check if clipboard has image data
MIME=$(wl-paste --list-types 2>/dev/null | grep -m1 'image/' || true)
if [ -z "$MIME" ]; then
    echo "Error: No image data in clipboard." >&2
    echo "Copy a screenshot first (PrintScreen or selection tool)." >&2
    exit 1
fi

# Determine extension from MIME type
case "$MIME" in
    image/png)  EXT="png" ;;
    image/jpeg) EXT="jpg" ;;
    image/webp) EXT="webp" ;;
    image/bmp)  EXT="bmp" ;;
    *)          EXT="png" ;;
esac

# Generate filename
if [ -n "${1:-}" ]; then
    FILENAME="${1}.${EXT}"
else
    FILENAME="clip-$(date +%Y%m%d-%H%M%S).${EXT}"
fi

FILEPATH="$SCREENSHOT_DIR/$FILENAME"

# Save image from clipboard
wl-paste --type "$MIME" > "$FILEPATH"

# Verify it was saved
if [ -s "$FILEPATH" ]; then
    echo "$FILEPATH"
else
    echo "Error: Failed to save clipboard image." >&2
    rm -f "$FILEPATH"
    exit 1
fi
