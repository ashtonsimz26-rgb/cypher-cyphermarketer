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

PROVIDER (v1.2 ruling, 2026-09-09)
  * PRIMARY: OpenAI Images, gpt-image-2.5-flare, quality medium. Cost is
    COMPUTED PER IMAGE from the response's `usage` tokens x the published
    per-1M rates and written to the ledger, so the $1/day breaker counts real
    dollars instead of a guessed constant.
  * FALLBACK: xAI grok-imagine-image-2.0 @ a flat $0.04, kept for one cycle.
    Selected when OPENAI_API_KEY is absent, or after an OpenAI 5xx/network
    failure. A 4xx is NOT retried on xAI -- that means OUR request is wrong,
    and silently succeeding elsewhere would hide the bug.
"""
from __future__ import annotations
import argparse, json, re, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import x_client as X  # noqa: E402
import card_render as CR  # noqa: E402

# ── xAI (FALLBACK) ──────────────────────────────────────────────────────────
ENDPOINT = "https://api.x.ai/v1/images/generations"
MODEL = "grok-imagine-image-2.0"
COST_PER_IMAGE = 0.04                    # flat; xAI path only
# xAI-supported aspect ratios (422s on anything else — 4:5 is NOT among them):
SUPPORTED_ASPECTS = ("1:1","3:4","4:3","9:16","16:9","2:3","3:2","1:2","2:1","auto")

# ── OpenAI Images (PRIMARY) ─────────────────────────────────────────────────
# Request/response contract: https://developers.openai.com/api/docs/api-reference/images/create
# Rates + quality set:       https://developers.openai.com/api/docs/models/gpt-image-2.5-flare
# Both retrieved 2026-09-08.
OPENAI_ENDPOINT = "https://api.openai.com/v1/images/generations"
# PINNED DELIBERATELY. A floating alias can shift output style under an
# unattended cron job with no code change and no ledger signal — the drift
# would first surface as Ashton rejecting proposals for reasons nobody can
# trace. Unpinning is a ruling, not a maintenance edit.
OPENAI_MODEL = "gpt-image-2.5-flare-2026-09-08"
OPENAI_QUALITY = "medium"                # low|medium|high|xhigh|max|auto

# Published per-1M-token rates, gpt-image-2.5-flare, 2026-09-08. Snapshotted
# into every ledger record so a historical cost can be re-derived even after
# the published rates move.
RATE_IMAGE_OUT_PER_M = 30.00
RATE_TEXT_IN_PER_M = 5.00
RATE_IMAGE_IN_PER_M = 8.00

# OpenAI takes an explicit WIDTHxHEIGHT, not a ratio. Every value below is
# divisible by 16 and inside the documented 1:3–3:1 / 3840px bounds. 4:5 and
# 16:9 are generated NATIVELY here — the crop-a-3:4 workaround is retired.
SIZE_FOR_ASPECT = {"3:4": "1152x1536", "4:5": "1088x1360", "16:9": "1536x864"}

# Used ONLY when a 200 carries no usage object. Deliberately pessimistic: a
# generated image must never be ledgered at $0, or the daily breaker goes blind
# to real spend.
COST_FALLBACK_USD = 0.25
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

# ★ BRAND_LOOK IS RETIRED (2026-09-16). It was a global colour instruction and it
# made fourteen different stories look like one. Its replacement is STAGE_RULE,
# which says nothing about colour. Kept bound and EMPTY so any caller that still
# concatenates it is harmless rather than broken — and so this note is findable.
BRAND_LOOK = ""

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


# ══ STORY-DRIVEN SCENES (E2, 2026-09-16) ═══════════════════════════════════════
#
# ★★ THE PROMPT IS ASSEMBLED ONLY FROM STRINGS IN THIS FILE.
#
# That sentence is the whole answer to "how do you stop a story smuggling a brand
# mark into the prompt". No code path copies dossier fact text, a colorway, a
# collab partner or a catalog name into a prompt. A hook fact is read to CHOOSE a
# key; the key selects a stem that was written here, by hand, in advance. A
# Supreme shoe cannot produce a box logo on a wall because the word "Supreme"
# never reaches the model — only the stem `downtown_ny_2000s` does, and that stem
# describes a street, not a storefront.
#
# The alternative — asking a model to turn the fact into a scene brief — would be
# richer and would put brand names in the prompt by construction. Rejected.
#
# Two further guarantees, because one mechanism is not a rail:
#   * NEGATIVE_CONSTRAINTS is still concatenated structurally in build_prompt().
#   * assert_no_brand() re-scans the FINISHED prompt against a denylist and falls
#     back to the category scene rather than shipping a suspect prompt.
#
# Adding a STORY_VOCAB entry is a content decision with the same discipline as
# moments.json: the PATTERN may name a brand (it is matched against a fact, never
# emitted); the STEM may never contain a proper noun of any kind.

# (compiled pattern key, story key) — matched against the HOOK FACT's text only.
# Order matters: first match wins, so the specific precedes the general.
STORY_VOCAB = (
    (r"chinese new year|lunar new year|year of the", "lunar_new_year"),
    (r"\bolympic|team usa|\bgold medal", "olympic_podium"),
    (r"grateful dead|dead\b.{0,12}\btour|psychedelic", "psychedelic_venue"),
    (r"\bpigeon\b|lower east side|\bL\.?E\.?S\.?\b|riot", "downtown_ny_2000s"),
    (r"supreme|skate shop|downtown manhattan|\bnyc\b|new york", "downtown_ny_2000s"),
    (r"\bbanned\b|fined|league.{0,15}(ban|rule)", "locker_tunnel"),
    (r"hospital|charit|foundation|proceeds|doernbecher", "quiet_atrium"),
    (r"friends and family|player exclusive|\bPE\b|never released|unreleased", "vault_room"),
    (r"\bparis\b|\bmilan\b|\brunway\b|fashion week|luxury", "atelier_night"),
    (r"\btokyo\b|\bjapan|harajuku|shibuya", "tokyo_backstreet"),
    (r"\bmarathon\b|\btrack\b|\brunner|\bracing\b", "dawn_track"),
    (r"\bskate\b|skateboard|\bSB\b", "skate_basement"),
    (r"\bcourt\b|\bNBA\b|playoff|finals|dunk contest", "arena_tunnel"),
    (r"summer|beach|surf|\bmiami\b|\bLA\b|los angeles", "sunbleached_lot"),
    (r"winter|snow|\bcold\b|storm", "snowlit_street"),
)

# ══ THE STAGE RULE — the ONLY thing every scene shares ═══════════════════════
#
# BRAND_LOOK used to append "deep near-black base, cyan and violet accent
# lighting" to all fourteen stems, so every story came out the same purple-black
# wet alley — a month of them. It also contradicted the four stems that specify
# daylight outright, and on a provider that follows instructions closely
# (gpt-image) the brand line won and a "winter morning" rendered as neon night.
#
# So colour is gone from the global. What survives is the one thing that is true
# of every scene regardless of look: THE CARD IS THE SUBJECT AND THE SCENE IS A
# STAGE. The card needs somewhere to sit.
#
# ★ THE CLEAR ZONE IS MEASURED, NOT GUESSED. research/composition.placements()
# was evaluated for every composition at 4:5: the vertical band from 38% to 60%
# of frame height is covered by EVERY one of them. That centre band — not the
# lower third — is what must stay open.
STAGE_RULE = (
    "Composition: the middle of the frame is the stage. Keep the central third "
    "open, unobstructed and evenly lit, with no object crossing it and no bright "
    "highlight competing there — a product will be placed in that space. Shoot it "
    "as a real photograph: physically plausible light, natural materials, no "
    "illustration, no 3D-render look, no vignette burned into the corners."
)

# story key -> ONE COMPLETE LOOK. Place, time of day, palette, light quality,
# atmosphere. Hand-written, no proper nouns, and deliberately spread: if two of
# these read the same at a glance, one of them is wrong.
STORY_SCENES = {
    # ── night, warm, saturated ──────────────────────────────────────────────
    "lunar_new_year":
        "a narrow temple courtyard at night, strung with paper lanterns. Palette "
        "deep red and gold on wet grey stone. Light comes only from the lanterns — "
        "warm, low, pooling. Incense smoke drifts at knee height. Dense, festive, "
        "intimate.",
    "psychedelic_venue":
        "the empty floor of a small music hall an hour after the show, scuffed "
        "warm wood underfoot. Palette saturated orange, magenta and amber. Light "
        "is a hot stage wash from high above, thick in the haze. Loud, warm, "
        "spent.",
    "atelier_night":
        "a high-ceilinged workroom at night, worn parquet and long empty tables. "
        "Palette amber, ivory and dust. Light is one tungsten work lamp and "
        "nothing else, falling off fast into brown shadow, dust hanging in the "
        "beam. "
        "Quiet, close, hand-made.",
    # ── night, cool ─────────────────────────────────────────────────────────
    "tokyo_backstreet":
        "a very narrow back alley at night, tangled cables overhead, wet asphalt "
        "underfoot. Palette electric cyan and magenta against black. Light is "
        "mixed neon and vending-machine glow from both walls at once. Tight, "
        "buzzing, close.",
    "snowlit_street":
        "an empty residential street under fresh deep snow at night. Palette "
        "sodium orange pooling on blue-white snow. Light is one streetlamp and the "
        "snow's own glow; everything beyond is dark. Silent, cold, still.",
    "arena_tunnel":
        "a wide concrete players' tunnel at night, opening at the far end onto a "
        "lit hardwood floor. Palette near-black green concrete with a single warm "
        "amber rectangle of spill at the mouth. Light is entirely at the far end. "
        "Held breath, anticipation.",
    # ── interior, no weather ────────────────────────────────────────────────
    "locker_tunnel":
        "a narrow corridor of painted cinderblock, one caged fluorescent overhead. "
        "Palette institutional green-white and chalky grey. Light is a single hard "
        "source directly above with fast falloff and a hard shadow line. Severe, "
        "airless, disciplinary.",
    "vault_room":
        "a low-ceilinged private strongroom, wider than it is deep, seen square "
        "from one side — a shallow room, not a corridor. Brushed steel drawer "
        "banks fill the wall behind, the ceiling close overhead. Palette cool "
        "neutral grey, no colour cast at all. Light is even and shadowless from a "
        "recessed perimeter strip. Clinical, precise, expensive, airless.",
    "skate_basement":
        "a raw concrete basement with a plywood quarter-pipe pushed against one "
        "wall. Palette grey concrete, tan plywood, black scuff. Light is harsh "
        "midday daylight falling through a single street hatch, everything else in "
        "shadow. Dusty, plain, unglamorous.",
    # ── daylight ────────────────────────────────────────────────────────────
    "quiet_atrium":
        "a broad empty atrium in mid-morning, pale terrazzo underfoot and tall "
        "glass on one side. Palette white, pale oak and deep planting green. Light "
        "is soft diffused daylight, generous and shadow-free. Calm, airy, "
        "unhurried.",
    "olympic_podium":
        "an empty stadium infield under heavy overcast, banks of dark unlit "
        "floodlights above. Palette bleached white, wet concrete grey and cold "
        "steel. Light is flat, broad and sourceless. Vast, ceremonial, waiting.",
    "downtown_ny_2000s":
        "a working city side street on a winter morning, roll-down shutters and "
        "scaffolding, steam from a grate. Palette drab brown brick, grey slush and "
        "dull sodium. Light is flat overcast daylight, no sun, no neon whatsoever. "
        "Plain, documentary, unstyled.",
    "dawn_track":
        "an outdoor running track at first light, mist lying flat across the "
        "lanes. Palette deep oxblood-red rubber under pale lavender-blue sky. "
        "Light is a low cold sun raking from one side, long shadows. Crisp, empty, "
        "early.",
    "sunbleached_lot":
        "a cracked empty parking lot at golden hour, dry palms far in the "
        "background. Palette bleached tan asphalt and hot amber light. Sun is low "
        "and harsh, shadows long and hard-edged. Dry, still, baked.",
}

# ══ R4 — STEMS THAT MUST BE INSPECTED AT FULL RESOLUTION ═════════════════════
#
# NEGATIVE_CONSTRAINTS forbids logos, lettering and readable marks, and a
# generated image obeys it at a RATE, not absolutely. Some scenes are far more
# likely to produce a mark than others: anywhere the scene implies printed
# surfaces — packaging on a shelf, signage on a storefront, apparel, a screen —
# is a place a mark can form, and at thumbnail size a resolving label and an
# abstract colour block look identical.
#
# ★ THE FAILURE THIS PREVENTS IS A REVIEWER SAYING "looks clean" FROM A CONTACT
# SHEET. tokyo_backstreet's vending machines were checked at full resolution on
# 2026-09-16 and the bottle labels were non-resolving colour — but that is a
# statement about ONE render, not about the stem. A different seed can resolve
# one, so the stem carries the warning, not the image.
#
# Add a stem here whenever its text implies printed surfaces. The test in
# tests/test_story_scenes.py fails if a stem mentions one of the risk nouns and
# is NOT listed, so this cannot quietly fall behind the stems.
INSPECT_CLOSELY = {
    "tokyo_backstreet": "vending-machine bottles and cans — product labels can "
                        "resolve into readable marks; zoom the machine banks",
    "downtown_ny_2000s": "storefront shutters and awnings — signage can resolve; "
                         "zoom the shopfronts and the scaffolding banners",
    "psychedelic_venue": "stage backline — amp cabinets and drum heads are where "
                         "an instrument brand appears; zoom the stage",
    "skate_basement": "plywood ramp and wall — stickers and graffiti tags can "
                      "resolve into lettering; zoom the ramp face",
    "vault_room": "safe-deposit drawer fronts carry recessed card-holder plates, "
                  "which is where box NUMBERING sits on a real one; zoom the side "
                  "walls. Checked 2026-09-16: abstract, no digits — but that is "
                  "one render, and the plates are a standing invitation",
}
# Nouns that mean a stem needs a listing. Kept beside the list so the test can
# hold them together as the stems change.
#
# ★ MATCHED WORD-BOUNDED, and that is not pedantry: the first version used plain
# substrings and flagged atelier_night and snowlit_street, because "amp" is
# inside "lamp" and "streetlamp". A watch list that cries wolf on two safe stems
# is one a reviewer learns to ignore, which is worse than not having it.
#
# ★★ THE LIMIT, STATED SO NOBODY MISTAKES THIS FOR COMPLETENESS. This catches
# stems that ANNOUNCE a printed surface. It cannot catch a stem that implies one
# without naming it, because that requires knowing what a thing looks like in
# the world rather than what a word is.
#
#   vault_room named "drawer banks" and passed clean. Safe-deposit drawer fronts
#   carry recessed card-holder plates, which is exactly where box NUMBERING
#   sits — so the scene invites lettering while naming nothing that sounds like
#   lettering. It reached the list because a human looked at a render, not
#   because this function fired. `drawer` was added AFTER the fact.
#
# So: the guard is a floor, not a ceiling. It stops the list silently falling
# behind stems that say the quiet part; it does not make the list complete, and
# a new stem still deserves one full-resolution look before anyone trusts it.
PRINTED_SURFACE_NOUNS = ("vending", "shutter", "shutters", "awning", "awnings",
                         "signage", "sign", "signs", "amp", "amps", "drum",
                         "drums", "packaging", "label", "labels", "poster",
                         "posters", "billboard", "screen", "screens", "sticker",
                         "stickers", "jersey", "banner", "banners",
                         "storefront", "storefronts", "shopfront", "graffiti",
                         "drawer", "drawers", "plate", "plates", "plaque")


def printed_surface_nouns_in(text: str) -> list[str]:
    """Which risk nouns a stem names, matched as WHOLE WORDS."""
    low = (text or "").lower()
    return [w for w in PRINTED_SURFACE_NOUNS
            if re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(w), low)]


def inspection_note(scene_key: str | None) -> str:
    """The extra warning a reviewer needs, or "" — appended to the digest note."""
    r = INSPECT_CLOSELY.get(scene_key or "")
    return (" ⚠️ ZOOM BEFORE APPROVING: %s" % r) if r else ""


# Belt and braces on top of the structural guarantee. Matched against the
# FINISHED prompt; a hit means something reached it that never should have.
BRAND_TOKENS = (
    "nike", "jordan", "adidas", "yeezy", "puma", "reebok", "asics", "converse",
    "vans", "balenciaga", "supreme", "off-white", "travis scott", "cactus jack",
    "clot", "stussy", "staple", "swoosh", "jumpman", "three stripes", "new balance",
    "louis vuitton", "dior", "fragment", "sacai", "union", "kith", "bape",
)


class BrandLeak(AssertionError):
    """A brand token reached a finished prompt. Never suppressed silently."""


def assert_no_brand(prompt: str) -> None:
    low = prompt.lower()
    # NEGATIVE_CONSTRAINTS legitimately says "no swooshes" etc., so scan only the
    # part of the prompt the story can influence.
    scene_part = low.split("absolute constraints:")[0]
    hit = [t for t in BRAND_TOKENS if t in scene_part]
    if hit:
        raise BrandLeak("brand token(s) reached the prompt: %s" % ", ".join(hit))


# ★ story_key() MOVED to research/story.py (E5). It is the one function that had
# to read fact text, so it does not live in the module that builds prompts. What
# stays here is the VOCABULARY it matches against and the hand-written stems —
# data, not a door.
HOOKABLE_FOR_SCENE = frozenset({"collab_origin", "cultural_moment", "release_drama",
                                "price_reason", "designer"})


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ledger(rec: dict):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(rec); rec.setdefault("ts", now())
    with LEDGER.open("a", encoding="utf-8") as fh:      # append-only
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _era(row: dict) -> str:
    year = row.get("year")
    if isinstance(year, int):
        if year < 2000:
            return " Late-90s period feel, warm tungsten light, slight haze."
        if year < 2010:
            return " Mid-2000s period feel, cooler fluorescent tones."
    return ""


def scene_for(row: dict, scene_key: str | None = None) -> tuple[str, str, str]:
    """(scene text, source, "").

    ★★ E5, 2026-09-16: THIS TAKES A KEY, NOT A FACT. Previously it accepted the
    hook TEXT and re-derived the key here. The fact never reached the prompt
    even then — but it reached this MODULE, and "we are careful with it" is a
    weaker guarantee than "there is no parameter it can arrive in". There is now
    no parameter it can arrive in. A test asserts that by AST, the same way the
    set_completion branch is asserted never to touch `frag`.

    The key is chosen by research/story.py from the fact the WRITER says it used,
    so the image and the lead are composed from one fact by construction rather
    than by two selectors happening to agree.

    ★ E2, 2026-09-16: THE STORY DECIDES, and the category is the FALLBACK.
    Before this, the scene came from row["category"] and row["year"] and nothing
    else — six stems of which two were byte-identical, so a CLOT Chinese New Year
    shoe and a Supreme SB got the same purple night street, every day. The
    dossier held the story and this module had never read it.

    source is one of: "story" (a hook fact matched the curated vocabulary),
    "category" (no story signal — the old behaviour, unchanged), "default".
    """
    if scene_key and scene_key in STORY_SCENES:
        # ★ NO _era() HERE. Each stem now declares its own time of day and
        # palette; appending "Late-90s period feel, warm tungsten light" on top
        # would reintroduce exactly the global-override problem BRAND_LOOK had,
        # one layer down. The era still shapes the CATEGORY fallback below,
        # which carries no time of day of its own.
        return STORY_SCENES[scene_key], "story:%s" % scene_key, ""
    cat = (row.get("category") or "").strip()
    if cat in SCENES:
        return SCENES[cat] + _era(row), "category:%s" % cat, ""
    return DEFAULT_SCENE + _era(row), "default", ""


def build_prompt(row: dict, scene_key: str | None = None) -> str:
    """NEGATIVE_CONSTRAINTS is concatenated HERE, structurally — never left to a
    caller to remember. assert_no_brand then re-reads the finished string and
    falls back to the category scene rather than shipping a suspect prompt."""
    scene, source, _why = scene_for(row, scene_key)
    prompt = "%s %s %s" % (scene, STAGE_RULE, NEGATIVE_CONSTRAINTS)
    try:
        assert_no_brand(prompt)
    except BrandLeak as e:
        ledger({"event": "brand_leak_blocked", "source": source, "error": str(e)})
        scene, source, _why = (SCENES.get((row.get("category") or "").strip(),
                                          DEFAULT_SCENE) + _era(row), "category_fallback", "")
        prompt = "%s %s %s" % (scene, STAGE_RULE, NEGATIVE_CONSTRAINTS)
        assert_no_brand(prompt)          # the fallback is curated too; if THIS
                                         # leaks, something is very wrong — raise
    return prompt


def prompt_source(row: dict, scene_key: str | None = None) -> str:
    """The source label, for the ledger and the digest note."""
    return scene_for(row, scene_key)[1]


def _openai_cost(usage: dict | None) -> tuple[float, str | None]:
    """Real dollars from the response's own token counts.

    A 200 with no usage object must NOT be ledgered at $0 — that would make the
    daily breaker blind to spend that actually happened. Fall back high instead.
    """
    if not usage:
        return COST_FALLBACK_USD, "usage_missing"
    d = usage.get("input_tokens_details") or {}
    cost = (float(usage.get("output_tokens") or 0) * RATE_IMAGE_OUT_PER_M
            + float(d.get("text_tokens") or 0) * RATE_TEXT_IN_PER_M
            + float(d.get("image_tokens") or 0) * RATE_IMAGE_IN_PER_M) / 1e6
    return round(cost, 6), None


def _generate_openai(prompt: str, aspect: str, out: Path, env: dict) -> dict:
    """OpenAI Images path. Raises _OpenAIServerError on 5xx/network so the
    caller can fall back; die()s on 4xx, which means our request is wrong."""
    if aspect not in SIZE_FOR_ASPECT:
        X.die("aspect %r unsupported by provider openai; use one of %s"
              % (aspect, ", ".join(sorted(SIZE_FOR_ASPECT))))
    size = SIZE_FOR_ASPECT[aspect]
    body = {"model": OPENAI_MODEL, "prompt": prompt, "n": 1, "size": size,
            "quality": OPENAI_QUALITY, "output_format": "png",
            # The backdrop is ALWAYS composited under a card. A transparent
            # background would produce a broken composite that nothing
            # downstream inspects before it reaches Telegram.
            "background": "opaque"}
    req = urllib.request.Request(OPENAI_ENDPOINT, data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer %s" % env["OPENAI_API_KEY"],
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            status, raw = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read().decode()
    except Exception as e:
        raise _OpenAIServerError("transport:%s" % type(e).__name__)

    if status >= 500:
        raise _OpenAIServerError("http_%d:%s" % (status, raw[:200]))
    if status != 200:
        ledger({"event": "generation_failed", "provider": "openai",
                "model": OPENAI_MODEL, "aspect": aspect, "size": size,
                "http": status, "error": raw[:300], "cost_usd": 0.0})
        X.die("OpenAI generation failed (HTTP %s): %s" % (status, raw[:300]))

    j = json.loads(raw)
    item = j["data"][0]
    usage = j.get("usage")
    cost, detail = _openai_cost(usage)
    rec = {"event": "generated", "provider": "openai", "model": OPENAI_MODEL,
           "quality": OPENAI_QUALITY, "size": size, "aspect": aspect,
           "cost_usd": cost, "output": str(out), "prompt": prompt,
           "revised_prompt": item.get("revised_prompt"),
           "usage": usage, "rate_snapshot": {
               "image_out_per_m": RATE_IMAGE_OUT_PER_M,
               "text_in_per_m": RATE_TEXT_IN_PER_M,
               "image_in_per_m": RATE_IMAGE_IN_PER_M},
           "inspection": "PENDING"}
    if detail:
        rec["detail"] = detail
    # Charged at the 200 — ledger HERE, before the decode can fail.
    ledger(rec)

    if item.get("b64_json"):
        import base64
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(item["b64_json"]))
    elif item.get("url"):
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(item["url"], timeout=300) as r:
                out.write_bytes(r.read())
        except Exception as ex:
            ledger({"event": "download_failed", "provider": "openai",
                    "output": str(out), "error": type(ex).__name__,
                    "note": "spend already ledgered above"})
            X.die("image generated (charged) but download failed: %s" % type(ex).__name__)
    else:
        X.die("no image payload in response: %s" % str(item)[:200])
    return dict(rec)


class _OpenAIServerError(RuntimeError):
    """OpenAI failed in a way that is plausibly transient — fall back to xAI."""


def generate(prompt: str, aspect: str, out: Path, env: dict) -> dict:
    """Provider dispatcher. Signature and return contract unchanged.

    Key ABSENT is a configuration choice, not a failure: it selects xAI
    directly and writes NO provider_fallback record. Only a real OpenAI
    5xx/network failure is a fallback event worth alerting on.
    """
    if env.get("OPENAI_API_KEY"):
        try:
            return _generate_openai(prompt, aspect, out, env)
        except _OpenAIServerError as e:
            ledger({"event": "provider_fallback", "from": "openai", "to": "xai",
                    "reason": str(e)[:300], "aspect": aspect})
    if aspect not in SUPPORTED_ASPECTS:
        X.die("aspect %r unsupported by provider xai; use one of %s"
              % (aspect, ", ".join(SUPPORTED_ASPECTS)))
    return _generate_xai(prompt, aspect, out, env)


def _generate_xai(prompt: str, aspect: str, out: Path, env: dict) -> dict:
    """Unchanged xAI path. Flat $0.04. Reached when OPENAI_API_KEY is absent,
    or as the fallback after an OpenAI 5xx/network failure."""
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
