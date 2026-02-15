#!/usr/bin/env python3
"""
Manual smoke test for Editor AI hardening patches.

Runs real API calls through SmartAgentServiceV2OR to verify:
  - Fix 1: Inheritance — V2OR inherits helpers from V2, no duplicated methods
  - Fix 2: Retry logic — _is_retryable and retry constants exist and work
  - Fix 3: print() replaced with logger — no print() in source files
  - Fix 4: Bare except fixed — _semantic_search uses specific exception types
  - Fix 5: Deterministic helpers still work end-to-end through inheritance

Requires:
  - Running inside docker compose (needs DB access):
      docker compose exec backend python tests/test_editor_ai_patches.py

  - OR locally with OPENROUTER_API_KEY set (DB tests skipped):
      cd backend && OPENROUTER_API_KEY=sk-... python tests/test_editor_ai_patches.py

Options:
  --model MODEL    OpenRouter model to use (default: openai/gpt-5-mini)
  --live           Run live API + DB tests (requires docker compose)
  --skip-live      Skip live tests, only run structural checks (default)
"""

from __future__ import annotations

import argparse
import inspect
import logging
import os
import re
import sys
import time
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("patch_test")


# ── ANSI helpers ──────────────────────────────────────────────────────

class C:
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    DIM    = "\033[2m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"


def ok(label: str, detail: str = ""):
    print(f"  {C.GREEN}PASS{C.RESET}  {label}{C.DIM}  {detail}{C.RESET}")


def fail(label: str, detail: str = ""):
    print(f"  {C.RED}FAIL{C.RESET}  {label}  {detail}")


def warn(label: str, detail: str = ""):
    print(f"  {C.YELLOW}WARN{C.RESET}  {label}  {detail}")


def section(title: str):
    print(f"\n{C.BOLD}{C.CYAN}── {title} ──{C.RESET}")


# ── Sample document ──────────────────────────────────────────────────

SAMPLE_LATEX = r"""\documentclass{article}
\usepackage{amsmath}
\title{Adaptive Gradient Methods for LLM Training}
\author{Alice Chen \and Bob Martinez}
\date{2026}
\begin{document}
\maketitle

\begin{abstract}
Large language models have achieved remarkable performance. However, training
these models remain computationally expensive. We propose AdaptGrad, an
adaptive gradient method that dynamicaly adjusts learning rates.
\end{abstract}

\section{Introduction}
The scaling of language models has led to significant advances in NLP.

\section{Method}
We introduce AdaptGrad which computes per-parameter learning rates.

\section{Results}
Our experiments show a 23\% reduction in training time.

\section{Conclusion}
AdaptGrad is effective for large-scale training.

\end{document}
"""


# ── Structural checks (no API calls needed) ─────────────────────────

