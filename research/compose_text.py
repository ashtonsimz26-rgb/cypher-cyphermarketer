#!/usr/bin/env python3.12
"""
compose_text.py — assembles a post from parts (F4.2). ZERO LLM. Pure assembly.

★★ THE WRITER NEVER AUTHORS THE ATTRIBUTION SENTENCE.
   rails.check_draft demands an attribution marker in EVERY post, because
   card_shows_value=True is unconditional — the card render always displays
   EST. VALUE, so the text must always scope that figure to the real sneaker.

   Trap, measured in F4 GROUND: the check is `any(m in low for m in
   ATTRIBUTION_MARKERS)` — PLAIN SUBSTRING, not has_phrase — and "resale" ALONE
   IS NOT A MARKER. Only "resale market" and "real-world resale" contain it. So
   the most natural phrasing a model would reach for, "tracks its resale, not
   the card", FAILS the rail. No amount of prompt instruction reliably beats
   that, so the model is never asked: it writes the LEAD, and this module
   appends the attribution from a FROZEN set it cannot reach.

   That is what turns gate 8 from a coin flip on phrasing into a real check on
   the lead. Every member of ATTRIBUTION_LINES is asserted rails-passing by the
   test suite, so an edit that silently drops a marker fails the tests rather
   than production.

★★ MOMENT TEXT IS BYTE-IDENTICAL TO THE FILE, OR WE HALT.
   A verified moment's prose is the only text in this system that has passed
   HUMAN judgment against a FETCHED SOURCE. assert_moment_verbatim() RE-READS
   data/moments.json FROM DISK at compose time and compares bytes. It
   deliberately does NOT compare against an in-memory copy loaded earlier in the
   run: an in-memory comparison would pass even if the loader mutated the
   string, which is exactly the failure it exists to catch. A mismatch raises
   MomentTextMismatch — a HALT, never a warning.
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MOMENTS = HERE / "data" / "moments.json"
LINK = "https://apps.apple.com/app/cypher-unlock-the-vault/id6761334111"

# ── the frozen attribution set ───────────────────────────────────────────────
# A TUPLE, not a list: it cannot be appended to at runtime. Every member must
# satisfy rails' has_attr; the suite asserts it for all of them.
# [0] is the default and is the exact line shipped in production to date.
# [0] is the production default (ruled 2026-09-10). It replaced the longer
# "est. value ... tracks the real pair's resale" line, which read as a
# disclaimer and doubled est.value/resale; this one works identically whether
# or not the text mentioned a price, and returns 13 characters to the lead.
ATTRIBUTION_LINES: tuple[str, ...] = (
    "Its card is in CYPHER. That estimate is for the real pair, not for the card.",
    "Its card is in CYPHER — the est. value on it tracks the real pair's resale, not the card.",
    "Its card is in CYPHER. The estimate on the card follows the real pair, not the card.",
    "Its card is in CYPHER — the number on it is the real pair's market, not the card's.",
)
DEFAULT_ATTRIBUTION = 0


class MomentTextMismatch(AssertionError):
    """Composed moment text differs from data/moments.json. HALT."""


def attribution(index: int = DEFAULT_ATTRIBUTION) -> str:
    return ATTRIBUTION_LINES[index]


def _moment_text_on_disk(moment_id: str, path: Path | None = None) -> str | None:
    """Re-read from DISK. Never from a caller's in-memory copy — see docstring."""
    path = path or MOMENTS
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return None
    for entries in (raw.get("moments") or {}).values():
        for e in entries:
            if e.get("id") == moment_id:
                return e.get("text")
    return None


def assert_moment_verbatim(moment_id: str, composed: str,
                           path: Path | None = None) -> None:
    """HALT unless the on-disk moment text appears byte-for-byte in `composed`."""
    on_disk = _moment_text_on_disk(moment_id, path)
    if on_disk is None:
        raise MomentTextMismatch(
            "moment %r not found in %s — cannot verify verbatim carriage"
            % (moment_id, (path or MOMENTS).name))
    if on_disk.encode("utf-8") not in composed.encode("utf-8"):
        raise MomentTextMismatch(
            "moment %r text is NOT byte-identical to the file.\n  file    : %r\n"
            "  composed: %r" % (moment_id, on_disk, composed))


REPLY_TEXT = "Free on the App Store: %s" % LINK
"""The link LEAVES the post body (ruled 2026-09-10). A post containing a URL
costs $0.20 on X vs $0.015 without — 13x — against a $15/cycle cap, and link
posts are the most reach-suppressed shape on the platform. It ships as
reply_text in the proposal for Ashton to post as a first reply by hand; the
auto-reply mechanic is a later commit."""


def compose(*, lead: str | None = None, body: str | None = None,
            moment_text: str | None = None, moment_id: str | None = None,
            linking_line: str | None = None,
            attribution_index: int = DEFAULT_ATTRIBUTION,
            include_link: bool = False, moments_path: Path | None = None) -> str:
    """Assemble the post.

    MOMENT DAY  -> moment_text VERBATIM, then the writer's linking_line (which
                   is the ONLY part gates (b) and 8 evaluate), then attribution.
                   A failed linking line is dropped, not fatal: an approved
                   moment plus a card is already a complete post.
    NORMAL DAY  -> lead (+ optional body), then attribution.
    """
    parts: list[str] = []
    if moment_text is not None:
        parts.append(moment_text.strip())
        if linking_line:
            parts.append(linking_line.strip())
    else:
        if not (lead or "").strip():
            raise ValueError("a non-moment post needs a lead")
        parts.append(lead.strip())
        if body and body.strip():
            parts.append(body.strip())
    parts.append(attribution(attribution_index))
    if include_link:
        parts.append("Free: %s" % LINK)
    out = "\n\n".join(parts)
    if moment_text is not None and moment_id:
        assert_moment_verbatim(moment_id, out, moments_path)   # HALT on drift
    return out
