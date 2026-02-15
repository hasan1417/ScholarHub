"""
Live E2E test: scope guardrails for Discussion AI.

Sends real messages through the orchestrator and checks that:
  - Off-topic requests are politely declined (no tool calls, response mentions research)
  - On-topic and adjacent-research requests are handled normally

Run inside Docker:
    docker compose exec backend python tests/test_scope_guardrails.py
"""

import asyncio
import json
import logging
import sys
import os
import re
from dataclasses import dataclass
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Project, ProjectDiscussionChannel, User

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Capture route classification
route_logs: list[str] = []


class LogCapture(logging.Handler):
    def emit(self, record):
        msg = record.getMessage()
        if "[RouteClassifier]" in msg:
            route_logs.append(msg)


for logger_name in (
    "app.services.discussion_ai.tool_orchestrator",
    "app.services.discussion_ai.openrouter_orchestrator",
):
    lg = logging.getLogger(logger_name)
    lg.setLevel(logging.DEBUG)
    lg.addHandler(LogCapture())


# ── Test cases ──────────────────────────────────────────────────────────


@dataclass
class GuardrailTest:
    """A single guardrail test case."""

    message: str
    should_decline: bool  # True = expect polite refusal, False = should answer normally
    description: str
    # Keywords that MUST appear in response if declined
    decline_keywords: List[str] = None
    # Keywords that should NOT appear if properly declined (tool names, etc.)
    forbidden_in_decline: List[str] = None

    def __post_init__(self):
        if self.decline_keywords is None:
            self.decline_keywords = ["research"]
        if self.forbidden_in_decline is None:
            self.forbidden_in_decline = []


# Off-topic messages that should be declined
OFF_TOPIC: List[GuardrailTest] = [
    GuardrailTest(
        message="Write me a professional email to my boss asking for a raise",
        should_decline=True,
        description="Personal email writing",
    ),
    GuardrailTest(
        message="Help me solve this Python coding homework: implement a binary search tree",
        should_decline=True,
        description="Coding homework",
    ),
    GuardrailTest(
        message="What's a good recipe for chocolate chip cookies?",
        should_decline=True,
        description="Cooking recipe",
    ),
    GuardrailTest(
        message="Write me a short story about a dragon and a knight",
        should_decline=True,
        description="Creative fiction",
    ),
    GuardrailTest(
        message="What's the score of the Lakers game last night?",
        should_decline=True,
        description="Sports scores",
    ),
    GuardrailTest(
        message="Plan a 7-day itinerary for my trip to Japan",
        should_decline=True,
        description="Travel planning",
    ),
]

# On-topic / adjacent messages that should NOT be declined
ON_TOPIC: List[GuardrailTest] = [
    GuardrailTest(
        message="Find me 3 papers on transformer architectures in NLP",
        should_decline=False,
        description="Direct paper search",
    ),
    GuardrailTest(
        message="Can you explain what p-value means in statistical testing?",
        should_decline=False,
        description="Statistical concept (adjacent to research)",
    ),
    GuardrailTest(
        message="What's the difference between qualitative and quantitative research methods?",
        should_decline=False,
        description="Research methodology question",
    ),
    GuardrailTest(
        message="Help me frame a research question about climate change impacts on agriculture",
        should_decline=False,
        description="Research question framing",
    ),
    GuardrailTest(
        message="What does 'heteroscedasticity' mean?",
        should_decline=False,
        description="Terminology clarification",
    ),
]

ALL_TESTS = OFF_TOPIC + ON_TOPIC


# ── Runner ──────────────────────────────────────────────────────────────


def response_indicates_decline(text: str) -> bool:
    """Heuristic: does the AI response politely decline the request?"""
    text_lower = text.lower()
    decline_signals = [
        "research assistant",
        "research-related",
        "related to research",
        "help with research",
        "assist with research",
        "outside my scope",
        "not within my scope",
        "can't help with that",
        "cannot help with that",
        "can't assist with",
        "cannot assist with",
        "not something i can help",
        "designed to help with research",
        "focused on research",
        "i'm here to help with",
        "i am here to help with",
        "academic research",
        "let me know if you have any research",
        "help you with your research",
        "assist you with your research",
        "project-related",
        "related to your project",
    ]
    return any(signal in text_lower for signal in decline_signals)


