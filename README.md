# Lifesight — Budget-Optimisation Multi-Agent Assignment

Build a reliable multi-agent system that turns a marketer's natural-language goal into
the correct sequence of **internal tool** calls, over deliberately messy data, **without
guessing**.

- **Time:** 2–3 hours.
- **Stack:** any framework, any LLM. ADK / LangGraph / CrewAI / raw — your call.
- **Full brief:** [ASSIGNMENT.md](ASSIGNMENT.md)
- **How you're scored:** [EVALUATION.md](EVALUATION.md)

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # only if you add deps; stdlib runs as-is

python3 harness.py                        # runs the 12 golden prompts (all FAIL until you build it)
python3 run.py "Optimise my latest revenue model, moderate, $500k"   # single prompt
```

On a fresh checkout the harness prints `0/12`. Your job is to make it meaningfully green
**and** cheap (few LLM hops, small token counts) **and** honest (asks or fails instead of
guessing).

## What's in the repo

| File | What it is |
|---|---|
| `tools.py` | The internal toolbox (~13 mock tools). Faithful to real endpoints, fully offline. **Do not change its behaviour.** |
| `golden_prompts.json` | 12 prompts you must handle, with structural expectations. |
| `run.py` | The contract. Implement `solve(prompt) -> {answer, trace}`. Do not rename it. |
| `candidate_agent.py` | Where your system goes. Has a tool-call recorder to save you boilerplate. |
| `harness.py` | Runs the golden prompts, checks structure, reports hops/tokens/latency. Improving it counts. |
| `ASSIGNMENT.md` | The problem statement, requirements, and the specific hard problems. |
| `EVALUATION.md` | The scoring rubric. |

## The one-line version

The tools are messy on purpose: a ~19MB model list, a strict camelCase param, two tools
that look identical but aren't, a hard optimise→forecast ordering, and business terms that
map to multiple fields. Make an agent that **knows, asks, or fails — but never guesses** —
and prove it with the harness.

## Deliverables

1. Working code (one command runs the harness).
2. `DESIGN.md` (max 1 page): your architecture and how you handled each hard problem.
3. Your harness output (metrics) committed.

Read [ASSIGNMENT.md](ASSIGNMENT.md) next.
