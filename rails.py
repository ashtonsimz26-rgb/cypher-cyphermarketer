#!/usr/bin/env python3.12
"""
rails.py — content rails, enforced in code. SOUL.md is canonical; this file is
the machine-checkable subset.

PRICE POLICY (ruled 2026-08-19)
  The contract allows price claims only from PK data, <=7 days old, and ALWAYS
  attributed to the real sneaker. Two consequences, both implemented here:

  1. FAIL-CLOSED DEFAULT. If freshness cannot be positively verified, the draft
     OMITS the number from the agent's own voice. Silence costs nothing; an
     unverifiable price claim on a brand account is not recoverable.

  2. ATTRIBUTION IS STILL REQUIRED WHEN THE CARD SHOWS A FIGURE. The card render
     displays "EST. VALUE $N" on its face. Omitting the number from the text
     does NOT remove it from the image — so a post whose image carries the value
     field MUST carry real-sneaker attribution in the text, or the figure reads
     as the CARD's worth. That is exactly the ambiguity locked decision 3
     rejects (Apple 5.3 exposure). Enforced by check_draft().
"""
from __future__ import annotations
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

PK_DATA = Path.home() / "Documents/openclaw/CYPHER/sneaker_market_agent/data"
FRESHNESS_DAYS = 7

GAMBLING = ("bet", "betting", "jackpot", "wager", "gamble", "gambling", "lottery",
            "odds of winning", "casino", "spin to win")
INVESTMENT = ("invest", "investment", "roi", "returns", "portfolio play",
              "guaranteed profit", "flip for profit", "appreciate in value")
CARD_VALUE_CLAIMS = ("this card is worth", "card is worth", "cards are worth",
                     "worth $", "cash out", "sell your cards for", "redeem for cash")
COMPETITORS = ("stockx", "goat.com", "boxed up", "sole retriever", "kicksdb")
ATTRIBUTION_MARKERS = ("real pair", "real pairs", "the real shoe", "resale market",
                       "resell", "resells", "real-world resale", "real pair's")


def price_claim_allowed(style_code: str | None) -> tuple[bool, str]:
    """Fail-closed: True only if PK holds a price for this style within N days."""
    if not style_code or style_code in ("N/A", ""):
        return False, "no style_code to look up in PK"
    if not PK_DATA.is_dir():
        return False, "PK data directory not reachable"
    cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)
    try:
        for p in PK_DATA.rglob("*.json"):
            try:
                if datetime.fromtimestamp(p.stat().st_mtime, timezone.utc) < cutoff:
                    continue
                if style_code in p.read_text(encoding="utf-8", errors="ignore"):
                    return True, "PK file %s (<=%dd)" % (p.name, FRESHNESS_DAYS)
            except Exception:
                continue
    except Exception as e:
        return False, "PK scan failed: %s" % type(e).__name__
    return False, "no PK record within %d days" % FRESHNESS_DAYS


def check_draft(text: str, *, card_shows_value: bool, pool_reachable: bool,
                price_verified: bool) -> list[tuple[str, bool, str]]:
    low = text.lower()
    has_attr = any(m in low for m in ATTRIBUTION_MARKERS)
    checks = [
        ("no gambling language", not any(w in low for w in GAMBLING), ""),
        ("no investment framing", not any(w in low for w in INVESTMENT), ""),
        ("no card-value claim", not any(w in low for w in CARD_VALUE_CLAIMS), ""),
        ("no competitor named", not any(w in low for w in COMPETITORS), ""),
        ("shoe is pool-reachable (R1/R2)", pool_reachable,
         "never show a reserve shoe as pullable"),
        ("card image w/ value figure carries real-sneaker attribution",
         (not card_shows_value) or has_attr,
         "card renders EST. VALUE; text must scope it to the real pair"),
        ("no unverified price asserted in agent voice",
         price_verified or not re.search(r"(trades?|sells?|going|worth|sits?)\s+(for\s+|at\s+|around\s+)?\$", low),
         "PK freshness unverified -> omit the number from our own voice"),
    ]
    return checks


def report(checks) -> bool:
    ok = True
    for label, passed, note in checks:
        ok &= passed
        print("  %-4s %s%s" % ("PASS" if passed else "FAIL", label,
                               ("  — " + note) if (note and not passed) else ""))
    return ok
