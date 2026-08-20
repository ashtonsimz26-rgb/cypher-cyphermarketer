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
