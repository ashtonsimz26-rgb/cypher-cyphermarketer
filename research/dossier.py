#!/usr/bin/env python3.12
"""
dossier.py — deterministic fact extraction from GOAT snapshots (D1).

NO LLM. Every fact is EXTRACTED from a field already on disk, never invented and
never embellished. A fact whose text carries a claim absent from its source is a
defect, not a style choice. If the source sentence is dull, the fact is dull.

★ THE NAME-CONSISTENCY GATE — why it exists
    A misattributed fact passes the entire truth gate: every fact traces to a
    real source, the source is real, the gate is satisfied, and the post is
    still FALSE — because nothing verifies the source is about the SAME SHOE.
    Found in D1 GROUND: `nike_air_foamposite_one_wu_tang` carries a GOAT story
    that describes the 'Optic Yellow', never mentioning Wu-Tang. F4's truth gate
    structurally cannot catch that, so it closes here, fail-closed, before any
    fact is emitted.

    Signal 1 SILHOUETTE — the catalog silhouette must appear in GOAT's name or
      story as a word-bounded phrase. Same discipline as the RSS silhouette fix
      after Goadome -> Humara matched on a bare token.
    Signal 2 COLORWAY  — at least one DISTINCTIVE colorway/name token must
      appear in the story. Generic tokens corroborate nothing and are stripped.

    both      -> "confirmed"        facts emitted normally
    sil only  -> "silhouette_only"  ONLY designer / release_date / spec facts;
                 story-derived facts DROPPED, so no hook can come from prose we
                 cannot tie to this card
    no sil    -> "failed"           usable=false, ZERO story-derived facts

    The snapshot is never edited. It is a faithful record of what GOAT returned;
    the dossier is where judgment is applied (capture vs interpretation).

    ★★ LOCKED INVARIANT — SIGNAL PRECEDENCE. DO NOT "SIMPLIFY".
    Signal 3 (year) rescues ABSENCE of evidence only; it may NEVER override
    NEGATIVE evidence. It applies if and only if signal 2 is "unavailable" —
    never when signal 2 is "fail". nike_air_foamposite_one_wu_tang is the proof:
    its years agree (2016 == 2016), so any code path that let signal 3 outrank a
    failed signal 2 would silently recover the exact misattribution this gate
    was built to stop. If you are tempted to collapse the three-way signal 2
    into a boolean, this is why you must not.

    ⚠ WATCH ITEM (2026-09-10). Signal 3 has confirmed 11 of 11 and held back 0.
    It is carrying 11 dossiers on a signal that has never once said no, so it is
    not yet discriminating on this data. If a later rebuild still shows it at
    100% pass, it is decoration: give it teeth or remove it.

PRICE: `retail_price_cents` is the ONLY price field in a snapshot and is NEVER
read. Prose carries no currency at all (verified across 250 files, 0 hits).
Price claims belong to PK and rails.py alone.

★★ FACT-LEVEL SENSITIVITY — A FACT THE WRITER CAN NEVER SEE (R1, 2026-09-12)
    Some facts are true, verified, on-topic, and must still never reach a
    generator. aj13_doernbecher's best-scoring support fact is a named
    11-year-old's daily medication count: distinctiveness double-weights
    numbers, so "the seven pills he takes per day to manage his condition"
    ranked FIRST and was handed to the writer on every single call. Four
    sampled drafts happening not to use it is luck, not a rail.

    Every fact carries `sensitivity`, default "none".
    WRITER_REACHABLE_SENSITIVITIES is a POSITIVE FILTER — a fact reaches the
    writer by MEMBERSHIP, so a value nobody anticipated is excluded BY
    CONSTRUCTION rather than by remembering to blocklist it. Same discipline as
    moments.PROPOSABLE_SENSITIVITIES and editorial.ALLOWED_FEEDBACK_CODES.

    A flagged fact is removed AT THE SOURCE: it never enters hook_candidates,
    never enters the support bucket, never enters lineage. The dossier still
    records it — the record is not censored, the REACH is.

    ★ THE FLAGS ARE HUMAN-APPROVED DATA, NEVER A REGEX. Terms only SURFACE
    candidates; data/fact_sensitivity.json carries what Ashton approved. The
    surfacing pass over 250 dossiers returned 8 candidates of which 5 were
    false positives — "given a treatment of white paint", three "low-light
    conditions", "post-game recovery". A pattern would have flagged all five.

★★ A RAIL GOES ON EVERY DOOR (R4, banked 2026-09-12)
    THE RULE: a new rail must be placed at EVERY ENTRY POINT to the candidate
    pool, and its test must prove EACH PATH SEPARATELY. The digest and the
    selector are two doors. A lock on one is not a lock.

    Concretely, today that means all four of selector.eligibility(),
    selector._anniversary_pass(), selector._moment_lane() AND
    daily_digest.build_one(). daily_digest.candidates() builds its pool
    DIRECTLY from Supabase and never calls eligibility(), so a rail written
    into the selector alone gates nothing on the path that actually runs at
    09:00 every morning.

    ★ AND IT WOULD HAVE BEEN INVISIBLE. The dossiers that needed gating clear
    the pool's `estimated_resale >= 400` filter, so they were in the pool ON
    MERIT — no error, no skipped row, no log line, nothing to notice. A green
    suite asserting "the selector refuses it" would have been TRUE AND
    IRRELEVANT. So assert the refusal on each path BY ITS OWN MECHANISM: by AST
    that the gate is the first statement of build_one, and by sampled select()
    calls that no flagged dossier is ever returned.

    This is the sixth instance of a mechanism built correctly whose information
    never reached it — see contracts.py for the first five. It is by far the
    most serious of them, because the mechanism was a child-safety rail.

★★ WHAT `spec` IS — AND WHY THAT IS THE ROOT DEFECT (R3, banked 2026-09-12)
    `spec` IS THE ELSE BRANCH. IT CLASSIFIES NOTHING BY EVIDENCE. A sentence is
    tagged spec because no story pattern matched it — never because anything
    tested it for BEING a spec. There is no materials vocabulary deciding this,
    and if you go looking for one you will find SPEC_MARKERS below and be
    misled: it is compiled, it is never read, and it has never once classified
    a sentence.

    That shape is the defect, not a detail of it. A classifier whose default
    bucket is "everything that did not match" will always accumulate whatever
    the patterns do not cover, and EVERY FUTURE PATTERN GAP LANDS THERE
    SILENTLY. That is how 89 facts naming people, collectives, events and
    origins sat in the same bucket as "a rubber outsole delivers grip", and
    nothing in the code could have told you.

    The narrative_detail tier below ROUTES part of that accumulation somewhere
    useful. It does not fix the shape, and it was not meant to. THE REAL FIX IS
    POSITIVE CLASSIFICATION FOR SPEC — a sentence should have to prove it is
    materials copy, the same way a hook has to prove it is a story, and the
    else branch should end up meaning "unclassified" rather than "spec".
    Deliberately not done here. Written down so a future session inherits the
    shape instead of rediscovering it.

★ THE narrative_detail COUNT IS UNACCOUNTED, AND STAYS THAT WAY (R5, ruled)
    The H4 proposal measured 101 of 735 facts moving and 86.3% retention. This
    implementation moves 89 and retains 87.3%. The rule here was rebuilt from
    the ruling's four categories — people, collectives, provenance, events —
    because the proposal's actual term list was never written down. Three of
    the difference is the B fixes claiming those sentences first; the remaining
    ~9 is UNRECONCILED, and deliberately so: the lists were not widened to
    reach a number. The direction is conservative. Ruled to record the gap
    rather than close it retroactively, because a count reached by tuning
    toward it is not a measurement.

★ H3 IS RETIRED (R7, ruled 2026-09-12)
    H3 was a two-shoe batch selected by "the support bucket is empty". After
    this tier airmax90_bacon_og left it — its one spec fact is narrative_detail
    now — and blazermid_off-white_grim_reaper stayed, having no spec prose at
    all to reclassify. Retired not because one shoe is too few, but because THE
    PREMISE IS GONE: support-emptiness was only ever a proxy for the writer
    being STARVED, and writer payload under 200 characters is now ZERO across
    138 usable dossiers (it is 3 without narrative_detail). blazermid hands the
    writer 391 characters across two hooks. There is nothing left to fix.
"""
from __future__ import annotations
import html, json, re, sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SNAPS = HERE / "data" / "goat_snapshots"
OUT = HERE / "data" / "dossiers"
RELEASE_DATES = HERE / "data" / "release_dates.json"
FACT_SENSITIVITY = HERE / "data" / "fact_sensitivity.json"
DOSSIER_SENSITIVITY = HERE / "data" / "dossier_sensitivity.json"

