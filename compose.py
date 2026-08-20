#!/usr/bin/env python3.12
"""
compose.py — composite the TRUE card render over a generated backdrop.

INVARIANT: the card is never generated, restyled, recoloured or redrawn. It is
the pixel-true PNG from card_render.py (CPA's renderer), scaled with LANCZOS and
alpha-composited. Only the BACKDROP is synthetic, and it never contains the
product. This is what keeps "no fake/imagined cards" true while the visual still
looks designed.

Outputs 4:5 (X feed optimal) and 16:9. Note the API cannot generate 4:5 — it
422s on that ratio — so 4:5 is produced by cropping a generated 3:4.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from PIL import Image, ImageFilter

TARGETS = {"4:5": (1080, 1350), "16:9": (1600, 900)}
CARD_HEIGHT_FRACTION = {"4:5": 0.76, "16:9": 0.82}


def fit_backdrop(bd: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Cover-fit: scale to cover, then centre-crop. Never distorts."""
    tw, th = size
    s = max(tw / bd.width, th / bd.height)
    nb = bd.resize((max(1, round(bd.width * s)), max(1, round(bd.height * s))), Image.LANCZOS)
    left, top = (nb.width - tw) // 2, (nb.height - th) // 2
    return nb.crop((left, top, left + tw, top + th)).convert("RGBA")


def compose(card_path: Path, backdrop_path: Path, ratio: str, out: Path) -> dict:
    size = TARGETS[ratio]
    canvas = fit_backdrop(Image.open(backdrop_path), size)

    card = Image.open(card_path).convert("RGBA")
    target_h = int(size[1] * CARD_HEIGHT_FRACTION[ratio])
    scale = target_h / card.height
    card = card.resize((max(1, round(card.width * scale)), target_h), Image.LANCZOS)
    cx, cy = (size[0] - card.width) // 2, (size[1] - card.height) // 2

    # soft dark drop shadow, offset down
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    sh = Image.new("RGBA", card.size, (0, 0, 0, 170))
    sh.putalpha(card.getchannel("A").point(lambda a: int(a * 0.66)))
    shadow.paste(sh, (cx, cy + int(size[1] * 0.018)), sh)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(10, size[0] // 45)))

    # cyan brand glow, tight halo behind the card
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    gl = Image.new("RGBA", card.size, (0, 229, 255, 130))       # CypherColors.accent
    gl.putalpha(card.getchannel("A").point(lambda a: int(a * 0.5)))
    glow.paste(gl, (cx, cy), gl)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=max(14, size[0] // 30)))

    canvas = Image.alpha_composite(canvas, shadow)
    canvas = Image.alpha_composite(canvas, glow)
    canvas.paste(card, (cx, cy), card)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, "PNG", optimize=True)
    return {"ratio": ratio, "size": size, "card_px": card.size, "output": str(out),
            "bytes": out.stat().st_size}


def main():
    ap = argparse.ArgumentParser(description="Composite a true card render over a backdrop")
    ap.add_argument("--card", required=True)
    ap.add_argument("--backdrop", required=True)
    ap.add_argument("--ratio", choices=list(TARGETS), default="4:5")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    r = compose(Path(a.card), Path(a.backdrop), a.ratio, Path(a.out))
    print("  %s -> %s  canvas=%s card=%s  %d bytes"
          % (a.ratio, r["output"], r["size"], r["card_px"], r["bytes"]))


if __name__ == "__main__":
    main()
