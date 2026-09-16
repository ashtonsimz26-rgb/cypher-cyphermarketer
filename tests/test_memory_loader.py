#!/usr/bin/env python3.12
"""E2.5 — the memory loader. Zero LLM, zero network, zero spend.

memory.md said in prose since the day it was written that a `pending: true`
entry may never inform a draft. Nothing read the file, so the sentence was true
by accident — the inert-rail shape a third time. These tests make it fail.

Section 5 is the one that matters. "The loader did not return it" is weaker than
the claim: the claim is that a pending entry NEVER REACHES A DRAFT. So the test
puts a sentinel in a pending entry and asserts the sentinel is absent from the
actual system prompt the writer assembles.
"""
import ast, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research import memory as MEM, writer as W

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent
SENTINEL = "ZZQX-PENDING-SENTINEL-9471"

HEAD = """# memory.md

### Entry shape

```
### M00N — the template, inside a fence
pending: true
approved_by: —
approved_on: —
```

## ENTRIES
"""

def entry(eid, title, pending="false", by="ashton", on="2026-09-16",
          body="A body.", omit=()):
    lines = ["### %s — %s" % (eid, title)]
    for k, v in (("pending", pending), ("approved_by", by), ("approved_on", on)):
        if k not in omit:
            lines.append("%s: %s" % (k, v))
    lines += ["evidence: `somewhere`", "", body, ""]
    return "\n".join(lines)

def write(*entries):
    p = Path(tempfile.mkdtemp()) / "memory.md"
    p.write_text(HEAD + "\n" + "\n".join(entries), encoding="utf-8")
    return p

print("\n=== 1. THE HAPPY PATH ===")
p = write(entry("M001", "An approved one", body="Approved body text."))
okd, bad = MEM.load(p)
ok(len(okd) == 1 and not bad, "an entry with all three fields correct loads")
ok(okd[0]["id"] == "M001" and "Approved body" in okd[0]["body"], "id, title and body survive")

print("\n=== 2. EACH FIELD FAILS CLOSED ON ITS OWN ===")
cases = [
    ("pending missing",        dict(omit=("pending",)),            "missing field 'pending'"),
    ("approved_by missing",    dict(omit=("approved_by",)),        "missing field 'approved_by'"),
    ("approved_on missing",    dict(omit=("approved_on",)),        "missing field 'approved_on'"),
    ("pending: true",          dict(pending="true"),               "pending is 'true'"),
    ("pending: True",          dict(pending="True"),               "pending is 'True'"),
    ("pending: no",            dict(pending="no"),                 "pending is 'no'"),
    ("pending: 0",             dict(pending="0"),                  "pending is '0'"),
    ("pending: (empty)",       dict(pending=""),                   "pending is ''"),
    ("pending: false-ish",     dict(pending="falsey"),             "pending is 'falsey'"),
    ("approved_by: claude",    dict(by="claude"),                  "approved_by is 'claude'"),
    ("approved_by: Ashton",    dict(by="Ashton"),                  "approved_by is 'Ashton'"),
    ("approved_by: —",         dict(by="—"),                       "approved_by is '—'"),
    ("approved_on: —",         dict(on="—"),                       "not an ISO date"),
    ("approved_on: yesterday", dict(on="yesterday"),               "not an ISO date"),
    ("approved_on: 2026-13-99",dict(on="2026-13-99"),              "not an ISO date"),
    ("approved_on: (empty)",   dict(on=""),                        "not an ISO date"),
]
for label, kw, expect in cases:
    okd, bad = MEM.load(write(entry("M001", "x", **kw)))
    got = (bad[0]["reason"] if bad else "")
    ok(not okd and expect in got, "%-24s -> withheld (%s)" % (label, got[:44]))

print("\n=== 3. A BLOCKLIST WOULD HAVE LET THESE THROUGH ===")
ok(MEM.PENDING_FALSE == "false" and MEM.APPROVER == "ashton",
   "the filter is an EQUALITY against one literal, not `!= 'true'`")
