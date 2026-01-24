"""
Detailed Tests for Deep Search & Paper Focus Tools

These tests verify the actual implementation behavior, not just mock returns.
They test:
1. Actual data transformations
2. Memory state changes
3. Response structure validation
4. Error handling paths
5. Edge cases with realistic data

Run with: python tests/test_deep_search_tools_detailed.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# Realistic Mock Classes
# ============================================================

class RealisticMockChannel:
    """Mock channel that actually stores and retrieves memory."""
    def __init__(self):
        self.id = str(uuid4())
        self.name = "Research Discussion"
        self._ai_memory = None

    @property
    def ai_memory(self):
        return self._ai_memory

    @ai_memory.setter
    def ai_memory(self, value):
        # Actually store the value
        self._ai_memory = value


class RealisticMockProject:
    """Mock project with realistic data."""
    def __init__(self):
        self.id = str(uuid4())
        self.created_by = str(uuid4())
        self.title = "Deep Learning for Medical Image Analysis"
        self.idea = "Investigating CNN and transformer architectures for diagnostic imaging"
        self.scope = "1. Review existing methods\n2. Compare performance\n3. Propose improvements"
        self.keywords = "deep learning, medical imaging, CNN, transformers"


class RealisticMockDB:
    """Mock DB that tracks state changes."""
    def __init__(self):
        self.committed = False
        self.commit_count = 0
        self.rollback_count = 0
        self._references = {}
        self._queries = []

    def add_reference(self, ref_id, ref_data):
        self._references[ref_id] = ref_data

    def commit(self):
        self.committed = True
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def query(self, model_class):
        self._queries.append(model_class)
        return RealisticMockQuery(self._references)


class RealisticMockQuery:
    """Mock query that simulates real query behavior."""
    def __init__(self, references):
        self._references = references
        self._filters = []
        self._joined = False

    def join(self, *args, **kwargs):
        self._joined = True
        return self

    def filter(self, *args, **kwargs):
        self._filters.append(args)
        return self

    def first(self):
        # Return first reference if any
        if self._references:
            ref_id = list(self._references.keys())[0]
            return self._create_mock_reference(ref_id, self._references[ref_id])
        return None

    def all(self):
        return [self._create_mock_reference(k, v) for k, v in self._references.items()]

    def count(self):
        return len(self._references)

    def order_by(self, *args):
        return self

    def limit(self, n):
        return self

    def _create_mock_reference(self, ref_id, data):
        """Create a mock reference object from data."""
        class MockRef:
            pass
        ref = MockRef()
        ref.id = ref_id
        for key, value in data.items():
            setattr(ref, key, value)
        return ref


class RealisticMockAIService:
    """Mock AI service."""
    def __init__(self):
        self.default_model = "gpt-4o-mini"
        self.openai_client = None  # No actual API calls


# ============================================================
# Test Data Generators
# ============================================================

def create_realistic_search_results(count=5):
    """Create realistic academic paper search results."""
    papers = [
        {
            "title": "Attention Is All You Need",
            "authors": "Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, L., Polosukhin, I.",
            "year": 2017,
            "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.",
            "doi": "10.5555/3295222.3295349",
            "url": "https://arxiv.org/abs/1706.03762",
            "source": "semantic_scholar",
            "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
            "is_open_access": True,
            "citation_count": 82000,
            "journal": "NeurIPS 2017",
        },
        {
            "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
            "authors": "Devlin, J., Chang, M., Lee, K., Toutanova, K.",
            "year": 2019,
            "abstract": "We introduce a new language representation model called BERT, which stands for Bidirectional Encoder Representations from Transformers. Unlike recent language representation models, BERT is designed to pre-train deep bidirectional representations from unlabeled text by jointly conditioning on both left and right context in all layers.",
            "doi": "10.18653/v1/N19-1423",
            "url": "https://arxiv.org/abs/1810.04805",
            "source": "semantic_scholar",
            "pdf_url": "https://arxiv.org/pdf/1810.04805.pdf",
            "is_open_access": True,
            "citation_count": 65000,
            "journal": "NAACL 2019",
        },
        {
            "title": "Language Models are Few-Shot Learners",
            "authors": "Brown, T. B., Mann, B., Ryder, N., Subbiah, M., Kaplan, J., et al.",
            "year": 2020,
            "abstract": "Recent work has demonstrated substantial gains on many NLP tasks and benchmarks by pre-training on a large corpus of text followed by fine-tuning on a specific task. We demonstrate that scaling up language models greatly improves task-agnostic, few-shot performance.",
            "doi": "10.5555/3495724.3495883",
            "url": "https://arxiv.org/abs/2005.14165",
            "source": "semantic_scholar",
            "pdf_url": None,  # No PDF available
            "is_open_access": False,
            "citation_count": 25000,
            "journal": "NeurIPS 2020",
        },
        {
            "title": "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
            "authors": "Dosovitskiy, A., Beyer, L., Kolesnikov, A., Weissenborn, D., Zhai, X., et al.",
            "year": 2021,
            "abstract": "While the Transformer architecture has become the de-facto standard for natural language processing tasks, its applications to computer vision remain limited. We show that this reliance on CNNs is not necessary and a pure transformer applied directly to sequences of image patches can perform very well on image classification tasks.",
            "doi": "10.48550/arXiv.2010.11929",
            "url": "https://arxiv.org/abs/2010.11929",
            "source": "semantic_scholar",
            "pdf_url": "https://arxiv.org/pdf/2010.11929.pdf",
            "is_open_access": True,
            "citation_count": 18000,
            "journal": "ICLR 2021",
        },
        {
            "title": "Deep Residual Learning for Image Recognition",
            "authors": "He, K., Zhang, X., Ren, S., Sun, J.",
            "year": 2016,
            "abstract": "Deeper neural networks are more difficult to train. We present a residual learning framework to ease the training of networks that are substantially deeper than those used previously. We explicitly reformulate the layers as learning residual functions with reference to the layer inputs.",
            "doi": "10.1109/CVPR.2016.90",
            "url": "https://arxiv.org/abs/1512.03385",
            "source": "semantic_scholar",
            "pdf_url": "https://arxiv.org/pdf/1512.03385.pdf",
            "is_open_access": True,
            "citation_count": 150000,
            "journal": "CVPR 2016",
        },
    ]
    return papers[:count]


def create_focused_papers_with_analysis():
    """Create focused papers with full analysis data."""
    return [
        {
            "source": "library",
            "reference_id": str(uuid4()),
            "title": "Attention Is All You Need",
            "authors": "Vaswani et al.",
            "year": 2017,
            "abstract": "We propose the Transformer architecture...",
            "doi": "10.5555/3295222.3295349",
            "has_full_text": True,
            "summary": "This paper introduces the Transformer architecture, which relies entirely on self-attention mechanisms without using recurrence or convolutions.",
            "key_findings": [
                "Self-attention can replace recurrence for sequence modeling",
                "Multi-head attention allows the model to jointly attend to information from different representation subspaces",
                "The Transformer achieves state-of-the-art results on machine translation",
            ],
            "methodology": "The authors trained Transformer models on the WMT 2014 English-German and English-French translation tasks using 8 NVIDIA P100 GPUs.",
            "limitations": [
                "Quadratic complexity with respect to sequence length",
                "May struggle with very long sequences without modifications",
            ],
        },
        {
            "source": "search_result",
            "index": 1,
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "authors": "Devlin et al.",
            "year": 2019,
            "abstract": "We introduce BERT, which stands for Bidirectional Encoder Representations from Transformers...",
            "doi": "10.18653/v1/N19-1423",
            "has_full_text": False,
        },
    ]


# ============================================================
# Detailed Test Cases
# ============================================================

def test_deep_search_response_structure():
    """Verify deep_search_papers returns correct response structure."""
    print("\n=== test_deep_search_response_structure ===")

    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    db = RealisticMockDB()
    ai_service = RealisticMockAIService()
    orchestrator = ToolOrchestrator(ai_service, db)

    channel = RealisticMockChannel()
    project = RealisticMockProject()
    ctx = {
        "project": project,
        "channel": channel,
        "recent_search_results": [],
    }

    result = orchestrator._tool_deep_search_papers(
        ctx,
        research_question="What are the main approaches to attention mechanisms in transformers?",
        max_papers=15
    )

    # Verify required fields exist
    assert "status" in result, "Missing 'status' in response"
    assert "message" in result, "Missing 'message' in response"
    assert "action" in result, "Missing 'action' in response"
    assert "research_question" in result, "Missing 'research_question' in response"

    # Verify action structure
    action = result["action"]
    assert action["type"] == "deep_search_references", f"Wrong action type: {action['type']}"
    assert "payload" in action, "Missing 'payload' in action"

    payload = action["payload"]
    assert payload["query"] == "What are the main approaches to attention mechanisms in transformers?"
    assert payload["max_results"] == 15
    assert payload["synthesis_mode"] == True

    print(f"  Response status: {result['status']}")
    print(f"  Action type: {action['type']}")
    print(f"  Payload query: {payload['query'][:50]}...")
    print("  ✓ All response structure checks passed")


def test_deep_search_memory_persistence():
    """Verify deep_search_papers persists question in memory."""
    print("\n=== test_deep_search_memory_persistence ===")

    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    db = RealisticMockDB()
    ai_service = RealisticMockAIService()
    orchestrator = ToolOrchestrator(ai_service, db)

    channel = RealisticMockChannel()
    channel.ai_memory = {}

    ctx = {
        "project": RealisticMockProject(),
        "channel": channel,
        "recent_search_results": [],
    }

    question = "How do vision transformers compare to CNNs for medical imaging?"
    orchestrator._tool_deep_search_papers(ctx, research_question=question)

    # Verify memory was updated
    assert channel.ai_memory is not None, "Memory should not be None"
    assert "deep_search" in channel.ai_memory, "Missing 'deep_search' in memory"
    assert "last_question" in channel.ai_memory["deep_search"], "Missing 'last_question'"
    assert channel.ai_memory["deep_search"]["last_question"] == question

    # Verify DB commit was called
    assert db.commit_count > 0, "DB commit should have been called"

    print(f"  Memory stored question: {channel.ai_memory['deep_search']['last_question'][:50]}...")
    print(f"  DB commits: {db.commit_count}")
    print("  ✓ Memory persistence verified")


def test_focus_papers_from_search_results_data_transformation():
    """Verify focus_on_papers correctly transforms search result data."""
    print("\n=== test_focus_papers_data_transformation ===")

    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    db = RealisticMockDB()
    ai_service = RealisticMockAIService()
    orchestrator = ToolOrchestrator(ai_service, db)

    search_results = create_realistic_search_results(5)
    channel = RealisticMockChannel()
    channel.ai_memory = {}

    ctx = {
        "project": RealisticMockProject(),
        "channel": channel,
        "recent_search_results": search_results,
    }

    result = orchestrator._tool_focus_on_papers(ctx, paper_indices=[0, 1, 3])

    assert result["status"] == "success"
    assert result["focused_count"] == 3

    # Verify memory contains correct data
    focused = channel.ai_memory.get("focused_papers", [])
    assert len(focused) == 3, f"Expected 3 focused papers, got {len(focused)}"

    # Verify first paper data
    paper0 = focused[0]
    assert paper0["source"] == "search_result"
    assert paper0["index"] == 0
    assert paper0["title"] == "Attention Is All You Need"
    assert "Vaswani" in paper0["authors"]
    assert paper0["year"] == 2017
    assert len(paper0["abstract"]) > 100  # Has substantial abstract

    # Verify third paper (index 3 = ViT paper)
    paper2 = focused[2]
    assert paper2["index"] == 3
    assert "Transformer" in paper2["title"] or "Image" in paper2["title"]
    assert paper2["year"] == 2021

    print(f"  Focused papers: {[p['title'][:30] + '...' for p in focused]}")
    print(f"  Paper 0 authors: {focused[0]['authors'][:50]}...")
    print(f"  Paper 0 year: {focused[0]['year']}")
    print("  ✓ Data transformation verified")


def test_focus_papers_error_handling():
    """Verify focus_on_papers handles errors correctly."""
    print("\n=== test_focus_papers_error_handling ===")

    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    db = RealisticMockDB()
    ai_service = RealisticMockAIService()
    orchestrator = ToolOrchestrator(ai_service, db)

    search_results = create_realistic_search_results(3)
    channel = RealisticMockChannel()
    channel.ai_memory = {}

    ctx = {
        "project": RealisticMockProject(),
        "channel": channel,
        "recent_search_results": search_results,
    }

    # Test with mix of valid and invalid indices
    result = orchestrator._tool_focus_on_papers(ctx, paper_indices=[0, 5, 10, 1, -1])

    assert result["status"] == "success", "Should succeed with valid indices"
    assert result["focused_count"] == 2, f"Should have 2 valid papers, got {result['focused_count']}"

    # Check errors were reported
    errors = result.get("errors", [])
    assert len(errors) == 3, f"Should have 3 errors, got {len(errors)}"

    print(f"  Valid papers focused: {result['focused_count']}")
    print(f"  Errors reported: {len(errors)}")
    for err in errors:
        print(f"    - {err}")
    print("  ✓ Error handling verified")


def test_focus_papers_no_valid_inputs():
    """Verify focus_on_papers returns error when no valid inputs."""
    print("\n=== test_focus_papers_no_valid_inputs ===")

    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    db = RealisticMockDB()
    ai_service = RealisticMockAIService()
    orchestrator = ToolOrchestrator(ai_service, db)

    channel = RealisticMockChannel()
    ctx = {
        "project": RealisticMockProject(),
        "channel": channel,
        "recent_search_results": [],  # Empty search results
    }

    # Test with no search results and invalid indices
    result = orchestrator._tool_focus_on_papers(ctx, paper_indices=[0, 1])

    assert result["status"] == "error"
    assert "No papers could be focused" in result["message"]

    print(f"  Status: {result['status']}")
    print(f"  Message: {result['message']}")
    print("  ✓ No valid inputs error handling verified")


def test_analyze_across_papers_context_building():
    """Verify analyze_across_papers builds correct context from focused papers."""
    print("\n=== test_analyze_across_papers_context_building ===")

    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    db = RealisticMockDB()
    ai_service = RealisticMockAIService()
    orchestrator = ToolOrchestrator(ai_service, db)

    channel = RealisticMockChannel()
    channel.ai_memory = {
        "focused_papers": create_focused_papers_with_analysis()
    }

    ctx = {
        "project": RealisticMockProject(),
        "channel": channel,
    }

    result = orchestrator._tool_analyze_across_papers(
        ctx,
        analysis_question="How do their architectures differ?"
    )

    assert result["status"] == "success"
    assert result["paper_count"] == 2

    # Verify context contains paper information
    context = result["papers_context"]
    assert "Attention Is All You Need" in context
    assert "BERT" in context
    assert "Vaswani" in context
    assert "Devlin" in context

    # Verify full-text content is included for analyzed paper
    assert "self-attention" in context.lower() or "Self-attention" in context
    assert "Multi-head attention" in context or "key_findings" in context.lower()

    # Verify instruction is comprehensive
    instruction = result["instruction"]
    assert "Analyze" in instruction
    assert "common themes" in instruction.lower() or "patterns" in instruction.lower()
    assert "[Paper 1]" in instruction or "cite" in instruction.lower()

    print(f"  Context length: {len(context)} chars")
    print(f"  Papers in context: {result['paper_count']}")
    print(f"  Contains 'Attention Is All You Need': {'Yes' if 'Attention Is All You Need' in context else 'No'}")
    print(f"  Contains analysis data: {'Yes' if 'self-attention' in context.lower() else 'No'}")
    print("  ✓ Context building verified")


def test_analyze_across_papers_memory_update():
    """Verify analyze_across_papers updates memory correctly."""
    print("\n=== test_analyze_across_papers_memory_update ===")

    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    db = RealisticMockDB()
    ai_service = RealisticMockAIService()
    orchestrator = ToolOrchestrator(ai_service, db)

    channel = RealisticMockChannel()
    channel.ai_memory = {
        "focused_papers": [
            {"title": "Paper A", "authors": "Author", "year": 2024, "abstract": "Test"}
        ]
    }

    ctx = {
        "project": RealisticMockProject(),
        "channel": channel,
    }

    question = "Compare the methodologies used"
    orchestrator._tool_analyze_across_papers(ctx, analysis_question=question)

    # Verify memory was updated
    assert "cross_paper_analysis" in channel.ai_memory
    assert channel.ai_memory["cross_paper_analysis"]["last_question"] == question
    assert channel.ai_memory["cross_paper_analysis"]["paper_count"] == 1

    print(f"  Stored question: {channel.ai_memory['cross_paper_analysis']['last_question']}")
    print(f"  Paper count stored: {channel.ai_memory['cross_paper_analysis']['paper_count']}")
    print("  ✓ Memory update verified")


def test_analyze_across_papers_no_focused():
    """Verify analyze_across_papers handles no focused papers."""
    print("\n=== test_analyze_across_papers_no_focused ===")

    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    db = RealisticMockDB()
    ai_service = RealisticMockAIService()
    orchestrator = ToolOrchestrator(ai_service, db)

    channel = RealisticMockChannel()
    channel.ai_memory = {"focused_papers": []}  # Empty list

    ctx = {
        "project": RealisticMockProject(),
        "channel": channel,
    }

    result = orchestrator._tool_analyze_across_papers(ctx, analysis_question="Compare")

    assert result["status"] == "error"
    assert "No papers in focus" in result["message"]
    assert "suggestion" in result

    print(f"  Status: {result['status']}")
    print(f"  Message: {result['message']}")
    print(f"  Suggestion: {result['suggestion']}")
    print("  ✓ No focused papers error handling verified")


def test_generate_section_context_aggregation():
    """Verify generate_section aggregates all context sources."""
    print("\n=== test_generate_section_context_aggregation ===")

    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    db = RealisticMockDB()
    ai_service = RealisticMockAIService()
    orchestrator = ToolOrchestrator(ai_service, db)

    channel = RealisticMockChannel()
    channel.ai_memory = {
        "focused_papers": [
            {"title": "Focused Paper 1", "year": 2024, "key_findings": ["Finding A", "Finding B"]}
        ],
        "summary": "The user discussed transformer architectures for NLP applications.",
        "facts": {
            "research_topic": "Transformer-based NLP Models",
            "decisions_made": ["Use BERT as baseline", "Focus on encoder-only models"],
        },
        "deep_search": {
            "last_question": "What are the best practices for fine-tuning transformers?"
        },
        "cross_paper_analysis": {
            "last_question": "How do BERT and GPT architectures compare?"
        }
    }

    ctx = {
        "project": RealisticMockProject(),
        "channel": channel,
    }

    result = orchestrator._tool_generate_section_from_discussion(
        ctx,
        section_type="related_work",
        custom_instructions="Focus on recent 2023-2024 papers"
    )

    assert result["status"] == "success"

    context = result["context"]

    # Verify all context sources are included
    assert "Focused Paper 1" in context, "Missing focused papers"
    assert "transformer architectures" in context.lower() or "Transformer" in context, "Missing summary"
    assert "Transformer-based NLP" in context, "Missing research topic"
    assert "BERT as baseline" in context, "Missing decisions"
    assert "fine-tuning" in context.lower(), "Missing deep search question"
    assert "BERT and GPT" in context or "compare" in context.lower(), "Missing cross-analysis"

    # Verify custom instructions are included
    assert "2023-2024" in result["generation_prompt"]

    print(f"  Context length: {len(context)} chars")
    print(f"  Contains focused papers: Yes")
    print(f"  Contains summary: Yes")
    print(f"  Contains research topic: Yes")
    print(f"  Contains decisions: Yes")
    print(f"  Contains deep search: Yes")
    print(f"  Contains cross-analysis: Yes")
    print(f"  Custom instructions in prompt: Yes")
    print("  ✓ Context aggregation verified")


def test_generate_section_all_types():
    """Verify all section types generate different prompts."""
    print("\n=== test_generate_section_all_types ===")

    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    db = RealisticMockDB()
    ai_service = RealisticMockAIService()
    orchestrator = ToolOrchestrator(ai_service, db)

    section_types = ["methodology", "related_work", "introduction", "results", "discussion", "conclusion", "abstract"]
    prompts = {}

    for section_type in section_types:
        channel = RealisticMockChannel()
        channel.ai_memory = {}
        ctx = {
            "project": RealisticMockProject(),
            "channel": channel,
        }

        result = orchestrator._tool_generate_section_from_discussion(ctx, section_type=section_type)

        assert result["status"] == "success", f"Failed for {section_type}"
        assert result["section_type"] == section_type
        prompts[section_type] = result["generation_prompt"]

    # Verify prompts are different for each section type
    prompt_texts = list(prompts.values())
    unique_prompts = set(prompt_texts)
    assert len(unique_prompts) == len(section_types), "All section types should have unique prompts"

    # Verify specific keywords in prompts
    assert "research approach" in prompts["methodology"].lower() or "method" in prompts["methodology"].lower()
    assert "review" in prompts["related_work"].lower() or "literature" in prompts["related_work"].lower()
    assert "motivate" in prompts["introduction"].lower() or "background" in prompts["introduction"].lower()
    assert "150" in prompts["abstract"] or "250" in prompts["abstract"] or "word" in prompts["abstract"].lower()

    print(f"  Tested {len(section_types)} section types")
    print(f"  All prompts unique: Yes")
    for st in section_types:
        print(f"    - {st}: {len(prompts[st])} chars")
    print("  ✓ All section types verified")


def test_generate_section_with_target_paper():
    """Verify generate_section handles target paper correctly."""
    print("\n=== test_generate_section_with_target_paper ===")

    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    db = RealisticMockDB()
    ai_service = RealisticMockAIService()
    orchestrator = ToolOrchestrator(ai_service, db)

    channel = RealisticMockChannel()
    channel.ai_memory = {}
    ctx = {
        "project": RealisticMockProject(),
        "channel": channel,
    }

    paper_id = str(uuid4())
    result = orchestrator._tool_generate_section_from_discussion(
        ctx,
        section_type="methodology",
        target_paper_id=paper_id
    )

    assert result["status"] == "success"
    assert result["target_paper_id"] == paper_id
    assert "update_paper" in result["instruction"]

    # Should NOT have focused_paper_count (that's for artifacts)
    assert "focused_paper_count" not in result

    print(f"  Target paper ID: {paper_id[:8]}...")
    print(f"  Instruction mentions update_paper: Yes")
    print("  ✓ Target paper handling verified")


def test_tool_integration_workflow():
    """Test a realistic multi-step workflow."""
    print("\n=== test_tool_integration_workflow ===")

    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    db = RealisticMockDB()
    ai_service = RealisticMockAIService()
    orchestrator = ToolOrchestrator(ai_service, db)

    channel = RealisticMockChannel()
    channel.ai_memory = {}
    project = RealisticMockProject()
    search_results = create_realistic_search_results(5)

    ctx = {
        "project": project,
        "channel": channel,
        "recent_search_results": search_results,
    }

    # Step 1: Deep search
    print("  Step 1: Deep search")
    step1 = orchestrator._tool_deep_search_papers(
        ctx,
        research_question="How do transformers compare to CNNs for image classification?"
    )
    assert step1["status"] == "success"
    assert channel.ai_memory.get("deep_search", {}).get("last_question") is not None
    print(f"    - Question stored: Yes")

    # Step 2: Focus on papers
    print("  Step 2: Focus on papers")
    step2 = orchestrator._tool_focus_on_papers(ctx, paper_indices=[0, 3, 4])
    assert step2["status"] == "success"
    assert step2["focused_count"] == 3
    print(f"    - Papers focused: {step2['focused_count']}")

    # Step 3: Cross-paper analysis
    print("  Step 3: Cross-paper analysis")
    step3 = orchestrator._tool_analyze_across_papers(
        ctx,
        analysis_question="Compare their computational complexity"
    )
    assert step3["status"] == "success"
    assert step3["paper_count"] == 3
    print(f"    - Papers analyzed: {step3['paper_count']}")

    # Step 4: Generate section
    print("  Step 4: Generate related work section")
    step4 = orchestrator._tool_generate_section_from_discussion(
        ctx,
        section_type="related_work",
        custom_instructions="Emphasize efficiency comparisons"
    )
    assert step4["status"] == "success"

    # Verify context includes all previous steps
    context = step4["context"]
    assert "Attention Is All You Need" in context or "Paper" in context  # Has focused paper
    assert step4["focused_paper_count"] == 3
    print(f"    - Context includes focused papers: Yes")
    print(f"    - Focused paper count: {step4['focused_paper_count']}")

    # Verify memory state after workflow
    assert "deep_search" in channel.ai_memory
    assert "focused_papers" in channel.ai_memory
    assert "cross_paper_analysis" in channel.ai_memory
    print("    - Memory state preserved: Yes")

    print("  ✓ Full integration workflow verified")


def test_tool_routing_all_new_tools():
    """Verify all new tools are properly routed."""
    print("\n=== test_tool_routing_all_new_tools ===")

    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    db = RealisticMockDB()
    ai_service = RealisticMockAIService()
    orchestrator = ToolOrchestrator(ai_service, db)

    channel = RealisticMockChannel()
    channel.ai_memory = {"focused_papers": [{"title": "Test", "authors": "A", "year": 2024, "abstract": "X"}]}

    ctx = {
        "project": RealisticMockProject(),
        "channel": channel,
        "recent_search_results": create_realistic_search_results(3),
    }

    test_cases = [
        {
            "name": "deep_search_papers",
            "arguments": {"research_question": "Test question"},
            "expected_status": "success",
        },
        {
            "name": "focus_on_papers",
            "arguments": {"paper_indices": [0]},
            "expected_status": "success",
        },
        {
            "name": "analyze_across_papers",
            "arguments": {"analysis_question": "Compare them"},
            "expected_status": "success",
        },
        {
            "name": "generate_section_from_discussion",
            "arguments": {"section_type": "methodology"},
            "expected_status": "success",
        },
    ]

    for tc in test_cases:
        tool_calls = [{
            "id": f"call_{tc['name']}",
            "name": tc["name"],
            "arguments": tc["arguments"],
        }]

        results = orchestrator._execute_tool_calls(tool_calls, ctx)

        assert len(results) == 1, f"Expected 1 result for {tc['name']}"
        assert results[0]["name"] == tc["name"], f"Wrong tool name in result"

        result = results[0].get("result", {})
        if tc["expected_status"]:
            assert result.get("status") == tc["expected_status"], \
                f"Expected status '{tc['expected_status']}' for {tc['name']}, got '{result.get('status')}'"

        print(f"  {tc['name']}: {result.get('status', 'OK')}")

    print("  ✓ All tools properly routed")


# ============================================================
# Run All Tests
# ============================================================

def run_all_tests():
    """Run all detailed tests."""
    print("\n" + "=" * 70)
    print("Deep Search & Paper Focus Tools - Detailed Tests")
    print("=" * 70)

    tests = [
        test_deep_search_response_structure,
        test_deep_search_memory_persistence,
        test_focus_papers_from_search_results_data_transformation,
        test_focus_papers_error_handling,
        test_focus_papers_no_valid_inputs,
        test_analyze_across_papers_context_building,
        test_analyze_across_papers_memory_update,
        test_analyze_across_papers_no_focused,
        test_generate_section_context_aggregation,
        test_generate_section_all_types,
        test_generate_section_with_target_paper,
        test_tool_integration_workflow,
        test_tool_routing_all_new_tools,
    ]

    passed = 0
    failed = 0
    errors = []

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            failed += 1
            errors.append((test.__name__, f"ASSERTION: {e}"))
            print(f"  ✗ FAILED: {e}")
        except Exception as e:
            failed += 1
            errors.append((test.__name__, f"ERROR: {e}"))
            print(f"  ✗ ERROR: {e}")

    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    if errors:
        print("\nFailed tests:")
        for name, error in errors:
            print(f"  - {name}: {error}")

    return failed == 0


if __name__ == "__main__":
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(backend_dir)

    success = run_all_tests()
    sys.exit(0 if success else 1)
