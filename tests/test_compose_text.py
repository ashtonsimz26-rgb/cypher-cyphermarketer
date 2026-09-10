#!/usr/bin/env python3.12
"""F4.2 suite. Zero LLM, zero network."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rails
from research import compose_text as C

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

ATTR_LABEL = "card image w/ value figure carries real-sneaker attribution"
def attr_passes(text: str) -> bool:
    checks = rails.check_draft(text, card_shows_value=True, pool_reachable=True,
                               price_verified=True)
    return dict((c[0], c[1]) for c in checks)[ATTR_LABEL]

print("\n=== 1. EVERY member of the constant set satisfies has_attr ===")
for i, line in enumerate(C.ATTRIBUTION_LINES):
    ok(attr_passes(line), f"[{i}] {line[:62]}…")
ok(len(C.ATTRIBUTION_LINES) >= 2, f"set has alternates: {len(C.ATTRIBUTION_LINES)}")

print("\n=== 2. the set is FROZEN — cannot be appended to at runtime ===")
ok(isinstance(C.ATTRIBUTION_LINES, tuple),
   f"is a tuple, not a list: {type(C.ATTRIBUTION_LINES).__name__}")
try:
    C.ATTRIBUTION_LINES.append("x"); ok(False, "append() raised")
except AttributeError:
    ok(True, "append() raises AttributeError — immutable")
try:
    C.ATTRIBUTION_LINES[0] = "x"; ok(False, "item assignment raised")
except TypeError:
    ok(True, "item assignment raises TypeError — immutable")

print("\n=== 3. a composed post passes the attribution rail end to end ===")
post = C.compose(lead="1985. The NBA sent Nike a letter.", body=None)
ok(attr_passes(post), "normal-day post carries a marker")
ok(C.attribution() in post, "attribution sentence present verbatim")
print("      " + post.replace("\n", " / ")[:110] + "…")

print("\n=== 4. the writer's own phrasing CANNOT break the rail ===")
# the natural-but-failing phrasing from GROUND, supplied as a LEAD
bad_lead = "The card tracks its resale, not the card."
ok(not attr_passes(bad_lead), "the trap phrasing alone FAILS the rail (as measured)")
ok(attr_passes(C.compose(lead=bad_lead)), "…but the composed post still PASSES — writer cannot break it")

print("\n=== 5. MOMENT TEXT byte-identity — reads the FILE, not memory ===")
d = json.loads((Path(__file__).resolve().parent.parent / "data/moments.json").read_text())
mid, mtext = None, None
for entries in d["moments"].values():
    for e in entries:
        if e.get("sources") and e.get("post_text"):
            # post_text is what ships; `text` is the verified fact record and
            # composing it must HALT (asserted below).
            mid, mtext = e["id"], e["post_text"]; break
    if mid: break
post = C.compose(moment_text=mtext, moment_id=mid, linking_line="Its card is pullable today.")
ok(mtext in post, f"moment {mid} carried verbatim")
ok(attr_passes(post), "moment post also carries an attribution marker")

print("\n=== 6. drift HALTS — and an in-memory copy would NOT have caught it ===")
drifted = mtext.replace(".", ".", 1)
drifted = drifted[:-1] + "!" if drifted.endswith(".") else drifted + " "
try:
    C.compose(moment_text=drifted, moment_id=mid, linking_line="x")
    ok(False, "drifted moment text raised MomentTextMismatch")
except C.MomentTextMismatch:
    ok(True, "one-character drift raises MomentTextMismatch (HALT)")
# prove the comparison is against DISK: point at a file whose text differs
alt = Path(tempfile.mkdtemp()) / "m.json"
d2 = json.loads(json.dumps(d))
for entries in d2["moments"].values():
    for e in entries:
        if e["id"] == mid: e["text"] = mtext + " EDITED"
alt.write_text(json.dumps(d2))
try:
    C.compose(moment_text=mtext, moment_id=mid, linking_line="x", moments_path=alt)
    ok(False, "disk-vs-argument mismatch raised")
except C.MomentTextMismatch:
    ok(True, "compares against the FILE: unedited arg vs edited file -> HALT")
try:
    C.compose(moment_text="whatever", moment_id="m_does_not_exist")
    ok(False, "unknown moment id raised")
except C.MomentTextMismatch:
    ok(True, "unknown moment id -> HALT, never silent pass")

print("\n=== 6b. composing the fact RECORD instead of post_text HALTs ===")
rec = None
for entries in d["moments"].values():
    for e in entries:
        if e.get("id") == mid: rec = e["text"]
try:
    C.compose(moment_text=rec, moment_id=mid, linking_line="x")
    ok(False, "posting `text` raises")
except C.MomentTextMismatch:
    ok(True, "the long-form verified record can never ship by accident")

print("\n=== 7. a failed linking line is DROPPED, not fatal ===")
p1 = C.compose(moment_text=mtext, moment_id=mid, linking_line=None)
ok(mtext in p1 and attr_passes(p1), "moment + card with no linking line is a complete post")

print("\n" + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAILURE(S): {FAILS}"))
sys.exit(1 if FAILS else 0)
