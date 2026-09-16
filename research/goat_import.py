#!/usr/bin/env python3.12
"""
goat_import.py — RELEASE DATES + raw GOAT snapshots for the reachable catalogue.

WHAT THIS PRODUCES
  data/release_dates.json          one entry per reachable shoe: an exact
                                   release date, or an explicit null with the
                                   reason it could not be established.
  data/goat_snapshots/<img>.json   raw whitelisted capture, NO interpretation.

WHAT THIS DELIBERATELY DOES NOT DO
  No scoring, no hook extraction, no "interesting fact" selection. That is the
  dossier builder's job in a later batch. This module captures and matches; it
  never decides what any of it means.

★ WHY THE MATCH RULE IS STRICTER THAN THE PIPELINE'S
  ~/Documents/openclaw/cipher/sneaker_pipeline/kicksdb_scraper.py:355-362 uses
  `best = hits[0]`, then upgrades to an exact-SKU hit if one happens to exist.
  That is a first-hit fallback, and this module deliberately does NOT do it —
  do not "harmonize" the two.
      A wrong date is worse than no date. A fabricated "N years ago today"
      passes every rail we have: it is well-formed, it is specific, it reads as
      researched, and nothing downstream can catch it. A null is visible and
      costs us one post. A wrong date is invisible and costs us credibility.
  Every date this module emits satisfies exact normalized-SKU equality AND
  release_year == the catalogue's year. Nothing weaker is ever written.

DATA SOURCE
  GOAT's public Algolia index. Unauthenticated, free, no rate limit published.
  App id / search key / index / request-body shape copied verbatim from
  kicksdb_scraper.py:325-342 (retrieved 2026-09-09). Copied rather than
  imported on purpose: that module carries cwd assumptions and import-time side
  effects, and this one must stay runnable from anywhere.
"""

from __future__ import annotations

import argparse
import html.parser
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATES_PATH = HERE / "data" / "release_dates.json"
SNAP_DIR = HERE / "data" / "goat_snapshots"
LEDGER = HERE / "ledger" / "research.jsonl"

# ── GOAT Algolia (copied from kicksdb_scraper.py:325-342, 2026-09-09) ────────
ALGOLIA_APP_ID = "2FWOTDVM2O"
ALGOLIA_API_KEY = "ac96de6fef0e02bb95d433d8d5c7038a"          # public search key
ALGOLIA_INDEX = "product_variants_v2"
ALGOLIA_URL = ("https://%s-dsn.algolia.net/1/indexes/%s/query"
               % (ALGOLIA_APP_ID, ALGOLIA_INDEX))

USER_AGENT = "cyphermarketer/1.0 research"
TIMEOUT = 30
SLEEP_BETWEEN = 0.3
HITS_PER_PAGE = 20          # a real SKU returns only its own size rows; 20 is
                            # margin against fuzzy hits crowding page one, which
                            # is exactly what a junk query ("N/A") produces.

# Snapshot whitelist. CAPTURE ONLY — no price ladders, no variant arrays, no
# image URLs. Widening this list is a ruling, not a convenience.
SNAPSHOT_FIELDS = ("name", "nickname", "designer", "story_html", "details",
                   "keywords", "silhouette", "collection_slugs", "season",
                   "release_date", "release_year", "sku", "retail_price_cents")

# style codes that are present but carry no information
_NULL_SKUS = {"", "N/A", "NA", "-", "?", "TBD", "UNKNOWN", "NONE", "NULL"}

REASON_NO_STYLE_CODE = "no_style_code"
REASON_NO_HIT = "no_hit"
REASON_YEAR_MISMATCH = "year_mismatch"
REASON_AMBIGUOUS = "ambiguous"
REASON_BAD_DATE = "bad_date_format"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ledger(rec: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec)
    rec.setdefault("ts", now())
    with LEDGER.open("a", encoding="utf-8") as fh:          # append-only
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── normalisation ───────────────────────────────────────────────────────────
def norm_sku(s) -> str:
    """Uppercase, strip spaces and dashes.

    NOT cosmetic. GOAT stores SKUs space-separated ('304292 051') where the
    catalogue stores them dash-separated ('304292-051'). Without this, exact
    matching fails on every single shoe and the whole file comes back null.
    """
    return re.sub(r"[\s\-]", "", str(s or "")).upper()


