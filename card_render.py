#!/usr/bin/env python3.12
"""
card_render.py — TRUE CYPHER card renders for cyphermarketer.

Q2b, activated. Renders are produced by CPA's CypherCardRenderer — the SAME
binary that produces CPA's Telegram proposal cards — so the output is the real
SneakerCardView, not a reconstruction. Nothing here draws card chrome.

HARD RAIL (ruling Q2b): CPA's directory is INVOKE-ONLY.
  * never `swift build`, never write into cpa/CypherCardRenderer/**
  * output always goes to a cyphermarketer-owned path
  * assert_renderer_pristine() re-checks `git status` on that directory after
    every invocation and raises if a single byte changed. The rail is enforced
    at runtime, not just documented.

FIELD MAPPING — this is where the two reported defects actually lived. The
renderer displays `sneakerName` VERBATIM (SneakerCardView.swift:123,
`Text(sneakerName.uppercased())`) and renders `flavorText` only when non-empty
(:444). Passing the bare catalog `name` therefore drops the brand ("SB DUNK LOW"
instead of "NIKE SB DUNK LOW"), and passing an empty flavorText drops the
description entirely. Both are caller-side mapping bugs, not renderer defects.

`normalize_display_name` below is replicated faithfully from
cpa/sources/proposal_card_build.py so cyphermarketer and CPA compose the same
title from the same catalog row. Replicated rather than imported to avoid a
cross-repo runtime dependency; if CPA's version changes, re-sync this one.
"""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path.home() / "Documents/openclaw/CYPHER"
CPA_RENDERER_DIR = REPO / "cpa/CypherCardRenderer"
RENDERER_BIN = CPA_RENDERER_DIR / ".build/release/CypherCardRenderer"
ASSETS = REPO / "CYPHER/Assets.xcassets"


def die(msg: str):
    sys.stderr.write("FATAL [card_render]: %s\n" % msg)
    raise SystemExit(2)


# ── display-name normalization (replicated from CPA) ─────────────────────────
def _display_key(v: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", v.casefold()).strip()


def _contains_whole_display_phrase(value: str, phrase: str) -> bool:
    nv, np_ = _display_key(value), _display_key(phrase)
    if not nv or not np_:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(np_)}(?![a-z0-9])", nv) is not None


def _strip_leading_womens_indicator(v: str) -> str:
    return re.sub(r"^\s*(?:wmns|women(?:'|’)?s)\b[\s:,-]*", "", v, count=1,
                  flags=re.IGNORECASE).strip()


def _model_contains_brand_or_alias(model: str, brand: str) -> bool:
    aliases = {"Jordan": ["Jordan", "Air Jordan"]}.get(brand, [brand])
    return any(_contains_whole_display_phrase(model, a) for a in aliases)


def normalize_display_name(brand: str, raw_name: str) -> str:
    model = _strip_leading_womens_indicator(str(raw_name or "").strip())
    brand = str(brand or "").strip()
    if not brand or not model or _model_contains_brand_or_alias(model, brand):
        return model
    return f"{brand} {model}"


# ── catalog ──────────────────────────────────────────────────────────────────
def fetch_card(image_name: str, rarity: str) -> dict:
    """Authoritative row from the server catalog (equal to Swift since the backfill)."""
    sql = ("select image_name, rarity::text as rarity, name, brand, colorway, style_code, "
           "year, retail_price, estimated_resale, description, is_set_reward, "
           "category, silhouette, tags "
           "from public.catalog_cards where image_name=%s and rarity=%s;"
           % (_lit(image_name), _lit(rarity)))
    # File form only. The positional `-- <sql>` form hangs on this CLI version.
    # Per-call temp file, not state/_q.sql — scratch does not belong in state/
    # (see daily_digest._sql for why).
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".sql", encoding="utf-8", delete=False) as fh:
        fh.write(sql); f = Path(fh.name)
    try:
        p = subprocess.run(["supabase", "db", "query", "--linked", "-o", "json", "-f", str(f)],
                           capture_output=True, text=True, cwd=str(REPO), timeout=120)
    finally:
        f.unlink(missing_ok=True)
    try:
        rows = json.loads(re.search(r"\[.*\]", p.stdout, re.S).group(0))
    except Exception:
        die("catalog query failed for %s/%s: %s" % (image_name, rarity, p.stderr[:200]))
    if not rows:
        die("no catalog row for %s / %s" % (image_name, rarity))
    return rows[0]