def check_fix1_inheritance() -> List[str]:
    """Fix 1: V2OR inherits from V2, no duplicated methods."""
    section("Fix 1: Inheritance (V2OR subclass of V2)")
    errors = []

    from app.services.smart_agent_service_v2 import SmartAgentServiceV2
    from app.services.smart_agent_service_v2_or import SmartAgentServiceV2OR

    # Check subclass relationship
    if issubclass(SmartAgentServiceV2OR, SmartAgentServiceV2):
        ok("SmartAgentServiceV2OR inherits from SmartAgentServiceV2")
    else:
        fail("SmartAgentServiceV2OR does NOT inherit from SmartAgentServiceV2")
        errors.append("inheritance")

    # Check that duplicated methods are NOT in V2OR's own __dict__
    should_be_inherited = [
        "_build_clarification",
        "_detect_operation",
        "_detect_target",
        "_has_constraints",
        "_is_convert_request",
        "_has_explicit_replacement",
        "_is_review_message",
        "_rewrite_affirmation",
        "_sanitize_assistant_content",
        "_format_tool_response",
        "_handle_list_templates",
        "_handle_apply_template",
        "_add_line_numbers",
    ]

    v2or_own = set(SmartAgentServiceV2OR.__dict__.keys())
    for method in should_be_inherited:
        if method in v2or_own:
            fail(f"{method} is still defined in V2OR (should be inherited)")
            errors.append(f"duplicate:{method}")
        else:
            # Verify it's accessible via inheritance
            if hasattr(SmartAgentServiceV2OR, method):
                ok(f"{method} inherited from V2")
            else:
                fail(f"{method} missing entirely!")
                errors.append(f"missing:{method}")

    # Check V2OR-only methods exist
    should_be_own = [
        "stream_query", "_stream_llm_call", "_emit_status",
        "_resolve_tool_choice", "_get_recent_history",
        "_store_chat_exchange", "_is_retryable",
    ]
    for method in should_be_own:
        if method in v2or_own:
            ok(f"{method} defined in V2OR (override/own)")
        else:
            warn(f"{method} not in V2OR's own dict", "(may be a class attr)")

    # Verify inherited helpers work on V2OR instances
    svc = SmartAgentServiceV2OR(user_api_key="dummy-not-used")
    result = svc._detect_operation("fix grammar in the abstract")
    if result == "fix":
        ok("_detect_operation works via inheritance", f"result={result}")
    else:
        fail("_detect_operation via inheritance returned unexpected", str(result))
        errors.append("detect_operation")

    result = svc._build_clarification("improve the abstract", SAMPLE_LATEX)
    if result and "options" in result:
        ok("_build_clarification works via inheritance", f"question={result.get('question', '')[:50]}")
    else:
        fail("_build_clarification via inheritance unexpected result", str(result))
        errors.append("build_clarification")

    fmt = "".join(svc._format_tool_response("answer_question", {"answer": "Test answer"}))
    if fmt == "Test answer":
        ok("_format_tool_response works via inheritance")
    else:
        fail("_format_tool_response via inheritance unexpected", repr(fmt[:50]))
        errors.append("format_tool_response")

    return errors


def check_fix2_retry() -> List[str]:
    """Fix 2: Retry constants and _is_retryable exist."""
    section("Fix 2: Retry with exponential backoff")
    errors = []

    from app.services.smart_agent_service_v2_or import SmartAgentServiceV2OR

    # Check retry constants
    if hasattr(SmartAgentServiceV2OR, "_MAX_RETRIES") and SmartAgentServiceV2OR._MAX_RETRIES == 3:
        ok("_MAX_RETRIES = 3")
    else:
        fail("_MAX_RETRIES missing or wrong")
        errors.append("max_retries")

    if hasattr(SmartAgentServiceV2OR, "_INITIAL_BACKOFF") and SmartAgentServiceV2OR._INITIAL_BACKOFF == 1.0:
        ok("_INITIAL_BACKOFF = 1.0")
    else:
        fail("_INITIAL_BACKOFF missing or wrong")
        errors.append("initial_backoff")

    expected_codes = {429, 500, 502, 503, 504}
    if hasattr(SmartAgentServiceV2OR, "_RETRYABLE_STATUS_CODES") and SmartAgentServiceV2OR._RETRYABLE_STATUS_CODES == expected_codes:
        ok(f"_RETRYABLE_STATUS_CODES = {expected_codes}")
    else:
        fail("_RETRYABLE_STATUS_CODES missing or wrong")
        errors.append("retryable_codes")

    # Check _is_retryable
    import httpx
    from openai import RateLimitError, APIConnectionError, APITimeoutError, APIStatusError

    # 429 → retryable
    resp429 = httpx.Response(429, request=httpx.Request("POST", "https://x.com"), json={"error": {"message": "rate limit"}})
    err429 = RateLimitError("rate limited", response=resp429, body={})
    if SmartAgentServiceV2OR._is_retryable(err429):
        ok("RateLimitError (429) is retryable")
    else:
        fail("RateLimitError should be retryable")
        errors.append("429_retryable")

    # 502 → retryable
    resp502 = httpx.Response(502, request=httpx.Request("POST", "https://x.com"), json={"error": {"message": "bad gateway"}})
    err502 = APIStatusError("bad gateway", response=resp502, body={})
    if SmartAgentServiceV2OR._is_retryable(err502):
        ok("APIStatusError (502) is retryable")
    else:
        fail("502 should be retryable")
        errors.append("502_retryable")

    # 400 → NOT retryable
    resp400 = httpx.Response(400, request=httpx.Request("POST", "https://x.com"), json={"error": {"message": "bad request"}})
    err400 = APIStatusError("bad request", response=resp400, body={})
    if not SmartAgentServiceV2OR._is_retryable(err400):
        ok("APIStatusError (400) is NOT retryable")
    else:
        fail("400 should NOT be retryable")
        errors.append("400_not_retryable")

    # ValueError → NOT retryable
    if not SmartAgentServiceV2OR._is_retryable(ValueError("nope")):
        ok("ValueError is NOT retryable")
    else:
        fail("ValueError should NOT be retryable")
        errors.append("valueerror")

    # Check retry guard in stream_query source
    source = inspect.getsource(SmartAgentServiceV2OR.stream_query)
    if "tokens_already_sent" in source:
        ok("Retry guard: tokens_already_sent check present in stream_query")
    else:
        fail("Missing tokens_already_sent guard in retry loop")
        errors.append("retry_guard")

    if "_is_retryable" in source:
        ok("_is_retryable called in stream_query")
    else:
        fail("_is_retryable not referenced in stream_query")
        errors.append("retryable_call")

    return errors


