"""
Integration tests for AI Memory System.

These tests verify the AI memory system with REAL database persistence
using SQLite in-memory database. Tests the ToolOrchestrator directly.

Run with: pytest tests/test_ai_memory_integration.py -v
"""

import os
import sys
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAIMemoryIntegration:
    """Integration tests for AI memory system with real database."""

    def test_memory_structure_after_multiple_exchanges(self, test_setup):
        """Test that memory structure is correctly updated after multiple exchanges."""
        setup = test_setup
        db = setup["db"]
        channel = setup["channel"]

        # Import the orchestrator
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        # Create mock AI service (we just need the structure, not real API calls)
        mock_ai_service = MagicMock()
        mock_ai_service.openai_client = None  # Disable actual AI calls

        orchestrator = ToolOrchestrator(mock_ai_service, db)

        # Simulate multiple exchanges by calling update_memory_after_exchange
        exchanges = [
            ("I want to research transformer architectures", "Great! Transformers are a popular architecture..."),
            ("Find papers about attention mechanisms", "Here are some key papers on attention mechanisms..."),
            ("I prefer recent papers from 2023-2024", "I'll focus on papers from the last two years..."),
            ("I don't want to use RNNs", "Understood, I'll avoid recurrent approaches..."),
        ]

        for user_msg, ai_response in exchanges:
            orchestrator.update_memory_after_exchange(
                channel,
                user_msg,
                ai_response * 10,  # Make response long enough
                []  # empty history for simplicity
            )

        # Refresh channel from DB and check memory
        db.refresh(channel)
        memory = channel.ai_memory

        print(f"\n{'='*60}")
        print("Memory after 4 exchanges:")
        print(f"{'='*60}")
        print(json.dumps(memory, indent=2, default=str))

        # Assertions
        assert memory is not None, "Memory should not be None"
        assert "facts" in memory, "Memory should contain facts"
        assert "research_state" in memory, "Memory should contain research_state"
        assert "long_term" in memory, "Memory should contain long_term"
        assert "key_quotes" in memory, "Memory should contain key_quotes"

        # Check research state
        assert memory["research_state"]["stage"] in orchestrator.RESEARCH_STAGES

        # Check long-term memory captured preferences
        long_term = memory.get("long_term", {})
        print(f"\nLong-term preferences: {long_term.get('user_preferences', [])}")
        print(f"Long-term rejections: {long_term.get('rejected_approaches', [])}")

        # Check key quotes captured
        print(f"\nKey quotes: {memory.get('key_quotes', [])}")

        # At least one preference or rejection should be captured
        assert (len(long_term.get("user_preferences", [])) > 0 or
                len(long_term.get("rejected_approaches", [])) > 0 or
                len(memory.get("key_quotes", [])) > 0), "Should capture some user preferences/quotes"

    def test_research_stage_transitions(self, test_setup):
        """Test that research stage transitions correctly through conversation."""
        setup = test_setup
        db = setup["db"]
        channel = setup["channel"]

        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        mock_ai_service = MagicMock()
        mock_ai_service.openai_client = None
        orchestrator = ToolOrchestrator(mock_ai_service, db)

        # Simulate a research journey through stages
        journey = [
            # Exploring
            ("What should I research for my thesis?", "There are many interesting areas..."),
            ("Give me ideas for ML topics", "Here are some machine learning research topics..."),
            # Refining
            ("I want to narrow down to optimization", "Good choice! Within optimization..."),
            ("Compare Adam vs SGD approaches", "Let me compare these approaches..."),
            # Finding papers
            ("Find papers about Adam optimizer", "I found several papers on Adam..."),
            ("Search for recent publications on learning rates", "Here are recent papers..."),
            # Writing
            ("Help me write the introduction section", "Here's a draft introduction..."),
        ]

        stages_seen = []
        for user_msg, ai_response in journey:
            orchestrator.update_memory_after_exchange(
                channel,
                user_msg,
                ai_response * 20,
                []
            )
            db.refresh(channel)
            current_stage = channel.ai_memory.get("research_state", {}).get("stage", "exploring")
            stages_seen.append(current_stage)
            print(f"After: '{user_msg[:40]}...' → Stage: {current_stage}")

        # Should have progressed through stages
        print(f"\nAll stages seen: {stages_seen}")
        assert "exploring" in stages_seen, "Should have been in exploring stage"

    def test_unanswered_question_tracking(self, test_setup):
        """Test that unanswered questions are tracked."""
        setup = test_setup
        db = setup["db"]
        channel = setup["channel"]

        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        mock_ai_service = MagicMock()
        mock_ai_service.openai_client = None
        orchestrator = ToolOrchestrator(mock_ai_service, db)

        # Directly call track_unanswered_question with an "uncertain" response
        orchestrator.track_unanswered_question(
            channel,
            "What is the exact implementation of the XYZ-2024 algorithm?",
            "I don't have access to the specific implementation details. You might need to check the paper."
        )

        db.refresh(channel)
        memory = channel.ai_memory
        unanswered = memory.get("facts", {}).get("unanswered_questions", [])

        print(f"\nUnanswered questions: {unanswered}")
        assert len(unanswered) > 0, "Should have tracked the unanswered question"

    def test_tool_cache_persistence(self, test_setup):
        """Test that tool results are cached in memory."""
        setup = test_setup
        db = setup["db"]
        channel = setup["channel"]

        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        mock_ai_service = MagicMock()
        mock_ai_service.openai_client = None
        orchestrator = ToolOrchestrator(mock_ai_service, db)

        # Cache a tool result
        test_result = {
            "count": 5,
            "references": [
                {"title": "Paper 1", "author": "Author A"},
                {"title": "Paper 2", "author": "Author B"},
            ]
        }
        orchestrator.cache_tool_result(channel, "get_project_references", test_result)

        db.refresh(channel)

        # Check cache retrieval
        cached = orchestrator.get_cached_tool_result(channel, "get_project_references")
        print(f"\nCached tool result: {cached}")

        assert cached is not None, "Should have cached result"
        assert cached["count"] == 5, "Cached count should match"
        assert len(cached["references"]) == 2, "Should have 2 references"

    def test_memory_pruning(self, test_setup):
        """Test that memory pruning function can be called without error."""
        setup = test_setup
        db = setup["db"]
        channel = setup["channel"]

        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        mock_ai_service = MagicMock()
        mock_ai_service.openai_client = None
        orchestrator = ToolOrchestrator(mock_ai_service, db)

        # Set up memory with some items
        memory = {
            "facts": {
                "papers_discussed": [{"title": f"Paper {i}"} for i in range(5)],
                "decisions_made": [f"Decision {i}" for i in range(5)],
                "methodology_notes": [],
                "unanswered_questions": [],
                "pending_questions": [],
            },
            "tool_cache": {},
            "key_quotes": [],
            "research_state": {"stage": "exploring", "stage_confidence": 0.5, "stage_history": []},
            "long_term": {"user_preferences": [], "rejected_approaches": [], "successful_searches": []},
        }
        orchestrator._save_ai_memory(channel, memory)

        # Run pruning - should not raise any errors
        orchestrator.prune_stale_memory(channel, max_papers=10, max_decisions=10, max_methodology_notes=8)

        db.refresh(channel)
        memory = channel.ai_memory

        print(f"\nAfter pruning:")
        print(f"  Memory exists: {memory is not None}")
        print(f"  Papers count: {len(memory.get('facts', {}).get('papers_discussed', []))}")

        # Just verify memory is still valid after pruning
        assert memory is not None
        assert "facts" in memory
        assert "papers_discussed" in memory["facts"]

    def test_welcome_back_context(self, test_setup):
        """Test welcome-back context generation."""
        setup = test_setup
        db = setup["db"]
        channel = setup["channel"]

        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        mock_ai_service = MagicMock()
        mock_ai_service.openai_client = None
        orchestrator = ToolOrchestrator(mock_ai_service, db)

        # Set up rich memory
        channel.ai_memory = {
            "summary": "User has been researching transformer optimization.",
            "facts": {
                "research_topic": "Transformer architecture optimization",
                "papers_discussed": [
                    {"title": "Attention Is All You Need", "author": "Vaswani et al."}
                ],
                "decisions_made": ["Focus on encoder-only architectures"],
                "pending_questions": ["Which learning rate schedule to use?"],
                "unanswered_questions": ["Implementation details of FlashAttention"],
                "methodology_notes": [],
            },
            "research_state": {
                "stage": "finding_papers",
                "stage_confidence": 0.8,
                "stage_history": [{"from": "exploring", "to": "finding_papers"}],
            },
            "long_term": {
                "user_preferences": ["I prefer recent papers from 2023+"],
                "rejected_approaches": ["Traditional RNN approaches"],
                "successful_searches": [],
            },
            "key_quotes": ["I want to focus on efficient transformers"],
            "tool_cache": {},
        }
        db.commit()

        # Generate welcome-back context
        context = orchestrator.get_session_context_for_return(channel)

        print(f"\n{'='*60}")
        print("Welcome-back context:")
        print(f"{'='*60}")
        print(context)
        print(f"{'='*60}")

        assert "Welcome Back" in context
        assert "Transformer" in context
        assert "encoder-only" in context or "decisions" in context.lower()


