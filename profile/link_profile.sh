#!/usr/bin/env bash
# link_profile.sh — point the Hermes profile at this repo's profile/ files.
#
# WHY THIS EXISTS. The four files that specify this agent's behaviour
# (SOUL.md, instructions.md, context.md, memory.md) are tracked HERE, in git.
# Hermes and the runtime read them from ~/.hermes/profiles/cyphermarketer/.
# Those two facts are reconciled by symlinks, not by copies: ONE file, two
# names. A mirror would be two files with one name, agreeing only where you
# happened to look — which is the exact failure this repo has already been
# bitten by once (see memory.md M001/M004).
#
# A fresh `git clone` creates the files but NOT the links. Run this once.
# It is idempotent and refuses to destroy anything it did not expect.
#
#   ./profile/link_profile.sh          # create/repair the links
#   ./profile/link_profile.sh --check  # verify only, exit 1 if wrong (CI-safe)
#
# It NEVER touches .env or anything else in the profile directory.
set -euo pipefail

REPO_PROFILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_DIR="${HERMES_PROFILE_DIR:-$HOME/.hermes/profiles/cyphermarketer}"
FILES=(SOUL.md instructions.md context.md memory.md)
CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

fail=0
for f in "${FILES[@]}"; do
  src="$REPO_PROFILE/$f"
  dst="$PROFILE_DIR/$f"

  if [[ ! -f "$src" ]]; then
    echo "FAIL  $f — missing in repo at $src" >&2; fail=1; continue
  fi

  # Already correct?
  if [[ -L "$dst" && "$(readlink "$dst")" == "$src" ]]; then
    echo "ok    $f -> repo"; continue
  fi

  # ── THE DETECTOR ────────────────────────────────────────────────────────
  # A REGULAR FILE here means the link was severed and edits since then went
  # to the profile copy, not to git. That content is NOT in version control
  # and this script will not silently overwrite it.
  if [[ -f "$dst" && ! -L "$dst" ]]; then
    if cmp -s "$dst" "$src"; then
      echo "WARN  $f is a regular file but is byte-identical to the repo copy;"
      echo "      relinking is safe (no content would be lost)."
      [[ $CHECK_ONLY -eq 1 ]] && { fail=1; continue; }
      rm "$dst"; ln -s "$src" "$dst"; echo "ok    $f -> repo (relinked)"; continue
    fi
    echo "FAIL  $f is a REGULAR FILE at $dst and DIFFERS from the repo copy." >&2
    echo "      The symlink was severed and that file holds unversioned edits." >&2
    echo "      Diff them and merge BY HAND before relinking:" >&2
    echo "        diff '$src' '$dst'" >&2
    fail=1; continue
  fi

  if [[ -e "$dst" || -L "$dst" ]]; then
    echo "FAIL  $f at $dst is neither a regular file nor the expected link." >&2
    fail=1; continue
  fi

  if [[ $CHECK_ONLY -eq 1 ]]; then
    echo "FAIL  $f — no link at $dst (run without --check to create it)" >&2
    fail=1; continue
  fi

  mkdir -p "$PROFILE_DIR"
  ln -s "$src" "$dst"
  echo "ok    $f -> repo (created)"
done

if [[ $fail -ne 0 ]]; then
  echo >&2
  echo "PROFILE LINKS ARE WRONG. The agent may be reading files that are not" >&2
  echo "under version control. Fix before trusting anything it writes." >&2
  exit 1
fi
echo
echo "All ${#FILES[@]} profile files are linked to the repo. .env untouched."
