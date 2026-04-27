# Orchestrating with ai-dispatch

This is the complete guide for an orchestrator model (or human operator) using ai-dispatch to manage worker agents. Treat it as a runbook.

## 1. Authoring a Brief with a Custom System Prompt

A brief is the contract between the orchestrator and the worker. It defines what the worker sees, what it does, and how it reports back.

### Basic brief structure

```markdown
---
title: Fix authentication bug in login handler
executor: sonnet
includes:
  - branch-safety
---

# Task

Fix the race condition in `src/auth/login.py:handle_login()` where
concurrent requests can create duplicate user sessions.

## Context

The bug was reported in issue #142. The login handler reads the session
store, checks for existing sessions, then writes a new one. Under load,
two requests can pass the check before either writes.

## Constraints

- Only modify src/auth/login.py
- Add a test in tests/test_login.py
- Do not refactor surrounding code
- Use the existing session lock mechanism in src/auth/locks.py
```

### Custom system prompts

The worker's system prompt is assembled from:
1. `_baseline.md` (always prepended, carries branch safety + status protocol)
2. Included packs (declared via `includes:`)
3. The `executor_prompt.md` template (wraps everything with worker identity + question protocol)

To give a worker a completely custom voice or role, write the instructions in the brief body:

```markdown
---
title: Code review with security focus
executor: opus
includes:
  - branch-safety
---

# Your Role

You are a senior security engineer reviewing code for vulnerabilities.
Focus on: injection attacks, auth bypass, data exposure, SSRF.
Ignore style issues unless they mask a security concern.

Report findings in this format:
- **CRITICAL**: immediate risk, blocks merge
- **HIGH**: should fix before merge
- **LOW**: note for future

# Task

Review all changes on branch `feature/user-api` against `main`.
```

## 2. Declaring Nested Dispatch

To allow a worker to spawn sub-workers, add a `nested_dispatch:` block:

```yaml
---
title: Refactor auth module
executor: sonnet
nested_dispatch:
  max_depth: 2
  allowed_executors: [haiku, kimi]
---
```

At launch, `breakout.py` injects `DISPATCH_NESTED=1` and `DISPATCH_MAX_DEPTH=2` into the worker's environment. The worker can then call:

```bash
python cli.py task start \
  --parent-id "$DISPATCH_WORKER_ID" \
  --parent-executor sonnet \
  --depth 1 \
  --executor haiku \
  --task-file /path/to/subtask.md \
  --cwd /path/to/worktree
```

## 3. Picking the Right Executor

### The routing matrix

`dispatch_matrix.toml` encodes every executor's strengths. The auto-router consults it, but you can (and should) override when you have specific knowledge.

### Decision table

| Task type | Best executor | Why |
|-----------|--------------|-----|
| Long doc summarization (>50K tokens) | `kimi` | 256K context window, cheap per-token |
| Mechanical refactor (rename, move) | `kimi` or `haiku` | No reasoning needed, fast |
| Hard coding with clear spec | `deepseek` or `kimi-think` | Strong code generation |
| Architecture/planning | `opus` | Best synthesis and judgment |
| Trivial (lint fix, typo) | `haiku` | Fast, cheapest |
| Code review | `opus` | Needs judgment about trade-offs |
| Default (no strong signal) | `sonnet` | Good all-rounder |

### When to override auto-routing

- You know the task needs a large context window -> set `executor: kimi`
- You know the task is trivial -> set `executor: haiku`
- The auto-router picked sonnet but this needs real thinking -> set `executor: opus`

## 4. Scoping Context via includes: Packs

### When to use packs

Use `includes:` when:
- Multiple briefs need the same context (DRY)
- The context is large enough to be worth separating
- The context is reusable across different tasks

### When to inline

Write context directly in the brief when:
- It's task-specific and won't be reused
- It's short (under 50 lines)
- It references specific files or line numbers

### Available packs

| Pack | What it provides |
|------|-----------------|
| `dispatch-protocol` | Matrix, modes, routing, budget details |
| `branch-safety` | Worktree rules, commit discipline |
| `brief-format` | Brief schema and includes: protocol |
| `nested-dispatch` | Permissions, budget cascade, depth caps |
| `orchestrator-protocol` | How to use the dispatch system |

### Creating custom packs

1. Write a markdown file in `dispatch_packs/`
2. Register it in `dispatch_packs/_registry.toml`
3. Reference it in briefs via `includes:`

## 5. Handling Worker Failures

### Exit statuses

| Status | Meaning | Your action |
|--------|---------|-------------|
| `DONE` | Success | Review changes, merge |
| `DONE_WITH_CONCERNS` | Success with notes | Read concerns, decide |
| `NEEDS_GUIDANCE` | Blocked on your input | Read question file, respond |
| `BLOCKED` | Cannot proceed | Diagnose blocker |
| `errored` | Crashed or failed | Check logs, re-dispatch or fix |
| `killed` | Terminated | Was this intentional? |

### The question file protocol

When a worker hits ambiguity, it writes a structured question to `$DISPATCH_ROOT/questions/<worker-id>.md`:

