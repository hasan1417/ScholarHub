"""
API tests for Discussion AI metrics export/reset endpoints.
"""

import pytest
import importlib.util
from pathlib import Path

from app.core.config import settings
from app.services.discussion_ai.quality_metrics import get_discussion_ai_metrics_collector


def _load_metrics_module():
    metrics_path = Path(__file__).resolve().parent.parent / "app" / "api" / "v1" / "metrics.py"
    spec = importlib.util.spec_from_file_location("metrics_api_module", metrics_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_discussion_ai_metrics_endpoint_disabled(monkeypatch):
    metrics_api = _load_metrics_module()
    monkeypatch.setattr(settings, "ENABLE_METRICS", False)
    result = await metrics_api.get_discussion_ai_metrics()
    assert result["ok"] is True
    assert result["enabled"] is False


@pytest.mark.asyncio
async def test_discussion_ai_metrics_endpoint_enabled(monkeypatch):
    metrics_api = _load_metrics_module()
    monkeypatch.setattr(settings, "ENABLE_METRICS", True)
    collector = get_discussion_ai_metrics_collector()
    collector.reset()
    collector.record_turn(
        direct_search_intent=True,
        search_tool_called=True,
        clarification_first_detected=False,
        recency_requested=True,
        recency_filter_applied=True,
        stage_transition_expected=True,
        stage_transition_success=True,
    )

    result = await metrics_api.get_discussion_ai_metrics()
    assert result["ok"] is True
    assert result["enabled"] is True
    assert result["data"]["turns_total"] == 1
    assert result["data"]["direct_search_intents_total"] == 1


@pytest.mark.asyncio
async def test_discussion_ai_metrics_reset_endpoint(monkeypatch):
    metrics_api = _load_metrics_module()
    monkeypatch.setattr(settings, "ENABLE_METRICS", True)
    collector = get_discussion_ai_metrics_collector()
    collector.record_turn(
        direct_search_intent=True,
        search_tool_called=True,
        clarification_first_detected=False,
        recency_requested=False,
        recency_filter_applied=False,
        stage_transition_expected=False,
        stage_transition_success=False,
    )

    reset_result = await metrics_api.reset_discussion_ai_metrics()
    assert reset_result["ok"] is True
    assert reset_result["enabled"] is True

    result = await metrics_api.get_discussion_ai_metrics()
    assert result["data"]["turns_total"] == 0


@pytest.mark.asyncio
async def test_discussion_ai_metrics_history_endpoint(monkeypatch):
    metrics_api = _load_metrics_module()
    monkeypatch.setattr(settings, "ENABLE_METRICS", True)

    collector = get_discussion_ai_metrics_collector()
    captured = {}

    def fake_history(hours=24, limit=120, aggregate_minutes=1):
        captured["hours"] = hours
        captured["limit"] = limit
        captured["aggregate_minutes"] = aggregate_minutes
        return [{"turns_total": 3, "bucket_start_epoch": 1234567890}]

    monkeypatch.setattr(
        collector,
        "history",
        fake_history,
    )

    result = await metrics_api.get_discussion_ai_metrics_history(hours=12, limit=50, aggregate_minutes=15)
    assert result["ok"] is True
    assert result["enabled"] is True
    assert isinstance(result["data"], list)
    assert result["data"][0]["turns_total"] == 3
    assert captured["hours"] == 12
    assert captured["limit"] == 50
    assert captured["aggregate_minutes"] == 15
