# Contributing to ai-dispatch

## Getting Started

1. Fork the repo
2. Clone your fork
3. Copy `dispatch_matrix.toml.example` to `dispatch_matrix.toml`
4. Run `bash bin/check-prereqs.sh` to verify your environment
5. Make your changes on a feature branch
6. Run `bash bin/smoke-test.sh` to verify nothing is broken
7. Submit a PR

## Code Style

### Python

- Python 3.11+ (no external dependencies beyond stdlib)
- Use `tomllib` (stdlib) for TOML parsing
- Type hints where they add clarity (not required everywhere)
- No docstrings on obvious functions; add them on non-obvious ones

### Shell

- `set -euo pipefail` at the top of every script
- Quote all variable expansions
- Use `$()` not backticks
- Keep wrappers under 30 lines; shared logic goes in `_exec.sh`

### Commits

Follow Conventional Commits:
- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation only
- `refactor:` code change that neither fixes nor adds
- `test:` adding or updating tests
- `chore:` maintenance (CI, tooling, etc.)

One logical change per commit. Keep the subject under 72 characters.

## What to Contribute

### Good first contributions

- Adding a new provider wrapper (see docs/CUSTOMIZATION.md)
- Improving documentation
- Adding test coverage for dispatch_lib modules
- Reporting bugs with reproduction steps

### Architecture changes

For changes to the dispatch protocol, matrix schema, or nested dispatch behavior, open an issue first to discuss the design. These are load-bearing components where backwards compatibility matters.

## Testing

No formal test suite yet (good first contribution!). For now:

- `bash bin/check-prereqs.sh` -- environment OK
- `bash bin/smoke-test.sh` -- full pipeline works
- `python cli.py validate-matrix dispatch_matrix.toml` -- matrix is valid
- `python skeleton_lint.py` -- CLAUDE.md sizes are within budget

## PR Conventions

- Keep PRs focused (one feature or fix per PR)
- Include a brief description of what changed and why
- If adding a provider, include the provider's API docs link
- If changing the matrix schema, update `matrix_validator.py` and the `.example` file

## Code of Conduct

Be respectful, constructive, and focused on the work. This is a technical project; keep discussions technical.
