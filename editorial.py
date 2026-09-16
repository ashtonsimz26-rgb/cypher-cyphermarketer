#!/usr/bin/env python3.12
"""
editorial.py — THE BAR. "Year + retail + name + link" is not content.

Ashton's ruling, 2026-08-20. Four gates, all enforced in code so the bar
survives sessions rather than living in someone's memory:

(a) HOOK REQUIRED. Every draft must lead with a story element. The hook is
    DERIVED FROM DATA and named explicitly in the proposal metadata. No hook
    -> no proposal. The drafter cannot shrug and post anyway.
(b) LEAD MUST BE SPECIFIC. Operationalised from Ashton's own test: "if the
    first sentence could describe any shoe by swapping the name, it fails."
    We strip the shoe's own name/colorway from the lead; what remains must
    still carry something concrete (a year, a price, a named person or
    collaborator). Otherwise it is filler wearing a shoe's name.
(c) FORMAT ROTATION. No two consecutive posts share a copy skeleton. The last
    format used is persisted; the next draft must differ.
(d) ZERO IS A VALID DAY. Quality over quota — "no strong hook today" beats a
    filler post. candidates() returning nothing is success, not failure.
"""
from __future__ import annotations
import json, re
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from x_client import weighted_len  # noqa: E402  (pure function, no side effects)
import rails  # noqa: E402  (PULL_MARKERS — the set skeleton asserts against them)

HERE = Path(__file__).resolve().parent
FORMAT_STATE = HERE / "state" / "last_format.json"
REJECT_REASONS = HERE / "state" / "reject_reasons.json"

# ── REJECTION FEEDBACK — SHAPE ONLY, NEVER SUBJECT ───────────────────────────
# (Deliberately UNLETTERED: the editorial bar's letters are load-bearing —
#  SOUL.md already uses (e) for A MATCH IS NOT A MOMENT and (f) for VERIFY
#  BEFORE YOU CLAIM, and daily_digest.py keys comments to those letters.
#  This is a feedback channel, not a fifth gate. Do not letter it.)
# v1.3 ruling (2026-09-09): the agent may learn the SHAPE of a post from human
# rejection — never its SUBJECT. Subject selection stays pillar- and lore-driven.
# This frozenset IS that ruling in code, as a POSITIVE filter: a reason whose
# code is null, unrecognised, or absent from this set feeds NOTHING into
# drafting. Rejections are still recorded in full for Ashton to read.
#
# ⚠️ ADDING A SUBJECT-SHAPED CODE HERE (a shoe, a brand, a topic, "no interest")
# would silently convert human feedback into topic-selection-by-engagement —
# the exact objective v1.3 rejected. The allow-list is the mechanism that keeps
# "learn the shape, not the topic" true. Do not widen it without a ruling.
ALLOWED_FEEDBACK_CODES = frozenset({
    "generic_lead", "too_wordy", "weak_hook", "format_repeat", "price_unattributed",
})

# When a human has said "too wordy", aim well under the ceiling rather than
# trimming to fit it. This is the one code a TEMPLATE writer can act on today;
# the rest become writer constraints when the LLM writer lands (F4).
TOO_WORDY_LIMIT = 240
LINK = "https://apps.apple.com/app/cypher-unlock-the-vault/id6761334111"

# Copy skeletons. All six are selectable as of 2026-09-16 (E4 built the last of
# them). DECLARED_NOT_READY is the escape hatch for a format that is named but
# unbuilt; it is empty, and listing a format without implementing it would
# silently reduce the rotation to a lie.
FORMATS = ["story_spotlight", "price_journey", "on_this_day", "grail_lore",
           "set_completion", "which_would_you_pull"]
DECLARED_NOT_READY: dict[str, str] = {}      # emptied 2026-09-16 — see below

