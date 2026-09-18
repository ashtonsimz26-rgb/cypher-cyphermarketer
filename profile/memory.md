# memory.md — what has been learned

**Rank 5 of 5, and the only file that is EVIDENCE rather than INSTRUCTION.**
Precedence: `SOUL.md` > `rails.py` > `instructions.md` > `context.md` > **`memory.md`**.

An entry here may MOTIVATE a change to `instructions.md`. It may never override one,
and it is never itself a rule. "This worked once" is a fact about the past, not a
licence for the future.

---

## THE APPROVAL CONTRACT (Ashton's ruling, 2026-09-16)

Every entry carries a `pending` field.

- **The agent may write a `pending: true` entry freely.** Recording an observation
  needs no permission and should not wait.
- **The agent may NEVER flip the flag.** `pending: true` → `pending: false` is
  Ashton's action alone. An agent that flips its own flag has written its own
  conclusion into the record as fact, which is the exact failure this contract exists
  to prevent.
- **The agent may NEVER read a pending entry as guidance.** Only approved entries
  inform a draft. A pending entry is invisible to the writer.

The entry sits in its final place with its final wording while pending, so what Ashton
approves is exactly what a future session will read.

### Loader contract — a POSITIVE filter

The same shape as `research/moments.PROPOSABLE_SENSITIVITIES` and
`research/dossier.PROPOSABLE_DOSSIER_SENSITIVITIES`: an allowed set, not a blocklist.
An entry loads **only** when ALL of these hold:

```
pending      is exactly false
approved_by  == "ashton"
approved_on  parses as an ISO date
```

Anything else — missing field, malformed date, a different approver, a `pending` value
that is not a literal boolean — **does not load**. Fail closed. A blocklist would let
a new field shape through by default; this cannot.

### Entry shape

```
### M00N — <one-line claim>
pending: true
approved_by: —
approved_on: —
evidence: <file / query / ledger row that anyone can re-check>

<body: what was observed, and what it does NOT license>
```

---

## ENTRIES

**All seed entries below are `pending: true`.** The agent wrote them; none has been
approved. Until Ashton flips them the loader returns an empty set and no entry informs
any draft — which is the contract working, not a bug.

### M001 — The account has never been shared once
pending: true
approved_by: —
approved_on: —
evidence: `ledger/metrics.jsonl`, 22 rows, split by the `kind` field

**CORRECTED 2026-09-16.** This entry previously read "the five posts in
`ledger/posts.jsonl` account for 91 impressions and 5 likes". That was the wrong cut
twice over: it counted the v1 acceptance-test announcement as agent output, and it
never said that the other 17 rows are Ashton's manual replies rather than anything the
agent wrote. The `kind` field in `ledger/metrics.jsonl` encoded the split the whole
time — `content` 4, `manual_reply` 17, `announcement` 1 — and nothing read it.

**The agent's record is 4 posts (`kind == "content"`): 54 impressions, 3 likes, 0
reposts, 0 replies, 0 quotes, 0 bookmarks.** The account's lifetime totals of **204
impressions and 8 likes across 22 rows are a different population**, 18 of which are
Ashton's manual replies and the acceptance-test announcement. Per the citation rule in
`SOUL.md` § THE GOAL, **any use of 204/8 must carry the 4-of-22 split in the same
sentence, never in a footnote** — stating the total without the split is what produced
this error. n=4 is not a sample.

Zero is not a small number here, and it holds on both cuts — across the agent's 4 and
across all 22, nothing this account has published has ever been passed on by anyone.
**Does not license** chasing trending subjects; it licenses preferring formats that ask
for a response.

### M002 — All four rejections were the formula SOUL later banned — and no reason was recorded
pending: true
approved_by: —
approved_on: —
evidence: `ledger/proposals.jsonl`, four `rejected` rows, all 2026-08-20

Three of the four (`p_afbd558609`, `p_a1ee4a2845`, `p_23e8164f77`) were drop-correspondent
posts of the shape *"2017. Retail $170. Nike Air Humara 17 'Black'."* — literally
"year + retail + name + link", the formula the editorial bar was written to ban. Two of
them were the same copy against two different headlines. The fourth (`p_5e67f5836b`)
carried a price the agent itself flagged as unverifiable for freshness.

**The rejected rows carry no `reason` field at all** — the reasons above are inferred
from the proposal text, not recorded. Every conclusion drawn from these four is
therefore weaker than it looks.

