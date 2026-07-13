# Customization Guide

`dispatch_matrix.toml` is the only active executor catalog. Keep the installed
matrix and `dispatch_matrix.toml.example` in parity.

## Add or Replace an Executor

1. Create a thin native-harness wrapper in `bin/wrappers/`.
2. Add one `[executors.<name>]` entry with provider, exact model id, supported
   modes, context window, turns, and truthful capabilities.
3. Add it to the appropriate ordered `auto_route` candidate list.
4. Add only the nested-dispatch permissions that are actually required.
5. Add matrix-shape, routing, and wrapper tests.
6. Run the full green gate, including a live probe through the real harness.

Do not keep a retired wrapper callable “just in case.” Version control is the
archive; the working tree should expose only current operational lanes.

## Capabilities

Vision must be explicit:

```toml
capabilities = ["vision"]
```

GLM 5.2 must remain `capabilities = []`. Kilo free, MiniMax M3 through GJC, and
LM Studio are also non-vision in the current matrix. Search capability is not
assumed; the universal fallback is the global DuckDuckGo `ddg` MCP.

## Kilo Free-Only Rule

The stable executor is:

```toml
[executors.kilo-free-auto]
provider = "kilo-cli"
model_id = "kilo/kilo-auto/free"
```

Named monthly free models may be added only after live verification that they
are currently free. Never configure a paid fallback.

## Nested Permissions

Self-dispatch and leaf-parent dispatch are hard-denied. Use exact keys:

```toml
[nested_dispatch.permissions]
"codex-sol.codex-terra" = true
"codex-terra.codex-luna" = true
```

Missing pairs are denied. Avoid wildcard permissions.

## Context and Thinking

Keep `context_window` and reasoning/thinking settings in the matrix rather than
hard-coding them in orchestration docs. When a provider changes an identifier
or limit, update matrix, wrapper, tests, and provider docs in the same change.

## Verification

```bash
python3 -m pytest -q
pushing-dispatch validate-matrix dispatch_matrix.toml
pushing-dispatch doctor --probe
```

Do not call a customization complete until the real wrapper succeeds.
