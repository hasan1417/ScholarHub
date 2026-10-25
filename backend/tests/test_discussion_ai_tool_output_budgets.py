"""Tool-output caps include valid JSON envelopes and exhaustion notices."""

import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.discussion_ai.token_utils import count_tokens
from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator


def _orchestrator() -> ToolOrchestrator:
    orchestrator = object.__new__(ToolOrchestrator)
    orchestrator.ai_service = SimpleNamespace(default_model="openai/gpt-4o")
    return orchestrator


@pytest.mark.parametrize("content", ["x" * 100000, "界語\\\n" * 20000], ids=["large_text", "escaped_unicode"])
def test_full_batch_results_and_exhaustion_notices_fit_hard_turn_caps(content: str) -> None:
    orchestrator = _orchestrator()
    ctx: dict[str, Any] = {}
    calls = [{"id": str(index), "name": "get_project_references", "arguments": {}}
             for index in range(100)]
    selected = orchestrator._limit_turn_tool_calls(calls, ctx)
    outputs = [orchestrator._serialize_tool_result(
        {"name": call["name"], "result": {"papers": [{"abstract": content}]}}, ctx,
    ) for call in selected]

    assert len(selected) == orchestrator.TURN_TOOL_CALL_MAX
    assert all(len(output) <= orchestrator.TOOL_RESULT_MAX_CHARS for output in outputs)
    assert all(count_tokens(output, orchestrator.model) <= orchestrator.TOOL_RESULT_MAX_TOKENS for output in outputs)
    assert sum(map(len, outputs)) <= orchestrator.TURN_TOOL_OUTPUT_MAX_CHARS
    assert sum(count_tokens(output, orchestrator.model) for output in outputs) <= orchestrator.TURN_TOOL_OUTPUT_MAX_TOKENS
    assert ctx["_tool_output_chars"] == sum(map(len, outputs))
    assert all(json.loads(output)["output_truncated"] for output in outputs)
    assert "Turn tool-output budget exhausted" in outputs[-1]
    assert ctx["_tool_output_exhausted"] is True
    assert orchestrator._limit_turn_tool_calls(calls, ctx) == []


def test_result_item_and_depth_limits_are_explicit_without_altering_full_result() -> None:
    orchestrator = _orchestrator()
    deep: dict[str, Any] = {"text": "hidden"}
    for _ in range(20):
        deep = {"nested": deep}
    result = {"result": {"papers": list(range(100)), "nested": deep}}

    output = json.loads(orchestrator._serialize_tool_result(result, {}))

    assert output["output_truncated"] is True
    assert len(output["result"]["papers"]) == 20
    assert "Additional content omitted" in json.dumps(output)
    assert len(result["result"]["papers"]) == 100


def test_excess_tool_calls_are_reported_in_provider_context() -> None:
    orchestrator = _orchestrator()
    ctx: dict[str, Any] = {}
    selected = orchestrator._limit_turn_tool_calls([{"id": str(index)} for index in range(40)], ctx)

    output = json.loads(orchestrator._serialize_tool_result({"result": {"status": "success"}}, ctx))

    assert len(selected) == 32
    assert output["tool_calls_omitted"] == 8
    assert "not executed" in output["tool_call_notice"]


def test_per_result_character_cap_does_not_end_turn_early() -> None:
    orchestrator = _orchestrator()
    ctx: dict[str, Any] = {}

    first = orchestrator._serialize_tool_result({"result": {"content": "x" * 100000}}, ctx)
    second = orchestrator._serialize_tool_result({"result": {"content": "second result"}}, ctx)

    assert json.loads(first)["output_truncated"] is True
    assert json.loads(second)["result"]["content"] == "second result"
    assert not ctx.get("_tool_output_exhausted")


def test_list_tool_result_is_wrapped_before_truncation() -> None:
    assert json.loads(_orchestrator()._serialize_tool_result(list(range(100)), {}))["result"] == list(range(20))
