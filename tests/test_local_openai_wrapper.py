import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WRAPPERS = ROOT / "bin" / "wrappers"


class _MismatchHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = json.dumps({
            "object": "list",
            "data": [{"id": "unexpected-model", "object": "model"}],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.dumps({
            "id": "test-response",
            "object": "chat.completion",
            "model": "unexpected-model",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "OK\nStatus: DONE"},
                "finish_reason": "stop",
            }],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


class TestLocalOpenAIWrapper(unittest.TestCase):
    def test_pi_local_identity_guard_is_mandatory_and_runs_twice(self):
        source = (WRAPPERS / "_exec.sh").read_text(encoding="utf-8")
        function = source.split("ce_run_pi_local() {", 1)[1]

        self.assertIn("PI_LOCAL_HEALTH_URL is required", source)
        self.assertIn("PI_LOCAL_EXPECT_MODEL is required", source)
        self.assertGreaterEqual(function.count("ce_verify_pi_local_identity"), 2)

    def _run_wrapper(self, wrapper_name, env_overrides):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _MismatchHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        with tempfile.TemporaryDirectory() as td:
            env = os.environ.copy()
            env.update({
                "DISPATCH_ROOT": td,
                "OPENAI_COMPAT_TIMEOUT": "2",
            })
            env.update(env_overrides(server.server_port))
            result = subprocess.run(
                [
                    "/usr/bin/env", "bash", str(WRAPPERS / wrapper_name),
                    "--worker-id", "identity-mismatch",
                    "--cwd", td,
                    "--mode", "task",
                    "--task", "Reply OK and finish.",
                ],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
        return result

    def test_wrapper_rejects_response_from_unexpected_model(self):
        result = self._run_wrapper(
            "ollama-xps-gpu.sh",
            lambda port: {
                "XPS_OLLAMA_BASE_URL": f"http://127.0.0.1:{port}/v1",
                "XPS_OLLAMA_MODEL": "qwen35-2b-max",
            },
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("response model identity mismatch", result.stdout + result.stderr)

    def test_nuc_wrappers_reject_response_from_unexpected_model(self):
        cases = (
            (
                "unsloth-nucbox.sh",
                lambda port: {
                    "UNSLOTH_BASE_URL": f"http://127.0.0.1:{port}/v1",
                    "UNSLOTH_MODEL": "unsloth/Qwen3.6-27B-MTP-GGUF",
                },
            ),
            (
                "lm-studio.sh",
                lambda port: {
                    "OPENAI_COMPAT_BASE_URL": f"http://127.0.0.1:{port}/v1",
                    "OPENAI_COMPAT_MODEL": "qwen3.5-35b-a3b",
                    "LOCAL_API_KEY": "test-only",
                },
            ),
        )
        for wrapper_name, env_factory in cases:
            with self.subTest(wrapper=wrapper_name):
                result = self._run_wrapper(wrapper_name, env_factory)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "model identity mismatch",
                    result.stdout + result.stderr,
                )


if __name__ == "__main__":
    unittest.main()
