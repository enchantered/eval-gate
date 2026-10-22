import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from eval_gate.core import FixtureError, evaluate, load_fixture, validate_response

ROOT = Path(__file__).resolve().parents[1]
GOOD = {"version": 1, "sources": {"s": ["hello world"]}, "cases": [{"id": "c", "attempts": [{"delay_ms": 0, "response": {"answer": "hello", "citations": [{"source": "s", "line": 1, "quote": "hello"}]}}]}]}


class FixtureTests(unittest.TestCase):
    def load_text(self, text):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
            f.write(text)
            name = f.name
        try:
            return load_fixture(name)
        finally:
            os.unlink(name)

    def test_valid_example(self):
        data = load_fixture(ROOT / "examples/valid.json")
        self.assertEqual(data["version"], 1)

    def test_strict_root(self):
        with self.assertRaises(FixtureError):
            self.load_text(json.dumps({**GOOD, "extra": 1}))

    def test_bool_version_rejected(self):
        with self.assertRaises(FixtureError): self.load_text(json.dumps({**GOOD, "version": True}))

    def test_bool_delay_rejected(self):
        d = json.loads(json.dumps(GOOD)); d["cases"][0]["attempts"][0]["delay_ms"] = True
        with self.assertRaises(FixtureError): self.load_text(json.dumps(d))

    def test_nan_rejected(self):
        text = json.dumps(GOOD).replace('"delay_ms": 0', '"delay_ms": NaN')
        with self.assertRaises(FixtureError): self.load_text(text)

    def test_duplicate_keys_rejected(self):
        with self.assertRaises(FixtureError): self.load_text('{"version":1,"version":1,"sources":{},"cases":[]}')

    def test_invalid_source_id(self):
        d = json.loads(json.dumps(GOOD)); d["sources"] = {"bad id": []}
        with self.assertRaises(FixtureError): self.load_text(json.dumps(d))

    def test_line_caps(self):
        d = json.loads(json.dumps(GOOD)); d["sources"]["s"] = ["x" * 2001]
        with self.assertRaises(FixtureError): self.load_text(json.dumps(d))

    def test_duplicate_case_ids(self):
        d = json.loads(json.dumps(GOOD)); d["cases"].append(d["cases"][0])
        with self.assertRaises(FixtureError): self.load_text(json.dumps(d))

    def test_fixture_file_size(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b" " * (1024 * 1024 + 1)); name = f.name
        try:
            with self.assertRaises(FixtureError): load_fixture(name)
        finally: os.unlink(name)

    def test_extremely_large_integer_rejected_cleanly(self):
        for digits in (1000, 5000):
            text = json.dumps(GOOD).replace('"delay_ms": 0', '"delay_ms": ' + '9' * digits)
            with self.subTest(digits=digits), self.assertRaises(FixtureError):
                self.load_text(text)

    def test_deep_json_rejected_cleanly(self):
        with self.assertRaises(FixtureError):
            self.load_text('[' * 2000 + '0' + ']' * 2000)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO required')
    def test_named_pipe_rejected_before_opening(self):
        with tempfile.TemporaryDirectory() as root:
            pipe = Path(root) / 'pipe.json'
            os.mkfifo(pipe)
            with self.assertRaisesRegex(FixtureError, 'regular file'):
                load_fixture(pipe)


