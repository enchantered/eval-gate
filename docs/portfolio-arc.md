# A portfolio about trustworthy tool use

The portfolio's common thread is **inspect the evidence, check the output, approve consequential actions**. The owner's twelve stages guide the learning sequence; they are not twelve boxes to claim complete.

## Why evaluation comes earlier

Context Pocket made source recovery visible. Eval Gate now tests the next boundary: can a structured response be read safely, does its quoted citation exist, and do concurrent attempts fail predictably? That combines Python/async foundations, structured outputs, evaluation, small traces and input guardrails before adding more agents. Today's [research decision](2026-10-22-decision.md) explains the evidence: checkable answers matter to developers, and schema validity is not correctness.

This is a deliberate return to foundations, not a claim that every earlier LLM stage is finished. Multiple agents would multiply handoffs and obscure which boundary failed. A small offline gate gives the next single-agent workflow a useful regression contract first. The daily research/build process used parallel agents with separate research and implementation responsibilities; the shipped runtime intentionally requires no agent framework or paid provider.

## Where the existing work fits

**Return Window** demonstrates explicit user-entered state and a legacy CSV-to-calendar handoff. **Occlusion Lab** demonstrates deterministic planning and the distinction between unknown and confirmed information. Neither is being presented as an LLM system.

**Context Pocket** covers a narrow memory/retrieval concern: recover original local text with inspectable source locations. It has no embeddings, model memory, native provider JSON importer or answer generator.

**ReviewGate** explores persistent draft state, approval and audit boundaries. Its optional agent adapter has prior offline SDK compatibility tests. This is a human-review prototype, not authenticated enterprise authorization or proof-carrying security.

**Eval Gate** adds bounded async execution, strict response contracts, exact citation checks and metadata-only diagnostics. Its simulated tool is not a live LLM or a live integration with the earlier projects. The connection is an explicit output/evidence contract; a real cross-project adapter remains future work.

## How the twelve reference stages remain useful

1. **Python and async:** demonstrated here with cooperative cancellation, semaphores, ordered results and bounded retries.
2. **LLM fundamentals:** vocabulary and limits are documented; no live model quality or token/cost benchmark is claimed.
3. **Tool calling and structured output:** this milestone checks a tool-like response contract, not real model tool selection.
4. **Memory and state:** source-backed retrieval and persisted review records exist as separate prototypes; durable shared agent memory does not.
5. **Single-agent workflows:** a sensible next step is an opt-in adapter that produces this contract, with offline recorded fixtures first.
6. **Multi-agent orchestration:** defer the product runtime until single-step errors can be attributed and measured.
7. **Human-in-the-loop:** ReviewGate is the portfolio's review demonstration; model approval flags are not authenticated human approval.
8. **Evaluation and QA:** thirty-one tests and positive/negative example runs cover this milestone's explicit checks, not broad intelligence or usefulness.
9. **Observability:** local queue/start/finish/retry events and timings are implemented. Production tracing, costs, aggregation and retention are not.
10. **Security and guardrails:** bounded input, strict parsing and payload omission reduce specific risks; there is no hostile-process sandbox, intent authorization or semantic safety proof.
11. **Production deployment:** not reached. No hosted service, reliability target, incident response, tenant isolation or production rollout is claimed.
12. **Open source and portfolio:** publish a reviewed, handle-only portfolio repository after its safety gate. Public visibility is not an open-source license; licensing remains explicit rather than assumed.

## What would justify the next change

A real user or integration should drive the next milestone, not a new repository quota. Test one consenting developer's authorized tool-output samples and one ordinary user's source-retrieval task. If fixed schema/citation rules miss the failures they care about, improve the contract or add a calibrated human rubric before buying model-judge calls. Only introduce orchestration when multiple independently useful steps require it.

The existing randomized 0–72-hour maintenance cadence remains separately owned. No local per-project due ledger was available in this run, so due status is unknown; no replacement timer or filler maintenance commit was created. Earlier repository histories contain non-handle author metadata. They were not imported, rewritten or republished here; this repository starts with handle-only authorship.
