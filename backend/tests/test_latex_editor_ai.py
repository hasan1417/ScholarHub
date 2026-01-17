#!/usr/bin/env python3
"""
Comprehensive Test Suite for LaTeX Editor AI Chat (SmartAgentService)

Tests all routes:
1. Simple - Greetings, help (gpt-5-mini)
2. Paper - Draft questions (gpt-5-mini)
3. Research - Reference queries (gpt-5.2, low effort)
4. Review - Feedback requests (gpt-5.2, low effort)
5. Edit - Document modifications (gpt-5.2, low effort)
6. Reasoning - Complex analysis (gpt-5.2, high effort)

Also tests scope limitations:
- Should NOT search for papers online
- Should suggest Discussion AI or Discovery page for paper discovery
"""

import sys
import time
import json
from datetime import datetime
from typing import Dict, List, Any, Tuple

sys.path.insert(0, "/app")

from app.database import SessionLocal
from app.models import ResearchPaper, PaperReference, Reference, User
from app.services.smart_agent_service import SmartAgentService


# Test paper ID (AI TEST with 3 attached references)
TEST_PAPER_ID = "c335ad85-40cb-4c66-b388-b1bd5ae42310"


def get_test_context() -> Tuple[str, str, str, str]:
    """Get test paper details and content."""
    db = SessionLocal()
    try:
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == TEST_PAPER_ID).first()
        if not paper:
            raise ValueError(f"Test paper not found: {TEST_PAPER_ID}")

        content = paper.content_json.get("latex_source", "")[:4000]  # First 4000 chars
        user_id = str(paper.owner_id)
        paper_id = str(paper.id)

        return user_id, paper_id, paper.title, content
    finally:
        db.close()


def run_test(
    service: SmartAgentService,
    db,
    test_name: str,
    query: str,
    user_id: str,
    paper_id: str,
    document_excerpt: str,
    expected_route: str,
    check_scope: bool = False,
    reasoning_mode: bool = False,
) -> Dict[str, Any]:
    """Run a single test and return results."""
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"{'='*60}")
    print(f"Query: {query[:80]}{'...' if len(query) > 80 else ''}")
    print(f"Expected route: {expected_route}")
    print(f"Reasoning mode: {reasoning_mode}")

    start_time = time.time()

    try:
        # Collect streamed response
        full_response = ""
        for chunk in service.stream_query(
            db=db,
            user_id=user_id,
            query=query,
            paper_id=paper_id,
            document_excerpt=document_excerpt,
            reasoning_mode=reasoning_mode,
        ):
            full_response += chunk

        elapsed = time.time() - start_time

        # Analyze response
        result = {
            "test_name": test_name,
            "query": query,
            "expected_route": expected_route,
            "response_length": len(full_response),
            "elapsed_seconds": round(elapsed, 2),
            "response_preview": full_response[:500] + "..." if len(full_response) > 500 else full_response,
            "passed": True,
            "issues": [],
        }

        # Check if scope limitation message appears when needed
        if check_scope:
            scope_keywords = ["Discussion AI", "Discovery page", "cannot search", "attached"]
            has_scope_msg = any(kw.lower() in full_response.lower() for kw in scope_keywords)
            if not has_scope_msg:
                result["issues"].append("Missing scope limitation message")
                result["passed"] = False

        # Check for empty response
        if len(full_response.strip()) < 20:
            result["issues"].append("Response too short")
            result["passed"] = False

        # Check for error messages
        if "error" in full_response.lower() and "user error" not in full_response.lower():
            if "cannot" not in full_response.lower():  # "cannot search" is expected
                result["issues"].append("Contains error message")
                result["passed"] = False

        status = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(f"\nStatus: {status}")
        print(f"Response length: {len(full_response)} chars")
        print(f"Time: {elapsed:.2f}s")
        print(f"\nResponse preview:\n{result['response_preview']}")

        if result["issues"]:
            print(f"\nIssues: {result['issues']}")

        return result

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ ERROR: {str(e)}")
        return {
            "test_name": test_name,
            "query": query,
            "expected_route": expected_route,
            "elapsed_seconds": round(elapsed, 2),
            "passed": False,
            "issues": [f"Exception: {str(e)}"],
            "response_preview": "",
        }