```markdown
---
worker_id: w-a1b2-fix-auth
task_summary: Fix login race condition
timestamp: 2026-04-27T14:32:00Z
---

# What I tried
Implemented a lock around the session check-and-write.

# Where I'm stuck
There are two lock implementations: src/auth/locks.py and src/auth/redis_locks.py.
The brief says "use the existing session lock mechanism" but doesn't specify which.

# My question
Should I use the file-based lock (locks.py) or the Redis-based lock (redis_locks.py)?

# What would unblock me
A yes/no: "use redis_locks.py" or "use locks.py"
```

### Responding to questions

```bash
python cli.py answer w-a1b2-fix-auth --answer-file /tmp/answer.md
```

The answer is incorporated and the worker is re-dispatched.

### Stall detection

If a worker produces no output for its `stall_threshold_seconds` (configured per-executor in the matrix), it is flagged. Auto-poll surfaces stalls within ~90 seconds.

For a stalled worker:
1. Check logs: `python cli.py status <worker-id>` (look at `log_path`)
2. If recoverable, let it continue
3. If stuck, kill and re-dispatch: `python cli.py kill <worker-id>`

### Dispatch CLI exit codes

| Code | Token | Meaning |
|------|-------|---------|
| 0 | Success | Worker spawned |
| 3 | BUDGET_EXHAUSTED | Remaining budget too low |
| 4 | DEPTH_EXCEEDED | Nesting limit reached |
| 5 | PERMISSION_DENIED | Executor pair not allowed |
| 6 | DEADLINE_EXCEEDED | Would outlast deadline |

## 6. Surfacing Progress via Auto-Poll

### How it works

1. The `auto_poll.sh` hook runs on SessionStart and UserPromptSubmit
2. It counts active workers for this session
3. If workers are active and no polling loop is running, it emits a system reminder: "start `/loop 90s /dispatch-poll`"
4. Each poll tick checks for completions and questions
5. When all workers finish, the loop auto-terminates

### Manual polling

If auto-poll isn't configured, check manually:

```bash
python cli.py list --active       # Active workers
python cli.py completions         # Recent completions
python cli.py questions           # Pending questions
```

## 7. Worked Examples

### Example 1: Code review worker with custom voice

```markdown
---
title: Security-focused code review
executor: opus
includes:
  - branch-safety
---

# Your Role

You are a senior security engineer. Review for: injection, auth bypass,
data exposure, SSRF. Ignore style issues.

# Task

Review the diff between main and feature/payment-api.
Run: git diff main...feature/payment-api

Report findings as CRITICAL / HIGH / LOW with file:line references.

# Constraints

- Read-only: do not modify any files
- Focus on security, not style
- Complete review in one pass
```

**Expected output:** Worker reviews the diff, produces a structured security report, exits with `Status: DONE`.

### Example 2: Parallel batch via nested dispatch

```markdown
---
title: Update copyright headers across codebase
executor: sonnet
nested_dispatch:
  max_depth: 1
  allowed_executors: [haiku]
---

# Task

Update the copyright year from 2025 to 2026 in all source files.

## Approach

1. List all files with `Copyright 2025` headers
2. For each batch of 10 files, dispatch a haiku sub-worker with a brief
   specifying exactly which files to update
3. Verify all sub-workers complete successfully
4. Run a final grep to confirm no 2025 headers remain

## Constraints

- Only modify the copyright line (first 5 lines of each file)
- Do not change file formatting or encoding
- Sub-workers should use haiku (this is mechanical find-replace)
```

**Expected output:** Sonnet orchestrates, dispatching N haiku workers. Each haiku worker updates ~10 files. Sonnet verifies completion.

### Example 3: Long-context summarization via Kimi

```markdown
---
title: Summarize architecture docs
executor: kimi
includes:
  - branch-safety
---

# Task

Read all markdown files in docs/architecture/ (approximately 80K tokens total).
Produce a single summary document at docs/ARCHITECTURE_SUMMARY.md covering:

1. System components and their responsibilities
2. Data flow between components
3. Key design decisions and their rationale
4. Known limitations and technical debt

## Constraints

- Output should be under 2000 words
- Use the same heading structure as the source docs
- Link back to specific source files for details
```

**Expected output:** Kimi reads all architecture docs (within its 256K window), produces a concise summary. Routed to Kimi specifically because of the large input context.

### Example 4: Mid-flight orchestrator handoff

```markdown
---
title: Continue API implementation from handoff
executor: opus
includes:
  - dispatch-protocol
  - branch-safety
---

# Task

A previous session started the REST API implementation. The handoff
document is at docs/handoff_api_implementation.md. Read it, understand
the current state, and continue from where it left off.

## Context

The handoff contains:
- What was completed (user CRUD endpoints)
- What remains (auth middleware, rate limiting, error handling)
- Design decisions made
- Open questions that need operator input

## Approach

1. Read the handoff document
2. Verify the completed work matches the handoff description
3. Continue implementation from the next uncompleted item
4. If you hit a decision point not covered by the handoff, write a
   question file

## Constraints

- Follow the patterns established by the completed endpoints
- Do not redesign what's already built
```

**Expected output:** Opus reads the handoff, picks up where the previous session left off, and continues implementation. If it encounters ambiguity not covered by the handoff, it surfaces a question via the question file protocol.