def _lit(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def imageset_png(image_name: str) -> Path:
    d = ASSETS / f"{image_name}.imageset"
    if not d.is_dir():
        die("imageset not found: %s" % d.name)
    pngs = sorted(d.glob("*.png"))
    if not pngs:
        die("imageset has no PNG: %s" % d.name)
    # prefer the highest available scale
    for suffix in ("_3x.png", "@3x.png", "_2x.png", "@2x.png"):
        for p in pngs:
            if p.name.endswith(suffix):
                return p
    return pngs[-1]


# ── the invoke-only rail ─────────────────────────────────────────────────────
def assert_renderer_pristine():
    p = subprocess.run(["git", "status", "--porcelain", "CypherCardRenderer/"],
                       capture_output=True, text=True, cwd=str(CPA_RENDERER_DIR.parent))
    if p.stdout.strip():
        die("CPA renderer directory was MODIFIED — rail violated:\n%s" % p.stdout[:400])


def render_card(image_name: str, rarity: str, out: Path, serial: str = "",
                set_name: str = "") -> dict:
    if not RENDERER_BIN.exists():
        die("renderer binary missing at %s — do NOT build it here (rail); "
            "it belongs to CPA." % RENDERER_BIN)
    row = fetch_card(image_name, rarity)
    display = normalize_display_name(row.get("brand", ""), row.get("name", ""))
    card = {
        "sneakerName": display,                       # DEFECT (a) fix: brand + model
        "colorway": row.get("colorway") or "",
        "brand": row.get("brand") or "",
        "imageName": image_name,
        "imagePath": str(imageset_png(image_name)),
        "rarity": rarity,
        "badges": [],
        "condition": None,
        "serialNumber": serial,
        "setName": set_name,
        "retailPrice": ("$%s" % f"{int(row['retail_price']):,}") if row.get("retail_price") is not None else "N/A",
        "resalePrice": ("$%s" % f"{int(row['estimated_resale']):,}") if row.get("estimated_resale") is not None else "N/A",
        "year": str(row.get("year") or ""),
        "flavorText": row.get("description") or "",   # DEFECT (b) fix: real description
        "outputFilename": None,
    }
    tmp = HERE / "state" / "_card_input.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([str(RENDERER_BIN), "--input", str(tmp), "--output", str(out)],
                       capture_output=True, text=True)
    assert_renderer_pristine()                        # rail, checked every run
    if p.returncode != 0 or not out.exists():
        die("render failed: %s %s" % (p.stdout[-200:], p.stderr[-200:]))
    return {"card": card, "row": row, "output": str(out)}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Render a TRUE CYPHER card (CPA renderer, invoke-only)")
    ap.add_argument("--image-name", required=True)
    ap.add_argument("--rarity", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--serial", default="")
    a = ap.parse_args()
    r = render_card(a.image_name, a.rarity, Path(a.out), a.serial)
    c = r["card"]
    print("  title      : %s" % c["sneakerName"])
    print("  colorway   : %s" % c["colorway"])
    print("  description: %s%s" % (c["flavorText"][:70], "…" if len(c["flavorText"]) > 70 else ""))
    print("  stats      : %s / %s / %s" % (c["retailPrice"], c["resalePrice"], c["year"]))
    print("  output     : %s" % r["output"])
    print("  CPA dir    : pristine ✅")


if __name__ == "__main__":
    main()
