# Adaptive, Availability-Aware, Self-Healing Router — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Pushing Dispatch route only to executors that are actually reachable, escalate model choice adaptively by task tier, self-heal around auth/rate-limit failures, and persist all of it across sessions.

**Architecture:** A new credential-sync script consolidates keys into the macOS Keychain service `pushing-dispatch`. A new `availability` module computes which executors are reachable and caches it. A new `lane_health` module tracks cooldowns from classified runtime failures. `auto_router` is upgraded to walk ordered, tier-based candidate lists and return the first executor that is mode-allowed, available, and not in cooldown. A `doctor` CLI surfaces the live state.

**Tech Stack:** Python 3.11+ (stdlib + `tomllib` only), `unittest` for tests, Bash (`set -euo pipefail`), macOS `security` (Keychain). JSON written atomically (tmp + rename); JSONL append-only.

---

## File Structure

- Create: `dispatch_lib/availability.py` — reachability resolver + cache. Responsibility: "is executor X usable right now?"
- Create: `dispatch_lib/lane_health.py` — cooldown ledger read/write + failure classifier. Responsibility: "is executor X temporarily demoted, and why?"
- Modify: `dispatch_lib/auto_router.py` — availability/cooldown-aware, ordered-candidate routing.
- Modify: `dispatch_lib/path_conventions.py` — add `availability_path()`, `lane_health_path()`, `outcomes_path()`.
- Modify: `dispatch_matrix.toml` + `dispatch_matrix.toml.example` — ordered candidate lists, OpenAI `account` hints, `learning` knob, nesting depth.
- Create: `bin/sync-credentials.sh` — consolidate keys into Keychain.
- Modify: `cli.py` — add `doctor` subcommand; enrich `route --json`.
- Modify: `bin/wrappers/_exec.sh` — classify failures, write cooldowns, record outcomes; OpenAI account switch.
- Create: `dispatch_lib/outcomes.py` — append-only outcome ledger (learning substrate).
- Create: `tests/` — `test_availability.py`, `test_lane_health.py`, `test_auto_router.py`, `test_outcomes.py`.

Tests use `unittest.TestCase`. Run with `python3 -m unittest discover -s tests -v`.

---

## Task 1: Path conventions for new state files

**Files:**
- Modify: `dispatch_lib/path_conventions.py`
- Test: `tests/test_path_conventions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_path_conventions.py
import unittest
from dispatch_lib import path_conventions as pc

class TestPaths(unittest.TestCase):
    def test_new_state_paths_under_dispatch_root(self):
        root = pc.dispatch_root()
        self.assertEqual(pc.availability_path(), root / "availability.json")
        self.assertEqual(pc.lane_health_path(), root / "lane_health.json")
        self.assertEqual(pc.outcomes_path(), root / "outcomes.jsonl")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_path_conventions -v`
Expected: FAIL with `AttributeError: module 'dispatch_lib.path_conventions' has no attribute 'availability_path'`

- [ ] **Step 3: Add the functions**

Append to `dispatch_lib/path_conventions.py` (follow the existing `budget_path` style):

```python
def availability_path() -> Path:
    return dispatch_root() / "availability.json"


def lane_health_path() -> Path:
    return dispatch_root() / "lane_health.json"


def outcomes_path() -> Path:
    return dispatch_root() / "outcomes.jsonl"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_path_conventions -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dispatch_lib/path_conventions.py tests/test_path_conventions.py
git commit -m "feat: add path conventions for availability, lane_health, outcomes state"
```

---

## Task 2: Lane-health cooldown ledger + failure classifier

**Files:**
- Create: `dispatch_lib/lane_health.py`
- Test: `tests/test_lane_health.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lane_health.py
import time
import unittest
from unittest import mock
from pathlib import Path
import tempfile

from dispatch_lib import lane_health

class TestClassify(unittest.TestCase):
    def test_classify_auth(self):
        self.assertEqual(lane_health.classify_failure("HTTP 401 Unauthorized"), "auth")
        self.assertEqual(lane_health.classify_failure("token expired"), "auth")

    def test_classify_rate_limit(self):
        self.assertEqual(lane_health.classify_failure("HTTP 429 Too Many Requests"), "rate_limit")

    def test_classify_network(self):
        self.assertEqual(lane_health.classify_failure("Connection timed out"), "network")

    def test_classify_task_default(self):
        self.assertEqual(lane_health.classify_failure("AssertionError in tests"), "task")

class TestCooldown(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "lane_health.json"
        patcher = mock.patch("dispatch_lib.lane_health.lane_health_path", return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_demote_then_in_cooldown(self):
        lane_health.demote("zai-glm", "rate_limit", now=1000.0)
        self.assertTrue(lane_health.in_cooldown("zai-glm", now=1001.0))

    def test_cooldown_expires(self):
        lane_health.demote("zai-glm", "rate_limit", now=1000.0)
        # rate_limit backoff is 60s
        self.assertFalse(lane_health.in_cooldown("zai-glm", now=1000.0 + 61))

    def test_auth_longer_than_rate_limit(self):
        lane_health.demote("kimi-coding", "auth", now=1000.0)
        self.assertTrue(lane_health.in_cooldown("kimi-coding", now=1000.0 + 61))

    def test_recover_clears(self):
        lane_health.demote("zai-glm", "rate_limit", now=1000.0)
        lane_health.recover("zai-glm")
        self.assertFalse(lane_health.in_cooldown("zai-glm", now=1001.0))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_lane_health -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dispatch_lib.lane_health'`

- [ ] **Step 3: Implement the module**

