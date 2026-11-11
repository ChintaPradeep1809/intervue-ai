"""Interviewer tool registry.

Read-only tools are exposed to the LLM (it must call them instead of guessing). State-changing
tools (update_interview_state, complete_round, generate_report, run_code, run_sql) are executed by
the engine/orchestrator only, never by the model, so the state machine stays authoritative.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from intervue_ai import ToolSpec

ToolFn = Callable[[dict[str, Any]], Awaitable[Any]]

READ_ONLY_TOOLS: dict[str, tuple[str, dict[str, Any]]] = {
    "get_candidate_profile": ("Candidate's name, declared experience and target role.", {}),
    "get_resume_analysis": ("Verified resume skills with verbatim evidence, skill gaps and priority topics.", {}),
    "get_job_description": ("The job description text (truncated).", {}),
    "get_interview_state": ("Current phase, round, question, difficulty and time remaining.", {}),
    "get_previous_answers": (
        "The candidate's most recent answers with their questions.",
        {"limit": {"type": "integer", "description": "How many recent answers to return (1-10)"}},
    ),
    "get_current_code": ("The candidate's current editor contents and language.", {}),
    "get_execution_result": ("The latest code/SQL execution result summary.", {}),
    "analyze_screen_snapshot": ("Summary of the latest consented screen snapshot analysis, if any.", {}),
}

ENGINE_TOOLS = ["run_code", "run_sql", "calculate_score", "update_interview_state", "generate_followup", "complete_round", "generate_report"]


def build_toolspecs(handlers: dict[str, ToolFn]) -> list[ToolSpec]:
    specs: list[ToolSpec] = []
    for name, (desc, props) in READ_ONLY_TOOLS.items():
        fn = handlers.get(name)
        if fn is None:
            continue

        async def _call(args: dict[str, Any], _fn: ToolFn = fn) -> str:
            result = await _fn(args)
            text = result if isinstance(result, str) else json.dumps(result, default=str)
            return text[:6000]

        specs.append(
            ToolSpec(
                name=name,
                description=desc,
                # strict tool schemas require every property to be listed as required
                input_schema={"type": "object", "properties": props, "required": list(props), "additionalProperties": False},
                handler=_call,
            )
        )
    return specs
