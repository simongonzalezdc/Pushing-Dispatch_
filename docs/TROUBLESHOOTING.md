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
Vision-capable lanes are Codex Luna/Terra/Sol, Grok Build, Kimi K3, and AGY Gemini.

## Search Fails

Use the globally configured DuckDuckGo MCP server named `ddg`. This is the
required fallback when native search is absent or unreliable. Never invent results.

## Wrong Harness

- Kimi K3 subscription: official Kimi CLI only (`kimi-k3-cli`, technical alias `kimi-code/k3`).
- Kimi K3 on Ollama Cloud: `kimi-k3-ollama` only, and only after the live catalog exposes `kimi-k3`; this is the future Hermes-native route.
- Gemini: AGY only.
- MiniMax M3: GJC backup path only.
- Kilo: native CLI, free models only; default `kilo/kilo-auto/free`.

## Local Qwen Context or Residency Failure

The Qwen 3.5 35B general, Qwen 3.5 27B review, and Qwen 3.6 35B coding
workcells use 32,768-token serving slots. The review and coding lanes reserve
22,000 tokens for measured Pi/tool-loop growth and reject oversized requests
before changing NUC residency. Review admits only the read tool. Coding admits
read, edit, and bounded shell; its systemd drop-in caps inference and batch
threads at 8. A larger model-card context is not a hardware-safe serving
budget; context changes still require memory, thermal, identity, and
restoration evidence.

The serving context is not the generation allowance. The controller retains the
full per-lane slot while bounding generated output per role (2,048 general,
1,536 review, and 1,024 coding tokens).

Before activation, verify Tctl is at most 85°C and
`/sys/class/drm/card1/device/power_dpm_force_performance_level` is `low`.
The runtime guard samples Tctl every two seconds and stops the workcell at
90°C. Do not raise either threshold to make a canary pass.

After every on-demand request, verify that the resident
`unsloth-agent-qwen27.service` and its watchdog timer are active, Studio and
the Studio proxy are inactive and disabled, the GPU performance level remains
`low`, the shared mutex is inactive, and every on-demand service is both
inactive **and disabled**. An inactive-but-enabled on-demand unit is a failed
restoration because systemd can start it beside the resident model at boot.
The Dell `ollama-xps-gpu` lane must fail closed when resident NUC validation is
unavailable or returns anything other than exact `YES`.
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
