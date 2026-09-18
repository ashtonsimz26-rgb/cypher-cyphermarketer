#!/usr/bin/env python3.12
"""R6 suite — format / composition / tier / proposal_id survive the whole chain.

Zero LLM, zero network, zero spend. The chain under test is:

    build_one -> propose argv -> `proposed` row -> proposal_state -> `posted` row

Every one of those five hops previously dropped composition and tier on the
floor, which is why the five August posts are unmeasurable. This suite proves
each hop carries them, and it proves it STRUCTURALLY where it can: the argv
assertions read the source, so a future refactor that stops passing a field
fails here rather than silently producing another year of null columns.
"""
import ast, json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent
R6_FIELDS = ("format", "composition", "tier")

print("\n=== 1. the `proposed` row carries all four ===")
import telegram_bot as TB

tmp = Path(tempfile.mkdtemp()) / "proposals.jsonl"
TB.PROPOSAL_LEDGER = tmp
TB.ledger({"event": "proposed", "proposal_id": "p_test", "text": "t", "image": "i",
           "format": "grail_lore", "hook_type": "cultural_moment",
           "composition": "shoe_crop", "tier": "Legendary"})
row = json.loads(tmp.read_text().strip())
for f in R6_FIELDS + ("proposal_id",):
    ok(row.get(f) is not None, "proposed row carries %s=%r" % (f, row.get(f)))

print("\n=== 2. proposal_state folds composition + tier through ===")
st = TB.proposal_state()["p_test"]
ok(st.get("composition") == "shoe_crop", "state.composition survives the fold")
ok(st.get("tier") == "Legendary", "state.tier survives the fold")
ok(st.get("format") == "grail_lore", "state.format survives the fold")

print("\n=== 3. a proposal that never carried them folds to None, not a crash ===")
tmp.write_text(json.dumps({"event": "proposed", "proposal_id": "p_old", "text": "t"}) + "\n")
old = TB.proposal_state()["p_old"]
ok(old.get("composition") is None and old.get("tier") is None,
   "a pre-R6 proposal folds to None — the August rows stay readable")

print("\n=== 4. decide() writes the fields to BOTH posted rows ===")
src = (REPO / "telegram_bot.py").read_text()
tree = ast.parse(src)
fn = next(n for n in ast.walk(tree)
          if isinstance(n, ast.FunctionDef) and n.name == "decide")
posted_calls = []
for node in ast.walk(fn):
    if not isinstance(node, ast.Call):
        continue
    for a in node.args:
        if isinstance(a, ast.Dict):
            keys = [k.value for k in a.keys if isinstance(k, ast.Constant)]
            if "event" in keys:
                vals = {k.value: v for k, v in zip(a.keys, a.values)
                        if isinstance(k, ast.Constant)}
                ev = vals.get("event")
                if isinstance(ev, ast.Constant) and ev.value == "posted":
                    posted_calls.append(set(keys))
ok(len(posted_calls) == 2, "decide() writes exactly two posted rows (found %d)" % len(posted_calls))
for i, keys in enumerate(posted_calls):
    for f in R6_FIELDS + ("proposal_id",):
        ok(f in keys, "posted row %d carries %s" % (i + 1, f))

print("\n=== 5. both propose call sites pass composition + tier ===")
for path, fnname in (("daily_digest.py", "cmd_propose"), ("drop_correspondent.py", "cmd_propose")):
    s = (REPO / path).read_text()
    ok("composition" in s and "tier" in s, "%s mentions composition and tier" % path)
    # the tier must come from the CANDIDATE's rarity, never a literal
    ok('rarity' in s, "%s derives tier from rarity, not a constant" % path)

print("\n=== 6. the backfill never rewrites a posted row ===")
posts = [json.loads(l) for l in (REPO / "ledger/posts.jsonl").read_text().splitlines() if l.strip()]
bf = [r for r in posts if r.get("event") == "posted_meta_backfill"]
pd = [r for r in posts if r.get("event") == "posted"]
# The claim is about the FIVE PRE-R6 rows, identified by the backfill that
# enriches them. It used to check `len(pd) == 5` and "no posted row carries
# composition" over the WHOLE ledger — true only until the first post after R6.
# p_34f18679da (2026-09-18) was that post, its row correctly carries composition,
# and the suite failed on R6 working. memory.md M004 predicted this exact event.
orig_ids = {r["tweet_id"] for r in bf}
orig = [r for r in pd if r["tweet_id"] in orig_ids]
ok(len(bf) == 5 and len(orig) == 5,
   "the five original posted rows are still present (%d), each with a backfill row (%d)"
   % (len(orig), len(bf)))
ok(all("composition" not in r for r in orig),
   "no ORIGINAL posted row was rewritten — enrichment lives in its own event")
new_rows = [r for r in pd if r["tweet_id"] not in orig_ids]
ok(all(all(k in r for k in ("format", "composition", "tier")) for r in new_rows),
   "every post AFTER R6 carries format/composition/tier on its own row (%d such post(s))"
   % len(new_rows))
ok(all(r["recoverable"]["composition"] is False for r in bf),
   "every backfill row marks composition UNRECOVERABLE rather than guessing")
ok(all(r["methods"].get("tier") for r in bf),
   "every backfill row states the method that produced its tier")

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
