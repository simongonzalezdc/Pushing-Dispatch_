The following skills provide specialized instructions for specific tasks.
Use the read tool to load a skill's file when the task matches its description.
When a skill file references a relative path, resolve it against the skill directory (parent of SKILL.md / dirname of the path) and use that absolute path in tool commands.

<available_skills>
  <skill>
    <name>brainstorm</name>
    <description>Use at the start of any &quot;let&apos;s build / design / figure out X&quot; task — turns loose thinking into a numbered spec before any code is written.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/brainstorm/SKILL.md</location>
  </skill>
  <skill>
    <name>brainstorming</name>
    <description>You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/brainstorming/SKILL.md</location>
  </skill>
  <skill>
    <name>claim-audit</name>
    <description>Run a claim-vs-evidence audit — prove that things claimed &quot;done / fixed / merged / live&quot; are actually reachable on the execution path, with runtime evidence. Use before declaring a campaign done, when reviewing delegated/agent work, auditing a &quot;supposedly live&quot; feature, or whenever a status says FIXED but you have not seen it run. Model-agnostic (works on any model; this was Claude Fable 5&apos;s signature capability, distilled).</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/claim-audit/SKILL.md</location>
  </skill>
  <skill>
    <name>codebase-design</name>
    <description>Shared vocabulary for designing deep modules. Use when the user wants to design or improve a module&apos;s interface, find deepening opportunities, decide where a seam goes, make code more testable or AI-navigable, or when another skill needs the deep-module vocabulary.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/codebase-design/SKILL.md</location>
  </skill>
  <skill>
    <name>design-an-interface</name>
    <description>Generate multiple radically different interface designs for a module using parallel sub-agents. Use when user wants to design an API, explore interface options, compare module shapes, or mentions &quot;design it twice&quot;.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/design-an-interface/SKILL.md</location>
  </skill>
  <skill>
    <name>diagnosing-bugs</name>
    <description>Diagnosis loop for hard bugs and performance regressions. Use when the user says &quot;diagnose&quot;/&quot;debug this&quot;, or reports something broken/throwing/failing/slow.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/diagnosing-bugs/SKILL.md</location>
  </skill>
  <skill>
    <name>dispatching-parallel-agents</name>
    <description>Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/dispatching-parallel-agents/SKILL.md</location>
  </skill>
  <skill>
    <name>domain-modeling</name>
    <description>Build and sharpen a project&apos;s domain model. Use when the user wants to pin down domain terminology or a ubiquitous language, record an architectural decision, or when another skill needs to maintain the domain model.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/domain-modeling/SKILL.md</location>
  </skill>
  <skill>
    <name>executing-plans</name>
    <description>Use when you have a written implementation plan to execute in a separate session with review checkpoints</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/executing-plans/SKILL.md</location>
  </skill>
  <skill>
    <name>finishing-a-development-branch</name>
    <description>Use when implementation is complete, all tests pass, and you need to decide how to integrate the work</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/finishing-a-development-branch/SKILL.md</location>
  </skill>
  <skill>
    <name>handoff-doc</name>
    <description>Write a worker/agent handoff that needs zero re-explanation — the 10-field contract that let Fable hand a live campaign to Codex cold. Use when delegating non-trivial work to another agent/session, writing an overnight brief, or preserving a task across a context limit. Pairs with safe-delegate.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/handoff-doc/SKILL.md</location>
  </skill>
  <skill>
    <name>karpathy-guidelines</name>
    <description>Behavioral guidelines to reduce common LLM coding mistakes. Use when writing, reviewing, or refactoring code to avoid overcomplication, make surgical changes, surface assumptions, and define verifiable success criteria.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/karpathy-guidelines/SKILL.md</location>
  </skill>
  <skill>
    <name>morning</name>
    <description>Use at session start to compile scoped approved knowledge and a current operational dashboard.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/morning/SKILL.md</location>
  </skill>
  <skill>
    <name>night</name>
    <description>Use at session end to prepare governed memory candidates and a clean next-session review.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/night/SKILL.md</location>
  </skill>
  <skill>
    <name>ornith-local-agent</name>
    <description>Run multi-step local coding/ops jobs on NUCBox Ornith (self-scaffolding) via Unsloth OpenAI proxy or Pushing Dispatch executor unsloth-nucbox. Use when Simon asks for Ornith agent work, local nucbox coding loops, unsloth-ops health, Signal measure fix, media-import debug, or Dispatch local leaf tasks with tools + acceptance.
