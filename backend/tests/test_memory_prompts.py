"""
Prompt-based tests for the AI Memory System.

Tests each memory subsystem against a curated list of realistic user prompts
and their expected extraction/classification outcomes.

Run with: pytest tests/test_memory_prompts.py -v
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockChannel:
    def __init__(self, ai_memory=None):
        self.id = "prompt-test-channel"
        self.name = "Prompt Test"
        self.ai_memory = ai_memory


class MockDB:
    def commit(self): pass
    def rollback(self): pass
    def query(self, *a, **kw): return self
    def filter(self, *a, **kw): return self
    def count(self): return 0
    def order_by(self, *a): return self
    def limit(self, n): return self
    def all(self): return []


class MockAIService:
    def __init__(self):
        self.default_model = "gpt-4o-mini"
        self.openai_client = MagicMock()


def _make_orchestrator():
    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator
    return ToolOrchestrator(MockAIService(), MockDB())


# ===================================================================
# 1. Direct Research Question Extraction
# ===================================================================

# Each tuple: (user_message, should_extract: bool, substring_in_result_or_None)
RQ_EXTRACTION_CASES = [
    # --- Should extract ---
    (
        "My research question is: How does social media usage affect academic performance among university students?",
        True,
        "social media",
    ),
    (
        "The research question is: What role does sleep quality play in cognitive function of elderly adults?",
        True,
        "sleep quality",
    ),
    (
        'My research question is "How do microplastics accumulate in freshwater ecosystems?"',
        True,
        "microplastics",
    ),
    (
        "My RQ is: What factors influence teacher retention in rural school districts?",
        True,
        "teacher retention",
    ),
    (
        "I'm investigating the relationship between gut microbiome diversity and autoimmune disorders.",
        True,
        "gut microbiome",
    ),
    (
        "I'm exploring how remote work policies affect employee productivity and well-being in tech companies.",
        True,
        "remote work",
    ),
    (
        "I am studying the effects of urbanization on biodiversity in tropical regions.",
        True,
        "urbanization",
    ),
    (
        "I want to understand how algorithmic bias in hiring tools impacts minority job applicants.",
        True,
        "algorithmic bias",
    ),
    (
        "I'd like to investigate how climate change affects migration patterns of Arctic bird species.",
        True,
        "climate change",
    ),
    (
        "I want to find out whether gamification improves student engagement in online learning platforms.",
        True,
        "gamification",
    ),
    # Standalone research question (short message, single ?)
    (
        "How does exposure to air pollution during childhood affect long-term cognitive development?",
        True,
        "air pollution",
    ),
    (
        "What is the relationship between social media addiction and depression in adolescents?",
        True,
        "social media addiction",
    ),
    # --- Should NOT extract ---
    (
        "Can you help me find papers?",
        False,
        None,
    ),
    (
        "Could you search for more recent studies?",
        False,
        None,
    ),
    (
        "What is X?",
        False,
        None,  # Too short (<30 chars)
    ),
    (
        "Tell me more about this topic.",
        False,
        None,
    ),
    (
        "Thanks, that's helpful!",
        False,
        None,
    ),
    (
        "Yes, I agree with that approach.",
        False,
        None,
    ),
    (
        "Do you have access to full-text PDFs?",
        False,
        None,
    ),
    (
        "Will you remember this for next time?",
        False,
        None,
    ),
    (
        "Have you seen the latest paper by Smith et al.?",
        False,
        None,
    ),
    # Edge case: long message with multiple questions (>300 chars) — standalone pattern won't fire
    (
        "I have a few things on my mind. First, I'm not sure which database to use for my literature search. "
        "Second, I need help narrowing down my scope because there are too many subtopics. "
        "Third, should I include qualitative studies or stick to quantitative only? "
        "Also, what time frame should I limit my search to? Last five years or ten years?",
        False,
        None,
    ),
    # Edge case: research-sounding but actually a request
    (
        "Are you able to research the history of quantum computing for me?",
        False,
        None,
    ),
]


class TestRQExtractionPrompts:
    """Test _extract_research_question_direct against curated prompts."""

    @pytest.mark.parametrize(
        "user_message, should_extract, expected_substring",
        RQ_EXTRACTION_CASES,
        ids=[f"rq_{i}" for i in range(len(RQ_EXTRACTION_CASES))],
    )
    def test_rq_extraction(self, user_message, should_extract, expected_substring):
        orchestrator = _make_orchestrator()
        result = orchestrator._extract_research_question_direct(user_message)

        if should_extract:
            assert result is not None, f"Expected extraction from: {user_message!r}"
            assert expected_substring.lower() in result.lower(), (
                f"Expected '{expected_substring}' in result '{result}'"
            )
        else:
            assert result is None, (
                f"Expected None but got '{result}' from: {user_message!r}"
            )


# ===================================================================
# 2. Urgency Bypass for should_update_facts
# ===================================================================

# Each tuple: (user_message, should_bypass: bool)
URGENCY_BYPASS_CASES = [
    # --- Should bypass rate limit ---
    ("My research question is about the impact of AI on education.", True),
    ("I want to study the effects of exercise on mental health.", True),
    ("I'm investigating whether bilingual education improves test scores.", True),
    ("My topic is machine learning for drug discovery.", True),
    ("I decided to focus on renewable energy policy.", True),
    ("I've decided to narrow my scope to CRISPR applications in agriculture.", True),
    ("Let's go with the qualitative methodology approach.", True),
    ("I'm focusing on NLP applications in healthcare.", True),
    ("My goal is to understand vaccine hesitancy in rural communities.", True),
    ("The main question is whether autonomous vehicles reduce traffic accidents.", True),
    ("I want to explore the link between diet and Alzheimer's disease.", True),
    ("My thesis is about climate change adaptation strategies in coastal cities.", True),
    # --- Should NOT bypass (normal conversation) ---
    ("Tell me more about this.", False),
    ("Can you find more papers?", False),
    ("That's interesting, continue.", False),
    ("What do you think about methodology?", False),
    ("Search for papers on BERT.", False),
    ("Summarize the last three papers.", False),
    ("I like the second approach better.", False),
    ("Show me the references.", False),
    ("Thanks for the help!", False),
    ("Yes, that sounds right.", False),
]


class TestUrgencyBypassPrompts:
    """Test should_update_facts urgency bypass against curated prompts."""

    @pytest.mark.parametrize(
        "user_message, should_bypass",
        URGENCY_BYPASS_CASES,
        ids=[f"urgency_{i}" for i in range(len(URGENCY_BYPASS_CASES))],
    )
    def test_urgency_bypass(self, user_message, should_bypass):
        orchestrator = _make_orchestrator()

        # Set up channel with existing facts and exchange_count=0
        # (i.e., rate limiter would normally block)
        channel = MockChannel(ai_memory={
            "facts": {"research_topic": "Existing Topic"},
            "_exchanges_since_fact_update": 0,
        })

        long_response = "Here is a detailed analysis of the topic. " * 20
        result = orchestrator.should_update_facts(
            channel, long_response, user_message=user_message
        )

        assert result is should_bypass, (
            f"Expected bypass={should_bypass} for: {user_message!r}"
        )


# ===================================================================
# 3. Unanswered Question Tracking
# ===================================================================

# Each tuple: (user_message, ai_response, should_track: bool, description)
UNANSWERED_QUESTION_CASES = [
    # --- Should track (real unanswered question) ---
    (
        "What datasets are commonly used for NER evaluation in biomedical text?",
        "That's a great area to explore, let me think about it.",
        True,
        "Direct research question, vague AI response",
    ),
    (
        "What are the main limitations of transformer models for low-resource languages?",
        "I'll need to look into that further.",
        True,
        "Specific technical question, non-answer",
    ),
    (
        "Which statistical tests should I use to compare these two groups?",
        "There are various options depending on your data distribution.",
        True,
        "Methodology question, generic response",
    ),
    (
        "How does the attention mechanism handle variable-length sequences in this architecture?",
        "Let me check on the specific implementation details.",
        True,
        "Technical detail question, deferred answer",
    ),
    # --- Should NOT track (answered questions) ---
    (
        "What is the difference between BERT and GPT architectures?",
        "Here's a comparison: BERT uses bidirectional encoding while GPT uses autoregressive decoding. Based on the literature...",
        False,
        "Question with substantive answer containing 'here's' and 'based on'",
    ),
    (
        "How do I calculate effect size for my study?",
        "I found several methods: Cohen's d for comparing means, eta-squared for ANOVA. According to Cohen (1988)...",
        False,
        "Question answered with 'I found' and 'according to'",
    ),
    (
        "What are the key findings from Smith et al. 2023?",
        "The key finding is that the intervention reduced symptoms by 40%. The results show a significant improvement.",
        False,
        "Question answered with 'the results show'",
    ),
    # --- Should NOT track (not real questions) ---
    (
        "What?",
        "Could you clarify your question?",
        False,
        "Too short (<30 chars)",
    ),
    (
        "Huh?",
        "I didn't understand. Could you rephrase?",
        False,
        "Too short",
    ),
    (
        "I know how transformers work, right?",
        "Yes, your understanding seems correct.",
        False,
        "Declaration with '?' — starts with 'I know'",
    ),
    (
        "I think this approach is better, don't you agree?",
        "Yes, I agree that approach has merit.",
        False,
        "Short rhetorical question — question sentence too short",
    ),
    (
        "I want to use BERT for my project, okay?",
        "Sure, BERT is a great choice.",
        False,
        "Declaration starting with 'I want' — excluded",
    ),
    (
        "I believe this is the right framework, what do you think?",
        "It could work, let me consider alternatives.",
        False,
        "Starts with 'I believe' — excluded",
    ),
    (
        "Tell me more about deep learning.",
        "Deep learning is a subset of machine learning...",
        False,
        "No question mark at all",
    ),
    (
        "I need help with my literature review.",
        "Sure, let's start by identifying key papers.",
        False,
        "No question mark",
    ),
]


class TestUnansweredQuestionPrompts:
    """Test _track_unanswered_question_inline against curated prompts."""

    @pytest.mark.parametrize(
        "user_message, ai_response, should_track, description",
        UNANSWERED_QUESTION_CASES,
        ids=[c[3] for c in UNANSWERED_QUESTION_CASES],
    )
    def test_unanswered_tracking(self, user_message, ai_response, should_track, description):
        orchestrator = _make_orchestrator()
        memory = {"facts": {"unanswered_questions": []}}

        orchestrator._track_unanswered_question_inline(
            memory, user_message, ai_response
        )

        tracked_count = len(memory["facts"]["unanswered_questions"])

        if should_track:
            assert tracked_count >= 1, (
                f"Expected question to be tracked [{description}]: {user_message!r}"
            )
        else:
            assert tracked_count == 0, (
                f"False positive [{description}]: {user_message!r} "
                f"tracked as: {memory['facts']['unanswered_questions']}"
            )


# ===================================================================
# 4. Key Quote Extraction
# ===================================================================

# Each tuple: (user_message, should_extract: bool, expected_pattern_in_quote)
KEY_QUOTE_CASES = [
    # --- Should extract ---
    (
        "I want to focus on neural network architectures for image classification in medical imaging.",
        True,
        "focus on neural network",
    ),
    (
        "I need a framework that supports real-time inference on edge devices.",
        True,
        "need a framework",
    ),
    (
        "I decided to use a mixed-methods approach combining surveys and interviews.",
        True,
        "decided to use",
    ),
    (
        "I prefer quantitative studies over qualitative for this research.",
        True,
        "prefer quantitative",
    ),
    (
        "I'm focusing on the intersection of AI ethics and healthcare policy.",
        True,
        "focusing on",
    ),
    (
        "My goal is to develop a model that outperforms current baselines on the GLUE benchmark.",
        True,
        "goal is to develop",
    ),
    (
        "Specifically, I want to look at attention mechanisms in vision transformers.",
        True,
        "specifically",
    ),
    (
        "I don't want to include papers older than 2020 in my review.",
        True,
        "don't want",
    ),
    # --- Should NOT extract ---
    (
        "Yes, that sounds good.",
        False,
        None,
    ),
    (
        "Okay, let's continue.",
        False,
        None,
    ),
    (
        "Thanks for the summary.",
        False,
        None,
    ),
    (
        "Can you search for more papers?",
        False,
        None,
    ),
]


class TestKeyQuotePrompts:
    """Test _extract_key_quotes against curated prompts."""

    @pytest.mark.parametrize(
        "user_message, should_extract, expected_pattern",
        KEY_QUOTE_CASES,
        ids=[f"quote_{i}" for i in range(len(KEY_QUOTE_CASES))],
    )
    def test_key_quote_extraction(self, user_message, should_extract, expected_pattern):
        orchestrator = _make_orchestrator()
        quotes = orchestrator._extract_key_quotes(user_message, [])

        if should_extract:
            assert len(quotes) >= 1, (
                f"Expected quote extraction from: {user_message!r}"
            )
            assert any(expected_pattern.lower() in q.lower() for q in quotes), (
                f"Expected '{expected_pattern}' in quotes {quotes}"
            )
        else:
            assert len(quotes) == 0, (
                f"Unexpected quote extracted from: {user_message!r} — got {quotes}"
            )


# ===================================================================
# 5. Research Stage Detection
# ===================================================================

# Each tuple: (user_message, ai_response, current_stage, expected_stage)
RESEARCH_STAGE_CASES = [
    # Exploring
    (
        "What should I research for my thesis? I need ideas for a topic.",
        "Here are some research areas you could explore...",
        "exploring",
        "exploring",
    ),
    (
        "Where do I start with my literature review? I need a broad overview.",
        "Let me introduce you to the main areas...",
        "exploring",
        "exploring",
    ),
    # Refining
    (
        "I want to narrow down my scope. Should I focus on NLP or computer vision?",
        "Let's compare the pros and cons of each approach...",
        "exploring",
        "refining",
    ),
    (
        "Between these two approaches, which should I choose? I need to be more specific.",
        "Here are the pros and cons...",
        "exploring",
        "refining",
    ),
    # Finding papers
    (
        "Find papers about transformer architectures in NLP. I need recent publications.",
        "I found several key papers on transformers...",
        "exploring",
        "finding_papers",
    ),
    (
        "Search for literature on deep reinforcement learning. Who wrote about this recently?",
        "Here are some seminal works and recent papers...",
        "refining",
        "finding_papers",
    ),
    # Analyzing
    (
        "Explain this paper's methodology in detail. How does this technique work?",
        "The paper uses a novel approach to implement...",
        "finding_papers",
        "analyzing",
    ),
    (
        "I want to dive deeper into the specific technique described in section 3.",
        "Let me break down the details of this method...",
        "finding_papers",
        "analyzing",
    ),
    # Writing
    (
        "Help me write the introduction section for my literature review.",
        "Here's a draft introduction for your literature review...",
        "analyzing",
        "writing",
    ),
    (
        "I need to draft an abstract and create a thesis statement for my paper.",
        "Here's a draft abstract...",
        "analyzing",
        "writing",
    ),
    # Inertia: weak signal doesn't change stage
    (
        "That's interesting, tell me more.",
        "Sure, here's more detail...",
        "finding_papers",
        "finding_papers",  # Should stay because no strong signal
    ),
]


class TestResearchStagePrompts:
    """Test detect_research_stage against curated prompts."""

    @pytest.mark.parametrize(
        "user_message, ai_response, current_stage, expected_stage",
        RESEARCH_STAGE_CASES,
        ids=[f"stage_{i}" for i in range(len(RESEARCH_STAGE_CASES))],
    )
    def test_research_stage(self, user_message, ai_response, current_stage, expected_stage):
        orchestrator = _make_orchestrator()
        stage, confidence = orchestrator.detect_research_stage(
            user_message, ai_response, current_stage
        )

        assert stage == expected_stage, (
            f"Expected stage '{expected_stage}' but got '{stage}' "
            f"(confidence={confidence:.2f}) for: {user_message!r}"
        )


# ===================================================================
# 6. Long-Term Memory: Preferences & Rejections
# ===================================================================

# Each tuple: (user_message, category: "preference"|"rejection"|"none", expected_substring)
LONG_TERM_MEMORY_CASES = [
    # Preferences
    ("I prefer using recent papers from the last 5 years.", "preference", "prefer"),
    ("I like quantitative methods more than qualitative.", "preference", "like quantitative"),
    ("I want to use PyTorch for all experiments.", "preference", "want to use PyTorch"),
    ("Let's use the BERT model as our baseline.", "preference", "use the BERT"),
    ("We should use cross-validation for evaluation.", "preference", "should use cross"),
    ("I'd rather focus on English-language papers only.", "preference", "rather focus"),
    # Rejections
    ("I don't want to include survey-based studies.", "rejection", "don't want"),
    ("I'm not interested in approaches that require proprietary datasets.", "rejection", "not interested"),
    ("Avoid papers that only test on synthetic data.", "rejection", "avoid"),
    ("I don't like the Bayesian approach for this problem.", "rejection", "don't like"),
    ("I ruled out using RNNs since transformers outperform them.", "rejection", "ruled out"),
    ("That method won't work because we don't have enough training data.", "rejection", "won't work"),
    # Neither
    ("Tell me more about the methodology.", "none", None),
    ("Can you search for recent papers on this topic?", "none", None),
    ("That's a good point, I agree.", "none", None),
    ("Summarize the key findings from those three papers.", "none", None),
]


class TestLongTermMemoryPrompts:
    """Test _update_long_term_memory_inline against curated prompts."""

    @pytest.mark.parametrize(
        "user_message, category, expected_substring",
        LONG_TERM_MEMORY_CASES,
        ids=[f"ltm_{i}" for i in range(len(LONG_TERM_MEMORY_CASES))],
    )
    def test_long_term_memory(self, user_message, category, expected_substring):
        orchestrator = _make_orchestrator()
        memory = {
            "long_term": {
                "user_preferences": [],
                "rejected_approaches": [],
            }
        }

        orchestrator._update_long_term_memory_inline(
            memory, user_message, "Understood, I'll adjust accordingly."
        )

        prefs = memory["long_term"]["user_preferences"]
        rejections = memory["long_term"]["rejected_approaches"]

        if category == "preference":
            assert len(prefs) >= 1, (
                f"Expected preference from: {user_message!r}"
            )
            assert any(expected_substring.lower() in p.lower() for p in prefs), (
                f"Expected '{expected_substring}' in {prefs}"
            )
            assert len(rejections) == 0, (
                f"Unexpected rejection from preference message: {rejections}"
            )
        elif category == "rejection":
            assert len(rejections) >= 1, (
                f"Expected rejection from: {user_message!r}"
            )
            assert any(expected_substring.lower() in r.lower() for r in rejections), (
                f"Expected '{expected_substring}' in {rejections}"
            )
            assert len(prefs) == 0, (
                f"Unexpected preference from rejection message: {prefs}"
            )
        else:
            assert len(prefs) == 0 and len(rejections) == 0, (
                f"Expected no extraction from: {user_message!r} "
                f"— got prefs={prefs}, rejections={rejections}"
            )


# ===================================================================
# 7. Integration: Direct RQ + Memory Update Flow
# ===================================================================

class TestRQIntegrationFlow:
    """Test that direct RQ extraction integrates into update_memory_after_exchange."""

    def test_rq_set_in_memory_after_exchange(self):
        """Explicit RQ statement should populate memory.facts.research_question."""
        orchestrator = _make_orchestrator()
        channel = MockChannel(ai_memory={})

        # Mock _save_ai_memory to actually store on channel (bypass DB)
        def fake_save(ch, mem):
            ch.ai_memory = mem

        # Mock _extract_research_facts to return existing facts unchanged
        def passthrough_facts(user_msg, ai_resp, existing, **kw):
            return existing

        with patch.object(orchestrator, '_save_ai_memory', side_effect=fake_save), \
             patch.object(orchestrator, '_extract_research_facts', side_effect=passthrough_facts), \
             patch('app.services.discussion_ai.token_utils.should_summarize', return_value=False):
            orchestrator.update_memory_after_exchange(
                channel,
                "My research question is: How does social media usage affect academic performance?",
                "That's a great research question. Let me help you explore this topic. " * 20,
                [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}],
            )

        memory = orchestrator._get_ai_memory(channel)
        rq = memory.get("facts", {}).get("research_question")
        assert rq is not None, "research_question should be populated"
        assert "social media" in rq.lower()

    def test_rq_not_overwritten_by_casual_message(self):
        """A casual follow-up should not wipe out an existing RQ."""
        orchestrator = _make_orchestrator()
        channel = MockChannel(ai_memory={
            "facts": {
                "research_question": "How does X affect Y?",
                "research_topic": "X and Y",
            },
            "key_quotes": [],
        })

        with patch.object(orchestrator, '_save_ai_memory'), \
             patch('app.services.discussion_ai.token_utils.should_summarize', return_value=False):
            orchestrator.update_memory_after_exchange(
                channel,
                "Tell me more about methodology options.",
                "Here are some methodology options you might consider... " * 20,
                [],
            )

        memory = orchestrator._get_ai_memory(channel)
        rq = memory.get("facts", {}).get("research_question")
        assert rq == "How does X affect Y?", (
            f"RQ should be preserved but got: {rq!r}"
        )
