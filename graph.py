#!/usr/bin/env python3.12
"""
graph.py — the goal graph, GENERATED from live state rather than transcribed.

★ WHY THIS FILE EXISTS. The first version of this diagram was hand-authored: a
session read the prose in profile/*.md, typed the numbers into a JSON spec, and
compiled it to HTML. Every figure in it was therefore a claim about a claim. It
was accurate the day it was built and had no way to stay that way, because
nothing in the artifact could notice the ledger moving underneath it.

That is precisely the defect memory.md M004 is about — an honest artifact and a
dishonest one sitting in the same repo, disagreeing for weeks, because the prose
and the code that computes the same figure were never diffed. A hand-typed
diagram is that failure with a nicer font.

So the numbers are MEASURED at build time or they are NOT DRAWN. There is no
third option and no default-to-last-known.

★ MEASUREMENT vs RULING — the distinction this file is organised around.

  MEASURED  a number that moves on its own: post counts, engagement, how many
            cards are pool-reachable. Re-derived every run. Never typed.
  RULING    a decision Ashton made on a date: THE GOAL, the precedence chain,
            the autonomy phase, the ~15% top-tier weighting. These do not drift;
            they are superseded. They are quoted WITH their ruling date so a
            reader can see how old the governance is, and they live in SOUL.md /
            instructions.md, which this file cites rather than restates.

Mixing the two is what produced the original problem: "n=4" was written in the
same voice as "narrative outranks arithmetic", and only one of them was still
true a week later.

★ FAIL CLOSED, AND SAY SO. If a source cannot be read this run, the fact it
would have produced is not drawn, and the graph states in its own body that the
figure was not verified. It never falls back to a previous value. An unverified
number that looks verified is the shape rails.py fails closed against, and the
shape the price rail was tightened for on 2026-08-19.

★ THE CITATION RULE IS ENFORCED IN CODE, NOT REMEMBERED. SOUL.md requires that
any citation of the account's lifetime totals carry the 4-of-22 split in the
same sentence. cite_lifetime() is the only way this module can render those
totals and it returns both halves in one string, so the rule cannot be violated
by a future edit that forgets it.

Usage
    python3.12 graph.py                 # measure, build, deliver
    python3.12 graph.py --facts-only    # print what is measurable, build nothing
    python3.12 graph.py --no-catalog    # ledger only; catalog claims are dropped
    python3.12 graph.py --open          # reveal the delivered HTML afterwards
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

HERE = Path(__file__).resolve().parent
METRICS = HERE / "ledger" / "metrics.jsonl"          # read only
GRAPH_LEDGER = HERE / "ledger" / "graph.jsonl"       # the ONLY ledger this writes

# state/ is gitignored: the IR and the HTML are both reproducible from the
# ledger plus this file, so they are build output, not source. Same reasoning
# the .gitignore already applies to content/*.png.
OUT_DIR = HERE / "state" / "graph"
IR_PATH = OUT_DIR / "goal.workflow.json"
HTML_PATH = OUT_DIR / "cyphermarketer-goal.html"

ARCHIFY = Path(os.environ.get(
    "ARCHIFY_BIN", Path.home() / ".claude/skills/archify/bin/archify.mjs"))

# ── rulings, quoted with their dates ─────────────────────────────────────────
# Not measurements. Superseded by Ashton, never drifted into by the system.
RULING_GOAL_DATE = "2026-09-16"
RULING_PHASE = "PHASE 1"
PRECEDENCE = "SOUL.md > rails.py > instructions.md > context.md > memory.md"

# The nine rails, by stable name, as rails.py defines them. Counted, not typed:
# if a rail is added or removed, the graph says the new number.
RAILS_SOURCE = HERE / "rails.py"


class Fact(NamedTuple):
    """A value with its provenance and whether this run actually established it.

    `verified=False` means the source could not be read. It does NOT mean the
    value is zero, and nothing downstream may treat it as a number.
    """
    name: str
    value: Any
    source: str
    verified: bool

    def require(self) -> Any:
        if not self.verified:
            raise ValueError("fact %r was not verified this run" % self.name)
        return self.value


def read_jsonl(p: Path) -> tuple[list[dict], bool]:
    """Returns (rows, verified). A missing or unreadable file is NOT an empty
    ledger — the caller must not render a count from it."""
    if not p.exists():
        return [], False
    rows = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as e:
        print("  !! %s unreadable: %s" % (p.name, e), file=sys.stderr)
        return [], False
    return rows, True


def cite_lifetime(impressions: int, likes: int, rows: int,
                  n_content: int) -> str:
    """The ONLY way this module renders lifetime totals.

    SOUL.md § THE GOAL: any citation of the account's lifetime figures must
    carry the split in the SAME sentence, never in a footnote, because stating
    the total alone overstates the agent's record by roughly 4x. Returning the
    two halves welded into one string is what makes that structural instead of
    a thing a future edit has to remember.
    """
    assert rows >= n_content, "content rows cannot exceed total rows"
    return ("account lifetime %d impressions / %d likes across %d rows, of "
            "which only %d are agent content" % (impressions, likes, rows,
                                                 n_content))


# ── MEASURE: the ledger ──────────────────────────────────────────────────────

def measure_ledger() -> dict[str, Fact]:
    """The agent's own record, cut by `kind` the way metrics.jsonl has encoded
    it the whole time. M001 exists because nothing read that field."""
    f: dict[str, Fact] = {}
    rows, ok = read_jsonl(METRICS)
    src = "ledger/metrics.jsonl"

    if not ok:
        for k in ("n_content", "impressions", "likes", "goal_events",
                  "kind_split", "lifetime"):
            f[k] = Fact(k, None, src, False)
        return f

    content = [r for r in rows if r.get("kind") == "content"]
    split = {}
    for r in rows:
        split[r.get("kind") or "unlabelled"] = split.get(
            r.get("kind") or "unlabelled", 0) + 1

    def total(key: str, src_rows: list[dict]) -> int:
        return sum(int(r.get(key) or 0) for r in src_rows)

    # THE GOAL is a single event of any of three kinds. Summed, not inferred.
    goal_events = (total("replies", content) + total("quotes", content)
                   + total("bookmarks", content))

    f["n_content"] = Fact("n_content", len(content), src, True)
    f["impressions"] = Fact("impressions", total("impressions", content), src, True)
    f["likes"] = Fact("likes", total("likes", content), src, True)
    f["goal_events"] = Fact("goal_events", goal_events, src, True)
    f["kind_split"] = Fact("kind_split", split, src, True)
    f["lifetime"] = Fact("lifetime", {
        "rows": len(rows),
        "impressions": total("impressions", rows),
        "likes": total("likes", rows),
    }, src, True)
    return f


def measure_rails() -> Fact:
    """Count the rails rather than trusting the docstring that says nine.

    rails.py builds its checks as Rail("NAME", ...) literals inside
    check_draft(); counting the constructor calls is the closest honest proxy
    for "how many named rails exist" without importing the module and running
    a draft through it.
    """
    src = "rails.py"
    if not RAILS_SOURCE.exists():
        return Fact("n_rails", None, src, False)
    try:
        import ast
        tree = ast.parse(RAILS_SOURCE.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as e:
        print("  !! rails.py unparseable: %s" % e, file=sys.stderr)
        return Fact("n_rails", None, src, False)

    names = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Rail"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            names.add(node.args[0].value)
    if not names:
        return Fact("n_rails", None, src, False)
    return Fact("n_rails", sorted(names), src, True)


# ── MEASURE: the catalog ─────────────────────────────────────────────────────

def measure_frame_check() -> Fact:
    """Does the image gate exist yet?

    ★ The Frame Check node is drawn BEFORE its code exists, deliberately: the
    check needs an owner in the diagram so it lands as a named stage rather
    than bolted onto whatever ran last. But a node drawn for work not yet done
    must SAY so, or the graph becomes a picture of intentions.

    So the node's tag is measured, not typed. The day research/frame.py lands
    with a check_frame(), the tag flips on the next build and nobody edits this
    file. Until then it reads NOT BUILT, which is the honest state.
    """
    src = "research/frame.py"
    mod = HERE / "research" / "frame.py"
    if not mod.exists():
        return Fact("frame_check_built", False, src, True)
    try:
        import ast
        tree = ast.parse(mod.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return Fact("frame_check_built", False, src, True)
    built = any(isinstance(n, ast.FunctionDef) and n.name == "check_frame"
                for n in ast.walk(tree))
    return Fact("frame_check_built", built, src, True)


def measure_catalog(enabled: bool) -> dict[str, Fact]:
    """Pool reachability and the earn route, from the live database.

    ★ The CTEs are IMPORTED, never re-typed. daily_digest's own comment records
    that the obtainable set had been written out four times in three files by
    2026-09-16 — "three chances for one of them to drift". A copy here would be
    the fifth, and it would drift in the one place nobody runs tests against.
    """
    src = "supabase (public.catalog_cards + pools via daily_digest CTEs)"
    keys = ("tier_ladder", "top_tier_pullable", "earnable")
    if not enabled:
        print("  -- catalog skipped (--no-catalog)")
        return {k: Fact(k, None, src + " [skipped]", False) for k in keys}

    try:
        sys.path.insert(0, str(HERE))
        import daily_digest as dd
    except Exception as e:                                    # noqa: BLE001
        print("  !! cannot import daily_digest: %s" % e, file=sys.stderr)
        return {k: Fact(k, None, src, False) for k in keys}

    out: dict[str, Fact] = {}

    ladder_q = dd.REACHABLE_CTE + """
    select c.rarity as tier,
           count(*) as catalog_rows,
           count(r.image_name) as reachable_rows
    from public.catalog_cards c
    left join reachable r
      on r.image_name = c.image_name and r.rarity = c.rarity
    group by c.rarity;"""
    try:
        ladder = dd._sql(ladder_q)
    except Exception as e:                                    # noqa: BLE001
        print("  !! catalog query failed: %s" % e, file=sys.stderr)
        ladder = []

    if ladder:
        out["tier_ladder"] = Fact("tier_ladder", ladder, src, True)
        top = [r for r in ladder
               if str(r.get("tier", "")).upper().replace(" ", "_")
               in ("GRAIL", "HOLY_GRAIL")]
        # Fail closed: only claim "none pullable" if the top tiers were RETURNED.
        if top:
            pullable = sum(int(r.get("reachable_rows") or 0) for r in top)
            out["top_tier_pullable"] = Fact("top_tier_pullable", pullable, src, True)
        else:
            out["top_tier_pullable"] = Fact("top_tier_pullable", None, src, False)
    else:
        out["tier_ladder"] = Fact("tier_ladder", None, src, False)
        out["top_tier_pullable"] = Fact("top_tier_pullable", None, src, False)

    earn_q = dd.OBTAINABLE_CTE + """
    select e.image_name, e.rarity from earnable e order by e.image_name;"""
    try:
        earn = dd._sql(earn_q)
    except Exception as e:                                    # noqa: BLE001
        print("  !! earnable query failed: %s" % e, file=sys.stderr)
        earn = None
    out["earnable"] = (Fact("earnable", earn, src, True) if earn is not None
                       else Fact("earnable", None, src, False))
    return out


# ── BUILD: the archify IR ────────────────────────────────────────────────────

def build_ir(f: dict[str, Fact]) -> tuple[dict, list[str]]:
    """Emit the typed IR. Returns (ir, unverified) — the second is rendered into
    the artifact so a reader sees what this run could not establish."""
    unverified = [k for k, v in f.items() if not v.verified]

    # Node text is length-constrained by the renderer's legibility floor
    # (~24 chars of sublabel at 132px, checked at a 1440px viewport). Measured
    # values are short by nature; these stay well inside it.
    if f["goal_events"].verified:
        goal_tag = "count: %d" % f["goal_events"].value
        goal_met = f["goal_events"].value > 0
    else:
        goal_tag = "count: unverified"
        goal_met = False

    n_label = ("append-only · n=%d" % f["n_content"].value
               if f["n_content"].verified else "append-only · n=?")

    # ★ The node is drawn before the code exists, so its STATUS must be visible
    # at a glance, not only in a tag the viewer reveals on focus. Measured, so
    # it flips the day research/frame.py lands and nobody edits this file.
    _fb = f["frame_check_built"]
    frame_tag = (("live" if _fb.value else "NOT BUILT")
                 if _fb.verified else "unverified")
    frame_sub = (("geometry + contrast" if _fb.value else "NOT BUILT YET")
                 if _fb.verified else "status unverified")

    rails_label = ("%d named rails" % len(f["n_rails"].value)
                   if f["n_rails"].verified else "named rails (unverified)")

    # ── goal card: measured line, or an explicit statement of absence ────────
    if f["n_content"].verified and f["goal_events"].verified:
        record = ("Agent record is %d posts: %d impressions, %d likes, %d of "
                  "the goal event" % (f["n_content"].value,
                                      f["impressions"].value,
                                      f["likes"].value,
                                      f["goal_events"].value))
    else:
        record = "Agent record NOT VERIFIED this run — ledger unreadable"

    goal_items = [
        "One person who does not know Ashton replies to, quotes, or bookmarks a post",
        record,
    ]
    if goal_met:
        # SOUL.md § EXPIRY: the ordering stops being automatic the day this
        # lands, and Ashton sets the successor. The graph must not keep drawing
        # an expired goal as pending.
        goal_items.append("★ GOAL MET — SOUL.md says it expires now and Ashton "
                          "sets the next one")
    else:
        goal_items.append("It expires the day the first one lands, and Ashton "
                          "sets the next")

    # ── the catalog line: one slot, measured or explicitly absent ────────────
    if (f["top_tier_pullable"].verified and f["earnable"].verified
            and f["tier_ladder"].verified):
        rows = f["tier_ladder"].value
        total_rows = sum(int(r.get("catalog_rows") or 0) for r in rows)
        total_reach = sum(int(r.get("reachable_rows") or 0) for r in rows)
        catalog_line = ("Catalog %d rows, %d pool-reachable; top tier pullable "
                        "%d, earnable by set %d"
                        % (total_rows, total_reach,
                           f["top_tier_pullable"].value,
                           len(f["earnable"].value)))
    else:
        catalog_line = ("Pool reachability NOT VERIFIED this run — catalog "
                        "claims omitted, not defaulted")

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Exactly three slots, filled by priority. The omission notice outranks the
    # lifetime citation: knowing a figure is missing matters more than a figure
    # that is merely interesting.
    provenance = ["Built %s — figures re-derived from the ledger, none "
                  "transcribed" % built, catalog_line]
    if unverified:
        provenance.append("NOT VERIFIED: " + ", ".join(sorted(unverified)))
    elif f["lifetime"].verified and f["n_content"].verified:
        lt = f["lifetime"].value
        provenance.append(cite_lifetime(lt["impressions"], lt["likes"],
                                        lt["rows"], f["n_content"].value))

    # ★★ THE LAYOUT CEILING IS viewBox WIDTH (~1240px), NOT NODE COUNT.
    # Ruled 2026-09-17 after adding Frame Check. The viewer scales the diagram
    # to the reader width, so projected text = sourceFont x scale, and scale =
    # availableDiagramWidth / viewBoxWidth (930 / vbW at a 1440px viewport).
    # The source font is CAPPED AT 8px, so below scale ~0.75 EVERY sublabel
    # falls under the 6px legibility floor no matter how short it is:
    #     8.0 x 0.726 = 5.81  -> fails
    #     8.0 x 0.777 = 6.21  -> passes
    # Adding Frame Check pushed vbW to 1281 (scale 0.726) and shortening words
    # did nothing, because the text already fit at full size. THE LEVER IS NODE
    # WIDTH, NOT WORDING: 132 -> 120 across all twelve nodes brought vbW back
    # under the ceiling. A future session adding a node should expect to pay for
    # it in node width, and should re-run archify visual-check rather than
    # trusting that validate passing means it is readable — validate caught this
    # at 1440x900 only because that viewport is checked explicitly.
    #
    # ★ THE LAYOUT BUDGET IS A BUILD-TIME ASSERTION, NOT A STYLE NOTE.
    # Four cards wrap to two rows and push the page past the fold at 1440x900;
    # three fit one row and contain. That was found by a browser check, not by
    # reading the CSS, so it is pinned here where a future edit trips over it
    # rather than in a comment it can ignore. archify's own visual-check is the
    # backstop; this assertion is the thing that fails FIRST and says why.
    MAX_CARDS, MAX_ITEMS = 3, 3
    cards = [
        {"dot": "rose", "title": "The Goal (ruled %s)" % RULING_GOAL_DATE,
         "items": goal_items},
        {"dot": "cyan", "title": "Frame Check — the missing owner",
         "items": [
             "Rails Check reads text only; the composed image has had no gate",
             "SOUL.md makes it the precondition for Phase 2 — governance, not polish",
             "Scope: geometry + contrast. Card-on-card occlusion is a known gap, "
             "not built"]},
        {"dot": "slate", "title": "Measured this build", "items": provenance},
    ]
    assert len(cards) <= MAX_CARDS, (
        "%d cards will overflow 1440x900 — see visual-check, not the CSS"
        % len(cards))
    for c in cards:
        assert len(c["items"]) <= MAX_ITEMS, "card %r over item budget" % c["title"]

    return {
        "schema_version": 2,
        "diagram_type": "workflow",
        "meta": {
            "title": "CypherMarketer Goal Pipeline",
            "locale": "en",
            "quality_profile": "showcase",
            "legend": {"mode": "auto", "entries": {"frontend": {"label": "The goal"}}},
        },
        "lanes": [
            {"id": "pipeline", "label": "Editorial Pipeline"},
            {"id": "gates", "label": "Hard Gates"},
            {"id": "halt", "label": "Halt Paths", "variant": "exception"},
            {"id": "loop", "label": "Goal & Evidence Loop"},
        ],
        "phases": [
            {"id": "source", "label": "Select + hook", "fromCol": 0, "toCol": 1},
            {"id": "make", "label": "Make text + image", "fromCol": 2, "toCol": 3,
             "variant": "emphasis"},
            {"id": "gate", "label": "Gate + publish", "fromCol": 4, "toCol": 5,
             "variant": "dashed"},
        ],
        "groups": [
            {"id": "editorial_bar", "label": "The editorial bar", "lane": "pipeline",
             "fromCol": 1, "toCol": 2, "variant": "emphasis"},
            {"id": "two_artifacts", "label": "Two artifacts, two gates", "lane": "gates",
             "fromCol": 3, "toCol": 4, "variant": "security"},
            {"id": "silence_ok", "label": "Zero is a complete output", "lane": "halt",
             "fromCol": 1, "toCol": 4, "variant": "security"},
            {"id": "closed_loop", "label": "The goal judges the output", "lane": "loop",
             "fromCol": 0, "toCol": 1, "variant": "dashed"},
        ],
        "mainPath": ["select", "hook", "write", "compose", "frame", "rails",
                     "approve", "post"],
        "semanticChecks": {
            # No allowedRoots: goal -> select closes the cycle, so the graph has
            # no source node. That is the point of the loop, not an omission.
            "allowedTerminals": ["nohook", "halted"],
            "requiredPaths": [{"from": "select", "to": "post"},
                              {"from": "post", "to": "goal"},
                              {"from": "compose", "to": "frame"}],
        },
        "nodes": [
            {"id": "select", "lane": "pipeline", "col": 0, "type": "backend",
             "label": "Select", "sublabel": "3 lanes, first match",
             "tag": "one per lane", "width": 120},
            {"id": "hook", "lane": "pipeline", "col": 1, "type": "backend",
             "label": "Name the Hook", "sublabel": "narrative > price",
             "tag": "no hook, no post", "width": 120},
            {"id": "write", "lane": "pipeline", "col": 2, "type": "backend",
             "label": "Write Text", "sublabel": "lead + attribution", "width": 120},
            {"id": "compose", "lane": "pipeline", "col": 3, "type": "cloud",
             "label": "Compose Image", "sublabel": "card crop + backdrop", "width": 120},
            {"id": "frame", "lane": "gates", "col": 3, "type": "security",
             "label": "Frame Check", "sublabel": frame_sub,
             "tag": frame_tag, "width": 120},
            {"id": "rails", "lane": "gates", "col": 4, "type": "security",
             "label": "Rails Check", "sublabel": rails_label,
             "tag": "text only", "width": 120},
            {"id": "approve", "lane": "gates", "col": 5, "type": "security",
             "label": "Ashton Approves", "sublabel": "Telegram digest", "width": 120},
            {"id": "nohook", "lane": "halt", "col": 1, "type": "messagebus",
             "label": "No Post Today", "sublabel": "a complete answer", "width": 120},
            # ★ RULED 2026-09-17: Draft Halted stays MERGED. Frame, rails and
            # Ashton's reject all land here, and the three labelled edges
            # ("clipped or dark", "FAIL", "reject / edit") carry the whole
            # distinction. Splitting them back out costs a lane, and a lane
            # costs more than it buys. This is a decision, not a layout
            # compromise to be tidied away on aesthetics.
            {"id": "halted", "lane": "halt", "col": 4, "type": "security",
             "label": "Draft Halted", "sublabel": "frame/rails/Ashton", "width": 120},
            {"id": "goal", "lane": "loop", "col": 0, "type": "frontend",
             "label": "THE GOAL", "sublabel": "reply/quote/bookmark",
             "tag": goal_tag, "width": 120},
            {"id": "evidence", "lane": "loop", "col": 1, "type": "database",
             "label": "Ledger + Metrics", "sublabel": n_label, "width": 120},
            {"id": "post", "lane": "loop", "col": 5, "type": "messagebus",
             "label": "Post to X", "sublabel": "@appCYPHERR, 4/24h", "width": 120},
        ],
        "edges": [
            {"id": "select-hook", "from": "select", "to": "hook", "variant": "default"},
            {"id": "hook-write", "from": "hook", "to": "write", "label": "hook named",
             "variant": "emphasis"},
            {"id": "write-compose", "from": "write", "to": "compose",
             "label": "text drafted", "variant": "default"},
            {"id": "compose-frame", "from": "compose", "to": "frame",
             "label": "the image", "variant": "emphasis"},
            {"id": "frame-rails", "from": "frame", "to": "rails",
             "label": "frame passes", "variant": "emphasis"},
            {"id": "rails-approve", "from": "rails", "to": "approve",
             "label": "all %s pass" % (len(f["n_rails"].value)
                                       if f["n_rails"].verified else "?"),
             "variant": "emphasis"},
            {"id": "approve-post", "from": "approve", "to": "post", "label": "approved",
             "variant": "emphasis"},
            {"id": "post-evidence", "from": "post", "to": "evidence",
             "label": "impressions \u00b7 replies", "variant": "dashed", "role": "return"},
            {"id": "evidence-goal", "from": "evidence", "to": "goal",
             "label": "measured against", "variant": "emphasis"},
            {"id": "goal-select", "from": "goal", "to": "select",
             "label": "reorders what wins", "variant": "emphasis", "role": "branch"},
            {"id": "hook-nohook", "from": "hook", "to": "nohook", "label": "no hook",
             "variant": "security", "role": "error"},
            {"id": "frame-halted", "from": "frame", "to": "halted",
             "label": "clipped or dark", "variant": "security", "role": "error"},
            {"id": "rails-halted", "from": "rails", "to": "halted", "label": "FAIL",
             "variant": "security", "role": "error"},
            {"id": "approve-halted", "from": "approve", "to": "halted",
             "label": "reject / edit", "variant": "security", "role": "error"},
        ],
        "cards": cards,
    }, unverified


# ── DELIVER ──────────────────────────────────────────────────────────────────

def deliver(ir_path: Path, html_path: Path) -> dict:
    if not ARCHIFY.exists():
        raise SystemExit("archify not found at %s — set ARCHIFY_BIN" % ARCHIFY)
    cmd = ["node", str(ARCHIFY), "deliver", "workflow", str(ir_path),
           str(html_path), "--quality", "showcase", "--json"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                       cwd=str(ARCHIFY.parent.parent))
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise SystemExit("archify produced no JSON receipt:\n%s\n%s"
                         % (p.stdout[-2000:], p.stderr[-2000:]))
    # ★ A non-zero exit can never be described as success (run_all.py's lesson,
    # applied to a different reporting layer).
    if p.returncode != 0 or not out.get("ok"):
        for d in out.get("diagnostics", []):
            print("  DIAG %s: %s" % (d.get("code"), d.get("message")), file=sys.stderr)
        raise SystemExit("archify deliver FAILED (exit %d)" % p.returncode)
    return out


def ledger_log(**kw) -> None:
    GRAPH_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    kw.setdefault("ts", datetime.now(timezone.utc).isoformat())
    with GRAPH_LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(kw, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--facts-only", action="store_true",
                    help="print measured facts and exit; build nothing")
    ap.add_argument("--no-catalog", action="store_true",
                    help="skip supabase; catalog-derived claims are dropped")
    ap.add_argument("--open", action="store_true", help="reveal the HTML when done")
    ap.add_argument("--out", type=Path, default=HTML_PATH)
    a = ap.parse_args()

    print("MEASURING")
    facts = measure_ledger()
    facts["n_rails"] = measure_rails()
    facts["frame_check_built"] = measure_frame_check()
    facts.update(measure_catalog(enabled=not a.no_catalog))

    for k in sorted(facts):
        v = facts[k]
        shown = v.value
        if isinstance(shown, list) and len(shown) > 4:
            shown = "%d items" % len(shown)
        print("  %-18s %-9s %s" % (k, "ok" if v.verified else "UNVERIFIED", shown))

    if facts["goal_events"].verified and facts["goal_events"].value > 0:
        print("\n★★ THE GOAL HAS BEEN MET (%d event(s)). SOUL.md § EXPIRY: the "
              "ordering stops being automatic and Ashton sets the successor. "
              "This graph should not keep drawing it as pending."
              % facts["goal_events"].value)

    if a.facts_only:
        return 0

    ir, unverified = build_ir(facts)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    IR_PATH.write_text(json.dumps(ir, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nIR   %s" % IR_PATH)

    receipt = deliver(IR_PATH, a.out)
    v = receipt.get("validation", {})
    print("HTML %s" % a.out)
    print("     checks %s/%s  composition=%s  errors=%s warnings=%s"
          % (v.get("checksPassed"), v.get("checkCount"),
             v.get("compositionStatus"), v.get("errors"), v.get("warnings")))
    print("     spec sha256 %s" % receipt.get("specification", {}).get("sha256", "")[:16])
    print("     html sha256 %s" % receipt.get("artifact", {}).get("sha256", "")[:16])

    ledger_log(event="graph_built",
               html=str(a.out),
               spec_sha256=receipt.get("specification", {}).get("sha256"),
               artifact_sha256=receipt.get("artifact", {}).get("sha256"),
               checks_passed=v.get("checksPassed"),
               n_content=facts["n_content"].value if facts["n_content"].verified else None,
               goal_events=facts["goal_events"].value if facts["goal_events"].verified else None,
               unverified=sorted(unverified))

    if unverified:
        # Not a failure — a stated limitation. The artifact says so too.
        print("\n  NOT VERIFIED this run: %s" % ", ".join(sorted(unverified)))
        print("  (those claims were omitted from the graph, not defaulted)")

    if a.open:
        subprocess.run(["open", str(a.out)], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