# ── tags ─────────────────────────────────────────────────────────────────────
# POSITIVE FILTER, same discipline as editorial.ALLOWED_FEEDBACK_CODES and
# format_report.GROUP_DIMENSIONS. A tag becomes hookable only by membership.
# "spec" is deliberately ABSENT: a spec is not a story. Materials, silhouette
# geometry and construction can never open a post, no matter how well written.
HOOKABLE_TAGS = frozenset({
    "collab_origin", "cultural_moment", "release_drama", "price_reason",
})
# narrative_detail is SUPPORT-ONLY and joins ALL_TAGS here and nowhere else.
# Its absence from HOOKABLE_TAGS above is the whole guarantee: a fact tagged
# narrative_detail cannot enter hook_candidates, cannot make a dossier usable,
# and cannot open a post. Do not "tidy" it into the frozenset above.
ALL_TAGS = HOOKABLE_TAGS | {"release_date", "spec", "silhouette_lineage",
                            "narrative_detail"}

# What a dossier EMITS into the pipeline (contracts.py).
DOSSIER_OUTPUT_FIELDS = frozenset({
    "hook_facts", "lineage_facts", "spec_facts", "narrative_detail_facts",
    "support_facts", "release_date_fact", "dossier_usable", "name_match",
    "fact_sensitivity", "dossier_sensitivity",
})

# ── support_facts: the THIRD BUCKET (ruled 2026-09-12) ───────────────────────
# spec facts were withheld from the writer ABSOLUTELY. That is right for HOOKS
# — a spec cannot open a post — but it was also deciding what the writer may
# KNOW, and those are different jobs. Measured across 136 usable dossiers: 156
# hook facts / 24,648 chars reached the writer while 367 spec facts / 45,036
# chars were discarded — 65% of the story prose. 94 dossiers handed the writer
# under 200 characters.
#
# The canonical case is the CLOT Chinese Candy Box: its best detail — "ditched
# the typical shoebox for a hexagonal red candy box with an interior tray" —
# was tagged spec and never reached the writer, which then had 152 characters
# to work with and produced a 98-character post. Correct behaviour on starved
# input; the starvation was self-inflicted.
#
# ★ A SUPPORT FACT CAN NEVER BECOME A HOOK. It is not in HOOKABLE_TAGS and
# never will be — same positive filter that keeps `designer` out. Support
# material may only EXTEND a lead hooked elsewhere.

