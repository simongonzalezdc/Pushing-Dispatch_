# Delivery Checklist

What is covered vs deferred in this release.

## Covered

- [x] Fresh git repo at confirmed destination
- [x] `README.md` (human marquee with architecture overview)
- [x] `CLAUDE.md` (LLM skeleton for Claude Code sessions)
- [x] `AGENTS.md` (LLM skeleton for OpenAI Codex / generic agents)
- [x] `GEMINI.md` (LLM skeleton for Gemini CLI sessions)
- [x] `INSTALL.md` (comprehensive installation walkthrough)
- [x] `docs/ORCHESTRATING.md` (complete orchestrator guide with 4 worked examples)
- [x] `docs/CUSTOMIZATION.md` (per-user customization recipes)
- [x] `docs/PROVIDERS.md` (per-provider configuration)
- [x] `docs/TROUBLESHOOTING.md` (common gotchas and debugging)
- [x] `CONTRIBUTING.md` (how to contribute)
- [x] `LICENSE` (MIT)
- [x] `examples/` with 3 worked orchestrator briefs
- [x] `bin/check-prereqs.sh` (environment verification)
- [x] `bin/smoke-test.sh` (first-run pipeline validation)
- [x] `dispatch_packs/` with baseline + 5 detail packs
- [x] `dispatch_matrix.toml.example` (reference matrix)
- [x] `bin/wrappers/` with 5 provider wrappers (sonnet, opus, haiku, moonshot, deepseek)
- [x] `.github/ISSUE_TEMPLATE/` with 3 seeded first issues
- [x] Core Python framework (cli.py, breakout.py, dispatch_lib/)
- [x] Shared execution library (_exec.sh)
- [x] Auto-poll hook and dispatch-poll command
- [x] Skeleton lint tool
- [x] This checklist

## Deferred

- [ ] Formal test suite (test_*.py files) -- seeded as a good first issue
- [ ] `pyproject.toml` / pip-installable package
- [ ] `dispatch init` command (seeded as issue template)
- [ ] Budget dashboard with rich/textual (seeded as issue template)
- [ ] OpenAI-compat provider adapter (seeded as issue template)
- [ ] Ollama local model wrapper (commented in matrix example)
- [ ] Architecture diagrams (ASCII/Mermaid) in README
- [ ] MiniMax wrapper (available but omitted due to hallucination track record)
- [ ] Gemini wrapper (consult-only mode, low priority)
- [ ] Observer/telemetry module (feedback loop for routing improvement)
- [ ] Daily maintenance orchestrator (lint + health checks)
- [ ] `dispatch_pricing.toml` (real pricing data, ships as skeleton)
- [ ] Status pipe for live streaming progress
- [ ] Cross-platform CI/CD pipeline
