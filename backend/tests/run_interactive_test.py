"""
Interactive multi-prompt test through the real orchestrator.

Tests a broad range of scenarios:
- Lite route (greetings, acknowledgments)
- Low-info queries ("find papers about my project")
- Deictic references ("on this topic")
- Explicit topics
- Project context resolution
- Structural overrides (count, OA, year)

Run inside Docker:
    docker compose exec backend python tests/run_interactive_test.py
"""

import asyncio
import json
import logging
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Project, ProjectDiscussionChannel, User

logging.basicConfig(level=logging.INFO, format="%(message)s")

# Capture structured logs
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

for logger_name in ("app.services.discussion_ai.tool_orchestrator",
                     "app.services.discussion_ai.openrouter_orchestrator"):
    lg = logging.getLogger(logger_name)
    lg.setLevel(logging.DEBUG)
    lg.addHandler(LogCapture())


# ── Test prompts ──────────────────────────────────────────────────────
# Each tuple: (message, expected_checks_dict)
# Checks: route, intent, query_contains, count, oa, year_from, year_to,
#          query_not_contains, tools_called_contains, tools_called_not_contains

PROMPTS = [
    # 1. Greeting → lite route
    {
        "msg": "Hi there!",
        "label": "Greeting → lite",
        "expect": {"route": "lite"},
    },
    # 2. Research question statement → general (no search)
    {
        "msg": "I'm researching the effects of microplastics on marine ecosystems.",
        "label": "Research statement → general, no search",
        "expect": {"intent": "general"},
    },
    # 3. LOW-INFO BUG: "find papers about my project" → should resolve to project context
    {
        "msg": "Can you find 3 papers about my project?",
        "label": "Low-info 'about my project' → project context resolution",
        "expect": {
            "intent": "direct_search",
            "count": 3,
            "query_not_contains": ["my project", "about my project", "3 papers about my project"],
        },
    },
    # 4. Explicit topic search
    {
        "msg": "Find me 5 papers on deep reinforcement learning for robotics.",
        "label": "Explicit topic search",
        "expect": {
            "intent": "direct_search",
            "count": 5,
            "query_contains": ["reinforcement learning"],
        },
    },
    # 5. Acknowledgment → lite
    {
        "msg": "Thanks, that's helpful!",
        "label": "Acknowledgment → lite",
        "expect": {"route": "lite"},
    },
    # 6. Deictic "on this topic" → should use memory/last search
    {
        "msg": "Can you find me 2 more papers on this topic?",
        "label": "Deictic 'this topic' → memory resolution",
        "expect": {
            "intent": "direct_search",
            "count": 2,
            "query_not_contains": ["this topic", "2 more papers"],
        },
    },
    # 7. Open access + year range
    {
        "msg": "Find 4 open access papers from 2022 to 2025 on transformer architectures.",
        "label": "OA + year range + explicit topic",
        "expect": {
            "intent": "direct_search",
            "count": 4,
            "oa": True,
            "year_from": 2022,
            "year_to": 2025,
            "query_contains": ["transformer"],
        },
    },
    # 8. Relative-only "another 3 papers" → should carry over topic
    {
        "msg": "Can you find another 3 papers?",
        "label": "Relative-only 'another 3' → carry-over topic",
        "expect": {
            "intent": "direct_search",
            "count": 3,
            "query_not_contains": ["another 3 papers", "another 3"],
        },
    },
    # 9. Project update
    {
        "msg": "Update project keywords to microplastics, marine pollution, ocean health.",
        "label": "Project update → no search",
        "expect": {
            "intent": "project_update",
            "tools_called_not_contains": ["search_papers"],
        },
    },
    # 10. Short confirmation → lite (no pending action)
    {
        "msg": "ok",
        "label": "Short confirmation → lite",
        "expect": {"route": "lite"},
    },
    # 11. Topic switch — completely new explicit topic
    {
        "msg": "Can you find papers on quantum error correction codes?",
        "label": "Topic switch → explicit new topic",
        "expect": {
            "intent": "direct_search",
            "query_contains": ["quantum"],
        },
    },
    # 12. "recent papers" with no explicit topic → should use memory
    {
        "msg": "Find me some recent papers on this.",
        "label": "Deictic 'this' + recent → memory + year filter",
        "expect": {
            "intent": "direct_search",
            "query_not_contains": ["some recent papers", "this"],
        },
    },
]


