#!/usr/bin/env python3
"""
AI Chat Test Runner

Runs test prompts against the Discussion AI assistant and records responses.
Results are saved for analysis.

Usage:
    python run_ai_chat_tests.py --category 1  # Run Category 1 tests only
    python run_ai_chat_tests.py --test 1.1    # Run specific test
    python run_ai_chat_tests.py --all         # Run all tests
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import requests

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
PROJECT_ID = os.getenv("TEST_PROJECT_ID", "0a9e580c-240c-4289-9ec5-8579b8164d37")
CHANNEL_ID = os.getenv("TEST_CHANNEL_ID", "6e2a2aa5-4e0e-4ffb-ae45-45e1b50a52f3")  # General channel

# Test user credentials
TEST_EMAIL = "g20240390@kfupm.edu.sa"
TEST_PASSWORD = "test123"


@dataclass
class TestCase:
    id: str
    category: int
    name: str
    prompt: str
    expected_behavior: str
    check_tools: Optional[List[str]] = None  # Tools that SHOULD be called
    check_no_tools: Optional[List[str]] = None  # Tools that should NOT be called
    requires_previous: Optional[str] = None  # Test ID this depends on


@dataclass
class TestResult:
    test_id: str
    test_name: str
    prompt: str
    status: str  # "pass", "fail", "error"
    response_message: str
    suggested_actions: List[Dict]
    tools_called: List[str]
    expected_behavior: str
    notes: str
    duration_ms: int
    timestamp: str


# Define test cases
TEST_CASES: List[TestCase] = [
    # Category 1: Simple Tasks
    TestCase(
        id="1.1",
        category=1,
        name="Get Project Info",
        prompt="What is this project about?",
        expected_behavior="AI calls get_project_info tool, returns project title/idea/scope/keywords. No search triggered.",
        check_tools=["get_project_info"],
        check_no_tools=["search_papers", "create_paper"],
    ),
    TestCase(
        id="1.2",
        category=1,
        name="List Project Papers",
        prompt="Show me the papers in this project",
        expected_behavior="AI calls get_project_papers tool. Lists papers or says none exist. No creation attempt.",
        check_tools=["get_project_papers"],
        check_no_tools=["create_paper", "search_papers"],
    ),
    TestCase(
        id="1.3",
        category=1,
        name="List Project References",
        prompt="What references do we have in the library?",
        expected_behavior="AI calls get_project_references tool. Lists references or says none exist. No search triggered.",
        check_tools=["get_project_references"],
        check_no_tools=["search_papers"],
    ),
    TestCase(
        id="1.4",
        category=1,
        name="Simple Paper Search",
        prompt="Search for papers about transformer architecture",
        expected_behavior="AI calls search_papers tool. Returns search action for frontend. Does NOT call get_recent_search_results in same turn.",
        check_tools=["search_papers"],
        check_no_tools=["get_recent_search_results", "create_paper"],
    ),
    TestCase(
        id="1.5",
        category=1,
        name="Get Channel Resources",
        prompt="What resources are attached to this channel?",
        expected_behavior="AI calls get_channel_resources tool. Returns list of resources. Single tool call.",
        check_tools=["get_channel_resources"],
    ),

    # Category 2: Medium Tasks
    TestCase(
        id="2.1",
        category=2,
        name="Search with Year Filter",
        prompt="Find papers about diffusion models published in 2024",
        expected_behavior="AI calls search_papers with query including '2024'. Uses proper academic terms.",
        check_tools=["search_papers"],
    ),
    TestCase(
        id="2.2",
        category=2,
        name="Multi-keyword Search",
        prompt="I need papers about federated learning for healthcare applications",
        expected_behavior="AI calls search_papers with combined query (federated learning healthcare). Single search, not multiple.",
        check_tools=["search_papers"],
    ),
    TestCase(
        id="2.3",
        category=2,
        name="Get Paper Content",
        prompt="Show me the content of any paper we have",
        expected_behavior="AI calls get_project_papers with include_content=True. Displays content in readable format.",
        check_tools=["get_project_papers"],
    ),
    TestCase(
        id="2.4",
        category=2,
        name="Check Search Results",
        prompt="Do we have any search results from earlier?",
        expected_behavior="AI calls get_recent_search_results. Reports count. Does NOT trigger new search.",
        check_tools=["get_recent_search_results"],
        check_no_tools=["search_papers"],
    ),
    TestCase(
        id="2.5",
        category=2,
        name="Ambiguous Request",
        prompt="Write something for me",
        expected_behavior="AI asks ONE clarifying question. Does NOT attempt to create anything. Does NOT ask multiple questions.",
        check_no_tools=["create_paper", "create_artifact"],
    ),

    # Category 3: Complex Tasks (Multi-phase - these need manual verification)
    TestCase(
        id="3.1",
        category=3,
        name="Search Then Create (Phase 1)",
        prompt="Search for papers about mixture of experts",
        expected_behavior="AI triggers search and STOPS. Does NOT create paper. Tells user to wait for results.",
        check_tools=["search_papers"],
        check_no_tools=["create_paper", "get_recent_search_results"],
    ),
    TestCase(
        id="3.2",
        category=3,
        name="Batch Search Multiple Topics",
        prompt="I need papers on three topics: transformer efficiency, model compression, and knowledge distillation",
        expected_behavior="AI calls batch_search_papers with 3 queries. Does NOT make 3 separate search_papers calls.",
        check_tools=["batch_search_papers"],
    ),

    # Category 4: Section Editing
    TestCase(
        id="4.1",
        category=4,
        name="Add New Section",
        prompt="Add a Related Work section about attention mechanisms to the paper",
        expected_behavior="AI calls update_paper with append=True. New section added. Existing content preserved.",
        check_tools=["update_paper"],
    ),

    # Category 5: Error Handling
    TestCase(
        id="5.1",
        category=5,
        name="No Papers Exist",
        prompt="Show me the conclusion of our paper",
        expected_behavior="AI calls get_project_papers. If no papers, says 'No papers found'. Does NOT hallucinate content.",
        check_tools=["get_project_papers"],
    ),
    TestCase(
        id="5.2",
        category=5,
        name="No Search Results",
        prompt="Use the papers from the search to write a summary",
        expected_behavior="AI calls get_recent_search_results. If empty, asks user to search first. Does NOT hallucinate papers.",
        check_tools=["get_recent_search_results"],
        check_no_tools=["create_paper"],
    ),
    TestCase(
        id="5.3",
        category=5,
        name="Vague Yes Response",
        prompt="Yes",
        expected_behavior="AI checks context. If no previous question, asks what user wants. Does NOT trigger random actions.",
        check_no_tools=["search_papers", "create_paper"],
    ),

    # Category 7: Content Quality
    TestCase(
        id="7.1",
        category=7,
        name="LaTeX Format Check",
        prompt="Create a short paper outline about neural networks with an introduction and conclusion",
        expected_behavior="AI creates paper using LaTeX format (\\section{}, \\textbf{}). NO Markdown (#, **bold**). Proper document structure.",
        check_tools=["create_paper"],
    ),

    # Category 8: Conversation Flow
    TestCase(
        id="8.1",
        category=8,
        name="Stop After Search",
        prompt="Search for papers about BERT and then create a summary",
        expected_behavior="AI calls search_papers and STOPS. Does NOT immediately create paper. Says to wait for results.",
        check_tools=["search_papers"],
        check_no_tools=["create_paper", "create_artifact"],
    ),

    # Category 10: Specific Paper Operations
    TestCase(
        id="10.1",
        category=10,
        name="Get Specific Paper by Name",
        prompt="Show me the Literature Review paper",
        expected_behavior="AI finds and displays the 'Literature Review: Advances in Transformer Architectures' paper content.",
        check_tools=["get_project_papers"],
    ),
    TestCase(
        id="10.2",
        category=10,
        name="Get Paper Introduction Section",
        prompt="Show me the introduction section of our transformer paper",
        expected_behavior="AI retrieves paper and shows the Introduction section specifically.",
        check_tools=["get_project_papers"],
    ),
    TestCase(
        id="10.3",
        category=10,
        name="Extend Conclusion Request",
        prompt="Extend the conclusion section of the Literature Review paper with future research directions",
        expected_behavior="AI calls update_paper with section_name='Conclusion'. Replaces (not duplicates) the conclusion.",
        check_tools=["update_paper"],
    ),
    TestCase(
        id="10.4",
        category=10,
        name="Add New Section to Paper",
        prompt="Add a Related Work section to the Literature Review paper",
        expected_behavior="AI calls update_paper with append=True. Adds new section without replacing existing ones.",
        check_tools=["update_paper"],
    ),

    # Category 11: Direct Paper Creation (with explicit instructions)
    TestCase(
        id="11.1",
        category=11,
        name="Create Paper with Explicit Topic",
        prompt="Create a new paper titled 'Survey of Attention Mechanisms' with an introduction about how attention transformed NLP",
        expected_behavior="AI calls create_paper. Paper uses LaTeX format (\\section{}, not #). Proper document structure.",
        check_tools=["create_paper"],
    ),
    TestCase(
        id="11.2",
        category=11,
        name="Create Paper Using Library References",
        prompt="Create a short paper about transformers using the 3 references we have in our library",
        expected_behavior="AI calls get_project_references then create_paper. Uses \\cite{} for citations. References linked.",
        check_tools=["create_paper"],
    ),

    # Category 12: Reference Handling
    TestCase(
        id="12.1",
        category=12,
        name="List References with Details",
        prompt="Show me all references in the library with their abstracts",
        expected_behavior="AI calls get_project_references. Shows title, authors, year, AND abstracts for each reference.",
        check_tools=["get_project_references"],
    ),
    TestCase(
        id="12.2",
        category=12,
        name="Find Reference by Author",
        prompt="Do we have any papers by Vaswani in our library?",
        expected_behavior="AI calls get_project_references. Finds and shows 'Attention Is All You Need' paper.",
        check_tools=["get_project_references"],
    ),

    # Category 13: Edge Cases
    TestCase(
        id="13.1",
        category=13,
        name="Search After Search",
        prompt="Actually, search for diffusion models instead",
        expected_behavior="AI initiates new search for diffusion models. Replaces previous search context.",
        check_tools=["search_papers"],
    ),
    TestCase(
        id="13.2",
        category=13,
        name="Cancel/Nevermind",
        prompt="Nevermind, forget about that",
        expected_behavior="AI acknowledges and asks what user wants to do instead. Does NOT execute any action.",
        check_no_tools=["search_papers", "create_paper", "update_paper"],
    ),
    TestCase(
        id="13.3",
        category=13,
        name="Multiple Instructions at Once",
        prompt="Search for papers about GPT-4 and also show me our current papers",
        expected_behavior="AI either handles both (search + list papers) or asks which to do first. Should not ignore either request.",
    ),
    TestCase(
        id="13.4",
        category=13,
        name="Typo in Request",
        prompt="serch for paeprs about transformrs",
        expected_behavior="AI understands intent despite typos. Searches for transformer papers.",
        check_tools=["search_papers"],
    ),
]


class AITestRunner:
    def __init__(self, api_base_url: str, project_id: str, channel_id: str):
        self.api_base_url = api_base_url
        self.project_id = project_id
        self.channel_id = channel_id
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.results: List[TestResult] = []

    def authenticate(self, email: str, password: str) -> bool:
        """Login and get auth token."""
        try:
            response = self.session.post(
                f"{self.api_base_url}/login",
                json={"email": email, "password": password}
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.session.headers["Authorization"] = f"Bearer {self.token}"
                print(f"✓ Authenticated as {email}")
                return True
            else:
                print(f"✗ Authentication failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"✗ Authentication error: {e}")
            return False

    def send_prompt(self, prompt: str, recent_search_results: Optional[List] = None) -> Dict[str, Any]:
        """Send a prompt to the AI assistant."""
        url = f"{self.api_base_url}/projects/{self.project_id}/discussion/channels/{self.channel_id}/assistant"

        payload = {
            "question": prompt,
            "reasoning": False,
        }
        if recent_search_results:
            payload["recent_search_results"] = recent_search_results

        start_time = time.time()
        try:
            response = self.session.post(url, json=payload, timeout=120)
            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "message": data.get("message", ""),
                    "suggested_actions": data.get("suggested_actions", []),
                    "citations": data.get("citations", []),
                    "reasoning_used": data.get("reasoning_used", False),
                    "duration_ms": duration_ms,
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "duration_ms": duration_ms,
                }
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "error": str(e),
                "duration_ms": duration_ms,
            }

    def extract_tools_from_response(self, response: Dict) -> List[str]:
        """Extract which tools were called based on response/actions."""
        tools = []

        # Check suggested_actions for tool indicators
        for action in response.get("suggested_actions", []):
            action_type = action.get("action_type", "")
            if action_type == "search_references":
                tools.append("search_papers")
            elif action_type == "batch_search_references":
                tools.append("batch_search_papers")
            elif action_type == "paper_created":
                tools.append("create_paper")
            elif action_type == "paper_updated":
                tools.append("update_paper")
            elif action_type == "artifact_created":
                tools.append("create_artifact")

        # Infer from message content
        message = response.get("message", "").lower()
        if "project" in message and ("about" in message or "title" in message or "scope" in message):
            if "get_project_info" not in tools:
                tools.append("get_project_info")
        if "papers in this project" in message or "no papers" in message:
            if "get_project_papers" not in tools:
                tools.append("get_project_papers")
        if "references" in message and "library" in message:
            if "get_project_references" not in tools:
                tools.append("get_project_references")
        if "searching" in message or "search for" in message:
            if "search_papers" not in tools and "batch_search_papers" not in tools:
                tools.append("search_papers")
        if "recent search" in message or "no recent" in message:
            if "get_recent_search_results" not in tools:
                tools.append("get_recent_search_results")
        if "channel" in message and "resource" in message:
            if "get_channel_resources" not in tools:
                tools.append("get_channel_resources")

        return tools

    def run_test(self, test: TestCase) -> TestResult:
        """Run a single test case."""
        print(f"\n{'='*60}")
        print(f"Test {test.id}: {test.name}")
        print(f"Prompt: {test.prompt}")
        print(f"{'='*60}")

        response = self.send_prompt(test.prompt)

        if not response.get("success"):
            return TestResult(
                test_id=test.id,
                test_name=test.name,
                prompt=test.prompt,
                status="error",
                response_message=response.get("error", "Unknown error"),
                suggested_actions=[],
                tools_called=[],
                expected_behavior=test.expected_behavior,
                notes=f"API Error: {response.get('error')}",
                duration_ms=response.get("duration_ms", 0),
                timestamp=datetime.now().isoformat(),
            )

        tools_called = self.extract_tools_from_response(response)

        # Check tool expectations
        notes = []
        status = "pass"

        if test.check_tools:
            for tool in test.check_tools:
                if tool not in tools_called:
                    notes.append(f"MISSING: Expected tool '{tool}' was not detected")
                    status = "fail"

        if test.check_no_tools:
            for tool in test.check_no_tools:
                if tool in tools_called:
                    notes.append(f"UNEXPECTED: Tool '{tool}' should NOT have been called")
                    status = "fail"

        result = TestResult(
            test_id=test.id,
            test_name=test.name,
            prompt=test.prompt,
            status=status,
            response_message=response.get("message", "")[:500],  # Truncate for readability
            suggested_actions=response.get("suggested_actions", []),
            tools_called=tools_called,
            expected_behavior=test.expected_behavior,
            notes="; ".join(notes) if notes else "OK",
            duration_ms=response.get("duration_ms", 0),
            timestamp=datetime.now().isoformat(),
        )

        # Print result summary
        print(f"\nResponse ({response.get('duration_ms', 0)}ms):")
        print(f"  Message: {response.get('message', '')[:200]}...")
        print(f"  Actions: {[a.get('action_type') for a in response.get('suggested_actions', [])]}")
        print(f"  Tools detected: {tools_called}")
        print(f"  Status: {'✓ PASS' if status == 'pass' else '✗ FAIL'}")
        if notes:
            print(f"  Notes: {'; '.join(notes)}")

        return result

    def run_tests(self, test_ids: Optional[List[str]] = None, category: Optional[int] = None) -> List[TestResult]:
        """Run multiple tests."""
        tests_to_run = TEST_CASES

        if test_ids:
            tests_to_run = [t for t in TEST_CASES if t.id in test_ids]
        elif category:
            tests_to_run = [t for t in TEST_CASES if t.category == category]

        print(f"\n{'#'*60}")
        print(f"Running {len(tests_to_run)} tests")
        print(f"{'#'*60}")

        results = []
        for test in tests_to_run:
            result = self.run_test(test)
            results.append(result)
            self.results.append(result)
            time.sleep(1)  # Small delay between tests

        return results

    def save_results(self, filename: str = "test_results.json"):
        """Save results to JSON file."""
        output = {
            "run_timestamp": datetime.now().isoformat(),
            "project_id": self.project_id,
            "channel_id": self.channel_id,
            "total_tests": len(self.results),
            "passed": len([r for r in self.results if r.status == "pass"]),
            "failed": len([r for r in self.results if r.status == "fail"]),
            "errors": len([r for r in self.results if r.status == "error"]),
            "results": [asdict(r) for r in self.results],
        }

        with open(filename, "w") as f:
            json.dump(output, f, indent=2)

        print(f"\n✓ Results saved to {filename}")

    def print_summary(self):
        """Print test summary."""
        passed = len([r for r in self.results if r.status == "pass"])
        failed = len([r for r in self.results if r.status == "fail"])
        errors = len([r for r in self.results if r.status == "error"])
        total = len(self.results)

        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Total:  {total}")
        print(f"Passed: {passed} ({100*passed//total if total else 0}%)")
        print(f"Failed: {failed}")
        print(f"Errors: {errors}")

        if failed > 0:
            print(f"\nFailed tests:")
            for r in self.results:
                if r.status == "fail":
                    print(f"  - {r.test_id}: {r.test_name}")
                    print(f"    Notes: {r.notes}")


def main():
    parser = argparse.ArgumentParser(description="AI Chat Test Runner")
    parser.add_argument("--category", type=int, help="Run tests from specific category (1-9)")
    parser.add_argument("--test", type=str, help="Run specific test by ID (e.g., 1.1)")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--output", type=str, default="test_results.json", help="Output file for results")

    args = parser.parse_args()

    runner = AITestRunner(API_BASE_URL, PROJECT_ID, CHANNEL_ID)

    # Authenticate
    if not runner.authenticate(TEST_EMAIL, TEST_PASSWORD):
        print("Failed to authenticate. Exiting.")
        sys.exit(1)

    # Run tests
    if args.test:
        runner.run_tests(test_ids=[args.test])
    elif args.category:
        runner.run_tests(category=args.category)
    elif args.all:
        runner.run_tests()
    else:
        # Default: run Category 1 (Simple Tasks)
        print("No specific tests requested. Running Category 1 (Simple Tasks)...")
        runner.run_tests(category=1)

    # Save and summarize
    runner.save_results(args.output)
    runner.print_summary()


if __name__ == "__main__":
    main()
