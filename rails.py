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
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
PK_DATA = Path.home() / "Documents/openclaw/CYPHER/sneaker_market_agent/data"
FRESHNESS_DAYS = 7

# ── the rails, by STABLE NAME ────────────────────────────────────────────────
# ★ Named, never numbered (ruled 2026-09-16). "Rail 7" was never a real name: it
# came from a session report counting seven checks, and it pointed at the FIFTH
# of them. research/moments.py used "Rail 4" under a different scheme entirely.
# Ordinals drift the moment a check is added and there is no way to notice.
# A name maps to a SOUL clause and survives reordering.
#
#   name                     SOUL clause
#   ──────────────────────── ─────────────────────────────────────────────────
#   NO_GAMBLING              HARD RULES — never use gambling language
#   NO_INVESTMENT_FRAMING    HARD RULES — never imply investments
#   NO_CARD_VALUE_CLAIM      HARD RULES — never imply real-world monetary value
#   NO_COMPETITOR_NAMED      HARD RULES — never trash competitors by name
#   OBTAINABLE               HARD RULES — never show a card as obtainable when
#                            it is not (pull vs earn)
#   SET_ROUTE_STATED         same rule, route clause — "complete the set" is the
#                            claim
#   NO_PULL_IMPLICATION      same rule, route clause — "pull this" is forbidden
#   VALUE_FIGURE_ATTRIBUTED  HARD RULES — monetary value, via the card face
#   NO_UNVERIFIED_PRICE      OPERATING NOTES — PK data, <=7 days, real sneaker


class Rail(NamedTuple):
    name: str          # stable, maps to SOUL. Never an ordinal.
    label: str         # human text. Fed to the writer as retry feedback.
    passed: bool
    note: str          # remediation, shown only on failure


# ── OBTAINABILITY (the rail formerly miscalled "Rail 7") ─────────────────────
# ★ AMENDED 2026-09-16. Two routes, and the card must prove one of them:
#   PULLABLE  — the (image_name, rarity) pair is pool-reachable.
#   EARNABLE  — the pair is a live set_rewards reward AND every card its set
#               requires is itself pool-reachable. Both halves, every time.
#
# ★★ AND IT NOW ACTUALLY RUNS. Until this change both call sites passed the
# literal `pool_reachable=True`, so the check could not fail. Reachability was
# real, but guaranteed UPSTREAM by candidates() and by drop_correspondent's SQL
# join — the rail itself was inert, which is the shape banked on 2026-09-10 and
# again in d6e900d. An inert rail is worse than no rail because it is trusted.
#
# rails.py does NOT grow DB access. The verdict is read from a cache that
# daily_digest regenerates at the start of every run; a cache older than
# FRESHNESS_DAYS FAILS CLOSED and says so in its reason.
SET_ROUTES = HERE / "state" / "_set_routes.json"

# Positive filter, same shape as moments.PROPOSABLE_SENSITIVITIES: a post on the
# EARN route must say so. Membership, never the absence of a blocklist hit.
ROUTE_MARKERS = ("complete the set", "completing the set", "complete this set",
                 "completes the set", "finish the set", "finishing the set",
                 "set reward", "complete the", "completing all")
# ...and must not let the reward read as a pack outcome.
PULL_MARKERS = ("pull it", "pull this", "pull one", "pull the", "pulled it",
                "in packs", "in a pack", "from a pack", "open a pack",
                "pack odds", "rip a pack")


def _pair(image_name: str | None, rarity: str | None) -> str:
    return "%s|%s" % (image_name or "", rarity or "")


def load_set_routes() -> tuple[dict | None, str]:
    """The obtainability cache, or None plus the reason it cannot be trusted.

    FAIL CLOSED on every failure mode — missing, malformed, undated, stale. A
    card cannot be shown as obtainable on the strength of a file we cannot
    vouch for, and the reason is returned so the digest can SAY why rather than
    simply producing nothing (ruled 2026-09-16)."""
    if not SET_ROUTES.exists():
        return None, "obtainability cache missing (%s) — run the digest to build it" % SET_ROUTES.name
    try:
        blob = json.loads(SET_ROUTES.read_text(encoding="utf-8"))
    except Exception as e:
        return None, "obtainability cache unreadable: %s" % type(e).__name__
    try:
        gen = datetime.fromisoformat(blob["generated_at"])
    except Exception:
        return None, "obtainability cache carries no usable generated_at"
    age = datetime.now(timezone.utc) - gen
    if age > timedelta(days=FRESHNESS_DAYS):
        return None, ("obtainability cache is %d days old (max %d) — pools may have "
                      "drifted; refusing to vouch for it" % (age.days, FRESHNESS_DAYS))
    return blob, "cache %s (%dd old)" % (gen.strftime("%Y-%m-%d"), age.days)


