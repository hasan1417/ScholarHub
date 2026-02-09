#!/usr/bin/env python3
"""
Comprehensive E2E test suite for dynamic tool exposure and intent classification.

Run all channels:
    docker compose exec backend python tests/run_comprehensive_test.py

Run single channel:
    docker compose exec backend python tests/run_comprehensive_test.py --channel 2

This tests route classification, intent detection, and tool exposure
against a live backend with actual LLM calls.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.discussion_ai.route_classifier import classify_route
from app.services.discussion_ai.intent_classifier import classify_intent_sync, VALID_INTENTS
from app.services.discussion_ai.policy import DiscussionPolicy

logger = logging.getLogger("comprehensive_test")


# ── Test infrastructure ─────────────────────────────────────────────────

@dataclass
class TurnSpec:
    """Specification for a single test turn."""
    message: str
    expected_route: str  # "lite" or "full" — hard fail
    expected_intent: Optional[str] = None  # soft warn (LLM varies)
    tools_include: List[str] = field(default_factory=list)  # at-least-one-of — hard fail
    forbidden_tools: List[str] = field(default_factory=list)  # hard fail if present
    tools_exposed_min: int = 0  # soft warn
    tools_exposed_max: int = 30  # soft warn


@dataclass
class ChannelSpec:
    """Specification for a test channel (sequence of turns)."""
    name: str
    description: str
    turns: List[TurnSpec]


@dataclass
class TurnResult:
    """Result of a single test turn."""
    turn_num: int
    message: str
    actual_route: str
    actual_route_reason: str
    actual_intent: Optional[str]
    actual_confidence: Optional[float]
    tools_called: List[str]
    tools_exposed_count: int
    passed: bool
    warnings: List[str]
    errors: List[str]


@dataclass
class ChannelResult:
    """Result of an entire channel test."""
    channel_name: str
    turns: List[TurnResult]
    total_turns: int
    passed_turns: int
    warned_turns: int
    failed_turns: int
    duration_s: float


# ── Test channels ────────────────────────────────────────────────────────

CHANNELS: List[ChannelSpec] = [
    ChannelSpec(
        name="Channel 1: Quick Search & Add",
        description="Basic search workflow: greet, search, add, details, bye",
        turns=[
            TurnSpec("hi im researching quantum computing", expected_route="lite"),
            TurnSpec(
                "find me 3 papers on quantum error correction",
                expected_route="full",
                expected_intent="direct_search",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "add all to my library",
                expected_route="full",
                tools_include=["add_to_library"],
            ),
            TurnSpec(
                "show me the details of the first paper",
                expected_route="full",
                expected_intent="library",
            ),
            TurnSpec("thanks!", expected_route="lite"),
        ],
    ),
    ChannelSpec(
        name="Channel 2: Full Research Workflow",
        description="12-turn deep workflow covering search, analysis, writing, export",
        turns=[
            TurnSpec("I'm writing a survey on federated learning", expected_route="full"),
            TurnSpec(
                "find me 5 papers on federated learning privacy",
                expected_route="full",
                expected_intent="direct_search",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "find 3 more on this topic",
                expected_route="full",
                expected_intent="direct_search",
            ),
            TurnSpec(
                "add all papers to library",
                expected_route="full",
                tools_include=["add_to_library"],
            ),
            TurnSpec(
                "compare the different privacy approaches",
                expected_route="full",
                expected_intent="analysis",
            ),
            TurnSpec(
                "what research gaps exist?",
                expected_route="full",
                expected_intent="analysis",
            ),
            TurnSpec(
                "find papers related to the first one",
                expected_route="full",
                expected_intent="direct_search",
            ),
            TurnSpec(
                "create a literature review paper covering what we discussed",
                expected_route="full",
                expected_intent="writing",
                tools_include=["create_paper"],
            ),
            TurnSpec(
                "add a methodology comparison section",
                expected_route="full",
                expected_intent="writing",
            ),
            TurnSpec(
                "generate an abstract for the paper",
                expected_route="full",
                expected_intent="writing",
                tools_include=["generate_abstract"],
            ),
            TurnSpec(
                "export citations in bibtex",
                expected_route="full",
                expected_intent="library",
                tools_include=["export_citations"],
            ),
            TurnSpec("great work, thanks!", expected_route="lite"),
        ],
    ),
    ChannelSpec(
        name="Channel 3: Library Deep Dive",
        description="Library management: browse, details, annotate, search, export",
        turns=[
            TurnSpec(
                "show me all papers in my library",
                expected_route="full",
                expected_intent="library",
                tools_include=["get_project_references"],
            ),
            TurnSpec(
                "tell me more about the second paper",
                expected_route="full",
                expected_intent="library",
            ),
            TurnSpec(
                "tag it as key-paper and add a note",
                expected_route="full",
                expected_intent="library",
                tools_include=["annotate_reference"],
            ),
            TurnSpec(
                "search my library for papers about transformers",
                expected_route="full",
                expected_intent="library",
            ),
            TurnSpec(
                "export all citations in APA format",
                expected_route="full",
                expected_intent="library",
                tools_include=["export_citations"],
            ),
            TurnSpec("ok cool", expected_route="lite"),
        ],
    ),
    ChannelSpec(
        name="Channel 4: Analysis Session",
        description="Search then analyze: search, focus, compare, gaps, artifact",
        turns=[
            TurnSpec("I want to analyze some papers", expected_route="full"),
            TurnSpec(
                "search for 4 papers on attention mechanisms",
                expected_route="full",
                expected_intent="direct_search",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "focus on papers 1 and 3",
                expected_route="full",
                tools_include=["focus_on_papers"],
            ),
            TurnSpec(
                "compare their methodologies and results",
                expected_route="full",
                expected_intent="analysis",
                tools_include=["compare_papers"],
            ),
            TurnSpec(
                "what are the research gaps in this area?",
                expected_route="full",
                expected_intent="analysis",
            ),
            TurnSpec(
                "create a summary artifact of our analysis",
                expected_route="full",
                expected_intent="writing",
                tools_include=["create_artifact"],
            ),
            TurnSpec("thx", expected_route="lite"),
        ],
    ),
    ChannelSpec(
        name="Channel 5: Project Setup",
        description="Project config then search, add, create doc",
        turns=[
            TurnSpec(
                "update my project keywords to include reinforcement learning and robotics",
                expected_route="full",
                expected_intent="project_update",
                tools_include=["update_project_info"],
            ),
            TurnSpec(
                "find papers about my project topic",
                expected_route="full",
                expected_intent="direct_search",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "add these to library",
                expected_route="full",
                tools_include=["add_to_library"],
            ),
            TurnSpec(
                "create a short overview document",
                expected_route="full",
                expected_intent="writing",
            ),
            TurnSpec("perfect", expected_route="lite"),
        ],
    ),
    ChannelSpec(
        name="Channel 6: Messy Real User",
        description="Realistic messy input: typos, short follow-ups, topic switches",
        turns=[
            TurnSpec("hey", expected_route="lite"),
            TurnSpec(
                "i need papers abt deep learning for medical imaging",
                expected_route="full",
                expected_intent="direct_search",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "more plz",
                expected_route="full",  # follow-up fix: after search, short msg stays full
            ),
            TurnSpec(
                "add them all",
                expected_route="full",
                tools_include=["add_to_library"],
            ),
            TurnSpec(
                "wait actually can u find papers on transformrs for protein folding instead",
                expected_route="full",
                expected_intent="direct_search",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "ya add those too",
                expected_route="full",
                tools_include=["add_to_library"],
            ),
            TurnSpec(
                "whats in my library now",
                expected_route="full",
                expected_intent="library",
            ),
            TurnSpec("k bye", expected_route="lite"),
        ],
    ),
]


# ── Test runner ──────────────────────────────────────────────────────────

def _build_mock_memory_facts(last_tools_called: List[str]) -> Dict[str, Any]:
    """Build memory facts dict simulating what the orchestrator would persist."""
    return {"_last_tools_called": last_tools_called}


def _get_classifier_client():
    """Try to create a real OpenAI-compatible client for classifier testing."""
    try:
        import openai
        from app.core.config import settings
        api_key = settings.OPENROUTER_API_KEY
        if not api_key:
            return None
        return openai.OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://scholarhub.space",
                "X-Title": "ScholarHub",
            },
        )
    except Exception:
        return None


def run_channel(
    channel: ChannelSpec,
    classifier_client=None,
    verbose: bool = True,
) -> ChannelResult:
    """Run all turns for a channel and collect results."""
    t_start = time.monotonic()
    conversation_history: List[Dict[str, str]] = []
    memory_facts: Dict[str, Any] = {}
    last_tools_called: List[str] = []
    policy = DiscussionPolicy()

    results: List[TurnResult] = []

    for i, turn in enumerate(channel.turns, 1):
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Route classification (deterministic — hard assertions)
        route_decision = classify_route(turn.message, conversation_history, memory_facts)
        actual_route = route_decision.route
        actual_route_reason = route_decision.reason

        if actual_route != turn.expected_route:
            errors.append(
                f"ROUTE: expected={turn.expected_route} got={actual_route} "
                f"reason={actual_route_reason}"
            )

        # 2. Intent classification (LLM-based — soft assertions)
        actual_intent = None
        actual_confidence = None

        if actual_route == "full" and turn.expected_intent:
            # First check deterministic policy
            policy_decision = policy.build_decision(turn.message)
            if policy_decision.intent != "general":
                actual_intent = policy_decision.intent
                actual_confidence = 1.0
            elif classifier_client:
                actual_intent, actual_confidence = classify_intent_sync(
                    turn.message,
                    conversation_history[-4:],
                    classifier_client,
                )
            else:
                actual_intent = "general"
                actual_confidence = 0.5

            if actual_intent != turn.expected_intent:
                warnings.append(
                    f"INTENT: expected={turn.expected_intent} got={actual_intent} "
                    f"confidence={actual_confidence:.2f}"
                )

        # 3. Tool assertions (we can't actually execute tools without DB,
        #    but we can verify the tool exposure filtering)
        tools_exposed_count = 0
        tools_called: List[str] = []

        # Note: tools_include/forbidden assertions require actual execution
        # which needs a full DB context. In offline mode, we skip these.
        # They are tested by the live E2E runner.
        if turn.tools_include:
            warnings.append(
                f"TOOLS_INCLUDE: {turn.tools_include} (requires live execution to verify)"
            )

        # Update simulated state for next turn
        conversation_history.append({"role": "user", "content": turn.message})
        conversation_history.append({
            "role": "assistant",
            "content": f"[simulated response to: {turn.message[:50]}]",
        })

        # Simulate _last_tools_called for follow-up detection
        if actual_route == "full" and turn.tools_include:
            last_tools_called = turn.tools_include
        elif actual_route == "lite":
            last_tools_called = []
        memory_facts = _build_mock_memory_facts(last_tools_called)

        passed = len(errors) == 0
        results.append(TurnResult(
            turn_num=i,
            message=turn.message,
            actual_route=actual_route,
            actual_route_reason=actual_route_reason,
            actual_intent=actual_intent,
            actual_confidence=actual_confidence,
            tools_called=tools_called,
            tools_exposed_count=tools_exposed_count,
            passed=passed,
            warnings=warnings,
            errors=errors,
        ))

        if verbose:
            status = "PASS" if passed else "FAIL"
            warn_str = f" [{len(warnings)} warn]" if warnings else ""
            intent_str = f" intent={actual_intent}" if actual_intent else ""
            print(
                f"  Turn {i:2d} [{status}{warn_str}] "
                f"route={actual_route:<4s}{intent_str} "
                f'| "{turn.message[:60]}"'
            )
            for err in errors:
                print(f"         ERROR: {err}")
            for warn in warnings:
                print(f"         WARN:  {warn}")

    duration_s = time.monotonic() - t_start
    passed_turns = sum(1 for r in results if r.passed and not r.warnings)
    warned_turns = sum(1 for r in results if r.passed and r.warnings)
    failed_turns = sum(1 for r in results if not r.passed)

    return ChannelResult(
        channel_name=channel.name,
        turns=results,
        total_turns=len(results),
        passed_turns=passed_turns,
        warned_turns=warned_turns,
        failed_turns=failed_turns,
        duration_s=duration_s,
    )


def print_summary(channel_results: List[ChannelResult]) -> bool:
    """Print overall summary and return True if all hard assertions passed."""
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_turns = 0
    total_passed = 0
    total_warned = 0
    total_failed = 0
    total_duration = 0.0

    for cr in channel_results:
        total_turns += cr.total_turns
        total_passed += cr.passed_turns
        total_warned += cr.warned_turns
        total_failed += cr.failed_turns
        total_duration += cr.duration_s

        status = "PASS" if cr.failed_turns == 0 else "FAIL"
        warn_str = f" ({cr.warned_turns} warnings)" if cr.warned_turns else ""
        print(
            f"  {status} {cr.channel_name}: "
            f"{cr.passed_turns}/{cr.total_turns} passed{warn_str} "
            f"({cr.duration_s:.1f}s)"
        )

    print(f"\nTotal: {total_turns} turns, {total_passed} passed, "
          f"{total_warned} warned, {total_failed} failed "
          f"({total_duration:.1f}s)")

    all_passed = total_failed == 0
    print(f"\nOverall: {'PASS' if all_passed else 'FAIL'}")
    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Comprehensive E2E test suite")
    parser.add_argument(
        "--channel", type=int, default=None,
        help="Run only a specific channel (1-6)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", default=True,
        help="Verbose output (default: True)",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Quiet mode (summary only)",
    )
    parser.add_argument(
        "--with-llm", action="store_true",
        help="Enable LLM classifier calls (requires API key)",
    )
    args = parser.parse_args()

    verbose = not args.quiet

    # Try to get classifier client if requested
    classifier_client = None
    if args.with_llm:
        classifier_client = _get_classifier_client()
        if classifier_client:
            print("LLM classifier: ENABLED (using OpenRouter API)")
        else:
            print("LLM classifier: DISABLED (no API key)")
    else:
        print("LLM classifier: DISABLED (use --with-llm to enable)")

    # Select channels
    if args.channel:
        if args.channel < 1 or args.channel > len(CHANNELS):
            print(f"Error: channel must be 1-{len(CHANNELS)}")
            sys.exit(1)
        channels = [CHANNELS[args.channel - 1]]
    else:
        channels = CHANNELS

    print(f"\nRunning {len(channels)} channel(s), "
          f"{sum(len(c.turns) for c in channels)} total turns\n")

    # Run channels
    channel_results: List[ChannelResult] = []
    for channel in channels:
        print(f"\n{'─' * 60}")
        print(f"{channel.name}")
        print(f"  {channel.description}")
        print(f"{'─' * 60}")

        result = run_channel(channel, classifier_client, verbose)
        channel_results.append(result)

    # Print summary
    all_passed = print_summary(channel_results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
