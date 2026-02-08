from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, List, Literal, Optional


IntentType = Literal["direct_search", "analysis", "clarify", "project_update", "general"]

# Words with no research-topic content — used to detect queries like
# "papers about my project" that need context resolution instead of literal search.
_LOW_INFO_WORDS = frozenset({
    # request verbs
    "find", "search", "get", "look", "show", "give", "retrieve", "fetch",
    # determiners / pronouns
    "me", "my", "our", "the", "this", "that", "a", "an", "some", "any",
    "it", "them", "these", "those", "its", "their",
    # paper-like nouns
    "papers", "paper", "articles", "article", "studies", "study",
    "references", "reference", "literature", "results",
    # generic context nouns
    "project", "research", "topic", "area", "field", "work", "subject",
    # prepositions / conjunctions
    "about", "on", "for", "of", "in", "with", "from", "to", "and", "or",
    # relative/quantity modifiers
    "more", "another", "additional", "extra", "other", "few", "several",
    # recency (handled separately by year extraction)
    "recent", "new", "latest", "current",
})


@dataclass(frozen=True)
class ContextResolution:
    """Deterministic context resolution outcome for the current user turn."""

    resolved_topic: str
    source: Literal["explicit_user_topic", "memory_topic_hint", "last_search_topic", "project_context", "fallback_default"]
    cleaned_user_text: str
    is_deictic: bool
    is_relative_only: bool


@dataclass(frozen=True)
class ActionPlan:
    """Tool-agnostic execution guardrails for a user turn."""

    primary_tool: Optional[str] = None
    force_tool: Optional[str] = None
    blocked_tools: tuple[str, ...] = ()
    reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchPolicy:
    """Deterministic defaults and constraints for paper search."""

    query: str
    count: int = 5
    open_access_only: bool = False
    year_from: Optional[int] = None
    year_to: Optional[int] = None


@dataclass(frozen=True)
class PolicyDecision:
    """Deterministic policy decision produced before model/tool execution."""

    intent: IntentType
    force_tool: Optional[str] = None
    search: Optional[SearchPolicy] = None
    reasons: List[str] = field(default_factory=list)
    action_plan: Optional[ActionPlan] = None

    def should_force_tool(self, tool_name: str) -> bool:
        forced_tool = self.force_tool
        if self.action_plan and self.action_plan.force_tool:
            forced_tool = self.action_plan.force_tool
        return forced_tool == tool_name and self.search is not None


