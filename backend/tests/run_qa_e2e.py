"""
End-to-end QA test: 6-step sequence from MANUAL_QA_MEMORY.md.

Creates a fresh channel, sends all 6 messages through the real orchestrator,
and validates policy decisions, search args, and memory state after each step.

Run inside Docker:
    docker compose exec backend python tests/run_qa_e2e.py
"""

import asyncio
import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Project, ProjectDiscussionChannel, User

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Capture PolicyDecision and SearchArgs logs
policy_logs = []
search_args_logs = []
turn_metrics_logs = []
route_logs = []

class LogCapture(logging.Handler):
    def emit(self, record):
        msg = record.getMessage()
        if "[PolicyDecision]" in msg:
            policy_logs.append(msg)
        if "[SearchArgs]" in msg:
            search_args_logs.append(msg)
        if "[TurnMetrics]" in msg:
            turn_metrics_logs.append(msg)
        if "[RouteClassifier]" in msg:
            route_logs.append(msg)

# Attach to all relevant loggers
for logger_name in ("app.services.discussion_ai.tool_orchestrator",
                     "app.services.discussion_ai.openrouter_orchestrator"):
    lg = logging.getLogger(logger_name)
    lg.setLevel(logging.DEBUG)
    lg.addHandler(LogCapture())


QA_STEPS = [
    "My research question is: How does sleep deprivation affect cognitive function in medical residents?",
    "Can you find me 5 recent papers on this topic?",
    "Can you find another 3 papers?",
    "Find 4 open access papers from the last 3 years on this topic.",
    "Please update project keywords to sleep deprivation, cognition, medical residents.",
    "Can you find papers on climate adaptation policy from 2021 to 2024?",
]


def separator(step_num, msg):
    print(f"\n{'='*80}")
    print(f"  STEP {step_num}: {msg[:70]}")
    print(f"{'='*80}")


def print_policy_log(step_num):
    """Print the last captured PolicyDecision log."""
    if policy_logs:
        last = policy_logs[-1]
        # Extract JSON part
        idx = last.find("{")
        if idx >= 0:
            try:
                data = json.loads(last[idx:])
                print(f"  [Step {step_num}] PolicyDecision:")
                print(f"    intent:        {data.get('intent')}")
                print(f"    force_tool:    {data.get('force_tool')}")
                print(f"    reasons:       {data.get('reasons')}")
                search = data.get("search", {})
                if search.get("query"):
                    print(f"    search.query:  {search.get('query', '')[:80]}")
                    print(f"    search.count:  {search.get('count')}")
                    print(f"    search.oa:     {search.get('open_access_only')}")
                    print(f"    search.year_from: {search.get('year_from')}")
                    print(f"    search.year_to:   {search.get('year_to')}")
                action = data.get("action_plan", {})
                if action.get("primary_tool"):
                    print(f"    action.primary_tool: {action.get('primary_tool')}")
                if action.get("blocked_tools"):
                    print(f"    action.blocked:      {action.get('blocked_tools')}")
                return data
            except json.JSONDecodeError:
                print(f"  [Step {step_num}] PolicyDecision (raw): {last}")
    return None


def print_search_args(step_num):
    """Print the last captured SearchArgs log."""
    if search_args_logs:
        last = search_args_logs[-1]
        idx = last.find("{")
        if idx >= 0:
            try:
                data = json.loads(last[idx:])
                print(f"  [Step {step_num}] SearchArgs (normalized):")
                for k, v in data.items():
                    print(f"    {k}: {v}")
                return data
            except json.JSONDecodeError:
                pass
    return None


def print_route(step_num):
    """Print the route classification."""
    if route_logs:
        last = route_logs[-1]
        print(f"  [Step {step_num}] Route: {last}")


def print_metrics(step_num):
    """Print TurnMetrics."""
    if turn_metrics_logs:
        last = turn_metrics_logs[-1]
        print(f"  [Step {step_num}] {last}")


def check_memory_state(db, channel_id):
    """Print the current search_state from memory."""
    channel = db.query(ProjectDiscussionChannel).filter_by(id=channel_id).first()
    if channel and channel.ai_memory:
        mem = channel.ai_memory if isinstance(channel.ai_memory, dict) else json.loads(channel.ai_memory)
        ss = mem.get("search_state", {})
        print(f"  Memory search_state:")
        print(f"    last_effective_topic: {ss.get('last_effective_topic', '(none)')}")
        print(f"    last_count:           {ss.get('last_count', '(none)')}")
        facts = mem.get("facts", {})
        rq = facts.get("research_question")
        if rq:
            print(f"    research_question:    {rq[:80]}")