# ── which_would_you_pull (E4, 2026-09-16) ────────────────────────────────────
# Named in SOUL since the beginning, declared not-ready for a month, never once
# produced. It is the only format that asks the reader for a response, and the
# account's reply/quote/bookmark count is zero.
#
# ★★ STRUCTURALLY PRICE-FREE, the same way set_completion is pull-free. SOUL
# says two cards, one question, NO PRICES, both names legible. "The skeleton
# doesn't mention a price" is not a guarantee, so:
#   1. The branch interpolates ONLY two display titles. No year, no retail, no
#      resale, no `frag` — none of the fields a price could arrive in are read.
#   2. assemble() ASSERTS the output carries no currency figure before returning.
#   3. The composition is two_card_crop, which crops the EST. VALUE row out of
#      frame — so the IMAGE cannot carry a figure either, which is why this
#      format needs no attribution sentence.
# Both cards are PULL-route only; that is enforced in pairing.py and by the
# OBTAINABLE rail per card, not here.
PULL_QUESTION = "Which one are you pulling for?"
_MONEY_RX = re.compile(r"[$£€]\s?\d|\bUSD\b|\bretail\b|\bresale\b|\bworth\b", re.I)

# ── set_completion (Ashton's ruling, 2026-09-16) ─────────────────────────────
# The only tentpole the catalog can actually support: three cards, all live, all
# with claimed rewards on the server. SOUL admits them on the EARN route only,
# and the route IS the claim.
#
# ★★ STRUCTURALLY INCAPABLE OF PULL LANGUAGE, not merely discouraged from it.
# Three mechanisms, because "the template doesn't say pull" is not a guarantee:
#   1. The skeleton has NO free-text slot. Every variable it interpolates is a
#      catalog field — display name, colorway, set name, requirement names. The
#      story fragment, which is the one slot that carries arbitrary prose, is
#      not used by this format at all.
#   2. SET_LEAD_TEMPLATE literally contains the route phrase, so
#      SET_ROUTE_STATED cannot fail for a draft this skeleton produced.
#   3. assemble() ASSERTS the output against rails.PULL_MARKERS before
#      returning. A future edit that reintroduces a free slot fails loudly here
#      rather than shipping a false claim.
SET_LEAD_TEMPLATE = "Complete the %s set and the %s is yours."
SET_ROUTE_PHRASE = "complete the"       # lowercase; the assertion is case-folded


def _join_names(names: list[str]) -> str:
    """'a and b' / 'a, b and c'. Catalog display names only — never free text."""
    names = [n for n in names if n]
    if len(names) <= 1:
        return names[0] if names else ""
    return "%s and %s" % (", ".join(names[:-1]), names[-1])

# Signals that a catalog description actually carries a STORY rather than specs.
# Human-interest markers. These outrank the price hook — see detect_hook().
STRONG_STORY_MARKERS = [
    (r"designed by ([A-Z][a-z]+ [A-Z][a-z]+)", "named designer — a person"),
    (r"\bworn by\b|\bplayer exclusive\b|\bfriends and family\b", "provenance"),
    (r"\bhospital\b|\bcharit\w+\b|\bfoundation\b|\bproceeds\b", "cause"),
    (r"\bbanned\b|\bcontrovers\w+\b", "controversy"),
]

STORY_MARKERS = [
    (r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)'s\b", "named designer/artist"),
    (r"\b(\w+)\s+x\s+(\w+)", "collaboration"),
    (r"\bfirst\b|\bdebut(ed)?\b|\boriginal\b", "first/debut"),
    (r"\bonly\b|\brarest\b|\bnever\b", "scarcity"),
    (r"\bworn by\b|\bplayer exclusive\b|\bfriends and family\b", "provenance"),
    (r"\banniversar\w+\b|\bretro(ed)?\b|\breturn(s|ed)?\b", "retro/return"),
    (r"\bbanned\b|\bcontrovers\w+\b|\bfined\b", "controversy"),
]
GENERIC_LEAD_WORDS = {"sneaker", "shoe", "colorway", "silhouette", "classic", "clean",
                      "iconic", "premium", "everyday", "versatile", "staple", "fresh"}


def _now_year() -> int:
    return datetime.now(timezone.utc).year


def last_format() -> str | None:
    try:
        return json.loads(FORMAT_STATE.read_text()).get("format")
    except Exception:
        return None


def record_format(fmt: str):
    FORMAT_STATE.parent.mkdir(parents=True, exist_ok=True)
    FORMAT_STATE.write_text(json.dumps(
        {"format": fmt, "ts": datetime.now(timezone.utc).isoformat()}))