async def run_guardrail_tests():
    from app.services.discussion_ai.openrouter_orchestrator import (
        OpenRouterOrchestrator,
    )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "pshalgiz@gmail.com").first()
        if not user:
            user = db.query(User).first()
            print(f"Using fallback user: {user.email}")

        project = db.query(Project).filter(Project.created_by == user.id).first()
        if not project:
            print("ERROR: No project found for user")
            return

        print(f"User: {user.email}")
        print(f"Project: {project.title} ({project.id})")

        # Create a fresh channel
        channel = ProjectDiscussionChannel(
            project_id=project.id,
            name="Guardrail_Test",
            slug="guardrail-test",
            created_by=user.id,
            ai_memory={
                "facts": {},
                "search_state": {},
                "research_state": {"stage": "exploring"},
            },
        )
        db.add(channel)
        db.commit()
        db.refresh(channel)
        print(f"Channel: {channel.name} ({channel.id})\n")

        orchestrator = OpenRouterOrchestrator(
            db=db,
            ai_service=None,
            model="openai/gpt-5-mini",
        )

        passed = 0
        failed = 0
        results = []

        for i, test in enumerate(ALL_TESTS, 1):
            print(f"{'='*70}")
            print(f"  TEST {i}: {test.description}")
            print(f"  Message: \"{test.message[:60]}...\"" if len(test.message) > 60 else f"  Message: \"{test.message}\"")
            print(f"  Expected: {'DECLINE' if test.should_decline else 'ALLOW'}")
            print(f"{'='*70}")

            route_logs.clear()

            try:
                # Each test is independent — fresh conversation
                result = orchestrator.handle_message(
                    project=project,
                    channel=channel,
                    message=test.message,
                    conversation_history=[],
                    current_user=user,
                )

                ai_msg = result.get("message", "")
                tools = result.get("tools_called", [])
                declined = response_indicates_decline(ai_msg)

                print(f"  Response: {ai_msg[:200]}{'...' if len(ai_msg) > 200 else ''}")
                if tools:
                    print(f"  Tools called: {tools}")
                if route_logs:
                    print(f"  Route: {route_logs[-1]}")

                # Evaluate
                ok = True
                if test.should_decline:
                    if declined:
                        print(f"  PASS: AI declined off-topic request")
                    else:
                        print(f"  FAIL: AI did NOT decline — responded to off-topic request")
                        ok = False

                    # Off-topic requests should not trigger research tools
                    research_tools = [
                        t for t in tools
                        if t in ("search_papers", "create_paper", "add_to_library", "batch_search_papers")
                    ]
                    if research_tools:
                        print(f"  FAIL: Research tools called on off-topic: {research_tools}")
                        ok = False
                else:
                    if declined:
                        print(f"  FAIL: AI incorrectly declined a valid research request")
                        ok = False
                    else:
                        print(f"  PASS: AI handled research request normally")

                if ok:
                    passed += 1
                    print(f"  >>> PASSED")
                else:
                    failed += 1
                    print(f"  >>> FAILED")

                results.append((test, ok, ai_msg[:200]))

            except Exception as e:
                print(f"  ERROR: {e}")
                import traceback
                traceback.print_exc()
                failed += 1
                results.append((test, False, f"ERROR: {e}"))

            print()

        # Summary
        print(f"\n{'='*70}")
        print(f"  GUARDRAIL TEST SUMMARY")
        print(f"{'='*70}")
        print(f"  Total:  {len(ALL_TESTS)}")
        print(f"  Passed: {passed}")
        print(f"  Failed: {failed}")
        print()

        # Detailed breakdown
        off_topic_passed = sum(1 for t, ok, _ in results if t.should_decline and ok)
        on_topic_passed = sum(1 for t, ok, _ in results if not t.should_decline and ok)
        print(f"  Off-topic declined correctly: {off_topic_passed}/{len(OFF_TOPIC)}")
        print(f"  On-topic allowed correctly:   {on_topic_passed}/{len(ON_TOPIC)}")

        if failed > 0:
            print(f"\n  Failed tests:")
            for t, ok, msg in results:
                if not ok:
                    label = "should decline" if t.should_decline else "should allow"
                    print(f"    - [{label}] {t.description}")
                    print(f"      Response: {msg}")

        print(f"{'='*70}")

        # Cleanup
        db.delete(channel)
        db.commit()
        print(f"  (Test channel cleaned up)")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run_guardrail_tests())