def separator(step_num, label):
    print(f"\n{'='*80}")
    print(f"  STEP {step_num}: {label}")
    print(f"{'='*80}")


def extract_json(log_line):
    idx = log_line.find("{")
    if idx >= 0:
        try:
            return json.loads(log_line[idx:])
        except json.JSONDecodeError:
            pass
    return None


def validate(step_num, expect, route_log, pd, sa, tools_called):
    """Validate expectations. Returns (passed, failed, messages)."""
    passed = 0
    failed = 0
    msgs = []

    # Route check
    if "route" in expect:
        actual_route = None
        if route_log:
            parts = route_log.split("route=")
            if len(parts) > 1:
                actual_route = parts[1].split()[0]
        if actual_route == expect["route"]:
            msgs.append(f"  PASS: route={actual_route}")
            passed += 1
        else:
            msgs.append(f"  FAIL: Expected route={expect['route']}, got {actual_route}")
            failed += 1

    # Intent check
    if "intent" in expect:
        actual_intent = pd.get("intent") if pd else None
        if actual_intent == expect["intent"]:
            msgs.append(f"  PASS: intent={actual_intent}")
            passed += 1
        else:
            msgs.append(f"  FAIL: Expected intent={expect['intent']}, got {actual_intent}")
            failed += 1

    # Count check
    if "count" in expect:
        actual_count = (sa or {}).get("count")
        if actual_count == expect["count"]:
            msgs.append(f"  PASS: count={actual_count}")
            passed += 1
        else:
            msgs.append(f"  FAIL: Expected count={expect['count']}, got {actual_count}")
            failed += 1

    # OA check
    if "oa" in expect:
        actual_oa = (sa or {}).get("open_access_only")
        if actual_oa == expect["oa"]:
            msgs.append(f"  PASS: open_access_only={actual_oa}")
            passed += 1
        else:
            msgs.append(f"  FAIL: Expected OA={expect['oa']}, got {actual_oa}")
            failed += 1

    # Year checks
    for key in ("year_from", "year_to"):
        if key in expect:
            actual = (sa or {}).get(key)
            if actual == expect[key]:
                msgs.append(f"  PASS: {key}={actual}")
                passed += 1
            else:
                msgs.append(f"  FAIL: Expected {key}={expect[key]}, got {actual}")
                failed += 1

    # Query contains
    query = ((sa or {}).get("query") or "").lower()
    for term in expect.get("query_contains", []):
        if term.lower() in query:
            msgs.append(f"  PASS: query contains '{term}' (query='{query[:60]}')")
            passed += 1
        else:
            msgs.append(f"  FAIL: query missing '{term}' (query='{query[:60]}')")
            failed += 1

    # Query NOT contains
    for term in expect.get("query_not_contains", []):
        if term.lower() not in query:
            msgs.append(f"  PASS: query does NOT contain '{term}' (query='{query[:60]}')")
            passed += 1
        else:
            msgs.append(f"  FAIL: query should NOT contain '{term}' (query='{query[:60]}')")
            failed += 1

    # Tools called contains
    for tool in expect.get("tools_called_contains", []):
        if tool in (tools_called or []):
            msgs.append(f"  PASS: {tool} was called")
            passed += 1
        else:
            msgs.append(f"  FAIL: {tool} was NOT called")
            failed += 1

    # Tools called NOT contains
    for tool in expect.get("tools_called_not_contains", []):
        if tool not in (tools_called or []):
            msgs.append(f"  PASS: {tool} was NOT called")
            passed += 1
        else:
            msgs.append(f"  FAIL: {tool} should NOT have been called")
            failed += 1

    return passed, failed, msgs


