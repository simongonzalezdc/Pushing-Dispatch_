# Brief Format Reference

## Structure

A brief is a markdown file with optional YAML frontmatter. It is the contract between the orchestrator and the worker.

```markdown
---
title: Short descriptive title
executor: sonnet           # Optional: override auto-routing
workspace: my-project      # Optional: project context
includes:
  - dispatch-protocol
  - branch-safety
nested_dispatch:           # Optional: enable nested dispatch
  max_depth: 2
  allowed_executors: [haiku, kimi]
---

# Task description

What the worker should do. Be specific. Include file paths,
expected outcomes, and constraints.

## Context

Background information the worker needs. Keep it minimal.
Use includes: for shared context rather than repeating it.

## Constraints

- Only modify the files specified
- Follow existing patterns
- Do not refactor surrounding code
```

## Fields

### Frontmatter (YAML)

| Field | Required | Description |
|-------|----------|-------------|
| `title` | No | Human-readable title |
| `executor` | No | Override auto-routing (e.g. "opus", "kimi") |
| `workspace` | No | Project/workspace name for context |
| `includes` | No | List of pack names to resolve and prepend |
| `nested_dispatch` | No | Enable nested dispatch with constraints |
| `read_only` | No | If true, worker cannot modify files |

### Body (Markdown)

The body should contain at minimum a clear task description. Recommended sections:

- **Task**: What to do
- **Context**: Background (if not covered by includes)
- **Constraints**: What NOT to do
- **Acceptance criteria**: How to know it's done

## includes: Directive

The `includes:` field references named packs from the pack registry (`dispatch_packs/_registry.toml`). The wrapper resolves pack names to files and prepends them to the brief.

**Important:** `includes:` is only recognized at column 0 (start of line). Indented `includes:` in the task body is treated as regular text.

## Assembly Order

The wrapper assembles the final prompt in this order:
1. `_baseline.md` (always prepended)
2. Resolved packs (in declaration order)
3. Brief body (with `includes:` line removed)