def avoid_guidance(window: int = 10) -> list[str]:
    """Allow-listed craft codes from recent human rejections, most recent first.

    The filter is POSITIVE — a code enters only by being IN
    ALLOWED_FEEDBACK_CODES. Uncoded reasons ("nobody cares about Crocs") and
    unrecognised codes return nothing, so a subject judgment cannot reach the
    drafter even though it is recorded. Missing or malformed file -> no
    guidance, never an exception: feedback is an improvement, not a dependency.
    """
    try:
        rows = json.loads(REJECT_REASONS.read_text())
        if not isinstance(rows, list):
            return []
    except Exception:
        return []
    out: list[str] = []
    for r in reversed(rows[-window:]):
        if not isinstance(r, dict):
            continue
        code = r.get("reason_code")
        if code in ALLOWED_FEEDBACK_CODES and code not in out:
            out.append(code)
    return out


# Dossier tags that are narrative hooks, in preference order. These are
# VERIFIED facts that passed the name-consistency gate, so they outrank a regex
# over catalog prose as well as outranking arithmetic.
DOSSIER_HOOK_TAGS = ("cultural_moment", "release_drama", "collab_origin")

# PIPELINE FIELDS this decision-maker consults (contracts.py). Not its Python
# parameters — the fields other components produce.
DETECT_HOOK_READS = frozenset({
    "hook_facts", "description", "year", "retail_price", "estimated_resale",
    "price_verified", "source", "headline",
})
CHOOSE_FORMAT_READS = frozenset({"hook_type", "last_format", "avoid_codes"})


def detect_hook(row: dict, *, source: str, price_verified: bool,
                headline: str = "",
                hook_facts: list[dict] | None = None,
                earn_route: bool = False) -> tuple[str | None, str]:
    """Return (hook_type, human-readable hook) or (None, reason-to-skip).

    Order matters: the most specific, most time-relevant hook wins.

    ★ THE EARN ROUTE OUTRANKS EVERYTHING (2026-09-16). Three cards in the whole
    catalog can be earned and not pulled. When one comes up, that IS the story —
    a top-tier card with a route to it is rarer than any collab origin — and it
    is also the only hook whose format can state the route. Placed first for
    both reasons.

    ★★ NARRATIVE OUTRANKS ARITHMETIC (ruled 2026-09-11).
    A 3x multiple is a FILTER, not a hook — it tells you a shoe is interesting,
    not what to say about it. Nineteen of 28 early drafts hooked on price
    precisely because arithmetic is ALWAYS available and a story never is.
    price_journey therefore sits below EVERY story signal, not just the strong
    ones.

    ★★ AND THIS FUNCTION NOW READS THE DOSSIER.
    It previously read only row["description"], so the verified fact that
    justified a post was invisible to the component choosing its hook. On
    2026-09-11 that shipped format=story_spotlight on HOOK[price_journey] for a
    card whose dossier held "Travis Scott's first sneaker collab in women's
    sizing". Fifth instance of a rule going inert because the information never
    reached the decision-maker.
    """
    desc = row.get("description") or ""
    year = row.get("year")
    retail, resale = row.get("retail_price"), row.get("estimated_resale")

    # FIRST — see the docstring. Only three cards in the catalog can reach here.
    if earn_route:
        return "set_completion", ("earnable by completing the %s set"
                                  % (row.get("set_name") or "?"))

    if source in ("drop_correspondent", "drop_overnight") and headline:
        return "drop_moment", "matched today's headline: %s" % headline[:70]

    if source == "on_this_day" and isinstance(year, int):
        return "on_this_day", "%d — %d years ago" % (year, _now_year() - year)

    # A HUMAN story outranks a number. Leading with "3.4x retail" on a shoe a
    # sick kid designed for a children's hospital is tone-deaf, and no rails
    # check would have caught it — so the priority itself has to be right.
    # 1. DOSSIER narrative facts — verified, gated, about THIS card.
    by_tag = {}
    for f in (hook_facts or []):
        by_tag.setdefault(f.get("tag"), f)
    for tag in DOSSIER_HOOK_TAGS:
        f = by_tag.get(tag)
        if f:
            return tag, "dossier %s [%s]: %s" % (tag, f.get("id"), f.get("text", "")[:70])

    # 2. STRONG story markers in catalog prose (the STRONG/weak split stays).
    for pat, label in STRONG_STORY_MARKERS:
        m = re.search(pat, desc)
        if m:
            return "story", "%s — %r" % (label, m.group(0)[:48])

    # 3. weak story markers — still ABOVE price.
    for pat, label in STORY_MARKERS:
        m = re.search(pat, desc)
        if m:
            return "story", "%s — %r" % (label, m.group(0)[:48])

    # 4. price LAST among content hooks. A multiple is a filter, not a hook.
    if price_verified and retail and resale and resale >= retail * 3:
        return "price_journey", "PK-verified $%d retail -> $%d resale (%.1fx)" % (
            retail, resale, resale / retail)

    if (row.get("rarity") or "") in ("GRAIL", "HOLY GRAIL"):
        return "grail_lore", "top-tier card with catalog lore"

    return None, "no story element in the catalog row (description is spec-only)"


