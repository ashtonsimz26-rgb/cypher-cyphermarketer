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


# ★★ `angled` IS RETIRED — DO NOT RESURRECT IT (ruled 2026-09-17).
# It rotated an ALREADY-OVERSIZED card: ANGLED_SCALE 1.32 gave a 1133px-wide
# card, and rotate(-6, expand=True) grew that to 1314px against a 1080px frame.
# It shipped clipped at BOTH edges every time it ran (twice, per runs.jsonl).
#
# IT WAS NOT RESCALED, AND THE ARITHMETIC IS WHY. Rotated width is
# w*cos(6) + h*sin(6), so the safe scale depends on the rotation angle AND the
# card's aspect ratio — which CPA owns, not this repo. Measured:
#     4:5  (1080x1350) tolerates ANGLED_SCALE <= 1.085
#     16:9 (1600x900)  tolerates              <= 2.411
# One constant cannot serve both; they are 2.2x apart. A rescale would be a
# hand-tuned number that silently re-breaks the day CPA changes the card
# aspect or a new target ratio is added — which is precisely how shoe_crop
# (1.45 -> 1.25) and two_card_crop (0.95H -> cropped regions) were each
# "fixed" once without ever gaining a gate. Nine compositions remain, four of
# them no-attribution. Losing one is cheaper than keeping one that needs
# watching.
#
# WHAT THE ROTATION BOUGHT, recorded so the loss is known rather than
# discovered: it was the ONLY composition with a non-axis-aligned card. Every
# remaining frame is square to the canvas, so the rotation was the single
# source of tilt in the rotation, and nothing else provides it. If that
# attitude is wanted again, it needs a composition designed to rotate — one
# that fits the frame AFTER rotation by construction, not a constant trimmed
# until it happens to.
POSTER_SCALE = 0.82
SHOE_WINDOW = (0.315, 0.615)       # the card's shoe panel, measured on the render
# 0.08 sheared the TOP of the title ("NIKE AIR FORCE 1 SUPREME TZ" lost its
# caps); 0.045 clears it. Measured by looking at the render, not computed.
TITLE_SHOE_WINDOW = (0.045, 0.615)  # header + title + colorway + shoe, no stats


def _card_region(card, y0f, y1f):
    """Crop the card to a vertical band. Pixel-true — a crop, never a redraw."""
    h = card.height
    return card.crop((0, int(h * y0f), card.width, int(h * y1f)))