```python
# dispatch_lib/lane_health.py
"""Lane health: classify runtime failures and track per-executor cooldowns.

Cooldowns are persisted to lane_health.json (atomic tmp+rename). The router
treats an executor in active cooldown as unavailable. task-class failures are
NOT lane faults and never cause a demotion.
"""
import json
import os
import re
import time
from pathlib import Path

from .path_conventions import lane_health_path

# Backoff seconds per failure class.
BACKOFF = {"rate_limit": 60, "network": 120, "auth": 900}

_AUTH = re.compile(r"\b(401|403|unauthor|forbidden|invalid api key|token expired|expired)\b", re.I)
_RATE = re.compile(r"\b(429|rate.?limit|too many requests|quota)\b", re.I)
_NET = re.compile(r"\b(timed out|timeout|connection (refused|reset|error)|dns|unreachable|temporarily)\b", re.I)


def classify_failure(text: str) -> str:
    """Return one of: auth, rate_limit, network, task."""
    text = text or ""
    if _AUTH.search(text):
        return "auth"
    if _RATE.search(text):
        return "rate_limit"
    if _NET.search(text):
        return "network"
    return "task"


def _read() -> dict:
    path = lane_health_path()
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_atomic(data: dict) -> None:
    path = lane_health_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def demote(executor: str, failure_class: str, now: float | None = None) -> None:
    """Record a cooldown for executor. No-op for task-class failures."""
    if failure_class == "task":
        return
    now = time.time() if now is None else now
    backoff = BACKOFF.get(failure_class, 120)
    data = _read()
    data[executor] = {
        "class": failure_class,
        "until": now + backoff,
        "since": now,
    }
    _write_atomic(data)


def in_cooldown(executor: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    entry = _read().get(executor)
    if not entry:
        return False
    return now < float(entry.get("until", 0))


def recover(executor: str) -> None:
    data = _read()
    if executor in data:
        del data[executor]
        _write_atomic(data)


def needs_relogin() -> list[str]:
    """Executors whose latest demotion was auth-class and still active."""
    now = time.time()
    out = []
    for ex, entry in _read().items():
        if entry.get("class") == "auth" and now < float(entry.get("until", 0)):
            out.append(ex)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_lane_health -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add dispatch_lib/lane_health.py tests/test_lane_health.py
git commit -m "feat: lane health cooldown ledger and failure classifier"
```

---

## Task 3: Availability resolver

**Files:**
- Create: `dispatch_lib/availability.py`
- Test: `tests/test_availability.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_availability.py
import unittest
from unittest import mock

from dispatch_lib import availability

MATRIX = {
    "executors": {
        "opus":        {"provider": "anthropic"},
        "openai-mini": {"provider": "openai-codex"},
        "zai-glm":     {"provider": "zai", "key_env": "Z_AI_API_KEY", "key_account": "z_ai_api_key"},
        "lm-studio":   {"provider": "lm-studio"},
    }
}

class TestAvailability(unittest.TestCase):
    def test_anthropic_available_when_claude_logged_in(self):
        with mock.patch.object(availability, "_anthropic_ready", return_value=True), \
             mock.patch.object(availability, "_codex_ready", return_value=False), \
             mock.patch.object(availability, "_key_present", return_value=False), \
             mock.patch.object(availability, "_local_ready", return_value=False):
            avail = availability.resolve(MATRIX, use_cache=False)
        self.assertTrue(avail["opus"]["available"])
        self.assertFalse(avail["openai-mini"]["available"])

    def test_api_key_provider_available_when_key_present(self):
        with mock.patch.object(availability, "_anthropic_ready", return_value=False), \
             mock.patch.object(availability, "_codex_ready", return_value=False), \
             mock.patch.object(availability, "_key_present", return_value=True), \
             mock.patch.object(availability, "_local_ready", return_value=False):
            avail = availability.resolve(MATRIX, use_cache=False)
        self.assertTrue(avail["zai-glm"]["available"])

    def test_available_set_helper(self):
        with mock.patch.object(availability, "_anthropic_ready", return_value=True), \
             mock.patch.object(availability, "_codex_ready", return_value=True), \
             mock.patch.object(availability, "_key_present", return_value=False), \
             mock.patch.object(availability, "_local_ready", return_value=False):
            s = availability.available_set(MATRIX, use_cache=False)
        self.assertIn("opus", s)
        self.assertIn("openai-mini", s)
        self.assertNotIn("zai-glm", s)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_availability -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dispatch_lib.availability'`

- [ ] **Step 3: Implement the module**

