#!/usr/bin/env bash
# Keep the local pushing-dispatch checkout on canonical origin/main.
# Safe by design: never merges, never discards local changes.
# If the tree is dirty or locally diverged, it logs DRIFT and exits non-zero.
set -uo pipefail

REPO="${PD_REPO:-$HOME/.local/share/pushing-dispatch/repo}"
LOG="${PD_SYNC_LOG:-/tmp/pd-sync.log}"
BRANCH="${PD_BRANCH:-main}"

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" >>"$LOG"; }

cd "$REPO" || { log "FATAL cannot enter $REPO"; exit 1; }

if [ -n "$(git status --porcelain)" ]; then
  log "DRIFT dirty worktree in $REPO — manual attention needed"
  exit 2
fi

git fetch origin "$BRANCH" >>"$LOG" 2>&1 || { log "ERROR fetch failed"; exit 3; }

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")
if [ "$LOCAL" = "$REMOTE" ]; then
  log "OK $LOCAL"
  exit 0
fi

if git merge-base --is-ancestor "$LOCAL" "$REMOTE"; then
  if git pull --ff-only origin "$BRANCH" >>"$LOG" 2>&1; then
    log "SYNCED $LOCAL -> $REMOTE"
  else
    log "ERROR ff-only pull failed"
    exit 4
  fi
else
  log "DRIFT local $LOCAL diverged from origin/$BRANCH $REMOTE"
  exit 5
fi
