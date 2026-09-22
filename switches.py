#!/usr/bin/env python3.12
"""switches.py — operator switches, read from .env. One switch per concern.

IMAGES_ENABLED (added 2026-09-22; images turned OFF at Ashton's request)
────────────────────────────────────────────────────────────────────────
One setting in .env decides whether the marketer makes or sends ANY image:

    IMAGES_ENABLED=false   -> proposals and posts are TEXT ONLY
    IMAGES_ENABLED=true    -> the image path, unchanged
    (absent)               -> IMAGES_ENABLED_DEFAULT below (true)

When disabled, nothing image-related runs: no card render, no backdrop, no call
to either image API (zero image spend), no Frame Check (recorded as SKIPPED, not
dropped), no photo on Telegram, no media upload to X. The image code is left in
place, not deleted or commented out, so turning images back on is this one line.

★ A value that is neither a recognised true nor a recognised false reads as
DISABLED, with a warning. A typo must never turn image spend back on. The one
case that reads as enabled without saying so is the key being absent, which is
the code default and the state every install had before this switch existed.
"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import x_client as X  # noqa: E402

IMAGES_ENABLED_DEFAULT = True
_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


def images_enabled(env: dict | None = None) -> bool:
    """The ONE reader of IMAGES_ENABLED. Every image decision goes through it."""
    if env is None:
        env = X.load_env(Path(X.DEFAULT_ENV))
    raw = env.get("IMAGES_ENABLED")
    if raw is None:
        return IMAGES_ENABLED_DEFAULT
    v = str(raw).strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    sys.stderr.write("WARN: IMAGES_ENABLED=%r is not true/false — treating it as "
                     "DISABLED (text only). Fix .env.\n" % raw)
    return False


if __name__ == "__main__":
    print("  IMAGES_ENABLED = %s" % ("true (image path)" if images_enabled()
                                     else "false (TEXT ONLY — no image made, sent or spent)"))
