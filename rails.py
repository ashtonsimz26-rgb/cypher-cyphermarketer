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
import json
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


MIN_LISTINGS = 3                # liquidity floor — below this, no price claim


PRICE_HISTORY = PK_DATA / "price_history"


def pk_market(style_code: str | None) -> tuple[dict | None, str]:
    """Size-aware market band, read from PK's OWN canonical fields.

    ★ CORRECTED 2026-08-20. Option A turned out to be ALREADY BUILT: PK's
    Pass 3.3.1/3.3.2 compute an ADULT-SIZE-BAND summary
    (adult_band_min/median/max_cents, adult_band_variant_count) plus an observed
    band and a confidence grade, and store them per snapshot in
    data/price_history/<sku>.jsonl.

    My rail had been reading raw_market/price_refresh/<date>/<sku>.json and
    taking hits[0].lowest_price_cents — the field PK's own source comments
    explicitly warn about:

        "Algolia sorts ascending by lowest_price_cents, so this is the cheapest
         variant — typically a TODDLER SIZE. Stored for forensic context only —
         DO NOT use for decisions; use canonical_price_cents."

    So the false-alarm storm was self-inflicted twice over: wrong file, and the
    one field PK documents as not-for-decisions. Reading PK's band instead of
    re-deriving one also inherits its toddler-size exclusion and its confidence
    grading for free."""
    if not style_code or style_code in ("N/A", ""):
        return None, "no style_code"
    hist = PRICE_HISTORY / ("%s.jsonl" % style_code)
    if not hist.exists():
        return None, "no PK price history for %s" % style_code
    cutoff = datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS)
    last = None
    try:
        for line in hist.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("status") != "ok":
                continue
            try:
                ts = datetime.fromisoformat(r["captured_at"].replace("Z", "+00:00"))
            except Exception:
                continue
            if ts >= cutoff and (last is None or ts > last[0]):
                last = (ts, r)
    except Exception as e:
        return None, "PK history read failed: %s" % type(e).__name__
    if last is None:
        return None, "no ok PK snapshot within %d days" % FRESHNESS_DAYS

    a = (last[1].get("sources") or {}).get("algolia") or {}
    c = lambda k: (a.get(k) or 0) // 100
    lo, hi = c("adult_band_min_cents"), c("adult_band_max_cents")
    n = a.get("adult_band_variant_count") or 0
    if not lo or not hi:                       # band held/empty -> fall back to observed
        lo, hi = c("observed_band_min_cents"), c("observed_band_max_cents")
        n = n or (a.get("observed_band_variant_count") or 0)
    if not lo or not hi:
        return None, "PK snapshot carries no usable band"
    med = c("adult_band_median_cents") or c("observed_band_median_cents") or 0
    return ({"low": lo, "high": hi, "median": med, "n": n,
             "canonical": c("canonical_price_cents"),
             "confidence": a.get("observed_confidence"),
             "hold": a.get("canonical_hold_reason"),
             "as_of": last[0].strftime("%Y-%m-%d")},
            "PK %s adult-band" % last[0].strftime("%Y-%m-%d"))


def pk_price(style_code: str | None) -> tuple[int | None, str]:
    """Back-compat single number = the market LOW. Prefer pk_market()."""
    m, why = pk_market(style_code)
    return (m["low"], why) if m else (None, why)


def price_claim_allowed(style_code: str | None,
                        catalog_resale: int | None = None) -> tuple[bool, str]:
    """A price claim needs a LIQUID market and a catalog value inside its range.

    Two gates, both ratified 2026-08-20:

    1. LIQUIDITY. Fewer than MIN_LISTINGS live listings and we make no claim in
       either direction. A one-listing "market" is not a yardstick — it cannot
       confirm a catalog value OR condemn it, so a thin market blocks rather
       than decides.
    2. RANGE, not point. The catalog value must sit within the live cross-size
       ask range. Outside it in EITHER direction is a real signal worth
       blocking on (too high overstates; too low understates a grail).

    Replaces a point comparison against an arbitrary size's ask — see pk_market."""
    m, why = pk_market(style_code)
    if m is None:
        return False, why
    span = "$%d-$%d (median $%d, n=%d, conf=%s, %s)" % (
        m["low"], m["high"], m["median"], m["n"],
        m.get("confidence") or "?", m["as_of"])
    if m["n"] < MIN_LISTINGS:
        return False, "thin market: only %d live listing(s) — %s" % (m["n"], span)
    if catalog_resale is None:
        return True, span
    if m["low"] <= catalog_resale <= m["high"]:
        return True, "catalog $%d in range %s" % (catalog_resale, span)
    side = "ABOVE" if catalog_resale > m["high"] else "BELOW"
    return False, "catalog $%d is %s the live range %s" % (catalog_resale, side, span)


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
