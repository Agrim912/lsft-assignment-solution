"""
Evaluation harness. Runs the 12 golden prompts through your `solve` and reports:
  - structural checks it can automate (right tools, right order, forbidden tools,
    asked-vs-guessed, failed-vs-fabricated)
  - efficiency metrics (LLM hops, tokens, latency)

Run:  python harness.py

This is a STARTER harness. Improving it counts (see EVALUATION.md — "Harness quality").
Add checks you think matter: grounding assertions, token budgets, regression snapshots,
per-prompt cost, flakiness over N runs, etc.

The harness resolves `{MODEL_ID}` in prompts to a real, recent Revenue model id so you
have a concrete id to work with.
"""

from __future__ import annotations

import json
import time
from typing import Any

import tools
from run import solve


def _recent_revenue_model_id() -> str:
    revenue = [m for m in tools.list_models()["data"]
               if m["outcomeKPI"] == "Revenue" and m["modelStatus"] == "Success"]
    revenue.sort(key=lambda m: m["createdAt"]["seconds"], reverse=True)
    return str(revenue[0]["id"])


def _check(expects: dict[str, Any], trace: dict[str, Any]) -> list[str]:
    """Return a list of failure strings ([] == all structural checks passed)."""
    fails: list[str] = []
    names = [c["name"] for c in trace.get("tool_calls", [])]

    for t in expects.get("must_call", []):
        if t not in names:
            fails.append(f"missing tool {t}")
    for t in expects.get("must_not_call", []):
        if t in names:
            fails.append(f"called forbidden tool {t}")
    for before, after in expects.get("order", []):
        if before in names and after in names and names.index(before) > names.index(after):
            fails.append(f"order: {before} must precede {after}")
    if expects.get("expect_ask") and not trace.get("asked_user"):
        fails.append("expected a clarifying question (asked_user=True)")
    if expects.get("expect_fail") and not trace.get("failed"):
        fails.append("expected a loud failure (failed=True)")
    return fails


def main() -> None:
    spec = json.load(open("golden_prompts.json"))
    model_id = _recent_revenue_model_id()
    rows = []
    for p in spec["prompts"]:
        tools.reset_session()
        prompt = p["prompt"].replace("{MODEL_ID}", model_id)
        t0 = time.time()
        try:
            out = solve(prompt)
            trace = out.get("trace", {})
        except Exception as e:  # a crash is a hard fail
            trace = {"tool_calls": [], "llm_calls": 0, "latency_s": time.time() - t0,
                     "asked_user": False, "failed": False, "_crash": str(e)}
            out = {"answer": f"CRASH: {e}"}
        fails = _check(p.get("expects", {}), trace)
        rows.append({
            "id": p["id"],
            "status": "PASS" if not fails and "_crash" not in trace else "FAIL",
            "hops": trace.get("llm_calls", "?"),
            "tokens": trace.get("prompt_tokens", 0) + trace.get("completion_tokens", 0),
            "latency_s": round(trace.get("latency_s", 0.0), 2),
            "issues": "; ".join(fails) or trace.get("_crash", ""),
        })

    # ---- report ----
    print(f"\nGolden model id used for {{MODEL_ID}}: {model_id}\n")
    print(f"{'id':<28}{'status':<8}{'hops':<6}{'tokens':<9}{'lat(s)':<8}issues")
    print("-" * 100)
    for r in rows:
        print(f"{r['id']:<28}{r['status']:<8}{str(r['hops']):<6}{str(r['tokens']):<9}{str(r['latency_s']):<8}{r['issues']}")
    passed = sum(1 for r in rows if r["status"] == "PASS")
    tot_tokens = sum(r["tokens"] for r in rows if isinstance(r["tokens"], int))
    tot_hops = sum(r["hops"] for r in rows if isinstance(r["hops"], int))
    print("-" * 100)
    print(f"Structural checks passed: {passed}/{len(rows)}  |  total LLM hops: {tot_hops}  |  total tokens: {tot_tokens}")
    print("\nNote: structural PASS != correct answer. Answer correctness + grounding are judged separately.")


if __name__ == "__main__":
    main()
