"""
Budget-optimisation agent — REAL LLM (OpenAI via LangGraph).

`Agent.solve` runs a small LangGraph pipeline:

    START -> router (LLM) -> execute (deterministic handlers) -> END

The LLM does the one thing it beats a regex at: turning messy natural language into a
structured `Intent` (which action, which slots). Everything after that — tool ordering,
camelCase params, output slimming, grounding, and the "know / ask / fail, never guess"
guardrail — stays deterministic Python. That keeps us at a single LLM hop per prompt,
keeps tokens tiny, and makes hallucination structurally impossible: the model picks an
action, it never emits a number or a model id that a tool did not return.

If the LLM is unavailable (no OPENAI_API_KEY, no network, or bad output), the router
falls back to `_parse_intent`, a deterministic regex parser, so the harness still runs
fully offline.

`Tools` is a thin recorder around tools.py: every call through it is added to the
`tool_calls` trace automatically.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Optional, TypedDict

import tools as _tools

try:  # optional deps — real LLM path. Absent => deterministic fallback still works.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


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


def _slim_model_list(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract only essential fields from the fat model objects."""
    slimmed = []
    for m in models:
        slimmed.append({
            "id": m["id"],
            "modelName": m["modelName"],
            "outcomeKPI": m["outcomeKPI"],
            "modelStatus": m["modelStatus"],
            "createdAt": m["createdAt"],
            "country": m["country"],
            "currency": m["currency"],
        })
    slimmed.sort(key=lambda x: x["createdAt"]["seconds"], reverse=True)
    return slimmed


def _slim_current_budget(data: dict[str, Any]) -> dict[str, Any]:
    """Drop the huge referencePoint decomposition."""
    return {
        "startDate": data.get("startDate"),
        "endDate": data.get("endDate"),
        "mmmCurrentBudgetResponseList": data.get("mmmCurrentBudgetResponseList", []),
    }


def _slim_optimise_result(data: dict[str, Any]) -> dict[str, Any]:
    """Drop the simulatedResponseCurveList from each row; keep the summary."""
    result = {}
    for date_range, range_data in data.get("dateRangeToResponseMap", {}).items():
        rows = range_data.get("mmmBudgetOptimisationResponseList", [])
        slimmed_rows = []
        for row in rows:
            slimmed_row = {
                "platformName": row.get("platformName"),
                "currentBudgetData": row.get("currentBudgetData"),
                "optimisedBudgetData": row.get("optimisedBudgetData"),
            }
            slimmed_rows.append(slimmed_row)
        result[date_range] = {"mmmBudgetOptimisationResponseList": slimmed_rows}
    return {"dateRangeToResponseMap": result}


def _parse_amount(text: str) -> float | None:
    """Parse a monetary amount like $500k, $1M, $1,000,000."""
    match = re.search(r"\$?([\d,]+(?:\.\d+)?)\s*([kKmM])?", text)
    if match:
        amount_str = match.group(1).replace(",", "")
        suffix = (match.group(2) or "").lower()
        try:
            amount = float(amount_str)
            if suffix == "k":
                amount *= 1000
            elif suffix == "m":
                amount *= 1000000
            return amount
        except ValueError:
            pass
    return None


