# Setup With Claude Code

A runnable setup walkthrough. Paste the repo URL into a fresh Claude Code session and ask it to read this file. By the end, you will have:

1. The framework installed and smoke-tested.
2. A working `dispatch_matrix.toml` for your providers.
3. Secrets stored properly (Keychain, `pass`, or env).
4. The advisor pattern wired into a project of your choice, with an orchestrator brief and a first dispatched worker.

---

## Instructions for Claude Code (the agent reading this)

You are walking a human through setup. Treat every numbered step as a gate: do the work, verify it, then ask the user to confirm before moving on. Never skip steps. Never assume prior state. If a verification fails, stop and debug with the user before continuing.

Use the user's actual machine, not hypothetical commands. Run real shell commands via Bash. When you need a decision from the user, ask one specific question and wait. Do not infer answers.

At the end, the human should have a working dispatch setup AND a clear mental model of advisor-driven development.

Output style: short paragraphs, one decision per turn, end each turn with a clear next question or action.

---

## Step 1 -- Verify prereqs

Run `bin/check-prereqs.sh` if the repo is already cloned, otherwise check manually:

- `python3 --version` -- need 3.11+
- `bash --version` -- need 4+. **On macOS** the system `/bin/bash` is 3.2; if version is 3.x, instruct the user to `brew install bash` and ensure Homebrew's bash is ahead of `/bin/bash` in `PATH`.
- `git --version` -- any recent
- `claude --version` -- the Anthropic Claude Code CLI must be installed

If any fail, stop and link the user to the install page for the missing tool. Do not proceed until all four pass.

**Gate:** all four prereqs pass on the user's machine.

## Step 2 -- Clone the repo (if not already)

If the user pasted the GitHub URL but is not yet inside the repo, clone it:

```bash
git clone https://github.com/PUSHINGSQUARES/Pushing-Dispatch_.git pushing-dispatch
cd pushing-dispatch
```

If they already cloned it, just `cd` in.

**Gate:** `pwd` shows the repo root, `ls` shows `cli.py`, `README.md`, `dispatch_matrix.toml.example`.

## Step 3 -- Pick providers

Ask the user which providers they have API keys for. Common choices:

- **Anthropic** (Claude Opus, Sonnet, Haiku) -- via `claude` CLI subscription or `ANTHROPIC_API_KEY`.
- **Moonshot / Kimi** -- via `MOONSHOT_API_KEY` (or kimi-cli).
- **DeepSeek** -- via `DEEPSEEK_API_KEY`.

If the user only has Anthropic, that is fine. The framework works with one provider. Recommend at least two for the cost-routing benefit.

**Gate:** user names which providers they want enabled. Note their answer.

## Step 4 -- Generate the matrix

Copy the example matrix and trim to the user's chosen providers:

```bash
cp dispatch_matrix.toml.example dispatch_matrix.toml
```

Open `dispatch_matrix.toml`. For each provider the user did NOT pick in Step 3, comment out or delete its `[[executors]]` block. Verify the remaining model IDs match what the user wants (e.g. `claude-opus-4-7` is current; older IDs like `claude-opus-4-6` should be updated).

Validate the matrix:

```bash
python3 cli.py validate-matrix
```

**Gate:** `validate-matrix` exits 0.

## Step 5 -- Configure secrets

Ask the user how they want to store API keys. Recommend in this order:

1. **macOS Keychain** (most secure on Mac):
   ```bash
   security add-generic-password -s "pushing-dispatch" -a "<provider>_api_key" -w "<key>"
   ```
2. **`pass`** (Linux / cross-platform):
   ```bash
   pass insert pushing-dispatch/<provider>_api_key
   ```
3. **Env vars** (simplest, least secure):
   ```bash
   export MOONSHOT_API_KEY="..."
   ```

Walk them through storing one key, then verify the wrapper can read it:

```bash
bash bin/wrappers/<provider>.sh --check-auth
```

Repeat per provider.

**Gate:** every enabled provider's `--check-auth` returns success.

## Step 6 -- Smoke test

Run the bundled smoke test:

```bash
bash bin/smoke-test.sh
```

This dispatches a sub-$0.01 worker against the user's cheapest enabled provider, checks the worker exits cleanly, and verifies the status file lands where expected.

If the smoke test fails, debug from the log path it prints. Common failures:

- Wrong API endpoint: check `dispatch_matrix.toml` `endpoint` field.
- Missing `claude` CLI: re-run Step 1.
- Auth not wired: re-run Step 5.

**Gate:** smoke test green.

## Step 7 -- Explain the advisor pattern

Once the framework runs, the user needs the mental model. Explain in your own words, using these talking points:

- **Two seats: orchestrator and worker.** The orchestrator is YOU (the advisor model in their main Claude Code session). The worker is a dispatched process running a different model on a focused task.
- **Briefs are the contract.** The orchestrator writes a brief (a markdown file with frontmatter + task body), dispatches it, and the worker reads it as its full context.
- **Judgment stays in the orchestrator seat.** Execution fans out. The orchestrator does NOT do the mechanical work itself.
- **Brief-only context.** Workers do not auto-load the project's CLAUDE.md. They get exactly what the brief includes via `includes:` packs.
- **Three modes:** `breakout` (worktree-isolated multi-step work), `task` (mechanical, no worktree), `consult` (read-only advice).

Show the user [docs/ORCHESTRATING.md](docs/ORCHESTRATING.md) and walk them through the first worked example in [examples/](examples/).

**Gate:** user can explain back the difference between orchestrator and worker, and when to use each dispatch mode.

## Step 8 -- Wire the advisor pattern into a real project

Ask: "Which project do you want to start using advisor-driven dispatch in?"

Have them `cd` to that project. Then:

1. Create a `briefs/` directory in their project (or wherever they want to keep dispatch briefs).
2. Copy `examples/code-review-with-custom-voice.md` into `briefs/` as a starting template.
3. Edit it to describe a real, small task they have right now -- a code review, a refactor, a docs pass. Keep it under 30 minutes of worker time.

Then dispatch it:

```bash
python3 /path/to/pushing-dispatch/cli.py breakout start \
  --executor sonnet \
  --task-file briefs/<their-brief>.md \
  --cwd "$(pwd)"
```

Watch the status file. When the worker exits, review what it produced.

**Gate:** the user has dispatched and reviewed at least one real worker on their own project.

## Step 9 -- Confirm completion

Recap with the user:

- Prereqs verified.
- Matrix configured for their chosen providers.
- Secrets stored.
- Smoke test green.
- Advisor pattern understood.
- First real worker dispatched and reviewed.

Point them at:

- [docs/ORCHESTRATING.md](docs/ORCHESTRATING.md) -- complete orchestrator guide.
- [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md) -- tuning per their workflow.
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) -- when things break.
- [CONTRIBUTING.md](CONTRIBUTING.md) -- if they want to extend.

Tell them: from here, the pattern is to write briefs in your main session, dispatch workers, and never do mechanical work yourself. The judgment stays in one chair.

**Done.**
