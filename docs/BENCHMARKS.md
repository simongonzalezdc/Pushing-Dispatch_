# Roster benchmarks (looked up 2026-08-16)

Third-party figures, directional not gospel. Purpose: route by measured strength
× budget, not vibes. Sources listed at bottom.

| Model (lane) | Key numbers | Routing implication |
|---|---|---|
| GPT-5.6 Sol (codex-sol) | SWE-bench Verified ~96.2 (tops), Terminal-Bench 88.8 | Best raw coder alive — but $20 plan = scarce. Reserve for highest-stakes work. |
| GPT-5.6 Terra (codex-terra) | Terminal-Bench 87.4 | Strong agentic; escalation rung before Sol. |
| GPT-5.6 Luna (codex-luna) | Fast/cheap tier, matches GLM-5.2(max)/Gemini 3.5 Flash class | Good default paid lane; still scarce under $20 plan. |
| Gemini 3.7 Flash (agy-gemini-flash) | Terminal-Bench 85.8 (1.6 behind Terra), ~3x faster, ~2/3 cheaper, AutomationBench 30.4 > Terra 23.6, 1M ctx, vision | Best CHEAP agentic/automation lane — should sit high in consult/long-context/hard fallbacks. |
| Kimi K3 (kimi-k3-*) | Terminal-Bench 88.3 (beats Terra), SWE Marathon 42 (leads), ProgramBench 77.8, front-end Arena #1, 1M ctx | Elite agentic + long-context + front-end on cheap subs. Kyanite (dying) drains first. |
| DeepSeek V4 Pro (deepseek-v4-pro) | SWE-bench Verified 80.6, LiveCodeBench 93.5, Codeforces 3206 (highest ever) | Raw-coding king of the cheap lanes; algo/competitive work goes here. |
| DeepSeek V4 Flash (deepseek-v4-flash) | Strong price-performance | Trivial/standard filler. |
| MiniMax M3 (minimax-m3) | SWE-bench Pro 59.0 (> DS V4 55.4), agentic/MCP edge, video input | Agentic workflows where K3/DS busy. |
| GLM-5.3 (zai-glm) | 743B; leads CyberGym + AutomationBench; 5.2 was top open SWE-Pro 62.1; no verified 5.3 SWE number yet | Default standard-lane workhorse (cheap, strong, no vision). |
| Grok 4.6 (grok-build) | "Comparable to Claude Opus 5" (Reddit/CodingFleet), 500k ctx, vision | Hard-lane anchor — but $30 plan = scarce, so cheap elites (K3/DS-Pro/Gemini 3.7) take what they can do. |
| Qwen3.8-27B (unsloth-nucbox) | Local champion (fleet-measured, beats Ornith on time-per-task) | Bounded/localized/verifying tasks only — never architect/vision. |

## Routing consequences (encoded in dispatch_matrix.toml)
1. Hard/consult: grok stays first-pick anchor, but Kimi K3 (Terminal-Bench 88.3),
   DeepSeek V4 Pro, and Gemini 3.7 Flash now sit AHEAD of the codex ladder as
   cheaper near-peers — the scarce codex/grok budgets last for what only they do.
2. Long-context: kimi (1M) first, Gemini 3.7 Flash (1M, cheap) promoted.
3. Standard: zai-glm first (cheap workhorse), kimi/deepseek next — unchanged.
4. Trivial: local + deepseek-flash + kilo — unchanged.

## Sources
- swebench.com official leaderboards
- morphllm.com / llm-stats.com SWE-bench Verified/Pro trackers
- akash.network — Gemini 3.7 Flash vs GPT-5.6 Terra vs Sonnet 5
- codingfleet.com — Gemini 3.7 Flash vs GPT-5.6 Terra; MiniMax M3 vs DeepSeek V4 Pro
- macaron.im — DeepSeek V4 benchmarks
- minimaxm3.com — M3 vs V4 Pro
- whatllm.org / nxcode.io — Kimi K3
- explainx.ai — GLM-5.3 launch benchmarks
- artificialanalysis.ai — GPT-5.6 lineup positioning