def _parse_intent(prompt: str) -> dict[str, Any]:
    """Deterministic rule-based intent parser — the OFFLINE FALLBACK for the LLM router.

    Used only when the LLM is unavailable (no key/network) or returns nothing usable, so
    the harness still runs with zero LLM hops. The default path is the LLM router below.
    """
    lower = prompt.lower()

    # Detect action (in priority order to avoid conflicts)
    action = None
    if "list" in lower and "model" in lower:
        action = "list_models"
    elif "locked" in lower and "channel" in lower:
        action = "locked_channels"
    elif "current budget" in lower or ("what" in lower and "current" in lower and "budget" in lower):
        action = "get_current_budget"
    elif "compare" in lower and ("vs" in lower or "versus" in lower or "which wins" in lower):
        action = "compare_scenarios"
    elif "how much budget" in lower and ("hit" in lower or "reach" in lower):
        action = "target_kpi"
    elif ("optimise" in lower or "optimize" in lower):
        action = "optimise"
    elif ("what revenue" in lower or "would deliver" in lower) and ("model" in lower or "quarter" in lower):
        action = "forecast"
    elif "forecast" in lower:
        action = "forecast"
    elif "conversions" in lower:
        action = "ambiguous"
    elif "installs" in lower:
        action = "ambiguous"
    else:
        action = "unknown"

    # Extract model ID
    model_id = None
    model_match = re.search(r"model\s+(\d+)", lower)
    if model_match:
        model_id = model_match.group(1)
    elif "latest" in lower or "recent" in lower or "most recent" in lower:
        model_id = "latest"

    # Extract all money amounts from the prompt (in order)
    amounts = []
    for match in re.finditer(r"\$\s*([0-9,]+(?:\.[0-9]+)?)\s*([kKmM])?", prompt):
        amount_str = match.group(1).replace(",", "")
        suffix = (match.group(2) or "").lower()
        try:
            amount = float(amount_str)
            if suffix == "k":
                amount *= 1000
            elif suffix == "m":
                amount *= 1000000
            amounts.append(amount)
        except ValueError:
            pass

    # Extract the ambiguous metric term (if any)
    metric = None
    if "conversions" in lower:
        metric = "conversions"
    elif "installs" in lower:
        metric = "installs"

    # Extract constraint type
    constraint_type = None
    if "aggressive" in lower:
        constraint_type = "Aggressive"
    elif "moderate" in lower:
        constraint_type = "Moderate"
    elif "conservative" in lower:
        constraint_type = "Conservative"
    elif "current" in lower and "constraints" in lower:
        constraint_type = "Current"

    # Extract time period
    time_period = "quarter"
    if "week" in lower:
        time_period = "week"
    elif "month" in lower:
        time_period = "month"
    elif "quarter" in lower:
        time_period = "quarter"

    # Assign amounts based on action type
    budget = None
    target_revenue = None
    budgets = None

    if action == "compare_scenarios":
        budgets = amounts
    elif action == "target_kpi":
        target_revenue = amounts[0] if amounts else None
    elif action in ("optimise", "forecast"):
        budget = amounts[0] if amounts else None

    # Build result, then apply the shared "never guess" guardrail.
    result = {
        "action": action,
        "model_id": model_id,
        "budget": budget,
        "target_revenue": target_revenue,
        "budgets": budgets,
        "constraint_type": constraint_type,
        "time_period": time_period,
        "metric": metric,
        "reason": None,
    }

    return _finalize_intent(result)


def _finalize_intent(result: dict[str, Any]) -> dict[str, Any]:
    """Enforce 'know, ask, or fail — never guess' on an intent dict.

    Shared by the deterministic regex parser and the LLM router: if an action's
    required slots are absent, downgrade to `missing_input` and name exactly what's
    missing. This is the guardrail — even if the LLM tries to invent a budget or a
    model id, the required slots are re-validated here before any tool runs.
    """
    action = result.get("action") or "unknown"
    missing_fields: list[str] = []

    if action in ("optimise", "forecast"):
        if result.get("model_id") is None:
            missing_fields.append("which model to use")
        if result.get("budget") is None:
            missing_fields.append("a total budget amount")
        if missing_fields:
            action = "missing_input"
    elif action == "target_kpi":
        if result.get("model_id") is None:
            missing_fields.append("which model to use")
        if result.get("target_revenue") is None:
            missing_fields.append("a target revenue amount")
        if missing_fields:
            action = "missing_input"
    elif action == "compare_scenarios":
        if len(result.get("budgets") or []) < 2:
            missing_fields.append("at least two budget amounts to compare")
            action = "missing_input"
    elif action == "unknown":
        action = "missing_input"

    reason = result.get("reason")
    if action == "missing_input" and not reason:
        if missing_fields:
            reason = "I need " + " and ".join(missing_fields) + " to proceed."
        else:
            reason = "Could you clarify what you'd like me to do?"

    result["action"] = action
    result["reason"] = reason
    return result


# =========================================================================== #
# LLM router — natural language -> structured Intent (the only LLM hop).
# =========================================================================== #
_MODEL_NAME = os.getenv("LLM_MODEL", "gpt-4o-mini")
_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0") or 0)