# The closed vocabulary generic spec copy draws on. A sentence made mostly of
# these says nothing distinctive about THIS shoe.
GENERIC_SPEC = frozenset({
    "rubber","outsole","midsole","upper","leather","suede","mesh","tongue","collar",
    "swoosh","stripes","eyelets","laces","lining","insole","sockliner","heel","toe",
    "panel","panels","overlay","overlays","branding","logo","hits","accents","tonal",
    "premium","classic","design","designs","silhouette","low","high","mid","top",
    "shoe","sneaker","pair","colorway","white","black","red","blue","green","grey",
    "gray","cream","sail","bone","olive","navy","brown","tan","gum","featuring",
    "features","comes","dressed","finished","constructed","built","sits","atop",
    "paired","complemented","punctuated","anchoring","combines","base","cupsole",
    "sidewalls",
})
_SUPPORT_STOP = frozenset({
    "the","a","an","and","with","of","in","on","for","to","is","are","was","were",
    "its","it","this","that","by","from","as","at","also","along","into","their","has",
})
MAX_SUPPORT_FACTS = 3

# ── fact-level sensitivity (R1, ruled 2026-09-12) ────────────────────────────
# POSITIVE FILTER. DO NOT WIDEN, and do not convert to a blocklist: the point is
# that a sensitivity value nobody anticipated is unreachable by construction.
WRITER_REACHABLE_SENSITIVITIES = frozenset({"none"})
SENSITIVITY_APPROVER = "ashton"                  # the only valid approver
_FACT_SENS: dict | None = None


def _norm_text(s: str) -> str:
    """Whitespace-collapsed text — the identity a curated flag matches on.

    NOT the fact id. Ids are positional (f1, f2 ...) and shift the moment the
    tagger changes; keying a flag by id would silently move it onto a different
    sentence, which is the worst possible failure for this particular rail.
    """
    return re.sub(r"\s+", " ", (s or "")).strip()


def fact_sensitivity(image_name: str | None = None) -> dict:
    """Curated per-fact flags. LOUD on a missing file or an unapproved entry.

    Failing open here means a medical detail reaches a generator, so every
    failure mode is a raise. An unapproved entry is NOT silently skipped — that
    would leave a flag someone wrote sitting inert in the file.
    """
    global _FACT_SENS
    if _FACT_SENS is None:
        blob = json.loads(FACT_SENSITIVITY.read_text())
        out: dict[str, dict[str, str]] = {}
        for e in blob.get("facts", []):
            missing = [k for k in ("image_name", "sensitivity", "text", "approved_by")
                       if not e.get(k)]
            if missing:
                raise ValueError("fact_sensitivity.json: entry missing %s" % missing)
            if e["approved_by"] != SENSITIVITY_APPROVER:
                raise ValueError("fact_sensitivity.json: entry for %s is not approved by %s "
                                 "(found %r). The agent may never approve one."
                                 % (e["image_name"], SENSITIVITY_APPROVER, e["approved_by"]))
            if e["sensitivity"] in WRITER_REACHABLE_SENSITIVITIES:
                raise ValueError("fact_sensitivity.json: %r is a reachable sensitivity — "
                                 "flagging a fact with it is a no-op" % e["sensitivity"])
            out.setdefault(e["image_name"], {})[_norm_text(e["text"])] = e["sensitivity"]
        _FACT_SENS = out
    return _FACT_SENS if image_name is None else _FACT_SENS.get(image_name, {})


# ── dossier-level sensitivity (R2, ruled 2026-09-12) ─────────────────────────
# POSITIVE FILTER, in the same position as moments.PROPOSABLE_SENSITIVITIES: a
# dossier is proposable by MEMBERSHIP, so a dossier inheriting a value nobody
# anticipated cannot slip through a missing branch. DO NOT WIDEN.
PROPOSABLE_DOSSIER_SENSITIVITIES = frozenset({"none"})
_DOSSIER_SENS: dict | None = None


def dossier_sensitivity(image_name: str | None = None) -> dict:
    """Curated per-dossier flags. LOUD on a missing file or unapproved entry."""
    global _DOSSIER_SENS
    if _DOSSIER_SENS is None:
        blob = json.loads(DOSSIER_SENSITIVITY.read_text())
        out: dict[str, dict] = {}
        for name, e in (blob.get("dossiers") or {}).items():
            if name.startswith("_"):
                continue
            if not e.get("sensitivity"):
                raise ValueError("dossier_sensitivity.json: %s has no sensitivity" % name)
            if e.get("approved_by") != SENSITIVITY_APPROVER:
                raise ValueError("dossier_sensitivity.json: %s is not approved by %s "
                                 "(found %r). The agent may never approve one."
                                 % (name, SENSITIVITY_APPROVER, e.get("approved_by")))
            out[name] = e
        _DOSSIER_SENS = out
    return _DOSSIER_SENS if image_name is None else _DOSSIER_SENS.get(image_name, {})


