"""
Entrypoint CONTRACT. Do not rename `solve`. The harness imports it from here.

Implement your multi-agent system behind `solve(prompt)`. Wire your own LLM/framework
inside `candidate_agent.py` (or wherever) and call it from here.

Return shape (required):

    {
      "answer": str,          # the final natural-language answer for the user
      "trace": {
        "tool_calls":  [ {"name": str, "args": dict, "ok": bool}, ... ],  # in call order
        "llm_calls":   int,   # number of LLM round-trips this prompt took
        "prompt_tokens":     int,   # best-effort; 0 if you truly can't measure
        "completion_tokens": int,   # best-effort
        "latency_s":   float, # wall-clock seconds
        "asked_user":  bool,  # did you stop to ask a clarifying question?
        "failed":      bool   # did you refuse / fail loudly (e.g. unknown model)?
      }
    }

Notes:
  - `tool_calls` MUST reflect real calls to functions in tools.py (record every one).
  - If you ask the user a question, set asked_user=True and put the question in `answer`.
  - If you refuse (bad/missing input), set failed=True and explain why in `answer`.
  - Accuracy of trace is graded. Do not fake it.
"""

from __future__ import annotations

from typing import Any


_AGENT: Any = None


def _get_agent() -> Any:
    """Cache one agent across prompts (builds the LangGraph + LLM client once)."""
    global _AGENT
    if _AGENT is None:
        from candidate_agent import Agent  # real-LLM LangGraph agent (regex fallback inside)

        _AGENT = Agent()
    return _AGENT


def solve(prompt: str) -> dict[str, Any]:
    return _get_agent().solve(prompt)


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "List my models."
    out = solve(q)
    print("ANSWER:\n", out["answer"])
    print("\nTRACE:\n", out["trace"])
