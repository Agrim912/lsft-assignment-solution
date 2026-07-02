# Assignment: a reliable budget-optimisation multi-agent system

## Context

We build marketing-measurement agents over messy internal APIs. This assignment is a
scaled-down version of the same problem, with the same traps we hit in production.

A marketer types a goal in plain language. Your system orchestrates a set of **internal
tools** (in `tools.py`) to produce a correct, grounded answer. The tools are realistic:
large nested responses, overlapping tools that look interchangeable, strict parameter
formats, hard ordering dependencies, ambiguous business terms, and required inputs the
user often omits.

We are **not** testing whether you can call an LLM. We are testing whether you can make a
multi-agent system **reliable, cheap, fast, and honest** on real-world-messy tools.

## The core principle we're testing

> The system must **know, ask, or fail. Never guess.**

A slightly-less-featureful system that is provably honest and cheap beats a feature-complete
one that occasionally hands the user a confident wrong number.

## What to build

Implement `solve(prompt) -> {answer, trace}` in `run.py` (via `candidate_agent.py`), backed
by a multi-agent system of your design. The `trace` must accurately record every tool call,
LLM-call count, tokens, latency, and whether you asked / failed. See `run.py` for the exact
shape.

Handle the 12 prompts in `golden_prompts.json`.

## The hard problems (this is the actual test)

Address each. Call out in `DESIGN.md` how you did it.

1. **Tool orchestration.** Correct sequencing and state passing. `run_default_optimise`
   must precede `run_constrained_optimise`, which must precede `forecast_revenue`. Get the
   order wrong and the tools error (by design). Compare needs scenarios saved first.

2. **Ambiguity across tools.** `get_current_budget` and `get_planner_budget` look
   interchangeable. One is the canonical current-budget tool; the other is a deprecated v1
   twin with a stale, different shape and a snake_case param. Using the wrong one is a
   correctness bug. Resolve deterministically. Same idea for `list_models` vs
   `get_model_details` — don't pull the 19MB list to read one model's fields.

3. **Multi-agent design.** If you use multiple agents, justify why more than one is needed.
   Two agents that can both "do the optimise" is a smell, not a feature. Show you route
   cleanly and collapse to fewer agents when one suffices.

4. **Token optimisation.** `list_models` returns ~220 fat objects (~800KB). Dumping that
   into context will wreck you. Show what you keep, what you drop, and why. Same for the
   big `referencePoint` in `get_current_budget` and the `simulatedResponseCurveList` in the
   optimise result.

5. **Latency and fewer LLM hops.** Minimise round-trips. A deterministic step wrapped in an
   LLM call is a liability. Show where you took the model out of the loop. The harness
   reports hops and latency per prompt.

6. **Zero hallucination.** Never emit a field, number, or model id a tool did not return.
   On a missing required input (no budget, no model), **ask or fail loudly**. On an unknown
   model id, fail — do not invent. The adversarial prompts (`g07`, `g08`) exist to catch this.

7. **Grounding (no lookup crutch).** There is deliberately **no glossary / term→field
   tool**. Map the user's words ("revenue", "spend", "conversions") to the real fields
   yourself, from the actual tool responses and `channel_metadata`. Your strategy, your
   call. Detect when a term is ambiguous ("conversions" could mean several things, and the
   latest model may not even measure it) and clarify instead of picking one. "locked
   channel" has a specific definition (`currentBudgetData.spend == 0`, per
   `channel_metadata`). Never invent a field name or a metric a model does not produce.

8. **Param correctness.** `get_current_budget` requires camelCase `mmmRequestId`. A
   snake_case attempt errors. If your first attempt is wrong, recover gracefully — do not
   surface a raw 400 to the user, and do not give up.

9. **Internal tools only.** No web, no external calls. The model reasons; the tools are the
   only source of truth.

10. **The harness.** Ship a reproducible eval that scores correctness signals AND the
    efficiency metrics. Improving the starter harness (grounding checks, token budgets,
    N-run flakiness, per-prompt cost) is explicitly rewarded.

## Rules

- Do not change the behaviour of `tools.py` (you may wrap, cache, slim it).
- Any LLM provider. **No API key?** A stub/fake LLM that demonstrates the orchestration and
  the harness is acceptable and will be judged on architecture and reliability, not model IQ.
- Commit your trace/metrics output.
- `solve` must not fake its trace. Trace accuracy is graded.

## Time guidance (you will not finish everything — prioritise)

- **~30 min** — read `tools.py`, find the traps (the fat list, camelCase, the deprecated
  twin, the ordering dependency, the ambiguous terms).
- **~90 min** — core orchestration + grounding + output slimming + get the harness green on
  the straightforward prompts.
- **~30 min** — adversarial handling (ask/fail on `g07`–`g10`) + write `DESIGN.md`.
- **Stretch** — multi-scenario compare, a router that skips the LLM for trivial prompts,
  caching, token budgets in the harness.

## Out of scope (do not spend time here)

- A UI. CLI / JSON output is fine.
- Real API integration, auth, deployment.
- Fine-tuning, a vector DB, RAG infra.
- Prompt-golfing one specific model.

## Deliverables

1. Runnable code, one command runs the harness.
2. `DESIGN.md` (max 1 page): architecture, agent topology and why, and one line per hard
   problem above. List your trade-offs and what you'd do with more time.
3. Harness output committed.

## Submission

A repo or zip: code, `DESIGN.md`, harness output. One command to reproduce.
