#!/usr/bin/env python3.12
"""The three state/ caches are written ATOMICALLY. Zero network; scratch files only.

A reader must see the old cache or the new one, never half. The run_all data guard
cannot catch this class — a torn read looks like corruption, not like a changed
file — so it is held here instead: the helper's semantics, a live reader racing a
writer, and a structural check that all three cache writes go through the helper.
"""
import ast, json, sys, tempfile, threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from atomicio import write_text_atomic  # noqa: E402

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

T = Path(tempfile.mkdtemp())

print("\n=== 1. it writes, and leaves nothing behind ===")
f = T / "cache.json"
write_text_atomic(f, '{"v": 1}\n')
ok(f.read_text() == '{"v": 1}\n', "content written")
write_text_atomic(f, '{"v": 2}\n')
ok(f.read_text() == '{"v": 2}\n', "overwrite replaces it")
ok(sorted(p.name for p in T.iterdir()) == ["cache.json"], "no temp file left in the directory")

print("\n=== 2. a failed write leaves the original EXACTLY as it was ===")
try:
    write_text_atomic(f, object())                 # fh.write raises TypeError mid-write
    ok(False, "a non-str payload should raise")
except TypeError:
    ok(f.read_text() == '{"v": 2}\n', "original untouched after the failure")
    ok(sorted(p.name for p in T.iterdir()) == ["cache.json"], "the temp file was removed")

print("\n=== 3. a reader racing a writer never parses half a file ===")
big = [json.dumps({"k": i, "pad": "x" * 400_000}) for i in range(2)]   # ~400 KB each
g = T / "race.json"; write_text_atomic(g, big[0])
stop = threading.Event(); torn = [0]; reads = [0]
def reader():
    while not stop.is_set():
        try:
            json.loads(g.read_text()); reads[0] += 1
        except Exception:
            torn[0] += 1
th = threading.Thread(target=reader); th.start()
for i in range(300):
    write_text_atomic(g, big[i % 2])
stop.set(); th.join()
ok(reads[0] > 0 and torn[0] == 0, "atomic: %d reads during 300 rewrites, %d torn" % (reads[0], torn[0]))

print("\n=== 4. all three caches are written through the helper ===")
def calls_in(path, fn_name):
    tree = ast.parse((REPO / path).read_text())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == fn_name)
    atomic = [a.args[0].id for a in ast.walk(fn) if isinstance(a, ast.Call)
              and getattr(a.func, "id", "") == "write_text_atomic"
              and a.args and isinstance(a.args[0], ast.Name)]
    plain = [a.func.value.id for a in ast.walk(fn) if isinstance(a, ast.Call)
             and getattr(a.func, "attr", "") in ("write_text", "write_bytes")
             and isinstance(getattr(a.func, "value", None), ast.Name)]
    return atomic, plain
a, p = calls_in("daily_digest.py", "refresh_set_routes")
ok(set(a) == {"SET_ROUTES", "REACHABLE_CACHE"}, "refresh_set_routes writes both caches atomically: %s" % a)
ok(not {"SET_ROUTES", "REACHABLE_CACHE"} & set(p), "…and never with a plain write_text: %s" % p)
a, p = calls_in("research/dossier.py", "load_catalog")
ok(a == ["CATALOG_CACHE"], "load_catalog writes the catalog cache atomically: %s" % a)
ok("CATALOG_CACHE" not in p, "…and never with a plain write_text: %s" % p)

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