# Which skeletons are SEMANTICALLY VALID for each hook. Rotation may only pick
# inside this set. Variety is a nice-to-have; appropriateness is not.
# ★★ A FORMAT THAT CANNOT VOICE THE HOOK MAY NOT BE SELECTED FOR IT.
# Enforced by construction: the format simply is not in the hook's list, so
# there is no check to pass and no exception branch to take.
#
# The 2026-09-11 proposal shipped format=story_spotlight on HOOK[price_journey]
# with NO PRICE ANYWHERE IN THE COPY — the identical defect as p_63d2666163 in
# the original diagnosis. The hook that justified the post was invisible in it.
# story_spotlight has no price slot; it could never voice that hook. It was
# listed here anyway as a general-purpose fallback, and a fallback that cannot
# say the thing is not a fallback, it is a silent topic change.
#
# RULE: a format belongs in a hook's list only if the format can SAY the hook.
VOICES_PRICE = frozenset({"price_journey"})

ALLOWED_FORMATS = {
    "story":         ["story_spotlight", "grail_lore"],
    "drop_moment":   ["story_spotlight", "grail_lore"],
    "on_this_day":   ["on_this_day", "story_spotlight"],
    # story_spotlight REMOVED: it cannot voice a price. A price hook has exactly
    # one format that can express it; if rotation wants variety on this hook,
    # the answer is a new price-capable skeleton, not a silent substitution.
    "price_journey": ["price_journey"],
    "grail_lore":    ["grail_lore", "story_spotlight"],
    # dossier-borne narrative hooks — story-shaped, so story skeletons voice them
    "cultural_moment": ["story_spotlight", "grail_lore"],
    "release_drama":   ["story_spotlight", "grail_lore"],
    "collab_origin":   ["story_spotlight", "grail_lore"],
    # The EARN route has exactly one skeleton, by design. No story format may
    # voice it: story_spotlight and grail_lore have no route slot, so either
    # would produce a true-looking post that never says how the card is got —
    # which is the failure SET_ROUTE_STATED exists to catch. Same reasoning as
    # price_journey's single entry.
    "set_completion":  ["set_completion"],
    # A pair hook has exactly one skeleton, for the same reason price_journey
    # does: no other skeleton has two title slots, so any substitution would
    # silently drop a card the post is about.
    "which_would_you_pull": ["which_would_you_pull"],
}


def format_can_voice(hook_type: str, fmt: str) -> bool:
    """Structural guard. A price hook demands a price-capable format."""
    if hook_type == "price_journey":
        return fmt in VOICES_PRICE
    return fmt in ALLOWED_FORMATS.get(hook_type, [])


def choose_format(hook_type: str) -> str:
    """Rotate for variety, but never out of the hook's valid set.

    ★ The rotation once flipped a human-story hook (a child designing a shoe for
    a children's hospital) onto the price_journey skeleton — "retailed at $225,
    real pairs now trade around $775". Correct by the variety rule, tone-deaf in
    fact. Rotation now only chooses among skeletons that fit the hook, and will
    REPEAT a format rather than misframe a story."""
    allowed = ALLOWED_FORMATS.get(hook_type, ["story_spotlight"])
    last = last_format()
    for f in allowed:
        if f != last:
            return f
    return allowed[0]                       # repeat beats misframing