### M003 — The 21 expiries were a backfill, not 21 rejections
pending: true
approved_by: —
approved_on: —
evidence: `ledger/proposals.jsonl`, 21 `expired` rows, reason `retroactive_ttl_introduction`, 2026-09-09

A TTL was introduced and applied retroactively on one day. These are **not** signal
about quality and must never be counted as rejections in any report.

### M004 — The posted row records nothing measurable — and did so for a reason that has since changed
pending: true
approved_by: —
approved_on: —
evidence: `ledger/proposals.jsonl` (4 `posted` rows, 7 keys each); `data/post_format_labels.json`; `telegram_bot.py:433` and `:438`

**CORRECTED 2026-09-17.** This entry carried four errors. Three were wrong when
written; the fourth was true when written and has since gone stale. They are kept
apart below because they do not license the same thing — a wrong claim is retracted, a
stale claim is still true today and stops being true on a known event.

The entry previously read, in full:

> No format, no composition, no tier, no hook type on any posted row.
> `data/post_format_labels.json` exists precisely because five posts had to be labelled
> after the fact, three of them by hand against copy skeletons. **Until the posted row
> carries these fields, no weekly report can say anything but totals.**

**WRONG (1) — "five posts had to be labelled."** Two populations, one number. The
**labelling** population is **5**; the **agent-content** population is **4**. They
differ by exactly one row: the v1 acceptance-test announcement
(`2090222611443732627`), which `post_format_labels.json` records as `format: null,
kind: announcement` and excludes from format aggregation by ruling C3. Five tweets
were labelled; four of them are agent content. Per the citation rule in `SOUL.md`
§ THE GOAL, neither number may be stated without the other. Same defect as M001.

**WRONG (2) — "three of them by hand against copy skeletons."** It was **two by hand,
and only one against skeletons**. Three of the five were joined deterministically. The
real method counts, from the `method` field on each entry:

| method | n | hand or joined |
|---|---:|---|
| `joined_exact` | 2 | joined — deterministic |
| `joined_format_unambiguous` | 1 | joined — >1 candidate, all one format |
| `hand_from_text` | 1 | hand — the announcement |
| `hand_from_skeleton` | 1 | hand — the only one matched against skeletons |

The claim overstated hand-labelling roughly 3x on the skeleton count and inverted the
hand/joined majority. The labelling was in better shape than the entry said.

**WRONG (3) — the key list.** `posted` rows carry **7** keys, not the 6 listed:
`{edited, event, final_text, proposal_id, ts, tweet_id, url}`. `final_text` was
missing, which matters because it is the only record of what was actually published
when Ashton edited a draft before posting.

**STALE (4) — NOT a correction. The fields ARE wired.** "Until the posted row carries
these fields" was true when written and is no longer the blocker. **R6 (`405d2eb`,
2026-09-16)** wired `format`, `hook_type`, `composition` and `tier` into **both** write
sites — `telegram_bot.py:433` (posts ledger) and `:438` (proposals ledger).

The conclusion still holds **today**, but for a different reason than the entry gives:
not *"not implemented"* but ***"not yet exercised."*** All 4 existing `posted` rows
predate R6 and are therefore bare, and no post has shipped since R6 landed. A future
session must not read this entry as "the work is outstanding" — the work is done and
waiting on traffic.

**This line expires on its own.** The day the first post ships after R6, the next
`posted` row carries all four fields and the weekly report can say more than totals for
it. Nobody needs to edit this entry for that to happen — so check
`ledger/proposals.jsonl` for a `posted` row carrying a `format` key before repeating
the conclusion. If one exists, this paragraph is finished and the entry should be
re-opened, not cited.

**All four errors were in PROSE. The code computing the same numbers was right.**
`format_report.py` filtered on `in_post_ledger` and split `kind == "announcement"` into
its own category from the day it was written, and `post_format_labels.json` recorded
the true method on every entry. The honest artifact and the dishonest one sat in the
same repo and disagreed for weeks, and nobody diffed them. **Does not license** trusting
prose over the code that computes the same figure: when a document and its generator
disagree, check the generator first. This is the concrete instance of the mixed-
population lesson, sitting in the file the lesson is about.

### M005 — The format mix is two formats wearing four names
pending: true
approved_by: —
approved_on: —
evidence: `ledger/runs.jsonl`, 36 `draft_built` rows