def shoe_only(card, backdrop, size):
    """The SHOE alone on a scene — the card's shoe panel, cropped out of the
    chrome entirely.

    ★ card_shows_value is False here for a STRONGER reason than framing: no
    part of the card's stats panel is drawn at all. The crop is taken from the
    shoe window (0.315-0.615), which ends a full 0.003 above STATS_PANEL_TOP,
    so the figure cannot appear even at the edge. placements() returns [] for
    this composition, so stats_in_frame() is False by construction rather than
    by arithmetic.
    """
    canvas = _fit(backdrop, size) if backdrop else _gradient(size)
    win = _card_region(card, *SHOE_WINDOW)
    s = min((size[0] * 0.92) / win.width, (size[1] * 0.62) / win.height)
    win = win.resize((max(1, round(win.width * s)), max(1, round(win.height * s))),
                     Image.LANCZOS)
    pos = ((size[0] - win.width) // 2, int(size[1] * 0.54) - win.height // 2)
    canvas = _shadow_glow(canvas, win, pos, size, glow=False)
    canvas.paste(win, pos, win)
    return canvas


def two_card_crop(card, backdrop, size, card_b=None):
    """which_would_you_pull WITHOUT the disclaimer.

    Each card is CROPPED to its title+shoe region (0.08-0.615) and the two sit
    side by side, so both names stay legible and neither contributes a value
    figure. The first attempt scaled whole cards to 0.95H and overlapped them —
    titles were clipped on both sides and the stats panel was only just out of
    frame. Cropping the region first is both safer and more legible.
    """
    canvas = _fit(backdrop, size) if backdrop else _gradient(size)
    W, H = size
    for i, src in enumerate((card_b or card, card)):
        win = _card_region(src, TITLE_SHOE_WINDOW[0], TITLE_SHOE_WINDOW[1])
        tw = int(W * 0.46)
        s_ = tw / win.width
        win = win.resize((tw, max(1, round(win.height * s_))), Image.LANCZOS)
        x = int(W * (0.265 if i == 0 else 0.735)) - win.width // 2
        y = int(H * (0.40 if i == 0 else 0.58)) - win.height // 2
        canvas = _shadow_glow(canvas, win, (x, y), size, glow=False)
        canvas.paste(win, (x, y), win)
    return canvas


def poster(card, backdrop, size):
    """Editorial-poster: the BACKDROP is the subject, the card is placed small
    and low, still cut above the stats panel."""
    canvas = _fit(backdrop, size) if backdrop else _gradient(size)
    ch = int(size[1] * POSTER_SCALE)
    c = _scaled(card, ch)
    top = round(size[1] * 0.52 - STATS_CUT * ch)
    pos = (int(size[0] * 0.50) - c.width // 2, top)
    canvas = _shadow_glow(canvas, c, pos, size, glow=False)
    canvas.paste(c, pos, c)
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
    "shoe_crop": shoe_crop, "shoe_only": shoe_only,
    "two_card_crop": two_card_crop, "poster": poster,
    "hero": hero, "close_crop": close_crop, "off_centre": off_centre,
    "no_backdrop": no_backdrop, "two_card": two_card,
}
NEEDS_BACKDROP = frozenset(set(COMPOSITIONS) - {"no_backdrop"})
# Compositions that draw a SECOND card. render() forwards card_b by membership
# here rather than by an equality test on one name.
TWO_CARD_COMPOSITIONS = frozenset({"two_card", "two_card_crop"})
# ★ Not an image composition, and deliberately NOT in COMPOSITIONS: there is
# nothing to render. It names a proposal/post made with IMAGES_ENABLED=false
# (switches.py), so every ledger row, rotation read and report can tell a
# text-only post from an image post. rails_card_shows_value maps it to False.
TEXT_ONLY = "text_only"

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

# ★★ card_shows_value IS DERIVED FROM GEOMETRY, NOT A HAND-MAINTAINED DICT.
# A wrongly-computed False is a RAILS VIOLATION, not a cosmetic error: the post
# would ship with no attribution sentence while the EST. VALUE figure sat in
# frame. A dict is exactly the kind of thing that goes stale when a composition
# is retuned — shoe_crop's scale and cut changed twice on the day it was built.
# So PLACEMENTS is the single source of truth: every composition declares where
# it puts each card, render() uses it to draw, and card_shows_value() uses the
# same numbers to decide. They cannot disagree.
#
# A card CONTRIBUTES the figure only if the stats band, mapped through that
# card's own placement, intersects the canvas.

def placements(name: str, size: tuple[int, int]) -> list[tuple[int, int]]:
    """[(top_y, card_height)] for every card this composition draws."""
    W, H = size
    if name == "hero":
        ch = int(H * 0.76); return [((H - ch) // 2, ch)]
    if name == "close_crop":
        ch = int(H * 1.45); return [(int(-ch * 0.20), ch)]
    if name == "off_centre":
        ch = int(H * 0.66); return [(int(H * 0.56) - ch // 2, ch)]
    if name == "no_backdrop":
        ch = int(H * 0.80); return [((H - ch) // 2, ch)]
    if name == "two_card":
        b = int(H * 0.52); a_ = int(H * 0.56)
        return [(int(H * 0.34) - b // 2, b), (int(H * 0.66) - a_ // 2, a_)]
    if name == "shoe_crop":
        ch = int(H * CROP_SCALE); return [(round(H - STATS_CUT * ch), ch)]
    if name == "shoe_only":
        return []                      # no card chrome at all — see shoe_only()
    if name == "two_card_crop":
        return []                      # cropped regions only — no stats panel drawn
    if name == "poster":
        ch = int(H * POSTER_SCALE); return [(round(H * 0.52 - STATS_CUT * ch), ch)]
    raise KeyError("no placement declared for composition %r" % name)


# ── R3: the scene promises a band; this checks the composition uses it ───────
# backdrop.STAGE_RULE tells every generated scene to keep the CENTRAL THIRD open
# and evenly lit, because placements() showed 38%-60% of frame height is covered
# by every composition. That number is a measurement of today's compositions, so
# it can go stale the moment one is added or retuned — and the symptom would be
# a card landing on a lamppost, in a frame that was never asked to be clear
# there.
#
# ★ OWNERSHIP: the scene GUARANTEES the band, the composition USES it, and this
# VERIFIES they agree. It does not reposition anything. Letting the scene drive
# placement would invert the ownership — framing belongs to the composition —
# and silently re-centring a card would hide exactly the drift worth seeing.
CLEAR_ZONE = (0.38, 0.60)          # fraction of frame height, from STAGE_RULE


def clear_zone_ok(name: str, size: tuple[int, int]) -> tuple[bool, str]:
    """(ok, why). True when every card this composition draws overlaps the band
    the scenes are told to keep clear.

    A composition drawing NO card chrome (shoe_only, two_card_crop) trivially
    passes: there is no card band to fall outside.
    """
    W, H = size
    lo, hi = CLEAR_ZONE
    pl = placements(name, size)
    if not pl:
        return True, "%s draws no card chrome" % name
    bad = []
    for top, ch in pl:
        a, b = top / H, (top + ch) / H
        if b <= lo or a >= hi:                     # no overlap with the band
            bad.append("card at %.0f%%-%.0f%%" % (100 * a, 100 * b))
    if bad:
        return False, ("%s places %s, outside the %.0f%%-%.0f%% band the scenes "
                       "are told to keep clear" % (name, "; ".join(bad),
                                                   100 * lo, 100 * hi))
    return True, "%s overlaps the clear band" % name


def assert_clear_zone(name: str, size: tuple[int, int]) -> None:
    """★ LOUD, never silent. A composition that has drifted outside what the
    stems promise is reported — the caller does not get a quietly re-centred
    card and no way to know."""
    ok, why = clear_zone_ok(name, size)
    if not ok:
        raise ClearZoneDrift(why)


class ClearZoneDrift(AssertionError):
    """A composition places its card where no scene was asked to stay clear."""


def stats_in_frame(name: str, size: tuple[int, int]) -> bool:
    """Does the EST. VALUE band land inside the canvas for ANY card drawn?"""
    H = size[1]
    for top, ch in placements(name, size):
        y0 = top + ch * STATS_PANEL_TOP
        y1 = top + ch * STATS_BAND[1]
        if y1 > 0 and y0 < H:          # any overlap at all
            return True
    return False


def card_shows_value(composition: str, size: tuple[int, int] | None = None) -> bool:
    """Fail CLOSED. An undeclared composition returns True — assume the figure
    is shown — rather than guessing; a silent False here is a rails violation.
    (Corrected 2026-09-18: this said "raises". It never raised.)"""
    size = size or TARGETS["4:5"]
    if composition not in COMPOSITIONS:
        return True                    # unknown -> assume the figure is shown
    return stats_in_frame(composition, size)


def rails_card_shows_value(composition: str | None) -> bool:
    """The ONE derivation of card_shows_value that rails.check_draft() receives.

    ★★ BOTH DOORS CALL THIS, AND THAT IS THE WHOLE POINT. gate8 (draft time,
    daily_digest) and rails_gate (approve time, telegram_bot) each used to derive
    this input for themselves. G2 (13834d0, 09-11) taught the digest door to
    compute it from the composition and never touched the approve door, which kept
    a literal True. From then until 2026-09-18 the same text on the same card
    passed at draft and failed at approval for every composition that crops the
    EST. VALUE row out — shoe_crop, shoe_only, two_card_crop, 3 of 9 — while a
    docstring at each door asserted the two matched.

    Two call sites deriving one input independently agree only while their
    sources happen to coincide. One function called from both cannot disagree
    with itself. tests/test_rails_door_parity.py holds the doors to the same
    verdict across every composition.

    Missing composition -> True: fail closed, require attribution.

    TEXT_ONLY -> False (2026-09-22, IMAGES_ENABLED=false). A text-only post shows
    no card, so it shows no EST. VALUE figure, so there is nothing to attribute.
    The mapping lives HERE, in the one function both doors call, so a text-only
    proposal cannot pass at draft and fail at approval. It is an explicit name,
    not a fall-through: anything unregistered still fails closed to True.
    """
    if composition == TEXT_ONLY:
        return False
    return True if not composition else card_shows_value(composition)


def render(name: str, card_path: Path, backdrop_path: Path | None, out: Path,
           ratio: str = "4:5", card_b_path: Path | None = None) -> dict:
    size = TARGETS[ratio]
    card = Image.open(card_path).convert("RGBA")
    bd = Image.open(backdrop_path) if backdrop_path else None
    fn = COMPOSITIONS[name]
    # ★ FIXED 2026-09-16. This read `if name == "two_card"`, so two_card_crop —
    # the composition E4 FORCES for which_would_you_pull — never received the
    # second card and drew `(card_b or card, card)`: the same card twice, in a
    # post whose entire point is a choice between two. Named by MEMBERSHIP now,
    # so a third two-card composition cannot silently miss the same way.
    if name in TWO_CARD_COMPOSITIONS:
        b = Image.open(card_b_path).convert("RGBA") if card_b_path else None
        canvas = fn(card, bd, size, b)
    else:
        canvas = fn(card, bd, size)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, "PNG", optimize=True)
    return {"composition": name, "ratio": ratio, "output": str(out),
            "bytes": out.stat().st_size}
