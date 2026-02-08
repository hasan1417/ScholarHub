"""
Full workflow test — realistic research session with test@test.com.

Simulates a complete workflow:
1. Search for papers on a topic
2. Search for more papers (follow-up)
3. Add papers to library
4. Compare papers
5. Create a document from the discussion

Run inside Docker:
    docker compose exec backend python tests/run_full_workflow_test.py
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


def separator(step_num, label):
    print(f"\n{'='*80}")
    print(f"  TURN {step_num}: {label}")
    print(f"{'='*80}")


def print_turn_summary(route_log, pd, sa, tools, ai_msg, elapsed):
    """Print a concise summary of the turn."""
    if route_log:
        parts = route_log.split("] ")
        print(f"  Route: {parts[-1] if len(parts) > 1 else route_log}")
    if pd:
        intent = pd.get("intent")
        if intent != "general":
            print(f"  Intent: {intent}")
    if sa:
        print(f"  Query: {sa.get('query', '')[:80]}")
        print(f"  Source: {sa.get('query_source', '')} | Count: {sa.get('count')} | OA: {sa.get('open_access_only')} | Year: {sa.get('year_from')}-{sa.get('year_to')}")
    if tools:
        print(f"  Tools: {tools}")
    print(f"  AI: {ai_msg[:200]}...")
    print(f"  Elapsed: {elapsed}ms")


# ── Conversation ──────────────────────────────────────────────────────

CONVERSATION = [
    # Phase 1: Warm up
    {
        "msg": "Hi! I'm working on a survey paper about attention mechanisms in transformers.",
        "label": "Introduction & research topic",
    },

    # Phase 2: Initial search
    {
        "msg": "Can you find me 5 recent papers on self-attention mechanisms in transformer models?",
        "label": "Initial search — 5 papers on self-attention",
    },

    # Phase 3: More papers (follow-up)
    {
        "msg": "Great, can you find another 3 papers on this topic?",
        "label": "Follow-up — 3 more papers (deictic)",
    },

    # Phase 4: Specific angle
    {
        "msg": "Now find me 4 papers specifically about efficient attention — like linear attention or sparse attention.",
        "label": "Specific sub-topic search",
    },

    # Phase 5: Add to library
    {
        "msg": "These look good. Please add all of them to my library.",
        "label": "Add papers to library",
    },

    # Phase 6: More papers with constraints
    {
        "msg": "Find 3 open access papers from 2023 to 2025 on attention mechanisms for long documents.",
        "label": "OA + year range + specific topic",
    },

    # Phase 7: Add those too
    {
        "msg": "Add these to my library as well.",
        "label": "Add more papers to library",
    },

    # Phase 8: Compare papers
    {
        "msg": "Can you compare the different attention approaches from the papers we've found? What are the main trade-offs between standard self-attention, sparse attention, and linear attention?",
        "label": "Compare papers — analysis request",
    },

    # Phase 9: Low-info test deep in convo
    {
        "msg": "Can you find more papers about my project?",
        "label": "Low-info 'about my project' — should resolve to context",
    },

    # Phase 10: Topic pivot
    {
        "msg": "Actually, I also want to cover the application of transformers in computer vision. Find me 3 papers on Vision Transformers (ViT).",
        "label": "Topic pivot — Vision Transformers",
    },

    # Phase 11: Relative follow-up after pivot
    {
        "msg": "Find 2 more on this.",
        "label": "Relative follow-up after topic pivot",
    },

    # Phase 12: Add everything
    {
        "msg": "Add all the new papers to my library.",
        "label": "Add all to library",
    },

    # Phase 13: Create a document
    {
        "msg": "Based on everything we've discussed, can you help me create a literature review section? Cover the main themes: standard self-attention, efficient attention variants, and vision transformers. Include key findings from the papers.",
        "label": "Create document / literature review",
    },

    # Phase 14: Follow-up on document
    {
        "msg": "That's a good start. Can you also add a comparison table summarizing the key papers, their methods, and contributions?",
        "label": "Follow-up document edit",
    },

    # Phase 15: Final
    {
        "msg": "Thanks, this is really helpful for my survey paper!",
        "label": "Final acknowledgment",
    },
]


async def run_full_workflow():
    from app.services.discussion_ai.openrouter_orchestrator import OpenRouterOrchestrator

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "test@test.com").first()
        if not user:
            print("ERROR: test@test.com not found")
            return

        project = db.query(Project).filter(
            Project.created_by == user.id,
            Project.title == "Machine Learning Research",
        ).first()
        if not project:
            print("ERROR: 'Machine Learning Research' project not found")
            return

        print(f"User: {user.email}")
        print(f"Project: {project.title}")
        print(f"Keywords: {project.keywords}")

        # Fresh channel with unique slug to avoid conflicts from killed runs
        import uuid
        test_id = uuid.uuid4().hex[:8]
        channel = ProjectDiscussionChannel(
            project_id=project.id,
            name=f"Full_Workflow_Test_{test_id}",
            slug=f"full-workflow-test-{test_id}",
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
            model="openai/gpt-4o-mini",
        )

        conversation_history = []
        turn_timings = []
        turn_tools = []
        errors = []

        # Cross-turn state: simulates what the frontend + API layer does
        last_search_id = None
        last_search_results = None

        for i, turn in enumerate(CONVERSATION, 1):
            msg = turn["msg"]
            label = turn["label"]

            separator(i, label)
            print(f"  User: \"{msg[:100]}{'...' if len(msg)>100 else ''}\"")

            # Clear per-turn logs
            policy_logs.clear()
            search_args_logs.clear()
            turn_metrics_logs.clear()
            route_logs.clear()

            t0 = time.monotonic()

            try:
                # Pass cross-turn search results (like the API layer does)
                result = orchestrator.handle_message(
                    project=project,
                    channel=channel,
                    message=msg,
                    recent_search_results=last_search_results,
                    recent_search_id=last_search_id,
                    conversation_history=conversation_history,
                    current_user=user,
                )
                elapsed = int((time.monotonic() - t0) * 1000)
                turn_timings.append(elapsed)

                route_log = route_logs[-1] if route_logs else ""
                pd = extract_json(policy_logs[-1]) if policy_logs else None
                sa = extract_json(search_args_logs[-1]) if search_args_logs else None
                tools = result.get("tools_called", [])
                ai_msg = result.get("message", "")
                turn_tools.append(tools)

                print_turn_summary(route_log, pd, sa, tools, ai_msg, elapsed)

                # Extract search_id from actions for cross-turn state
                # (simulates frontend receiving search results and sending
                #  recent_search_id back on the next request)
                actions = result.get("actions", [])
                for action in actions:
                    payload = action.get("payload", {})
                    if payload.get("search_id") and payload.get("papers"):
                        last_search_id = payload["search_id"]
                        last_search_results = payload["papers"]
                        print(f"  [CrossTurn] Captured search_id={last_search_id[:12]}... ({len(last_search_results)} papers)")

                # Update conversation
                conversation_history.append({"role": "user", "content": msg})
                conversation_history.append({"role": "assistant", "content": ai_msg})
                db.refresh(channel)

            except Exception as e:
                elapsed = int((time.monotonic() - t0) * 1000)
                turn_timings.append(elapsed)
                turn_tools.append([])
                errors.append((i, label, str(e)))
                print(f"  ERROR: {e}")
                import traceback
                traceback.print_exc()
                conversation_history.append({"role": "user", "content": msg})
                conversation_history.append({"role": "assistant", "content": f"Error: {e}"})

        # ── Memory state ──────────────────────────────────────────────
        print(f"\n\n{'='*80}")
        print(f"  FINAL MEMORY STATE")
        print(f"{'='*80}")
        db.refresh(channel)
        if channel.ai_memory:
            mem = channel.ai_memory if isinstance(channel.ai_memory, dict) else json.loads(channel.ai_memory)
            facts = mem.get("facts", {})
            ss = mem.get("search_state", {})
            rs = mem.get("research_state", {})
            print(f"  Research question: {facts.get('research_question', '(none)')[:100]}")
            print(f"  Research topic:    {facts.get('research_topic', '(none)')[:100]}")
            print(f"  Last search topic: {ss.get('last_effective_topic', '(none)')[:100]}")
            print(f"  Last count:        {ss.get('last_count', '(none)')}")
            print(f"  Stage:             {rs.get('stage', '(none)')}")
            lt = mem.get("long_term", {})
            if lt.get("session_summary"):
                print(f"  Session summary:   {lt['session_summary'][:200]}...")

        # ── Workflow summary ──────────────────────────────────────────
        print(f"\n{'='*80}")
        print(f"  WORKFLOW SUMMARY — {len(CONVERSATION)} turns")
        print(f"{'='*80}")

        all_tools_flat = []
        for i, (turn, tools, elapsed) in enumerate(zip(CONVERSATION, turn_tools, turn_timings), 1):
            tools_str = ", ".join(tools) if tools else "(none)"
            all_tools_flat.extend(tools)
            icon = "✅" if not any(e[0] == i for e in errors) else "❌"
            print(f"  {icon} Turn {i:2d} ({elapsed:5d}ms) [{tools_str}]: {turn['label']}")

        # Tool usage stats
        from collections import Counter
        tool_counts = Counter(all_tools_flat)
        print(f"\n  Tool usage:")
        for tool, count in tool_counts.most_common():
            print(f"    {tool}: {count}x")

        # Timing stats
        total_time = sum(turn_timings)
        avg_time = total_time // len(turn_timings) if turn_timings else 0
        print(f"\n  Timing:")
        print(f"    Total: {total_time/1000:.1f}s")
        print(f"    Average: {avg_time}ms per turn")
        print(f"    Fastest: {min(turn_timings)}ms")
        print(f"    Slowest: {max(turn_timings)}ms")

        if errors:
            print(f"\n  Errors ({len(errors)}):")
            for step, label, err in errors:
                print(f"    Turn {step} ({label}): {err[:100]}")
        else:
            print(f"\n  No errors!")

        print(f"{'='*80}")

        # Cleanup
        db.delete(channel)
        db.commit()
        print(f"  (Test channel cleaned up)")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run_full_workflow())
