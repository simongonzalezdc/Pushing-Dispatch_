# Dispatch lane: `unsloth-nucbox` (Ornith)

Sticky **m3-class** local executor on NUCBox Ornith via Unsloth Studio OpenAI proxy.

## Identity

| | |
|--|--|
| Executor | `unsloth-nucbox` |
| Model | `SC117/Ornith-1.0-35B-MTP-APEX-GGUF` |
| Base URL | `http://100.113.174.74:8890/v1` |
| Harness | Pi (`--thinking off` by default; tools read/bash/edit/write/grep/find/ls) |
| Seats | **leaf only** (blocked as breakout top) |
| Modes | `task` |

## Policy

Full fleet rules: **`launchpad/docs/agents/ORNITH-GUIDELINES.md`**.

- Admit only bounded · localized · reversible · verifying work  
- Never architect / critic / security / vision / web as sole judge  
- Sampling forced at proxy (`UNSLOTH_ORNITH_SAMPLING=force`)  
- Do not dual-load another 27B/35B agent port (`:8892` retired)

## Ops

```bash
pushing-dispatch doctor | rg unsloth-nucbox    # expect available
ssh nucbox '~/unsloth-ops/bin/ornith-workhorse-verify.sh'

pushing-dispatch route --mode task --task "local coding: <brief>"
pushing-dispatch task start --executor unsloth-nucbox --cwd "$PWD" --task "<brief + Status: DONE>"
```

Auto-route uses `local_coding_candidates` when the brief matches local-coding keywords and token ceilings in `dispatch_matrix.toml`.

## Files

| Path | Role |
|------|------|
| `bin/wrappers/unsloth-nucbox.sh` | wrapper |
| `ops/unsloth-nucbox/pi-agent/models.json` | Pi provider registry |
| `dispatch_matrix.toml` `[executors.unsloth-nucbox]` | matrix |

## Related (retired while Ornith sticky)

On-demand dual-load workcells (`qwen35-35b-general`, `qwen35-27b-review`, `qwen36-35b-coding`) that activate via `:8892` remain UNAVAILABLE by design.

## Skills (progressive disclosure)

**Goal:** same coding skills as cloud workers (Matt Pocock deep-modules suite, wayfinder/to-spec/to-tickets, TDD/debug/review, `ornith-local-agent`) — **without** stuffing full skill bodies into every turn.

### How it works

1. Curated skill dirs live as **host-local symlinks** under `pi-agent/skills/` (not committed; absolute paths). Includes **obra/superpowers** (14) + Matt Pocock deep-modules + wayfinder/to-spec/to-tickets + `ornith-local-agent`.
2. At worker start, the wrapper injects a **catalog only** (name + description + absolute path) into the system prompt (~3.5k tokens) via `SKILLS-PROMPT-BLOCK.md`.
3. Ornith uses the `read` tool on a skill path when the task matches a description.
4. Pi **native** `--skills` discovery stays **off** for this lane: enabling it also loads global Pi package skills and blows past the 32k context window.

Obra pack source of truth: `~/.agents/skills/.vendors/obra-superpowers/skills/` (clone of `github.com/obra/superpowers`).

### Files

| Path | Role |
|------|------|
| `pi-agent/skills/` | Curated skill catalog (symlinks) |
| `SKILLS-INDEX.md` | Human-readable table |
| `SKILLS-PROMPT-BLOCK.md` | Injected progressive catalog (generated) |
| `SYSTEM.md` | Leaf operating contract |

### Refresh catalog after adding skills

```bash
# add symlink under pi-agent/skills/, then regenerate:
node --input-type=module <<'JS'
import { loadSkills, formatSkillsForPrompt } from "@earendil-works/pi-coding-agent/dist/core/skills.js";
import { writeFileSync } from "fs";
const agentDir = "ops/unsloth-nucbox/pi-agent"; // from repo root
const r = loadSkills({ agentDir: process.cwd()+"/"+agentDir, cwd: process.cwd(), skillPaths: [], includeDefaults: true });
writeFileSync("ops/unsloth-nucbox/SKILLS-PROMPT-BLOCK.md", formatSkillsForPrompt(r.skills).trim()+"\n");
console.log(r.skills.length);
JS
```

### Env knobs

| Env | Default | Meaning |
|-----|---------|---------|
| `PI_LOCAL_SKILLS_MODE` | `off` | Keep off; catalog is injected by wrapper |
| `PI_LOCAL_CONTEXT_FILES` | `on` | Load project `AGENTS.md` / `CLAUDE.md` |
| `PI_LOCAL_TOOLS` | read,bash,edit,write,grep,find,ls | Same coding tools as other Pi leaves |