class ResponseTests(unittest.TestCase):
    def test_quote_matches(self): self.assertIsNone(validate_response(GOOD["cases"][0]["attempts"][0]["response"], GOOD["sources"]))
    def test_real_quote_does_not_imply_answer_truth(self):
        response = dict(GOOD['cases'][0]['attempts'][0]['response'],
                        answer='The source says goodbye, not hello.')
        self.assertIsNone(validate_response(response, GOOD['sources']))

    def test_bad_quote(self):
        r = GOOD["cases"][0]["attempts"][0]["response"] | {"citations": [{"source": "s", "line": 1, "quote": "nope"}]}
        self.assertEqual(validate_response(r, GOOD["sources"]), "citation_error")
    def test_missing_source(self):
        r = GOOD["cases"][0]["attempts"][0]["response"] | {"citations": [{"source": "missing", "line": 1, "quote": "hello"}]}
        self.assertEqual(validate_response(r, GOOD["sources"]), "citation_error")
    def test_bool_citation_line(self):
        r = GOOD["cases"][0]["attempts"][0]["response"] | {"citations": [{"source": "s", "line": True, "quote": "hello"}]}
        self.assertEqual(validate_response(r, GOOD["sources"]), "schema_error")
    def test_extra_response_field(self):
        r = dict(GOOD["cases"][0]["attempts"][0]["response"], private="secret")
        self.assertEqual(validate_response(r, GOOD["sources"]), "schema_error")


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_only_retry(self):
        d = json.loads(json.dumps(GOOD)); d["cases"][0]["attempts"] = [{"delay_ms": 0, "error": "permanent"}, {"delay_ms": 0, "response": GOOD["cases"][0]["attempts"][0]["response"]}]
        result = await evaluate(d, concurrency=1, timeout=1, retries=2)
        self.assertEqual(result["cases"][0]["attempts"], 1)
        self.assertEqual(result["cases"][0]["status"], "tool_error")

    async def test_timeouts_retry_and_then_pass(self):
        d = json.loads(json.dumps(GOOD)); d["cases"][0]["attempts"] = [{"delay_ms": 30, "response": GOOD["cases"][0]["attempts"][0]["response"]}, GOOD["cases"][0]["attempts"][0]]
        result = await evaluate(d, concurrency=1, timeout=.005, retries=1)
        self.assertEqual(result["cases"][0]["attempts"], 2)
        self.assertEqual(result["cases"][0]["status"], "pass")

    async def test_schema_error_not_retried(self):
        d = json.loads(json.dumps(GOOD)); d["cases"][0]["attempts"] = [{"delay_ms": 0, "response": {"leak": "secret"}}, GOOD["cases"][0]["attempts"][0]]
        result = await evaluate(d, concurrency=1, timeout=1, retries=2)
        self.assertEqual((result["cases"][0]["status"], result["cases"][0]["attempts"]), ("schema_error", 1))

    async def test_concurrency_cap(self):
        d = json.loads(json.dumps(GOOD)); base = d["cases"][0]["attempts"][0]
        d["cases"] = [{"id": f"c{i}", "attempts": [dict(base, delay_ms=20)]} for i in range(8)]
        result = await evaluate(d, concurrency=2, timeout=1, retries=0)
        self.assertLessEqual(result["summary"]["peak_active_attempts"], 2)
        self.assertGreater(result["summary"]["peak_active_attempts"], 0)

    async def test_input_order(self):
        d = json.loads(json.dumps(GOOD)); slow = dict(d["cases"][0]["attempts"][0], delay_ms=15)
        d["cases"] = [{"id": "first", "attempts": [slow]}, {"id": "second", "attempts": [d["cases"][0]["attempts"][0]]}]
        result = await evaluate(d, concurrency=2, timeout=1, retries=0)
        self.assertEqual([x["case_id"] for x in result["cases"]], ["first", "second"])

    async def test_cancel_releases_and_propagates(self):
        d = json.loads(json.dumps(GOOD)); d["cases"][0]["attempts"][0]["delay_ms"] = 500
        task = asyncio.create_task(evaluate(d, concurrency=1, timeout=1, retries=0))
        await asyncio.sleep(.01); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task

    async def test_direct_api_settings_fail_before_work(self):
        for setting, value in [('concurrency', 0), ('concurrency', True),
                               ('retries', 4), ('retries', True), ('timeout', float('nan')),
                               ('timeout', 10 ** 1000), ('timeout', True)]:
            options = {'concurrency': 1, 'timeout': 1, 'retries': 0}
            options[setting] = value
            with self.subTest(setting=setting), self.assertRaises(ValueError):
                await evaluate(GOOD, **options)

    async def test_trace_distinguishes_queue_from_active_work(self):
        result = await evaluate(GOOD, concurrency=1, timeout=1, retries=0)
        events = result['cases'][0]['events']
        self.assertEqual([e['event'] for e in events],
                         ['attempt_queued', 'attempt_started', 'attempt_finished'])


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "eval_gate", *args], cwd=ROOT, text=True, capture_output=True)
    def test_cli_exit_success(self): self.assertEqual(self.run_cli("run", "examples/valid.json", "--retries", "1", "--json").returncode, 0)
    def test_cli_exit_rejected_case(self): self.assertEqual(self.run_cli("run", "examples/invalid.json", "--json").returncode, 1)
    def test_cli_invalid_fixture_no_json_output(self):
        p = self.run_cli("run", "missing.json", "--json"); self.assertEqual(p.returncode, 2); self.assertEqual(p.stdout, "")
    def test_json_traces_redact_payload(self):
        p = self.run_cli("run", "examples/valid.json", "--json")
        self.assertNotIn("Retries are allowed", p.stdout); self.assertNotIn("Only retry transient", p.stdout)
        self.assertNotIn("response", p.stdout)


if __name__ == "__main__": unittest.main()
