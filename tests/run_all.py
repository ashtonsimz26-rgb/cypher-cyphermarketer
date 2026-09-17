#!/usr/bin/env python3.12
"""
run_all.py — the suite runner, and the only honest source of "N suites green".

★★ WHY THIS FILE EXISTS. For a day the suite was run with:

    for t in tests/test_*.py; do python3.12 "$t" >/dev/null 2>&1 || echo "FAIL $t"; done
    echo "18 suites clean"

That last line is unconditional. It printed "18 suites clean" directly beneath
"FAIL tests/test_story_scenes.py", and a commit went out on the strength of it.

A REPORT THAT CANNOT REPORT FAILURE IS THE REPORTING-LAYER VERSION OF A RAIL
THAT CANNOT FAIL — and it is worse, because a rail that cannot fail launders one
check while a summary that cannot fail LAUNDERS EVERY CHECK BENEATH IT. Eighteen
honest suites reported by a dishonest line are eighteen results you cannot use.

So: the count is DERIVED from results, the exit code is non-zero on any failure,
and there is no string in this file that says "green" without having counted.
"""
from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TIMEOUT = 300


def discover() -> list[Path]:
    return sorted(p for p in HERE.glob("test_*.py"))


def run_one(p: Path) -> tuple[str, int, float, str]:
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, str(p)], capture_output=True,
                           text=True, timeout=TIMEOUT, cwd=str(HERE.parent))
        code, out = r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        code, out = 124, "TIMEOUT after %ds" % TIMEOUT
    return p.name, code, time.time() - t0, out


def main() -> int:
    files = discover()
    if not files:
        print("NO TEST FILES FOUND — refusing to report success over an empty set")
        return 2
    results = [run_one(p) for p in files]
    passed = [r for r in results if r[1] == 0]
    failed = [r for r in results if r[1] != 0]

    for name, code, secs, _ in results:
        print("  %-34s %-5s %5.1fs" % (name, "PASS" if code == 0 else "FAIL", secs))

    for name, code, _, out in failed:
        print("\n" + "=" * 62)
        print("FAILING: %s  (exit %d)" % (name, code))
        tail = [l for l in out.splitlines() if l.strip()][-14:]
        print("\n".join("  " + l for l in tail))

    # ★ Counted, never asserted. len(passed) cannot disagree with the exit codes.
    print("\n%d of %d suites passed." % (len(passed), len(results)))
    if failed:
        print("%d FAILED: %s" % (len(failed), ", ".join(f[0] for f in failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