def run_all_tests():
    """Run comprehensive test suite."""
    print("\n" + "="*70)
    print("LATEX EDITOR AI CHAT - COMPREHENSIVE TEST SUITE")
    print("="*70)
    print(f"Time: {datetime.now().isoformat()}")

    # Get test context
    user_id, paper_id, paper_title, document_excerpt = get_test_context()
    print(f"\nTest Paper: {paper_title}")
    print(f"Paper ID: {paper_id}")
    print(f"Document length: {len(document_excerpt)} chars")

    db = SessionLocal()
    service = SmartAgentService()

    if not service.client:
        print("\n❌ ERROR: OpenAI client not initialized")
        return False

    # Define test cases
    test_cases = [
        # ==================== SIMPLE ROUTE ====================
        {
            "name": "Simple - Greeting",
            "query": "Hello!",
            "route": "simple",
            "check_scope": False,
            "reasoning": False,
        },
        {
            "name": "Simple - Help",
            "query": "What can you help me with?",
            "route": "simple",
            "check_scope": False,
            "reasoning": False,
        },

        # ==================== PAPER ROUTE ====================
        {
            "name": "Paper - Structure question",
            "query": "What is the structure of my paper?",
            "route": "paper",
            "check_scope": False,
            "reasoning": False,
        },
        {
            "name": "Paper - Content question",
            "query": "What is the main topic of my introduction?",
            "route": "paper",
            "check_scope": False,
            "reasoning": False,
        },
        {
            "name": "Paper - Specific section",
            "query": "Can you summarize the abstract?",
            "route": "paper",
            "check_scope": False,
            "reasoning": False,
        },

        # ==================== RESEARCH ROUTE ====================
        {
            "name": "Research - Reference question",
            "query": "What references do I have attached to this paper?",
            "route": "research",
            "check_scope": False,
            "reasoning": False,
        },
        {
            "name": "Research - Citation help",
            "query": "Which of my references discusses AI agents?",
            "route": "research",
            "check_scope": False,
            "reasoning": False,
        },

        # ==================== SCOPE LIMITATION TESTS ====================
        {
            "name": "Scope - Search request",
            "query": "Find me papers about transformer architectures",
            "route": "research",
            "check_scope": True,  # Should mention Discussion AI or Discovery
            "reasoning": False,
        },
        {
            "name": "Scope - Literature search",
            "query": "Search for recent literature on neural networks",
            "route": "research",
            "check_scope": True,
            "reasoning": False,
        },
        {
            "name": "Scope - Find references",
            "query": "I need more references about machine learning, can you find some?",
            "route": "research",
            "check_scope": True,
            "reasoning": False,
        },

        # ==================== REVIEW ROUTE ====================
        {
            "name": "Review - General feedback",
            "query": "Can you review my paper and give feedback?",
            "route": "review",
            "check_scope": False,
            "reasoning": False,
        },
        {
            "name": "Review - Check quality",
            "query": "What do you think about my introduction? Any suggestions?",
            "route": "review",
            "check_scope": False,
            "reasoning": False,
        },

        # ==================== EDIT ROUTE ====================
        {
            "name": "Edit - Improve text",
            "query": "Can you improve the writing in my abstract?",
            "route": "edit",
            "check_scope": False,
            "reasoning": False,
        },
        {
            "name": "Edit - Rewrite request",
            "query": "Please rewrite the first paragraph of the introduction to be more engaging",
            "route": "edit",
            "check_scope": False,
            "reasoning": False,
        },
        {
            "name": "Edit - Fix grammar",
            "query": "Fix any grammar issues in the conclusion section",
            "route": "edit",
            "check_scope": False,
            "reasoning": False,
        },

        # ==================== REASONING ROUTE ====================
        {
            "name": "Reasoning - Complex analysis",
            "query": "Analyze the logical flow of arguments in my paper and identify any gaps",
            "route": "reasoning",
            "check_scope": False,
            "reasoning": True,
        },
        {
            "name": "Reasoning - Deep review",
            "query": "Critically evaluate the methodology section and suggest improvements",
            "route": "reasoning",
            "check_scope": False,
            "reasoning": True,
        },
    ]

    results = []

    try:
        for tc in test_cases:
            result = run_test(
                service=service,
                db=db,
                test_name=tc["name"],
                query=tc["query"],
                user_id=user_id,
                paper_id=paper_id,
                document_excerpt=document_excerpt,
                expected_route=tc["route"],
                check_scope=tc.get("check_scope", False),
                reasoning_mode=tc.get("reasoning", False),
            )
            results.append(result)

            # Small delay between tests
            time.sleep(0.5)

    finally:
        db.close()

    # ==================== SUMMARY ====================
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)

    # Group by route
    routes = {}
    for r in results:
        route = r["expected_route"]
        if route not in routes:
            routes[route] = {"passed": 0, "total": 0, "tests": []}
        routes[route]["total"] += 1
        if r["passed"]:
            routes[route]["passed"] += 1
        routes[route]["tests"].append(r)

    print(f"\nOverall: {passed}/{total} tests passed ({100*passed/total:.1f}%)\n")

    for route, data in routes.items():
        status = "✅" if data["passed"] == data["total"] else "⚠️" if data["passed"] > 0 else "❌"
        print(f"{status} {route.upper()}: {data['passed']}/{data['total']} passed")
        for t in data["tests"]:
            t_status = "✓" if t["passed"] else "✗"
            issues = f" - {t['issues']}" if t.get("issues") else ""
            print(f"    {t_status} {t['test_name']} ({t['elapsed_seconds']}s){issues}")

    # Performance stats
    print("\n" + "-"*40)
    print("PERFORMANCE")
    print("-"*40)

    avg_time = sum(r["elapsed_seconds"] for r in results) / len(results)
    max_time = max(r["elapsed_seconds"] for r in results)
    min_time = min(r["elapsed_seconds"] for r in results)

    print(f"Average response time: {avg_time:.2f}s")
    print(f"Min: {min_time:.2f}s | Max: {max_time:.2f}s")

    # Save results to JSON
    output_file = "/app/tests/latex_editor_ai_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "paper_id": paper_id,
            "paper_title": paper_title,
            "summary": {
                "passed": passed,
                "total": total,
                "pass_rate": f"{100*passed/total:.1f}%",
                "avg_time": f"{avg_time:.2f}s",
            },
            "results": results,
        }, f, indent=2)

    print(f"\nResults saved to: {output_file}")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