def check_fix3_no_print() -> List[str]:
    """Fix 3: No print() statements in V2 source."""
    section("Fix 3: print() replaced with logger")
    errors = []

    v2_path = os.path.join(os.path.dirname(__file__), "..", "app", "services", "smart_agent_service_v2.py")
    with open(v2_path, "r") as f:
        v2_source = f.read()

    # Find print() calls that aren't in comments or strings
    print_calls = []
    for i, line in enumerate(v2_source.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("print(") or "  print(" in line or "\tprint(" in line:
            # Check it's not inside a string
            if "print(" in line and not line.strip().startswith('"') and not line.strip().startswith("'"):
                print_calls.append((i, stripped[:80]))

    if not print_calls:
        ok("No print() calls in smart_agent_service_v2.py")
    else:
        for lineno, content in print_calls:
            fail(f"print() at line {lineno}", content)
        errors.append("print_found")

    # Check logger is used instead
    if "logger.debug" in v2_source:
        ok("logger.debug() used in V2", "(replaced print)")
    else:
        warn("No logger.debug() found in V2")

    return errors


def check_fix4_bare_except() -> List[str]:
    """Fix 4: No bare except: in _semantic_search."""
    section("Fix 4: Bare except fixed in _semantic_search")
    errors = []

    v2or_path = os.path.join(os.path.dirname(__file__), "..", "app", "services", "smart_agent_service_v2_or.py")
    with open(v2or_path, "r") as f:
        v2or_source = f.read()

    # Check for bare except: anywhere in file
    bare_except_pattern = re.compile(r"^\s+except\s*:\s*(#.*)?$", re.MULTILINE)
    matches = bare_except_pattern.findall(v2or_source)
    if not matches:
        ok("No bare 'except:' in smart_agent_service_v2_or.py")
    else:
        fail(f"Found {len(matches)} bare except: statement(s)")
        errors.append("bare_except")

    # Verify _semantic_search uses specific exception types
    source = inspect.getsource(
        __import__("app.services.smart_agent_service_v2_or", fromlist=["SmartAgentServiceV2OR"]).SmartAgentServiceV2OR._semantic_search
    )
    if "except (ValueError, TypeError, KeyError)" in source:
        ok("_semantic_search uses except (ValueError, TypeError, KeyError)")
    else:
        fail("_semantic_search exception handling unexpected")
        errors.append("semantic_search_except")

    return errors


def check_fix5_class_attrs() -> List[str]:
    """Fix 5: Shared class attributes accessible on V2OR via inheritance."""
    section("Fix 5: Shared class attributes via inheritance")
    errors = []

    from app.services.smart_agent_service_v2 import SmartAgentServiceV2
    from app.services.smart_agent_service_v2_or import SmartAgentServiceV2OR

    # Check class attrs accessible on V2OR
    svc = SmartAgentServiceV2OR(user_api_key="dummy")

    if hasattr(svc, "_LITE_SYSTEM_PROMPT") and "ScholarHub" in svc._LITE_SYSTEM_PROMPT:
        ok("_LITE_SYSTEM_PROMPT accessible via inheritance")
    else:
        fail("_LITE_SYSTEM_PROMPT not accessible on V2OR")
        errors.append("lite_prompt")

    if hasattr(svc, "_EDITOR_ACTION_VERBS") and svc._EDITOR_ACTION_VERBS.search("improve"):
        ok("_EDITOR_ACTION_VERBS accessible via inheritance")
    else:
        fail("_EDITOR_ACTION_VERBS not accessible on V2OR")
        errors.append("action_verbs")

    if hasattr(svc, "_QUESTION_PREFIXES") and "what" in svc._QUESTION_PREFIXES:
        ok("_QUESTION_PREFIXES accessible via inheritance")
    else:
        fail("_QUESTION_PREFIXES not accessible on V2OR")
        errors.append("question_prefixes")

    if hasattr(svc, "_TARGET_TERMS") and "abstract" in svc._TARGET_TERMS:
        ok("_TARGET_TERMS accessible via inheritance")
    else:
        fail("_TARGET_TERMS not accessible on V2OR")
        errors.append("target_terms")

    return errors


# ── Live API + DB tests ──────────────────────────────────────────────

def check_live_greeting(db, user_id: str, paper_id: str, project_id: str, model: str, api_key: str) -> List[str]:
    """Live test: greeting takes lite route."""
    section("Live: Lite route (greeting)")
    errors = []

    from app.services.smart_agent_service_v2_or import SmartAgentServiceV2OR
    agent = SmartAgentServiceV2OR(model=model, user_api_key=api_key)

    t0 = time.monotonic()
    response = "".join(agent.stream_query(
        db=db, user_id=user_id, query="Hello!",
        paper_id=paper_id, project_id=project_id,
        document_excerpt=SAMPLE_LATEX,
    ))
    ms = int((time.monotonic() - t0) * 1000)

    # Strip status markers for display
    clean = re.sub(r"\[\[\[STATUS:.*?\]\]\]", "", response).strip()
    tools = getattr(agent, "_last_tools_called", [])

    if clean:
        ok(f"Got response ({ms}ms)", clean[:80])
    else:
        fail("Empty response for greeting")
        errors.append("greeting_empty")

    if not tools:
        ok("No tools called (lite route confirmed)")
    else:
        warn("Tools called for greeting", str(tools))

    return errors


def check_live_question(db, user_id: str, paper_id: str, project_id: str, model: str, api_key: str) -> List[str]:
    """Live test: question about paper → answer_question tool."""
    section("Live: Question about paper")
    errors = []

    from app.services.smart_agent_service_v2_or import SmartAgentServiceV2OR
    agent = SmartAgentServiceV2OR(model=model, user_api_key=api_key)

    t0 = time.monotonic()
    response = "".join(agent.stream_query(
        db=db, user_id=user_id,
        query="What is the main contribution of this paper?",
        paper_id=paper_id, project_id=project_id,
        document_excerpt=SAMPLE_LATEX,
    ))
    ms = int((time.monotonic() - t0) * 1000)

    clean = re.sub(r"\[\[\[STATUS:.*?\]\]\]", "", response).strip()
    tools = getattr(agent, "_last_tools_called", [])

    if clean and len(clean) > 20:
        ok(f"Got answer ({ms}ms, {len(clean)} chars)", clean[:80])
    else:
        fail("Answer too short or empty", repr(clean[:50]))
        errors.append("question_short")

    if "answer_question" in tools:
        ok("answer_question tool called")
    elif tools:
        warn(f"Expected answer_question, got {tools}")
    else:
        warn("No tools called (content-only response)")

    # Should mention AdaptGrad or gradient or training
    lower = clean.lower()
    if any(kw in lower for kw in ("adaptgrad", "gradient", "training", "learning rate")):
        ok("Answer references paper content")
    else:
        warn("Answer may not reference paper content")

    return errors


def check_live_edit(db, user_id: str, paper_id: str, project_id: str, model: str, api_key: str) -> List[str]:
    """Live test: edit request → propose_edit tool with <<<EDIT>>> markers."""
    section("Live: Edit request (fix grammar)")
    errors = []

    from app.services.smart_agent_service_v2_or import SmartAgentServiceV2OR
    agent = SmartAgentServiceV2OR(model=model, user_api_key=api_key)

    t0 = time.monotonic()
    response = "".join(agent.stream_query(
        db=db, user_id=user_id,
        query="Fix grammar and typos in the abstract",
        paper_id=paper_id, project_id=project_id,
        document_excerpt=SAMPLE_LATEX,
    ))
    ms = int((time.monotonic() - t0) * 1000)

    clean = re.sub(r"\[\[\[STATUS:.*?\]\]\]", "", response).strip()
    tools = getattr(agent, "_last_tools_called", [])

    if "propose_edit" in tools:
        ok("propose_edit tool called")
    else:
        warn(f"Expected propose_edit, got {tools}")

    if "<<<EDIT>>>" in clean:
        ok(f"Edit markers present in response ({ms}ms)")
    else:
        warn("No <<<EDIT>>> markers in response", clean[:80])

    if "<<<PROPOSED>>>" in clean:
        ok("<<<PROPOSED>>> marker present")
    else:
        warn("No <<<PROPOSED>>> marker")

    # Should fix "remain" → "remains" and "dynamicaly" → "dynamically"
    if "remains" in clean or "dynamically" in clean:
        ok("Typos appear to be fixed in proposed edit")
    else:
        warn("Expected typo fixes not detected in response")

    return errors


def check_live_clarification(db, user_id: str, paper_id: str, project_id: str, model: str, api_key: str) -> List[str]:
    """Live test: vague request triggers clarification (via inherited _build_clarification)."""
    section("Live: Clarification (inherited _build_clarification)")
    errors = []

    from app.services.smart_agent_service_v2_or import SmartAgentServiceV2OR
    agent = SmartAgentServiceV2OR(model=model, user_api_key=api_key)

    t0 = time.monotonic()
    response = "".join(agent.stream_query(
        db=db, user_id=user_id,
        query="improve it",
        paper_id=paper_id, project_id=project_id,
        document_excerpt=None,  # No document → should ask "What should I change?"
    ))
    ms = int((time.monotonic() - t0) * 1000)

    clean = re.sub(r"\[\[\[STATUS:.*?\]\]\]", "", response).strip()

    if "<<<CLARIFY>>>" in clean:
        ok(f"Clarification triggered ({ms}ms)", "(inherited _build_clarification works)")
    else:
        fail("Expected <<<CLARIFY>>> for vague 'improve it' with no document")
        errors.append("clarification_missing")

    if "QUESTION:" in clean:
        ok("Clarification question present")
    else:
        warn("No QUESTION: in clarification response")

    if "OPTIONS:" in clean:
        ok("Clarification options present")
    else:
        warn("No OPTIONS: in clarification response")

    return errors


def check_live_status_markers(db, user_id: str, paper_id: str, project_id: str, model: str, api_key: str) -> List[str]:
    """Live test: status markers emitted during streaming."""
    section("Live: Status markers")
    errors = []

    from app.services.smart_agent_service_v2_or import SmartAgentServiceV2OR
    agent = SmartAgentServiceV2OR(model=model, user_api_key=api_key)

    chunks = list(agent.stream_query(
        db=db, user_id=user_id,
        query="What is this paper about?",
        paper_id=paper_id, project_id=project_id,
        document_excerpt=SAMPLE_LATEX,
    ))

    status_markers = [c for c in chunks if "[[[STATUS:" in c]
    if status_markers:
        labels = [re.search(r"STATUS:(.*?)\]\]", m).group(1) for m in status_markers if re.search(r"STATUS:(.*?)\]\]", m)]
        ok(f"{len(status_markers)} status marker(s) emitted", ", ".join(labels))
    else:
        warn("No status markers in stream (expected at least Classifying request)")

    return errors


# ── DB setup for live tests ──────────────────────────────────────────

def setup_live_test_db():
    """Create minimal test data for live tests. Returns (db, user_id, paper_id, project_id)."""
    import uuid
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings

    engine = create_engine(str(settings.DATABASE_URL))
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    # Find an existing user, or use a dummy UUID
    from app.models.user import User
    user = db.query(User).first()
    if not user:
        logger.warning("No users in DB — using dummy user_id")
        user_id = str(uuid.uuid4())
    else:
        user_id = str(user.id)

    # Find an existing paper, or use None
    from app.models.research_paper import ResearchPaper
    paper = db.query(ResearchPaper).filter(ResearchPaper.owner_id == user_id).first()
    paper_id = str(paper.id) if paper else None

    # Find project
    from app.models.project import Project
    project = db.query(Project).first()
    project_id = str(project.id) if project else None

    return db, user_id, paper_id, project_id


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Manual smoke test for Editor AI patches")
    parser.add_argument("--model", default="openai/gpt-5-mini", help="OpenRouter model (default: openai/gpt-5-mini)")
    parser.add_argument("--live", action="store_true", help="Run live API + DB tests")
    parser.add_argument("--skip-live", action="store_true", help="Skip live tests (default if --live not given)")
    args = parser.parse_args()

    print(f"\n{C.BOLD}Editor AI Patch Verification{C.RESET}")
    print(f"{C.DIM}Model: {args.model}{C.RESET}")

    all_errors: List[str] = []

    # ── Structural checks (always run, no API calls) ──
    all_errors.extend(check_fix1_inheritance())
    all_errors.extend(check_fix2_retry())
    all_errors.extend(check_fix3_no_print())
    all_errors.extend(check_fix4_bare_except())
    all_errors.extend(check_fix5_class_attrs())

    # ── Live tests (optional, need API key + DB) ──
    if args.live:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            print(f"\n{C.RED}ERROR: OPENROUTER_API_KEY not set. Cannot run live tests.{C.RESET}")
            print("Set it or run inside docker compose.")
            sys.exit(1)

        try:
            db, user_id, paper_id, project_id = setup_live_test_db()
            print(f"\n{C.DIM}DB connected. user={user_id[:8]}... paper={paper_id[:8] if paper_id else 'None'}{C.RESET}")
        except Exception as e:
            print(f"\n{C.RED}ERROR: Could not connect to DB: {e}{C.RESET}")
            print("Run inside docker compose: docker compose exec backend python tests/test_editor_ai_patches.py --live")
            sys.exit(1)

        try:
            all_errors.extend(check_live_greeting(db, user_id, paper_id, project_id, args.model, api_key))
            all_errors.extend(check_live_question(db, user_id, paper_id, project_id, args.model, api_key))
            all_errors.extend(check_live_edit(db, user_id, paper_id, project_id, args.model, api_key))
            all_errors.extend(check_live_clarification(db, user_id, paper_id, project_id, args.model, api_key))
            all_errors.extend(check_live_status_markers(db, user_id, paper_id, project_id, args.model, api_key))
        finally:
            db.close()
    else:
        print(f"\n{C.DIM}Skipping live tests. Use --live to run with real API calls.{C.RESET}")

    # ── Summary ──
    section("Summary")
    if not all_errors:
        print(f"\n  {C.GREEN}{C.BOLD}ALL CHECKS PASSED{C.RESET}\n")
    else:
        print(f"\n  {C.RED}{C.BOLD}{len(all_errors)} ERROR(S):{C.RESET}")
        for err in all_errors:
            print(f"    - {err}")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
