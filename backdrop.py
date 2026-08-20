#!/usr/bin/env python3.12
"""
backdrop.py — AI-generated SCENE BACKDROPS for cyphermarketer visuals.

WHAT THIS DOES AND DOES NOT GENERATE
  Generates: an empty environment (arena, skate park, street, studio…) chosen
             from the shoe's own era / category / culture.
  NEVER generates: the card, the sneaker, or any part of either. The card is a
             pixel-true render from card_render.py and is only ever COMPOSITED
             on top (compose.py). SOUL.md forbids fake or imagined cards; this
             module exists precisely so the visual can be rich without the
             product ever being synthesized.

RAILS (ratified 2026-08-19)
  * Every prompt carries the NEGATIVE_CONSTRAINTS block structurally — it is
    concatenated in build_prompt(), not left to the caller to remember.
  * There is NO automated logo/face/text detector, and this module does not
    pretend to have one. Each backdrop is inspected by Claude before it can
    reach Telegram; the verdict is recorded in the ledger via record_verdict().
    Anything ambiguous is flagged in the proposal note rather than silently used.
  * Every generation is ledgered with prompt, model, aspect, cost.

MODEL: grok-imagine-image-2.0 @ $0.04/image (ratified). Flat per-image pricing.
"""
from __future__ import annotations
import argparse, json, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import x_client as X  # noqa: E402
import card_render as CR  # noqa: E402

ENDPOINT = "https://api.x.ai/v1/images/generations"
MODEL = "grok-imagine-image-2.0"
COST_PER_IMAGE = 0.04
# API-supported aspect ratios (422s on anything else — 4:5 is NOT supported, so the
# feed-optimal 4:5 is produced by generating 3:4 and cropping height in compose.py):
SUPPORTED_ASPECTS = ("1:1","3:4","4:3","9:16","16:9","2:3","3:2","1:2","2:1","auto")
LEDGER = HERE / "ledger" / "backdrops.jsonl"

# Structural. Appended to EVERY prompt — the single most important rail here.
NEGATIVE_CONSTRAINTS = (
    "ABSOLUTE CONSTRAINTS: no text of any kind, no lettering, no words, no numbers, "
    "no captions, no signage, no banners, no scoreboards with characters, no jersey "
    "numbers; no logos, no brand marks, no trademarks, no swooshes, no team or league "
    "insignia, no sponsor boards; no people, no faces, no human figures, no silhouettes "
    "of people in focus, no hands, no mannequins; no watermarks. Distant out-of-focus "
    "light bokeh is fine but must never resolve into faces or readable marks. "
    "Empty scene only — leave the central area uncluttered and unobstructed."
)

BRAND_LOOK = (
    "CYPHER brand aesthetic: deep near-black base, cyan and violet accent lighting, "
    "cinematic volumetric haze, glossy reflective floor, subtle film grain, "
    "high production value, moody, premium."
)

# scene stems keyed by catalog category, refined by tags/silhouette
SCENES = {
    "Skateboarding": "a gritty empty concrete skate park at dusk under harsh floodlights, "
                     "worn ledges and rails, cracked asphalt, chain-link fencing, urban decay",
    "Basketball":    "an empty retro indoor basketball arena at night, polished hardwood floor "
                     "with mirror-like reflections, tiered empty seating fading into darkness, "
                     "dramatic overhead spotlights, drifting haze",
    "Retro":         "an empty retro indoor basketball arena at night, polished hardwood floor "
                     "with mirror-like reflections, tiered empty seating fading into darkness, "
                     "dramatic overhead spotlights, drifting haze",
    "Running":       "an empty outdoor running track at blue hour, wet rubberized lanes with "
                     "reflections, stadium lights flaring, mist low to the ground",
    "Lifestyle":     "an empty rain-slicked city street at night, neon shop glow reflecting in "
                     "puddles, steam rising from grates, deep shadows, cinematic wide angle",
    "Training":      "an empty industrial training facility at night, polished concrete floor, "
                     "shafts of light through high windows, haze",
}
DEFAULT_SCENE = SCENES["Lifestyle"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ledger(rec: dict):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec); rec.setdefault("ts", now())
    with LEDGER.open("a", encoding="utf-8") as fh:      # append-only
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def scene_for(row: dict) -> str:
    """Derive the scene from the shoe's own story — category first, then era/tags."""
    cat = (row.get("category") or "").strip()
    base = SCENES.get(cat, DEFAULT_SCENE)
    year = row.get("year")
    era = ""
    if isinstance(year, int):
        if year < 2000:
            era = " Late-90s period feel, warm tungsten light, slight haze."
        elif year < 2010:
            era = " Mid-2000s period feel, cooler fluorescent tones."
    return base + era