def _story_fragment(desc: str) -> str:
    """First sentence of the catalog description, trimmed — that is the story."""
    s = re.split(r"(?<=[.!?])\s+", (desc or "").strip())
    frag = s[0] if s else ""
    return frag.rstrip(".").strip()


DANGLING = {"of", "the", "a", "an", "and", "with", "his", "her", "their", "its",
            "through", "whose", "that", "to", "in", "on", "for", "by", "at",
            "from", "as", "into", "was", "were", "is", "are", "made", "told"}


def _tidy(frag: str) -> str:
    """Drop trailing function words so a trim never dangles."""
    w = frag.rstrip(" ,;:—-").split()
    while w and w[-1].lower().strip(",;:") in DANGLING:
        w.pop()
    return " ".join(w).rstrip(" ,;:—-")


def _clause_prefixes(frag: str) -> list[str]:
    """Progressively shorter prefixes cut at natural clause boundaries."""
    out, parts = [], re.split(r"\s+—\s+|,\s+", frag)
    for i in range(len(parts) - 1, 0, -1):
        cand = _tidy(" ".join(parts[:i]))
        if len(cand.split()) >= 4:
            out.append(cand)
    return out


def build_draft(row: dict, hook_type: str, fmt: str, *, price_verified: bool,
                display_name: str, limit: int = 280) -> str:
    """Compose to fit. A draft that is 44 characters too long is not a failed
    draft — it is an untrimmed one. The STORY is what gets shortened (at a word
    boundary); the hook, the attribution and the link are structural and never
    truncated."""
    # Honour a human "too wordy" by lowering the target, but only when the caller
    # took the default — an explicit limit is the caller's decision, not ours.
    if limit == 280 and "too_wordy" in avoid_guidance():
        limit = TOO_WORDY_LIMIT
    cw = row.get("colorway") or ""
    year, retail = row.get("year"), row.get("retail_price")
    frag_full = _story_fragment(row.get("description") or "")
    title = '%s “%s”' % (display_name, cw) if cw else display_name
    attr = ("Its card is in CYPHER — the est. value on it tracks the real pair's "
            "resale, not the card.")

    def assemble(frag: str) -> str:
        if fmt == "on_this_day":
            lead = "%d years ago, the %s dropped at $%s." % (
                _now_year() - int(year), title, retail)
        elif fmt == "price_journey" and price_verified:
            lead = "The %s retailed at $%s. Real pairs now trade around $%s." % (
                title, retail, row.get("estimated_resale"))
        elif fmt == "which_would_you_pull":
            # NOTE what is absent: year, retail, resale, frag. Two titles and a
            # question. There is no field here a price could travel in.
            other = row.get("pair_title") or ""
            lead = "%s or %s. %s" % (title, other, PULL_QUESTION)
        elif fmt == "set_completion":
            # NOTE the absence of `frag`. That is deliberate and load-bearing —
            # see the block comment on SET_LEAD_TEMPLATE.
            reqs = row.get("set_requirements") or []
            lead = SET_LEAD_TEMPLATE % (row.get("set_name") or "", title)
            if reqs:
                lead += " You need the %s." % _join_names(reqs)
        elif fmt == "grail_lore":
            lead = "%s. %s." % (title, frag) if frag else "%s." % title
        else:
            lead = "%s. $%s retail. %s." % (year, retail, frag) if frag \
                else "%s. $%s retail. %s." % (year, retail, title)
        # two_card_crop carries no value figure, so this format needs no
        # attribution sentence — and adding one would spend characters saying
        # something the image does not claim.
        if fmt == "which_would_you_pull":
            out = "%s\n\nFree: %s" % (lead, LINK)
            leaked = _MONEY_RX.findall(out)
            assert not leaked, \
                "which_would_you_pull produced a price reference %s — SOUL says two " \
                "cards, one question, NO PRICES, and this skeleton must be incapable " \
                "of saying otherwise" % leaked
            assert PULL_QUESTION in out, "the question IS the format"
            return out
        out = "%s\n\n%s\n\nFree: %s" % (lead, attr, LINK)
        if fmt == "set_completion":
            low = out.lower()
            assert SET_ROUTE_PHRASE in low, \
                "set_completion lost its route phrase — the route IS the claim"
            leaked = [m for m in rails.PULL_MARKERS if m in low]
            assert not leaked, \
                "set_completion produced pull language %s — a set reward cannot be " \
                "pulled, and this skeleton must be incapable of saying otherwise" % leaked
        return out

    text = assemble(frag_full)
    if weighted_len(text) <= limit:
        return text

    # Keep the MOST story that fits: walk words off the end (tidying dangling
    # function words each time, so we never emit "...told his story of."), and
    # take the first prefix that fits. Cutting straight to a clause boundary
    # threw away 78 characters of usable room on the Doernbecher draft.
    words = frag_full.split()
    while words:
        words.pop()
        cand = assemble(_tidy(" ".join(words)))
        if weighted_len(cand) <= limit:
            return cand
    for cut in _clause_prefixes(frag_full):      # fallback
        cand = assemble(cut)
        if weighted_len(cand) <= limit:
            return cand
    return assemble("")                     # story dropped entirely rather than overflow


