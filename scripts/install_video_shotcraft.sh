#!/usr/bin/env bash
# Install Vincentwei1021/video-shotcraft as a Cursor (and Claude) agent skill.
# https://github.com/Vincentwei1021/video-shotcraft
set -euo pipefail

DEST="${1:-$HOME/.cursor/skills/video-shotcraft}"
REPO="https://github.com/Vincentwei1021/video-shotcraft.git"

mkdir -p "$(dirname "$DEST")"
if [[ -d "$DEST/.git" ]]; then
  echo "Updating $DEST"
  git -C "$DEST" pull --ff-only || git -C "$DEST" fetch --depth 1 origin main
else
  echo "Cloning video-shotcraft → $DEST"
  git clone --depth 1 "$REPO" "$DEST"
fi

# Optional Claude Code / Codex symlinks when those dirs exist
for link_dir in "$HOME/.claude/skills" "$HOME/.codex/skills"; do
  if [[ -d "$(dirname "$link_dir")" ]]; then
    mkdir -p "$link_dir"
    if [[ ! -e "$link_dir/video-shotcraft" ]]; then
      ln -s "$DEST" "$link_dir/video-shotcraft"
      echo "Linked $link_dir/video-shotcraft"
    fi
  fi
done

echo "OK — skill at $DEST"
echo "Gallery: https://vincentwei1021.github.io/video-shotcraft/"
echo "ClipOps notes: docs/VIDEO_SHOTCRAFT.md"
