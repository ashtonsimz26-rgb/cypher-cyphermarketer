#!/usr/bin/env python3.12
"""
story.py — fact text in, scene KEY out (E5).

★★ THIS IS THE ONLY MODULE THAT READS A FACT AND TALKS ABOUT SCENES, and it
returns a KEY. backdrop.py holds the vocabulary and the hand-written stems but
has no function that accepts fact text any more, so the guarantee E2 stated —
the fact never enters the image prompt — stopped depending on discipline and
became a property of the call graph. backdrop.scene_for(row, scene_key) has no
parameter a fact could arrive in, asserted by AST in tests/test_story_scenes.py.

THE BRIEF. detect_hook picks a fact and the WRITER picks a fact, and before E5
nothing made those the same one: the image could be about a collab while the
lead was about a stash pocket, both true, both about the same shoe, and not
about the same thing. The writer now returns the id of the fact it wrote from
and the scene is composed from THAT fact. One brief, two outputs.

The writer choosing is deliberate. detect_hook applies a tag-priority rule; the
model can see which fact will actually carry a sentence. Following the model's
choice costs nothing, because the backdrop is generated only after the draft has
cleared gate 8 — a failed draft still spends $0.00.
"""
from __future__ import annotations
import re

from backdrop import STORY_VOCAB, STORY_SCENES, HOOKABLE_FOR_SCENE

_STORY_RX = tuple((re.compile(p, re.I), k) for p, k in STORY_VOCAB)


def key_for_text(text: str | None) -> str | None:
    """The scene key a single fact implies, or None. First match wins."""
    if not text:
        return None
    for rx, key in _STORY_RX:
        if rx.search(text):
            return key
    return None


def fact_by_id(dossier: dict | None, fact_id: str | None) -> dict | None:
    if not dossier or not fact_id:
        return None
    for f in dossier.get("facts") or []:
        if f.get("id") == fact_id:
            return f
    return None


def fallback_fact(dossier: dict | None) -> dict | None:
    """The first hookable fact, used when the writer named none we can trust."""
    for f in (dossier or {}).get("facts") or []:
        if f.get("tag") in HOOKABLE_FOR_SCENE and key_for_text(f.get("text")):
            return f
    return None


# ── divergence heuristic (R2) ───────────────────────────────────────────────
# NOT proof and NOT a gate. A lead sharing zero distinctive tokens with the fact
# it claims to be built on is worth SEEING in a week's data; it is not worth
# blocking a post over, and it is certainly not worth a second LLM call.
_STOP = frozenset("""a an the and or of in on at to for from with by is was were
be been being as its it this that these those his her their our your my one two
three new first only more most very just also than then when where which who
what how why all any each both few many some such no nor not own same so too can
will would could should may might must have has had do does did""".split())


def distinctive(text: str | None) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'\-]{2,}|\d{2,}", text or "")
    return {w.lower() for w in words if w.lower() not in _STOP}


def shared_tokens(lead: str | None, fact_text: str | None) -> int:
    """How many distinctive tokens the lead and its claimed fact share."""
    return len(distinctive(lead) & distinctive(fact_text))


def brief(dossier: dict | None, fact_id: str | None,
          lead: str | None = None) -> dict:
    """Resolve the writer's claim into a scene key, loudly.

    Returns {scene_key, fact_id, fact_tag, source, fallback_fired, shared_tokens}.
    `source` is "writer" when the model's own fact produced the key, "fallback"
    when it did not and the first hookable fact did, "none" when neither did.
    """
    f = fact_by_id(dossier, fact_id)
    key = key_for_text((f or {}).get("text"))
    if f is not None and key:
        return {"scene_key": key, "fact_id": f.get("id"), "fact_tag": f.get("tag"),
                "source": "writer", "fallback_fired": False,
                "shared_tokens": shared_tokens(lead, f.get("text"))}
    fb = fallback_fact(dossier)
    if fb is not None:
        return {"scene_key": key_for_text(fb.get("text")), "fact_id": fb.get("id"),
                "fact_tag": fb.get("tag"), "source": "fallback",
                "fallback_fired": True,
                "shared_tokens": shared_tokens(lead, fb.get("text"))}
    return {"scene_key": None, "fact_id": None, "fact_tag": None,
            "source": "none", "fallback_fired": True, "shared_tokens": 0}
