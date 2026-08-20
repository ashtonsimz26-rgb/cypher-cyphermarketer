#!/usr/bin/env python3.12
"""Regression tests for the Drop Correspondent matcher.

Case 1 is the live defect: proposal p_afbd558609 (2026-08-20 03:46) paired the
headline "Nike Air Max Goadome Low 'Black'" with the Nike Air Humara 17 card.
Two generic overlaps (colorway "Black", token "air") were enough under the old
rule. It would have posted a factual error about a shoe we never matched.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import drop_correspondent as DC

HUMARA = {"image_name": "nike_air_humara_17_black", "rarity": "Rare",
          "name": "Nike Air Humara 17", "colorway": "Black",
          "silhouette": "Air Humara 17"}
MIND   = {"image_name": "nike_mind_001_mule_light_smoke_grey", "rarity": "Common",
          "name": "Nike Mind 001 Mule", "colorway": "Light Smoke Grey",
          "silhouette": "Mind 001 Mule"}
PUSHEAD = {"image_name": "sb_dunk_low_pushead", "rarity": "Rare",
           "name": "SB Dunk Low", "colorway": "Pushead", "silhouette": "SB Dunk Low"}
ROWS = [HUMARA, MIND, PUSHEAD]

CASES = [
    # (headline, expected image_name or None, why)
    ('Nike Air Max Goadome Low &#8220;Black&#8221;', None,
     "THE REGRESSION: different model, generic colourway must not match Humara"),
    ('Nike Air Max Goadome Low &#8220;Light Orewood Brown/Black&#8221;', None,
     "same defect, second overnight variant"),
    ('Nike Mind 001 &#8220;Light Smoke Grey&#8221;', None,
     "silhouette is 'Mind 001 Mule'; headline omits Mule -> stay conservative"),
    ('Nike Air Humara 17 &#8220;Black&#8221; Release Date', "nike_air_humara_17_black",
     "true positive: full silhouette present"),
    ('Nike Mind 001 Mule &#8220;Light Smoke Grey&#8221; drops Friday',
     "nike_mind_001_mule_light_smoke_grey", "true positive: full silhouette present"),
    ('The Nike SB Dunk Low &#8220;Pushead&#8221; is rumoured to return',
     "sb_dunk_low_pushead", "true positive: silhouette + distinctive colourway"),
    ('Nike Dunk Low &#8220;Black&#8221; restock', None,
     "generic colourway + partial silhouette must not match"),
    ('Air Jordan 1 High &#8220;Black&#8221;', None, "unrelated model"),
]


def main() -> int:
    bad = 0
    for headline, expect, why in CASES:
        got = DC.match(headline, ROWS)
        got_name = got["image_name"] if got else None
        ok = got_name == expect
        bad += 0 if ok else 1
        print("  %-4s %-58s -> %s" % ("PASS" if ok else "FAIL", headline[:58],
                                      got_name or "no match"))
        if not ok:
            print("       expected %s  (%s)" % (expect or "no match", why))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
