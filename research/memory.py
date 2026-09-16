#!/usr/bin/env python3.12
"""
memory.py — the loader for ~/.hermes/profiles/cyphermarketer/memory.md (E2.5).

★★ THE CONTRACT WAS IN PROSE AND NOTHING ENFORCED IT.
memory.md has said since it was written that a `pending: true` entry may never
inform a draft. Nothing read the file, so the sentence was true by accident.
That is the inert-rail shape a third time — a rule that cannot fail is not a
rule — and this module exists to make it fail.

RANK 5 OF 5. SOUL.md > rails.py > instructions.md > context.md > memory.md.
An entry here is EVIDENCE, never instruction. It may motivate a change to
instructions.md; it may never override one. for_prompt() labels it as such in
the text the writer actually sees, because a list of facts pasted under a system
prompt reads as instruction unless it says otherwise.

THE POSITIVE FILTER — the same shape as moments.PROPOSABLE_SENSITIVITIES and
dossier.PROPOSABLE_DOSSIER_SENSITIVITIES. An entry loads only when ALL of:

    pending      is the literal `false`   (not absent, not "no", not "False ")
    approved_by  == "ashton"
    approved_on  parses as an ISO date

Anything else does not load: a missing field, a malformed date, a different
approver, a `pending` value nobody anticipated. FAIL CLOSED, always, per field.
A blocklist would admit a new field shape by default; this cannot.

★ THE AGENT MAY NEVER FLIP THE FLAG. There is no code path in this module that
WRITES to memory.md, and there must never be one. Writing a pending entry is a
file edit a session makes deliberately; approving one is Ashton's, by hand.
"""
from __future__ import annotations
import re
from datetime import date
from pathlib import Path

MEMORY = Path.home() / ".hermes/profiles/cyphermarketer/memory.md"
APPROVER = "ashton"                       # the only valid approver. Do not widen.
PENDING_FALSE = "false"                   # the literal that means approved
REQUIRED_FIELDS = ("pending", "approved_by", "approved_on")

# An entry heading. `M00N` in the file's own template has no third digit, so the
# template can never be parsed as an entry — the same trick the flip command
# uses, kept identical on purpose so the two cannot disagree.
ENTRY_RX = re.compile(r"^### (M\d{3}) — (.+)$")
FIELD_RX = re.compile(r"^([a-z_]+):\s*(.*)$")

MAX_ENTRIES_IN_PROMPT = 12                # a bound, so memory cannot balloon the
MAX_BODY_CHARS = 400                      # system prompt as the file grows


def _parse(text: str) -> list[dict]:
    """Every entry in the file, approved or not, with its raw fields.

    Fenced blocks are skipped: the file documents its own entry shape inside a
    ``` fence, and a parser that reads the documentation as data would be
    parsing an example that was never meant to load.
    """
    out, cur, fenced, in_fields = [], None, False, False
    for raw in text.splitlines():
        if raw.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = ENTRY_RX.match(raw)
        if m:
            if cur:
                out.append(cur)
            cur = {"id": m.group(1), "title": m.group(2).strip(),
                   "fields": {}, "body": []}
            in_fields = True
            continue
        if cur is None:
            continue
        if raw.startswith("### ") or raw.startswith("## "):
            out.append(cur); cur = None; in_fields = False
            continue
        if in_fields:
            fm = FIELD_RX.match(raw)
            if fm:
                cur["fields"][fm.group(1)] = fm.group(2).strip()
                continue
            if not raw.strip():
                in_fields = False
                continue
        cur["body"].append(raw)
    if cur:
        out.append(cur)
    for e in out:
        e["body"] = "\n".join(e["body"]).strip()
    return out


def _approved(e: dict) -> tuple[bool, str]:
    """The positive filter, one field at a time, each failing closed on its own."""
    f = e.get("fields") or {}
    for k in REQUIRED_FIELDS:
        if k not in f:
            return False, "missing field %r" % k
    if f["pending"] != PENDING_FALSE:
        # Deliberately an EQUALITY against the one literal that means approved.
        # `!= "true"` would admit "no", "0", "False", "" and anything a future
        # editor invents.
        return False, "pending is %r, not the literal %r" % (f["pending"], PENDING_FALSE)
    if f["approved_by"] != APPROVER:
        return False, "approved_by is %r, not %r" % (f["approved_by"], APPROVER)
    try:
        date.fromisoformat(f["approved_on"])
    except Exception:
        return False, "approved_on %r is not an ISO date" % f["approved_on"]
    return True, "approved"


def load(path: Path | None = None) -> tuple[list[dict], list[dict]]:
    """(entries that may inform a draft, rejections with reasons).

    A missing or unreadable file is an empty memory, not an error: memory is
    evidence and the pipeline must run without it. A MALFORMED entry, by
    contrast, is reported — silence about a broken entry is how a pending one
    would quietly become invisible rather than visibly withheld.
    """
    p = path or MEMORY
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as ex:
        return [], [{"id": None, "reason": "file_unreadable",
                     "detail": type(ex).__name__}]
    ok, bad = [], []
    for e in _parse(text):
        good, why = _approved(e)
        (ok if good else bad).append(e if good else
                                     {"id": e["id"], "reason": why})
    return ok, bad


def for_prompt(path: Path | None = None) -> str:
    """The block appended to the writer's system prompt. Approved entries only.

    Returns "" when nothing is approved — which is the file's state today and a
    correct one. An empty memory adds nothing to the prompt rather than adding a
    heading with nothing under it.
    """
    entries, _ = load(path)
    if not entries:
        return ""
    lines = [
        "WHAT WE HAVE LEARNED — EVIDENCE, NOT INSTRUCTION",
        "These are observations Ashton has approved. They may inform a choice "
        "between two good options. They never override SOUL.md, the rails, or "
        "the playbook, and 'this worked once' is not a rule.",
        "",
    ]
    for e in entries[:MAX_ENTRIES_IN_PROMPT]:
        body = " ".join(e["body"].split())
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS].rsplit(" ", 1)[0] + "…"
        lines.append("- %s — %s: %s" % (e["id"], e["title"], body))
    return "\n".join(lines)


def main() -> None:
    entries, rejections = load()
    print("  approved  : %d" % len(entries))
    for e in entries:
        print("     %s  %s" % (e["id"], e["title"][:66]))
    print("  withheld  : %d" % len(rejections))
    for r in rejections:
        print("     %-6s %s" % (r.get("id"), r["reason"]))


if __name__ == "__main__":
    main()
