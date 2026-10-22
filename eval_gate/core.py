"""Strict fixture loading, citation validation and bounded asynchronous evaluation."""
from __future__ import annotations

import asyncio
import json
import math
import re
import stat
import time
from pathlib import Path
from typing import Any

MAX_FILE = 1024 * 1024
ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
ROOT_KEYS = {"version", "sources", "cases"}
CASE_KEYS = {"id", "attempts"}
ATTEMPT_KEYS = {"delay_ms", "response", "error"}


class FixtureError(ValueError):
    """Fixture rejected before any cases run."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise FixtureError("duplicate JSON object key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise FixtureError("non-finite JSON number")


def _exact(obj: Any, keys: set[str], where: str) -> None:
    if not isinstance(obj, dict) or set(obj) != keys:
        raise FixtureError(f"{where} must have exactly the required fields")


def load_fixture(path: str | Path) -> dict[str, Any]:
    try:
        path = Path(path)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise FixtureError("fixture must be a regular file")
        if info.st_size > MAX_FILE:
            raise FixtureError("fixture exceeds 1 MiB")
        with path.open("rb") as stream:
            raw = stream.read(MAX_FILE + 1)
    except OSError as exc:
        raise FixtureError("cannot read fixture") from exc
    if len(raw) > MAX_FILE:
        raise FixtureError("fixture exceeds 1 MiB")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise FixtureError("invalid UTF-8 JSON fixture") from exc
    _exact(data, ROOT_KEYS, "root")
    if type(data["version"]) is not int or data["version"] != 1:
        raise FixtureError("version must be integer 1")
    sources = data["sources"]
    if not isinstance(sources, dict) or len(sources) > 100:
        raise FixtureError("sources must be an object with at most 100 entries")
    for sid, lines in sources.items():
        if not isinstance(sid, str) or not ID.fullmatch(sid):
            raise FixtureError("invalid source id")
        if not isinstance(lines, list) or len(lines) > 1000:
            raise FixtureError("each source must be a list of at most 1000 lines")
        if any(not isinstance(line, str) or len(line) > 2000 for line in lines):
            raise FixtureError("source lines must be strings of at most 2000 characters")
    cases = data["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        raise FixtureError("cases must contain 1 to 100 cases")
    ids: set[str] = set()
    for case in cases:
        _exact(case, CASE_KEYS, "case")
        cid = case["id"]
        if not isinstance(cid, str) or not ID.fullmatch(cid) or cid in ids:
            raise FixtureError("case ids must be unique safe IDs")
        ids.add(cid)
        attempts = case["attempts"]
        if not isinstance(attempts, list) or not 1 <= len(attempts) <= 10:
            raise FixtureError("each case needs 1 to 10 scripted attempts")
        for attempt in attempts:
            if not isinstance(attempt, dict) or (set(attempt) not in ({"delay_ms", "response"}, {"delay_ms", "error"})):
                raise FixtureError("attempt must have delay_ms and exactly one of response or error")
            delay = attempt["delay_ms"]
            if type(delay) not in (int, float) or not 0 <= delay <= 30000 or not math.isfinite(delay):
                raise FixtureError("delay_ms must be finite numeric 0..30000")
            if "error" in attempt and attempt["error"] not in ("transient", "permanent"):
                raise FixtureError("error must be transient or permanent")
            if "response" in attempt and not isinstance(attempt["response"], dict):
                raise FixtureError("response must be an object")
    return data


def validate_response(response: Any, sources: dict[str, list[str]]) -> str | None:
    """Return None for schema+literal-citation pass, else safe status code."""
    if not isinstance(response, dict) or set(response) != {"answer", "citations"}:
        return "schema_error"
    answer = response["answer"]
    citations = response["citations"]
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 4000:
        return "schema_error"
    if not isinstance(citations, list) or not 1 <= len(citations) <= 10:
        return "schema_error"
    for citation in citations:
        if not isinstance(citation, dict) or set(citation) != {"source", "line", "quote"}:
            return "schema_error"
        source, line, quote = citation["source"], citation["line"], citation["quote"]
        if not isinstance(source, str) or type(line) is not int or not isinstance(quote, str) or not quote.strip() or len(quote) > 2000:
            return "schema_error"
        rows = sources.get(source)
        if rows is None or line < 1 or line > len(rows):
            return "citation_error"
        if quote not in rows[line - 1]:
            return "citation_error"
    return None


class ScriptedAdapter:
    """Deterministic, local fixture simulator—not a model or agent SDK."""
    async def invoke(self, attempt: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(attempt["delay_ms"] / 1000)
        if "error" in attempt:
            raise ScriptedToolError(attempt["error"])
        return attempt["response"]


class ScriptedToolError(Exception):
    def __init__(self, kind: str):
        self.kind = kind
        super().__init__(kind)


def _event(events: list[dict[str, Any]], name: str, **metadata: Any) -> None:
    events.append({"event": name, **metadata})


async def _run_case(case: dict[str, Any], sources: dict[str, list[str]], adapter: ScriptedAdapter,
                    semaphore: asyncio.Semaphore, timeout: float, retries: int,
                    active: list[int], peak: list[int]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    start = time.monotonic()
    status = "tool_error"
    attempts_done = 0
    for number in range(1, retries + 2):
        scripted = case["attempts"][min(number - 1, len(case["attempts"]) - 1)]
        attempts_done = number
        _event(events, "attempt_queued", attempt=number)
        try:
            async with semaphore:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
                _event(events, "attempt_started", attempt=number)
                try:
                    response = await asyncio.wait_for(adapter.invoke(scripted), timeout=timeout)
                finally:
                    active[0] -= 1
            status = validate_response(response, sources) or "pass"
            _event(events, "attempt_finished", attempt=number, outcome=status)
            break
        except asyncio.TimeoutError:
            status = "timeout"
            _event(events, "attempt_finished", attempt=number, outcome="timeout")
            if number <= retries:
                _event(events, "retry_scheduled", attempt=number + 1)
                continue
            break
        except ScriptedToolError as exc:
            status = "tool_error"
            _event(events, "attempt_finished", attempt=number, outcome="tool_error")
            if exc.kind == "transient" and number <= retries:
                _event(events, "retry_scheduled", attempt=number + 1)
                continue
            break
    return {"case_id": case["id"], "status": status, "attempts": attempts_done,
            "duration_ms": round((time.monotonic() - start) * 1000, 3), "events": events}


async def evaluate(data: dict[str, Any], *, concurrency: int, timeout: float, retries: int) -> dict[str, Any]:
    """Evaluate load_fixture output; cancel propagates and active slots clean up."""
    if type(concurrency) is not int or not 1 <= concurrency <= 32:
        raise ValueError("concurrency must be integer 1..32")
    if type(retries) is not int or not 0 <= retries <= 3:
        raise ValueError("retries must be integer 0..3")
    if type(timeout) not in (int, float) or not 0.001 <= timeout <= 30 or not math.isfinite(timeout):
        raise ValueError("timeout must be finite numeric 0.001..30")
    semaphore = asyncio.Semaphore(concurrency)
    active, peak = [0], [0]
    adapter = ScriptedAdapter()
    results = await asyncio.gather(*(_run_case(c, data["sources"], adapter, semaphore,
                                                timeout, retries, active, peak) for c in data["cases"]))
    valid = sum(row["status"] == "pass" for row in results)
    return {"cases": results, "summary": {"valid_count": valid,
            "failed_count": len(results) - valid, "peak_active_attempts": peak[0]}}