def build_prompt(row: dict) -> str:
    return "%s. %s %s" % (scene_for(row), BRAND_LOOK, NEGATIVE_CONSTRAINTS)


def generate(prompt: str, aspect: str, out: Path, env: dict) -> dict:
    if aspect not in SUPPORTED_ASPECTS:
        X.die("aspect %r unsupported by the API; use one of %s" % (aspect, ", ".join(SUPPORTED_ASPECTS)))
    body = {"model": MODEL, "prompt": prompt, "n": 1,
            "aspect_ratio": aspect, "response_format": "b64_json"}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer %s" % env["XAI_API_KEY"],
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            status, raw = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read().decode()
    except Exception as e:
        status, raw = 0, json.dumps({"transport_error": type(e).__name__})
    if status != 200:
        ledger({"event": "generation_failed", "model": MODEL, "aspect": aspect,
                "http": status, "error": raw[:300], "cost_usd": 0.0})
        X.die("xAI generation failed (HTTP %s): %s" % (status, raw[:300]))
    j = json.loads(raw)
    item = j["data"][0]
    # The charge is incurred HERE, at a 200 — so record it HERE. Writing the
    # ledger after the download meant a failed download lost the spend record
    # entirely (observed: a 403 on the image URL burned $0.04 unrecorded).
    ledger({"event": "generated", "model": MODEL, "aspect": aspect,
            "cost_usd": COST_PER_IMAGE, "output": str(out), "prompt": prompt,
            "revised_prompt": item.get("revised_prompt"), "inspection": "PENDING"})
    if item.get("url"):
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(item["url"], timeout=300) as r:
                out.write_bytes(r.read())
        except Exception as ex:
            ledger({"event": "download_failed", "output": str(out),
                    "error": type(ex).__name__, "note": "spend already ledgered above"})
            X.die("image generated (charged) but download failed: %s" % type(ex).__name__)
    elif item.get("b64_json"):
        import base64
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(item["b64_json"]))
    else:
        X.die("no image payload in response: %s" % str(item)[:200])
    return {"event": "generated", "model": MODEL, "aspect": aspect,
            "cost_usd": COST_PER_IMAGE, "output": str(out), "prompt": prompt,
            "inspection": "PENDING"}


def record_verdict(output: str, verdict: str, detail: str = ""):
    """Claude's visual inspection result. No auto-detector exists by design."""
    ledger({"event": "inspection", "output": output, "verdict": verdict,
            "detail": detail, "inspector": "claude"})


def spend_summary() -> dict:
    total, n, discarded = 0.0, 0, 0
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("event") == "generated":
                total += float(r.get("cost_usd") or 0); n += 1
            if r.get("event") == "inspection" and r.get("verdict") == "DISCARD":
                discarded += 1
    return {"images": n, "spend_usd": round(total, 4), "discarded": discarded,
            "discard_rate": round(discarded / n, 3) if n else 0.0}


def main():
    ap = argparse.ArgumentParser(description="Generate a scene backdrop (never the card)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen")
    g.add_argument("--image-name", required=True); g.add_argument("--rarity", required=True)
    g.add_argument("--aspect", default="3:4", help="API-supported ratio; 3:4 crops to 4:5")
    g.add_argument("--out", required=True)
    v = sub.add_parser("verdict")
    v.add_argument("--output", required=True); v.add_argument("--verdict", required=True)
    v.add_argument("--detail", default="")
    sub.add_parser("spend")
    a = ap.parse_args()
    if a.cmd == "spend":
        print("  " + json.dumps(spend_summary())); return
    if a.cmd == "verdict":
        record_verdict(a.output, a.verdict, a.detail); print("  verdict recorded"); return
    env = X.load_env(Path(X.DEFAULT_ENV))
    if not env.get("XAI_API_KEY"):
        X.die("env missing key: XAI_API_KEY")           # name only
    row = CR.fetch_card(a.image_name, a.rarity)
    prompt = build_prompt(row)
    print("  category : %s (%s)" % (row.get("category"), row.get("year")))
    print("  aspect   : %s   model: %s   cost: $%.2f" % (a.aspect, MODEL, COST_PER_IMAGE))
    rec = generate(prompt, a.aspect, Path(a.out), env)
    print("  output   : %s" % rec["output"])
    print("  INSPECTION PENDING — must be visually cleared before use.")


if __name__ == "__main__":
    main()