_ROUTER_SYSTEM_PROMPT = """You are the ROUTER for a marketing budget-optimisation agent. \
Your ONLY job is to classify one user message into a structured Intent. You do NOT call \
tools and you do NOT answer the question yourself.

Actions:
- list_models: user wants to see / list their models.
- get_current_budget: user asks for the CURRENT budget of a model.
- locked_channels: user asks which channels are locked.
- optimise: user wants to optimise / reallocate a budget (needs a model and a budget).
- forecast: user asks what revenue a given budget would deliver (needs a model and a budget).
- compare_scenarios: user wants to compare two or more budget amounts and pick a winner.
- target_kpi: user asks how much budget is needed to HIT a target revenue.
- ambiguous: user asks for a metric/term not clearly defined by the tools (e.g. \
"conversions", "installs"); set `metric` to their exact word.
- unknown: none of the above.

Rules (critical — we must never guess):
- Set model_id only if explicitly present. If they say "latest"/"recent"/"most recent \
revenue model", set model_id to the string "latest". Otherwise null. NEVER invent a numeric id.
- Parse dollar amounts exactly ($500k -> 500000, $1M -> 1000000, $2M -> 2000000). If no \
amount is present, leave the slot null/empty — do not assume a default.
- If a required amount or model is missing, still pick the base action and leave the \
missing slot null; a downstream guardrail will ask the user.
- constraint_type only if the user names one (aggressive/moderate/conservative/current)."""


def _build_intent_model():
    """Pydantic schema for structured output (built lazily so import never needs pydantic)."""
    from pydantic import BaseModel, Field
    from typing_extensions import Literal

    class Intent(BaseModel):
        action: Literal[
            "list_models", "get_current_budget", "locked_channels", "optimise",
            "forecast", "compare_scenarios", "target_kpi", "ambiguous", "unknown",
        ] = Field(description="The single best-matching action.")
        model_id: Optional[str] = Field(
            default=None,
            description="Numeric model id if given; 'latest' if they said latest/recent; else null.",
        )
        budget: Optional[float] = Field(default=None, description="Total budget in dollars; null if absent.")
        target_revenue: Optional[float] = Field(default=None, description="Target revenue in dollars; null if absent.")
        budgets: list[float] = Field(default_factory=list, description="All budgets to compare, in dollars.")
        constraint_type: Optional[Literal["Current", "Conservative", "Moderate", "Aggressive"]] = Field(default=None)
        time_period: Literal["week", "month", "quarter"] = Field(default="quarter")
        metric: Optional[str] = Field(default=None, description="Raw term for an ambiguous metric request.")

    return Intent


class _AgentState(TypedDict, total=False):
    prompt: str
    intent: dict[str, Any]
    answer: str
    asked_user: bool
    failed: bool
    llm_calls: int
    prompt_tokens: int
    completion_tokens: int
    agent: Any
    tools: Any