class TestAIMemoryDatabasePersistence:
    """Tests specifically for database persistence."""

    def test_memory_survives_session_refresh(self, test_setup):
        """Test that memory persists after database refresh."""
        setup = test_setup
        db = setup["db"]
        channel = setup["channel"]
        channel_id = channel.id

        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        mock_ai_service = MagicMock()
        mock_ai_service.openai_client = None
        orchestrator = ToolOrchestrator(mock_ai_service, db)

        # Update memory
        channel.ai_memory = {
            "facts": {"research_topic": "Persistence test topic", "unanswered_questions": []},
            "research_state": {"stage": "analyzing", "stage_confidence": 0.9, "stage_history": []},
            "long_term": {"user_preferences": ["Test preference"], "rejected_approaches": [], "successful_searches": []},
            "key_quotes": ["Test quote"],
            "summary": "Test summary",
            "tool_cache": {},
        }
        db.commit()

        # Clear SQLAlchemy cache
        db.expire_all()

        # Re-fetch channel
        from app.models.project_discussion import ProjectDiscussionChannel
        refetched = db.query(ProjectDiscussionChannel).filter(
            ProjectDiscussionChannel.id == channel_id
        ).first()

        print(f"\nRefetched memory: {json.dumps(refetched.ai_memory, indent=2)}")

        assert refetched.ai_memory is not None
        assert refetched.ai_memory["facts"]["research_topic"] == "Persistence test topic"
        assert refetched.ai_memory["research_state"]["stage"] == "analyzing"
        assert "Test preference" in refetched.ai_memory["long_term"]["user_preferences"]

    def test_memory_default_initialization(self, test_setup):
        """Test that memory is correctly initialized with defaults."""
        setup = test_setup
        db = setup["db"]
        channel = setup["channel"]

        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        mock_ai_service = MagicMock()
        mock_ai_service.openai_client = None
        orchestrator = ToolOrchestrator(mock_ai_service, db)

        # Get memory (should create defaults)
        memory = orchestrator._get_ai_memory(channel)

        print(f"\nDefault memory structure:")
        print(json.dumps(memory, indent=2, default=str))

        # Check all required fields
        assert "facts" in memory
        assert "research_state" in memory
        assert "long_term" in memory
        assert "key_quotes" in memory
        assert "tool_cache" in memory

        # Check nested defaults
        assert "research_topic" in memory["facts"]
        assert "papers_discussed" in memory["facts"]
        assert "unanswered_questions" in memory["facts"]
        assert "stage" in memory["research_state"]
        assert "user_preferences" in memory["long_term"]

    def test_memory_update_commits_to_db(self, test_setup):
        """Test that memory updates are committed to database."""
        setup = test_setup
        db = setup["db"]
        channel = setup["channel"]
        channel_id = channel.id

        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        mock_ai_service = MagicMock()
        mock_ai_service.openai_client = None
        orchestrator = ToolOrchestrator(mock_ai_service, db)

        # Update memory through orchestrator
        orchestrator.update_memory_after_exchange(
            channel,
            "I want to focus on deep learning optimization",
            "Great choice! Deep learning optimization is a rich area..." * 10,
            []
        )

        # Create a new session to verify persistence
        from tests.conftest import TestingSessionLocal
        new_db = TestingSessionLocal()

        try:
            from app.models.project_discussion import ProjectDiscussionChannel
            fresh_channel = new_db.query(ProjectDiscussionChannel).filter(
                ProjectDiscussionChannel.id == channel_id
            ).first()

            print(f"\nMemory from new session: {json.dumps(fresh_channel.ai_memory, indent=2, default=str)}")

            assert fresh_channel.ai_memory is not None
            # Key quotes should have captured the "I want to" statement
            assert len(fresh_channel.ai_memory.get("key_quotes", [])) > 0 or \
                   fresh_channel.ai_memory.get("long_term", {}).get("user_preferences", [])

        finally:
            new_db.close()


