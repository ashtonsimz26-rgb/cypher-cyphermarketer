# cyphermarketer

X marketing agent for CYPHER, posting as **@appCYPHERR**.

**Scope contract:** `~/Documents/openclaw/CYPHER/CYPHER/CYPHER_MARKETING_AGENT_STRATEGY.md`
(locked 2026-08-19). **Voice + rails:** `~/.hermes/profiles/cyphermarketer/SOUL.md` (canonical).
Anything not ruled in the contract is a HALT-and-ask, not a judgement call.

## Layout

| Path | Role |
|---|---|
| `x_client.py` | X posting client — media upload + create tweet, OAuth 1.0a |
| `content/` | exact post texts, one file per post (byte-verbatim) |
| `ledger/posts.jsonl` | append-only record of every attempt / post / failure |
| `.env` | credentials, chmod 600, **never committed** (`.env.example` is the template) |

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
