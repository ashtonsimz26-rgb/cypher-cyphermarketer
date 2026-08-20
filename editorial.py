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

HERE = Path(__file__).resolve().parent
FORMAT_STATE = HERE / "state" / "last_format.json"
LINK = "https://apps.apple.com/app/cypher-unlock-the-vault/id6761334111"

# Copy skeletons. `which_would_you_pull` is DECLARED but not yet selectable —
# it needs a two-card composite the compositor does not build yet. Listing it
# without implementing it would silently reduce the rotation to a lie.
FORMATS = ["story_spotlight", "price_journey", "on_this_day", "grail_lore"]
DECLARED_NOT_READY = {"which_would_you_pull": "needs a two-card composite (compose.py is single-card)"}

# Signals that a catalog description actually carries a STORY rather than specs.
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


def choose_format(hook_type: str) -> str:
    """Prefer the format matching the hook; never repeat the previous skeleton."""
    preferred = {"on_this_day": "on_this_day", "price_journey": "price_journey",
                 "grail_lore": "grail_lore", "drop_moment": "story_spotlight",
                 "story": "story_spotlight"}[hook_type]
    if preferred != last_format():
        return preferred
    for f in FORMATS:                       # rotate off the repeat
        if f != last_format():
            return f
    return preferred


def _story_fragment(desc: str) -> str:
    """First sentence of the catalog description, trimmed — that is the story."""
    s = re.split(r"(?<=[.!?])\s+", (desc or "").strip())
    frag = s[0] if s else ""
    return frag.rstrip(".").strip()


def build_draft(row: dict, hook_type: str, fmt: str, *, price_verified: bool,
                display_name: str) -> str:
    cw = row.get("colorway") or ""
    year, retail = row.get("year"), row.get("retail_price")
    frag = _story_fragment(row.get("description") or "")
    title = '%s “%s”' % (display_name, cw) if cw else display_name
    attr = ("Its card is in CYPHER — the est. value on it tracks the real pair's "
            "resale, not the card.")

    if fmt == "on_this_day":
        lead = "%d years ago, the %s dropped at $%s." % (_now_year() - int(year), title, retail)
    elif fmt == "price_journey" and price_verified:
        lead = "The %s retailed at $%s. Real pairs now trade around $%s." % (
            title, retail, row.get("estimated_resale"))
    elif fmt == "grail_lore":
        lead = "%s. %s." % (title, frag)
    else:                                    # story_spotlight
        lead = "%s. $%s retail. %s." % (year, retail, frag)
    return "%s\n\n%s\n\nFree: %s" % (lead, attr, LINK)


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
