"""
Conversation Flow Test for Deep Search & Paper Focus Tools

This test simulates a real user conversation with the Discussion AI,
sending sequential prompts and verifying the AI correctly uses the new tools.

Requires: OPENAI_API_KEY environment variable

Run with: python tests/test_deep_search_conversation.py
"""

import os
import sys
import json
from uuid import uuid4
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Check for API key
if not os.getenv('OPENAI_API_KEY'):
    print("ERROR: OPENAI_API_KEY environment variable required")
    print("Set it with: export OPENAI_API_KEY='your-key-here'")
    sys.exit(1)


# ============================================================
# Setup Real-ish Test Environment
# ============================================================

class TestChannel:
    """Simulates a real discussion channel."""
    def __init__(self):
        self.id = str(uuid4())
        self.name = "AI Research Discussion"
        self.ai_memory = None


class TestProject:
    """Simulates a real project."""
    def __init__(self):
        self.id = str(uuid4())
        self.created_by = str(uuid4())
        self.title = "Transformer Architecture Research"
        self.idea = "Investigating attention mechanisms and their applications in NLP and computer vision"
        self.scope = "1. Review transformer variants\n2. Compare attention mechanisms\n3. Analyze computational efficiency"
        self.keywords = "transformers, attention, BERT, GPT, ViT"
        self.status = "active"


class TestDB:
    """Minimal DB mock that tracks state."""
    def __init__(self):
        self.committed = 0
        self._data = {}

    def commit(self):
        self.committed += 1

    def rollback(self):
        pass

    def query(self, *args):
        return self

    def join(self, *args):
        return self

    def filter(self, *args):
        return self

    def first(self):
        return None

    def all(self):
        return []

    def count(self):
        return 0

    def order_by(self, *args):
        return self

    def limit(self, *args):
        return self


def create_search_results():
    """Create realistic search results that would come from paper discovery."""
    return [
        {
            "title": "Attention Is All You Need",
            "authors": "Vaswani, Shazeer, Parmar, Uszkoreit, Jones, Gomez, Kaiser, Polosukhin",
            "year": 2017,
            "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely. Experiments on machine translation tasks show these models achieve state-of-the-art results.",
            "doi": "10.5555/3295222.3295349",
            "url": "https://arxiv.org/abs/1706.03762",
            "source": "semantic_scholar",
            "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
            "is_open_access": True,
        },
        {
            "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
            "authors": "Devlin, Chang, Lee, Toutanova",
            "year": 2019,
            "abstract": "We introduce BERT, which stands for Bidirectional Encoder Representations from Transformers. Unlike recent language representation models, BERT is designed to pre-train deep bidirectional representations by jointly conditioning on both left and right context.",
            "doi": "10.18653/v1/N19-1423",
            "url": "https://arxiv.org/abs/1810.04805",
            "source": "semantic_scholar",
            "pdf_url": "https://arxiv.org/pdf/1810.04805.pdf",
            "is_open_access": True,
        },
        {
            "title": "Language Models are Few-Shot Learners (GPT-3)",
            "authors": "Brown, Mann, Ryder, Subbiah, Kaplan, et al.",
            "year": 2020,
            "abstract": "We demonstrate that scaling up language models greatly improves task-agnostic, few-shot performance, sometimes even reaching competitiveness with prior state-of-the-art fine-tuning approaches.",
            "doi": "10.5555/3495724.3495883",
            "url": "https://arxiv.org/abs/2005.14165",
            "source": "semantic_scholar",
            "pdf_url": None,
            "is_open_access": False,
        },
        {
            "title": "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
            "authors": "Dosovitskiy, Beyer, Kolesnikov, Weissenborn, Zhai, et al.",
            "year": 2021,
            "abstract": "We show that a pure transformer applied directly to sequences of image patches can perform very well on image classification tasks, challenging the dominance of convolutional neural networks.",
            "doi": "10.48550/arXiv.2010.11929",
            "url": "https://arxiv.org/abs/2010.11929",
            "source": "semantic_scholar",
            "pdf_url": "https://arxiv.org/pdf/2010.11929.pdf",
            "is_open_access": True,
        },
    ]


