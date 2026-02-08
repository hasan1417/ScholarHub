from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, List, Literal, Optional


IntentType = Literal["direct_search", "analysis", "clarify", "general"]


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

    def should_force_tool(self, tool_name: str) -> bool:
        return self.force_tool == tool_name and self.search is not None


class DiscussionPolicy:
    """Policy-first control logic for deterministic routing and defaults."""

    _LIBRARY_MARKERS = ("my library", "saved papers", "in the library", "project library")
    _DEICTIC_MARKERS = ("this topic", "that topic", "this area", "that area", "this field")
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
        search_tool_available: bool = False,
        derive_topic_fn: Optional[Callable[[str], Optional[str]]] = None,
    ) -> PolicyDecision:
        msg = (user_message or "").strip()
        if self.is_direct_paper_search_request(msg):
            year_from, year_to = self.extract_year_bounds(msg)
            search = SearchPolicy(
                query=self.build_search_query(msg, topic_hint=topic_hint, derive_topic_fn=derive_topic_fn),
                count=self.extract_requested_paper_count(msg) or 5,
                open_access_only=self.user_requested_open_access(msg),
                year_from=year_from,
                year_to=year_to,
            )
            reasons = ["direct_search_intent"]
            if search_tool_available:
                reasons.append("search_tool_available")
            if year_from is not None or year_to is not None:
                reasons.append("recency_or_year_filter_requested")
            return PolicyDecision(
                intent="direct_search",
                force_tool="search_papers" if search_tool_available else None,
                search=search,
                reasons=reasons,
            )

        return PolicyDecision(intent="general", reasons=["default_general"])

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

    def build_search_query(
        self,
        user_message: str,
        topic_hint: str = "",
        derive_topic_fn: Optional[Callable[[str], Optional[str]]] = None,
    ) -> str:
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

        user_is_deictic = any(marker in cleaned_user.lower() for marker in self._DEICTIC_MARKERS)
        base_query = cleaned_user
        if not base_query or user_is_deictic:
            base_query = topic_hint or cleaned_user

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