def lead_is_specific(text: str, row: dict) -> tuple[bool, str]:
    """Ashton's swap test, mechanised.

    Remove the shoe's own identifiers from the first sentence. Whatever remains
    must still contain something concrete — a year, a dollar figure, or a proper
    noun (a designer, a collaborator, a place). If only generic adjectives
    survive, the sentence would describe any shoe with the name swapped."""
    lead = re.split(r"(?<=[.!?])\s+", text.strip())[0]
    stripped = lead
    for token in filter(None, [row.get("name"), row.get("colorway"),
                               row.get("silhouette"), row.get("brand")]):
        stripped = re.sub(re.escape(token), " ", stripped, flags=re.I)
    has_year = re.search(r"\b(19|20)\d{2}\b", stripped) is not None
    has_money = re.search(r"\$\s?[\d,]+", stripped) is not None
    has_proper = re.search(r"\b[A-Z][a-z]{2,}\b", stripped) is not None
    words = [w.lower() for w in re.findall(r"[a-z]+", stripped, re.I)]
    only_generic = words and all(w in GENERIC_LEAD_WORDS or len(w) <= 3 for w in words)
    if only_generic:
        return False, "lead is generic filler once the shoe name is removed"
    if not (has_year or has_money or has_proper):
        return False, "lead carries no year, price, or proper noun — swap test fails"
    sig = []
    if has_year: sig.append("year")
    if has_money: sig.append("price")
    if has_proper: sig.append("proper noun")
    return True, "specific (%s)" % ", ".join(sig)


# ── (b) DROPS SELECTIVITY ────────────────────────────────────────────────────
# An RSS match alone is not a reason to post. Encoded form of Ashton's test:
# "would sneaker Twitter already be talking about this today?"
MOMENT_SIGNALS = [r"\brelease date\b", r"\bofficial (images|look)\b", r"\bfirst look\b",
                  r"\bunveil(s|ed)?\b", r"\breveal(s|ed)?\b", r"\bconfirm(s|ed)?\b",
                  r"\breturn(s|ing)?\b", r"\bcollab\w*\b", r"\bexclusive\b",
                  r"\banniversar\w+\b", r"\bretro\b", r"\bgrail\b"]
ROUTINE_SIGNALS = [r"\brestock\b", r"\bback in stock\b", r"\bnow available\b",
                   r"\bon sale\b", r"\bdiscount\b", r"\bwhere to buy\b",
                   r"\bshop\b", r"\bstyle guide\b", r"\bhow to\b"]


def is_moment(headline: str) -> tuple[bool, str]:
    """A routine restock is not a moment, even when the shoe matches perfectly."""
    h = headline.lower()
    for pat in ROUTINE_SIGNALS:
        m = re.search(pat, h)
        if m:
            return False, "routine coverage (%r) — not a moment" % m.group(0)
    for pat in MOMENT_SIGNALS:
        m = re.search(pat, h)
        if m:
            return True, "moment signal %r" % m.group(0)
    return False, "no moment signal in headline — sneaker Twitter is not on this today"