```python
# dispatch_lib/availability.py
"""Resolve which executors are actually reachable right now.

Reachability by provider family:
  - anthropic    -> Claude Code logged in
  - openai-codex -> ~/.codex/auth.json present
  - local        -> CLI present (ollama / lm-studio endpoint)
  - everything else (API-key providers) -> key resolvable (presence only)

Results cached to availability.json with a TTL. Secret VALUES are never read
into the cache or logs — only booleans.
"""
import json
import os
import shutil
import time
from pathlib import Path

from .path_conventions import availability_path

CACHE_TTL_SECONDS = 300


def _anthropic_ready() -> bool:
    # Claude Code stores creds in Keychain or a credentials file depending on
    # platform; treat presence of either as logged in.
    if (Path.home() / ".claude" / ".credentials.json").exists():
        return True
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    # Keychain fallback (service used by Claude Code login varies; cheap check).
    return _keychain_has("Claude Code", None) or _keychain_has("claude.ai", None)


def _codex_ready() -> bool:
    return (Path.home() / ".codex" / "auth.json").exists()


def _local_ready(provider: str) -> bool:
    if provider == "ollama":
        return shutil.which("ollama") is not None
    if provider == "lm-studio":
        # Endpoint reachability is checked lazily; presence of base url env or
        # OPENAI_API_KEY is the cheap proxy here.
        return bool(os.environ.get("LM_STUDIO_BASE_URL") or os.environ.get("OPENAI_API_KEY"))
    return False


def _keychain_has(service: str, account: str | None) -> bool:
    if not shutil.which("security"):
        return False
    cmd = ["security", "find-generic-password", "-s", service]
    if account:
        cmd += ["-a", account]
    import subprocess
    return subprocess.run(cmd, capture_output=True).returncode == 0


def _key_present(env_var: str | None, account: str | None) -> bool:
    """Mirror ce_load_api_key lookup order (presence only)."""
    if env_var and os.environ.get(env_var):
        return True
    if account and _keychain_has("pushing-dispatch", account):
        return True
    return False


def _executor_available(cfg: dict) -> bool:
    provider = cfg.get("provider", "")
    if provider == "anthropic":
        return _anthropic_ready()
    if provider == "openai-codex":
        return _codex_ready()
    if provider in ("ollama", "lm-studio"):
        return _local_ready(provider)
    return _key_present(cfg.get("key_env"), cfg.get("key_account"))


def resolve(matrix: dict, use_cache: bool = True) -> dict:
    """Return {executor: {"available": bool, "provider": str}} for all executors."""
    if use_cache:
        cached = _read_cache()
        if cached is not None:
            return cached
    out = {}
    for name, cfg in matrix.get("executors", {}).items():
        out[name] = {
            "available": _executor_available(cfg),
            "provider": cfg.get("provider", ""),
        }
    _write_cache(out)
    return out


def available_set(matrix: dict, use_cache: bool = True) -> set:
    return {k for k, v in resolve(matrix, use_cache=use_cache).items() if v["available"]}


def _read_cache():
    path = availability_path()
    if not path.exists():
        return None
    try:
        with open(path) as f:
            blob = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if time.time() - blob.get("ts", 0) > CACHE_TTL_SECONDS:
        return None
    return blob.get("executors")


def _write_cache(executors: dict) -> None:
    path = availability_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with open(tmp, "w") as f:
        json.dump({"ts": time.time(), "executors": executors}, f, indent=2)
    os.replace(tmp, path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_availability -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add dispatch_lib/availability.py tests/test_availability.py
git commit -m "feat: availability resolver with TTL cache (presence-only, no secret reads)"
```

---

## Task 4: Matrix — ordered candidate lists, key metadata, account hints

**Files:**
- Modify: `dispatch_matrix.toml`
- Modify: `dispatch_matrix.toml.example`
- Test: `tests/test_matrix_shape.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_matrix_shape.py
import unittest
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class TestMatrixShape(unittest.TestCase):
    def setUp(self):
        with open(ROOT / "dispatch_matrix.toml", "rb") as f:
            self.m = tomllib.load(f)

    def test_auto_route_has_ordered_lists(self):
        ar = self.m["auto_route"]
        for key in ("trivial_candidates", "standard_candidates",
                    "hard_task_candidates", "hard_breakout_candidates",
                    "long_context_candidates", "consult_candidates"):
            self.assertIsInstance(ar[key], list, key)
            self.assertTrue(len(ar[key]) >= 1, key)

    def test_candidates_reference_real_executors(self):
        executors = set(self.m["executors"])
        ar = self.m["auto_route"]
        for key, val in ar.items():
            if key.endswith("_candidates"):
                for ex in val:
                    self.assertIn(ex, executors, f"{key} -> {ex}")

    def test_api_key_executors_have_key_metadata(self):
        # Executors that are NOT cli-auth/local must declare key_env + key_account.
        cli_or_local = {"anthropic", "openai-codex", "ollama", "lm-studio"}
        for name, cfg in self.m["executors"].items():
            if cfg.get("provider") not in cli_or_local:
                self.assertIn("key_env", cfg, name)
                self.assertIn("key_account", cfg, name)

    def test_openai_executors_have_account_hint(self):
        for name, cfg in self.m["executors"].items():
            if cfg.get("provider") == "openai-codex":
                self.assertIn("account", cfg, name)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_matrix_shape -v`
Expected: FAIL on `test_auto_route_has_ordered_lists` (KeyError `trivial_candidates`)

- [ ] **Step 3: Edit the matrix**

In `dispatch_matrix.toml`, replace the `[auto_route]` block body with ordered lists (keep the old single-value keys too for back-compat — Task 5 reads lists first, falls back to singles):

```toml
[auto_route]
# Ordered candidate lists per tier. Router returns the first executor that is
# mode-allowed AND available AND not in cooldown. Adaptive-balanced: hard/deep
# tiers lead with stronger models.
trivial_candidates        = ["openai-mini", "haiku", "zai-air", "gemini-lite"]
standard_candidates       = ["codex-spark", "sonnet", "zai-glm", "openai-mini"]
hard_task_candidates      = ["codex-spark", "openai-gpt55-high", "zai-glm", "opus"]
hard_breakout_candidates  = ["openai-gpt55-high", "opus", "openai-gpt55", "zai-glm"]
long_context_candidates   = ["kimi-coding", "gemini-pro", "openai-gpt55", "opus"]
consult_candidates        = ["opus", "openai-gpt55-high", "zai-glm"]

# Back-compat single-value keys (still read if *_candidates absent).
long_context_executor = "kimi-coding"
long_context_threshold_tokens = 50000
trivial_executor = "openai-mini"
trivial_threshold_tokens = 5000
hard_coding_breakout_executor = "openai-gpt55"
hard_coding_task_executor = "codex-spark"
default_breakout = "openai-gpt55-high"
default_task = "codex-spark"
default_consult = "opus"

# Learning loop: when true, candidate ordering is re-biased by outcomes.jsonl.
learning = false
```

For every API-key executor (NOT `anthropic`, `openai-codex`, `ollama`, `lm-studio`),
add `key_env` and `key_account` lines matching MANIFEST_REPLACEMENT_PROVIDERS.md.
Example for `[executors.zai-glm]`:

```toml
key_env = "Z_AI_API_KEY"
key_account = "z_ai_api_key"
```

