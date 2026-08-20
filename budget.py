#!/usr/bin/env python3.12
"""budget.py — spend + cap guards enforced by the SCHEDULER, not just by hand.

Two independent limits:
  * POSTS: hard 4 / rolling 24h (x_client also enforces at post time; this stops
    the digest wasting a generation on a draft that could never post).
  * xAI IMAGE SPEND: circuit breaker at $1.00/day. Expected burn is ~$0.08-0.12
    a day, so $1 is ~10x expected — reaching it means something is looping, and
    the correct response is to STOP and alert, not to keep spending.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import x_client as X  # noqa: E402

DAILY_IMAGE_SPEND_LIMIT = 1.00

# QUIET HOURS (local). No proposal may reach Telegram between these times, and
# no image spend may be incurred for one. Overnight drop matches QUEUE and ride
# into the morning digest instead. Born of 2026-08-20, when the RSS job buzzed
# Ashton with proposals at 23:44, 01:45 and 03:46 — one of which was the wrong
# shoe. Matching overnight is fine (it is free); interrupting a person is not.
QUIET_START_H, QUIET_START_M = 22, 0
QUIET_END_H, QUIET_END_M = 8, 30
BACKDROP_LEDGER = HERE / "ledger" / "backdrops.jsonl"


def in_quiet_hours(now=None) -> bool:
    from datetime import datetime as _dt
    n = now or _dt.now()
    mins = n.hour * 60 + n.minute
    start = QUIET_START_H * 60 + QUIET_START_M
    end = QUIET_END_H * 60 + QUIET_END_M
    return mins >= start or mins < end          # window wraps midnight


def image_spend_last_24h() -> float:
    if not BACKDROP_LEDGER.exists():
        return 0.0
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    total = 0.0
    for line in BACKDROP_LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if r.get("event") != "generated":
                continue
            if datetime.fromisoformat(r["ts"]) >= cutoff:
                total += float(r.get("cost_usd") or 0)
        except Exception:
            continue
    return round(total, 4)


def posts_remaining() -> int:
    return max(0, X.MAX_POSTS_24H - X.posts_last_24h())


def check(require_image: bool = True, respect_quiet: bool = False) -> tuple[bool, str]:
    if respect_quiet and in_quiet_hours():
        return False, ("quiet hours %02d:%02d-%02d:%02d local — queue it, do not propose"
                       % (QUIET_START_H, QUIET_START_M, QUIET_END_H, QUIET_END_M))
    spend = image_spend_last_24h()
    if require_image and spend >= DAILY_IMAGE_SPEND_LIMIT:
        return False, ("CIRCUIT BREAKER: xAI image spend $%.2f in 24h >= $%.2f limit"
                       % (spend, DAILY_IMAGE_SPEND_LIMIT))
    if posts_remaining() <= 0:
        return False, "post cap reached (%d/%d in rolling 24h)" % (
            X.posts_last_24h(), X.MAX_POSTS_24H)
    return True, "ok (spend $%.2f, %d posts left)" % (spend, posts_remaining())


if __name__ == "__main__":
    ok, why = check()
    print("  %s — %s" % ("OK" if ok else "BLOCKED", why))