def obtainability(image_name: str | None, rarity: str | None,
                  routes: dict | None = None) -> tuple[bool, str, str]:
    """(ok, route, why) where route is 'pull', 'earn' or ''.

    The set path is PROVEN, never assumed. Note the empty-requirements guard:
    all([]) is True, so a set carrying zero requirement rows would otherwise
    qualify silently — the exact vacuous-truth trap this rail exists to avoid."""
    if not image_name or not rarity:
        return False, "", "no (image_name, rarity) supplied — cannot prove obtainability"
    if routes is None:
        routes, why = load_set_routes()
        if routes is None:
            return False, "", why
    key = _pair(image_name, rarity)
    if key in set(routes.get("reachable_pairs") or ()):
        return True, "pull", "pool-reachable"
    r = (routes.get("routes") or {}).get(key)
    if r is None:
        return False, "", "neither pool-reachable nor a live set reward"
    reqs = r.get("requirements") or []
    if not reqs:
        return False, "", ("set %r carries zero requirement rows — refusing "
                           "(an empty requirement list must never qualify)" % r.get("set_name"))
    missing = [q.get("image_name") for q in reqs if not q.get("reachable")]
    if missing:
        return False, "", ("set %r: %d of %d requirement cards are not pool-reachable (%s)"
                           % (r.get("set_name"), len(missing), len(reqs), ", ".join(missing[:3])))
    return True, "earn", ("set %r: all %d requirement cards pool-reachable"
                          % (r.get("set_name"), len(reqs)))

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


def check_draft(text: str, *, card_shows_value: bool, price_verified: bool,
                image_name: str | None = None, rarity: str | None = None,
                routes: dict | None = None) -> list[Rail]:
    """The machine-checkable subset of SOUL. Returns named Rails, never ordinals.

    ★ image_name + rarity REPLACE the old `pool_reachable` boolean. A caller can
    no longer assert obtainability — it is derived here, from the pair, so there
    is no argument a call site can get wrong. That is the whole point: the
    literal `pool_reachable=True` at both call sites made this rail inert.
    """
    low = text.lower()
    has_attr = any(m in low for m in ATTRIBUTION_MARKERS)
    ok_obtain, route, why_obtain = obtainability(image_name, rarity, routes)
    checks = [
        Rail("NO_GAMBLING", "no gambling language",
             not any(w in low for w in GAMBLING), ""),
        Rail("NO_INVESTMENT_FRAMING", "no investment framing",
             not any(w in low for w in INVESTMENT), ""),
        Rail("NO_CARD_VALUE_CLAIM", "no card-value claim",
             not any(w in low for w in CARD_VALUE_CLAIMS), ""),
        Rail("NO_COMPETITOR_NAMED", "no competitor named",
             not any(w in low for w in COMPETITORS), ""),
        Rail("OBTAINABLE",
             "card is obtainable (pool-reachable, or set-earnable with every "
             "requirement reachable)", ok_obtain, why_obtain),
        Rail("VALUE_FIGURE_ATTRIBUTED",
             "card image w/ value figure carries real-sneaker attribution",
             (not card_shows_value) or has_attr,
             "card renders EST. VALUE; text must scope it to the real pair"),
        Rail("NO_UNVERIFIED_PRICE", "no unverified price asserted in agent voice",
             price_verified or not re.search(r"(trades?|sells?|going|worth|sits?)\s+(for\s+|at\s+|around\s+)?\$", low),
             "PK freshness unverified -> omit the number from our own voice"),
    ]
    # ── the EARN route carries two obligations the PULL route does not ───────
    # They attach ONLY on the set path. A pool-reachable card is not required to
    # talk about sets, and a post that never claims the earn route is not asked
    # to prove it. This is a widening of OBTAINABLE, not a bypass around it.
    if ok_obtain and route == "earn":
        checks.append(Rail(
            "SET_ROUTE_STATED", "set-route post states the route explicitly",
            any(m in low for m in ROUTE_MARKERS),
            "the route IS the claim — say 'complete the set', not 'it's in CYPHER'"))
        checks.append(Rail(
            "NO_PULL_IMPLICATION", "set-route post does not imply a pack pull",
            not any(m in low for m in PULL_MARKERS),
            "a set reward cannot be pulled; phrasing that implies a pack is false"))
    return checks


def report(checks) -> bool:
    ok = True
    for c in checks:
        ok &= c.passed
        print("  %-4s %-22s %s%s" % ("PASS" if c.passed else "FAIL", c.name, c.label,
                                     ("  — " + c.note) if (c.note and not c.passed) else ""))
    return ok
