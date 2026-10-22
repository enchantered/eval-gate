# Eval Gate

A small, offline evaluation gate demonstrating a progressive AI-engineering portfolio flow: **Context Pocket provenance → response and citation QA → a gate before any multi-agent stage**. It validates output shape and verifies citations literally against supplied context. It does **not** judge answer truth, entailment, relevance, or completeness. This is a deterministic fixture simulator, not an actual Agents SDK, model call, or model verification service.

Read the [portfolio arc](docs/portfolio-arc.md), [dated evidence and paper/patent mapping](docs/2026-10-22-decision.md), and [preserved behavior history](docs/consumer-behavior-log.md). These explain why testing and async foundations come before more orchestration.

## Setup and run

Requires Python 3.11+; standard library only. From this directory:

```sh
python3 --version
python3 -m eval_gate run examples/valid.json --concurrency 2 --timeout 0.05 --retries 1 --json
python3 -m eval_gate run examples/invalid.json --json
python3 -m unittest discover -s tests -v
```

The valid example deliberately simulates a transient failure followed by a verified citation (exit 0). The invalid example has a fabricated quote and is rejected (exit 1). CLI exit codes are **0** when all cases pass, **1** when any case is rejected, and **2** for invalid arguments or a fixture rejected before evaluation. Human-readable output is the default; `--json` emits a machine-readable report.

## Fixture format

UTF-8 JSON, maximum 1 MiB, exact root fields only:

```json
{"version":1,"sources":{"manual":["A source line."]},"cases":[{"id":"demo","attempts":[{"delay_ms":0,"response":{"answer":"A response.","citations":[{"source":"manual","line":1,"quote":"A source line."}]}}]}]}
```

Each case contains 1–10 scripted attempts. An attempt has nonnegative finite `delay_ms` and exactly one of `response` or `error`; errors are `transient` or `permanent`. Each response has exactly `answer` and `citations`. Citations have exactly source ID, 1-based line number, and quote. Limits: 100 cases, 100 source IDs, 1,000 lines/source, 2,000 chars/line; safe IDs match `[A-Za-z0-9_-]{1,64}`. Duplicate JSON object keys and NaN/infinity are rejected. Each scripted attempt's input is validated structurally up front; response/citation validity is assessed when that attempt runs.

## Runtime behavior

- `--concurrency` bounds **active attempts** (1–32); semaphore acquisition is per attempt, so waiting cases do not occupy a slot. Peak active is reported.
- `--timeout` applies separately to each active attempt (finite 0.001–30 seconds). `wait_for` cancels a timed-out simulated invocation and cleans up the slot.
- `--retries` is the maximum retry count (0–3). Only scripted transient tool errors and timeouts retry. Schema and citation failures, and permanent tool errors, are terminal. If configured retries exceed fixture scripts, the **last scripted attempt is reused**.
- Cases are returned in fixture input order irrespective of completion order. Durations are wall-clock diagnostics, not benchmark results.
- Events contain only transition names, attempt numbers and safe outcome codes. Reports intentionally omit answers, source content, quotes, raw errors, and provider payloads. Case IDs remain present for correlation and may themselves identify data; use opaque IDs. Do not put real-customer information in fixtures.

This is local, deterministic simulation only: there is no API key, network call, provider payload, live model, or real-customer data. A passing result proves only the documented format and exact quote-substring checks—not that the answer is correct or supported by the quote.

## How the code works

`eval_gate/core.py` reads a regular file within a fixed byte bound and rejects duplicate keys, invalid numbers, excessive nesting and malformed fixture structure before evaluation. It does not execute commands from JSON. Each case runs a local script: `asyncio.Semaphore` limits active simulated attempts, `asyncio.wait_for` cancels an over-time invocation, and `asyncio.gather` preserves input order in results. A queued event is distinct from an active attempt. Slot cleanup uses `finally`, so cancellation cannot silently retain an occupied slot.

The timeout bounds cooperative simulated invocations, not queue waiting, the entire batch, hostile CPU work or external side effects. All input files should be trusted regular files; this is not a sandbox against hostile concurrent filesystem changes. The async `evaluate` helper expects data returned by `load_fixture` and independently validates its runtime settings. `cli.py` maps validation results to exit codes; it does not print fixture payloads. Report durations vary with the machine and scheduler.

## Publication and reuse

This is original portfolio code with synthetic fixtures and no third-party runtime dependencies or bundled third-party assets. External research and product workflows are paraphrased and linked, not copied as implementations or datasets. No open-source license has been assigned; public visibility does not grant an additional reuse license. See the [publication audit](docs/publication-audit.md) for checks and limits. Never commit personal fixtures; use the ignored `fixtures-local/` directory.
