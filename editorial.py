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

# Copy skeletons. `which_would_you_pull` is DECLARED but not yet selectable —
# it needs a two-card composite the compositor does not build yet. Listing it
# without implementing it would silently reduce the rotation to a lie.
FORMATS = ["story_spotlight", "price_journey", "on_this_day", "grail_lore"]
DECLARED_NOT_READY = {"which_would_you_pull": "needs a two-card composite (compose.py is single-card)"}

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


def detect_hook(row: dict, *, source: str, price_verified: bool,
                headline: str = "") -> tuple[str | None, str]:
    """Return (hook_type, human-readable hook) or (None, reason-to-skip).

    Order matters: the most specific, most time-relevant hook wins."""
    desc = row.get("description") or ""
    year = row.get("year")
    retail, resale = row.get("retail_price"), row.get("estimated_resale")

    if source in ("drop_correspondent", "drop_overnight") and headline:
        return "drop_moment", "matched today's headline: %s" % headline[:70]

    if source == "on_this_day" and isinstance(year, int):
        return "on_this_day", "%d — %d years ago" % (year, _now_year() - year)

    # A HUMAN story outranks a number. Leading with "3.4x retail" on a shoe a
    # sick kid designed for a children's hospital is tone-deaf, and no rails
    # check would have caught it — so the priority itself has to be right.
    for pat, label in STRONG_STORY_MARKERS:
        m = re.search(pat, desc)
        if m:
            return "story", "%s — %r" % (label, m.group(0)[:48])

    if price_verified and retail and resale and resale >= retail * 3:
        return "price_journey", "PK-verified $%d retail -> $%d resale (%.1fx)" % (
            retail, resale, resale / retail)

    for pat, label in STORY_MARKERS:
        m = re.search(pat, desc)
        if m:
            return "story", "%s — %r" % (label, m.group(0)[:48])

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
        elif fmt == "grail_lore":
            lead = "%s. %s." % (title, frag) if frag else "%s." % title
        else:
            lead = "%s. $%s retail. %s." % (year, retail, frag) if frag \
                else "%s. $%s retail. %s." % (year, retail, title)
        return "%s\n\n%s\n\nFree: %s" % (lead, attr, LINK)

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
