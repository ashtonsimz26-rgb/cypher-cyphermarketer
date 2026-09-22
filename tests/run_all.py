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
import hashlib
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


# ══ THE DATA GUARD (2026-09-22) ═══════════════════════════════════════════════
# ★★ A SUITE THAT PASSES WHILE WRITING PRODUCTION DATA HAS NOT PASSED.
# In one session two suites were found doing exactly that: test_cypher_resolver
# appended six fake rows to ledger/research.jsonl on every run (368 of them),
# and test_images_switch wrote a fake rejection into state/reject_reasons.json —
# the file the drafter reads as Ashton's feedback. The summary said "28 passed"
# over both. That is this file's founding lesson one level down: the report was
# honest about exit codes and blind to the damage.
#
# So every file under ledger/ and state/ is hashed before and after EACH suite.
# Any change — modified, added or deleted — fails the run, names the suite, and
# for an append-only .jsonl shows the rows it appended. There is no allowlist:
# scratch belongs in a temp dir, never in state/ (the three scratch .sql writers
# were moved out for exactly this reason). A live marketer job that happens to
# write mid-suite is NOT excused either — its name is printed beside the change
# so the collision is diagnosable, and a re-run settles it.
REPO = HERE.parent
GUARDED = ("ledger", "state")
LOGS = REPO / "logs"


def snapshot() -> dict[str, tuple[int, str]]:
    out: dict[str, tuple[int, str]] = {}
    for d in GUARDED:
        root = REPO / d
        if not root.exists():
            continue
        for f in sorted(root.rglob("*")):
            if f.is_file():
                b = f.read_bytes()
                out[str(f.relative_to(REPO))] = (len(b), hashlib.sha256(b).hexdigest())
    return out


def diff(before: dict, after: dict) -> list[str]:
    lines: list[str] = []
    for k in sorted(set(before) | set(after)):
        if k not in after:
            lines.append("  D %s  (deleted)" % k)
        elif k not in before:
            lines.append("  A %s  (new, %d bytes)" % (k, after[k][0]))
        elif before[k] != after[k]:
            n0, h0 = before[k]
            data = (REPO / k).read_bytes()
            if len(data) > n0 and hashlib.sha256(data[:n0]).hexdigest() == h0:
                added = data[n0:].decode("utf-8", "replace").splitlines()
                lines.append("  M %s  (+%d line%s appended)" % (k, len(added), "" if len(added) == 1 else "s"))
                lines.extend("      + %s" % l[:150] for l in added[:3])
                if len(added) > 3:
                    lines.append("      + … %d more" % (len(added) - 3))
            else:
                lines.append("  M %s  (rewritten: %d -> %d bytes)" % (k, n0, len(data)))
    return lines


def live_jobs_since(t0: float) -> list[str]:
    """Marketer launchd jobs whose logs moved since t0 — they write ledger/ and
    state/ on their own schedule, so a change may be theirs rather than a test's."""
    if not LOGS.exists():
        return []
    return sorted({f.name.split(".")[1] for f in LOGS.glob("ai.cyphermarketer.*.log")
                   if f.stat().st_mtime >= t0})


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
    t_start = time.time()
    results, damage = [], []
    snap = snapshot()
    for p in files:
        results.append(run_one(p))
        after = snapshot()
        d = diff(snap, after)
        if d:
            damage.append((p.name, d))
        snap = after
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
    if damage:                     # never let the count stand alone over damage
        line += "  — ⛔ DATA GUARD FAILED: %d suite(s) changed real data" % len(damage)
    print(line)
    if skipped:
        for name, _, _, out in skipped:
            print("  SKIPPED %-30s %s" % (name, _skip_reason(out)))
    if failed:
        print("%d FAILED: %s" % (len(failed), ", ".join(f[0] for f in failed)))
    if damage:
        print("\n" + "=" * 62)
        print("⛔ DATA GUARD FAILED — the suite changed REAL data under %s/."
              % "/ and ".join(GUARDED))
        print("   The pass count above does not stand: a suite that writes production")
        print("   data has not passed. Tests must write to scratch (tempfile).")
        for name, d in damage:
            print("\n  during %s:" % name)
            print("\n".join(d))
        jobs = live_jobs_since(t_start)
        if jobs:
            print("\n  live marketer job(s) also ran during the suite: %s — a change may be"
                  " theirs, not a test's. Re-run to confirm." % ", ".join(jobs))
    else:
        print("data guard: ledger/ and state/ unchanged (%d suites checked)" % len(results))
    return 1 if (failed or damage) else 0


if __name__ == "__main__":
    sys.exit(main())
