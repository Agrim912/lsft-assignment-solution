"""
YOUR IMPLEMENTATION GOES HERE.

This is a stub so the harness runs on a fresh checkout (every prompt will FAIL until
you build the system). Replace the body of `Agent.solve`. Keep the return contract in
run.py. Use any framework/LLM you like — wire it in here.

`Tools` below is a thin recorder around tools.py: call the tools through it and your
`tool_calls` trace is populated automatically. Use it (or don't — but you must produce
an accurate trace either way).
"""

from __future__ import annotations

import time
from typing import Any

import tools as _tools


class Tools:
    """Records every tool call into a trace list. Wrap tools.py through this."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, name: str, **kwargs: Any) -> dict[str, Any]:
        fn = getattr(_tools, name)
        result = fn(**kwargs)
        ok = isinstance(result, dict) and result.get("status") == "success"
        self.calls.append({"name": name, "args": kwargs, "ok": ok})
        return result


class Agent:
    def __init__(self) -> None:
        # TODO: construct your orchestrator + sub-agents + LLM client here.
        pass

    def solve(self, prompt: str) -> dict[str, Any]:
        t0 = time.time()
        tools_rec = Tools()

        # ================= TODO: your multi-agent system =================
        # Parse intent. Resolve the model. Ground ambiguous terms. Orchestrate the
        # tools in the right order. Slim tool outputs. Ask on missing input. Fail on
        # unknown model. Never fabricate a number a tool did not return.
        #
        # Example of calling a tool through the recorder:
        #     res = tools_rec.call("list_models")
        #
        answer = "NOT IMPLEMENTED"
        asked_user = False
        failed = False
        llm_calls = 0
        prompt_tokens = 0
        completion_tokens = 0
        # =================================================================

        return {
            "answer": answer,
            "trace": {
                "tool_calls": tools_rec.calls,
                "llm_calls": llm_calls,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_s": time.time() - t0,
                "asked_user": asked_user,
                "failed": failed,
            },
        }
