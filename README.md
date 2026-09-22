# cyphermarketer

X marketing agent for CYPHER, posting as **@appCYPHERR**.

**Scope contract:** `~/Documents/openclaw/CYPHER/CYPHER/CYPHER_MARKETING_AGENT_STRATEGY.md`
(locked 2026-08-19). **Voice + rails:** `profile/SOUL.md` (canonical; read at
`~/.hermes/profiles/cyphermarketer/SOUL.md` via symlink).
Anything not ruled in the contract is a HALT-and-ask, not a judgement call.

---

## ★ IMAGES ARE OFF — `IMAGES_ENABLED` (turned off 2026-09-22 at Ashton's request)

**What it does.** One setting decides whether the marketer makes or sends any image.
With `IMAGES_ENABLED=false`, every proposal and post is **text only**:

- no card render, no generated backdrop, and **no call to either image API**
  (OpenAI or xAI) — zero image spend. The spend breaker does not apply; the
  4-post/24h cap still does.
- the **Frame Check is skipped**, because there is no card to measure. The skip is
  recorded three ways: a `frame_check_skipped` row in `ledger/runs.jsonl`,
  `contrast.band = "skipped_text_only"` in the proposal's `rails_ctx`, and a line
  in the Telegram proposal note.
- the Telegram proposal is a **text message**, not a photo. It still carries the
  proposal id, the draft and the reply grammar. `approve`, `reject`, `edit:`,
  `tweak` and `override` all work as before.
- posting to X sends **text only**: no media upload. An image proposal made before
  the switch was turned off, and approved after it, also posts without its image.
- the composition is recorded as **`text_only`** on the proposed, draft and posted
  rows. The rails map it to `card_shows_value = False` in the one shared function
  both doors call (`research/composition.py: rails_card_shows_value`), so the
  draft and approve doors agree. A text-only post shows no EST. VALUE figure, so
  no attribution sentence is required. `tests/test_rails_door_parity.py` holds it.
- the format report keeps `text_only` out of the image composition distribution,
  and shows each format's image/text-only split beside its numbers.

**Where it lives.** `.env`, one line: `IMAGES_ENABLED=false`. It's read by
`switches.py: images_enabled()`, the only reader. If the key is absent, images are
**on** (the code default). A value that isn't a recognised true/false reads as
**off**, with a warning, so a typo can never turn image spend back on.

**How to turn images back on.** In `.env`, set `IMAGES_ENABLED=true` (or delete the
line). Nothing else changes: the image code was never deleted or commented out,
and the next digest renders and sends images exactly as before.
`python3.12 switches.py` prints the current state. `tests/test_images_switch.py`
covers both directions.

## `ledger/research.jsonl` has a RETRACTION — read it through `research/ledger_read.rows()`