</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/ornith-local-agent/SKILL.md</location>
  </skill>
  <skill>
    <name>prototype</name>
    <description>Build a throwaway prototype to answer a design question. Use when the user wants to sanity-check whether a state model or logic feels right, or explore what a UI should look like.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/prototype/SKILL.md</location>
  </skill>
  <skill>
    <name>qa</name>
    <description>Interactive QA session where user reports bugs or issues conversationally, and the agent files GitHub issues. Explores the codebase in the background for context and domain language. Use when user wants to report bugs, do QA, file issues conversationally, or mentions &quot;QA session&quot;.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/qa/SKILL.md</location>
  </skill>
  <skill>
    <name>receiving-code-review</name>
    <description>Use when receiving code review feedback, before implementing suggestions, especially if feedback seems unclear or technically questionable - requires technical rigor and verification, not performative agreement or blind implementation</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/receiving-code-review/SKILL.md</location>
  </skill>
  <skill>
    <name>request-refactor-plan</name>
    <description>Create a detailed refactor plan with tiny commits via user interview, then file it as a GitHub issue. Use when user wants to plan a refactor, create a refactoring RFC, or break a refactor into safe incremental steps.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/request-refactor-plan/SKILL.md</location>
  </skill>
  <skill>
    <name>requesting-code-review</name>
    <description>Use when completing tasks, implementing major features, or before merging to verify work meets requirements</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/requesting-code-review/SKILL.md</location>
  </skill>
  <skill>
    <name>research</name>
    <description>Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated to a background agent.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/research/SKILL.md</location>
  </skill>
  <skill>
    <name>resolving-merge-conflicts</name>
    <description>Use when you need to resolve an in-progress git merge/rebase conflict.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/resolving-merge-conflicts/SKILL.md</location>
  </skill>
  <skill>
    <name>safe-delegate</name>
    <description>Delegate work to worker/sub-agents safely and model-agnostically — leverage-triage (DO/HANDOFF/SKIP), worker model caps (never premium), env-scrub on headless dispatch, verify-before-accept (merge-base + tests). Use whenever handing a task to a sub-agent, a headless `claude -p`, or a pushing-dispatch worker. Operationalizes the Fable-ops routing without Fable.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/safe-delegate/SKILL.md</location>
  </skill>
  <skill>
    <name>scientific-rigor</name>
    <description>Enforces strict empirical verification, falsification, and scientific rigor for all software engineering tasks. Use when writing, debugging, or reviewing code to eliminate assumptions and ensure robust, mathematically sound implementations.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/scientific-rigor/SKILL.md</location>
  </skill>
  <skill>
    <name>subagent-driven-development</name>
    <description>Use when executing implementation plans with independent tasks in the current session</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/subagent-driven-development/SKILL.md</location>
  </skill>
  <skill>
    <name>systematic-debugging</name>
    <description>Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/systematic-debugging/SKILL.md</location>
  </skill>
  <skill>
    <name>tdd</name>
    <description>Test-driven development. Use when the user wants to build features or fix bugs test-first, mentions &quot;red-green-refactor&quot;, or wants integration tests.</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/tdd/SKILL.md</location>
  </skill>
  <skill>
    <name>test-driven-development</name>
    <description>Use when implementing any feature or bugfix, before writing implementation code</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/test-driven-development/SKILL.md</location>
  </skill>
  <skill>
    <name>using-git-worktrees</name>
    <description>Use when starting feature work that needs isolation from current workspace or before executing implementation plans - ensures an isolated workspace exists via native tools or git worktree fallback</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/using-git-worktrees/SKILL.md</location>
  </skill>
  <skill>
    <name>using-superpowers</name>
    <description>Use when starting any conversation - establishes how to find and use skills, requiring skill invocation before ANY response including clarifying questions</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/using-superpowers/SKILL.md</location>
  </skill>
  <skill>
    <name>verification-before-completion</name>
    <description>Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires running verification commands and confirming output before making any success claims; evidence before assertions always</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/verification-before-completion/SKILL.md</location>
  </skill>
  <skill>
    <name>writing-plans</name>
    <description>Use when you have a spec or requirements for a multi-step task, before touching code</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/writing-plans/SKILL.md</location>
  </skill>
  <skill>
    <name>writing-skills</name>
    <description>Use when creating new skills, editing existing skills, or verifying skills work before deployment</description>
    <location>/Users/simongonzalezdecruz/.local/share/pushing-dispatch/repo/ops/unsloth-nucbox/pi-agent/skills/writing-skills/SKILL.md</location>
  </skill>
</available_skills>