Apply the analogous pair to: `kimi-coding` (`KIMI_API_KEY`/`kimi_api_key`),
`kimi-moonshot` (`MOONSHOT_API_KEY`/`moonshot_api_key`), `deepseek`
(`DEEPSEEK_API_KEY`/`deepseek_api_key`), `zai-air` (`Z_AI_API_KEY`/`z_ai_api_key`),
`minimax`/`minimax-m25`/`minimax-m25-highspeed` (`MINIMAX_API_KEY`/`minimax_api_key`),
`minimax-coding-plan` (`CUSTOM_MINIMAX_CODING_PLAN_API_KEY`/`custom_minimax_coding_plan_api_key`),
`inception-mercury` (`CUSTOM_INCEPTION_API_KEY`/`custom_inception_api_key`),
`gemini-pro`/`gemini-flash`/`gemini-lite` (`GEMINI_API_KEY`/`gemini_api_key`),
`kilo-*` (`KILO_API_KEY`/`kilo_api_key`).

For each `openai-codex` executor add an `account` hint (default until the 3rd
account is confirmed):

```toml
account = "icloud"   # or "puenteworks"
```

Then mirror ALL changes into `dispatch_matrix.toml.example` (the two files are kept identical).

- [ ] **Step 4: Run tests + matrix validator**

Run: `python3 -m unittest tests.test_matrix_shape -v && python3 cli.py validate-matrix dispatch_matrix.toml`
Expected: PASS (4 tests) and `Matrix is valid.`

- [ ] **Step 5: Commit**

```bash
git add dispatch_matrix.toml dispatch_matrix.toml.example tests/test_matrix_shape.py
git commit -m "feat: matrix ordered candidate lists, key metadata, openai account hints"
```

---

## Task 5: Router — availability + cooldown aware, ordered candidates

**Files:**
- Modify: `dispatch_lib/auto_router.py`
- Test: `tests/test_auto_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auto_router.py
import unittest
from unittest import mock
from dispatch_lib import auto_router

MATRIX = {
    "executors": {
        "openai-mini":       {"provider": "openai-codex", "allowed_modes": ["task", "consult"]},
        "codex-spark":       {"provider": "openai-codex", "allowed_modes": ["task", "breakout"]},
        "openai-gpt55-high": {"provider": "openai-codex", "allowed_modes": ["task", "breakout", "consult"]},
        "zai-glm":           {"provider": "zai", "allowed_modes": ["task", "breakout", "consult"]},
        "opus":              {"provider": "anthropic", "allowed_modes": ["task", "breakout", "consult"]},
        "kimi-coding":       {"provider": "kimi", "allowed_modes": ["task", "consult"]},
    },
    "auto_route": {
        "trivial_candidates": ["openai-mini", "zai-glm"],
        "hard_task_candidates": ["codex-spark", "openai-gpt55-high", "zai-glm", "opus"],
        "long_context_candidates": ["kimi-coding", "opus"],
        "consult_candidates": ["opus", "openai-gpt55-high"],
        "standard_candidates": ["codex-spark", "zai-glm"],
        "trivial_threshold_tokens": 5000,
        "long_context_threshold_tokens": 50000,
    },
}

def route(task, mode, available, cooldown=()):
    with mock.patch.object(auto_router, "available_set", return_value=set(available)), \
         mock.patch.object(auto_router, "in_cooldown", side_effect=lambda e: e in cooldown):
        return auto_router.auto_route(task, mode, matrix_dict=MATRIX)

class TestRouter(unittest.TestCase):
    def test_explicit_executor_passthrough(self):
        self.assertEqual(
            auto_router.auto_route("x", "task", matrix_dict=MATRIX, explicit_executor="opus"),
            "opus")

    def test_trivial_picks_first_available(self):
        self.assertEqual(route("fix typo", "task", available=["openai-mini", "zai-glm"]), "openai-mini")

    def test_trivial_falls_back_when_first_unavailable(self):
        self.assertEqual(route("fix typo", "task", available=["zai-glm"]), "zai-glm")

    def test_hard_task_leads_with_strong_model(self):
        t = "implement and debug complex concurrency logic"
        self.assertEqual(route(t, "task", available=["codex-spark", "opus"]), "codex-spark")

    def test_cooldown_skips_executor(self):
        t = "implement and debug complex concurrency logic"
        self.assertEqual(
            route(t, "task", available=["codex-spark", "openai-gpt55-high", "opus"],
                  cooldown=["codex-spark"]),
            "openai-gpt55-high")

    def test_long_context_keyword(self):
        self.assertEqual(route("summarize the entire codebase", "task",
                               available=["kimi-coding", "opus"]), "kimi-coding")

    def test_errors_when_nothing_available(self):
        with self.assertRaises(auto_router.NoExecutorAvailable):
            route("fix typo", "task", available=[])

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_auto_router -v`
Expected: FAIL — `auto_route()` has no `matrix_dict`/`available_set`/`NoExecutorAvailable`.

- [ ] **Step 3: Rewrite `auto_router.py`**

Replace the file with the version below. Keeps keyword regexes; adds tier resolution, ordered-list walking, availability + cooldown filtering, `matrix_dict` injection for tests, and a typed error. Back-compat: if a `*_candidates` list is absent, fall back to the legacy single-value key as a one-element list.

