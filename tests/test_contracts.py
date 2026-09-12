#!/usr/bin/env python3.12
"""Pipeline contract suite. Proves the assertion FIRES, not just that it passes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research import contracts as C
import editorial

FAILS=[]
def ok(c,m):
    print(("  PASS  " if c else "  FAIL  ")+m)
    if not c: FAILS.append(m)

print("\n=== 1. the contract passes on the current pipeline ===")
ok(C.unconsumed()=={}, f"no unconsumed fields: {C.unconsumed()}")
C.assert_contract(); ok(True, "assert_contract() does not raise")

print("\n=== 2. a SYNTHETIC produced field consumed by nobody -> ImportError ===")
orig=dict(C.PRODUCED)
C.PRODUCED["synthetic"]=frozenset({"a_field_nobody_reads"})
try:
    C.assert_contract(); ok(False,"raises")
except ImportError as e:
    ok(True,"raises ImportError")
    ok("a_field_nobody_reads" in str(e), "names the orphan field")
    ok("inert-rule signature" in str(e), "explains WHY it is a failure")
    print("      " + str(e).splitlines()[1].strip())
C.PRODUCED.clear(); C.PRODUCED.update(orig)
ok(C.unconsumed()=={}, "restored clean")

print("\n=== 3. THE MEASURED LIMIT — G4 is NOT caught, and that is asserted ===")
print("    The proposal claimed this catches G4. Building it proved otherwise:")
print("    the contract asks 'read by AT LEAST ONE decision-maker?', not")
print("    'read by the RIGHT one'. hook_facts is read by the writer, so")
print("    detect_hook going blind to the dossier leaves it green.")
orig_reads=dict(C.READS)
C.READS["editorial.detect_hook"]=frozenset(editorial.DETECT_HOOK_READS)-{"hook_facts"}
try:
    C.assert_contract()
    ok(True,"G4 is NOT caught — limit asserted so no future session assumes otherwise")
except ImportError:
    ok(False,"G4 unexpectedly caught — the docstring's tally is now wrong, update it")
readers=[n for n,r in C.READS.items() if "hook_facts" in r]
ok(readers==["research.writer"], f"hook_facts still consumed, by: {readers}")
C.READS.clear(); C.READS.update(orig_reads)

print("\n=== 3b. F4.4's shape IS caught — a field read by nobody ===")
# F4.4's true state: produced, read by nobody, AND never declared withheld.
orig_withheld=dict(C.WITHHELD)
C.READS["research.writer"]=frozenset(C.READS["research.writer"])-{"occasion"}
C.WITHHELD.pop("occasion",None)
C.PRODUCED["occasion_producer"]=frozenset({"occasion"})
try:
    C.assert_contract(); ok(False,"F4.4 shape raises")
except ImportError as e:
    ok(True,"CAUGHT: a field produced and read by nobody -> ImportError")
    ok("occasion" in str(e), "names occasion")
C.READS.clear(); C.READS.update(orig_reads)
C.WITHHELD.clear(); C.WITHHELD.update(orig_withheld)
C.PRODUCED.pop("occasion_producer",None)
ok(C.unconsumed()=={}, "restored clean")

print("\n=== 4. deliberate non-consumption stays legal, but explicit ===")
ok("lane" in C.WITHHELD and C.WITHHELD["lane"], "withheld fields carry a reason")
ok(all(isinstance(v,str) and len(v)>10 for v in C.WITHHELD.values()),
   "every withheld reason is a real sentence, not a placeholder")
ok("anniversary_age" in C.WITHHELD, "anniversary_age declared and accounted (R2a)")

print("\n=== 5. the docstring states what this does NOT catch (R2b) ===")
doc=C.__doc__ or ""
ok("does **not** catch" in doc.lower() or "does NOT catch" in doc, "has a NOT-caught section")
ok("wrong input" in doc.lower(), "names the wrong-input class")
ok("adversarial" in doc.lower(), "says an adversarial test is what that class needs")
ok("D1 signal 2" in doc, "cites D1 signal 2 as the example that would still pass")

print("\n"+("ALL PASS" if not FAILS else f"{len(FAILS)} FAILURE(S): {FAILS}"))
sys.exit(1 if FAILS else 0)
