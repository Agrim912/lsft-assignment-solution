# Evaluation

Total: 100 points. We care more about **reliability and judgment** than feature count.

| Dimension | Pts | What "great" looks like |
|---|---:|---|
| Correctness on golden prompts | 20 | Right answers, right tool sequences. Adversarial prompts (`g07`, `g08`) handled. |
| Zero hallucination / grounding | 20 | Never invents a field, number, or model id. Asks/fails on missing input. Ambiguous terms resolved from the real tool responses + `channel_metadata` (there is no glossary tool), not memory. |
| Tool orchestration & ambiguity | 15 | Clean sequencing and state passing. Picks `get_current_budget` over the deprecated `get_planner_budget`. Doesn't pull the 19MB list to read one model. |
| Token optimisation | 10 | Tool outputs slimmed with a clear keep/drop rationale. Context stays small even after `list_models`. |
| Latency & LLM-hop reduction | 10 | Few round-trips. Determinism where the task allows. Reported per prompt. |
| Multi-agent justification | 10 | Topology is justified. No redundant agents. Collapses to one when one fits. |
| Harness quality | 10 | Reproducible. Measures correctness signals + tokens + hops + latency. Extended beyond the starter. |
| Design note & trade-offs | 5 | Clear, honest, prioritised. Names what was cut and why. |

## How we read it

**Green flags**
- The system says "I can't do this because X" instead of guessing.
- Tool outputs are summarised before they reach the model.
- The deterministic parts are code; the LLM is only at the edges (intent + narration).
- One clean path per goal, no redundant agents, no redundant tool calls.
- The trace is honest and the harness proves the claims.

**Red flags**
- Dumps raw tool output into the prompt (watch the token column explode).
- Uses `get_planner_budget` for a current-budget question.
- Invents a model id, a field name, or a number for `g07`/`g10`.
- Guesses a default budget on `g08` instead of asking.
- Picks one meaning of "conversions" on `g09` without clarifying.
- N agents where 1 would do, or an LLM call for a deterministic step.
- A trace that doesn't match what actually ran.

## A note on the harness score

`harness.py` automates the *structural* checks (right tools, order, forbidden tools,
asked-vs-guessed, failed-vs-fabricated). A structural PASS is necessary, not sufficient —
answer correctness and grounding are judged by a human reading your `answer` strings and
`DESIGN.md`. Gaming the structural checks without a correct, grounded answer scores low.

## If you run out of time

We would rather see 6 prompts handled *reliably and cheaply*, with honest failures on the
rest, than 12 handled by a system that guesses. Prioritise accordingly, and say so in
`DESIGN.md`.
