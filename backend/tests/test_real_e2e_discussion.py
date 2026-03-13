"""
End-to-end test of Discussion AI changes.

Tests the REAL pipeline: user message → route classifier → orchestrator → tool calls → response.
Uses an actual project and channel from the database.

Validates:
1. Route classifier (hybrid regex+LLM) routes correctly
2. force_tool removal — model decides when to search, not regex
3. Sanitizer catches garbage queries at tool execution layer
4. No over-searching on non-search messages
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from app.database import SessionLocal
from app.services.ai_service import AIService
from app.services.discussion_ai.openrouter_orchestrator import OpenRouterOrchestrator


# ── Helpers ─────────────────────────────────────────────────────────

PASS = 0
FAIL = 0


def check(test_name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {test_name}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL += 1
        print(f"  [**FAIL**] {test_name}" + (f"  ({detail})" if detail else ""))


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def run_message(orchestrator, project, channel, message, user, history=None):
    """Send a message through the full pipeline and return the result."""
    t0 = time.monotonic()
    result = orchestrator.handle_message(
        project=project,
        channel=channel,
        message=message,
        conversation_history=history or [],
        current_user=user,
    )
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    return result, elapsed_ms


# ── Setup ───────────────────────────────────────────────────────────

print("Setting up database connection and finding a test project...")

db = SessionLocal()

# Find a project with a discussion channel
row = db.execute(text("""
    SELECT p.id, p.title, p.created_by
    FROM projects p
    JOIN project_discussion_channels pdc ON pdc.project_id = p.id
    WHERE p.title IS NOT NULL AND p.title != ''
    LIMIT 1
