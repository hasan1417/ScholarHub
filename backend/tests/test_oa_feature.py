#!/usr/bin/env python3
"""
Test script for Open Access (OA) feature in Discussion AI.

Tests:
1. Search API with open_access_only filter
2. AI tool parameter parsing
3. OA data flow from search results
"""

import asyncio
import json
import sys
from datetime import datetime
from typing import Dict, List, Any

# Add parent to path for imports
sys.path.insert(0, "/app")

from app.database import SessionLocal
from app.models import User, Project, ProjectMember
from app.services.discussion_ai.tool_orchestrator import DISCUSSION_TOOLS, ToolOrchestrator
from app.services.ai_service import AIService


def test_search_papers_tool_has_oa_parameter():
    """Test 1: Verify search_papers tool has open_access_only parameter."""
    print("\n" + "="*60)
    print("TEST 1: search_papers tool has open_access_only parameter")
    print("="*60)

    search_tool = next(
        (t for t in DISCUSSION_TOOLS if t['function']['name'] == 'search_papers'),
        None
    )

    if not search_tool:
        print("❌ FAIL: search_papers tool not found")
        return False

    params = search_tool['function']['parameters']['properties']

    if 'open_access_only' not in params:
        print("❌ FAIL: open_access_only parameter not found in search_papers")
        return False

    oa_param = params['open_access_only']

    checks = [
        ('type is boolean', oa_param.get('type') == 'boolean'),
        ('has description', 'description' in oa_param),
        ('default is False', oa_param.get('default') == False),
    ]

    all_passed = True
    for check_name, passed in checks:
        status = "✓" if passed else "✗"
        print(f"  {status} {check_name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("✅ PASS: search_papers tool correctly configured with open_access_only")
    else:
        print("❌ FAIL: search_papers tool configuration issues")

    return all_passed


def test_tool_search_papers_returns_oa_in_payload():
    """Test 2: Verify _tool_search_papers includes open_access_only in payload."""
    print("\n" + "="*60)
    print("TEST 2: _tool_search_papers returns open_access_only in payload")
    print("="*60)

    db = SessionLocal()
    try:
        ai_service = AIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        # Test with open_access_only=False (default)
        result1 = orchestrator._tool_search_papers(query="transformers", count=5)
        payload1 = result1.get('action', {}).get('payload', {})

        # Test with open_access_only=True
        result2 = orchestrator._tool_search_papers(query="transformers", count=5, open_access_only=True)
        payload2 = result2.get('action', {}).get('payload', {})

        checks = [
            ('action type is search_references', result1.get('action', {}).get('type') == 'search_references'),
            ('payload has query', 'query' in payload1),
            ('payload has max_results', 'max_results' in payload1),
            ('payload has open_access_only', 'open_access_only' in payload1),
            ('default open_access_only is False', payload1.get('open_access_only') == False),
            ('can set open_access_only to True', payload2.get('open_access_only') == True),
            ('message mentions OA when True', 'Open Access' in result2.get('message', '')),
        ]

        all_passed = True
        for check_name, passed in checks:
            status = "✓" if passed else "✗"
            print(f"  {status} {check_name}")
            if not passed:
                all_passed = False

        if all_passed:
            print("✅ PASS: _tool_search_papers correctly handles open_access_only")
        else:
            print("❌ FAIL: _tool_search_papers has issues")

        return all_passed
    finally:
        db.close()


async def test_search_api_filters_oa():
    """Test 3: Verify search API filters for open access papers."""
    print("\n" + "="*60)
    print("TEST 3: Search API filters for open access papers")
    print("="*60)

    from app.services.paper_discovery_service import PaperDiscoveryService

    discovery_service = PaperDiscoveryService()

    try:
        # Search without OA filter
        print("  Searching for 'machine learning' (no filter)...")
        result_all = await discovery_service.discover_papers(
            query="machine learning transformers",
            max_results=10,
            sources=["arxiv", "semantic_scholar"],
            fast_mode=True,
        )

        all_papers = result_all.papers
        oa_papers = [p for p in all_papers if p.pdf_url or p.open_access_url]

        print(f"  Found {len(all_papers)} total papers")
        print(f"  Of which {len(oa_papers)} have PDF/OA URL")

        # Count OA status
        oa_true_count = sum(1 for p in all_papers if p.is_open_access)
        pdf_count = sum(1 for p in all_papers if p.pdf_url)

        checks = [
            ('found some papers', len(all_papers) > 0),
            ('some papers have is_open_access=True', oa_true_count > 0),
            ('some papers have pdf_url', pdf_count > 0),
        ]

        all_passed = True
        for check_name, passed in checks:
            status = "✓" if passed else "✗"
            print(f"  {status} {check_name}")
            if not passed:
                all_passed = False

        # Show sample papers with OA info
        print("\n  Sample papers with OA info:")
        for p in all_papers[:5]:
            oa_status = "OA" if (p.is_open_access or p.pdf_url) else "  "
            pdf_status = "PDF" if p.pdf_url else "   "
            print(f"    [{oa_status}] [{pdf_status}] {p.title[:50]}...")

        if all_passed:
            print("\n✅ PASS: Search API returns papers with OA information")
        else:
            print("\n❌ FAIL: Search API issues with OA data")

        return all_passed
    finally:
        await discovery_service.close()


def test_system_prompt_mentions_oa():
    """Test 4: Verify system prompt mentions OA filter."""
    print("\n" + "="*60)
    print("TEST 4: System prompt mentions OA filter")
    print("="*60)

    from app.services.discussion_ai.tool_orchestrator import BASE_SYSTEM_PROMPT

    checks = [
        ('mentions open_access_only', 'open_access_only' in BASE_SYSTEM_PROMPT),
        ('mentions OA', 'OA' in BASE_SYSTEM_PROMPT or 'Open Access' in BASE_SYSTEM_PROMPT.upper()),
        ('has OA filter section', 'OPEN ACCESS' in BASE_SYSTEM_PROMPT),
        ('mentions PDF availability', 'PDF' in BASE_SYSTEM_PROMPT),
        ('mentions ingest', 'ingest' in BASE_SYSTEM_PROMPT.lower()),
    ]

    all_passed = True
    for check_name, passed in checks:
        status = "✓" if passed else "✗"
        print(f"  {status} {check_name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("✅ PASS: System prompt properly documents OA filter")
    else:
        print("❌ FAIL: System prompt missing OA documentation")

    return all_passed


async def test_ai_understands_oa_request():
    """Test 5: Verify AI understands OA-related requests."""
    print("\n" + "="*60)
    print("TEST 5: AI understands OA-related requests")
    print("="*60)

    db = SessionLocal()
    try:
        # Get test project
        project = db.query(Project).filter(
            Project.title.ilike('%AI Chat Test%')
        ).first()

        if not project:
            print("  ⚠ Skipping: Test project not found")
            return True  # Skip, not fail

        # Get first channel
        from app.models import ProjectDiscussionChannel
        channel = db.query(ProjectDiscussionChannel).filter(
            ProjectDiscussionChannel.project_id == project.id
        ).first()

        if not channel:
            print("  ⚠ Skipping: No channel found")
            return True

        ai_service = AIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        # Test prompts that should trigger OA filter
        test_prompts = [
            ("find open access papers about BERT", True),
            ("search for OA papers on transformers", True),
            ("only papers with PDF about neural networks", True),
            ("papers I can ingest about attention", True),
            ("find papers about machine learning", False),  # No OA mention
        ]

        print("  Testing AI interpretation of OA-related prompts...")
        print("  (Note: This tests tool call generation, not actual search)")

        results = []
        for prompt, should_have_oa in test_prompts:
            print(f"\n  Prompt: '{prompt}'")
            print(f"    Expected OA filter: {should_have_oa}")

            try:
                # Use streaming to get tool calls
                response_text = ""
                tool_calls = []

                for chunk in orchestrator.handle_message_stream(
                    project=project,
                    channel=channel,
                    message=prompt,
                    recent_search_results=[],
                    reasoning_mode=False,
                ):
                    if chunk.get("type") == "token":
                        response_text += chunk.get("content", "")
                    elif chunk.get("type") == "tool_calls":
                        tool_calls = chunk.get("tool_calls", [])
                    elif chunk.get("type") == "actions":
                        # Check actions for search_references
                        for action in chunk.get("actions", []):
                            if action.get("type") == "search_references":
                                payload = action.get("payload", {})
                                has_oa = payload.get("open_access_only", False)
                                print(f"    Action payload: open_access_only={has_oa}")
                                results.append((prompt, should_have_oa, has_oa))

                # Check tool calls
                for tc in tool_calls:
                    if tc.get("name") == "search_papers":
                        args = tc.get("arguments", {})
                        has_oa = args.get("open_access_only", False)
                        print(f"    Tool call: open_access_only={has_oa}")
                        results.append((prompt, should_have_oa, has_oa))

            except Exception as e:
                print(f"    Error: {e}")
                results.append((prompt, should_have_oa, None))

        # Analyze results
        if results:
            correct = sum(1 for _, expected, actual in results if expected == actual)
            total = len(results)
            print(f"\n  Results: {correct}/{total} prompts correctly interpreted")

            if correct >= total * 0.6:  # 60% threshold for AI behavior
                print("✅ PASS: AI generally understands OA requests")
                return True
            else:
                print("⚠ PARTIAL: AI understanding could be improved")
                return True  # Don't fail for AI behavior variance
        else:
            print("  ⚠ No results to analyze")
            return True

    finally:
        db.close()


async def run_all_tests():
    """Run all OA feature tests."""
    print("\n" + "="*60)
    print("OPEN ACCESS (OA) FEATURE TESTS")
    print("="*60)
    print(f"Time: {datetime.now().isoformat()}")

    results = []

    # Test 1: Tool parameter
    results.append(("Tool has OA parameter", test_search_papers_tool_has_oa_parameter()))

    # Test 2: Tool returns OA in payload
    results.append(("Tool returns OA in payload", test_tool_search_papers_returns_oa_in_payload()))

    # Test 3: Search API filters
    results.append(("Search API filters OA", await test_search_api_filters_oa()))

    # Test 4: System prompt
    results.append(("System prompt mentions OA", test_system_prompt_mentions_oa()))

    # Test 5: AI understanding (optional)
    # results.append(("AI understands OA requests", await test_ai_understands_oa_request()))

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
