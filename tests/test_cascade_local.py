import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WRAPPER = ROOT / "bin" / "wrappers" / "cascade-local.sh"


class _DellHandler(BaseHTTPRequestHandler):
    last_path = None
    last_body = None

    def do_POST(self):
        type(self).last_path = self.path
        type(self).last_body = json.loads(
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
        )
        payload = json.dumps({
            "model": "qwen35-2b-max",
            "message": {
                "role": "assistant",
                "content": "Candidate output is long enough.\nStatus: DONE",
            },
            "done": True,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


class _AmbiguousValidatorHandler(BaseHTTPRequestHandler):
    last_body = None

    def do_POST(self):
        type(self).last_body = json.loads(
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
        )
        payload = json.dumps({
            "model": "unsloth/Qwen3.6-27B-MTP-GGUF",
            "choices": [{
                "message": {"role": "assistant", "content": "MAYBE"},
            }],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


class _WrongDellIdentityHandler(_DellHandler):
    def do_POST(self):
        type(self).last_path = self.path
        type(self).last_body = json.loads(
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
        )
        payload = json.dumps({
            "model": "wrong-model",
            "message": {
                "role": "assistant",
                "content": "Candidate output is long enough.\nStatus: DONE",
            },
            "done": True,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _YesValidatorHandler(_AmbiguousValidatorHandler):
    def do_POST(self):
        type(self).last_body = json.loads(
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
        )
        payload = json.dumps({
            "model": "unsloth/Qwen3.6-27B-MTP-GGUF",
            "choices": [{
                "message": {"role": "assistant", "content": "YES"},
            }],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class TestCascadeLocal(unittest.TestCase):
    def test_wrapper_has_valid_bash_syntax(self):
        result = subprocess.run(
            ["/usr/bin/env", "bash", "-n", str(WRAPPER)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_validator_unavailable_fails_closed(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _DellHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        with tempfile.TemporaryDirectory() as td:
            env = os.environ.copy()
            env.update({
                "XPS_OLLAMA_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                "NUCBOX_VALIDATOR_URL": (
                    "http://127.0.0.1:1/v1/chat/completions"
                ),
                "DELL_TIMEOUT": "2",
                "NUCBOX_TIMEOUT": "1",
            })
            result = subprocess.run(
                [
                    "/usr/bin/env", "bash", str(WRAPPER),
                    "--cwd", td,
                    "--task", "Fix a typo in this sentence.",
                ],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("validator unavailable", result.stderr)
        self.assertNotIn("accepting 2B output", result.stderr)

    def test_ambiguous_validator_verdict_fails_closed(self):
        dell = ThreadingHTTPServer(("127.0.0.1", 0), _DellHandler)
        validator = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _AmbiguousValidatorHandler,
        )
        for server in (dell, validator):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)

        with tempfile.TemporaryDirectory() as td:
            env = os.environ.copy()
            env.update({
                "XPS_OLLAMA_BASE_URL": f"http://127.0.0.1:{dell.server_port}",
                "NUCBOX_VALIDATOR_URL": (
                    f"http://127.0.0.1:{validator.server_port}/v1/chat/completions"
                ),
                "DELL_TIMEOUT": "2",
                "NUCBOX_TIMEOUT": "2",
            })
            result = subprocess.run(
                [
                    "/usr/bin/env", "bash", str(WRAPPER),
                    "--cwd", td,
                    "--task", "Fix a typo in this sentence.",
                ],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid validator verdict", result.stderr)

    def test_dell_response_model_identity_mismatch_fails_closed(self):
        dell = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _WrongDellIdentityHandler,
        )
        validator = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _YesValidatorHandler,
        )
        for server in (dell, validator):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)

        with tempfile.TemporaryDirectory() as td:
            env = os.environ.copy()
            env.update({
                "XPS_OLLAMA_BASE_URL": f"http://127.0.0.1:{dell.server_port}",
                "NUCBOX_VALIDATOR_URL": (
                    f"http://127.0.0.1:{validator.server_port}/v1/chat/completions"
                ),
                "DELL_TIMEOUT": "2",
                "NUCBOX_TIMEOUT": "2",
            })
            result = subprocess.run(
                [
                    "/usr/bin/env", "bash", str(WRAPPER),
                    "--cwd", td,
                    "--task", "Fix a typo in this sentence.",
                ],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("response model identity mismatch", result.stderr)

    def test_dell_uses_api_chat_with_thinking_disabled(self):
        _DellHandler.last_path = None
        _DellHandler.last_body = None
        _YesValidatorHandler.last_body = None
        dell = ThreadingHTTPServer(("127.0.0.1", 0), _DellHandler)
        validator = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _YesValidatorHandler,
        )
        for server in (dell, validator):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)

        with tempfile.TemporaryDirectory() as td:
            env = os.environ.copy()
            env.update({
                "XPS_OLLAMA_BASE_URL": f"http://127.0.0.1:{dell.server_port}",
                "NUCBOX_VALIDATOR_URL": (
                    f"http://127.0.0.1:{validator.server_port}/v1/chat/completions"
                ),
                "DELL_TIMEOUT": "2",
                "NUCBOX_TIMEOUT": "2",
            })
            result = subprocess.run(
                [
                    "/usr/bin/env", "bash", str(WRAPPER),
                    "--cwd", td,
                    "--task", "Fix a typo in this sentence.",
                ],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(_DellHandler.last_path, "/api/chat")
        self.assertIs(_DellHandler.last_body["think"], False)
        self.assertIs(_DellHandler.last_body["stream"], False)
        self.assertLessEqual(
            _DellHandler.last_body["options"]["num_predict"],
            512,
        )
        self.assertLessEqual(_YesValidatorHandler.last_body["max_tokens"], 16)
        self.assertIs(
            _YesValidatorHandler.last_body["chat_template_kwargs"][
                "enable_thinking"
            ],
            False,
        )


if __name__ == "__main__":
    unittest.main()
