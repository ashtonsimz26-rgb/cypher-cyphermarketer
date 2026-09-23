#!/usr/bin/env python3.12
"""atomicio.py — write a file so a concurrent reader sees the old copy or the new, never half.

A plain Path.write_text() truncates the file and then writes it. A reader that opens
it in between reads a PREFIX — for a JSON cache, a parse error. The three state/
caches (_set_routes.json, _reachable_cache.json, _catalog_cache.json) are written by
one job and read by others, and every reader fails CLOSED on a malformed file:
rails would refuse every card as unobtainable, moments would raise. So a torn read
does no damage, but it silently empties a run — and the run_all data guard cannot
see this class at all, because a half-read looks like corruption, not like a
changed file.

write_text_atomic() writes to a temp file IN THE SAME DIRECTORY (so the rename never
crosses a filesystem), flushes and fsyncs it, then os.replace()s it onto the target.
rename(2) within one filesystem is atomic. On any failure the temp file is removed
and the target is left exactly as it was.
"""
from __future__ import annotations
import os
import tempfile
from pathlib import Path


def write_text_atomic(path: Path | str, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".%s." % path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