# ============================================================
# Conversation Simulator
# ============================================================

class ConversationSimulator:
    """Simulates a real conversation with the Discussion AI."""

    def __init__(self):
        from app.services.ai_service import AIService
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        self.db = TestDB()
        self.ai_service = AIService()
        self.orchestrator = ToolOrchestrator(self.ai_service, self.db)

        self.project = TestProject()
        self.channel = TestChannel()
        self.conversation_history = []
        self.search_results = []
        self.tools_called = []

    def send_message(self, user_message: str, search_results=None) -> dict:
        """Send a message and get the AI response."""
        print(f"\n{'='*60}")
        print(f"USER: {user_message}")
        print('='*60)

        # Update search results if provided
        if search_results is not None:
            self.search_results = search_results

        # Call the orchestrator
        result = self.orchestrator.handle_message(
            project=self.project,
            channel=self.channel,
            message=user_message,
            recent_search_results=self.search_results,
            conversation_history=self.conversation_history,
            reasoning_mode=False,
        )

        # Track conversation history
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": result.get("message", "")})

        # Track tools called
        if result.get("tools_called"):
            self.tools_called.extend(result["tools_called"])

        # Print response
        print(f"\nASSISTANT:")
        print("-" * 40)
        response_text = result.get("message", "")[:500]
        if len(result.get("message", "")) > 500:
            response_text += "..."
        print(response_text)

        if result.get("tools_called"):
            print(f"\n[Tools called: {', '.join(result['tools_called'])}]")

        if result.get("actions"):
            print(f"\n[Actions: {[a.get('type') for a in result['actions']]}]")

        return result

    def get_memory_state(self) -> dict:
        """Get current AI memory state."""
        return self.channel.ai_memory or {}

    def print_memory_state(self):
        """Print current memory state."""
        memory = self.get_memory_state()
        print(f"\n{'='*60}")
        print("MEMORY STATE:")
        print('='*60)

        if memory.get("focused_papers"):
            print(f"\nFocused Papers ({len(memory['focused_papers'])}):")
            for i, p in enumerate(memory["focused_papers"], 1):
                print(f"  {i}. {p.get('title', 'Unknown')[:50]}...")

        if memory.get("deep_search"):
            print(f"\nDeep Search Question: {memory['deep_search'].get('last_question', 'None')[:60]}...")

        if memory.get("cross_paper_analysis"):
            print(f"\nCross-Paper Analysis: {memory['cross_paper_analysis'].get('last_question', 'None')[:60]}...")

        if memory.get("summary"):
            print(f"\nSession Summary: {memory['summary'][:100]}...")


# ============================================================
# Test Conversations
# ============================================================

def test_conversation_deep_search_flow():
    """Test a conversation that uses deep search."""
    print("\n" + "="*70)
    print("TEST 1: Deep Search Conversation Flow")
    print("="*70)

    sim = ConversationSimulator()

    # Turn 1: Ask a research question that should trigger deep_search_papers
    result1 = sim.send_message(
        "What are the main approaches to attention mechanisms in neural networks? "
        "I need a comprehensive overview."
    )

    # Check if deep_search_papers was called
    assert "deep_search_papers" in sim.tools_called, \
        f"Expected deep_search_papers to be called. Got: {sim.tools_called}"

    # Check action was generated
    actions = result1.get("actions", [])
    action_types = [a.get("type") for a in actions]
    assert "deep_search_references" in action_types or "search_references" in action_types, \
        f"Expected search action. Got: {action_types}"

    print("\n✓ Deep search was triggered correctly")
    return True