The ledger is append-only. Line 714 is a `retraction` row (2026-09-22, Ashton's ruling)
that withdraws 368 rows `tests/test_cypher_resolver.py` wrote into the real ledger
before `616965e`. They're 305 `cypher_uri_malformed` and 63 `cypher_resolve_failed`,
each named by line number and content hash. No existing row was changed. The row
records its matching rule and evidence, including the judgement call on the 61 bare
`cypher://` rows (a value production could also write; they're retracted only because
each sits inside a burst with all five test-only URIs). `rows()` skips retracted rows
and **refuses** if a listed line no longer matches its hash. A direct `open()` of the
file counts the 368 back in. `tests/test_research_retraction.py` re-derives the set
independently and holds the row to exactly those 368.

## WHERE BEHAVIOUR IS SPECIFIED

The agent's behaviour is specified in **five** places. As of 2026-09-17 all five
live in this repo: the four `.md` files moved under `profile/` and are reachable at
the Hermes profile path by symlink. Reading the repo is now reading the whole system.

| # | where | owns | in repo? |
|---|---|---|---|
| 1 | `profile/SOUL.md` | canonical voice, editorial bar, **THE GOAL**, hard rails, autonomy phase | **yes** |
| 2 | `rails.py` | the machine-checkable subset — 9 named rails, each mapped to a SOUL clause in the file header | yes |
| 3 | `profile/instructions.md` | the post-construction playbook: sequence, formats, craft rules, tier treatment, image brief | **yes** |
| 4 | `profile/context.md` | stable facts: what CYPHER is, what the tiers mean, what is postable, who the audience is | **yes** |
| 5 | `profile/memory.md` | evidence: what shipped, what was rejected, what the numbers say | **yes** |

All four are read at `~/.hermes/profiles/cyphermarketer/`, where they exist as
**symlinks into `profile/`**. See PROFILE FILES below before editing either path.

**Precedence, highest first:**

    SOUL.md  >  rails.py  >  instructions.md  >  context.md  >  memory.md

Two rules ride on that chain and neither is negotiable:

1. **`rails.py` can only ever be a SUBSET of SOUL.** If the code and SOUL disagree,
   that is a bug in rails — never a new rule, and never evidence that SOUL has changed.
2. **`memory.md` is evidence, never instruction.** An entry may motivate a change to
   `instructions.md`. It may never override one. Entries carry `pending: true` until
   Ashton flips the flag; the agent may write one freely, may never flip it, and may
   never read a pending entry as guidance.

**The enforced text stays in code.** `research/writer.py:147` holds `FORMAT_CONTRACT`
— the string actually sent to the model. `REGISTER` is not a separate constant: it is a
section *inside* that string (line 161), alongside the JSON contract, the character
ceiling and the swap test. `instructions.md` references it; it does not restate it.
Copying that text into a document would create a fourth source of truth that drifts
without anyone noticing.

---

## PROFILE FILES — ONE FILE, TWO NAMES

The four behaviour files live **here, in git**, under `profile/`. Hermes and the
runtime read them from `~/.hermes/profiles/cyphermarketer/`, where each is a
**symlink** into this repo.

**Why symlinks and not a mirror.** A mirror is two files under one name, agreeing
only where you happened to look — which is the precise defect `memory.md` M001 and
M004 were written about, applied to the files that hold the rules. A symlink is one
file with two names, so drift is not unlikely, it is impossible. There is no
precedence rule to remember because there is nothing to choose between.

**After a fresh clone, run this once.** It is a script and not a paragraph so it
cannot be done half-right:

```bash
./profile/link_profile.sh          # create or repair the links
./profile/link_profile.sh --check  # verify only; exit 1 if wrong
```

It never touches `.env` or anything else in the profile directory. Credentials
stay machine-local and out of git; only the four `.md` files moved.

**The one real failure mode is a SEVERED link** — something replacing a symlink
with a regular file, after which edits go where git cannot see them and nothing
says so. `tests/test_profile_links.py` is the detector, it runs in `tests/run_all.py`
with everything else, and it proves the checker itself fails rather than trusting
that it would.

Hermes is safe here and this was checked rather than assumed: both of its SOUL.md
write paths use `Path.write_text()`, which follows a symlink and writes *through*
to the target, and `hermes/utils.py:atomic_replace()` resolves symlinks deliberately
— its docstring names git-tracked profile packages as the case it exists to protect.
A SOUL edit made in the Hermes web UI therefore lands in the tracked file and shows
up as an ordinary `git diff`.

### `memory.md` will show as an uncommitted change. That is correct.

`memory.md` is an evidence log the agent appends to, so a new `pending: true` entry
makes the working tree dirty until someone commits it. **This is the feature, not a
problem to fix.** It puts the approval queue in `git status`, where an entry waiting
on Ashton is visible, rather than sitting invisibly in a file nobody diffs. Do not
gitignore it and do not auto-commit it — review the entry, then commit it like
anything else.

## WORKING CONVENTIONS

**Every string mutation asserts its match count.** When editing source
programmatically, `assert s.count(old) == 1` before `s.replace(old, new)` —
always, including "obviously unique" anchors.

Why this is a rule and not a preference (2026-09-10): while wiring the moment
lane into `daily_digest.draft_with_gate8`, one edit in a batch of six skipped
the assertion. Its anchor had already been changed by an earlier replacement in
the same script, so it matched zero times and silently did nothing. The script
reported success. The digest then went from producing a WRONG post (the linking
line shipped alone, dropping the verified moment and leaving "that day" with no
antecedent) to producing NO post — a second, different bug — while every log
line said the fix had applied. It cost two dry-run cycles to find.

A raised error is cheap. A silent no-op is expensive, because it looks exactly
like success and the next symptom appears somewhere else. The same applies to
any narrowing operation whose "nothing matched" case is indistinguishable from
"nothing needed changing": prefer the form that fails loudly.

## Layout

| Path | Role |
|---|---|
| `x_client.py` | X posting client — media upload + create tweet, OAuth 1.0a |
| `content/` | exact post texts, one file per post (byte-verbatim) |
| `ledger/posts.jsonl` | append-only record of every attempt / post / failure |
| `.env` | credentials, chmod 600, **never committed** (`.env.example` is the template) |
| `data/enrichment_scope.md` | what enriching the 111 spec-only dossiers would cost, and why it is sequenced after the concentration problem |

## Grounded decisions (build session 2026-08-19)

- **v2 endpoints only** — `POST /2/media/upload`, `POST /2/tweets`. The v1.1 media
  endpoint still answers 200 despite its 2025-06-09 sunset; it is treated as dead.
- **OAuth 1.0a for everything.** Probed live: `/2/media/upload` accepts it and takes a
  simple single-request multipart for images — no INIT/APPEND/FINALIZE. Public docs
  contradict each other on this point; the probe is the authority.
- **Hand-rolled signer**, no OAuth library (none installed on the mini; the surface is
  two endpoints). ⚠️ Query-string params must be folded into the signature base string;
  body params must not. A GET that skips this 401s.
- **Telegram uses a SIBLING bot token**, never CPA's. `getUpdates` is destructive
  per-token — a second poller on CPA's token permanently consumes CPA's approval
  decisions. Same chat is fine; same token is data loss.
- **Card art v1 = repo imagesets.** CPA's renderer binary may later be invoked
  read-only; **never run `swift build` in `cpa/CypherCardRenderer/`** — CPA's live
  proposal path depends on that built binary. No third `SneakerCardView` fork, ever.

## Rails enforced in code

- Explicit `--post` required; default is a dry run.
- Hard cap 4 posts / rolling 24h, counted from the ledger.
- Refuses text over X's 280 weighted chars (URLs count 23, emoji 2).
- Ledger is append-only: intent recorded *before* the network call, outcome after, so a
  crash mid-flight is still visible.
- Credentials load by path and are never logged, echoed, or written to the ledger.

## Usage

```sh
python3.12 x_client.py --text-file content/<post>.txt --image <path>          # dry run
python3.12 x_client.py --text-file content/<post>.txt --image <path> --post   # publish
```

## Scheduling — operational lessons (2026-08-19, learned the hard way)

**★ `last_exit=0` on a launchd job that has NEVER RUN proves nothing.**
launchd reports `0` for a job it has merely loaded. On install night three of
four jobs were broken and every one of them read `exit=0`, so a status-column
check reported "all healthy" while the poller was in fact failing every 300s.

> **Verify a job by forcing a real run and capturing its output — never by
> reading the status column.**
> ```sh
> : > logs/<label>.out.log
> launchctl kickstart -k gui/$(id -u)/<label>
> until ! launchctl list | grep -q "^[0-9]*[[:space:]].*<label>"; do sleep 2; done
> launchctl list | grep <label>          # NOW last_exit means something
> cat logs/<label>.out.log               # and this is the actual proof
> ```
> This is the same failure shape as the `assert` that can be satisfied by
> absence: a check structurally incapable of failing.

**★ Do not generate plists from shell loops — zsh does not word-split.**
`for a in $2` splits in bash but NOT in zsh, so `"script.py --flag value"`
became a single `<string>` argv entry and the job died with
`can't open file 'script.py --flag value'`. Plists are generated with
`plistlib` (see the git history), where argv is a real list. Jobs taking no
arguments were unaffected, which is why the breakage was partial and easy to
miss.

**★ `ai.cyphermarketer.watchdog` is a DEAD LABEL — do not resurrect it.**
The live health job is **`ai.cyphermarketer.health`**. The old label wedged
itself in launchd's per-user database after first registering with the
malformed plist above: it returned **78 (EX_CONFIG) with zero stdout and zero
stderr** — the process image never ran — and survived `bootout` + plist
deletion + fresh `bootstrap`. Proven label-specific by running the identical
script under a throwaway label, where it worked perfectly. Renaming was the
fix; the root cause was never fully identified (a reboot would likely clear it
too). **If you find yourself re-creating a job named `...watchdog`, don't.**

## Schedule + contention with CPA

| Job | Schedule |
|---|---|
| `ai.cyphermarketer.digest` | 09:00 local, daily |
| `ai.cyphermarketer.poller` | every 300s |
| `ai.cyphermarketer.drops` | every 7200s |
| `ai.cyphermarketer.health` | every 3600s |

The digest sits at **09:00** because CPA's daily round starts at 08:00 and takes
**31–38 minutes** (measured from CPA's own logs across three days, not
estimated) — 08:30 would land inside CPA's window. 09:00 clears the worst
observed round by ~22 minutes and still lands approved posts in the 9–10am
window.

**Renderer sharing is safe without a lock.** CPA's round does invoke the same
`CypherCardRenderer` binary, but it passes card JSON via **stdin** and writes
output to its own directories — it only sets `cwd` to the renderer dir and
never writes there, and `CypherCardRenderer/.build` is gitignored in CPA, so
`assert_renderer_pristine()` cannot false-alarm on CPA activity. Shared
resources are CPU, memory, and the supabase CLI (separate read-only
connections). **Memory is the only real contention** on a 16 GB machine, and
the digest is light (one card render + one network generation) against CPA's
35-card batch.

## Lesson: verify what a number MEANS before verifying its value

**A rail comparing two different statistics manufactures false alarms.**

On 2026-08-19 the price rail (commit `77f29c2`) was tightened to stop a real bug
— it had been treating "a recent PK file mentions this style code" as proof a
price was correct, and green-lit a `$2,000` claim for the DQM Bacon when PK's
file that morning read `$450`. That fix was right.

But the replacement compared the catalog's `estimated_resale` against
`hits[0].lowest_price_cents`, and reported that **26 of 30** showcase cards were
wrong. They were not. Two compounding mistakes:

1. **Wrong file.** It read the RAW ARCHIVE (`raw_market/price_refresh/…`) rather
   than PK's SNAPSHOT (`data/price_history/<sku>.jsonl`).
2. **Wrong field — one PK explicitly warns about.** From the engine source:
   *"Algolia sorts ascending by lowest_price_cents, so this is the cheapest
   variant — typically a toddler size. Stored for forensic context only — DO NOT
   use for decisions; use canonical_price_cents."*

`lowest_price_cents` is the lowest ask for ONE ARBITRARY SIZE. On the Bacon that
is $450 (size 10) while size 10.5 asks $2,000 — which is exactly the catalog's
number. **Both figures were real. They were different statistics.**

The catalog was never the problem the alarm claimed. The yardstick was.

**What to do instead:** PK already computes what was needed —
`adult_band_min/median/max_cents`, `adult_band_variant_count`,
`observed_confidence`, and a `canonical_hold_reason` when the sample is too thin.
Read PK's mandate-grade fields; never re-derive a band from raw hits, and never
quote `lowest_price_cents`.

**Generalisation worth keeping:** before trusting a comparison, confirm both
sides measure the same thing. A confident number derived from the wrong
statistic is more dangerous than a missing one, because it survives review.

### Price eligibility — current rule

`rails.price_claim_allowed()` gates on two things:
- **Liquidity:** fewer than `MIN_LISTINGS` (3) live adult-band variants blocks a
  claim in EITHER direction. A one-listing market cannot confirm a catalog value
  or condemn it.
- **Range, not point:** the catalog value must sit inside PK's adult band.
  Outside in either direction is a real signal (too high overstates; too low
  understates a grail).

Each proposal's metadata states the band and `n` it verified against.
`price_audit.py` re-runs the scan and appends out-of-range cards to
`ledger/pk_repricing_queue.jsonl` for PRICEKEEPER's operator loop — **flag only,
it never changes a price.**

### Deferred rulings (2026-08-20) — do not re-litigate cold

- **B — relabel the card's "EST. VALUE" field** (e.g. to a range, or
  "EST. VALUE (deadstock)"). DEFERRED: `SneakerCardView.swift` is a LOCKED file
  and this is a product call, not a cleanup.