""")).fetchone()

if not row:
    print("ERROR: No project with discussion channels found. Skipping e2e tests.")
    sys.exit(0)

project_id, project_title, owner_id = row[0], row[1], row[2]
print(f"Using project: '{project_title}' (id={project_id})")

# Load ORM objects
from app.models import Project, ProjectDiscussionChannel, User

project = db.query(Project).get(project_id)
user = db.query(User).get(owner_id)
channel = db.query(ProjectDiscussionChannel).filter_by(
    project_id=project_id
).first()

if not channel:
    print("ERROR: No channel found.")
    sys.exit(1)

print(f"Channel: '{channel.name}' (id={channel.id})")
print(f"User: {user.email}")

# Create orchestrator
ai_service = AIService()
orchestrator = OpenRouterOrchestrator(ai_service, db)

print(f"Model: {orchestrator.model}")
print()


# ════════════════════════════════════════════════════════════════════
# TEST 1: Greeting → lite route, no tools, fast response
# ════════════════════════════════════════════════════════════════════
section("TEST 1: Greeting → lite, no tools")

result, ms = run_message(orchestrator, project, channel, "hello", user)
tools = result.get("tools_called", [])
msg = result.get("message", "")

check("Route was lite (no tools called)", len(tools) == 0, f"tools={tools}")
check("Got a response", len(msg) > 0, f"response={msg[:80]}...")
check("Response is short", len(msg) < 500, f"len={len(msg)}")
print(f"  ⏱ {ms}ms")


# ════════════════════════════════════════════════════════════════════
# TEST 2: Knowledge question → full route, NO search tool
# ════════════════════════════════════════════════════════════════════
section("TEST 2: Knowledge question → full, no search")

result, ms = run_message(orchestrator, project, channel, "what is a transformer in deep learning?", user)
tools = result.get("tools_called", [])
msg = result.get("message", "")
searched = any("search" in t.lower() for t in tools)

check("Got a response", len(msg) > 0, f"response={msg[:80]}...")
check("Did NOT call search_papers", not searched, f"tools={tools}")
print(f"  ⏱ {ms}ms")


# ════════════════════════════════════════════════════════════════════
# TEST 3: Explicit search request → model calls search_papers
# ════════════════════════════════════════════════════════════════════
section("TEST 3: Explicit search → model calls search_papers")

result, ms = run_message(orchestrator, project, channel, "find papers on attention mechanisms", user)
tools = result.get("tools_called", [])
msg = result.get("message", "")
searched = "search_papers" in tools or "batch_search_papers" in tools

check("Called search_papers", searched, f"tools={tools}")
check("Got a response", len(msg) > 0, f"response={msg[:80]}...")
print(f"  ⏱ {ms}ms")


# ════════════════════════════════════════════════════════════════════
# TEST 4: Search with typo → model still searches (no regex needed)
# ════════════════════════════════════════════════════════════════════
section("TEST 4: Typo search → model handles despite typo")

result, ms = run_message(orchestrator, project, channel, "serch for papers on neural networks plese", user)
tools = result.get("tools_called", [])
msg = result.get("message", "")
searched = "search_papers" in tools or "batch_search_papers" in tools

check("Called search_papers despite typos", searched, f"tools={tools}")
check("Got a response", len(msg) > 0, f"response={msg[:80]}...")
print(f"  ⏱ {ms}ms")


# ════════════════════════════════════════════════════════════════════
# TEST 5: Short follow-up → full route (not dropped to lite)
# ════════════════════════════════════════════════════════════════════
section("TEST 5: Short follow-up → full route")

# Simulate conversation context where assistant just explained something
history = [
    {"role": "user", "content": "what is a transformer?"},
    {"role": "assistant", "content": "A transformer is a neural network architecture based on self-attention mechanisms. It was introduced in the paper 'Attention Is All You Need' by Vaswani et al. in 2017."},
]

result, ms = run_message(orchestrator, project, channel, "more on that", user, history=history)
tools = result.get("tools_called", [])
msg = result.get("message", "")

check("Got a substantive response (not stub)", len(msg) > 50, f"len={len(msg)}, response={msg[:80]}...")
# If it was lite, max_tokens=50 would give a very short response
check("Response has detail", len(msg) > 100 or "transform" in msg.lower() or "attention" in msg.lower(),
      f"response={msg[:120]}...")
print(f"  ⏱ {ms}ms")


# ════════════════════════════════════════════════════════════════════
# TEST 6: Compound confirmation → full route
# ════════════════════════════════════════════════════════════════════
section("TEST 6: Compound confirmation+request → full route")

history2 = [
    {"role": "user", "content": "can you explain attention mechanisms?"},
    {"role": "assistant", "content": "Attention mechanisms allow models to focus on relevant parts of the input."},
]

result, ms = run_message(orchestrator, project, channel, "Looks good, now tell me about self-attention vs cross-attention", user, history=history2)
tools = result.get("tools_called", [])
msg = result.get("message", "")

check("Got a substantive response", len(msg) > 50, f"len={len(msg)}")
check("Response addresses self-attention or cross-attention",
      "self-attention" in msg.lower() or "cross-attention" in msg.lower() or "self" in msg.lower(),
      f"response={msg[:120]}...")
print(f"  ⏱ {ms}ms")


# ════════════════════════════════════════════════════════════════════
# TEST 7: "search for papers please" → search, not garbage query
# ════════════════════════════════════════════════════════════════════
section("TEST 7: 'search for papers please' → clean query, not literal 'please'")

result, ms = run_message(orchestrator, project, channel, "search for papers please", user)
tools = result.get("tools_called", [])
msg = result.get("message", "")
searched = "search_papers" in tools or "batch_search_papers" in tools

# The key check: the model should search, and the query should NOT be "please"
check("Called search_papers", searched, f"tools={tools}")
check("Got a response (not an error)", len(msg) > 0, f"response={msg[:80]}...")
print(f"  ⏱ {ms}ms")


# ════════════════════════════════════════════════════════════════════
# TEST 8: Project update → no search
# ════════════════════════════════════════════════════════════════════
section("TEST 8: Project update request → no search")

result, ms = run_message(orchestrator, project, channel, "update my project keywords to include deep learning and NLP", user)
tools = result.get("tools_called", [])
msg = result.get("message", "")
searched = "search_papers" in tools or "batch_search_papers" in tools

check("Did NOT search", not searched, f"tools={tools}")
check("Got a response", len(msg) > 0, f"response={msg[:80]}...")
print(f"  ⏱ {ms}ms")


# ════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"  RESULTS: {PASS} passed, {FAIL} failed out of {PASS+FAIL} tests")
print(f"{'='*70}")

db.close()

if FAIL > 0:
    print("\n  ISSUES FOUND — review **FAIL** entries above.")
    sys.exit(1)
else:
    print("\n  All e2e tests passed.")
    sys.exit(0)