def test_conversation_focus_and_analyze_flow():
    """Test a conversation that focuses on papers and analyzes them."""
    print("\n" + "="*70)
    print("TEST 2: Focus and Analyze Conversation Flow")
    print("="*70)

    sim = ConversationSimulator()

    # Simulate search results already present
    sim.search_results = create_search_results()

    # Turn 1: Ask to focus on specific papers
    result1 = sim.send_message(
        "I found some interesting papers. Can you focus on the first two papers "
        "(Attention Is All You Need and BERT) so we can discuss them in detail?"
    )

    # Check if focus_on_papers was called
    assert "focus_on_papers" in sim.tools_called, \
        f"Expected focus_on_papers to be called. Got: {sim.tools_called}"

    # Check memory has focused papers
    memory = sim.get_memory_state()
    assert "focused_papers" in memory, "Expected focused_papers in memory"
    assert len(memory["focused_papers"]) >= 1, "Expected at least 1 focused paper"

    print(f"\n✓ Papers focused: {len(memory['focused_papers'])}")

    # Turn 2: Ask to compare the papers
    sim.tools_called = []  # Reset
    result2 = sim.send_message(
        "How do these two papers differ in their approach to attention? "
        "What are the key architectural differences?"
    )

    # Check if analyze_across_papers was called
    assert "analyze_across_papers" in sim.tools_called, \
        f"Expected analyze_across_papers to be called. Got: {sim.tools_called}"

    print("\n✓ Cross-paper analysis was triggered")

    sim.print_memory_state()
    return True


def test_conversation_generate_section_flow():
    """Test a conversation that generates a paper section."""
    print("\n" + "="*70)
    print("TEST 3: Generate Section Conversation Flow")
    print("="*70)

    sim = ConversationSimulator()
    sim.search_results = create_search_results()

    # Turn 1: Focus on papers first
    result1 = sim.send_message(
        "Let me focus on the Transformer and ViT papers to compare them."
    )

    # Turn 2: Ask to generate a section
    sim.tools_called = []
    result2 = sim.send_message(
        "Based on our discussion, can you help me write a Related Work section "
        "that covers these transformer architectures?"
    )

    # Check if generate_section was called
    assert "generate_section_from_discussion" in sim.tools_called, \
        f"Expected generate_section_from_discussion. Got: {sim.tools_called}"

    print("\n✓ Section generation was triggered")

    sim.print_memory_state()
    return True


def test_conversation_full_workflow():
    """Test a complete research workflow conversation."""
    print("\n" + "="*70)
    print("TEST 4: Full Research Workflow Conversation")
    print("="*70)

    sim = ConversationSimulator()

    # Turn 1: Initial research question
    print("\n--- Turn 1: Research Question ---")
    result1 = sim.send_message(
        "I'm researching how transformers have evolved from NLP to computer vision. "
        "Can you help me understand the main developments?"
    )

    # Simulate search results came back
    sim.search_results = create_search_results()

    # Turn 2: Focus on specific papers
    print("\n--- Turn 2: Focus on Papers ---")
    sim.tools_called = []
    result2 = sim.send_message(
        "Great, I see the search results. Let me focus on papers 1, 2, and 4 "
        "(the original Transformer, BERT, and Vision Transformer)."
    )

    focus_called = "focus_on_papers" in sim.tools_called
    print(f"  focus_on_papers called: {focus_called}")

    # Turn 3: Cross-paper analysis
    print("\n--- Turn 3: Cross-Paper Analysis ---")
    sim.tools_called = []
    result3 = sim.send_message(
        "Can you analyze how the attention mechanism evolved across these three papers? "
        "What modifications were made for vision tasks?"
    )

    analyze_called = "analyze_across_papers" in sim.tools_called
    print(f"  analyze_across_papers called: {analyze_called}")

    # Turn 4: Generate section
    print("\n--- Turn 4: Generate Section ---")
    sim.tools_called = []
    result4 = sim.send_message(
        "This is really helpful. Can you draft a methodology section based on our discussion "
        "that describes how attention mechanisms are applied in both domains?"
    )

    generate_called = "generate_section_from_discussion" in sim.tools_called
    print(f"  generate_section_from_discussion called: {generate_called}")

    # Print final memory state
    sim.print_memory_state()

    # Summary
    print("\n" + "="*60)
    print("WORKFLOW SUMMARY:")
    print("="*60)
    print(f"  Deep search triggered: {'deep_search_papers' in sim.tools_called or any('deep_search' in t for t in sim.tools_called)}")
    print(f"  Papers focused: {len(sim.get_memory_state().get('focused_papers', []))}")
    print(f"  Cross-analysis done: {'cross_paper_analysis' in sim.get_memory_state()}")
    print(f"  Total conversation turns: {len(sim.conversation_history) // 2}")

    return True


