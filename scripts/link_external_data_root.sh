#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
data_root="${1:-${ACQUITTIFY_DATA_ROOT:-$HOME/AcquittifyData}}"

paths=(
  "Corpus"
  "acquittify-data"
  "Obsidian"
  "Acquittify Storage"
  "finetune"
)

echo "Repository root: $repo_root"
echo "External data root: $data_root"
mkdir -p "$data_root"

for rel in "${paths[@]}"; do
  repo_path="$repo_root/$rel"
  target_path="$data_root/$rel"

  if [[ -L "$repo_path" ]]; then
    echo "skip (already symlink): $repo_path"
    continue
  fi

  mkdir -p "$(dirname "$target_path")"

  if [[ -e "$repo_path" && ! -e "$target_path" ]]; then
    echo "move: $repo_path -> $target_path"
    mv "$repo_path" "$target_path"
  elif [[ -e "$repo_path" && -e "$target_path" ]]; then
    echo "skip (both exist, merge manually): $repo_path and $target_path"
    continue
  elif [[ ! -e "$target_path" ]]; then
    mkdir -p "$target_path"
  fi

  rm -rf "$repo_path"
  ln -s "$target_path" "$repo_path"
  echo "linked: $repo_path -> $target_path"
done

echo "done"
