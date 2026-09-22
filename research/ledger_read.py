#!/usr/bin/env python3.12
"""ledger_read.py — the ONE reader of ledger/research.jsonl that honours retractions.

research.jsonl is append-only: a row is never edited or deleted. When rows turn
out to record no real event (test contamination, 2026-09-22), the correction is
itself an appended row — event "retraction" — that names every row it withdraws
by 1-based LINE NUMBER and the SHA-256 of that line's exact text. Line numbers
are stable because the file only grows. The hash makes the claim checkable: if
a listed line no longer hashes to what the retraction recorded, the ledger has
been rewritten underneath it, and this reader REFUSES rather than guessing which
row was meant.

    rows()                      -> live rows: retracted rows and retraction rows removed
    rows(include_retracted=True)-> every row, as written (the audit view)

Any future consumer of research.jsonl should read through rows(), not open the
file directly — a direct read silently counts the retracted rows back in.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
LEDGER = HERE / "ledger" / "research.jsonl"
RETRACTION = "retraction"


class RetractionMismatch(RuntimeError):
    """A retraction names a line whose text no longer matches its recorded hash."""


def line_hash(line: str) -> str:
    """SHA-256 of one ledger line's exact text, without its trailing newline."""
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def retracted_lines(path: Path | None = None) -> dict[int, str]:
    """{line_number: sha256} for every row withdrawn by a retraction row, verified."""
    lines = _lines(path or LEDGER)
    out: dict[int, str] = {}
    for raw in lines:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        if r.get("event") != RETRACTION:
            continue
        for item in r.get("rows") or []:
            n, h = int(item["line"]), item["sha256"]
            if not 1 <= n <= len(lines) or line_hash(lines[n - 1]) != h:
                raise RetractionMismatch(
                    "retraction names line %d with sha256 %s…, but that line %s — the "
                    "ledger was rewritten under it; refusing to guess"
                    % (n, h[:12], "does not exist" if not 1 <= n <= len(lines)
                       else "now hashes to %s…" % line_hash(lines[n - 1])[:12]))
            out[n] = h
    return out


def rows(path: Path | None = None, include_retracted: bool = False) -> list[dict]:
    p = path or LEDGER
    lines = _lines(p)
    skip = set() if include_retracted else set(retracted_lines(p))
    out: list[dict] = []
    for i, raw in enumerate(lines, start=1):
        try:
            r = json.loads(raw)
        except Exception:
            continue
        if include_retracted:
            out.append(r)
        elif i not in skip and r.get("event") != RETRACTION:
            out.append(r)
    return out
