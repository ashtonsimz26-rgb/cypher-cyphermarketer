#!/usr/bin/env python3.12
"""Shared helper: probe the live DB cheaply, or SKIP loudly.

★ A LIVE SUITE MUST NEVER PASS BY DEFAULT. If the database is unreachable the
suite has established nothing, and exiting 0 would make "did not run" look
identical to "ran and passed" — the summary-line defect one level down. So an
unreachable DB exits 77, which tests/run_all.py counts as SKIPPED, prints by
name, and never folds into the pass count.

The probe uses a SHORT timeout on purpose. The full suite timeout is 300s, and
tonight's intermittent failure was a 300s hang under load that read as a
failure. A fast probe turns a slow database into an immediate, legible skip.
"""
import subprocess, sys
from pathlib import Path

PROBE_TIMEOUT = 25          # seconds; the suite timeout is 300
SKIP_EXIT = 77


def skip(reason: str) -> None:
    print("SKIP: %s" % reason)
    sys.exit(SKIP_EXIT)


def require_db() -> None:
    """Cheap `select 1` against the linked project, or skip."""
    # a temp file, never state/ — the run_all data guard fails on ANY change there
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".sql", encoding="utf-8", delete=False) as fh:
        fh.write("select 1 as ok;"); f = Path(fh.name)
    try:
        p = subprocess.run(
            ["supabase", "db", "query", "--linked", "-o", "json", "-f", str(f)],
            capture_output=True, text=True, timeout=PROBE_TIMEOUT,
            cwd=str(Path.home() / "Documents/openclaw/CYPHER"))
    except subprocess.TimeoutExpired:
        skip("live DB unreachable (probe timed out after %ds)" % PROBE_TIMEOUT)
    except FileNotFoundError:
        skip("live DB unreachable (supabase CLI not on PATH)")
    finally:
        f.unlink(missing_ok=True)
    if p.returncode != 0:
        skip("live DB unreachable (probe exit %d)" % p.returncode)