def dossier_proposable(image_name: str) -> bool:
    """May the GENERATED-TEXT path propose this shoe at all?

    ★ READ FROM THE CURATED FILE, NOT FROM THE DOSSIER JSON. The stamped value
    is a record; a stale dossier on disk must never be able to GRANT
    proposability that the curated file withholds.

    ★ AND IT RAISES RATHER THAN FALLING THROUGH. When approved human copy
    exists, the correct behaviour is to ship that copy verbatim — and that lane
    is not built. Returning True here would hand the shoe to the writer, which
    is the exact outcome the flag exists to prevent, so it stops loudly instead.
    """
    e = dossier_sensitivity(image_name)
    if e.get("sensitivity", "none") in PROPOSABLE_DOSSIER_SENSITIVITIES:
        return True
    if e.get("human_copy") and e.get("human_copy_approved_by") == SENSITIVITY_APPROVER:
        raise NotImplementedError(
            "%s carries approved human copy but the VERBATIM SHIPPING LANE IS NOT BUILT "
            "(R2). Refusing to fall through to the generated-text path. Build the lane — "
            "compose_text already ships moment post_text byte-for-byte — before this "
            "dossier can post." % image_name)
    return False


def writer_reachable(fact: dict) -> bool:
    """Membership, never absence-from-a-blocklist. The whole rail is this line."""
    return fact.get("sensitivity", "none") in WRITER_REACHABLE_SENSITIVITIES


def hook_facts(dossier: dict) -> list[dict]:
    """The dossier's hook facts. THE ONLY correct way to obtain them.

    Three call sites used to inline `[f for f in d["facts"] if f["id"] in
    d["hook_candidates"]]`. A rail added to one of those would have been
    silently absent from the other two — the exact gap-between-components shape
    contracts.py exists to fight. One function, one rail.
    """
    ids = set(dossier.get("hook_candidates") or [])
    return [f for f in dossier.get("facts", []) if f["id"] in ids and writer_reachable(f)]


def lineage_facts(dossier: dict) -> list[dict]:
    """Silhouette-lineage facts, sensitivity-filtered. Same reasoning."""
    return [f for f in dossier.get("facts", [])
            if f.get("tag") == "silhouette_lineage" and writer_reachable(f)]


def distinctiveness(text: str) -> int:
    """Rank support facts by what they say about THIS shoe, not by order.

    Content words OUTSIDE the generic-spec vocabulary, plus proper nouns and
    numbers double-weighted. Verified to discriminate: the CLOT packaging
    sentence scores 29 against 3-8 for materials copy of comparable length.

    CAVEAT, stated because it is real: the score is a raw count, so longer
    sentences score higher all else equal. It beats length alone — a 111-char
    materials sentence scores 5 where a 235-char story sentence scores 29, far
    above the ~11 that length alone would predict — but it is a heuristic, not
    a semantic judgement.
    """
    import re as _re
    words = _re.findall(r"[A-Za-z][A-Za-z'\-]*|\d+", text or "")
    sent0 = {m.group(1) for m in _re.finditer(r"(?:^|[.!?]\s+)([A-Za-z]+)", text or "")}
    pn = sum(1 for w in words if w[:1].isupper() and w not in sent0)
    nums = sum(1 for w in words if w.isdigit())
    novel = sum(1 for w in words
                if w.lower() not in GENERIC_SPEC and w.lower() not in _SUPPORT_STOP
                and not w.isdigit() and not (w[:1].isupper() and w not in sent0))
    return novel + 2 * pn + 2 * nums


# The support bucket is spec + narrative_detail. Both are non-hookable by
# construction (neither is in HOOKABLE_TAGS), so widening the bucket widens what
# the writer may KNOW and nothing else.
SUPPORT_TAGS = frozenset({"spec", "narrative_detail"})


def support_facts(dossier: dict, limit: int = MAX_SUPPORT_FACTS) -> list[dict]:
    """Top-N support facts by distinctiveness. NEVER hook candidates.

    spec and narrative_detail rank TOGETHER in one pool. A narrative_detail
    fact gets no privilege for being narrative — it simply tends to score
    higher, because distinctiveness double-weights proper nouns and numbers and
    that is what a person, a collective or a date is made of. Ranking them in
    separate tiers would have been a second, untested judgement on top of a
    heuristic that is already only a heuristic.

    ★ SENSITIVITY IS FILTERED BEFORE RANKING, not after (R1). Filtering after
    would let a flagged fact consume one of the three slots and silently shrink
    the bucket — and the flagged fact is, by construction, the one that ranks
    highest, because numbers are double-weighted.
    """
    pool = [f for f in dossier.get("facts", [])
            if f.get("tag") in SUPPORT_TAGS and writer_reachable(f)]
    return sorted(pool, key=lambda f: -distinctiveness(f.get("text", "")))[:limit]

# ★★ "designer" IS GONE FROM HOOKABLE_TAGS, AND FROM THE TAG SET ENTIRELY.
# GOAT's `designer` field describes the SILHOUETTE, not the colorway, collab or
# SP built on it. It is correct on an original release and MISLEADING on
# everything after — the same class as D1's name-consistency problem, one layer
# down: the fact is true about a shoe, just not about THIS shoe.
#
# It shipped on 2026-09-11 as "...the Jordan 1 Retro Low OG SP designed by Peter
# Moore." Peter Moore designed the Jordan 1 in 1985; he had nothing to do with a
# 2023 Travis Scott SP.
#
# WHY EVERY CARD IS LINEAGE, measured rather than assumed. The obvious test —
# compare the card's year against the earliest year for its silhouette in
# release_dates.json — DOES NOT WORK, for two reasons:
#   1. the catalog's `silhouette` strings are VARIANT-level, not model-level.
#      The Jordan 1 is split across 13 of them ("1 Retro High OG", "1 Retro Low
#      OG SP", "Jordan 1 Mid", ...), 92 of 144 are singletons, and each carries
#      its own earliest year. A 2022 SP therefore looks like an "OG".
#   2. the catalog is a SAMPLE, not the historical record. Of the 97 cards that
#      test calls "OG", 90 released in 2010 or later and NONE in the 1980s or
#      1990s. It is measuring catalog coverage, not design origin.
# So the test is unusable, and since no card in this catalog is plausibly the
# original release of its silhouette, the fail-closed answer is that ALL of
# them are lineage. Confidence in that: high — it follows from the year
# distribution, not from a judgement call.
#
# A lineage fact is still worth carrying as supporting colour inside a lead
# hooked elsewhere, so it is emitted with its text SAYING SO EXPLICITLY. It can
# never be a hook_candidate, which is enforced by its absence above.