def is_usable_sku(s) -> bool:
    return norm_sku(s) != "" and str(s or "").strip().upper() not in _NULL_SKUS


class _Stripper(html.parser.HTMLParser):
    """story_html -> plain text. stdlib only; no bs4, no network."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._out = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self._out.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self._out)).strip()


def strip_html(raw) -> str:
    if not raw:
        return ""
    p = _Stripper()
    try:
        p.feed(str(raw))
        p.close()
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(raw))).strip()
    return p.text()


# ── transport ───────────────────────────────────────────────────────────────
def query_goat(sku: str) -> list[dict] | None:
    """Return hits, or None on a transport failure (caller skips that shoe).

    One retry on 5xx. A bare failure never aborts the run — a single flaky
    lookup must not cost the other 331.
    """
    body = json.dumps({"params": "query=%s&hitsPerPage=%d"
                       % (str(sku).replace("-", " "), HITS_PER_PAGE)}).encode()
    for attempt in (1, 2):
        req = urllib.request.Request(
            ALGOLIA_URL, data=body,
            headers={"x-algolia-application-id": ALGOLIA_APP_ID,
                     "x-algolia-api-key": ALGOLIA_API_KEY,
                     "Content-Type": "application/json",
                     "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r).get("hits", [])
        except urllib.error.HTTPError as e:
            if 500 <= e.code < 600 and attempt == 1:
                time.sleep(1.0)
                continue
            return None
        except Exception:
            if attempt == 1:
                time.sleep(1.0)
                continue
            return None
    return None


# ── the match rule ──────────────────────────────────────────────────────────
def take_date(raw) -> str | None:
    """First 10 characters, VERBATIM. Never parsed, never timezone-converted.

    GOAT's values are 'YYYY-MM-DDT23:59:59.999Z'. Parsing to a datetime and
    rendering in local time is safe only by coincidence in US zones (UTC minus
    something keeps 23:59 on the same date) and silently shifts the date forward
    a day anywhere east of Greenwich — a CI runner or a trip is enough. The
    failure is invisible and would corrupt every anniversary at once, so the
    string is sliced and never interpreted.
    """
    s = str(raw or "")
    if len(s) < 10:
        return None
    head = s[:10]
    return head if re.fullmatch(r"\d{4}-\d{2}-\d{2}", head) else None


def match_hit(hits: list[dict], sku: str, year, colorway: str) -> tuple[dict | None, str | None, int, int]:
    """-> (winning hit | None, reason | None, pre_collapse, post_collapse).

    Never falls back to hits[0]. Never relaxes to year-only matching.
    """
    want_sku, want_year = norm_sku(sku), str(year)
    sku_ok = [h for h in hits if norm_sku(h.get("sku")) == want_sku]
    if not sku_ok:
        return None, REASON_NO_HIT, 0, 0
    survivors = [h for h in sku_ok if str(h.get("release_year") or "") == want_year]
    if not survivors:
        return None, REASON_YEAR_MISMATCH, len(sku_ok), 0

    # ── COLLAPSE BEFORE THE AMBIGUITY TEST ──────────────────────────────────
    # product_variants_v2 is a PER-SIZE-VARIANT index: one product yields one
    # hit per size, so a normal match returns 33-121 identical survivors
    # (measured 2026-09-09). Treating that as ambiguity rejects 100% of shoes
    # and produces an empty file. Only DISTINCT (sku, date, name) triples are
    # real disagreement. Do not "simplify" this away — the duplication is the
    # index's shape, not noise.
    collapsed: dict[tuple, dict] = {}
    for h in survivors:
        collapsed.setdefault(
            (norm_sku(h.get("sku")), take_date(h.get("release_date")),
             str(h.get("name") or "")), h)
    groups = list(collapsed.values())
    pre, post = len(survivors), len(groups)

    if post == 1:
        return groups[0], None, pre, post

    # Genuinely conflicting dates behind one SKU. Untested against live data as
    # of 2026-09-09 — no probe reached this branch.
    token = (colorway or "").strip().lower()
    if token:
        narrowed = [h for h in groups if token in str(h.get("name") or "").lower()]
        if len(narrowed) == 1:
            return narrowed[0], None, pre, post
    return None, REASON_AMBIGUOUS, pre, post


def snapshot(hit: dict, sku: str, matched: bool, reason: str | None) -> dict:
    out = {}
    for f in SNAPSHOT_FIELDS:
        v = hit.get(f)
        out[f] = strip_html(v) if f == "story_html" else v
    out["_meta"] = {"fetched_at": now(), "matched": matched, "match_reason": reason,
                    "query": "%s?query=%s&hitsPerPage=%d"
                             % (ALGOLIA_URL, str(sku).replace("-", " "), HITS_PER_PAGE)}
    return out


# ── per-shoe driver ─────────────────────────────────────────────────────────
def lookup(shoe: dict, dry_run: bool = False) -> dict:
    img = shoe["image_name"]
    sku, year = shoe.get("style_code"), shoe.get("year")
    base = {"style_code": sku, "year": year, "release_date": None,
            "source": "goat:%s" % ALGOLIA_INDEX, "fetched_at": now(),
            "confidence": None, "reason": None}
    rec = {"event": "goat_lookup", "image_name": img, "matched": False,
           "reason": None, "hits": 0, "pre_collapse": 0, "post_collapse": 0}

    if not is_usable_sku(sku):
        # Never spend a request on a shoe we have no input for. "we lacked the
        # input" and "GOAT lacked the shoe" are different diagnoses.
        base["reason"] = rec["reason"] = REASON_NO_STYLE_CODE
        if not dry_run:
            ledger(rec)
        return {"entry": base, "hit": None, "hits": 0, "rec": rec}

    hits = query_goat(sku)
    if hits is None:
        base["reason"] = rec["reason"] = "fetch_failed"
        if not dry_run:
            ledger(rec)
        return {"entry": base, "hit": None, "hits": 0, "rec": rec}

    hit, reason, pre, post = match_hit(hits, sku, year, shoe.get("colorway") or "")
    rec.update(hits=len(hits), pre_collapse=pre, post_collapse=post)
    if hit is None:
        base["reason"] = rec["reason"] = reason
    else:
        d = take_date(hit.get("release_date"))
        if d is None:
            base["reason"] = rec["reason"] = REASON_BAD_DATE
            hit = None
        else:
            base.update(release_date=d, confidence="exact")
            rec["matched"] = True
    if not dry_run:
        ledger(rec)
    return {"entry": base, "hit": hit, "hits": len(hits), "rec": rec}


# ── catalogue access (read-only) ────────────────────────────────────────────
def reachable_shoes() -> list[dict]:
    """Every shoe the agent may post about — BOTH routes (widened 2026-09-16).

    ★ This is the OBTAINABLE set, not the pool-reachable set. A shoe qualifies by
    the PULL route (its (image_name, rarity) pair is pool-reachable) or by the
    EARN route (it is a live set_rewards reward AND every card its set requires
    is itself pool-reachable). Same definition as rails.obtainability; if these
    two ever disagree, the rail is right and this is the bug.

    It had to widen because the earn route unlocked three cards that had no
    dossiers — they were unreachable when the import last ran — so the three
    best cards in the catalog would have fallen back to a category scene, which
    is the exact failure E2 exists to fix.

    ★★ EARN MEANS EARN, NOT TOP TIER. The other 63 unobtainable GRAIL/HOLY GRAIL
    cards are NOT admitted by this and must never be: they are not set rewards.
    Note the `exists (...)` clause — a set carrying ZERO requirement rows is
    excluded, because `not exists (unreachable requirement)` is vacuously true
    over an empty set and would otherwise let an empty set through. Same
    vacuous-truth guard as rails.obtainability, expressed in SQL."""
    sys.path.insert(0, str(HERE))
    import daily_digest as DD
    return DD._sql(DD.REACHABLE_CTE + """,
      earnable as (
        select sr.reward_image_name as image_name, sr.reward_rarity as rarity
        from public.set_rewards sr
        where exists (select 1 from public.set_requirements q
                      where q.set_name = sr.set_name)
          and not exists (
            select 1 from public.set_requirements q
            where q.set_name = sr.set_name
              and not exists (select 1 from reachable r
                              where r.image_name = q.required_image_name))
      ),
      obtainable as (
        select image_name, rarity from reachable
        union select image_name, rarity from earnable
      )
      select distinct c.image_name, c.style_code, c.year, c.name, c.brand, c.colorway
      from public.catalog_cards c
      join obtainable o on o.image_name=c.image_name and o.rarity=c.rarity
      order by c.image_name;""")


def run(limit=None, dry_run=False, image_name=None) -> dict:
    shoes = reachable_shoes()
    allowed = {s["image_name"] for s in shoes}
    if image_name:
        shoes = [s for s in shoes if s["image_name"] == image_name]
        if not shoes:
            raise SystemExit("not in the reachable set: %s" % image_name)
    if limit:
        shoes = shoes[:limit]

    # idempotent: load, overwrite in place, never append duplicates
    dates = {}
    if DATES_PATH.exists():
        try:
            dates = json.loads(DATES_PATH.read_text(encoding="utf-8"))
        except Exception:
            dates = {}

    rows, counts = [], {}
    for i, s in enumerate(shoes):
        r = lookup(s, dry_run=dry_run)
        e = r["entry"]
        k = e["reason"] or "matched"
        counts[k] = counts.get(k, 0) + 1
        rows.append({"image_name": s["image_name"], "style_code": s.get("style_code"),
                     "year": s.get("year"), "hits": r["hits"],
                     "matched": e["confidence"] == "exact",
                     "date": e["release_date"], "reason": e["reason"]})
        if not dry_run:
            dates[s["image_name"]] = e
            if r["hit"] is not None:
                SNAP_DIR.mkdir(parents=True, exist_ok=True)
                (SNAP_DIR / ("%s.json" % s["image_name"])).write_text(
                    json.dumps(snapshot(r["hit"], s.get("style_code"), True, None),
                               indent=1, ensure_ascii=False), encoding="utf-8")
        if is_usable_sku(s.get("style_code")) and i < len(shoes) - 1:
            time.sleep(SLEEP_BETWEEN)

    if not dry_run:
        # every key must be a reachable shoe — assert before writing
        stray = sorted(set(dates) - allowed)
        if stray:
            raise SystemExit("REFUSING TO WRITE: %d keys outside the reachable "
                             "set: %s" % (len(stray), stray[:5]))
        DATES_PATH.parent.mkdir(parents=True, exist_ok=True)
        DATES_PATH.write_text(json.dumps(dates, indent=1, ensure_ascii=False,
                                         sort_keys=True), encoding="utf-8")
    return {"rows": rows, "counts": counts, "total": len(shoes)}


def main() -> None:
    ap = argparse.ArgumentParser(description="GOAT release dates + snapshots")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--image-name", default=None)
    a = ap.parse_args()
    res = run(limit=a.limit, dry_run=a.dry_run, image_name=a.image_name)
    print("%-52s %-14s %-5s %-5s %-6s %-11s %s"
          % ("image_name", "style_code", "year", "hits", "match", "date", "reason"))
    for r in res["rows"]:
        print("%-52s %-14s %-5s %-5s %-6s %-11s %s"
              % (r["image_name"][:52], str(r["style_code"])[:14], r["year"], r["hits"],
                 "YES" if r["matched"] else "no", r["date"] or "-", r["reason"] or ""))
    print("\ncounts:", json.dumps(res["counts"], sort_keys=True), "of", res["total"])
    if a.dry_run:
        print("DRY RUN — nothing written")


if __name__ == "__main__":
    main()
