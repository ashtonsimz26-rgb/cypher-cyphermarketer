#!/usr/bin/env python3.12
"""Stale-validator guards. Zero LLM, zero network, zero spend.

A stale validator DENIES, and denial produces no artifact, no error and no
symptom — the system just looks conservative. These tests exist because
moments.load_reachable() spent seven days validating against a file nothing
wrote, and returned set() on failure, which refuses every link one at a time.
"""
import ast, json, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research import moments as M
import daily_digest as DD

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent

def cache(payload):
    p = Path(tempfile.mkdtemp()) / "_reachable_cache.json"
    p.write_text(json.dumps(payload) if payload is not None else "{not json")
    return p

print("\n=== 1. THE READER FAILS CLOSED AND LOUD, NEVER EMPTY ===")
_orig = M.REACHABLE_CACHE
fresh = datetime.now(timezone.utc).isoformat()
cases = [
    ("missing",    Path("/nonexistent/_reachable_cache.json")),
    ("unreadable", cache(None)),
    ("undated",    cache({"image_names": ["a"]})),
    ("bare list",  cache(["a", "b"])),
    ("stale",      cache({"generated_at": (datetime.now(timezone.utc)
                                           - timedelta(days=8)).isoformat(),
                          "image_names": ["a"]})),
]
try:
    for label, p in cases:
        M.REACHABLE_CACHE = p
        try:
            got = M.load_reachable()
            ok(False, "a %s cache returned %r instead of raising" % (label, got))
        except M.ReachableCacheUnusable as e:
            ok("written by" in str(e) or "Regenerate" in str(e),
               "a %-11s cache raises AND names its writer" % label)
    M.REACHABLE_CACHE = cache({"generated_at": fresh, "image_names": ["a", "b"]})
    ok(M.load_reachable() == {"a", "b"}, "a fresh cache loads normally")
finally:
    M.REACHABLE_CACHE = _orig

print("\n=== 2. EMPTY IS NEVER A VALID ANSWER ===")
src = (REPO / "research" / "moments.py").read_text()
tree = ast.parse(src)
fn = next(n for n in ast.walk(tree)
          if isinstance(n, ast.FunctionDef) and n.name == "load_reachable")
returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
bare_empty = [r for r in returns if isinstance(r.value, ast.Call)
              and getattr(r.value.func, "id", "") == "set" and not r.value.args]
ok(not bare_empty, "load_reachable has no `return set()` path — an empty reference "
                   "set refuses every link rather than permitting them")
ok(any(isinstance(n, ast.Raise) for n in ast.walk(fn)), "it raises instead")

print("\n=== 3. THE CACHE NAMES ITS WRITER, IN THE FILE AND IN BOTH MODULES ===")
live = REPO / "state" / "_reachable_cache.json"
ok(live.exists(), "the live cache exists")
blob = json.loads(live.read_text())
ok(isinstance(blob, dict) and "_written_by" in blob and "_read_by" in blob,
   "the FILE says who writes and who reads it: %s" % blob.get("_written_by"))
ok("generated_at" in blob, "…and carries a timestamp so its age is checkable")
ok("REACHABLE_CACHE_WRITER" in src and "daily_digest" in src,
   "the READER names its writer in the module")
dsrc = (REPO / "daily_digest.py").read_text()
ok("REACHABLE_CACHE = HERE" in dsrc,
   "the WRITER uses a named constant — a literal path is invisible to a grep")
# ★ By AST. The first version of this check scanned dsrc for the path string and
# FAILED — on the comment in refresh_set_routes explaining that the file used to
# have no writer. Third time this session that a source scan matched its own
# prose (contracts.py). The rule is right; the habit is the problem.
dtree = ast.parse(dsrc)
literal_paths = 0
for node in ast.walk(dtree):
    if isinstance(node, ast.Constant) and node.value == "_reachable_cache.json":
        literal_paths += 1
ok(literal_paths <= 1,
   "the filename appears as a code literal at most once — in the constant, not "
   "re-derived at a write site (%d)" % literal_paths)

print("\n=== 4. THE OTHER SNAPSHOT AGES OUT TOO ===")
from research import dossier as DOS
ok(DOS.CATALOG_CACHE_MAX_AGE_DAYS == 7, "dossier's catalog cache has a max age")
dsrc2 = (REPO / "research" / "dossier.py").read_text()
lc = next(n for n in ast.walk(ast.parse(dsrc2))
          if isinstance(n, ast.FunctionDef) and n.name == "load_catalog")
ok("CATALOG_CACHE_MAX_AGE_DAYS" in ast.dump(lc),
   "load_catalog checks the age rather than only checking existence")
ok("st_mtime" in ast.dump(lc) or "st_mtime" in dsrc2, "…from the file's mtime")

print("\n=== 5. NO STATE FILE READ BY A CHECK IS WRITTEN BY NOTHING ===")
# The deliberate sweep, kept as a test so a NEW orphan fails here.
import re
py = [p for p in REPO.rglob("*.py")
      if "__pycache__" not in str(p) and "_backups" not in str(p)]
text = {p: p.read_text(encoding="utf-8", errors="ignore") for p in py}
alltext = "\n".join(text.values())
orphans = []
for f in (REPO / "state").glob("*.json"):
    name = f.name
    if name in ("_dq.sql", "_q.sql"):
        continue
    written = any(re.search(r"%s[^\n]*write_text|write_text[^\n]*%s" % (re.escape(name), re.escape(name)), t)
                  or (name in t and "write_text" in t) for t in text.values())
    referenced = name in alltext
    if referenced and not written:
        orphans.append(name)
ok(not orphans, "every referenced state/*.json has a writer in the repo: %s" % (orphans or "none orphaned"))

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
