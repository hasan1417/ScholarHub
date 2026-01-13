"""
Intent Classifier - Determines what the user wants BEFORE involving the main LLM.

Uses keyword-based detection for robustness (handles typos and variations).
This runs BEFORE the state machine to provide input for state transitions.
"""

from __future__ import annotations
import re
import logging
from typing import Optional, List, Dict, TYPE_CHECKING

from app.services.discussion_ai.state_machine import UserIntent, ClassifiedIntent, ConversationState

if TYPE_CHECKING:
    from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


def _fuzzy_contains(text: str, words: list, threshold: int = 1) -> bool:
    """Check if text contains any of the words with fuzzy matching (handles typos)."""
    text_lower = text.lower()
    text_words = text_lower.split()

    for target in words:
        # Exact match first
        if target in text_lower:
            return True
        # Fuzzy match for each word in text
        for word in text_words:
            if len(word) >= 3 and len(target) >= 3:
                # Simple edit distance check (allow 1 char difference for words >= 4 chars)
                if abs(len(word) - len(target)) <= threshold:
                    matches = sum(c1 == c2 for c1, c2 in zip(word, target))
                    if matches >= len(target) - threshold:
                        return True
    return False


class IntentClassifier:
    """
    Robust intent classification using keyword detection.

    Key principle: Use KEYWORDS not rigid patterns.
    - "topics" keyword → likely ambiguous (papers vs subtopics?)
    - "papers" or "references" keyword → clear search intent
    - Search verbs (find, search, look, get) → search context
    """

    # Keywords that indicate CLEAR paper search
    PAPER_KEYWORDS = ["papers", "paper", "references", "reference", "articles", "article", "publications"]

    # Keywords that indicate AMBIGUOUS request (topics vs papers?)
    # These words are ambiguous - could mean "list of subtopics" OR "papers about X"
    AMBIGUOUS_KEYWORDS = [
        "topics", "topic",
        "subjects", "subject",
        "themes", "theme",
        "areas", "area",
        "fields", "field",
        "directions", "direction",
        "categories", "category",
        "domains", "domain",
        "aspects", "aspect",
        "concepts", "concept",
        "ideas", "idea",
        "things", "stuff",
        "information", "info",
    ]

    # Keywords that indicate search intent (with fuzzy matching for typos)
    SEARCH_VERBS = ["find", "search", "look", "get", "discover", "fetch", "retrieve"]

    # Keywords that reference previous conversation content
    CONTEXT_REFERENCE_KEYWORDS = [
        "above", "these", "those", "the topics", "the subjects",
        "previous", "mentioned", "discussed", "listed",
        "each topic", "each subject", "each one", "for each",  # Common patterns
        "the ones", "the list", "them", "they",  # Reference to prior content
    ]

    # Simple chat patterns
    SIMPLE_PATTERNS = {
        "hi", "hey", "hello", "thanks", "thank you", "ok", "okay",
        "bye", "goodbye", "yes", "no", "sure", "great", "cool",
    }

    # Patterns that reference existing papers/results
    REFERENCE_PATTERNS = [
        r"(?:these|the|those)\s+(?:\d+\s+)?papers?",
        r"(?:these|the|those)\s+(?:\d+\s+)?references?",
        r"(?:these|the|those)\s+results?",
        r"use\s+(?:them|these|the\s+papers?)",
        r"(?:above|previous)\s+(?:papers?|references?)",
    ]

    # Project reference patterns
    PROJECT_PATTERNS = [
        r"(?:the|my|this)\s+project",
        r"project\s+(?:goals?|scope|title|description)",
        r"(?:about|for)\s+(?:the|my)\s+project",
    ]

    # Library reference patterns
    LIBRARY_PATTERNS = [
        r"(?:my|the)\s+library",
        r"saved\s+(?:papers?|references?)",
        r"(?:my|the)\s+collection",
    ]

    def __init__(self, ai_service: Optional["AIService"] = None):
        self.ai_service = ai_service
        # Compile patterns for context detection
        self._reference_re = [re.compile(p, re.IGNORECASE) for p in self.REFERENCE_PATTERNS]
        self._project_re = [re.compile(p, re.IGNORECASE) for p in self.PROJECT_PATTERNS]
        self._library_re = [re.compile(p, re.IGNORECASE) for p in self.LIBRARY_PATTERNS]

    def classify(
        self,
        message: str,
        previous_state: ConversationState,
        has_search_results: bool = False,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> ClassifiedIntent:
        """
        Classify user intent using robust keyword detection.

        Uses keywords (not rigid patterns) to handle typos and variations.

        Args:
            conversation_history: Previous messages for extracting context when
                                  user references "above topics", etc.
        """
        msg_lower = message.lower().strip()
        msg_stripped = msg_lower.strip(".,!?")

        # Check context needs
        needs_project = self._check_project_reference(message)
        needs_search = self._check_search_reference(message) or (
            has_search_results and self._implies_existing_papers(message)
        )
        needs_library = self._check_library_reference(message)

        # RULE 1: If we asked a clarification and user is responding
        if previous_state.clarification_asked:
            if len(message.split()) <= 5:
                logger.info("Short answer after clarification -> CLARIFY_RESPONSE")
                return ClassifiedIntent(
                    intent=UserIntent.CLARIFY_RESPONSE,
                    confidence=0.95,
                    needs_project_context=needs_project,
                    needs_search_results=needs_search or has_search_results,
                    needs_library=needs_library,
                    clarification_answer=message,
                )

        # RULE 2: Simple chat (greetings, acknowledgments)
        if msg_stripped in self.SIMPLE_PATTERNS:
            logger.info("Simple pattern match -> SIMPLE_CHAT")
            return ClassifiedIntent(
                intent=UserIntent.SIMPLE_CHAT,
                confidence=1.0,
                needs_project_context=False,
                needs_search_results=False,
                needs_library=False,
            )

        # RULE 2.5: Context-based search (find papers/references for "above topics", "these subjects")
        # This is DETERMINISTIC - we extract keywords from conversation, not rely on LLM
        has_context_reference = any(kw in msg_lower for kw in self.CONTEXT_REFERENCE_KEYWORDS)
        has_paper_or_ref_request = any(kw in msg_lower for kw in self.PAPER_KEYWORDS)

        print(f"[CLASSIFIER] Context check:")
        print(f"  - has_context_reference: {has_context_reference} (keywords: {self.CONTEXT_REFERENCE_KEYWORDS})")
        print(f"  - has_paper_or_ref_request: {has_paper_or_ref_request}")
        print(f"  - has_history: {conversation_history is not None} (len={len(conversation_history) if conversation_history else 0})")

        if has_context_reference and has_paper_or_ref_request and conversation_history:
            print("[CLASSIFIER] Context reference + paper request detected -> extracting from conversation")
            extracted_query = self._extract_keywords_from_history(conversation_history)
            print(f"[CLASSIFIER] Extracted query: {extracted_query}")
            if extracted_query:
                count_match = re.search(r"(\d+)\s+(?:papers?|references?)", message, re.IGNORECASE)
                count = int(count_match.group(1)) if count_match else 5
                print(f"[CLASSIFIER] Returning SEARCH_FROM_CONTEXT with count={count}")
                return ClassifiedIntent(
                    intent=UserIntent.SEARCH_FROM_CONTEXT,
                    confidence=0.95,
                    needs_project_context=False,
                    needs_search_results=False,
                    needs_library=False,
                    extracted_count=count,
                    extracted_context_query=extracted_query,
                )

        # KEYWORD-BASED DETECTION (robust to typos)
        has_search_verb = _fuzzy_contains(message, self.SEARCH_VERBS)
        has_paper_keyword = any(kw in msg_lower for kw in self.PAPER_KEYWORDS)
        has_ambiguous_keyword = any(kw in msg_lower for kw in self.AMBIGUOUS_KEYWORDS)

        logger.info(
            "Keyword detection: search_verb=%s, paper_kw=%s, ambiguous_kw=%s",
            has_search_verb, has_paper_keyword, has_ambiguous_keyword
        )

        # RULE 3: Ambiguous request - has search intent + ambiguous keywords (topics, information)
        # but NOT clear paper keywords
        if has_ambiguous_keyword and not has_paper_keyword:
            logger.info("Ambiguous keywords detected -> AMBIGUOUS_REQUEST")
            topic, count = self._extract_search_params(message)
            return ClassifiedIntent(
                intent=UserIntent.AMBIGUOUS_REQUEST,
                confidence=0.9,
                needs_project_context=needs_project,
                needs_search_results=needs_search,
                needs_library=needs_library,
                extracted_topic=topic,
                extracted_count=count,
            )

        # RULE 4: Clear search request - has search verb + paper keywords
        if has_search_verb and has_paper_keyword:
            logger.info("Clear paper search detected -> SEARCH_PAPERS")
            topic, count = self._extract_search_params(message)
            return ClassifiedIntent(
                intent=UserIntent.SEARCH_PAPERS,
                confidence=0.95,
                needs_project_context=needs_project,
                needs_search_results=False,
                needs_library=False,
                extracted_topic=topic,
                extracted_count=count,
            )

        # RULE 5: Search verb without specific keywords - might be search, let AI decide
        if has_search_verb:
            logger.info("Search verb detected without clear keywords -> SEARCH_PAPERS (let AI decide)")
            topic, count = self._extract_search_params(message)
            return ClassifiedIntent(
                intent=UserIntent.SEARCH_PAPERS,
                confidence=0.7,
                needs_project_context=needs_project,
                needs_search_results=needs_search,
                needs_library=needs_library,
                extracted_topic=topic,
                extracted_count=count,
            )

        # RULE 6: Content creation requests
        if self._is_content_request(message):
            logger.info("Content creation request -> CREATE_CONTENT")
            return ClassifiedIntent(
                intent=UserIntent.CREATE_CONTENT,
                confidence=0.85,
                needs_project_context=needs_project,
                needs_search_results=needs_search or has_search_results,
                needs_library=needs_library,
            )

        # RULE 7: If message contains paper/reference keywords, assume search intent
        # This is MORE PERMISSIVE - let LLM decide with tools available
        if has_paper_keyword:
            logger.info("Paper keyword detected -> SEARCH_PAPERS (let LLM decide with tools)")
            topic, count = self._extract_search_params(message)
            return ClassifiedIntent(
                intent=UserIntent.SEARCH_PAPERS,
                confidence=0.7,
                needs_project_context=needs_project,
                needs_search_results=needs_search,
                needs_library=needs_library,
                extracted_topic=topic,
                extracted_count=count,
            )

        # RULE 8: Question - but still give LLM tools access
        if self._is_question(message):
            logger.info("Question detected -> ASK_QUESTION")
            return ClassifiedIntent(
                intent=UserIntent.ASK_QUESTION,
                confidence=0.8,
                needs_project_context=needs_project,
                needs_search_results=needs_search,
                needs_library=needs_library,
            )

        # Default: Treat as general request - LLM will figure it out with tools
        logger.info("No specific pattern -> ASK_QUESTION (default, LLM will decide)")
        return ClassifiedIntent(
            intent=UserIntent.ASK_QUESTION,
            confidence=0.5,
            needs_project_context=needs_project,
            needs_search_results=needs_search,
            needs_library=needs_library,
        )

    def _matches_any(self, text: str, patterns: list) -> bool:
        """Check if text matches any of the compiled patterns."""
        return any(p.search(text) for p in patterns)

    def _check_project_reference(self, message: str) -> bool:
        """Check if message explicitly references the project."""
        return self._matches_any(message, self._project_re)

    def _check_search_reference(self, message: str) -> bool:
        """Check if message references search results."""
        return self._matches_any(message, self._reference_re)

    def _check_library_reference(self, message: str) -> bool:
        """Check if message references user's library."""
        return self._matches_any(message, self._library_re)

    def _implies_existing_papers(self, message: str) -> bool:
        """Check if message implies using existing papers."""
        triggers = ["use", "with", "using", "from", "these", "those", "them"]
        msg_lower = message.lower()
        return any(t in msg_lower for t in triggers)

    def _extract_search_params(self, message: str) -> tuple[Optional[str], Optional[int]]:
        """Extract topic and count from search request."""
        # Extract count
        count_match = re.search(r"(\d+)\s+(?:papers?|references?|topics?)", message, re.IGNORECASE)
        count = int(count_match.group(1)) if count_match else None

        # Extract topic (everything after "about", "on", "for")
        topic_match = re.search(r"(?:about|on|for|related\s+to)\s+(.+?)(?:\s*$|\s*\.|\s*\?)", message, re.IGNORECASE)
        topic = topic_match.group(1).strip() if topic_match else None

        return topic, count

    def _is_content_request(self, message: str) -> bool:
        """Check if this is a content creation request."""
        content_triggers = [
            r"(?:create|write|generate|make)\s+(?:a\s+)?(?:literature\s+review|review|summary|paper|report)",
            r"(?:summarize|analyze)\s+(?:these|the|those)",
            r"literature\s+review",
        ]
        return any(re.search(p, message, re.IGNORECASE) for p in content_triggers)

    def _is_question(self, message: str) -> bool:
        """Check if message is a question."""
        question_indicators = [
            message.strip().endswith("?"),
            message.lower().startswith(("what", "how", "why", "when", "where", "who", "which", "can", "could", "would", "is", "are", "do", "does")),
        ]
        return any(question_indicators)

    def _extract_keywords_from_history(
        self,
        conversation_history: List[Dict[str, str]],
    ) -> Optional[str]:
        """
        Extract keywords from conversation history for context-based search.

        Looks at the last substantial assistant message and extracts key terms.
        This is DETERMINISTIC - no LLM involved.
        """
        print(f"[EXTRACT] Looking for keywords in {len(conversation_history)} messages")
        # Find the last substantial assistant message
        for i, msg in enumerate(reversed(conversation_history)):
            role = msg.get("role", "")
            content_len = len(msg.get("content", ""))
            print(f"  [{len(conversation_history)-i-1}] role={role}, len={content_len}")

            if role == "assistant" and content_len > 100:
                content = msg["content"]
                print(f"[EXTRACT] Found substantial assistant message ({content_len} chars)")

                # Extract bold/header text (often contains key topics)
                # Look for **bold** or numbered items
                keywords = []

                # Extract bold text
                bold_matches = re.findall(r"\*\*([^*]+)\*\*", content)
                print(f"[EXTRACT] Bold matches: {bold_matches[:5]}")
                keywords.extend(bold_matches[:5])  # Take first 5

                # Extract numbered list items (1. Topic, 2. Topic, etc.)
                numbered_matches = re.findall(r"^\d+[.)]\s*([^\n]+)", content, re.MULTILINE)
                print(f"[EXTRACT] Numbered matches: {numbered_matches[:5]}")
                for match in numbered_matches[:5]:
                    # Clean up the match - take just the main phrase
                    cleaned = re.sub(r"\*\*|\*|^\s+|\s+$", "", match)
                    if len(cleaned) > 3 and len(cleaned) < 100:
                        keywords.append(cleaned.split("(")[0].strip())  # Remove parenthetical

                print(f"[EXTRACT] All keywords: {keywords}")

                # If we have keywords, build a query
                if keywords:
                    # Take unique keywords, limit to 5
                    unique_keywords = []
                    seen = set()
                    for kw in keywords:
                        kw_lower = kw.lower().strip()
                        if kw_lower not in seen and len(kw_lower) > 3:
                            seen.add(kw_lower)
                            unique_keywords.append(kw.strip())
                        if len(unique_keywords) >= 3:
                            break

                    if unique_keywords:
                        # Build a search query from the keywords
                        query = " ".join(unique_keywords)
                        print(f"[EXTRACT] Final query: {query}")
                        return query

        print("[EXTRACT] No substantial assistant message found")
        return None