class Agent:
    """Real-LLM agent: a LangGraph pipeline (LLM router -> deterministic execution)."""

    def __init__(self) -> None:
        self._llm = None
        self._intent_model = None
        self._graph = self._build_graph()

    # ---- LLM client (lazy, cached) --------------------------------------- #
    def _get_llm(self) -> Any:
        if self._llm is None:
            from langchain_openai import ChatOpenAI

            self._llm = ChatOpenAI(model=_MODEL_NAME, temperature=_TEMPERATURE)
            self._intent_model = _build_intent_model()
        return self._llm

    # ---- Graph ----------------------------------------------------------- #
    def _build_graph(self) -> Any:
        """Compile the LangGraph. Returns None if LangGraph isn't installed (fallback path)."""
        try:
            from langgraph.graph import END, START, StateGraph
        except Exception:
            return None
        g = StateGraph(_AgentState)
        g.add_node("router", self._router_node)
        g.add_node("execute", self._execute_node)
        g.add_edge(START, "router")
        g.add_edge("router", "execute")
        g.add_edge("execute", END)
        return g.compile()

    def _router_node(self, state: _AgentState) -> dict[str, Any]:
        """LLM node: prompt -> structured Intent. Falls back to the regex parser on any error."""
        prompt = state["prompt"]
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            structured = self._get_llm().with_structured_output(self._intent_model, include_raw=True)
            res = structured.invoke([SystemMessage(_ROUTER_SYSTEM_PROMPT), HumanMessage(prompt)])
            parsed = res["parsed"]
            if parsed is None:
                raise ValueError("structured output returned no parse")
            usage = getattr(res.get("raw"), "usage_metadata", None) or {}
            intent = parsed.model_dump()
            intent["reason"] = None
            intent = _finalize_intent(intent)
            return {
                "intent": intent,
                "llm_calls": 1,
                "prompt_tokens": int(usage.get("input_tokens", 0) or 0),
                "completion_tokens": int(usage.get("output_tokens", 0) or 0),
            }
        except Exception:
            intent = _parse_intent(prompt)  # deterministic fallback (already finalized)
            return {"intent": intent, "llm_calls": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def _execute_node(self, state: _AgentState) -> dict[str, Any]:
        """Deterministic node: run the grounded handlers for the routed intent."""
        answer, asked_user, failed = self._route_intent(state["intent"], state["prompt"], state["tools"])
        return {"answer": answer, "asked_user": asked_user, "failed": failed}

    # ---- Entry point ----------------------------------------------------- #
    def solve(self, prompt: str) -> dict[str, Any]:
        t0 = time.time()
        tools_rec = Tools()
        answer, asked_user, failed = "", False, False
        llm_calls = prompt_tokens = completion_tokens = 0

        try:
            if self._graph is not None:
                final = self._graph.invoke({"prompt": prompt, "agent": self, "tools": tools_rec})
                answer = final.get("answer", "")
                asked_user = bool(final.get("asked_user", False))
                failed = bool(final.get("failed", False))
                llm_calls = int(final.get("llm_calls", 0))
                prompt_tokens = int(final.get("prompt_tokens", 0))
                completion_tokens = int(final.get("completion_tokens", 0))
            else:  # LangGraph unavailable — deterministic path
                intent = _parse_intent(prompt)
                answer, asked_user, failed = self._route_intent(intent, prompt, tools_rec)
        except Exception as e:
            failed = True
            answer = f"System error: {str(e)}"

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

    def _route_intent(
        self, intent: dict[str, Any], prompt: str, tools_rec: Tools
    ) -> tuple[str, bool, bool]:
        """Route intent to appropriate action."""
        action = intent.get("action", "").lower().strip()

        if action == "missing_input":
            return (f"I need more information: {intent.get('reason', 'Please provide required details.')}", True, False)

        if action == "ambiguous":
            # Ground the ambiguity in the model's ACTUAL outcomeKPI. Resolve the model
            # first (including "latest"), read its KPI, and only then decide how to
            # phrase the clarification. Never invent a metric value.
            metric = intent.get("metric") or "that metric"
            model_id = intent.get("model_id")
            if not model_id or model_id == "latest":
                model_id = self._resolve_latest_model(tools_rec)

            model_kpi = None
            if model_id:
                res = tools_rec.call("get_model_details", mmmRequestId=str(model_id))
                if res["status"] == "success":
                    model_kpi = res["data"].get("outcomeKPI")

            if model_kpi and metric.lower() not in model_kpi.lower():
                reason = (
                    f"this model's outcome KPI is '{model_kpi}', not '{metric}'. "
                    f"There's no glossary mapping '{metric}' to a field, so I won't "
                    f"guess a number - could you clarify exactly what you'd like to see?"
                )
            else:
                reason = (
                    f"'{metric}' is ambiguous and there's no glossary tool to resolve "
                    f"it to a concrete field. Could you clarify which metric you mean?"
                )
            return (f"I need clarification: {reason}", True, False)

        if action == "list_models":
            return self._handle_list_models(tools_rec)

        if action == "get_current_budget":
            model_id = intent.get("model_id")
            if not model_id or model_id == "latest":
                model_id = self._resolve_latest_model(tools_rec)
            if not model_id:
                return ("Could not determine which model to check.", True, False)
            return self._handle_current_budget(model_id, tools_rec)

        if action == "locked_channels":
            model_id = intent.get("model_id")
            if not model_id or model_id == "latest":
                model_id = self._resolve_latest_model(tools_rec)
            if not model_id:
                return ("Could not determine which model to check.", True, False)
            return self._handle_locked_channels(model_id, tools_rec)

        if action == "optimise":
            return self._handle_optimise(intent, prompt, tools_rec)

        if action == "forecast":
            return self._handle_forecast(intent, tools_rec)

        if action == "compare_scenarios":
            return self._handle_compare_scenarios(intent, tools_rec)

        if action == "target_kpi":
            return self._handle_target_kpi(intent, tools_rec)

        return ("I'm not sure how to handle this request.", False, False)

    def _resolve_latest_model(self, tools_rec: Tools) -> str | None:
        """Find the latest successful Revenue model."""
        res = tools_rec.call("list_models")
        if res["status"] != "success":
            return None
        revenue = [
            m for m in res["data"]
            if m["outcomeKPI"] == "Revenue" and m["modelStatus"] == "Success"
        ]
        if not revenue:
            return None
        revenue.sort(key=lambda m: m["createdAt"]["seconds"], reverse=True)
        return str(revenue[0]["id"])

    def _handle_list_models(self, tools_rec: Tools) -> tuple[str, bool, bool]:
        """Handle listing models."""
        res = tools_rec.call("list_models")
        if res["status"] != "success":
            return (f"Failed to list models: {res.get('error_message')}", False, True)
        models = _slim_model_list(res["data"])
        answer = f"You have {len(models)} models. Your 5 newest:\n"
        for m in models[:5]:
            status = "[OK]" if m["modelStatus"] == "Success" else "[FAIL]"
            answer += f"  {status} {m['modelName']} (KPI: {m['outcomeKPI']}, {m['country']})\n"
        return (answer, False, False)

    def _handle_current_budget(self, model_id: str, tools_rec: Tools) -> tuple[str, bool, bool]:
        """Handle getting current budget."""
        res = tools_rec.call("get_current_budget", mmmRequestId=str(model_id))
        if res["status"] != "success":
            return (f"Failed to get current budget: {res.get('error_message')}", False, True)
        data = _slim_current_budget(res["data"])
        answer = f"Current budget for model {model_id}:\n"
        for item in data.get("mmmCurrentBudgetResponseList", []):
            answer += f"  {item['timePeriod']}: ${item['budget']:,.0f}\n"
        return (answer, False, False)

    def _handle_locked_channels(self, model_id: str, tools_rec: Tools) -> tuple[str, bool, bool]:
        """Handle identifying locked channels.

        Grounded in channel_metadata: "a channel with currentBudgetData.spend == 0 is LOCKED"
        """
        # Get channel metadata to ground the definition
        meta_res = tools_rec.call("channel_metadata")
        if meta_res["status"] != "success":
            return ("Failed to get channel metadata", False, True)

        # Get current budget to see actual spend per channel
        # Note: need to run optimisation to get per-channel breakdown
        default_res = tools_rec.call("run_default_optimise", mmmRequestId=str(model_id))
        if default_res["status"] != "success":
            return (f"Failed to get baseline: {default_res.get('error_message')}", False, True)

        constrained_res = tools_rec.call(
            "run_constrained_optimise",
            mmmRequestId=str(model_id),
            totalBudget=1000.0,
            constraintType=2,
        )
        if constrained_res["status"] != "success":
            return (f"Failed to get channel data: {constrained_res.get('error_message')}", False, True)

        # Extract per-channel data
        rows = (
            constrained_res["data"]
            .get("dateRangeToResponseMap", {})
            .get("aggregated_aggregated", {})
            .get("mmmBudgetOptimisationResponseList", [])
        )

        # Find locked channels (spend == 0 per metadata rule)
        locked_channels = []
        all_channels = []
        for row in rows:
            platform = row.get("platformName", "Unknown")
            if platform == "All Platforms":
                continue
            spend = row.get("currentBudgetData", {}).get("spend", 0)
            all_channels.append((platform, spend))
            if spend == 0:
                locked_channels.append(platform)

        if locked_channels:
            answer = f"Locked channels (spend = $0, per channel_metadata rule): {', '.join(locked_channels)}"
        else:
            answer = "No locked channels. All channels have non-zero current spend."

        return (answer, False, False)

    def _handle_optimise(self, intent: dict[str, Any], prompt: str, tools_rec: Tools) -> tuple[str, bool, bool]:
        """Handle budget optimisation."""
        model_id = intent.get("model_id")
        budget = intent.get("budget")

        if not model_id or model_id == "latest":
            model_id = self._resolve_latest_model(tools_rec)
        if not model_id or budget is None:
            missing = []
            if not model_id:
                missing.append("model")
            if budget is None:
                missing.append("budget")
            return (f"I need your {' and '.join(missing)}. Could you please provide?", True, False)

        constraint_type = intent.get("constraint_type", "Moderate")
        time_period = intent.get("time_period", "quarter")

        constraint_map = {"Current": 0, "Conservative": 1, "Moderate": 2, "Aggressive": 3}
        constraint_int = constraint_map.get(constraint_type, 2)

        # Execute optimisation sequence
        default_res = tools_rec.call("run_default_optimise", mmmRequestId=str(model_id), timePeriod=time_period)
        if default_res["status"] != "success":
            return (f"Failed to optimise: {default_res.get('error_message')}", False, True)

        constrained_res = tools_rec.call(
            "run_constrained_optimise",
            mmmRequestId=str(model_id),
            totalBudget=float(budget),
            constraintType=constraint_int,
        )
        if constrained_res["status"] != "success":
            return (f"Failed to optimise: {constrained_res.get('error_message')}", False, True)

        opt_data = _slim_optimise_result(constrained_res["data"])
        rows = opt_data.get("dateRangeToResponseMap", {}).get("aggregated_aggregated", {}).get("mmmBudgetOptimisationResponseList", [])
        all_platforms = next((r for r in rows if r.get("platformName") == "All Platforms"), {})

        opt_spend = all_platforms.get("optimisedBudgetData", {}).get("spend", 0)
        opt_revenue = all_platforms.get("optimisedBudgetData", {}).get("response", 0)
        roas = opt_revenue / float(budget) if float(budget) > 0 else 0

        answer = (
            f"Optimisation with {constraint_type} constraints:\n"
            f"  Budget: ${float(budget):,.0f}\n"
            f"  Optimised spend: ${opt_spend:,.0f}\n"
            f"  Expected revenue: ${opt_revenue:,.0f}\n"
            f"  ROAS: {roas:.2f}x"
        )

        if "forecast" in prompt.lower():
            forecast_res = tools_rec.call("forecast_revenue", mmmRequestId=str(model_id))
            if forecast_res["status"] == "success":
                total_forecast = forecast_res["data"].get("totalForecastRevenue", 0)
                answer += f"\n  Forecast: ${total_forecast:,.0f}"

        return (answer, False, False)

    def _handle_forecast(self, intent: dict[str, Any], tools_rec: Tools) -> tuple[str, bool, bool]:
        """Handle forecast query."""
        model_id = intent.get("model_id")
        budget = intent.get("budget")

        if not model_id or model_id == "latest":
            model_id = self._resolve_latest_model(tools_rec)
        if not model_id or budget is None:
            return ("I need the model ID and budget amount.", True, False)

        # Run optimisation first (required for forecast)
        default_res = tools_rec.call("run_default_optimise", mmmRequestId=str(model_id), timePeriod="quarter")
        if default_res["status"] != "success":
            return (f"Failed: {default_res.get('error_message')}", False, True)

        constrained_res = tools_rec.call(
            "run_constrained_optimise",
            mmmRequestId=str(model_id),
            totalBudget=float(budget),
            constraintType=2,
        )
        if constrained_res["status"] != "success":
            return (f"Failed: {constrained_res.get('error_message')}", False, True)

        # Run forecast
        forecast_res = tools_rec.call("forecast_revenue", mmmRequestId=str(model_id))
        if forecast_res["status"] != "success":
            return (f"Failed to forecast: {forecast_res.get('error_message')}", False, True)

        total_forecast = forecast_res["data"].get("totalForecastRevenue", 0)
        answer = f"With ${float(budget):,.0f} budget, you would deliver ${total_forecast:,.0f} in revenue next quarter."
        return (answer, False, False)

    def _handle_compare_scenarios(self, intent: dict[str, Any], tools_rec: Tools) -> tuple[str, bool, bool]:
        """Handle comparing multiple budget scenarios."""
        model_id = intent.get("model_id")
        budgets = intent.get("budgets", [])

        if not model_id or model_id == "latest":
            model_id = self._resolve_latest_model(tools_rec)
        if not model_id or len(budgets) < 2:
            return ("I need the model ID and at least two budget amounts to compare.", True, False)

        results = {}
        for idx, budget in enumerate(budgets):
            label = f"scenario_{idx}"

            # Run optimisation for this budget
            default_res = tools_rec.call("run_default_optimise", mmmRequestId=str(model_id), timePeriod="quarter")
            if default_res["status"] != "success":
                continue

            constrained_res = tools_rec.call(
                "run_constrained_optimise",
                mmmRequestId=str(model_id),
                totalBudget=float(budget),
                constraintType=2,
            )
            if constrained_res["status"] != "success":
                continue

            # Save scenario
            save_res = tools_rec.call("save_scenario", label=label)
            if save_res["status"] == "success":
                results[label] = budget

        if not results:
            return ("Failed to run scenarios.", False, True)

        # Compare saved scenarios
        compare_res = tools_rec.call("compare_scenarios", labels=list(results.keys()))
        if compare_res["status"] != "success":
            return (f"Failed to compare: {compare_res.get('error_message')}", False, True)

        # Extract and format results
        scenarios = compare_res["data"].get("scenarios", {})
        answer = "Scenario Comparison:\n"
        best_scenario = None
        best_revenue = 0

        for label, scenario_data in scenarios.items():
            budget_val = scenario_data.get("total_budget", 0)
            revenue = scenario_data.get("optimised_revenue", 0)
            roas = scenario_data.get("roas", 0)
            answer += f"  ${budget_val:,.0f}: ${revenue:,.0f} revenue (ROAS {roas:.2f}x)\n"

            if revenue > best_revenue:
                best_revenue = revenue
                best_scenario = budget_val

        if best_scenario:
            answer += f"\nBest option: ${best_scenario:,.0f} delivers the highest revenue."
        return (answer, False, False)

    def _handle_target_kpi(self, intent: dict[str, Any], tools_rec: Tools) -> tuple[str, bool, bool]:
        """Handle target KPI calculation."""
        model_id = intent.get("model_id")
        target_revenue = intent.get("target_revenue")

        if not model_id or model_id == "latest":
            model_id = self._resolve_latest_model(tools_rec)
        if not model_id or target_revenue is None:
            return ("I need the model ID and target revenue amount.", True, False)

        input_res = tools_rec.call("get_mmm_input", mmmRequestId=str(model_id))
        if input_res["status"] != "success":
            return (f"Failed to get current revenue: {input_res.get('error_message')}", False, True)

        current_revenue = sum(input_res["data"]["kpi"][0]["values"])

        default_res = tools_rec.call("run_default_optimise", mmmRequestId=str(model_id))
        if default_res["status"] != "success":
            return ("Failed to calculate", False, True)

        constrained_res = tools_rec.call(
            "run_constrained_optimise",
            mmmRequestId=str(model_id),
            totalBudget=1000.0,
            constraintType=2,
        )
        if constrained_res["status"] != "success":
            return ("Failed to calculate", False, True)

        rows = constrained_res["data"].get("dateRangeToResponseMap", {}).get("aggregated_aggregated", {}).get("mmmBudgetOptimisationResponseList", [])
        all_platforms = next((r for r in rows if r.get("platformName") == "All Platforms"), {})
        all_platform_revenue = all_platforms.get("optimisedBudgetData", {}).get("response", 0)

        calc_res = tools_rec.call(
            "calculate_target_budget",
            target_revenue=float(target_revenue),
            current_revenue=float(current_revenue),
            all_platform_revenue=float(all_platform_revenue),
        )
        if calc_res["status"] != "success":
            return ("Calculation failed", False, True)

        required_budget = calc_res["data"]["required_budget"]
        answer = (
            f"To reach ${target_revenue:,.0f} revenue:\n"
            f"  Current: ${current_revenue:,.0f}\n"
            f"  Required budget: ${required_budget:,.2f}"
        )
        return (answer, False, False)