`story_spotlight` 19, `price_journey` 15, `grail_lore` 2, `on_this_day` 0. Hook types:
`price_journey` 22 of 36 — the arithmetic hook fired more often than every narrative
hook combined, which is what the 2026-09-11 "narrative outranks arithmetic" ruling was
responding to. The last six days show the correction taking: `collab_origin`,
`cultural_moment`, `release_drama` now appear.

### M006 — "Which would you pull" has never been produced
pending: true
approved_by: —
approved_on: —
evidence: `editorial.DECLARED_NOT_READY`; zero occurrences in `ledger/runs.jsonl`

Named in `SOUL.md` as one of five rotation formats since the beginning. Declared in
code as not-ready. Never once drafted. It is the only named format that asks the reader
for a response, and the response count is zero — see M001.

### M007 — The top tier is four stories, not six shoes
pending: true
approved_by: —
approved_on: —
evidence: live catalog query, 2026-09-16; see `context.md` § 3

Six postable Legendary shoes collapse to four stories: two Grateful Dead colorways, two
Travis Scott pairs, plus `yeezy750_og` and `nike_air_force_1_low_lemonade`. At a 40%
top-tier weighting each returns every ~2.5 days. This is the measurement behind the
~15% ruling and the treatment-not-frequency principle in `instructions.md` § 3.

### M008 — GRAIL is ceremony-gated, not sealed
pending: true
approved_by: —
approved_on: —
evidence: `public.set_rewards`, `public.set_requirements`, `public.claimed_set_rewards`

Three of 69 top-tier cards are obtainable today by completing a set, and every card
those sets require is pool-reachable. Five claims exist.

**RESOLVED 2026-09-16.** The rail then called "Rail 7" blocked a post about them,
because a ceremony reward is not pool-reachable and the check knew only that one
route. Ashton amended SOUL: PULLABLE and EARNABLE are now distinct claims, and a card
qualifies on the earn route when it is a live `set_rewards` reward with every
requirement card pool-reachable. The rail is now named `OBTAINABLE`.

Two things surfaced in the same pass and matter more than the unlock. The check had
**never actually run** — both call sites passed a hardcoded `pool_reachable=True`, so
reachability was real only because `candidates()` guaranteed it upstream. And
`build_one` refused every `is_set_reward` row outright, so the amendment would have
unlocked nothing on its own. **Does not license** treating an upstream guarantee as a
rail: the lesson is that a rail which cannot fail is not a rail.

### M009 — Composition history begins 2026-09-11
pending: true
approved_by: —
approved_on: —
evidence: `ledger/runs.jsonl` — `composition` is `None` on 30 of 36 `draft_built` rows

Six labelled runs so far: `no_backdrop`, `shoe_crop` ×2, `angled` ×2, `shoe_only`.
`two_card_crop`, `off_centre` and `poster` have never run. Any claim about composition
performance rests on n=6 and must say so.

### M010 — The rails blocked a draft on 2026-09-16
pending: true
approved_by: —
approved_on: —
evidence: `ledger/proposals.jsonl`, `rails_blocked` row, `p_d65fe94c08`

First `rails_blocked` event in the ledger. Worth watching as a rate, not a one-off —
one block is not a trend and must not be reported as one.

### M011 — Revealed contrast threshold: n=1, a flagged card overridden at 1.325
pending: true
approved_by: —
approved_on: —
evidence: `ledger/proposals.jsonl` line 93 — `approved`, proposal_id `p_34f18679da`, ts `2026-09-18T19:13:24.133779+00:00`, `contrast: {"ratio": 1.325, "band": "flag", "overridden": true}`; posted as tweet `2101026827758162209`

**The first ruling on a contrast-flagged card.** The contrast gate logs the ratio on
every approval, flagged or not, so the threshold can later be re-derived from what
Ashton actually accepted rather than from the estimate it opened with
(`telegram_bot.contrast_gate`). This is row one of that dataset: a `shoe_crop` card
flagged at **1.325:1**, which Ashton **overrode** on 2026-09-18 after zooming it.

**n=1 is not a finding. It is the first row.** It does not license moving the flag
boundary, and it says nothing about cards below 1.325. One accepted card at 1.325 is
compatible with a true threshold anywhere below it. Re-derive only when there are enough
rulings on BOTH sides of the current boundary to say where he actually draws it.

Recorded only once the override landed on a real `approved` row (Ashton's ruling: never
record a ruling the ledger cannot point at). The override path that produced this row was
itself fixed the same day (`5ad3eb6`); before that fix, the same override would have
posted the draft rather than his edit — see `approval-posts-wrong-source`.