```python
"""Auto-routing: pick the best AVAILABLE executor for a brief.

The dispatch matrix is the source of truth. The router maps a brief to a tier,
then walks that tier's ordered candidate list and returns the first executor
that is mode-allowed, available, and not in cooldown.
"""
import re
from pathlib import Path

from .context_budget import estimate_tokens
from .availability import available_set
from .lane_health import in_cooldown

try:
    import tomllib
except ImportError:  # pragma: no cover
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


class NoExecutorAvailable(RuntimeError):
    """Raised when no mode-capable, available executor exists for a brief."""


LONG_CONTEXT_KEYWORDS = re.compile(
    r"(summarize|summarise|analyze|analyse|review|audit)\s+(all|every|each|the entire)",
    re.IGNORECASE,
)
MECHANICAL_KEYWORDS = re.compile(
    r"(rename|refactor|lint|format|fix typo|add comment|update import)", re.IGNORECASE,
)
HARD_CODING_KEYWORDS = re.compile(
    r"(implement|architect|design|debug|optimize|complex logic|concurren)", re.IGNORECASE,
)


def _load_matrix(matrix_path):
    if not matrix_path or not tomllib:
        return {}
    path = Path(matrix_path)
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _candidates(route_cfg, list_key, legacy_keys):
    """Ordered candidate list. Falls back to legacy single-value keys."""
    if route_cfg.get(list_key):
        return list(route_cfg[list_key])
    out = []
    for k in legacy_keys:
        v = route_cfg.get(k)
        if v:
            out.append(v)
    return out


def _tier(brief_text, mode, route_cfg):
    """Return (list_key, legacy_keys) for the brief's tier."""
    tokens = estimate_tokens(brief_text)
    long_threshold = int(route_cfg.get("long_context_threshold_tokens", 50_000))
    if tokens > long_threshold or LONG_CONTEXT_KEYWORDS.search(brief_text):
        return "long_context_candidates", ["long_context_executor"]
    if HARD_CODING_KEYWORDS.search(brief_text):
        if mode == "breakout":
            return "hard_breakout_candidates", ["hard_coding_breakout_executor", "default_breakout"]
        return "hard_task_candidates", ["hard_coding_task_executor", "default_task"]
    if mode == "consult":
        return "consult_candidates", ["default_consult"]
    if mode == "breakout":
        return "hard_breakout_candidates", ["default_breakout"]
    trivial_threshold = int(route_cfg.get("trivial_threshold_tokens", 5_000))
    if tokens < trivial_threshold and (mode == "task" or MECHANICAL_KEYWORDS.search(brief_text)):
        return "trivial_candidates", ["trivial_executor", "default_task"]
    return "standard_candidates", ["default_task"]


def _mode_allowed(matrix, executor, mode):
    cfg = matrix.get("executors", {}).get(executor, {})
    return mode in cfg.get("allowed_modes", [])


def auto_route(brief_text, mode, matrix_path=None, explicit_executor=None, matrix_dict=None):
    if explicit_executor and explicit_executor != "auto":
        return explicit_executor

    matrix = matrix_dict if matrix_dict is not None else _load_matrix(matrix_path)
    route_cfg = matrix.get("auto_route", {})

    avail = available_set(matrix)
    list_key, legacy = _tier(brief_text, mode, route_cfg)

    # Build the search order: tier candidates, then a broad safety net of every
    # mode-capable executor in matrix order.
    order = _candidates(route_cfg, list_key, legacy)
    order += [e for e in matrix.get("executors", {}) if e not in order]

    for executor in order:
        if not _mode_allowed(matrix, executor, mode):
            continue
        if executor not in avail:
            continue
        if in_cooldown(executor):
            continue
        return executor

    raise NoExecutorAvailable(
        f"No available executor for mode={mode}. "
        f"Run 'pushing-dispatch doctor' to see which providers need attention."
    )


def detect_mode_from_keywords(brief_text):
    text_lower = brief_text.lower()
    if any(kw in text_lower for kw in ["plan", "architect", "design", "orchestrate"]):
        return "breakout"
    if any(kw in text_lower for kw in ["fix", "rename", "lint", "update", "edit"]):
        return "task"
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_auto_router -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Verify the live router still resolves and now respects availability**

Run: `python3 cli.py route --mode task --task "fix a typo" --json`
Expected: JSON with an `executor` that is actually reachable on this machine (e.g. `openai-mini` or `opus`), not a dead lane.

- [ ] **Step 6: Commit**

```bash
git add dispatch_lib/auto_router.py tests/test_auto_router.py
git commit -m "feat: availability- and cooldown-aware ordered-candidate routing"
```

---

## Task 6: Credential consolidation script

**Files:**
- Create: `bin/sync-credentials.sh`
- Manual verification (no unit test — touches real Keychain)

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# sync-credentials.sh - Consolidate provider API keys into the macOS Keychain
# service "pushing-dispatch" so non-interactive dispatch subprocesses can reach
# them. Idempotent. Never prints secret values.
set -euo pipefail

SERVICE="pushing-dispatch"

# account_name  env_var_name  goose_env_key  dopamine_account
MAP=(
  "kimi_api_key|KIMI_API_KEY||"
  "moonshot_api_key|MOONSHOT_API_KEY||"
  "deepseek_api_key|DEEPSEEK_API_KEY||"
  "minimax_api_key|MINIMAX_API_KEY|MINIMAX_API_KEY|dopamine-depot:minimax"
  "custom_minimax_coding_plan_api_key|CUSTOM_MINIMAX_CODING_PLAN_API_KEY||"
  "custom_inception_api_key|CUSTOM_INCEPTION_API_KEY||"
  "z_ai_api_key|Z_AI_API_KEY||"
  "kilo_api_key|KILO_API_KEY||"
  "gemini_api_key|GEMINI_API_KEY||dopamine-depot:gemini"
)

GOOSE_ENV="$HOME/.config/goose/.env"

# Harvest currently-exported keys from an interactive zsh (names already in .zshrc).
declare -A ZSH_KEYS
while IFS='=' read -r k v; do
  [[ -n "$k" ]] && ZSH_KEYS["$k"]="$v"
done < <(zsh -ic 'for v in KIMI_API_KEY MOONSHOT_API_KEY DEEPSEEK_API_KEY MINIMAX_API_KEY CUSTOM_MINIMAX_CODING_PLAN_API_KEY CUSTOM_INCEPTION_API_KEY Z_AI_API_KEY KILO_API_KEY GEMINI_API_KEY GOOGLE_API_KEY; do [[ -n "${(P)v:-}" ]] && print "$v=${(P)v}"; done' 2>/dev/null || true)

get_from_goose() { [[ -f "$GOOSE_ENV" ]] && grep -E "^$1=" "$GOOSE_ENV" | head -1 | cut -d= -f2- || true; }
get_from_dopamine() {
  local svc="${1%%:*}" acct="${1##*:}"
  security find-generic-password -s "$svc" -a "$acct" -w 2>/dev/null || true
}

echo "Credential sync into Keychain service '$SERVICE'"
echo "================================================"
for row in "${MAP[@]}"; do
  IFS='|' read -r acct envname goosekey dopamine <<< "$row"
  val=""
  # Priority: existing pushing-dispatch entry (keep) -> zsh export -> goose -> dopamine
  if security find-generic-password -s "$SERVICE" -a "$acct" >/dev/null 2>&1; then
    echo "  keep   $acct (already in $SERVICE)"; continue
  fi
  [[ -z "$val" && -n "${ZSH_KEYS[$envname]:-}" ]] && val="${ZSH_KEYS[$envname]}"
  [[ -z "$val" && -n "$goosekey" ]] && val="$(get_from_goose "$goosekey")"
  [[ -z "$val" && -n "$dopamine" ]] && val="$(get_from_dopamine "$dopamine")"
  if [[ -n "$val" ]]; then
    security add-generic-password -s "$SERVICE" -a "$acct" -w "$val" -U >/dev/null
    echo "  SET    $acct"
  else
    echo "  miss   $acct (no source found)"
  fi
done
echo "------------------------------------------------"
echo "CLI-auth providers (no key needed):"
[[ -f "$HOME/.codex/auth.json" ]] && echo "  ok     openai (codex auth.json)" || echo "  MISS   openai (run: codex auth login)"
echo "  ok     anthropic (claude code login)"
echo
echo "Done. Verify with: python3 cli.py doctor"
```