# ★ AST, not a source scan. The first version of this check asserted
# `'!= "true"' not in src` and FAILED — on memory.py's own comment explaining
# why that shortcut was rejected. That is the exact false positive banked in
# contracts.py ("a test can match its own docstring"), hit one hour after
# banking it. Prose about a constraint and the constraint are the same bytes to
# `in`; only the AST distinguishes them.
src = (REPO / "research" / "memory.py").read_text()
tree = ast.parse(src)
fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_approved")
# Every string the filter actually COMPARES against, as code rather than text.
compared = set()
for n in ast.walk(fn):
    if isinstance(n, ast.Compare):
        for side in [n.left] + list(n.comparators):
            if isinstance(side, ast.Constant) and isinstance(side.value, str):
                compared.add(side.value)
            elif isinstance(side, ast.Name):
                compared.add("<%s>" % side.id)
ok("true" not in compared,
   "the filter never compares against 'true' — no `!= true` shortcut: %s" % sorted(compared))
ok("<PENDING_FALSE>" in compared and "<APPROVER>" in compared,
   "it compares against the named literals PENDING_FALSE and APPROVER")
neq = [n for n in ast.walk(fn) if isinstance(n, ast.Compare)
       and any(isinstance(o, ast.NotEq) for o in n.ops)]
ok(len(neq) >= 2, "the two gates are NotEq against those literals (%d found)" % len(neq))
# `not in` IS used, for required-field presence — that is membership on a dict,
# not a blocklist on a value. Assert it is only ever used that way.
notins = [n for n in ast.walk(fn) if isinstance(n, ast.Compare)
          and any(isinstance(o, ast.NotIn) for o in n.ops)]
ok(all(isinstance(n.comparators[0], ast.Name) and n.comparators[0].id == "f"
       for n in notins),
   "every `not in` tests dict-key presence, never a value blocklist (%d)" % len(notins))

print("\n=== 4. THE FILE'S OWN TEMPLATE IS NOT AN ENTRY ===")
okd, bad = MEM.load(write(entry("M001", "real")))
ok(len(okd) + len(bad) == 1, "the fenced M00N template is skipped: %d parsed" % (len(okd)+len(bad)))
live_ok, live_bad = MEM.load()
ok(len(live_ok) + len(live_bad) == 10,
   "the LIVE file parses as exactly 10 entries, not 11: %d" % (len(live_ok)+len(live_bad)))
ok(len(live_ok) == 0, "and all 10 are withheld today, because none is approved yet")

print("\n=== 5. A PENDING ENTRY NEVER REACHES A DRAFT ===")
mixed = write(
    entry("M001", "approved one", body="Approved body."),
    entry("M002", "pending one", pending="true", by="—", on="—",
          body="This body contains %s and must never be sent." % SENTINEL),
)
block = MEM.for_prompt(mixed)
ok(SENTINEL not in block, "for_prompt() omits the pending body")
ok("Approved body" in block, "…while including the approved one")
ok("EVIDENCE, NOT INSTRUCTION" in block, "the block labels itself evidence, per precedence")

_orig = MEM.MEMORY
try:
    MEM.MEMORY = mixed
    prompt = W.system_prompt("THE-FORMAT-CONTRACT")
    ok(SENTINEL not in prompt,
       "★ the SENTINEL is absent from the writer's assembled system prompt")
    ok("Approved body" in prompt, "…and the approved entry IS in it")
    ok("THE-FORMAT-CONTRACT" in prompt, "the contract is still there")
finally:
    MEM.MEMORY = _orig

print("\n=== 6. THERE IS EXACTLY ONE DOOR ===")
wsrc = (REPO / "research" / "writer.py").read_text()
wtree = ast.parse(wsrc)
calls = [n for n in ast.walk(wtree) if isinstance(n, ast.Call)
         and getattr(n.func, "attr", "") == "for_prompt"]
ok(len(calls) == 1, "for_prompt() is called exactly once in writer.py (%d)" % len(calls))
sp = next(n for n in ast.walk(wtree) if isinstance(n, ast.FunctionDef) and n.name == "system_prompt")
ok(any(getattr(c.func, "attr", "") == "for_prompt" for c in ast.walk(sp) if isinstance(c, ast.Call)),
   "…and that one call is inside system_prompt, the single assembly point")
ok('_soul() + "\\n\\n" + payload["format_contract"]' not in wsrc,
   "the old inline assembly is gone — no second door that skips memory")

print("\n=== 7. THE MODULE CANNOT WRITE TO memory.md ===")
ok(not any(w in src for w in ("write_text", "open(", ".unlink", "shutil")),
   "no write call of any kind in memory.py — approving is Ashton's, by hand")
ok(MEM.load(Path("/nonexistent/memory.md"))[0] == [],
   "a missing file is an empty memory, not a crash — the pipeline runs without it")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
