# ZCode — canonical GLM harness

**Owning ops doc:** `~/.agents/docs/ZCODE-GLM.md`  
Do not fork the procedure. This file is the Dispatch-repo face.

## Rule

Call GLM through **ZCode** (`zcode -p` / `zcode --prompt`). That is Z.AI’s own harness.

Do not teach agents to call GLM through Claude Code (`claude`, `claude-glm52`).

```bash
zcode -p "Inspect-only: …" --mode plan --cwd "$PWD"
zcode --prompt "…" --cwd "$PWD" --mode plan
```

Live-tested 2026-08-14: `zcode -p "…ZCODE PRINT MODE OK"` returned exactly those four words, exit 0.  
`-p` is `--prompt <text>`. Do not pass `--max-turns` (help lists it; 0.16.3 parser rejects it).  
`--mode plan` does not write files (rlenvs audit printed HOLD and asked for approval). Tee stdout or resume `--mode yolo` for one report path.  
CLI needs `~/.zcode/cli/config.json` `model.main = "zai/glm-5.3"` plus `provider.zai.options.baseURL`. See `~/.agents/docs/ZCODE-GLM.md`.

Shim: `bin/zcode` → `~/.local/bin/zcode` via `bin/install-global-routing.sh`.  
Bundled fallback: `node /Applications/ZCode.app/Contents/Resources/glm/zcode.cjs`.

Model pin: **glm-5.3**.

## Dispatch honesty

Executor `zai-glm` still uses `bin/wrappers/zai.sh` → Claude Code + Z.AI Anthropic-compatible endpoint. That is **legacy**. Agents invoking GLM themselves use ZCode. Rewiring `zai.sh` onto ZCode is a separate, tested change — do not claim it is done from this doc.

## See also

`GLOBAL_AGENT_ROUTING.md`, `docs/PROVIDERS.md`, `AGENTS.md`.