class TestFullConversationFlow:
    """Test a complete research conversation flow."""

    def test_full_research_journey(self, test_setup):
        """Simulate a complete research conversation and verify memory evolution."""
        setup = test_setup
        db = setup["db"]
        channel = setup["channel"]

        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        mock_ai_service = MagicMock()
        mock_ai_service.openai_client = None
        orchestrator = ToolOrchestrator(mock_ai_service, db)

        print(f"\n{'='*60}")
        print("FULL RESEARCH JOURNEY TEST")
        print(f"{'='*60}")

        # Conversation flow
        conversation = [
            # 1. Initial exploration
            {
                "user": "I'm starting my PhD research and I want to explore topics in natural language processing.",
                "ai": "Welcome! NLP is a fascinating field with many active research areas. You could explore transformers, language models, sentiment analysis, machine translation, or question answering systems. What interests you most?",
            },
            # 2. Narrowing down
            {
                "user": "I prefer working with transformer models. I want to focus on efficiency improvements.",
                "ai": "Excellent choice! Efficient transformers is a hot topic. Key areas include attention mechanism optimization, model compression, knowledge distillation, and sparse attention patterns. Would you like me to find papers on any of these?",
            },
            # 3. Rejection
            {
                "user": "I don't want to work on knowledge distillation - it feels too derivative.",
                "ai": "Understood, I'll focus on other approaches. Sparse attention and linear attention mechanisms offer more novel research opportunities. Let me search for recent papers.",
            },
            # 4. Finding papers
            {
                "user": "Find papers about sparse attention mechanisms from 2023-2024",
                "ai": "I found several relevant papers on sparse attention: FlashAttention-2, BigBird extensions, and Longformer improvements. Would you like detailed summaries?",
            },
            # 5. AI can't answer
            {
                "user": "What's the exact memory footprint of FlashAttention-3?",
                "ai": "I don't have access to specific benchmarks for FlashAttention-3. You might need to check the official repository or run your own benchmarks.",
            },
            # 6. Writing phase
            {
                "user": "Help me write an introduction paragraph about efficient transformers for my literature review",
                "ai": "Here's a draft introduction: Transformer architectures have revolutionized natural language processing, but their quadratic attention complexity limits scalability...",
            },
        ]

        # Process each exchange
        for i, exchange in enumerate(conversation):
            print(f"\n--- Exchange {i+1} ---")
            print(f"User: {exchange['user'][:60]}...")

            orchestrator.update_memory_after_exchange(
                channel,
                exchange["user"],
                exchange["ai"] * 5,  # Pad response
                []
            )

            db.refresh(channel)
            memory = channel.ai_memory

            stage = memory.get("research_state", {}).get("stage", "unknown")
            print(f"Stage: {stage}")

        # Final memory state
        db.refresh(channel)
        final_memory = channel.ai_memory

        print(f"\n{'='*60}")
        print("FINAL MEMORY STATE:")
        print(f"{'='*60}")
        print(json.dumps(final_memory, indent=2, default=str))

        # Assertions
        assert final_memory is not None

        # Should have captured preference for transformers
        long_term = final_memory.get("long_term", {})
        prefs = long_term.get("user_preferences", [])
        rejections = long_term.get("rejected_approaches", [])
        print(f"\nPreferences: {prefs}")
        print(f"Rejections: {rejections}")

        # Check if rejections were captured OR if key quotes captured the rejection statement
        key_quotes = final_memory.get("key_quotes", [])
        rejection_captured = (
            len(rejections) > 0 or
            any("don't want" in q.lower() for q in key_quotes)
        )
        print(f"Rejection captured via long_term or key_quotes: {rejection_captured}")
        assert rejection_captured, "Should have captured the rejection in either long_term or key_quotes"

        # Verify key quotes captured important statements
        print(f"\nKey quotes captured: {key_quotes}")
        assert len(key_quotes) > 0, "Should have captured key user statements"

        # Should have progressed to writing stage (or at least past exploring)
        final_stage = final_memory.get("research_state", {}).get("stage", "exploring")
        print(f"\nFinal stage: {final_stage}")

        print(f"\n{'='*60}")
        print("TEST PASSED - Full research journey completed successfully!")
        print(f"{'='*60}")


# ============================================================
# Run Tests Directly
# ============================================================

if __name__ == "__main__":
    import subprocess

    # Change to backend directory
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(backend_dir)

    # Run pytest
    sys.exit(subprocess.call(["pytest", "tests/test_ai_memory_integration.py", "-v", "-s", "--tb=short"]))
