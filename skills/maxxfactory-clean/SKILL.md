---
name: maxxfactory-clean
description: Leave a repository clean. Commits every meaningful uncommitted change to the current branch, deletes junk, removes orphan and finished worktrees and their branches, deletes local branches whose work is already merged or safely on a remote, and never destroys work in progress — it reports each one at the end with the command to continue it (/maxxfactory-continue). Reuses bin/gc, bin/pipeline status and bin/rebase-wt when the repo has an autopilot run. Use when the user says "/maxxfactory-clean", "clean the repo", "commit everything and remove the worktrees", "remove orphan worktrees", "tidy up the branches".
---

# Autopilot: clean

**Caveman, always.** Your first action: invoke the `caveman` skill and keep it for the whole session. If it is not installed, follow its rules anyway.

`bin/<x>` is the `bin` directory next to this SKILL.md (`~/.claude/skills/maxxfactory-clean/bin/<x>` after `install.sh`); resolve it once and use absolute paths.

Goal: at the end, `git status` is empty, `git worktree list` holds only the main checkout plus the worktrees that hold work in progress, and every local branch is either the current one, a branch with work in progress, or gone. Nothing of value is lost: when in doubt, keep and report, never delete.

## Steps

1. **Where.** `git rev-parse --show-toplevel`, current branch, default branch (`git symbolic-ref refs/remotes/origin/HEAD`, else `main`). Nearest `.maxxfactory/state.json` (or `$AUTOPILOT_REPO`): if found, this is an autopilot project; read `branch`, `inflight`, `queue`, `done`; its worktrees directory is `<repo>-wt`, next to the repo (`bin/pipeline wt` prints it; an older state.json may also name a `worktrees_dir` elsewhere, which `bin/gc` still collects). A rebase, merge or cherry-pick in progress in the main checkout: stop and report it, touch nothing.

2. **What is in flight (autopilot projects only).** `bin/pipeline status` and `bin/bgrun ls`. Every ticket in `inflight` or `queue`, its worktree and its `maxxfactory/<ISSUE>` branch are work in progress: never commit in, rebase, or remove them. If `pipeline run` is alive, do not race it: skip step 4 for its worktrees and say so.

3. **Uncommitted changes in the main checkout.** `git status --porcelain` and `git diff` (also `git diff --cached`). Read every changed and untracked file, then for each one decide:
   - **meaningful** (source, docs, tests, config the project uses): commit it to the current branch. Group by intent into small commits with conventional messages (`fix(scope): ...`, `feat(scope): ...`), never one catch-all "wip" commit. Run the project's fast checks first when they exist (syntax check, linter, the test file that covers the change); a change that breaks them is work in progress: leave it uncommitted and report it.
   - **junk** (logs, `*.log`, scratch output, editor and OS files, build output, `__pycache__`, temporary patches already applied): delete it. A kind of junk that will come back (a generated file, a log the tools write): add a pattern to `.gitignore` and commit that instead.
   - **unclear** (half-written code, a file you cannot tell apart from work): leave it, report it as work in progress.
   Never commit secrets (`.env`, keys, tokens, `credentials*`): leave them, warn. On the default branch, commit only when the project already commits there (look at `git log`); otherwise create a branch first.

4. **Worktrees.**
   - Autopilot project: `bin/gc --dry-run`, then `bin/gc`. It prunes dead entries, removes done and long-empty ticket worktrees (saving leftover work as `.maxxfactory/gc/*.patch`) and their branches, and prints a `GC orphan` line for each worktree that holds work but is not in flight. Decide each orphan: its commits are already in the project branch (`git branch --contains`, `git cherry`) and it has no uncommitted change → remove it; otherwise it is work in progress → keep and report.
   - Every repo, for the worktrees `bin/gc` does not look at (outside the worktrees directory, or no state.json): `git worktree prune -v` (entries whose directory is gone), then for each remaining worktree except the main checkout: `git -C <wt> status --porcelain` and `git rev-list --count <current>..<wt-branch>`. Clean and nothing of its own (or all of it already merged: `git cherry <current> <wt-branch>` shows no `+`) → `git worktree remove <wt>` and delete its branch. Locked (`git worktree list --porcelain` says `locked`), dirty, or with unmerged commits → work in progress: keep and report.
   - Directories in the worktrees directory that git does not know (no entry in `git worktree list`): an orphan directory. If it holds no file outside build output and dependencies, remove it. If it holds files, copy them as a tarball to `.maxxfactory/gc/<name>-<time>.tgz` (or the scratchpad when there is no `.maxxfactory/`), then remove it, and name the tarball in the report.
   - Never touch worktrees of other repositories, even if they sit in the same parent folder.

5. **Branches.** `git branch -vv --format='%(refname:short) %(upstream:short) %(upstream:track)'`. For each local branch other than the current one, the default branch, the project branch and the in-flight ones:
   - fully merged into the current or the default branch (`git branch --merged`, or `git cherry` shows no `+`): `git branch -d` (`-D` only after `git cherry` proved every commit is in).
   - identical to its upstream (`[gone]` excluded, no `ahead`): the remote keeps it; delete the local copy and print the remote ref so the owner can restore it (`git branch <name> <remote>/<name>`).
   - upstream `[gone]` and every commit merged: delete. Unmerged commits, ahead of its upstream, or no upstream with commits of its own: work in progress, keep and report.
   Never delete a remote branch, never force-push, never rewrite pushed history.

6. **Stashes.** `git stash list`. Report each one (age, message, `git stash show --stat`); never drop a stash unless its changes are already in the current branch (`git diff stash@{n}^ stash@{n}` applies as a no-op), then drop it.

7. **Push.** Only if the current branch tracks a remote and the owner asked for pushes before (`state.json` `push`, or the request). Otherwise say how many commits are ahead.

8. **Report, in a few lines:**
   - committed: one line per commit (`hash subject`);
   - deleted: junk files, worktrees, branches (with the remote ref that still holds it), stashes;
   - saved: every patch or tarball written before a removal;
   - **work in progress**, one line per item: path or branch, why it was kept (dirty files, N unmerged commits, in flight, locked, unclear change), and what to do next. For an autopilot ticket or orphan worktree: `/maxxfactory-continue` resumes it. For a plain branch or worktree: `git switch <branch>` (or `cd <wt>`) and finish it, or merge it with `git merge <branch>`.
   End with `git status --short` (empty) and `git worktree list`. If anything is in progress, the last line is: `Work in progress left: run /maxxfactory-continue to resume it.`

## Rules

- No work is lost: every removal of a worktree or branch with content of its own is preceded by proof it is merged, or by a saved patch or tarball.
- Never touch in-flight or queued tickets, locked worktrees, other repositories, remote branches, or pushed history.
- Never `git reset --hard`, `git clean -fdx`, `git checkout -- .` on the main checkout: delete junk file by file.
- Commit messages describe the change, not the cleanup.