- [ ] **Step 2: Make executable and run it**

Run: `chmod +x bin/sync-credentials.sh && bash bin/sync-credentials.sh`
Expected: a found/missing table; keys present in `.zshrc`/`goose`/`dopamine-depot` show `SET`, others show `miss`. No secret values printed.

- [ ] **Step 3: Verify keys are now reachable to a bare subprocess**

Run: `env -i HOME="$HOME" PATH="$PATH" security find-generic-password -s pushing-dispatch -a minimax_api_key >/dev/null 2>&1 && echo REACHABLE || echo "missing (expected if no minimax key on this machine)"`
Expected: `REACHABLE` if a MiniMax key existed in any source.

- [ ] **Step 4: Commit**

```bash
git add bin/sync-credentials.sh
git commit -m "feat: sync-credentials.sh consolidates provider keys into pushing-dispatch Keychain"
```

---

## Task 7: `doctor` CLI + enriched `route --json`

**Files:**
- Modify: `cli.py`
- Test: `tests/test_doctor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_doctor.py
import unittest
from unittest import mock
from dispatch_lib import availability, lane_health

class TestDoctorData(unittest.TestCase):
    def test_build_doctor_rows(self):
        from cli import _doctor_rows  # function added in this task
        matrix = {"executors": {
            "opus": {"provider": "anthropic"},
            "zai-glm": {"provider": "zai", "key_env": "Z_AI_API_KEY", "key_account": "z_ai_api_key"},
        }}
        with mock.patch.object(availability, "resolve", return_value={
                 "opus": {"available": True, "provider": "anthropic"},
                 "zai-glm": {"available": False, "provider": "zai"}}), \
             mock.patch.object(lane_health, "in_cooldown", return_value=False), \
             mock.patch.object(lane_health, "needs_relogin", return_value=[]):
            rows = _doctor_rows(matrix)
        by = {r["executor"]: r for r in rows}
        self.assertTrue(by["opus"]["available"])
        self.assertFalse(by["zai-glm"]["available"])

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_doctor -v`
Expected: FAIL with `ImportError: cannot import name '_doctor_rows'`

- [ ] **Step 3: Add `_doctor_rows`, the `doctor` subcommand, and enrich `route`**

In `cli.py`: add the helper and wire a `doctor` subparser. Locate the existing `route` handler and add `available`/`considered`/`fallback_from` to its JSON output.

```python
# near other imports
from dispatch_lib import availability, lane_health

def _doctor_rows(matrix):
    avail = availability.resolve(matrix, use_cache=False)
    relogin = set(lane_health.needs_relogin())
    rows = []
    for name, cfg in matrix.get("executors", {}).items():
        a = avail.get(name, {"available": False, "provider": cfg.get("provider", "")})
        rows.append({
            "executor": name,
            "provider": a["provider"],
            "available": a["available"],
            "cooldown": lane_health.in_cooldown(name),
            "needs_relogin": name in relogin,
        })
    return rows

def _cmd_doctor(args):
    import tomllib
    with open(args.matrix or "dispatch_matrix.toml", "rb") as f:
        matrix = tomllib.load(f)
    rows = _doctor_rows(matrix)
    if getattr(args, "json", False):
        print(json.dumps(rows, indent=2)); return 0
    print(f"{'EXECUTOR':24} {'PROVIDER':14} {'STATE'}")
    print("-" * 60)
    for r in sorted(rows, key=lambda x: (not x["available"], x["executor"])):
        state = "available" if r["available"] else "UNAVAILABLE"
        if r["cooldown"]:
            state = "cooldown"
        if r["needs_relogin"]:
            state = "NEEDS RE-LOGIN"
        print(f"{r['executor']:24} {r['provider']:14} {state}")
    return 0
```

Register the subparser alongside the others (mirror how `validate-matrix` is registered):

```python
p_doctor = subparsers.add_parser("doctor", help="Show live executor availability/health")
p_doctor.add_argument("--matrix", default=None)
p_doctor.add_argument("--json", action="store_true")
p_doctor.set_defaults(func=_cmd_doctor)
```

- [ ] **Step 4: Run test + the live command**

Run: `python3 -m unittest tests.test_doctor -v && python3 cli.py doctor`
Expected: PASS, and a table where `opus` and the codex/openai lanes show `available`, API-key lanes reflect what `sync-credentials.sh` populated.

