# Troubleshooting

Start with the installed command so diagnosis uses the same checkout agents do:

```bash
command -v pushing-dispatch
pushing-dispatch validate-matrix dispatch_matrix.toml
pushing-dispatch doctor
```

## A Lane Is Missing or Unavailable

`pushing-dispatch doctor` distinguishes a missing harness, authentication
failure, cooldown, and failed live probe. Fix the reported harness or login; do
not restore a retired executor to make the table look green.

The only valid executor names are those in `dispatch_matrix.toml`. Use
`pushing-dispatch route --mode task --task "<brief>" --json` to inspect the
availability-aware choice.

## Worker Starts but Produces No Output

```bash
pushing-dispatch status <worker-id>
pushing-dispatch list --active
bash bin/wrappers/codex-terra.sh --task-file brief.md --cwd "$TMPDIR" --dry-run
```

Brief `includes:` directives must start at column zero and reference a pack
registered in `dispatch_packs/_registry.toml`.

## Wrong Model Appears in Claude Code

On this machine Claude Code is the GLM 5.2 harness:

```bash
command -v claude
claude --version
claude-glm52 --version
```

Do not select Opus/Sonnet/Haiku as a workaround. Check the `claude` symlink and
the Z.AI credential used by `bin/claude-glm52`.

## Visual Task Routed to GLM

GLM has no vision. Make the visual requirement explicit and rerun `route`.
Vision-capable lanes are Codex Luna/Terra/Sol, Grok Build, Kimi K2.7, and AGY Gemini.

## Search Fails

Use the globally configured DuckDuckGo MCP server named `ddg`. This is the
required fallback when native search is absent or unreliable. Never invent results.

## Wrong Harness

- Kimi K2.7: native `kimi-cli` only.
- Gemini: AGY only.
- MiniMax M3: GJC backup path only.
- Kilo: native CLI, free models only; default `kilo/kilo-auto/free`.
- `grok-build`: official xAI `grok` CLI only; run `grok models` to verify login and the `grok-4.5` catalog entry.

If a legacy Moonshot, Gemini CLI, direct MiniMax, or paid Kilo path appears,
stop it and fix the active matrix/wrapper resolution.

## Nested Dispatch Is Denied

Self-dispatch and leaf-parent dispatch are always denied. Other parent/child
pairs must be explicitly present in `[nested_dispatch.permissions]`. Never add
a broad wildcard.

## Final Green Gate

```bash
python3 -m pytest -q
pushing-dispatch validate-matrix dispatch_matrix.toml
pushing-dispatch doctor --probe
```

Green means tests pass, the installed command resolves to the canonical
checkout, and all eleven active executor wrappers pass live probes.