class DiscussionPolicy:
    """Policy-first control logic for deterministic routing and defaults."""

    _LIBRARY_MARKERS = ("my library", "saved papers", "in the library", "project library")
    _DEICTIC_MARKERS = ("this topic", "that topic", "this area", "that area", "this field")
    # Detects cleaned queries that have no real topic — only relative modifiers
    # and paper-like nouns. Examples: "another 3 papers", "more papers", "a few more".
    _RELATIVE_ONLY_RE = re.compile(
        r"^(?:for\s+)?(?:another|more|additional|extra|other|a\s+few(?:\s+more)?)"
        r"(?:\s+\d+)?(?:\s+(?:papers?|articles?|references?|studies?|results?))?\s*$",
        re.IGNORECASE,
    )
    _PROJECT_UPDATE_PATTERN = re.compile(
        r"\b(?:project|keywords?|objectives?|scope|description)\b.*\b(?:update|change|set|add|remove|edit|modify)\b|"
        r"\b(?:update|change|set|add|remove|edit|modify)\b.*\b(?:project|keywords?|objectives?|scope|description)\b",
        re.IGNORECASE,
    )
    _DIRECT_SEARCH_PATTERNS = (
        r"^(?:can|could|would|will)\s+you\s+(?:find|search|look\s*up|get|retrieve)\b",
        r"^(?:please\s+)?(?:find|search|look\s*up|get|retrieve)\b",
    )
    _PAPER_TERMS_PATTERN = re.compile(
        r"\b(?:paper|papers|literature|article|articles|reference|references|studies|study)\b",
        re.IGNORECASE,
    )

    def build_decision(
        self,
        user_message: str,
        topic_hint: str = "",
        last_search_topic: str = "",
        project_context: str = "",
        search_tool_available: bool = False,
        derive_topic_fn: Optional[Callable[[str], Optional[str]]] = None,
    ) -> PolicyDecision:
        msg = (user_message or "").strip()
        if self.is_direct_paper_search_request(msg):
            resolution = self.resolve_search_context(
                user_message=msg,
                topic_hint=topic_hint,
                last_search_topic=last_search_topic,
                project_context=project_context,
            )
            query = resolution.resolved_topic
            if query and derive_topic_fn:
                derived_topic = derive_topic_fn(query)
                if derived_topic:
                    query = derived_topic

            year_from, year_to = self.extract_year_bounds(msg)
            search = SearchPolicy(
                query=query,
                count=self.extract_requested_paper_count(msg) or 5,
                open_access_only=self.user_requested_open_access(msg),
                year_from=year_from,
                year_to=year_to,
            )
            reasons = ["direct_search_intent"]
            reasons.append(f"topic_source={resolution.source}")
            if search_tool_available:
                reasons.append("search_tool_available")
            if year_from is not None or year_to is not None:
                reasons.append("recency_or_year_filter_requested")
            action_plan = ActionPlan(
                primary_tool="search_papers",
                force_tool="search_papers" if search_tool_available else None,
                reasons=reasons.copy(),
            )
            return PolicyDecision(
                intent="direct_search",
                force_tool="search_papers" if search_tool_available else None,
                search=search,
                reasons=reasons,
                action_plan=action_plan,
            )

        if self.is_project_update_request(msg):
            reasons = ["project_update_intent"]
            return PolicyDecision(
                intent="project_update",
                reasons=reasons,
                action_plan=ActionPlan(
                    primary_tool="update_project_info",
                    blocked_tools=("search_papers", "batch_search_papers", "discover_topics"),
                    reasons=reasons,
                ),
            )

        return PolicyDecision(
            intent="general",
            reasons=["default_general"],
            action_plan=ActionPlan(reasons=["default_general"]),
        )

    @staticmethod
    def user_requested_detailed_response(user_message: str) -> bool:
        """Return True when user explicitly asks for long-form, detailed output."""
        if not user_message:
            return False
        msg = user_message.lower()
        detail_markers = (
            "in detail",
            "detailed",
            "full detail",
            "comprehensive",
            "full protocol",
            "step by step",
            "deep dive",
            "thorough",
            "long version",
            "expanded version",
        )
        return any(marker in msg for marker in detail_markers)

    def is_direct_paper_search_request(self, user_message: str) -> bool:
        if not user_message:
            return False

        msg = user_message.strip().lower()
        if not msg:
            return False

        if any(marker in msg for marker in self._LIBRARY_MARKERS):
            return False

        starts_with_search_action = any(re.search(pattern, msg) for pattern in self._DIRECT_SEARCH_PATTERNS)
        if not starts_with_search_action:
            return False

        return bool(self._PAPER_TERMS_PATTERN.search(msg))

    @staticmethod
    def is_low_information_query(query: str) -> bool:
        """Return True if query has no substantive research-topic content.

        Examples that ARE low-info: "papers about my project", "more papers",
        "3 papers about this research".
        Examples that are NOT: "climate adaptation policy", "transformer architectures".
        """
        if not query:
            return True
        words = set(re.findall(r"\b[a-zA-Z]+\b", query.lower()))
        substantive = {w for w in words - _LOW_INFO_WORDS if len(w) > 1}
        return len(substantive) == 0

    def is_project_update_request(self, user_message: str) -> bool:
        if not user_message:
            return False
        return bool(self._PROJECT_UPDATE_PATTERN.search(user_message))

    @staticmethod
    def _clean_search_request_text(user_message: str) -> str:
        cleaned_user = re.sub(
            r"^(?:can|could|would|will)\s+you\s+(?:find|search|look\s*up|get|retrieve)\s+(?:me\s+)?",
            "",
            user_message,
            flags=re.IGNORECASE,
        )
        cleaned_user = re.sub(
            r"^(?:please\s+)?(?:find|search|look\s*up|get|retrieve)\s+(?:me\s+)?",
            "",
            cleaned_user,
            flags=re.IGNORECASE,
        )
        cleaned_user = re.sub(r"\s+", " ", cleaned_user).strip(" ?.!")
        return cleaned_user

    def resolve_search_context(
        self,
        user_message: str,
        topic_hint: str = "",
        last_search_topic: str = "",
        project_context: str = "",
    ) -> ContextResolution:
        """Resolve the effective search topic for this turn.

        Priority chain:
        1. Explicit user topic (only if it has substantive content)
        2. Memory topic hint (research_topic / research_question)
        3. Last effective search topic
        4. Project context (keywords / title)
        5. Fallback default
        """
        cleaned_user = self._clean_search_request_text(user_message)
        cleaned_lower = cleaned_user.lower()
        is_deictic = any(marker in cleaned_lower for marker in self._DEICTIC_MARKERS)
        is_relative_only = bool(self._RELATIVE_ONLY_RE.match(cleaned_user))

        # Only use the user's text as-is if it contains real topic content.
        # "climate adaptation policy" → explicit.  "my project" → low-info, fall through.
        if cleaned_user and not is_deictic and not is_relative_only:
            if not self.is_low_information_query(cleaned_user):
                return ContextResolution(
                    resolved_topic=cleaned_user[:300],
                    source="explicit_user_topic",
                    cleaned_user_text=cleaned_user,
                    is_deictic=is_deictic,
                    is_relative_only=is_relative_only,
                )

        if topic_hint:
            return ContextResolution(
                resolved_topic=topic_hint[:300],
                source="memory_topic_hint",
                cleaned_user_text=cleaned_user,
                is_deictic=is_deictic,
                is_relative_only=is_relative_only,
            )

        if last_search_topic:
            return ContextResolution(
                resolved_topic=last_search_topic[:300],
                source="last_search_topic",
                cleaned_user_text=cleaned_user,
                is_deictic=is_deictic,
                is_relative_only=is_relative_only,
            )

        if project_context:
            return ContextResolution(
                resolved_topic=project_context[:300],
                source="project_context",
                cleaned_user_text=cleaned_user,
                is_deictic=is_deictic,
                is_relative_only=is_relative_only,
            )

        fallback = cleaned_user[:300] if cleaned_user else "academic research papers"
        return ContextResolution(
            resolved_topic=fallback,
            source="fallback_default",
            cleaned_user_text=cleaned_user,
            is_deictic=is_deictic,
            is_relative_only=is_relative_only,
        )

    def build_search_query(
        self,
        user_message: str,
        topic_hint: str = "",
        last_search_topic: str = "",
        project_context: str = "",
        derive_topic_fn: Optional[Callable[[str], Optional[str]]] = None,
    ) -> str:
        resolution = self.resolve_search_context(
            user_message=user_message,
            topic_hint=topic_hint,
            last_search_topic=last_search_topic,
            project_context=project_context,
        )
        base_query = resolution.resolved_topic

        if base_query and derive_topic_fn:
            derived_topic = derive_topic_fn(base_query)
            if derived_topic:
                base_query = derived_topic

        query = re.sub(r"\s+", " ", (base_query or "").strip(" ?.!"))
        return query[:300] if query else "academic research papers"

    @staticmethod
    def user_requested_open_access(user_message: str) -> bool:
        if not user_message:
            return False
        msg = user_message.lower()
        markers = (
            "open access",
            "oa only",
            "only oa",
            "pdf available",
            "with pdf",
            "full text only",
            "only papers with pdf",
        )
        return any(marker in msg for marker in markers)

    @staticmethod
    def extract_requested_paper_count(user_message: str) -> Optional[int]:
        if not user_message:
            return None
        msg = user_message.lower()

        # Count must be tied to paper-like nouns to avoid false captures
        # from year/recency phrases (e.g., "last 3 years", "since 2020").
        digit_pattern = re.compile(
            r"\b(\d{1,3})\b(?P<between>(?:\s+\w+){0,4})\s+(?:papers?|references?|articles?|studies?)\b"
        )
        for match in digit_pattern.finditer(msg):
            between = (match.group("between") or "").strip()
            if re.search(r"\byears?\b", between):
                continue
            value = int(match.group(1))
            return max(1, min(value, 50))

        word_to_num = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
        }
        for word, value in word_to_num.items():
            match = re.search(
                rf"\b{word}\b(?P<between>(?:\s+\w+){{0,4}})\s+(?:papers?|references?|articles?|studies?)\b",
                msg,
            )
            if match and not re.search(r"\byears?\b", (match.group("between") or "").strip()):
                return value

        if "few papers" in msg:
            return 3
        if "several papers" in msg:
            return 7
        return None

    @staticmethod
    def extract_year_bounds(user_message: str) -> tuple[Optional[int], Optional[int]]:
        """Extract deterministic year filters from user recency constraints."""
        if not user_message:
            return (None, None)

        msg = user_message.lower()
        current_year = datetime.now(timezone.utc).year

        def clamp(year: int) -> int:
            return max(1900, min(year, current_year))

        # Explicit range: "from 2020 to 2024", "2020-2024", "between 2020 and 2024"
        range_patterns = (
            r"\b(?:from|between)\s+(19\d{2}|20\d{2})\s+(?:to|and|through|until|-)\s+(19\d{2}|20\d{2})\b",
            r"\b(19\d{2}|20\d{2})\s*(?:-|to|through|until)\s*(19\d{2}|20\d{2})\b",
        )
        for pattern in range_patterns:
            match = re.search(pattern, msg)
            if match:
                start = clamp(int(match.group(1)))
                end = clamp(int(match.group(2)))
                if start > end:
                    start, end = end, start
                return (start, end)

        # Since/from single year
        match = re.search(r"\b(?:since|from)\s+(19\d{2}|20\d{2})\b", msg)
        if match:
            return (clamp(int(match.group(1))), current_year)

        # Last/past N years
        match = re.search(r"\b(?:last|past)\s+(\d{1,2})\s+years?\b", msg)
        if match:
            n_years = max(1, min(int(match.group(1)), 30))
            return (current_year - n_years + 1, current_year)

        # Single explicit year if user asks with temporal signal
        single_year_match = re.search(r"\b(19\d{2}|20\d{2})\b", msg)
        if single_year_match and re.search(r"\b(?:in|during|around|published)\b", msg):
            year = clamp(int(single_year_match.group(1)))
            return (year, year)

        # Generic recency intent
        if re.search(r"\b(?:recent|latest|newest|current|up[-\s]?to[-\s]?date)\b", msg):
            return (current_year - 4, current_year)

        return (None, None)
