#!/usr/bin/env python3.12
"""
price_audit.py — READ-ONLY eligibility scan + H1 re-pricing queue.

Runs the showcase catalog through the RANGE + LIQUIDITY metric (rails.py) and
emits two things:

  1. a pass/block breakdown by reason — the measure of whether the yardstick fix
     did what we think it did
  2. ledger/pk_repricing_queue.jsonl — cards still out of range under the NEW
     metric, in BOTH directions, with liquidity counts. FLAG ONLY: this file is
     for PRICEKEEPER's operator-review loop to consume. Nothing here mutates a
     price, and it deliberately writes into cyphermarketer's own ledger rather
     than PK's tree — we produce, PK consumes.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rails, daily_digest as DD  # noqa: E402

QUEUE = HERE / "ledger" / "pk_repricing_queue.jsonl"


def scan(limit: int = 30) -> dict:
    rows = DD._sql(DD.REACHABLE_CTE + """
      select c.image_name, c.rarity::text as rarity, c.name, c.colorway,
             c.style_code, c.year, c.retail_price, c.estimated_resale
      from public.catalog_cards c
      join reachable r on r.image_name=c.image_name and r.rarity=c.rarity
      where c.is_set_reward=false and c.style_code <> 'N/A'
      order by c.estimated_resale desc limit %d;""" % (limit * 2))
    seen, out = set(), []
    for r in rows:
        if r["image_name"] in seen:
            continue
        seen.add(r["image_name"])
        out.append(r)
        if len(out) >= limit:
            break

    res = {"pass": [], "thin": [], "above": [], "below": [], "nodata": []}
    for r in out:
        ok, why = rails.price_claim_allowed(r["style_code"], r["estimated_resale"])
        m, _ = rails.pk_market(r["style_code"])
        rec = {**r, "why": why, "market": m}
        if ok:
            res["pass"].append(rec)
        elif "thin market" in why:
            res["thin"].append(rec)
        elif "ABOVE" in why:
            res["above"].append(rec)
        elif "BELOW" in why:
            res["below"].append(rec)
        else:
            res["nodata"].append(rec)
    return res


def write_queue(res: dict) -> int:
    """H1 tail: out-of-range in EITHER direction. Flag, never fix."""
    ts = datetime.now(timezone.utc).isoformat()
    rows = []
    for direction in ("above", "below"):
        for r in res[direction]:
            m = r["market"] or {}
            rows.append({
                "ts": ts, "source": "cyphermarketer.price_audit",
                "action": "REVIEW_ONLY — no price was changed",
                "sku": r["style_code"], "image_name": r["image_name"],
                "rarity": r["rarity"], "name": r["name"], "colorway": r["colorway"],
                "catalog_estimated_resale": r["estimated_resale"],
                "direction": direction,
                "pk_low": m.get("low"), "pk_median": m.get("median"),
                "pk_high": m.get("high"), "pk_listings": m.get("n"),
                "pk_as_of": m.get("as_of"), "detail": r["why"],
            })
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE.open("a", encoding="utf-8") as fh:      # append-only
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    return len(rows)


def main():
    res = scan(30)
    total = sum(len(v) for v in res.values())
    print("  ELIGIBILITY SCAN — %d showcase cards, RANGE + LIQUIDITY metric\n" % total)
    print("    PASS (catalog inside live range)   : %d" % len(res["pass"]))
    print("    BLOCK thin market (<%d listings)   : %d" % (rails.MIN_LISTINGS, len(res["thin"])))
    print("    BLOCK catalog ABOVE range          : %d" % len(res["above"]))
    print("    BLOCK catalog BELOW range          : %d" % len(res["below"]))
    print("    BLOCK no PK data in window         : %d" % len(res["nodata"]))
    for label in ("above", "below"):
        if not res[label]:
            continue
        print("\n  H1 TAIL — catalog %s live range:" % label.upper())
        for r in res[label]:
            m = r["market"] or {}
            print("    %-38s $%-6s vs $%s-$%s (n=%s)" % (
                r["image_name"][:38], r["estimated_resale"],
                m.get("low"), m.get("high"), m.get("n")))
    n = write_queue(res)
    print("\n  wrote %d row(s) to %s" % (n, QUEUE.relative_to(HERE)))
    print("  (REVIEW_ONLY — PK's operator loop consumes this; no price was changed)")


if __name__ == "__main__":
    main()
