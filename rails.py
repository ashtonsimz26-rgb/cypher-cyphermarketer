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


PRICE_TOLERANCE = 0.25          # catalog may differ from PK by at most 25%


def pk_price(style_code: str | None) -> tuple[int | None, str]:
    """Newest PK lowest-ask within the freshness window, in whole USD.

    PK writes one file per style per day under raw_market/price_refresh/<date>/.
    We take the NEWEST such file, not the first one found on disk — ordering by
    mtime matters, and an arbitrary rglob hit can be weeks old."""
    if not style_code or style_code in ("N/A", ""):
        return None, "no style_code"
    if not PK_DATA.is_dir():
        return None, "PK data unreachable"
    cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)
    best = None
    for p in PK_DATA.glob("raw_market/price_refresh/*/%s.json" % style_code):
        try:
            mt = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
        except Exception:
            continue
        if mt >= cutoff and (best is None or mt > best[0]):
            best = (mt, p)
    if not best:
        return None, "no PK price file within %d days" % FRESHNESS_DAYS
    try:
        import json as _j
        hits = (_j.loads(best[1].read_text()).get("raw", {}) or {}).get("hits") or []
        cents = hits[0].get("lowest_price_cents") if hits else None
        if not cents:
            return None, "PK file has no lowest_price_cents"
        return int(cents) // 100, "PK %s" % best[0].strftime("%Y-%m-%d")
    except Exception as e:
        return None, "PK parse failed: %s" % type(e).__name__


def price_claim_allowed(style_code: str | None,
                        catalog_resale: int | None = None) -> tuple[bool, str]:
    """Fresh PK price AND catalog agreement. Both, or no number in our voice.

    ★ THE BUG THIS REPLACES (found 2026-08-20 before it ever posted): the old
    version returned True if ANY recently-modified PK file merely CONTAINED the
    style code. That verifies the recency of a lookup, not the correctness of a
    number. It green-lit a "$2,000" price-journey draft for the DQM Bacon while
    PK's own file THAT MORNING put the lowest ask at $450 — a 4.4x overstatement
    on the brand account, with the card image showing the same wrong figure.

    Divergence is now a HARD BLOCK, not a warning: if the catalog and the market
    disagree beyond tolerance, the card's own EST. VALUE is untrustworthy, so no
    price claim is safe in either the text or the image."""
    price, why = pk_price(style_code)
    if price is None:
        return False, why
    if catalog_resale is None:
        return True, "%s: $%d" % (why, price)
    drift = abs(catalog_resale - price) / max(1, price)
    if drift > PRICE_TOLERANCE:
        return False, ("catalog $%d vs %s $%d — %.0f%% drift, exceeds %.0f%% tolerance"
                       % (catalog_resale, why, price, drift * 100, PRICE_TOLERANCE * 100))
    return True, "%s: $%d (catalog $%d, %.0f%% drift)" % (why, price, catalog_resale, drift * 100)


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
