# Liam/Hermes Integration

Hermes is Liam's resident orchestrator. Pushing Dispatch is its model-selection and external-worker front door.

## Boundary

- Hermes's primary conversation model is Z.AI GLM 5.3 (native HTTP provider). That is the in-app chat path, not the CLI.
- **CLI / headless GLM is ZCode** (`zcode -p`). See `docs/ZCODE.md`. Do not teach Hermes operators to call GLM through Claude Code.
- Hermes-native child agents inherit GLM 5.3 and are appropriate for tightly coupled, in-session decomposition.
- External delegated, background, parallel, consultation, coding, research, and specialist workers launch through the `hermes-dispatch` adapter.
- CLI-backed executors are not duplicated as Hermes HTTP providers. Dispatch owns their authentication, capability checks, availability, and launch behavior.

This prevents provider drift and avoids falsely representing ChatGPT subscription Codex, Kimi CLI, the official Grok CLI, AGY, GJC, or Kilo CLI as direct Hermes API providers. Ollama Cloud is different: it is a native Hermes provider, and Kimi K3 may become Hermes' main model there only after the live catalog and an authenticated completion both pass.

## Managed Hermes configuration

`bin/install-hermes-routing.sh` installs the adapter and skill, backs up the live Hermes configuration, and enforces the native provider boundary below. The native provider catalog contains only providers Hermes invokes directly.

```yaml
model:
  provider: zai
  default: glm-5.3
  base_url: https://api.z.ai/api/coding/paas/v4
  api_mode: chat_completions

providers:
  ollama-local:
    request_timeout_seconds: 300
    stale_timeout_seconds: 900
  zai:
    api_key: ''
    api_mode: chat_completions
    base_url: https://api.z.ai/api/coding/paas/v4
    model: glm-5.3
    reasoning_effort: high

fallback_providers: []
custom_providers: []

delegation:
  provider: zai
  model: glm-5.3
  orchestrator_enabled: true
```

The empty fallback lists are intentional. Retired models must not silently reactivate when GLM is unavailable.

## Dispatch behavior

Before external delegation, use the Hermes-owned adapter:

```bash
hermes-dispatch route --mode task --task "<brief>"
hermes-dispatch start --mode task --task "<brief>" --cwd "$PWD"
hermes-dispatch status <worker-id>
```

Use `breakout` or `consult` when that is the actual mode. The committed matrix remains authoritative.

## Credential bridge

The global Dispatch and ZCode/Claude launchers use one non-executing reader for the Z.AI aliases `Z_AI_API_KEY`, `ZAI_API_KEY`, or `GLM_API_KEY` from Liam's trusted `$HOME/.hermes/.env`. The reader rejects symlinks, non-owner files, and group/world-readable files. Other Hermes credentials are not imported. CLI/headless GLM is ZCode (`zcode -p`). The legacy `claude-glm52` wrapper still targets Z.AI GLM 5.3 over the Anthropic-compatible endpoint.

## Capability rules

- Do not default visual-QA to GLM/ZCode. Vision-critical work routes to a vision-capable Dispatch lane.
- Kimi subscription work routes externally through `kimi-k3-cli`. Hermes never imports or uses that subscription session.
- When Ollama Cloud exposes K3 and an authenticated completion passes, Hermes may set `provider: ollama-cloud` and `default: kimi-k3`; until then it keeps a working primary model.
- Grok Build routes through the `grok-build` executor and xAI's official CLI; it replaces retired Claude Opus-class hard implementation, architecture, adversarial review, breakout, and consult work. It is not a Hermes HTTP provider.
- Weak or failed search uses DuckDuckGo MCP.
- `pushing-dispatch doctor` reports host-specific availability.
- GPT-5.5, Codex OSS, NUCBox Gemma, direct MiniMax, direct Moonshot/Kimi, legacy Gemini CLI, paid Kilo, and Anthropic subscription models are retired.
