# Troubleshooting

## Common Issues

### Worker dispatched but no output (tokens_in = 0)

**Symptom:** Worker status shows `starting` or `errored` with `tokens_in: 0` and no log file.

**Cause:** The bash wrapper exited before `claude -p` ran. This typically means brief assembly failed.

**Fix:**
1. Check if the includes: directive references a valid pack name:
   ```bash
   ls dispatch_packs/  # Verify pack files exist
   cat dispatch_packs/_registry.toml  # Verify registry entries
   ```
2. Run the wrapper with `--dry-run` to see the assembled command:
   ```bash
   bash bin/wrappers/sonnet.sh --task-file brief.md --cwd /tmp --dry-run
   ```
3. Check for the **indented includes: bug**: `includes:` is only recognized at column 0. If your task body contains the word "includes:" indented or mid-sentence, the parser may try to resolve it as a pack directive.

### Worker stalls (no progress for several minutes)

**Symptom:** Worker status shows `thinking` or `writing` with no token count increase.

**Possible causes:**
- API rate limiting (especially metered providers)
- Worker stuck in a tool-use loop
- Network connectivity issue to the provider endpoint

**Fix:**
1. Check the log file: `cat $(python cli.py status <worker-id> | python -c "import json,sys; print(json.load(sys.stdin)['log_path'])")`
2. If stuck in a loop, kill and re-dispatch with a more specific brief
3. If rate-limited, wait and retry (or switch to a different provider)

### "Unknown executor" error

**Symptom:** `Error: Unknown executor 'kimi'. Valid: ['opus', 'sonnet', 'haiku']`

**Cause:** The CLI loads executor choices from `dispatch_matrix.toml`. If the matrix file is missing or doesn't include the executor, it's rejected.

**Fix:**
1. Ensure `dispatch_matrix.toml` exists (copy from `.example` if needed)
2. Ensure the executor has an `[executors.kimi]` section in the matrix
3. Check `DISPATCH_MATRIX` env var if you're using a custom matrix path

### API key not found

**Symptom:** `Error: API key not found for pushing-dispatch/moonshot_api_key`

**Cause:** This is the old Moonshot API-key path. The current
`kimi-moonshot` executor uses Kimi CLI OAuth instead.

**Fix:** Use the Kimi CLI login path:
```bash
kimi login
python3 cli.py doctor
```

For other API-key providers, set the provider-specific env var or Keychain
account shown by `bash bin/check-prereqs.sh`.

### Worktree already exists

**Symptom:** `Worktree already exists: .claude/worktrees/my-slug`

**Fix:** Either use a different slug, or remove the existing worktree:
```bash
git worktree remove .claude/worktrees/my-slug
```

### Permission denied for nested dispatch

**Symptom:** Exit code 5, `PERMISSION_DENIED: kimi -> opus not in permissions matrix`

**Cause:** The permissions matrix in `dispatch_matrix.toml` does not allow this parent-child executor pair. This is intentional for cost-asymmetric pairs (metered parent spawning expensive subscription child).

**Fix:** If this is a legitimate use case, add the permission:
```toml
[nested_dispatch.permissions]
kimi.opus = true  # Caution: cost-asymmetric
```

### Depth exceeded

**Symptom:** Exit code 4, `DEPTH_EXCEEDED: depth=1, max=1`

**Cause:** The nesting depth cap is set to 1 (default). The worker tried to dispatch at depth 2.

**Fix:** Increase the depth cap:
```bash
export DISPATCH_MAX_DEPTH=2
```
Or update `dispatch_matrix.toml`:
```toml
[nested_dispatch]
max_depth = 2
```

### Auto-poll not starting

**Symptom:** Workers are active but no polling loop starts.

**Possible causes:**
1. Hook not configured in Claude Code settings
2. Stale marker file (from a crashed session)
3. Worker missing `dispatched_by_session_id` (created before session scoping was added)

**Fix:**
1. Verify hook config in settings.json (see INSTALL.md)
2. Remove stale markers: `rm -f $DISPATCH_ROOT/auto_poll_active_*`
3. Start polling manually: `/loop 90s /dispatch-poll`

### Budget shows $0.00 for everything

**Symptom:** `python cli.py budget` shows all zeros.

**Cause:** Subscription providers (Anthropic) have no per-token cost. The budget ledger tracks tokens but cost is $0.00.

**Fix:** This is expected for subscription providers. Budget tracking is most useful for metered providers (Moonshot, DeepSeek). Check `python cli.py budget --tree` to see token counts even when cost is zero.

## Debugging Tips

### View the assembled brief

Run any wrapper with `--dry-run`:
```bash
bash bin/wrappers/sonnet.sh --task-file brief.md --cwd /tmp --dry-run
```

This shows the full assembled prompt without executing.

### Check worker logs

```bash
# Get log path
python cli.py status <worker-id>
# Read the log
cat $(python cli.py status <worker-id> --field log_path)
```

### Validate the dispatch matrix

```bash
python cli.py validate-matrix dispatch_matrix.toml
```

### List all workers with full details

```bash
python cli.py list --tree  # Tree view with nesting
python cli.py list         # Flat list
```

### Force-kill a stuck worker tree

```bash
python cli.py kill <worker-id>           # Kill worker + all children
python cli.py kill <worker-id> --no-cascade  # Kill only this worker
```