async def run_tests():
    from app.services.discussion_ai.openrouter_orchestrator import OpenRouterOrchestrator

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "pshalgiz@gmail.com").first()
        if not user:
            user = db.query(User).first()
            print(f"Using fallback user: {user.email}")

        project = db.query(Project).filter(Project.created_by == user.id).first()
        if not project:
            print("ERROR: No project found")
            return

        print(f"User: {user.email}")
        print(f"Project: {project.title} (id={project.id})")
        print(f"Project keywords: {project.keywords}")

        # Fresh channel
        channel = ProjectDiscussionChannel(
            project_id=project.id,
            name="Interactive_Test",
            slug="interactive-test",
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
        print(f"Channel: {channel.name} (id={channel.id})")

        orchestrator = OpenRouterOrchestrator(
            db=db,
            ai_service=None,
            model="openai/gpt-5-mini",
        )

        conversation_history = []
        total_passed = 0
        total_failed = 0
        step_results = []

        for i, test in enumerate(PROMPTS, 1):
            msg = test["msg"]
            label = test["label"]
            expect = test["expect"]

            separator(i, label)
            print(f"  Message: \"{msg}\"")

            # Clear per-step logs
            policy_logs.clear()
            search_args_logs.clear()
            turn_metrics_logs.clear()
            route_logs.clear()

            t0 = time.monotonic()

            try:
                result = orchestrator.handle_message(
                    project=project,
                    channel=channel,
                    message=msg,
                    conversation_history=conversation_history,
                    current_user=user,
                )
                elapsed = int((time.monotonic() - t0) * 1000)

                # Extract logs
                route_log = route_logs[-1] if route_logs else ""
                pd = extract_json(policy_logs[-1]) if policy_logs else None
                sa = extract_json(search_args_logs[-1]) if search_args_logs else None
                tools = result.get("tools_called", [])

                # Print summary
                if route_log:
                    route_part = route_log.split("] ")[-1] if "] " in route_log else route_log
                    print(f"  Route: {route_part}")
                if pd:
                    print(f"  Intent: {pd.get('intent')}")
                    search_info = pd.get("search", {})
                    if search_info.get("query"):
                        print(f"  Policy query: {search_info['query'][:70]}")
                if sa:
                    print(f"  Final query: {sa.get('query', '')[:70]}")
                    print(f"  Query source: {sa.get('query_source')}")
                    print(f"  Count: {sa.get('count')}, OA: {sa.get('open_access_only')}, Year: {sa.get('year_from')}-{sa.get('year_to')}")
                if tools:
                    print(f"  Tools: {tools}")

                ai_msg = result.get("message", "")[:150]
                print(f"  AI: {ai_msg}...")
                print(f"  Elapsed: {elapsed}ms")

                # Validate
                print(f"\n  --- Validation ---")
                p, f, validation_msgs = validate(i, expect, route_log, pd, sa, tools)
                for vm in validation_msgs:
                    print(vm)
                total_passed += p
                total_failed += f

                status = "PASSED" if f == 0 else "FAILED"
                step_results.append((i, label, status))
                print(f"\n  >>> STEP {i}: {status}")

                # Update conversation
                conversation_history.append({"role": "user", "content": msg})
                conversation_history.append({"role": "assistant", "content": result.get("message", "")})

                # Refresh channel for memory
                db.refresh(channel)

            except Exception as e:
                elapsed = int((time.monotonic() - t0) * 1000)
                print(f"  ERROR: {e}")
                import traceback
                traceback.print_exc()
                total_failed += 1
                step_results.append((i, label, "ERROR"))

        # ── Final Report ──────────────────────────────────────────────
        print(f"\n\n{'='*80}")
        print(f"  FINAL REPORT")
        print(f"{'='*80}")
        for num, label, status in step_results:
            icon = "✅" if status == "PASSED" else "❌"
            print(f"  {icon} Step {num:2d}: {label}")
        print(f"\n  Checks: {total_passed} passed, {total_failed} failed")
        print(f"  Steps:  {sum(1 for _,_,s in step_results if s=='PASSED')}/{len(step_results)} passed")
        print(f"{'='*80}")

        # Cleanup
        db.delete(channel)
        db.commit()
        print(f"  (Test channel cleaned up)")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run_tests())
