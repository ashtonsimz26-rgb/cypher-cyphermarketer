#!/usr/bin/env python3.12
"""The run_all DATA GUARD catches a suite that writes real data. Zero network.

A guard that has never been seen to fire is a rail nobody has tested. This suite
fires it on purpose, against a SCRATCH copy of the ledger/ and state/ layout —
never the real one — using run_all's own main(): one clean fake suite and one
that appends a row to a ledger, exactly the shape test_cypher_resolver had.
"""
import io, sys, tempfile, contextlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_all as RA  # noqa: E402

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

T = Path(tempfile.mkdtemp())
(T / "ledger").mkdir(); (T / "state").mkdir(); (T / "logs").mkdir(); (T / "suites").mkdir()
(T / "ledger" / "x.jsonl").write_text('{"event": "real"}\n')
(T / "state" / "s.json").write_text('{"a": 1}\n')
RA.REPO, RA.LOGS = T, T / "logs"          # the guard now watches the scratch layout only

clean = T / "suites" / "test_clean.py"
clean.write_text("import sys; sys.exit(0)\n")
leaky = T / "suites" / "test_leaky.py"
leaky.write_text("open(%r, 'a').write('{\"event\": \"cypher_uri_malformed\", \"uri\": \"cypher://listing/x/y\"}\\n')\n"
                 % str(T / "ledger" / "x.jsonl"))

def run(files):
    RA.discover = lambda: files
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = RA.main()
    return code, buf.getvalue()

print("\n=== 1. a clean suite passes the guard ===")
code, out = run([clean])
ok(code == 0 and "data guard: ledger/ and state/ unchanged" in out, "clean -> exit 0, guard says unchanged")

print("\n=== 2. a suite that appends to a ledger FAILS the run, though it exits 0 ===")
code, out = run([clean, leaky])
ok(code == 1, "leaky suite exited 0 but the run exits 1")
import re
summary = [l for l in out.splitlines() if re.match(r"^\d+ passed", l)]
ok(len(summary) == 1 and "DATA GUARD FAILED" in summary[0],
   "the counted summary line itself carries the guard failure: %r" % (summary[:1],))
ok("during test_leaky.py" in out and "during test_clean.py" not in out,
   "the guard names the suite that wrote, and only that one")
ok("+1 line appended" in out and "cypher://listing/x/y" in out, "it shows the appended row")

print("\n=== 3. added, deleted and rewritten files are caught too ===")
before = RA.snapshot()
(T / "state" / "new.json").write_text("{}")
(T / "state" / "s.json").write_text('{"a": 2}\n')          # rewritten, same size
(T / "ledger" / "x.jsonl").unlink()
d = "\n".join(RA.diff(before, RA.snapshot()))
ok("A state/new.json" in d, "new file -> A")
ok("M state/s.json" in d and "rewritten" in d, "rewrite in place -> M rewritten")
ok("D ledger/x.jsonl" in d, "deleted file -> D")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
