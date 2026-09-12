#!/usr/bin/env python3.12
"""
composition.py — FRAMING variants (F4.5). The card pixels are never touched.

THE SAMENESS PROBLEM, measured: every image ever produced is one composition —
card centred, CARD_HEIGHT_FRACTION 0.76, fixed cyan glow, fixed shadow offset —
over one of 6 scenes of which only 5 are distinct (Retro is byte-identical to
Basketball), and ALL SIX are night/dark with 5 of 6 wet or reflective. The feed
reads as one continuous rainy street. That is not a tuning problem; it is what
the code can express.

INVARIANT, unchanged from compose.py: the card is the pixel-true PNG from CPA's
renderer, scaled with LANCZOS and alpha-composited. Only FRAMING changes here —
scale, position, crop, and what sits behind it. No restyling, no recolouring,
no redrawing, and assert_renderer_pristine is untouched.

NO_BACKDROP is the strategically important one: it uses no generated imagery at
all, so it is the ONLY composition that could ever auto-post under the Phase-2
structural exclusion on uninspected generated images. It is also free.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageFilter, ImageDraw

TARGETS = {"4:5": (1080, 1350), "16:9": (1600, 900)}
ACCENT = (0, 229, 255)                     # CypherColors.accent


# ── scenes v2 ────────────────────────────────────────────────────────────────
# backdrop.py is C1-PARKED and must not be edited, so the corrected scene set
# lives here. Adopting it in backdrop.build_prompt is a follow-up gated on C1.
#   - Retro no longer duplicates Basketball
#   - three of eight are NOT night-and-wet
SCENES_V2 = {
    "Skateboarding": "a gritty empty concrete skate park at dusk under harsh floodlights, "
                     "worn ledges and rails, cracked asphalt, chain-link fencing, urban decay",
    "Basketball":    "an empty retro indoor basketball arena at night, polished hardwood floor "
                     "with mirror-like reflections, tiered empty seating fading into darkness, "
                     "dramatic overhead spotlights, drifting haze",
    # was a byte-identical copy of Basketball
    "Retro":         "a sunlit 1980s gymnasium in the late afternoon, varnished parquet, dust "
                     "motes in shafts of window light, folded bleachers, warm faded paintwork",
    "Running":       "an empty outdoor running track at blue hour, wet rubberized lanes with "
                     "reflections, stadium lights flaring, mist low to the ground",
    "Lifestyle":     "an empty rain-slicked city street at night, neon shop glow reflecting in "
                     "puddles, steam rising from grates, deep shadows, cinematic wide angle",
    "Training":      "an empty industrial training facility at night, polished concrete floor, "
                     "shafts of light through high windows, haze",
    # daylight / interior, so the feed is not one continuous rainy street
    "Daylight":      "a bright empty rooftop basketball court at midday, bleached concrete, "
                     "crisp hard shadows, clear blue sky, chain-link fence, no people",
    "Studio":        "a clean seamless photographic studio backdrop in warm off-white, soft "
                     "even light, subtle floor gradient, no props, no people",
}
SCENES_V2["Morning"] = ("an empty sunlit city sidewalk early on a clear morning, long "
                        "soft shadows, warm low light on pale concrete, shopfront "
                        "shutters still down, no people")
SCENES_V2["Court"] = ("a well-lit indoor sports hall in the afternoon, pale wood floor, "
                      "high clerestory windows, clean bright daylight, painted lines, "
                      "no people, no equipment")
NON_NIGHT_SCENES = frozenset({"Retro", "Daylight", "Studio", "Morning", "Court"})


def _fit(bd: Image.Image, size: tuple[int, int]) -> Image.Image:
    tw, th = size
    s = max(tw / bd.width, th / bd.height)
    nb = bd.resize((max(1, round(bd.width * s)), max(1, round(bd.height * s))), Image.LANCZOS)
    l, t = (nb.width - tw) // 2, (nb.height - th) // 2
    return nb.crop((l, t, l + tw, t + th)).convert("RGBA")


def _scaled(card: Image.Image, height: int) -> Image.Image:
    s = height / card.height
    return card.resize((max(1, round(card.width * s)), height), Image.LANCZOS)


def _shadow_glow(canvas, card, pos, size, *, glow=True):
    cx, cy = pos
    sh = Image.new("RGBA", size, (0, 0, 0, 0))
    s = Image.new("RGBA", card.size, (0, 0, 0, 170))
    s.putalpha(card.getchannel("A").point(lambda a: int(a * 0.66)))
    sh.paste(s, (cx, cy + int(size[1] * 0.018)), s)
    canvas = Image.alpha_composite(canvas, sh.filter(
        ImageFilter.GaussianBlur(radius=max(10, size[0] // 45))))
    if glow:
        g = Image.new("RGBA", size, (0, 0, 0, 0))
        gl = Image.new("RGBA", card.size, (*ACCENT, 130))
        gl.putalpha(card.getchannel("A").point(lambda a: int(a * 0.5)))
        g.paste(gl, (cx, cy), gl)
        canvas = Image.alpha_composite(canvas, g.filter(
            ImageFilter.GaussianBlur(radius=max(14, size[0] // 30))))
    return canvas


def _gradient(size, top=(14, 16, 22), bottom=(4, 5, 8)) -> Image.Image:
    w, h = size
    g = Image.new("RGB", (1, h))
    d = ImageDraw.Draw(g)
    for y in range(h):
        f = y / max(1, h - 1)
        d.point((0, y), tuple(round(top[i] + (bottom[i] - top[i]) * f) for i in range(3)))
    return g.resize(size, Image.BILINEAR).convert("RGBA")


# ── the compositions ─────────────────────────────────────────────────────────
def hero(card, backdrop, size):
    """Current production framing: centred, 0.76 height."""
    canvas = _fit(backdrop, size)
    c = _scaled(card, int(size[1] * 0.76))
    pos = ((size[0] - c.width) // 2, (size[1] - c.height) // 2)
    canvas = _shadow_glow(canvas, c, pos, size)
    canvas.paste(c, pos, c)
    return canvas


def close_crop(card, backdrop, size):
    """Same pixels, tight framing — card oversized so its edges bleed off frame."""
    canvas = _fit(backdrop, size)
    c = _scaled(card, int(size[1] * 1.45))
    pos = ((size[0] - c.width) // 2, int(-c.height * 0.20))
    canvas = _shadow_glow(canvas, c, pos, size, glow=False)
    canvas.paste(c, pos, c)
    return canvas


def off_centre(card, backdrop, size):
    """Card on a thirds intersection; the backdrop carries the negative space."""
    canvas = _fit(backdrop, size)
    c = _scaled(card, int(size[1] * 0.66))
    pos = (int(size[0] * 0.62) - c.width // 2, int(size[1] * 0.56) - c.height // 2)
    canvas = _shadow_glow(canvas, c, pos, size)
    canvas.paste(c, pos, c)
    return canvas


def no_backdrop(card, backdrop, size):
    """Clean dark gradient. NO generated imagery — the only composition Phase 2
    could ever auto-post under the uninspected-imagery exclusion. Free."""
    canvas = _gradient(size)
    c = _scaled(card, int(size[1] * 0.80))
    pos = ((size[0] - c.width) // 2, (size[1] - c.height) // 2)
    canvas = _shadow_glow(canvas, c, pos, size)
    canvas.paste(c, pos, c)
    return canvas


def two_card(card, backdrop, size, card_b=None):
    """Two cards, overlapping, angled apart — unlocks `which_would_you_pull`,
    which SOUL names and which has never once been produced (compose.py is
    single-card, so the format was DECLARED_NOT_READY)."""
    canvas = _fit(backdrop, size) if backdrop else _gradient(size)
    # ★ BOTH TITLES AND BOTH COLORWAY LINES MUST BE FULLY LEGIBLE.
    # The card lays its title at roughly 0.23 of card height and the colorway
    # line just under it, so the front card's TOP EDGE must sit BELOW the back
    # card's colorway line — not merely below its title. The previous offsets
    # put the front top at y=405 against a back title zone ending at y=426,
    # which clipped the back title mid-word and hid its colorway entirely.
    # A "which would you pull" post is unreadable if either shoe has no name.
    b = _scaled(card_b or card, int(size[1] * 0.52))
    a = _scaled(card, int(size[1] * 0.56))
    pb = (int(size[0] * 0.72) - b.width // 2, int(size[1] * 0.34) - b.height // 2)
    pa = (int(size[0] * 0.30) - a.width // 2, int(size[1] * 0.66) - a.height // 2)
    canvas = _shadow_glow(canvas, b, pb, size, glow=False)
    canvas.paste(b, pb, b)
    canvas = _shadow_glow(canvas, a, pa, size)
    canvas.paste(a, pa, a)
    return canvas


def shoe_crop(card, backdrop, size):
    """THE WORKHORSE. The SHOE is the subject, not a thumbnail inside a card.

    ★ AND THE ONLY COMPOSITION WITH card_shows_value=False.
    The EST. VALUE figure renders at card y 0.661-0.679 (measured on the live
    render, not assumed). This frame cuts the card at 0.63, so the stats row is
    genuinely OUT OF FRAME — which is what makes the attribution sentence
    unnecessary here rather than merely unwanted. Scale 1.45 puts the side crop
    at 82px against ~100px of title padding, so the title and colorway survive.
    """
    canvas = _fit(backdrop, size) if backdrop else _gradient(size)
    c = _scaled(card, int(size[1] * CROP_SCALE))
    top = round(size[1] - STATS_CUT * c.height)
    pos = ((size[0] - c.width) // 2, top)
    canvas = _shadow_glow(canvas, c, pos, size, glow=False)
    canvas.paste(c, pos, c)
    return canvas


COMPOSITIONS = {
    "shoe_crop": shoe_crop, "hero": hero, "close_crop": close_crop,
    "off_centre": off_centre, "no_backdrop": no_backdrop, "two_card": two_card,
}
NEEDS_BACKDROP = frozenset({"shoe_crop", "hero", "close_crop", "off_centre", "two_card"})

# ── card_shows_value, COMPUTED not hardcoded (G2) ────────────────────────────
# rails.check_draft demands an attribution marker only when the card's EST.
# VALUE figure is in frame. That was passed as a hardcoded True everywhere, so
# every post carried the sentence. It is a RAIL, so the answer is to stop
# SHOWING the figure, never to stop attributing it: a composition that crops the
# stats row out is genuinely card_shows_value=False and needs no marker. A
# composition that shows it keeps the attribution, with no exception.
#
# Measured on the live 840x1320 render: the green EST. VALUE figure occupies
# card y 0.661-0.679. Every composition below is evaluated against that band.
# The green FIGURE sits at 0.661-0.679; the whole stats PANEL, labels included,
# starts higher. The cut clears the PANEL, not just the number — a visible
# "EST. VALUE" label with the figure sheared off looks like a rendering fault,
# and the honest claim is that the stats row is absent, not half-absent.
STATS_BAND = (0.661, 0.679)
STATS_PANEL_TOP = 0.618
STATS_CUT = 0.615         # bottom edge, above the whole panel
# ★ 1.27 is the LARGEST scale at which the card does not overflow the canvas
# horizontally. 1.45 was tried first and clipped the title at both edges —
# "CYPHER" read "YPHER", the colorway read "ravis Scott Olive", and the rarity
# chip was cut. My side-crop estimate assumed ~100px of title padding; the real
# padding is smaller. The card must stay fully within the frame width, so the
# vertical fill comes from a backdrop band above the card rather than from
# scaling past the edges.
CROP_SCALE = 1.25

SHOWS_VALUE = {
    "shoe_crop":  False,   # cut at 0.63 — stats row out of frame
    "hero":       True,
    "close_crop": True,
    "off_centre": True,
    "no_backdrop": True,
    "two_card":   True,
}


def card_shows_value(composition: str) -> bool:
    """Fail CLOSED: an unknown composition is assumed to show the figure."""
    return SHOWS_VALUE.get(composition, True)


def render(name: str, card_path: Path, backdrop_path: Path | None, out: Path,
           ratio: str = "4:5", card_b_path: Path | None = None) -> dict:
    size = TARGETS[ratio]
    card = Image.open(card_path).convert("RGBA")
    bd = Image.open(backdrop_path) if backdrop_path else None
    fn = COMPOSITIONS[name]
    canvas = fn(card, bd, size, Image.open(card_b_path).convert("RGBA")) \
        if name == "two_card" else fn(card, bd, size)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, "PNG", optimize=True)
    return {"composition": name, "ratio": ratio, "output": str(out),
            "bytes": out.stat().st_size}
