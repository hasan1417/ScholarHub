"""
Intent Router - Classifies user messages and routes to appropriate skill.

Uses a fast LLM call or rule-based matching to determine intent.
This is the "dispatcher" in the dispatcher pattern.
"""

from __future__ import annotations

import re
from typing import Optional, TYPE_CHECKING

from .base import Intent, ClassifiedIntent, SkillState

if TYPE_CHECKING:
    from app.services.ai_service import AIService


class IntentRouter:
    """
    Classifies user intent and routes to appropriate skill.

    Uses a hybrid approach:
    1. Rule-based matching for common patterns (fast, no LLM call)
    2. LLM classification for ambiguous cases (slower, more accurate)
    """

    # Rule-based patterns for fast matching
    SEARCH_PATTERNS = [
        r"\b(find|search|look for|get|fetch)\b.*(paper|reference|article|study|research)",
        r"\b(paper|reference|article)s?\b.*(about|on|for|regarding)",
        r"\bsearch\b",
    ]

    CREATE_PATTERNS = [
        r"\b(create|write|generate|draft|make|compose)\b.*(review|summary|paper|outline|introduction|abstract)",
        r"\bliterature review\b",
        r"\bwrite.*(about|for|on)\b",
    ]

    EDIT_PATTERNS = [
        r"\b(edit|modify|change|update|fix|improve|revise)\b.*(paper|document|section|paragraph)",
        r"\b(add|remove|delete)\b.*(section|paragraph|sentence)",
    ]

    CHAT_PATTERNS = [
        r"^(hi|hello|hey|thanks|thank you|ok|okay|yes|no|sure)[\s!?.]*$",
        r"^(good morning|good afternoon|good evening|bye|goodbye)[\s!?.]*$",
        r"^what can you (do|help)",
        r"^how (can|do) you help",
    ]

    EXPLAIN_PATTERNS = [
        # Questions about papers
        r"\bexplain\b.*(paper|concept|method|approach|how|what)",
        r"\bexplain\s+how\b",
        r"\bwhat\s+(does|is)\s+(the|this|that|my)\s+(paper|first|second|third)",
        r"\b(first|second|third|\d+st|\d+nd|\d+rd)\s+paper\b",
        r"\bwhat\s+are\s+(our|the|my)\s+(project\s+)?(objectives?|goals?|scope)",
        r"\bwhat\s+does\s+(my|our)\s+paper\s+say",
        r"\b(summarize|explain)\s+(the|these|those|above)\s+papers?\b",
        r"\bsummarize\s+(the\s+)?(above|discovered|found)",
        r"\bmain\s+contribution\b",
        r"\bwhat\s+(is|are)\s+the\s+(key|main)\s+(point|finding|contribution)s?\b",
        r"\bcompare\s+(the|these)?\s*papers?\b",
        # Questions about project
        r"\bproject\s+(objective|goal|scope|description)s?\b",
        r"\bwhat\s+(is|are)\s+we\s+(doing|trying|working)",
        r"\bwhat('s|\s+is)\s+the\s+scope\b",
        r"\bremind\s+me\s+what\b",
        r"\bthis\s+project\s+(is\s+)?about\b",
        # Questions about references/library
        r"\bwhat\s+do\s+(my|our)\s+(reference|saved|library)",
        r"\b(my|our)\s+references?\s+say\b",
        r"\b(saved|my)\s+papers?\s+discuss",
        r"\bcite\s+from\s+(my|the)\s+library\b",
        # Questions about own paper
        r"\bour\s+paper'?s?\s+(introduction|methodology|conclusion)",
        r"\bwhat\s+claims?\s+(do|does)\s+(we|our)\b",
        # General concept explanations
        r"\bwhat\s+is\s+a?\s*(transformer|attention|bert|gpt|cnn|rnn)",
        r"\bhow\s+does\s+\w+\s+differ\b",
        r"\bhow\s+does\s+\w+\s+work\b",
    ]

    # Continuation patterns - user answering a previous question
    CONTINUATION_PATTERNS = [
        r"^(chat|in chat|paper|as paper|create paper|write in chat)[\s!?.]*$",
        r"^\d+\.\s*\w+",  # Numbered answers like "1. thematic, 2. 2 pages"
        r"^(yes|no|sure|ok|okay)[\s,]",
    ]

    def __init__(self, ai_service: Optional["AIService"] = None):
        self.ai_service = ai_service

    def classify(
        self,
        message: str,
        current_skill: Optional[str] = None,
        skill_state: SkillState = SkillState.IDLE,
    ) -> ClassifiedIntent:
        """
        Classify user message intent.

        If there's an active skill in non-IDLE state, treat as continuation.
        Otherwise, classify the intent.
        """
        msg = message.strip().lower()

        # If we're in a multi-turn flow, this is a continuation
        if current_skill and skill_state != SkillState.IDLE:
            return ClassifiedIntent(
                intent=Intent.CONTINUATION,
                confidence=1.0,
                params={"original_message": message},
            )

        # Try rule-based classification first (fast)
        result = self._rule_based_classify(msg, message)
        if result and result.confidence >= 0.8:
            return result

        # For ambiguous cases, could use LLM classification
        # For now, fall back to CHAT
        return ClassifiedIntent(intent=Intent.CHAT, confidence=0.5)

    def _rule_based_classify(self, msg_lower: str, original: str) -> Optional[ClassifiedIntent]:
        """Fast rule-based classification."""

        # Check continuation patterns first
        for pattern in self.CONTINUATION_PATTERNS:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                return ClassifiedIntent(
                    intent=Intent.CONTINUATION,
                    confidence=0.9,
                    params={"original_message": original},
                )

        # Check chat patterns (greetings, etc.)
        for pattern in self.CHAT_PATTERNS:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                return ClassifiedIntent(intent=Intent.CHAT, confidence=0.95)

        # Check explain patterns BEFORE search (to avoid misclassifying questions about papers)
        for pattern in self.EXPLAIN_PATTERNS:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                return ClassifiedIntent(intent=Intent.EXPLAIN, confidence=0.9)

        # Check search patterns
        for pattern in self.SEARCH_PATTERNS:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                # Extract search query
                query = self._extract_search_query(original)
                count = self._extract_count(original)
                return ClassifiedIntent(
                    intent=Intent.SEARCH,
                    confidence=0.9,
                    params={"query": query, "count": count},
                )

        # Check create patterns
        for pattern in self.CREATE_PATTERNS:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                params = self._extract_create_params(original)
                return ClassifiedIntent(
                    intent=Intent.CREATE_CONTENT,
                    confidence=0.9,
                    params=params,
                )

        # Check edit patterns
        for pattern in self.EDIT_PATTERNS:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                return ClassifiedIntent(intent=Intent.EDIT_PAPER, confidence=0.85)

        # If message contains "?" it's likely a question
        if "?" in original and len(original.split()) > 3:
            return ClassifiedIntent(intent=Intent.EXPLAIN, confidence=0.7)

        return None

    def _extract_search_query(self, message: str) -> str:
        """Extract the search query from a search request."""
        # Remove common prefixes
        patterns_to_remove = [
            r"^(can you |please |)?(find|search|look for|get)\s+(me\s+)?(\d+\s+)?(papers?|references?|articles?)\s+(about|on|for|regarding)\s+",
            r"^(search|look)\s+(for\s+)?",
        ]
        result = message
        for pattern in patterns_to_remove:
            result = re.sub(pattern, "", result, flags=re.IGNORECASE)
        return result.strip() or message

    def _extract_count(self, message: str) -> int:
        """Extract number of papers requested."""
        match = re.search(r"(\d+)\s*(papers?|references?|articles?)", message, re.IGNORECASE)
        if match:
            return min(int(match.group(1)), 20)  # Cap at 20
        return 5  # Default

    def _extract_content_type(self, message: str) -> str:
        """Extract what type of content to create."""
        msg_lower = message.lower()
        if "literature review" in msg_lower or "lit review" in msg_lower:
            return "literature_review"
        if "summary" in msg_lower or "summarize" in msg_lower:
            return "summary"
        if "outline" in msg_lower:
            return "outline"
        if "introduction" in msg_lower:
            return "introduction"
        if "abstract" in msg_lower:
            return "abstract"
        return "general"

    def _extract_create_params(self, message: str) -> dict:
        """Extract all parameters for create content: theme, length, structure, output."""
        params = {"content_type": self._extract_content_type(message)}
        msg_lower = message.lower()

        # Extract theme/topic using "about X" pattern
        theme_match = re.search(r"\babout\s+([^,\.!?]+)", msg_lower)
        if theme_match:
            theme = theme_match.group(1).strip()
            # Remove trailing words like "in chat" or "as paper"
            theme = re.sub(r"\s+(in\s+chat|as\s+paper|write|create).*$", "", theme)
            if theme:
                params["theme"] = theme

        # Extract length
        if re.search(r"\b(brief|short|2[- ]?page|concise)\b", msg_lower):
            params["length"] = "brief"
        elif re.search(r"\b(comprehensive|long|detailed|5\+?[- ]?page|in[- ]?depth)\b", msg_lower):
            params["length"] = "comprehensive"

        # Extract structure
        if "thematic" in msg_lower:
            params["structure"] = "thematic"
        elif "chronological" in msg_lower:
            params["structure"] = "chronological"
        elif "methodological" in msg_lower:
            params["structure"] = "methodological"

        # Extract output format
        if re.search(r"\b(in\s+chat|write\s+in\s+chat)\b", msg_lower):
            params["output"] = "chat"
        elif re.search(r"\b(as\s+paper|create\s+(as\s+)?paper)\b", msg_lower):
            params["output"] = "paper"

        return params
