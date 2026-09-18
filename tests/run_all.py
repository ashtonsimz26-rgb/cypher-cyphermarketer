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

# A suite exits 77 to say "I did not run". Borrowed from the autotools
# convention so it cannot collide with a real failure code.
SKIP_EXIT = 77


def _skip_reason(out: str) -> str:
    for line in (out or "").splitlines():
        if line.startswith("SKIP:"):
            return line[len("SKIP:"):].strip()
    return "no reason given"


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
    # ★ SKIP IS ITS OWN OUTCOME (2026-09-17). Exit 77 means "this suite did not
    # run", and it must never be counted as a pass. A suite whose live
    # dependency was unreachable has told us NOTHING, and a summary that prints
    # "21 of 21 passed" over it is the same defect as the unconditional
    # "18 suites clean" this file was written about — one level down, and
    # harder to see, because the skipped suite is usually the one that checks
    # the thing that drifts.
    skipped = [r for r in results if r[1] == SKIP_EXIT]
    passed = [r for r in results if r[1] == 0]
    failed = [r for r in results if r[1] not in (0, SKIP_EXIT)]

    for name, code, secs, _ in results:
        label = "PASS" if code == 0 else ("SKIP" if code == SKIP_EXIT else "FAIL")
        print("  %-34s %-5s %5.1fs" % (name, label, secs))

    for name, code, _, out in failed:
        print("\n" + "=" * 62)
        print("FAILING: %s  (exit %d)" % (name, code))
        tail = [l for l in out.splitlines() if l.strip()][-14:]
        print("\n".join("  " + l for l in tail))

    # ★ Counted, never asserted. These cannot disagree with the exit codes.
    line = "\n%d passed" % len(passed)
    if skipped:
        reasons = sorted({_skip_reason(o) for _, _, _, o in skipped})
        line += ", %d skipped (%s)" % (len(skipped), "; ".join(reasons))
    if failed:
        line += ", %d failed" % len(failed)
    line += "  [%d suite%s]" % (len(results), "" if len(results) == 1 else "s")
    print(line)
    if skipped:
        for name, _, _, out in skipped:
            print("  SKIPPED %-30s %s" % (name, _skip_reason(out)))
    if failed:
        print("%d FAILED: %s" % (len(failed), ", ".join(f[0] for f in failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
