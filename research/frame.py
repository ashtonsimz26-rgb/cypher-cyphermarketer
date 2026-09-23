#!/usr/bin/env python3.12
"""
frame.py — FRAME CHECK. The gate the composed image never had.

★★ WHY THIS EXISTS. rails.check_draft() reads TEXT. Every one of its nine rails
is a claim about a sentence, and `image_name` is a catalog key, not a pixel —
there is no parameter an image could arrive in. So on 2026-09-17 a proposal
shipped with a black shoe on a dark panel, all nine rails green, because
nothing in the pipeline had ever looked at the picture.

SOUL.md § AUTONOMY already names this hole: Phase 2 is excluded for generated
imagery "unless a backdrop inspection mechanism exists", because otherwise
Ashton's approval is the only review between an unreviewed image and the feed.
This module is the beginning of that mechanism. It is governance, not polish.

★ SCOPE, AND WHAT IS DELIBERATELY NOT IN IT (ruled 2026-09-17)
  IN   contrast — the shoe against the card panel behind it
  NOT  frame overflow (D1) — a separate check, separate PR
  NOT  card-on-card occlusion (D2 of the frame family) — a THIRD failure
       shape, distinct from overflow: the two_card incident was one card
       covering another's title, which no frame-bounds test would have caught.
       Recorded here as a KNOWN GAP so it is not mistaken for covered.

★★ THE FINDING THAT MAKES THIS CHEAP. The failure is shoe-vs-CARD, never
shoe-vs-backdrop. The card's panel is OPAQUE and always sits between the shoe
and the scene, so no backdrop choice changes this number — measured on the
2026-09-17 proposal: shoe vs panel 1.07:1, card vs backdrop 3.17:1. The card
was legible; the subject was not.

Two consequences, both load-bearing:
  1. It is a pure function of (card render, rarity). No scene, no composition.
  2. It therefore runs BEFORE the $0.04 backdrop call, so a dark-on-dark card
     costs nothing to reject.

★★ THE PANEL IS KNOWN, SO SEGMENTATION IS NOT A GUESS. The card background is
a fixed, rarity-coded gradient — byte-identical across every card of a rarity,
verified across 374 renders. Rendering one card per rarity with a FULLY
TRANSPARENT shoe asset yields the bare panel exactly. Shoe pixels are then
"where the card differs from its own bare panel", and every shoe pixel is
compared against THE EXACT PANEL PIXEL IT COVERS. No colour rule, nothing to
tune, no threshold on blueness.

An earlier attempt estimated the panel as the pixelwise MEDIAN across a tier's
cards and was wrong by 3x (55.9 luma against a true 17.9): in the card's centre
most shoes overlap, so the median returns a typical SHOE. The transparent-asset
render replaced an estimator with a measurement.

★★ THE THRESHOLDS ARE ASHTON'S, RULED 2026-09-17 AGAINST IMAGES.
Measured across all 374 pool-reachable cards, then ruled from a contact sheet of
the 1.15-1.50 band rather than from the ratios alone:

    edge contrast   min 1.04 | p5 1.16 | p25 1.53 | median 2.22 | max 7.80

    BLOCK <= 1.15   16 rows (4.3%), 14 shoes with no passing tier (4.2%)
    FLAG  <= 1.50   69 rows surfaced, overridable, nothing lost
    PASS  >  1.50

A single hard floor at 1.38 would have caught the 2026-09-17 proposal but cost
55 shoes permanently. The two-tier gate costs 14 and routes the judgement calls
to the person who makes them. These numbers are a RULING, not a measurement —
they may be revised, and the ledger is being fed to make that revision evidence-
based rather than another estimate (see telegram_bot: contrast is recorded on
EVERY approval, not only flagged ones).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import NamedTuple

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent.parent
PANELS = HERE / "state" / "panels"          # gitignored; regenerable
SHOE_WINDOW = (0.315, 0.615)                # research/composition.SHOE_WINDOW

# ── Ashton's ruling, 2026-09-17 ──────────────────────────────────────────────
BLOCK_AT = 1.15
FLAG_AT = 1.50
RULED_ON = "2026-09-17"

# A pixel counts as shoe when it departs this far from the bare panel. Well
# above renderer dithering, well below any real shoe edge.
SHOE_DELTA = 18
MIN_SHOE_PX = 2000
MIN_RING_PX = 200


class FrameResult(NamedTuple):
    band: str            # "block" | "flag" | "pass" | "unmeasured"
    ratio: float | None
    why: str
    frac_below_1_5: float | None = None

    @property
    def blocked(self) -> bool:
        return self.band == "block"

    @property
    def flagged(self) -> bool:
        return self.band == "flag"


def _luma(a: np.ndarray) -> np.ndarray:
    return 0.2126*a[..., 0] + 0.7152*a[..., 1] + 0.0722*a[..., 2]


def _contrast(l1, l2):
    hi, lo = np.maximum(l1, l2)/255.0, np.minimum(l1, l2)/255.0
    f = lambda c: np.where(c <= 0.04045, c/12.92, ((c+0.055)/1.055)**2.4)  # noqa: E731
    return (f(hi)+0.05)/(f(lo)+0.05)


def _window(png: Path) -> np.ndarray:
    a = np.asarray(Image.open(png).convert("RGB")).astype(float)
    h = a.shape[0]
    return a[int(h*SHOE_WINDOW[0]):int(h*SHOE_WINDOW[1])]


def bare_panel(rarity: str, *, refresh: bool = False) -> Path | None:
    """The card background for a rarity, with NO shoe on it.

    Rendered once per rarity by handing CPA's renderer a fully transparent
    image asset, then cached under state/. Read-only use of the binary — never
    `swift build`, never a write into its directory (card_render's rail).
    """
    PANELS.mkdir(parents=True, exist_ok=True)
    out = PANELS / ("%s.png" % rarity.replace(" ", "_"))
    if out.exists() and not refresh:
        return out
    import card_render as CR                      # local: keeps import cheap
    if not CR.RENDERER_BIN.exists():
        return None
    # ★ NO FIXED SCRATCH, AND AN ATOMIC CACHE (2026-09-22). The blank asset and the
    # renderer input used to be fixed files in this directory, and the renderer
    # wrote the panel straight onto its cache path. The digest and the drops job
    # both reach this through the Frame Check, so two first-time renders could
    # hand the renderer each other's input, and a reader could meet a half-written
    # panel. Now: the blank PNG and the input live in a per-call temp dir (gone on
    # exit), and the panel renders to a temp file IN THIS DIRECTORY and is renamed
    # onto the cache path — rename is atomic, a partial write is not.
    import os, tempfile
    with tempfile.TemporaryDirectory(prefix="cm_panel_") as td:
        blank = Path(td) / "transparent.png"
        Image.new("RGBA", (1200, 1200), (0, 0, 0, 0)).save(blank)
        card = {"sneakerName": "", "colorway": "", "brand": "", "imageName": "_panel",
                "imagePath": str(blank), "rarity": rarity, "badges": [], "condition": None,
                "serialNumber": "", "setName": "", "retailPrice": "N/A",
                "resalePrice": "N/A", "year": "", "flavorText": "", "outputFilename": None}
        tmp_in = Path(td) / "panel_in.json"
        tmp_in.write_text(json.dumps(card), encoding="utf-8")
        fd, part = tempfile.mkstemp(dir=PANELS, prefix=".%s." % out.stem, suffix=".png")
        os.close(fd)
        part = Path(part)
        try:
            p = subprocess.run([str(CR.RENDERER_BIN), "--input", str(tmp_in),
                                "--output", str(part)],
                               capture_output=True, text=True, timeout=120)
            CR.assert_renderer_pristine()         # rail, every invocation
            if p.returncode == 0 and part.exists() and part.stat().st_size > 0:
                os.replace(part, out)             # atomic: readers see old or new, never half
                return out
            return None
        finally:
            part.unlink(missing_ok=True)


def check_frame(card_png: Path | str, rarity: str) -> FrameResult:
    """Does the SHOE read against the panel behind it?

    ★ FAILS OPEN, DELIBERATELY, AND THIS IS THE ONE PLACE IT IS RIGHT.
    Everywhere else in this repo an unverifiable input fails CLOSED, because
    the thing being gated is a CLAIM and silence costs nothing. Here the thing
    being gated is a legibility judgement about a card that is otherwise
    postable, and a missing panel reference is a fault in THIS module, not
    evidence against the card. Blocking a good post because the renderer was
    unavailable would be this check inventing a rejection.

    So an unmeasurable card returns band="unmeasured", which never blocks and
    never flags — but it IS recorded, so a run of them is visible rather than
    looking like a clean pass.
    """
    card_png = Path(card_png)
    if not card_png.exists():
        return FrameResult("unmeasured", None, "no card render at %s" % card_png)
    ref_png = bare_panel(rarity)
    if ref_png is None:
        return FrameResult("unmeasured", None,
                           "no bare panel for %r (renderer unavailable)" % rarity)
    try:
        card, ref = _window(card_png), _window(ref_png)
    except Exception as e:                                       # noqa: BLE001
        return FrameResult("unmeasured", None, "unreadable image: %s" % e)
    if card.shape != ref.shape:
        return FrameResult("unmeasured", None,
                           "card %s does not match panel %s" % (card.shape, ref.shape))

    cardL, refL = _luma(card), _luma(ref)
    shoe = np.linalg.norm(card - ref, axis=-1) > SHOE_DELTA
    if shoe.sum() < MIN_SHOE_PX:
        # ★ THIS IS A MEASUREMENT, NOT A MODULE FAULT, AND THE DIFFERENCE MATTERS.
        # The first version returned "unmeasured" here, which fails OPEN — so the
        # single most invisible card possible, a shoe that departs from its panel
        # nowhere, would have been the one case the gate waved through. Caught by
        # tests/test_frame_contrast.py section 2 before it ever ran on a card.
        #
        # A readable card that does not differ from its own bare panel has told
        # us exactly what we asked: the shoe does not read. The unmeasured band
        # is for a broken input (no render, no panel, unreadable file) — all
        # returned ABOVE this line, before any pixel is judged.
        return FrameResult("block", float(_contrast(cardL.mean(), refL.mean())),
                           "shoe is indistinguishable from the %s panel "
                           "(%d departing pixels)" % (rarity, int(shoe.sum())), 1.0)

    pix = _contrast(cardL[shoe], refL[shoe])
    frac = float((pix < 1.5).mean())

    m = Image.fromarray((shoe*255).astype("uint8"))
    dil = np.asarray(m.filter(ImageFilter.MaxFilter(13))) > 127
    ero = np.asarray(m.filter(ImageFilter.MinFilter(13))) > 127
    ring_shoe, ring_panel = shoe & ~ero, dil & ~shoe
    if ring_shoe.sum() < MIN_RING_PX or ring_panel.sum() < MIN_RING_PX:
        return FrameResult("unmeasured", None, "silhouette too small to measure")

    ratio = float(_contrast(cardL[ring_shoe].mean(), refL[ring_panel].mean()))
    if ratio <= BLOCK_AT:
        band, why = "block", ("shoe does not read against the %s panel" % rarity)
    elif ratio <= FLAG_AT:
        band, why = "flag", ("dark shoe on the %s panel; %.0f%% of shoe pixels "
                             "below 1.5" % (rarity, 100*frac))
    else:
        band, why = "pass", "shoe reads"
    return FrameResult(band, ratio, why, frac)


def digest_note(r: FrameResult) -> str:
    """The reviewer-facing warning, or "".

    ★ Reuses backdrop.inspection_note()'s idiom on purpose (ruled 2026-09-17):
    same ⚠️ prefix, same "before approving" phrasing, appended to the same
    proposal note field. A second warning idiom would mean two things to learn
    and two places to look on a phone.
    """
    if r.band == "flag":
        return (" ⚠️ LOW CONTRAST %.2f:1 — %s. Zoom the card before approving; "
                "reply `override` to post anyway." % (r.ratio, r.why))
    if r.band == "unmeasured":
        return " ⚠️ CONTRAST NOT MEASURED — %s" % r.why
    return ""