def test_tool_selection_accuracy():
    """Test that the AI selects the right tools for different prompts."""
    print("\n" + "="*70)
    print("TEST 5: Tool Selection Accuracy")
    print("="*70)

    test_cases = [
        {
            "prompt": "What are the state-of-the-art methods for image segmentation?",
            "expected_tool": "deep_search_papers",
            "description": "Research question should trigger deep search"
        },
        {
            "prompt": "Focus on papers 1 and 3 from the search results.",
            "expected_tool": "focus_on_papers",
            "description": "Focus request should trigger focus_on_papers"
        },
        {
            "prompt": "Compare the methodologies in the focused papers.",
            "expected_tool": "analyze_across_papers",
            "description": "Comparison request should trigger analyze_across_papers",
            "needs_focused": True
        },
        {
            "prompt": "Write me a related work section based on what we discussed.",
            "expected_tool": "generate_section_from_discussion",
            "description": "Section generation request should trigger generate_section"
        },
    ]

    results = []

    for tc in test_cases:
        print(f"\n--- {tc['description']} ---")

        sim = ConversationSimulator()
        sim.search_results = create_search_results()

        # If test needs focused papers, add them first
        if tc.get("needs_focused"):
            sim.channel.ai_memory = {
                "focused_papers": [
                    {"title": "Paper 1", "authors": "A", "year": 2024, "abstract": "Test"},
                    {"title": "Paper 2", "authors": "B", "year": 2023, "abstract": "Test"},
                ]
            }

        result = sim.send_message(tc["prompt"])

        tool_called = tc["expected_tool"] in sim.tools_called
        results.append({
            "test": tc["description"],
            "expected": tc["expected_tool"],
            "called": sim.tools_called,
            "passed": tool_called
        })

        status = "✓ PASS" if tool_called else "✗ FAIL"
        print(f"  {status}: Expected {tc['expected_tool']}, got {sim.tools_called}")

    # Summary
    passed = sum(1 for r in results if r["passed"])
    total = len(results)

    print(f"\n{'='*60}")
    print(f"Tool Selection Accuracy: {passed}/{total} ({100*passed/total:.0f}%)")
    print("="*60)

    return passed == total


# ============================================================
# Main
# ============================================================

def main():
    print("\n" + "#"*70)
    print("# DEEP SEARCH & PAPER FOCUS - CONVERSATION FLOW TESTS")
    print("#"*70)

    tests = [
        ("Deep Search Flow", test_conversation_deep_search_flow),
        ("Focus and Analyze Flow", test_conversation_focus_and_analyze_flow),
        ("Generate Section Flow", test_conversation_generate_section_flow),
        ("Full Workflow", test_conversation_full_workflow),
        ("Tool Selection Accuracy", test_tool_selection_accuracy),
    ]

    results = []

    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed, None))
        except AssertionError as e:
            results.append((name, False, str(e)))
            print(f"\n✗ ASSERTION FAILED: {e}")
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"\n✗ ERROR: {e}")

    # Final Summary
    print("\n" + "#"*70)
    print("# FINAL RESULTS")
    print("#"*70)

    for name, passed, error in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {status}: {name}")
        if error:
            print(f"          Error: {error[:60]}...")

    passed_count = sum(1 for _, p, _ in results if p)
    total_count = len(results)

    print(f"\n  Total: {passed_count}/{total_count} tests passed")
    print("#"*70)

    return passed_count == total_count


if __name__ == "__main__":
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(backend_dir)

    # Load environment
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(backend_dir), ".env"))

    success = main()
    sys.exit(0 if success else 1)
