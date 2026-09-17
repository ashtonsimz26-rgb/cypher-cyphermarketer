#!/usr/bin/env python3.12
"""The four profile files are ONE file each, not two. Zero LLM, zero network.

The behaviour spec (SOUL.md, instructions.md, context.md, memory.md) is tracked
in this repo under profile/. Hermes and the runtime read it from
~/.hermes/profiles/cyphermarketer/. Symlinks reconcile those: one file, two
names.

★ WHY THIS SUITE EXISTS. A MIRROR WOULD BE TWO FILES UNDER ONE NAME, agreeing
only where you happened to look — the exact defect memory.md M001 and M004 were
written about, applied to the files that hold the rules. The symlink makes drift
structurally impossible, so the only remaining failure is the link being SEVERED:
Hermes replacing it with a regular file, a restore-from-backup landing a copy on
top, someone editing the profile path directly. Then edits go somewhere git
cannot see and nothing says so.

That risk was named when option (d) was ruled. A named risk with no detector is
unmonitored, not accepted. This is the detector.

Hermes itself is safe here — its two SOUL.md write paths use Path.write_text(),
which follows a symlink and writes THROUGH to the target, and utils.atomic_replace()
resolves symlinks on purpose (its docstring names git-tracked profile packages as
the case it protects). Verified empirically 2026-09-17. This suite guards against
everything else.
"""
import os, subprocess, sys, tempfile
from pathlib import Path

FAILS = []
def ok(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c: FAILS.append(m)

REPO = Path(__file__).resolve().parent.parent
REPO_PROFILE = REPO / "profile"
PROFILE_DIR = Path(os.environ.get(
    "HERMES_PROFILE_DIR", Path.home() / ".hermes/profiles/cyphermarketer"))
FILES = ["SOUL.md", "instructions.md", "context.md", "memory.md"]
SCRIPT = REPO_PROFILE / "link_profile.sh"

print("\n=== 1. THE REPO HOLDS THE REAL FILES ===")
for f in FILES:
    p = REPO_PROFILE / f
    ok(p.is_file() and not p.is_symlink() and p.stat().st_size > 0,
       "profile/%s is a real, non-empty file in the repo" % f)

print("\n=== 2. THE PROFILE PATH HOLDS LINKS, NOT COPIES ===")
for f in FILES:
    d = PROFILE_DIR / f
    if not d.exists() and not d.is_symlink():
        ok(False, "%s is MISSING at the profile path — run profile/link_profile.sh" % f)
        continue
    # The whole point: a regular file here means the link was severed and the
    # agent may be reading content that is not under version control.
    ok(d.is_symlink(),
       "%s is a symlink (a regular file here = severed link, unversioned edits)" % f)
    if d.is_symlink():
        ok(os.readlink(d) == str(REPO_PROFILE / f),
           "…and it points at profile/%s in this repo" % f)

print("\n=== 3. THEY RESOLVE, AND THE RUNTIME READS THEM ===")
for f in FILES:
    d = PROFILE_DIR / f
    ok(d.exists() and d.resolve() == (REPO_PROFILE / f).resolve(),
       "%s resolves to the repo copy (no dangling link)" % f)

sys.path.insert(0, str(REPO))
from research import writer as W, memory as MEM  # noqa: E402
ok(W.SOUL.exists() and W.SOUL.resolve() == (REPO_PROFILE / "SOUL.md").resolve(),
   "writer.py:SOUL resolves into the repo — the prompt reads the tracked file")
ok(MEM.MEMORY.exists() and MEM.MEMORY.resolve() == (REPO_PROFILE / "memory.md").resolve(),
   "memory.py:MEMORY resolves into the repo — the loader reads the tracked file")
ok("THE GOAL" in W.SOUL.read_text(),
   "SOUL.md read through the link still carries THE GOAL (content, not just a path)")

print("\n=== 4. THE CHECKER ITSELF FAILS WHEN IT SHOULD ===")
# A checker that cannot fail is the summary-that-cannot-report-failure again.
# Prove it fires, against a sandbox — never against the real profile directory.
ok(SCRIPT.is_file() and os.access(SCRIPT, os.X_OK),
   "profile/link_profile.sh exists and is executable")

def run_check(profile_dir):
    env = {**os.environ, "HERMES_PROFILE_DIR": str(profile_dir)}
    return subprocess.run([str(SCRIPT), "--check"], capture_output=True,
                          text=True, env=env, cwd=str(REPO)).returncode

with tempfile.TemporaryDirectory() as td:
    sandbox = Path(td) / "profile"
    sandbox.mkdir()
    ok(run_check(sandbox) != 0, "--check FAILS on an unlinked directory (fresh clone)")

    for f in FILES:
        (sandbox / f).symlink_to(REPO_PROFILE / f)
    ok(run_check(sandbox) == 0, "--check PASSES once the links are correct")

    # THE failure mode: link severed, content diverged.
    (sandbox / "SOUL.md").unlink()
    (sandbox / "SOUL.md").write_text("edited outside git\n")
    ok(run_check(sandbox) != 0,
       "--check FAILS when a link is severed and the copy DIFFERS (unversioned edits)")

    # Severed but identical is still a failure — the next edit would be lost.
    (sandbox / "SOUL.md").unlink()
    (sandbox / "SOUL.md").write_text((REPO_PROFILE / "SOUL.md").read_text())
    ok(run_check(sandbox) != 0,
       "--check FAILS when severed-but-identical too (relink is safe, silence is not)")

print("\n=== 5. NOTHING WIDENED TO THE DIRECTORY ===")
env_file = PROFILE_DIR / ".env"
if env_file.exists():
    ok(not env_file.is_symlink(),
       ".env is still a real file in the profile dir — credentials never moved into git")
else:
    print("  SKIP  .env not present at the profile path")
ok(not (REPO_PROFILE / ".env").exists(),
   "no .env was copied into the repo's profile/ directory")
tracked = subprocess.run(["git", "ls-files", "profile/"], capture_output=True,
                         text=True, cwd=str(REPO)).stdout.split()
ok(not any(t.endswith(".env") or "/.env" in t for t in tracked),
   "git tracks no .env under profile/ (tracked: %d file(s))" % len(tracked))

print("\n" + ("ALL PASS" if not FAILS else "%d FAILURE(S): %s" % (len(FAILS), FAILS)))
sys.exit(1 if FAILS else 0)