- **C — re-price the catalog at scale via PK.** DEFERRED to PRICEKEEPER's own
  arc: its autonomous write gate needs ≥0.70 confidence and currently sits at
  0.58, so corrections stay operator-supplied (34 SKUs applied to date).

## Incident 2026-08-21: ten hours of alerts, two real bugs, and a wrong hypothesis

**The reboot hypothesis was wrong.** The mini was rebooted the night of Aug 20 and
every job came back correctly — env, PATH, working directory, state-file perms
and Keychain access were all fine. Nothing needed re-arming. Chasing
reboot-survival would have been chasing a ghost; the logs said otherwise.

**Two genuinely separate bugs, neither reboot-related:**

### 1. The watchdog watched itself into a permanent alarm

`watchdog.py` returned `1` whenever it raised any alert, AND listed its own job
in `JOBS`. So once it alerted for any reason, its own `last_exit=1` became an
alert on the next run — which made it exit 1 again. **A self-sustaining loop
that could never return to healthy.**

The seed was real: the digest's `NameError` on 2026-08-20. But that was fixed the
same day, and the watchdog kept alerting hourly for ten more hours on nothing but
itself. The overnight alerts were *its own echo*.

> **A job's exit code is an alarm OUTPUT, not a health signal about itself.**
> For the watchdog, `loaded` is the only self-check that means anything. It now
> reports its own loaded state and never alerts on its own exit code.