# Tokens that corroborate nothing — present in half the catalog.
GENERIC_TOKENS = frozenset({
    "black", "white", "low", "high", "mid", "retro", "nike", "jordan", "og", "sp",
    "adidas", "air", "shoe", "sneaker", "the", "and", "grey", "gray", "university",
    "wmns", "gs", "qs", "prm", "premium", "se", "id", "v2", "one", "1", "2", "3",
})

MONEY = re.compile(r"[$£€]\s?\d|\bUSD\b|\bMSRP\b|\bdollars?\b|resell|resale|\bworth\b", re.I)


class _Strip(HTMLParser):
    def __init__(self):
        super().__init__(); self.out = []
    def handle_data(self, d): self.out.append(d)
    def text(self): return re.sub(r"\s+", " ", "".join(self.out)).strip()


def strip_html(h: str | None) -> str:
    p = _Strip(); p.feed(h or ""); return html.unescape(p.text())


def norm(s: str) -> str:
    """Lowercase, entity-decode, collapse punctuation. Feeds phrase matching."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ",
                  html.unescape(s or "").lower())).strip()


def has_phrase(haystack: str, phrase: str) -> bool:
    """Whole-phrase, word-bounded containment. 'air' must not match 'airmax'."""
    h, p = norm(haystack), norm(phrase)
    if not h or not p:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", h) is not None


def has_all_tokens(haystack: str, phrase: str) -> bool:
    """Every phrase token present as a whole word. Order NOT required.

    ★ Three passes taught this: PRESENCE is what matters, not contiguity and
    not order. The catalog and GOAT use different naming vocabularies —
    catalog "Jordan 1 High" vs GOAT "Air Jordan 1 Retro High OG" (interposed
    modifiers, which killed contiguity), and catalog "SB Dunk Low" vs GOAT
    "Nike Dunk Low Pro SB" (reordered, which killed ordered-subsequence).
    Neither is a mismatch; both are the same shoe named differently.

    This still rejects the case the strict form existed for: silhouette
    "Nike Air Humara" against an "Air Max Goadome" name fails because the
    token `humara` is ABSENT — in any order. Order never caught Goadome;
    presence did.
    """
    h, ph = set(norm(haystack).split()), norm(phrase).split()
    if not h or not ph:
        return False
    return all(t in h for t in ph)


def distinctive_tokens(*sources: str) -> list[str]:
    toks, seen = [], set()
    for s in sources:
        for t in norm(s).split():
            if t in GENERIC_TOKENS or len(t) < 3 or t in seen:
                continue
            seen.add(t); toks.append(t)
    return toks


# ── the gate ─────────────────────────────────────────────────────────────────
def name_consistency(cat: dict, snap: dict) -> dict:
    """Three signals, fail-closed. Auditable per shoe — every input recorded.

    Signal 2 is THREE-WAY, because "nothing to test" and "tested and found
    nothing" are different outcomes — the same distinction verify.py draws
    between unverified and contradicted. Collapsing them rejects shoes whose
    colorway is simply generic ("Black"); granting them a free pass is the
    opposite error. Signal 3 (year agreement) resolves the unavailable case:
    weak alone, but genuinely independent of silhouette, and a snapshot about a
    different shoe usually carries a different year.
    """
    story = strip_html(snap.get("story_html"))
    goat_name = snap.get("name") or ""
    silhouette = (cat.get("silhouette") or "").strip()

    sig1 = bool(silhouette) and (has_all_tokens(goat_name, silhouette)
                                 or has_all_tokens(story, silhouette))
    # ★ Signal 2 must be INDEPENDENT of signal 1, or it corroborates nothing.
    # First cut pulled tokens from colorway AND name — but `name` contains the
    # silhouette words, so "foamposite" alone satisfied signal 2 for
    # nike_air_foamposite_one_wu_tang and the gate returned "confirmed" on the
    # exact case it exists to catch (the story is about 'Optic Yellow'; the token
    # "tang" is absent). Silhouette tokens are now excluded, so signal 2 tests
    # only what signal 1 cannot.
    sil_tokens = set(norm(silhouette).split())
    tokens = [t for t in distinctive_tokens(cat.get("colorway") or "",
                                            cat.get("name") or "")
              if t not in sil_tokens]
    found = [t for t in tokens if has_phrase(story, t)]
    sig2 = "unavailable" if not tokens else ("pass" if found else "fail")

    cat_year, goat_year = cat.get("year"), snap.get("release_year")
    year_match = bool(cat_year) and bool(goat_year) and int(cat_year) == int(goat_year)
    sig3 = {"tested": {"catalog_year": cat_year, "goat_release_year": goat_year},
            "match": year_match, "applied": sig2 == "unavailable"}

    if not sig1:
        verdict, decided_by = "failed", "signal_1_silhouette"
    elif sig2 == "pass":
        verdict, decided_by = "confirmed", "signal_2_colorway"
    elif sig2 == "fail":
        verdict, decided_by = "silhouette_only", "signal_2_colorway"
    else:                                   # unavailable -> fall back to year
        verdict = "confirmed" if year_match else "silhouette_only"
        decided_by = "signal_3_year"
    return {"name_match": verdict,
            "decided_by": decided_by,
            "signal_1_silhouette": {"tested": silhouette, "found": sig1},
            "signal_2_colorway": {"tested": tokens, "found": found, "result": sig2},
            "signal_3_year": sig3}


# ── sentence-level extraction ────────────────────────────────────────────────
# Sentence-level, NOT story-level: most GOAT prose is 60-80% materials copy, so a
# whole-story blob would bury the one real fact under four sentences of spec.
# ⚠ UNUSED — READ BY NOTHING. This compiles a materials vocabulary and no code
# path calls it; it is not the spec classifier and never has been (see the R3
# note in the module docstring). Kept, not deleted, because it is the obvious
# seed for the positive spec classifier that R3 says is the real fix.
#
# ★ AND ITS EXISTENCE IS ITS OWN HAZARD (R8, banked 2026-09-12). A dead
# constant that LOOKS like the live mechanism is worse than no constant at all.
# This one describes a classifier that is present in the file and wired to
# nothing, and reading it is how the "spec is decided by materials vocabulary"
# hypothesis was invented — a description of behaviour that has never occurred.
# If you find yourself citing SPEC_MARKERS as evidence of what this module
# does, you are citing dead code. Wire it or delete it; do not believe it.
SPEC_MARKERS = re.compile(
    r"\b(upper|midsole|outsole|sockliner|insole|tongue|heel|collar|eyelet|lace|"
    r"suede|leather|mesh|nubuck|canvas|rubber|foam|boost|cushion|shank|overlay|"
    r"panel|stitch|embroider|print|graphic|branding|constructed|features|"
    r"crafted|built|finish|textured|colorway|palette|hue|tonal)\b", re.I)

# ★ FOUR FIXES, 2026-09-12 (H4 rulings B, R3, R4). ALL ARE BUG FIXES, NOT POLICY.
#   (i)   \bexclusive\b -> \bexclusiv\w+ . A word boundary was silently dropping
#         every "launched exclusively in Japan" — the adverb form, which is how
#         GOAT actually writes regional exclusivity. Measured: 5 sentences the
#         old boundary missed, 3 already tagged by another rule, 2 newly
#         release_drama (nike_dunk_low_retro_qs_argon f3, yeezy350v2_clay f5).
#   (ii)  patient / syndrome / disease added to cultural_moment. The Doernbecher
#         near-miss: a child at a children's hospital designs a shoe, and the
#         sentence saying so fell to spec because it named the illness and not
#         the hospital. Measured across all 250 dossiers: exactly 2 facts match,
#         both Doernbecher, both human stories, ZERO false positives.
#   (iii) R3 — \bdisease\b(?!-) . "disease" sits on a word boundary before a
#         hyphen, so the bare form would have matched "disease-resistant" and
#         "disease-causing" in performance and materials copy: a false positive
#         that promotes FILLER INTO A HOOK, the one direction fail-closed exists
#         to prevent. Zero hyphenated occurrences in the corpus today — the
#         guard is preventive, and measured at 0 deltas. Note the plural
#         "diseases" is still not matched; that is the ruled trade.
#   (iv)  R4 — \bsold out\b now also \bsell(?:s|ing)? out\b. Identical
#         word-boundary class to (i), no policy content. Measured: 1 sentence
#         newly reached — yeezy350v2_beluga_2.0 f4, "It was quickly restocked on
#         November 30th after selling out." — spec -> release_drama. Leaving a
#         known identical bug in place because it fell outside a prompt's
#         literal scope was the wrong kind of discipline.
TAG_RULES = (
    ("collab_origin",   re.compile(r"\bcollaborat\w*|\bpartnership\b|\bteamed up\b|\bjoint\b|\bx\s+[A-Z]", re.I)),
    ("cultural_moment", re.compile(r"\bhomage\b|\binspired by\b|\bpays? tribute\b|\bcelebrat\w+|\bcommemorat\w+|"
                                   r"\bproceeds\b|\bcharit\w+|\bfoundation\b|\bhospital\b|\bhonor\w*\b|"
                                   r"\bpatients?\b|\bsyndromes?\b|\bdisease\b(?!-)|"
                                   r"\bculture\b|\bmovie\b|\bfilm\b|\bvideo\b|\balbum\b|\bmusic\b", re.I)),
    ("release_drama",   re.compile(r"\bbanned\b|\bcontrovers\w+|\brecall\w*|\bcancel\w+|\blimited\b|"
                                   r"\bexclusiv\w+|\bfriends and family\b|\bplayer exclusive\b|\bunreleased\b|"
                                   r"\bsold out\b|\bsell(?:s|ing)? out\b|\briot\w*", re.I)),
    ("price_reason",    re.compile(r"\brare\b|\bscarc\w+|\bonly \d+ pairs?\b|\bnumbered\b|\bone[- ]of[- ]one\b", re.I)),
)


# ── narrative_detail: the SUPPORT tier, from CURATED DATA (ruled 2026-09-12) ──
# Of the 735 spec facts across 250 dossiers, a measured 89 are not materials
# copy at all: they name a PERSON, a COLLECTIVE, an EVENT, or say where the
# design CAME FROM. They reached the writer as nothing, because the else branch
# does not distinguish "a shoe designed by an 11-year-old" from "a rubber
# outsole delivers grip".
#
# ★ NEVER HOOKABLE. narrative_detail is absent from HOOKABLE_TAGS, and the tag
# is tested AFTER every rule in TAG_RULES, so it can only ever claim a sentence
# the hook patterns have already declined. Note the near-collision with
# selector.NARRATIVE_HOOK_TAGS — that frozenset is the HOOK filter and this tag
# must never be added to it. tests/test_narrative_detail.py asserts both.
#
# ★ THE VOCABULARY IS DATA, NOT CODE (ruled). The curated lists live in two
# reviewable JSON files, amendable by hand like data/moments.json. They are
# judgement calls about names — the kind that must stay visible to a human — and
# a regex literal buried in this module is not reviewable by anyone.
NARRATIVE_ENTITIES = HERE / "data" / "narrative_entities.json"
NARRATIVE_MARKERS = HERE / "data" / "narrative_markers.json"

_VOCAB: dict | None = None


def _phrase_rx(terms: list[str], *, case_sensitive: bool, closed: bool):
    """Word-bounded alternation. `closed` bounds the END of the phrase too."""
    tail = r"(?![A-Za-z0-9])" if closed else ""
    body = "|".join(r"(?<![A-Za-z0-9])%s%s" % (re.escape(t), tail) for t in terms)
    return re.compile(body, 0 if case_sensitive else re.I)


def _load_list(blob: dict, key: str, path: Path) -> list[str]:
    v = blob.get(key)
    if not isinstance(v, list) or not v or not all(
            isinstance(t, str) and t.strip() for t in v):
        raise ValueError("%s: '%s' must be a non-empty list of non-empty strings"
                         % (path.name, key))
    return v


def narrative_vocab() -> dict:
    """Compiled curated vocabulary. LOUD on a missing or malformed file.

    A missing list must never degrade to "matches nothing": that would retire
    the whole tier while every reader of this module still believed it was on.
    Same reasoning as contracts.py — silence is the failure mode, so it is made
    impossible rather than merely discouraged.
    """
    global _VOCAB
    if _VOCAB is None:
        ents = json.loads(NARRATIVE_ENTITIES.read_text())
        mrks = json.loads(NARRATIVE_MARKERS.read_text())
        # ★ ENTITIES MATCH CASE-SENSITIVELY. The colour "off-white" and the
        # label "Off-White" are the same letters; case is the ONLY thing
        # separating "off-white leather overlays" (materials) from
        # "Off-White™ for NIKE" (a collaborator). Matching insensitively put 11
        # pure materials sentences into this tier. Proper nouns are capitalised
        # in GOAT prose, so case-sensitivity costs nothing.
        entities = (_load_list(ents, "people", NARRATIVE_ENTITIES)
                    + _load_list(ents, "collectives", NARRATIVE_ENTITIES)
                    + _load_list(ents, "events", NARRATIVE_ENTITIES))
        prov = _load_list(mrks, "provenance", NARRATIVE_MARKERS)
        place = _load_list(mrks, "placement_frames", NARRATIVE_MARKERS)
        _VOCAB = {
            "entities": _phrase_rx(entities, case_sensitive=True, closed=True),
            # markers are verbs and prepositions: "debut" must also catch
            # "debuted", so the END of the phrase is deliberately unbounded.
            "provenance": _phrase_rx(prov, case_sensitive=False, closed=False),
            "placement": _phrase_rx(place, case_sensitive=False, closed=False),
            "counts": {"entities": len(entities), "provenance": len(prov),
                       "placement_frames": len(place)},
        }
    return _VOCAB


def is_narrative_detail(s: str) -> bool:
    """POSITIVE test: does this sentence name someone, or say where this came from?

    Two signals and one exclusion:
      entity      a curated name appears (case-sensitive)
      provenance  a curated origin/event frame appears
      placement   the entity is ONLY a logo sitting on a part of the shoe, so
                  the sentence stays spec — "a rubberized Cactus Jack patch
                  adorns the tongue" names a collaborator and is still pure
                  materials copy. 54 sentences are held back this way.

    A provenance marker OVERRIDES the placement exclusion, because
    "a '94' embroidered on the lateral heel — a nod to Supreme's founding year"
    is placement AND provenance, and the nod is the part worth telling.
    """
    v = narrative_vocab()
    entity = bool(v["entities"].search(s))
    prov = bool(v["provenance"].search(s))
    if not (entity or prov):
        return False
    if v["placement"].search(s) and not prov:
        return False
    return True


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def tag_sentence(s: str) -> str:
    """Hook tags first, then narrative_detail, then spec.

    FAIL-CLOSED on purpose, and STILL fail-closed after narrative_detail. Every
    HOOKABLE tag is tested BEFORE narrative_detail, so a sentence that could
    carry a post always becomes the hook; narrative_detail can only ever claim
    one the hook patterns have already declined. Both remaining outcomes are
    non-hookable, so being wrong between them costs a dull support fact, while
    the opposite default would let filler open a post.

    ★ `spec` IS STILL THE ELSE BRANCH AND STILL CLASSIFIES NOTHING BY EVIDENCE.
    narrative_detail routes part of the accumulation somewhere useful; it gives
    spec no evidence of its own. See the R3 note in the module docstring.
    """
    for tag, pat in TAG_RULES:
        if pat.search(s):
            return tag
    if is_narrative_detail(s):
        return "narrative_detail"
    return "spec"


def build(image_name: str, cat: dict, snap: dict, release_dates: dict) -> dict:
    gate = name_consistency(cat, snap)
    facts: list[dict] = []
    n = 0
    sens = fact_sensitivity(image_name)

    def add(tag, text, kind, ref, verified="self_evident"):
        nonlocal n
        text = re.sub(r"\s+", " ", text).strip()
        if not text or MONEY.search(text):      # no figure enters a fact, ever
            return
        if tag not in ALL_TAGS:
            return
        n += 1
        facts.append({"id": "f%d" % n, "tag": tag, "text": text,
                      "source": {"kind": kind, "ref": ref},
                      # stamped HERE, before any bucket exists, so there is no
                      # later branch that could forget to apply it
                      "sensitivity": sens.get(_norm_text(text), "none"),
                      "verified": verified, "checked_at": None})

    # designer — 83.6% populated, 13 distinct values: a controlled vocabulary and
    # the highest-confidence target in the snapshot. Emitted at every gate level
    # except "failed", because it is a field, not prose.
    designer = (snap.get("designer") or "").strip()
    silhouette = (cat.get("silhouette") or "").strip()
    if designer and silhouette and gate["name_match"] != "failed":
        # Phrased as LINEAGE, never as authorship of this card. The subject of
        # the sentence is the silhouette, which is what GOAT's field describes.
        add("silhouette_lineage",
            "Built on the %s silhouette, designed by %s." % (silhouette, designer),
            "goat_snapshot", "designer")

    # release_date — from cyphermarketer-owned release_dates.json (v1.2 ruling)
    rd = release_dates.get(image_name) or {}
    if rd.get("release_date") and gate["name_match"] != "failed":
        add("release_date", "Released %s." % rd["release_date"], "release_dates", image_name)

    # story-derived facts — DROPPED unless the gate confirms the story is about
    # this shoe. This is the whole point of the gate.
    if gate["name_match"] == "confirmed":
        for s in split_sentences(strip_html(snap.get("story_html"))):
            add(tag_sentence(s), s, "goat_snapshot", "story_html")

    # A flagged fact is never a hook CANDIDATE, so nothing downstream — not the
    # selector, not detect_hook, not the writer — can ever see it as one.
    hooks = [f["id"] for f in facts
             if f["tag"] in HOOKABLE_TAGS and writer_reachable(f)]
    return {"image_name": image_name,
            "built_at": datetime.now(timezone.utc).isoformat(),
            **gate,
            "facts": facts,
            "hook_candidates": hooks,
            # STAMPED AS A RECORD ONLY. Every consumer asks
            # dossier_proposable(), which reads the curated file — a stale
            # dossier must never be able to grant itself proposability.
            "sensitivity": (dossier_sensitivity(image_name).get("sensitivity") or "none"),
            "usable": bool(hooks)}


CATALOG_CACHE = HERE / "state" / "_catalog_cache.json"   # machine-local, gitignored


def load_catalog() -> dict:
    """Catalog rows for the name-consistency gate. Cached locally because
    state/ is gitignored; re-fetched read-only when the cache is absent, so the
    script is self-contained on a fresh checkout."""
    if CATALOG_CACHE.exists():
        return {r["image_name"]: r for r in json.loads(CATALOG_CACHE.read_text())}
    import subprocess
    q = HERE / "state" / "_dossier_cat.sql"
    q.parent.mkdir(parents=True, exist_ok=True)
    q.write_text("select distinct image_name, name, colorway, silhouette, brand, year "
                 "from public.catalog_cards order by image_name;", encoding="utf-8")
    r = subprocess.run(["supabase", "db", "query", "--linked", "-o", "json", "-f", str(q)],
                       capture_output=True, text=True, timeout=180,
                       cwd=str(Path.home() / "Documents/openclaw/CYPHER"))
    m = re.search(r"\[.*\]", r.stdout, re.S)
    if not m:
        sys.stderr.write("FATAL: catalog query failed: %s\n" % r.stderr[:200])
        raise SystemExit(2)
    rows = json.loads(m.group(0))
    CATALOG_CACHE.write_text(json.dumps(rows, indent=0))
    return {x["image_name"]: x for x in rows}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog()
    try:
        rd = json.loads(RELEASE_DATES.read_text())
    except Exception:
        rd = {}
    built = 0
    for f in sorted(SNAPS.glob("*.json")):
        image_name = f.stem
        snap = json.loads(f.read_text())
        cat = catalog.get(image_name)
        if not cat:
            continue
        d = build(image_name, cat, snap, rd)
        (OUT / ("%s.json" % image_name)).write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
        built += 1
    # ★ A CURATED FLAG THAT MATCHES NOTHING IS A HARD FAILURE. If GOAT rewrites
    # a story sentence, the flag silently stops applying and the fact becomes
    # reachable again — fail-open, on the one rail that must never fail open.
    seen = set()
    for f in sorted(OUT.glob("*.json")):
        d = json.loads(f.read_text())
        for fact in d["facts"]:
            if fact.get("sensitivity", "none") != "none":
                seen.add((d["image_name"], _norm_text(fact["text"])))
    orphans = [(im, t[:60]) for im, texts in fact_sensitivity().items()
               for t in texts if (im, t) not in seen]
    if orphans:
        raise SystemExit("FATAL: curated sensitivity flags matched no fact — a flag "
                         "has lost its target and the fact is REACHABLE again:\n" +
                         "\n".join("  %s  %s..." % o for o in orphans))
    print("built %d dossiers -> %s" % (built, OUT))
    print("sensitivity flags applied: %d" % len(seen))


if __name__ == "__main__":
    main()
