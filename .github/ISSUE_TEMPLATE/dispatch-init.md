---
name: "Add dispatch init command"
about: "Scaffold a project config with guided setup"
title: "feat: Add dispatch init command for guided project setup"
labels: ["enhancement", "good first issue"]
assignees: []
---

## Summary

Currently users must manually create the matrix TOML and pack registry. A guided init command (like `npm init`) would lower the entry barrier.

## Scope

- One new CLI subcommand: `python cli.py init`
- Interactive prompts for: which providers to enable, API key verification, default executor preference
- Generates `dispatch_matrix.toml` from the user's answers
- Creates `dispatch_packs/` directory with baseline if not present
- Optionally sets up hooks in Claude Code settings

## Acceptance criteria

- [ ] `python cli.py init` produces a valid `dispatch_matrix.toml`
- [ ] Generated matrix passes `python cli.py validate-matrix`
- [ ] Smoke test passes against the generated config
- [ ] Works on macOS and Linux
