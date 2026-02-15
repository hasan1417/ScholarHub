"""
Long conversation test — simulates a realistic 20+ turn session.

Tests:
- Memory accumulation over many turns
- Topic switching mid-conversation
- Context resolution after many messages
- Lite/full routing consistency across a long session
- Performance degradation check (latency per turn)

Run inside Docker:
    docker compose exec backend python tests/run_long_conversation_test.py
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


def extract_json(log_line):
    idx = log_line.find("{")
    if idx >= 0:
        try:
            return json.loads(log_line[idx:])
        except json.JSONDecodeError:
            pass
    return None


def separator(step_num, msg):
    print(f"\n{'─'*80}")
    print(f"  TURN {step_num}: {msg[:70]}")
    print(f"{'─'*80}")


# ── Conversation script ───────────────────────────────────────────────
# Simulates a realistic research session with topic evolution

CONVERSATION = [
    # Phase 1: Opening & research question setup
    {
        "msg": "Hello!",
        "checks": {"route": "lite"},
        "label": "Greeting",
    },
    {
        "msg": "I'm working on my thesis about the impact of social media on mental health among adolescents.",
        "checks": {"intent": "general"},
        "label": "Research statement (long)",
    },
    {
        "msg": "That's a broad topic, I know. I want to focus specifically on Instagram and TikTok usage.",
        "checks": {"intent": "general"},
        "label": "Narrowing scope",
    },
    {
        "msg": "ok sounds good",
        "checks": {"route": "lite"},
        "label": "Acknowledgment",
    },

    # Phase 2: First search round
    {
        "msg": "Can you find me 5 recent papers on this topic?",
        "checks": {
            "intent": "direct_search",
            "count": 5,
            "query_not_literal": ["this topic", "5 recent papers"],
        },
        "label": "Deictic search — should resolve from memory",
    },
    {
        "msg": "Great, thanks for those!",
        "checks": {"route": "lite"},
        "label": "Acknowledgment after search",
    },
    {
        "msg": "Can you find another 3 papers?",
        "checks": {
            "intent": "direct_search",
            "count": 3,
            "query_not_literal": ["another 3 papers"],
        },
        "label": "Relative follow-up — carry-over topic",
    },
    {
        "msg": "nice",
        "checks": {"route": "lite"},
        "label": "Short acknowledgment",
    },

    # Phase 3: Refinement & specific searches
    {
        "msg": "Find 4 open access papers from 2023 to 2025 on social media addiction in teenagers.",
        "checks": {
            "intent": "direct_search",
            "count": 4,
            "oa": True,
            "year_from": 2023,
            "year_to": 2025,
            "query_contains": ["social media"],
        },
        "label": "Explicit topic + OA + year range",
    },
    {
        "msg": "I see, those are useful.",
        "checks": {"route": "lite"},
        "label": "Acknowledgment mid-conversation",
    },

    # Phase 4: Project management
    {
        "msg": "Update project keywords to social media, mental health, adolescents, Instagram, TikTok.",
        "checks": {
            "intent": "project_update",
            "no_search": True,
        },
        "label": "Project update",
    },
    {
        "msg": "perfect",
        "checks": {"route": "lite"},
        "label": "Acknowledgment after update",
    },

    # Phase 5: Topic switch
    {
        "msg": "Actually, I also need to review literature on cyberbullying prevention programs.",
        "checks": {"intent": "general"},
        "label": "Topic switch statement",
    },
    {
        "msg": "Can you find papers on cyberbullying prevention in schools?",
        "checks": {
            "intent": "direct_search",
            "query_contains": ["cyberbullying"],
        },
        "label": "New explicit topic search",
    },
    {
        "msg": "Find 2 more on this.",
        "checks": {
            "intent": "direct_search",
            "count": 2,
            "query_not_literal": ["2 more on this", "more on this"],
        },
        "label": "Relative after topic switch — should carry new topic",
    },

    # Phase 6: Low-info queries deep in conversation
    {
        "msg": "Can you find papers about my project?",
        "checks": {
            "intent": "direct_search",
            "query_not_literal": ["my project", "about my project"],
        },
        "label": "Low-info 'my project' — deep in conversation",
    },
    {
        "msg": "Can you find papers about my research?",
        "checks": {
            "intent": "direct_search",
            "query_not_literal": ["my research", "about my research"],
        },
        "label": "Low-info 'my research' — deep in conversation",
    },
    {
        "msg": "thanks, that really helps",
        "checks": {"route": "lite"},
        "label": "Acknowledgment",
    },

    # Phase 7: Back to original topic
    {
        "msg": "Going back to the social media mental health angle — can you find 3 papers specifically about Instagram's effect on body image?",
        "checks": {
            "intent": "direct_search",
            "count": 3,
            "query_contains": ["instagram"],
        },
        "label": "Return to original topic with specificity",
    },
    {
        "msg": "Can you find another 2 papers?",
        "checks": {
            "intent": "direct_search",
            "count": 2,
            "query_not_literal": ["another 2 papers"],
        },
        "label": "Relative again — should carry Instagram topic",
    },
    {
        "msg": "ok I think that's enough papers for now",
        "checks": {"route": "lite"},
        "label": "Wrap-up acknowledgment",
    },

    # Phase 8: Late-session searches
    {
        "msg": "Find me 5 papers on digital wellbeing interventions for young adults from 2022 to 2026.",
        "checks": {
            "intent": "direct_search",
            "count": 5,
            "year_from": 2022,
            "year_to": 2026,
            "query_contains": ["digital wellbeing"],
        },
        "label": "Late-session explicit search with year range",
    },
    {
        "msg": "Find 3 open access papers on this topic.",
        "checks": {
            "intent": "direct_search",
            "count": 3,
            "oa": True,
            "query_not_literal": ["this topic", "3 open access papers"],
        },
        "label": "Deictic + OA late in conversation",
    },
    {
        "msg": "Thanks for all the help today!",
        "checks": {"route": "lite"},
        "label": "Final farewell",
    },
]


def validate_turn(turn_num, checks, route_log, pd, sa, tools, elapsed_ms):
    """Validate a single turn. Returns (pass_count, fail_count, messages)."""
    p, f, msgs = 0, 0, []

    # Route
    if "route" in checks:
        actual = None
        if route_log:
            parts = route_log.split("route=")
            if len(parts) > 1:
                actual = parts[1].split()[0]
        if actual == checks["route"]:
            msgs.append(f"  ✅ route={actual}")
            p += 1
        else:
            msgs.append(f"  ❌ Expected route={checks['route']}, got {actual}")
            f += 1

    # Intent
    if "intent" in checks:
        actual = pd.get("intent") if pd else None
        if actual == checks["intent"]:
            msgs.append(f"  ✅ intent={actual}")
            p += 1
        else:
            msgs.append(f"  ❌ Expected intent={checks['intent']}, got {actual}")
            f += 1

    # Count
    if "count" in checks:
        actual = (sa or {}).get("count")
        if actual == checks["count"]:
            msgs.append(f"  ✅ count={actual}")
            p += 1
        else:
            msgs.append(f"  ❌ Expected count={checks['count']}, got {actual}")
            f += 1

    # OA
    if "oa" in checks:
        actual = (sa or {}).get("open_access_only")
        if actual == checks["oa"]:
            msgs.append(f"  ✅ OA={actual}")
            p += 1
        else:
            msgs.append(f"  ❌ Expected OA={checks['oa']}, got {actual}")
            f += 1

    # Year
    for key in ("year_from", "year_to"):
        if key in checks:
            actual = (sa or {}).get(key)
            if actual == checks[key]:
                msgs.append(f"  ✅ {key}={actual}")
                p += 1
            else:
                msgs.append(f"  ❌ Expected {key}={checks[key]}, got {actual}")
                f += 1

    # Query contains
    query = ((sa or {}).get("query") or "").lower()
    for term in checks.get("query_contains", []):
        if term.lower() in query:
            msgs.append(f"  ✅ query contains '{term}'")
            p += 1
        else:
            msgs.append(f"  ❌ query missing '{term}' (got: '{query[:60]}')")
            f += 1

    # Query NOT literal
    for term in checks.get("query_not_literal", []):
        if term.lower() not in query:
            msgs.append(f"  ✅ query ≠ '{term}'")
            p += 1
        else:
            msgs.append(f"  ❌ query contains literal '{term}' (got: '{query[:60]}')")
            f += 1

    # No search tools
    if checks.get("no_search"):
        if "search_papers" not in (tools or []):
            msgs.append(f"  ✅ search_papers NOT called")
            p += 1
        else:
            msgs.append(f"  ❌ search_papers was called unexpectedly")
            f += 1

    return p, f, msgs


async def run_long_test():
    from app.services.discussion_ai.openrouter_orchestrator import OpenRouterOrchestrator

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "pshalgiz@gmail.com").first()
        if not user:
            user = db.query(User).first()

        project = db.query(Project).filter(Project.created_by == user.id).first()
        if not project:
            print("ERROR: No project found")
            return

        print(f"User: {user.email}")
        print(f"Project: {project.title} (keywords: {project.keywords})")

        channel = ProjectDiscussionChannel(
            project_id=project.id,
            name="Long_Conversation_Test",
            slug="long-convo-test",
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
        print(f"Total turns: {len(CONVERSATION)}")

        orchestrator = OpenRouterOrchestrator(
            db=db,
            ai_service=None,
            model="openai/gpt-5-mini",
        )

        conversation_history = []
        total_passed = 0
        total_failed = 0
        turn_results = []
        turn_timings = []

        for i, turn in enumerate(CONVERSATION, 1):
            msg = turn["msg"]
            checks = turn["checks"]
            label = turn["label"]

            separator(i, f"{label}  →  \"{msg[:50]}\"")

            # Clear per-turn logs
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
                turn_timings.append(elapsed)

                route_log = route_logs[-1] if route_logs else ""
                pd = extract_json(policy_logs[-1]) if policy_logs else None
                sa = extract_json(search_args_logs[-1]) if search_args_logs else None
                tools = result.get("tools_called", [])

                # Print summary
                route_reason = ""
                if route_log:
                    parts = route_log.split("] ")
                    route_reason = parts[-1] if len(parts) > 1 else route_log
                    print(f"  Route: {route_reason}")

                if pd and pd.get("intent") != "general":
                    print(f"  Intent: {pd.get('intent')}")
                if sa:
                    print(f"  Query: {sa.get('query', '')[:70]}")
                    src = sa.get("query_source", "")
                    if src:
                        print(f"  Source: {src}")
                if tools:
                    print(f"  Tools: {tools}")

                ai_msg = result.get("message", "")[:120]
                print(f"  AI: {ai_msg}...")
                print(f"  Time: {elapsed}ms | History: {len(conversation_history)} msgs")

                # Validate
                p, f_count, validation_msgs = validate_turn(i, checks, route_log, pd, sa, tools, elapsed)
                for vm in validation_msgs:
                    print(vm)
                total_passed += p
                total_failed += f_count

                status = "PASS" if f_count == 0 else "FAIL"
                turn_results.append((i, label, status, elapsed))

                # Update conversation history
                conversation_history.append({"role": "user", "content": msg})
                conversation_history.append({"role": "assistant", "content": result.get("message", "")})
                db.refresh(channel)

            except Exception as e:
                elapsed = int((time.monotonic() - t0) * 1000)
                print(f"  ❌ ERROR: {e}")
                import traceback
                traceback.print_exc()
                total_failed += 1
                turn_results.append((i, label, "ERROR", elapsed))
                turn_timings.append(elapsed)
                # Still add to history so conversation continues
                conversation_history.append({"role": "user", "content": msg})
                conversation_history.append({"role": "assistant", "content": f"Error: {e}"})

        # ── Memory state dump ─────────────────────────────────────────
        print(f"\n\n{'='*80}")
        print(f"  FINAL MEMORY STATE")
        print(f"{'='*80}")
        db.refresh(channel)
        if channel.ai_memory:
            mem = channel.ai_memory if isinstance(channel.ai_memory, dict) else json.loads(channel.ai_memory)
            facts = mem.get("facts", {})
            ss = mem.get("search_state", {})
            rs = mem.get("research_state", {})
            print(f"  Research question: {facts.get('research_question', '(none)')[:80]}")
            print(f"  Research topic:    {facts.get('research_topic', '(none)')[:80]}")
            print(f"  Last search topic: {ss.get('last_effective_topic', '(none)')[:80]}")
            print(f"  Last count:        {ss.get('last_count', '(none)')}")
            print(f"  Stage:             {rs.get('stage', '(none)')}")
            lt = mem.get("long_term", {})
            if lt.get("session_summary"):
                print(f"  Session summary:   {lt['session_summary'][:120]}...")

        # ── Performance report ────────────────────────────────────────
        print(f"\n{'='*80}")
        print(f"  PERFORMANCE REPORT")
        print(f"{'='*80}")
        lite_times = [t for (_, _, s, t) in turn_results if s == "PASS" and t < 2000]
        full_times = [t for (_, _, s, t) in turn_results if s == "PASS" and t >= 2000]
        print(f"  Lite turns avg: {sum(lite_times)//max(len(lite_times),1)}ms ({len(lite_times)} turns)")
        print(f"  Full turns avg: {sum(full_times)//max(len(full_times),1)}ms ({len(full_times)} turns)")

        # Check for latency degradation
        if len(turn_timings) >= 6:
            first_half = turn_timings[:len(turn_timings)//2]
            second_half = turn_timings[len(turn_timings)//2:]
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)
            ratio = avg_second / max(avg_first, 1)
            if ratio > 2.0:
                print(f"  ⚠️  Latency degradation: 2nd half {ratio:.1f}x slower ({avg_second:.0f}ms vs {avg_first:.0f}ms)")
            else:
                print(f"  ✅ No significant latency degradation ({ratio:.1f}x, {avg_second:.0f}ms vs {avg_first:.0f}ms)")

        # ── Final report ──────────────────────────────────────────────
        print(f"\n{'='*80}")
        print(f"  FINAL REPORT — {len(CONVERSATION)}-turn conversation")
        print(f"{'='*80}")
        for num, label, status, elapsed in turn_results:
            icon = "✅" if status == "PASS" else "❌"
            print(f"  {icon} Turn {num:2d} ({elapsed:5d}ms): {label}")
        passed_count = sum(1 for _, _, s, _ in turn_results if s == "PASS")
        print(f"\n  Turns:  {passed_count}/{len(turn_results)} passed")
        print(f"  Checks: {total_passed} passed, {total_failed} failed")
        print(f"  Total conversation time: {sum(turn_timings)/1000:.1f}s")
        print(f"{'='*80}")

        # Cleanup
        db.delete(channel)
        db.commit()
        print(f"  (Test channel cleaned up)")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run_long_test())
