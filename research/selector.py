#!/usr/bin/env python3.12
"""
selector.py — chooses at most ONE candidate for a given day (F4.1).

★★ LANE PRECEDENCE (ruled 2026-09-10): A VERIFIED MOMENT OUTRANKS A RELEASE
   DATE ON THE SAME DAY. One shoe, one day, one proposal.

   A moment has HUMAN APPROVAL and a FETCHED SOURCE; a release date is a GOAT
   field. When both fire, the moment is the candidate and the release date may
   ride along as a SUPPORTING FACT — never as a second proposal.

   The same shape applies one level down, INSIDE the release lane: a round
   anniversary is date-driven and outranks an ordinary catalog-driven
   candidate. Found in F4.1 verify — a 25-year anniversary was losing to
   whichever narrative-hook dossier sorted first alphabetically.

   ⚠ WHY THE ANNIVERSARY PASS RETURNS EARLY — DO NOT "SIMPLIFY" IT.
   It looks like a redundant branch. It is not. Before it existed,
   select(2026-09-15) returned adidas_yeezy_boost_700_analog instead of
   aj3_mocha_og's 25th, because the general pass took the first pool-order
   match and ~136 narrative-hook dossiers outrank the 0-1 anniversary ones by
   accident of the alphabet. The anniversary rule was correctly implemented and
   completely INERT. Collapse this branch and it goes inert again.

   LESSON, banked 2026-09-10: a rule can be correctly implemented and still
   inert if an earlier selection stage resolves first. Test that the SELECTOR
   RETURNS the thing, never that the calendar CONTAINS it. The first version of
   the F4.1 suite asserted the anniversary calendar contained aj3_mocha_og —
   which was true — and passed while select() returned a different shoe.

   PATTERN, banked 2026-09-10: structural guarantees in this repo are proved by
   AST — that a shape CANNOT BE EXPRESSED — not by asserting a case does not
   occur. See the F4.1 suite: no lane returns a list/tuple/set/comprehension,
   so no lane can carry two candidates, regardless of input.

   This is enforced BY CONSTRUCTION, not by checking. select() returns from the
   moment lane before the release lane is reachable, and each lane returns at
   most one candidate. There is no merge step anywhere in this module, so there
   is no place a duplicate could survive. Do not add one.

★ MOMENT TEXT IS VERBATIM (ruled 2026-09-10)
   A verified moment's prose is the only text in this system that has passed
   HUMAN judgment against a FETCHED SOURCE. An LLM rewrite converts a verified
   fact into a paraphrase that may drift — and the truth gate CANNOT catch that
   drift, because it checks facts against sources and the paraphrase still
   traces to the same URL. So on a moment day the moment text ships
   byte-for-byte and the writer supplies ONLY a card-linking line. compose
   asserts byte-identity at output time; a mismatch is a HALT.

ELIGIBILITY IS ONE POSITIVE RULE, not a filter with an exception branch:

    eligible(dossier, day) =
           has_non_designer_hook(dossier)
        OR day_has_verified_moment(day)
        OR day_is_round_anniversary(dossier, day)

   Designer-only dossiers are excluded from the GENERAL pool because 86 of them
   collapse to 10 designer names and would produce the same noun-swap sentence
   86 times. They are eligible when the hook comes from ELSEWHERE — a verified
   moment, or a round anniversary, where the DATE is the hook and the designer
   is the payload ("39 years ago today, Tinker Hatfield cut a window into a
   midsole"). That post passes the swap test; no other shoe swaps into it.

   5-year anniversaries stay eligible; editorial gate (b)'s swap test kills the
   weak ones rather than a second threshold that would need tuning forever.
   anniversary_age is logged on every candidate so we can see empirically
   whether 5-year entries ever survive gate (b). If none do in 30 days, the
   floor moves to 10.
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DOSSIERS = HERE / "data" / "dossiers"
RELEASE_DATES = HERE / "data" / "release_dates.json"

ROUND_ANNIVERSARIES = frozenset({5, 10, 15, 20, 25, 30})

# Every key a candidate dict carries. writer._assert_selector_boundary() fails
# AT IMPORT if any of these is neither passed to the writer nor explicitly
# withheld with a reason — see the R3 notes in writer.py. Adding a field here
# without accounting for it downstream is how a rule goes inert.
SELECTOR_OUTPUT_FIELDS = frozenset({
    "lane", "day", "image_name", "moment", "moment_text", "hook_facts",
    "supporting_facts", "eligibility", "dossier_usable",
})

# Positive filter: a hook tag that can carry a post on its own. `designer` is
# deliberately ABSENT — it is a payload, not a hook, unless a date supplies one.
NARRATIVE_HOOK_TAGS = frozenset({
    "collab_origin", "cultural_moment", "release_drama", "price_reason",
})


def load_dossier(image_name: str) -> dict | None:
    p = DOSSIERS / ("%s.json" % image_name)
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def load_release_dates() -> dict:
    try:
        return json.loads(RELEASE_DATES.read_text())
    except Exception:
        return {}


def hook_tags(d: dict) -> set[str]:
    ids = set(d.get("hook_candidates") or [])
    return {f["tag"] for f in d.get("facts") or [] if f["id"] in ids}


def has_narrative_hook(d: dict) -> bool:
    return bool(hook_tags(d) & NARRATIVE_HOOK_TAGS)


def anniversary_age(image_name: str, day: date, release_dates: dict) -> int | None:
    """Round-number anniversary falling EXACTLY on `day`, else None."""
    rec = release_dates.get(image_name) or {}
    ds = rec.get("release_date")
    if not ds:
        return None
    try:
        y, m, d = (int(x) for x in ds[:10].split("-"))
    except Exception:
        return None
    if (m, d) != (day.month, day.day):
        return None
    age = day.year - y
    return age if age in ROUND_ANNIVERSARIES else None


def eligibility(image_name: str, day: date, *, dossier: dict,
                day_has_moment: bool, release_dates: dict) -> dict | None:
    """The positive rule. Returns the reason it qualifies, or None."""
    if not dossier or not dossier.get("usable"):
        return None
    age = anniversary_age(image_name, day, release_dates)
    if has_narrative_hook(dossier):
        return {"reason": "narrative_hook", "anniversary_age": age}
    if day_has_moment:
        return {"reason": "moment_day", "anniversary_age": age}
    if age is not None:
        return {"reason": "round_anniversary", "anniversary_age": age}
    return None                                  # designer-only, ordinary day


def _supporting_release_fact(image_name: str, release_dates: dict) -> dict | None:
    rec = release_dates.get(image_name) or {}
    if not rec.get("release_date"):
        return None
    return {"tag": "release_date", "text": "Released %s." % rec["release_date"],
            "source": {"kind": "release_dates", "ref": image_name}}


def _moment_lane(day: date, moments_mod, moments_path, reachable,
                 release_dates: dict) -> dict | None:
    """At most ONE moment candidate. The release lane never runs after this."""
    key = "%02d-%02d" % (day.month, day.day)
    entries = moments_mod.proposable(key, moments_path, reachable)
    if not entries:
        return None
    m = entries[0]                               # one day, one proposal
    image_name = (m.get("linked_image_names") or [None])[0]
    dossier = load_dossier(image_name) if image_name else None
    supporting = []
    if image_name:
        f = _supporting_release_fact(image_name, release_dates)
        if f:
            supporting.append(f)                 # supporting FACT, not a candidate
    return {"lane": "moment", "day": key, "image_name": image_name,
            "moment": m,                          # post_text used VERBATIM downstream
            "moment_text": m["post_text"],        # NOT `text` — that is the fact record
            "hook_facts": [],                     # writer supplies a linking line only
            "supporting_facts": supporting,
            "eligibility": {"reason": "verified_moment", "anniversary_age": None},
            "dossier_usable": bool(dossier and dossier.get("usable"))}


def _build(image_name: str, d: dict, el: dict, day: date,
           release_dates: dict) -> dict:
    ids = set(d["hook_candidates"])
    hooks = [f for f in d["facts"] if f["id"] in ids]
    supporting = []
    f = _supporting_release_fact(image_name, release_dates)
    if f:
        supporting.append(f)
    lane = "anniversary" if el["reason"] == "round_anniversary" else "general"
    return {"lane": lane, "day": "%02d-%02d" % (day.month, day.day),
            "image_name": image_name, "moment": None, "moment_text": None,
            "hook_facts": hooks, "supporting_facts": supporting,
            "eligibility": el, "dossier_usable": True}


def _anniversary_pass(day: date, pool: list[str], release_dates: dict) -> dict | None:
    """★ DATE-DRIVEN OUTRANKS CATALOG-DRIVEN — the same precedence shape as
    moment-over-release, one level down. Without this, a 25-year anniversary
    lost to whichever narrative-hook dossier happened to sort first
    alphabetically, and the anniversary rule would never have surfaced a post.
    Highest age wins when a day carries more than one."""
    hits = []
    for image_name in pool:
        age = anniversary_age(image_name, day, release_dates)
        if age is None:
            continue
        d = load_dossier(image_name)
        if not d or not d.get("usable"):
            continue
        hits.append((age, image_name, d))
    if not hits:
        return None
    age, image_name, d = max(hits, key=lambda h: h[0])
    return _build(image_name, d, {"reason": "round_anniversary",
                                  "anniversary_age": age}, day, release_dates)


def _release_lane(day: date, pool: list[str], release_dates: dict) -> dict | None:
    """At most ONE candidate. Anniversary pass first; the general pass is not
    reachable when it fires — same construction guarantee as the moment lane."""
    anniv = _anniversary_pass(day, pool, release_dates)
    if anniv is not None:
        return anniv                             # <- general pass NOT reachable
    for image_name in pool:
        d = load_dossier(image_name)
        el = eligibility(image_name, day, dossier=d, day_has_moment=False,
                         release_dates=release_dates)
        if not el:
            continue
        return _build(image_name, d, el, day, release_dates)
    return None


def select(day: date, pool: list[str], *, moments_mod=None, moments_path=None,
           reachable=None, release_dates: dict | None = None) -> dict | None:
    """AT MOST ONE candidate for `day`. Moment lane first; if it fires, the
    release lane is unreachable — that is the collision guarantee."""
    if moments_mod is None:
        from research import moments as moments_mod          # noqa: PLC0415
    release_dates = load_release_dates() if release_dates is None else release_dates

    moment = _moment_lane(day, moments_mod, moments_path, reachable, release_dates)
    if moment is not None:
        return moment                            # <- release lane NOT reachable
    return _release_lane(day, pool, release_dates)


def anniversary_calendar(pool: list[str], start: date, days: int = 365) -> list[dict]:
    """Every round anniversary in the window. Used for reporting and tests."""
    from datetime import timedelta
    rd = load_release_dates()
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        for image_name in pool:
            age = anniversary_age(image_name, d, rd)
            if age is not None:
                out.append({"date": d.isoformat(), "image_name": image_name, "age": age})
    return out