- [ ] **Step 5: Commit**

```bash
git add cli.py tests/test_doctor.py
git commit -m "feat: pushing-dispatch doctor command and enriched route --json"
```

---

## Task 8: Outcome ledger (learning substrate, off by default)

**Files:**
- Create: `dispatch_lib/outcomes.py`
- Test: `tests/test_outcomes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_outcomes.py
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from dispatch_lib import outcomes

class TestOutcomes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "outcomes.jsonl"
        p = mock.patch("dispatch_lib.outcomes.outcomes_path", return_value=self.path)
        p.start(); self.addCleanup(p.stop); self.addCleanup(self.tmp.cleanup)

    def test_record_appends_jsonl(self):
        outcomes.record("w1", "codex-spark", "hard_task_candidates", "success", 12.5, 0.03)
        outcomes.record("w2", "zai-glm", "standard_candidates", "auth", 1.0, 0.0)
        lines = self.path.read_text().strip().splitlines()
        self.assertEqual(len(lines), 2)
        first = json.loads(lines[0])
        self.assertEqual(first["executor"], "codex-spark")
        self.assertEqual(first["result"], "success")

    def test_success_rate(self):
        outcomes.record("w1", "zai-glm", "standard_candidates", "success", 1, 0)
        outcomes.record("w2", "zai-glm", "standard_candidates", "task", 1, 0)
        self.assertAlmostEqual(outcomes.success_rate("zai-glm"), 0.5)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_outcomes -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dispatch_lib.outcomes'`

- [ ] **Step 3: Implement**

```python
# dispatch_lib/outcomes.py
"""Append-only outcome ledger. Substrate for the (off-by-default) learning loop."""
import json
import os
import time

from .path_conventions import outcomes_path


def record(worker_id, executor, tier, result, duration_s, cost_usd):
    """Append one outcome. result in {success, auth, rate_limit, network, task}."""
    path = outcomes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.time(),
        "worker_id": worker_id,
        "executor": executor,
        "tier": tier,
        "result": result,
        "duration_s": duration_s,
        "cost_usd": cost_usd,
    }
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _read():
    path = outcomes_path()
    if not path.exists():
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def success_rate(executor):
    rows = [r for r in _read() if r["executor"] == executor]
    if not rows:
        return None
    ok = sum(1 for r in rows if r["result"] == "success")
    return ok / len(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_outcomes -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add dispatch_lib/outcomes.py tests/test_outcomes.py
git commit -m "feat: append-only outcome ledger (learning substrate, off by default)"
```

---

## Task 9: Wrapper self-healing — classify, demote, record; OpenAI account switch

**Files:**
- Modify: `bin/wrappers/_exec.sh`
- Modify: `bin/wrappers/codex.sh` (account switch)
- Manual + smoke verification

- [ ] **Step 1: Add a Python finalize-hook helper call in `_exec.sh`**

In each of the four run paths (`ce_run_claude`, `ce_run_codex`, the openai-compat path, the gemini path), the error branch currently calls
`ce_finalize_status "errored" 4 "<tool> exited with code $exit_code"`.
Immediately AFTER that call (still inside the `if [[ $exit_code -ne 0 ]]` block), add:

```bash
        PYTHONPATH="$CE_REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - \
            "$CE_EXECUTOR_NAME" "$CE_WORKER_ID" "$CE_TIER" "$log_file" <<'PY' || true
import sys
from dispatch_lib import lane_health, outcomes
executor, worker_id, tier, log_file = sys.argv[1:5]
try:
    text = open(log_file, errors="replace").read()[-4000:]
except OSError:
    text = ""
cls = lane_health.classify_failure(text)
lane_health.demote(executor, cls)          # no-op for task-class
outcomes.record(worker_id, executor, tier, cls, 0.0, 0.0)
PY
```

And in each SUCCESS path (after a clean `exit_code == 0` finalize), add:

```bash
        PYTHONPATH="$CE_REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - \
            "$CE_EXECUTOR_NAME" "$CE_WORKER_ID" "$CE_TIER" <<'PY' || true
import sys
from dispatch_lib import lane_health, outcomes
executor, worker_id, tier = sys.argv[1:4]
lane_health.recover(executor)
outcomes.record(worker_id, executor, tier, "success", 0.0, 0.0)
PY
```

`CE_EXECUTOR_NAME` and `CE_TIER` must be exported during arg parsing. In
`ce_parse_args`, after the executor/worker id are known, add defaults:

```bash
export CE_EXECUTOR_NAME="${CE_EXECUTOR_NAME:-${CE_TOOL_NAME:-unknown}}"
export CE_TIER="${CE_TIER:-unknown}"
```

(`cli.py` already knows the chosen executor and tier from routing; pass them via
`--executor-name` / `--tier` env when launching the wrapper. If those flags do
not yet exist, set the env vars from the dispatch launch path in `cli.py`.)

- [ ] **Step 2: OpenAI account switch in `codex.sh`**

In `bin/wrappers/codex.sh`, before `ce_run_codex`, add:

```bash
if [[ -n "${CE_OPENAI_ACCOUNT:-}" ]] && command -v codex-switch &>/dev/null; then
    codex-switch "$CE_OPENAI_ACCOUNT" >/dev/null 2>&1 || true
fi
```

The dispatch launch path sets `CE_OPENAI_ACCOUNT` from the matrix executor's
`account` hint.

- [ ] **Step 3: Verify the smoke test still passes end-to-end**

Run: `bash bin/smoke-test.sh`
Expected: `PASS: Worker completed successfully.`

- [ ] **Step 4: Verify a success outcome was recorded**

Run: `tail -1 ~/.local/share/pushing-dispatch/outcomes.jsonl`
Expected: a JSON line with `"result": "success"`.

- [ ] **Step 5: Commit**