async def run_qa_sequence():
    from app.services.discussion_ai.openrouter_orchestrator import OpenRouterOrchestrator

    db = SessionLocal()
    try:
        # Use the user who owns projects
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

        # Create a fresh channel for testing
        channel = ProjectDiscussionChannel(
            project_id=project.id,
            name="QA_Policy_Test",
            slug="qa-policy-test",
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
        print(f"Channel: {channel.name} ({channel.id})")

        # Initialize orchestrator
        # Use a cheap/fast model for testing
        orchestrator = OpenRouterOrchestrator(
            db=db,
            ai_service=None,
            model="openai/gpt-4o-mini",
        )

        conversation_history = []
        passed = 0
        failed = 0

        for i, msg in enumerate(QA_STEPS, 1):
            separator(i, msg)
            # Clear per-step logs
            policy_logs.clear()
            search_args_logs.clear()
            turn_metrics_logs.clear()
            route_logs.clear()

            try:
                # Use non-streaming for simpler output capture
                result = orchestrator.handle_message(
                    project=project,
                    channel=channel,
                    message=msg,
                    conversation_history=conversation_history,
                    current_user=user,
                )

                # Print captured logs
                print_route(i)
                pd = print_policy_log(i)
                sa = print_search_args(i)
                print_metrics(i)

                # Print AI response (truncated)
                ai_msg = result.get("message", "")[:200]
                tools = result.get("tools_called", [])
                print(f"  AI Response: {ai_msg}...")
                if tools:
                    print(f"  Tools called: {tools}")

                # Check memory state
                db.refresh(channel)
                check_memory_state(db, channel.id)

                # Validate expectations
                print(f"\n  --- Validation ---")
                ok = True

                if i == 1:
                    # Should NOT be a search
                    if pd and pd.get("intent") == "general":
                        print(f"  PASS: intent=general (not a search request)")
                    else:
                        print(f"  FAIL: Expected intent=general, got {pd.get('intent') if pd else 'no policy'}")
                        ok = False

                elif i == 2:
                    # direct_search, count=5, recent filter
                    if pd and pd.get("intent") == "direct_search":
                        print(f"  PASS: intent=direct_search")
                    else:
                        print(f"  FAIL: Expected intent=direct_search")
                        ok = False
                    if sa and sa.get("count") == 5:
                        print(f"  PASS: count=5")
                    else:
                        print(f"  FAIL: Expected count=5, got {sa.get('count') if sa else 'none'}")
                        ok = False
                    if sa and sa.get("year_from") and sa.get("year_to"):
                        print(f"  PASS: year filter applied ({sa['year_from']}-{sa['year_to']})")
                    else:
                        print(f"  FAIL: Expected year filter from 'recent'")
                        ok = False

                elif i == 3:
                    # direct_search, count=3, query NOT literal "another 3 papers"
                    if pd and pd.get("intent") == "direct_search":
                        print(f"  PASS: intent=direct_search")
                    else:
                        print(f"  FAIL: Expected intent=direct_search")
                        ok = False
                    if sa and sa.get("count") == 3:
                        print(f"  PASS: count=3")
                    else:
                        print(f"  FAIL: Expected count=3, got {sa.get('count') if sa else 'none'}")
                        ok = False
                    query = (sa or {}).get("query", "")
                    if query and "another 3 papers" not in query.lower():
                        print(f"  PASS: query is NOT literal filler (got: {query[:60]})")
                    else:
                        print(f"  FAIL: query is literal filler: '{query}'")
                        ok = False

                elif i == 4:
                    # count=4, open_access=True, last 3 years
                    if sa and sa.get("count") == 4:
                        print(f"  PASS: count=4")
                    else:
                        print(f"  FAIL: Expected count=4")
                        ok = False
                    if sa and sa.get("open_access_only") is True:
                        print(f"  PASS: open_access_only=True")
                    else:
                        print(f"  FAIL: Expected open_access_only=True")
                        ok = False
                    from datetime import datetime, timezone
                    cy = datetime.now(timezone.utc).year
                    if sa and sa.get("year_from") == cy - 2 and sa.get("year_to") == cy:
                        print(f"  PASS: year filter last 3 years ({cy-2}-{cy})")
                    else:
                        print(f"  FAIL: Expected year {cy-2}-{cy}, got {sa.get('year_from')}-{sa.get('year_to')}")
                        ok = False

                elif i == 5:
                    # project_update intent, search tools blocked
                    if pd and pd.get("intent") == "project_update":
                        print(f"  PASS: intent=project_update")
                    else:
                        print(f"  FAIL: Expected intent=project_update, got {pd.get('intent') if pd else 'none'}")
                        ok = False
                    ap = (pd or {}).get("action_plan", {})
                    blocked = ap.get("blocked_tools", [])
                    if "search_papers" in blocked:
                        print(f"  PASS: search_papers is blocked")
                    else:
                        print(f"  FAIL: search_papers not in blocked_tools: {blocked}")
                        ok = False
                    if "search_papers" not in (tools or []):
                        print(f"  PASS: search_papers was NOT executed")
                    else:
                        print(f"  FAIL: search_papers was executed when it shouldn't be")
                        ok = False

                elif i == 6:
                    # climate topic, year 2021-2024
                    if pd and pd.get("intent") == "direct_search":
                        print(f"  PASS: intent=direct_search")
                    else:
                        print(f"  FAIL: Expected intent=direct_search")
                        ok = False
                    query = (sa or {}).get("query", "").lower()
                    if "climate" in query:
                        print(f"  PASS: query contains 'climate' ({query[:60]})")
                    else:
                        print(f"  FAIL: query missing 'climate': '{query}'")
                        ok = False
                    if sa and sa.get("year_from") == 2021 and sa.get("year_to") == 2024:
                        print(f"  PASS: year bounds 2021-2024")
                    else:
                        print(f"  FAIL: Expected 2021-2024, got {sa.get('year_from')}-{sa.get('year_to')}")
                        ok = False

                if ok:
                    passed += 1
                    print(f"  >>> STEP {i}: ALL CHECKS PASSED")
                else:
                    failed += 1
                    print(f"  >>> STEP {i}: SOME CHECKS FAILED")

                # Update conversation history for next turn
                conversation_history.append({"role": "user", "content": msg})
                conversation_history.append({"role": "assistant", "content": result.get("message", "")})

            except Exception as e:
                print(f"  ERROR in step {i}: {e}")
                import traceback
                traceback.print_exc()
                failed += 1

        # Final summary
        print(f"\n{'='*80}")
        print(f"  QA SUMMARY: {passed}/{len(QA_STEPS)} steps passed, {failed} failed")
        print(f"{'='*80}")

        # Cleanup: delete test channel
        db.delete(channel)
        db.commit()
        print(f"  (Test channel cleaned up)")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run_qa_sequence())