### 2. `--max` capped candidates EVALUATED, not proposals produced

`candidates(min(a.max, 3))` returned exactly `--max` candidates. With `--max 1`
the digest tried **one** shoe; that shoe hit `skipped_no_hook`, and the morning
produced nothing. The job exited 0 — it had not failed, it had been starved.

Combined with a deliberately strict editorial bar, a one-candidate search
guarantees frequent silence. The pool is now `POOL_FACTOR (8) x` the target and
the loop stops at the target, so `--max` means what its help text always claimed.

**The generalisable part:** a strict quality gate and a narrow candidate pool are
individually reasonable and jointly produce silence. When you tighten a filter,
widen what you feed it.

### Alerting is now a diagnosis, not a doorbell

Ten identical `last_exit=1` messages never once named the `NameError`. Alerts now
carry the last stderr lines inline, and 3+ consecutive failures of the same job
escalate to `🔴 PERSISTENT FAILURE (n CONSECUTIVE)` so severity is visible at a
glance. Alerts are also ledgered to `runs.jsonl` — previously they were printed
and lost, which is why the alert history could not be reconstructed.

### Verification note

`launchctl kickstart` with captured output remains the standard (see the earlier
lesson). This incident adds a caveat rather than a reboot clause: **a job exiting
0 is not proof it did its job.** The digest exited 0 all morning while producing
nothing. Check the ledger for the intended OUTPUT, not just the exit code.