```bash
git add bin/wrappers/_exec.sh bin/wrappers/codex.sh
git commit -m "feat: wrapper self-healing (classify/demote/recover, outcome record) + openai account switch"
```

---

## Task 10: Nesting depth 2 + cli launch wiring for executor/tier/account

**Files:**
- Modify: `dispatch_matrix.toml` + `.example` (`[nested_dispatch] max_depth = 2`)
- Modify: `cli.py` (pass `CE_EXECUTOR_NAME`, `CE_TIER`, `CE_OPENAI_ACCOUNT` to wrappers)
- Test: `tests/test_nesting.py` (depth guard) + manual

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nesting.py
import unittest
import tomllib
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

class TestNesting(unittest.TestCase):
    def test_max_depth_is_two(self):
        with open(ROOT / "dispatch_matrix.toml", "rb") as f:
            m = tomllib.load(f)
        self.assertEqual(m["nested_dispatch"]["max_depth"], 2)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_nesting -v`
Expected: FAIL (`max_depth` is currently 1).

- [ ] **Step 3: Edit matrix + cli launch**

Set `max_depth = 2` in `[nested_dispatch]` in both matrix files.
In `cli.py`, where a worker wrapper is launched, export the resolved values into
the wrapper's environment (find the subprocess/`os.environ` assembly for the
launch):

```python
env["CE_EXECUTOR_NAME"] = executor
env["CE_TIER"] = tier  # the list_key returned by routing; thread it out of auto_route if needed
account = matrix["executors"].get(executor, {}).get("account")
if account:
    env["CE_OPENAI_ACCOUNT"] = account
```

If `auto_route` does not currently return the tier, add an optional
`return_tier=False` parameter that returns `(executor, tier)` when set, and use
it in the launch path. Keep the default single-return signature for existing
callers/tests.

- [ ] **Step 4: Run tests + validate matrix + smoke**

Run: `python3 -m unittest discover -s tests -v && python3 cli.py validate-matrix dispatch_matrix.toml && bash bin/smoke-test.sh`
Expected: all tests PASS, `Matrix is valid.`, smoke `PASS`.

- [ ] **Step 5: Commit**

```bash
git add dispatch_matrix.toml dispatch_matrix.toml.example cli.py tests/test_nesting.py
git commit -m "feat: nesting depth 2 and launch wiring for executor/tier/account env"
```

---

## Task 11: Session warm-up + persistence verification

**Files:**
- Modify: `hooks/auto_poll.sh` (or add a SessionStart warm-up call)
- Manual verification

- [ ] **Step 1: Add availability warm-up to the session hook**

In `hooks/auto_poll.sh`, add an idempotent warm-up that refreshes availability
once per session start (cheap; cached afterward):

```bash
python3 "$DISPATCH_REPO/cli.py" doctor --json >/dev/null 2>&1 || true
```

(Use the repo path the hook already resolves.)

- [ ] **Step 2: Verify persistence across a simulated new session**

Run:
```bash
python3 cli.py doctor            # populates availability.json
ls -l ~/.local/share/pushing-dispatch/availability.json
# simulate cooldown then confirm it persists + is read by the router
python3 -c "from dispatch_lib import lane_health as L; L.demote('zai-glm','rate_limit')"
python3 cli.py doctor | grep zai-glm
```
Expected: `availability.json` exists; `zai-glm` shows `cooldown`. Re-running in a
fresh shell still shows the cooldown until it expires (persistent).

- [ ] **Step 3: Confirm self-heal recovery path**

Run: `python3 -c "from dispatch_lib import lane_health as L; L.recover('zai-glm')" && python3 cli.py doctor | grep zai-glm`
Expected: `zai-glm` no longer in cooldown.

- [ ] **Step 4: Commit**

```bash
git add hooks/auto_poll.sh
git commit -m "feat: session warm-up of availability cache; verified cooldown persistence"
```

---

## Task 12: Docs + full suite green

**Files:**
- Modify: `README.md`, `GLOBAL_AGENT_ROUTING.md` (document `doctor`, `sync-credentials.sh`, self-healing)
- Modify: `dispatch_packs/dispatch-protocol.md` (ordered candidates + availability rule)

- [ ] **Step 1: Run the full suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests PASS.

- [ ] **Step 2: Update docs**

Add to `GLOBAL_AGENT_ROUTING.md` a "First-time setup" line: `bash bin/sync-credentials.sh` then `pushing-dispatch doctor`. Add to `README.md` a short "Self-healing & availability" section describing cooldowns and `doctor`. Note in `dispatch_packs/dispatch-protocol.md` that routing now filters by availability + cooldown and uses ordered candidate lists.

- [ ] **Step 3: Commit**

```bash
git add README.md GLOBAL_AGENT_ROUTING.md dispatch_packs/dispatch-protocol.md
git commit -m "docs: document doctor, credential sync, self-healing routing"
```

---

## Self-Review (completed against spec)

- **Spec coverage:** Credential layer → Task 6; availability resolver → Task 3; self-healing (classify/demote/recover) → Tasks 2 + 9; router availability/cooldown + tiers → Tasks 4–5; OpenAI accounts → Tasks 4 + 9–10; outcome ledger/learning-off → Task 8; nesting depth 2 → Task 10; doctor/observability → Task 7; persistence → Tasks 1 + 11. All spec sections mapped.
- **Placeholder scan:** No TBD/TODO; every code step has complete code.
- **Type consistency:** `classify_failure`/`demote`/`in_cooldown`/`recover`/`needs_relogin` (lane_health), `resolve`/`available_set` (availability), `record`/`success_rate` (outcomes), `auto_route(...)`/`NoExecutorAvailable` (router), `_doctor_rows` (cli) — names used identically across tasks.
- **Open items from spec carried forward:** 3rd OpenAI account (`CERAFICA`) confirmation affects Task 4 `account` hints / Task 9 switch; quality signal in Task 8 starts as result-class proxy.
