#!/usr/bin/env bash
# install.sh [--agents] [--import <models.json>]
# Symlinks the nine skills into ~/.claude/skills (and ~/.agents/skills with --agents, for other harnesses that read
# the Agent Skills layout), then creates the user config ($AUTOPILOT_CONFIG_DIR, default ~/.config/maxxfactory)
# from templates/models.json, or from an existing roster with --import.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
IMPORT=""; AGENTS=0
while [ $# -gt 0 ]; do case "$1" in --agents) AGENTS=1;; --import) IMPORT="$2"; shift;; *) echo "unknown flag $1"; exit 1;; esac; shift; done
for dir in "$HOME/.claude/skills" $([ "$AGENTS" = 1 ] && echo "$HOME/.agents/skills"); do
  mkdir -p "$dir"
  # /maxxfactory-milestone became /maxxfactory-plan-more: drop the link of the old name (a link only, never a directory).
  if [ -L "$dir/maxxfactory-milestone" ]; then rm "$dir/maxxfactory-milestone"; echo "removed $dir/maxxfactory-milestone (renamed maxxfactory-plan-more)"; fi
  for s in maxxfactory-init maxxfactory-plan maxxfactory-plan-more maxxfactory-run maxxfactory-usage maxxfactory-idea maxxfactory-continue maxxfactory-status maxxfactory-clean; do
    ln -sfn "$HERE/skills/$s" "$dir/$s"; echo "linked $dir/$s -> $HERE/skills/$s"
  done
done
if [ -n "$IMPORT" ]; then "$HERE/bin/harness" init --import "$IMPORT"; else "$HERE/bin/harness" init; fi
echo "Next: open Claude Code (or any harness that loads ~/.claude/skills) and run /maxxfactory-init"
