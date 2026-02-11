"""
Memory management mixin for the Discussion AI orchestrator.

Handles AI memory persistence, summarization, fact extraction, research state
tracking, long-term memory, and tool result caching.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from sqlalchemy.orm.attributes import flag_modified

from app.services.discussion_ai.utils import sanitize_for_context

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import ProjectDiscussionChannel
    from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


class MemoryMixin:
    """Mixin providing AI memory management for the orchestrator.

    Expects the composed class to provide:
        - self.ai_service: AIService
        - self.db: Session
        - self.model: str (property)
    """

    # Token budget allocation (approximate)
    MEMORY_TOKEN_BUDGET = {
        "working_memory": 4000,    # Last N messages (token-based, not count-based)
        "session_summary": 1000,   # Compressed older messages
        "research_facts": 500,     # Structured facts
        "key_quotes": 300,         # Important verbatim statements
    }
    # Legacy: message-count based window (deprecated, kept for fallback)
    SLIDING_WINDOW_SIZE = 20  # Number of recent messages to keep in full

    # Token-based context management
    CONVERSATION_HISTORY_TOKEN_BUDGET = 16000  # Max tokens for conversation history

    # Research stages for state tracking
    RESEARCH_STAGES = [
        "exploring",      # Initial exploration, broad questions
        "refining",       # Narrowing down scope, comparing options
        "finding_papers", # Actively searching for literature
        "analyzing",      # Deep dive into specific papers/methods
        "writing",        # Drafting, synthesizing findings
    ]
    CLARIFICATION_DEFAULTS = {
        "scope_geography": "global",
    }

    def _default_clarification_state(self) -> Dict[str, Any]:
        """Default state for clarification loop guardrails."""
        return {
            "pending_slot": None,
            "asked_count": 0,
            "default_value": None,
            "last_prompt": None,
        }

    def _normalize_user_id(self, user_id: Optional[Any]) -> Optional[str]:
        """Normalize user IDs to stable string keys for memory maps."""
        if user_id is None:
            return None
        return str(user_id)

    def _ensure_long_term_schema(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure long-term memory schema exists with backward compatibility."""
        long_term = memory.setdefault("long_term", {})
        long_term.setdefault("user_preferences", [])
        long_term.setdefault("rejected_approaches", [])
        long_term.setdefault("follow_up_items", [])
        long_term.setdefault("user_profiles", {})
        return long_term

    def _get_long_term_bucket(
        self,
        memory: Dict[str, Any],
        user_id: Optional[Any] = None,
        create_user_profile: bool = False,
    ) -> Dict[str, Any]:
        """
        Return mutable long-term memory bucket.

        - If user_id is provided and a user profile exists (or create_user_profile=True),
          return the per-user bucket under channel-level memory.
        - Otherwise return legacy channel-level long_term bucket.
        """
        long_term = self._ensure_long_term_schema(memory)
        user_profiles = long_term.setdefault("user_profiles", {})
        normalized_user_id = self._normalize_user_id(user_id)

        if normalized_user_id:
            profile = user_profiles.get(normalized_user_id)
            if profile is None and create_user_profile:
                profile = {}
                user_profiles[normalized_user_id] = profile
            if isinstance(profile, dict):
                profile.setdefault("user_preferences", [])
                profile.setdefault("rejected_approaches", [])
                profile.setdefault("follow_up_items", [])
                return profile

        return long_term

    def _get_utility_client(self) -> tuple:
        """Return (client, model) for lightweight internal LLM calls.

        Prefers the OpenRouter client (which uses the user's configured key)
        and falls back to the direct OpenAI client if unavailable.
        """
        # OpenRouter client is set on OpenRouterOrchestrator instances
        or_client = getattr(self, "openrouter_client", None)
        if or_client:
            return or_client, "openai/gpt-4o-mini"

        # Fallback: direct OpenAI client from AIService
        client = getattr(self.ai_service, "openai_client", None)
        if client:
            return client, "gpt-4o-mini"

        return None, None

    def _refresh_focused_papers_with_library_data(
        self, focused_papers: List[Dict], project: "Project"
    ) -> List[Dict]:
        """
        Check if any focused papers have been ingested to the library since focusing.
        If so, enrich them with full-text analysis data.

        This handles the common flow:
        1. User searches papers (abstract only)
        2. User focuses on papers
        3. User asks to ingest them
        4. User asks analysis question - should now use full-text data
        """
        from app.models import Reference

        if not focused_papers or not project:
            return focused_papers

        # Get all project references for matching
        try:
            references = self.db.query(Reference).filter(
                Reference.project_id == project.id
            ).limit(1000).all()
        except Exception as e:
            logger.error(f"Failed to fetch references for refresh: {e}")
            return focused_papers

        if not references:
            return focused_papers

        # Build lookup maps for matching
        doi_to_ref = {}
        title_to_ref = {}
        url_to_ref = {}

        for ref in references:
            if ref.doi:
                # Normalize DOI for matching
                doi_normalized = ref.doi.lower().replace("https://doi.org/", "").strip()
                doi_to_ref[doi_normalized] = ref
            if ref.title:
                title_to_ref[ref.title.lower().strip()] = ref
            if ref.url:
                url_to_ref[ref.url] = ref

        refreshed_papers = []
        refreshed_count = 0

        for paper in focused_papers:
            # Skip if already has full text
            if paper.get("has_full_text"):
                refreshed_papers.append(paper)
                continue

            # Try to find matching reference
            matched_ref = None

            # Match by DOI first (most reliable)
            paper_doi = paper.get("doi", "")
            if paper_doi:
                doi_normalized = paper_doi.lower().replace("https://doi.org/", "").strip()
                matched_ref = doi_to_ref.get(doi_normalized)

            # Match by title if no DOI match
            if not matched_ref and paper.get("title"):
                matched_ref = title_to_ref.get(paper["title"].lower().strip())

            # Match by URL if still no match
            if not matched_ref and paper.get("url"):
                matched_ref = url_to_ref.get(paper["url"])

            # If found and has AI analysis, enrich the paper
            if matched_ref and matched_ref.ai_analysis:
                analysis = matched_ref.ai_analysis
                enriched_paper = paper.copy()
                enriched_paper["has_full_text"] = True
                enriched_paper["reference_id"] = str(matched_ref.id)
                enriched_paper["cite_key"] = matched_ref.cite_key

                # Add analysis fields
                if analysis.get("summary"):
                    enriched_paper["summary"] = analysis["summary"]
                if analysis.get("key_findings"):
                    enriched_paper["key_findings"] = analysis["key_findings"]
                if analysis.get("methodology"):
                    enriched_paper["methodology"] = analysis["methodology"]
                if analysis.get("limitations"):
                    enriched_paper["limitations"] = analysis["limitations"]
                if analysis.get("contributions"):
                    enriched_paper["contributions"] = analysis["contributions"]

                refreshed_papers.append(enriched_paper)
                refreshed_count += 1
                logger.info(f"Refreshed focused paper with full-text: {paper.get('title', 'Untitled')[:50]}")
            else:
                refreshed_papers.append(paper)

        if refreshed_count > 0:
            logger.info(f"Refreshed {refreshed_count} focused papers with library full-text data")

        return refreshed_papers

    def _get_ai_memory(self, channel: "ProjectDiscussionChannel") -> Dict[str, Any]:
        """Get AI memory from channel, with defaults."""
        if channel.ai_memory:
            # Ensure new fields exist in old memory structures
            memory = channel.ai_memory
            if "research_state" not in memory:
                memory["research_state"] = {
                    "stage": "exploring",
                    "stage_confidence": 0.5,
                    "stage_history": [],
                }
            if "long_term" not in memory:
                memory["long_term"] = {
                    "user_preferences": [],
                    "rejected_approaches": [],
                    "follow_up_items": [],
                    "user_profiles": {},
                }
            else:
                self._ensure_long_term_schema(memory)
            if "unanswered_questions" not in memory.get("facts", {}):
                memory.setdefault("facts", {})["unanswered_questions"] = []
            if "research_question" not in memory.get("facts", {}):
                memory.setdefault("facts", {})["research_question"] = None
            if "clarification_state" not in memory:
                memory["clarification_state"] = self._default_clarification_state()
            return memory
        return {
            "summary": None,
            "facts": {
                "research_topic": None,
                "research_question": None,  # Formal RQ, e.g. "How does X affect Y?"
                "papers_discussed": [],
                "decisions_made": [],
                "pending_questions": [],
                "unanswered_questions": [],  # Questions AI couldn't answer
                "methodology_notes": [],
            },
            "research_state": {
                "stage": "exploring",           # Current research stage
                "stage_confidence": 0.5,        # How confident we are (0-1)
                "stage_history": [],            # Track stage transitions
            },
            "long_term": {
                "user_preferences": [],         # Learned preferences (e.g., "prefers recent papers")
                "rejected_approaches": [],      # Approaches user explicitly rejected
                "follow_up_items": [],          # User-explicit "save for later" reminders
                "user_profiles": {},            # Per-user preferences inside this channel
            },
            "key_quotes": [],
            "last_summarized_exchange_id": None,
            "tool_cache": {},
            "clarification_state": self._default_clarification_state(),
        }

    @staticmethod
    def _deep_merge_memory(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        """Merge updates into base. Lists are extended (deduped), dicts are recursively merged."""
        merged = {**base}
        for key, value in updates.items():
            if key in merged:
                if isinstance(merged[key], dict) and isinstance(value, dict):
                    merged[key] = MemoryMixin._deep_merge_memory(merged[key], value)
                elif isinstance(merged[key], list) and isinstance(value, list):
                    existing = list(merged[key])
                    for item in value:
                        if item not in existing:
                            existing.append(item)
                    merged[key] = existing
                else:
                    merged[key] = value
            else:
                merged[key] = value
        return merged

    def _save_ai_memory(self, channel: "ProjectDiscussionChannel", memory: Dict[str, Any]) -> None:
        """Save AI memory to channel with row-level locking to prevent concurrent overwrites.

        Uses a dedicated DB session to avoid thread-safety issues.
        The orchestrator's self.db is a request-scoped session created in the
        main async thread, but _save_ai_memory may be called from a thread pool
        (via asyncio.to_thread in the streaming path). SQLAlchemy sessions are
        not thread-safe, so we use our own session here.

        Uses SELECT FOR UPDATE to serialize concurrent writes, then deep-merges
        our changes with the current DB state so no concurrent updates are lost.
        """
        from app.database import SessionLocal
        from app.models import ProjectDiscussionChannel as ChannelModel

        db = SessionLocal()
        try:
            # Lock the row to serialize concurrent memory writes
            fresh_channel = (
                db.query(ChannelModel)
                .filter_by(id=channel.id)
                .with_for_update()
                .first()
            )
            if not fresh_channel:
                logger.error(f"Channel {channel.id} not found when saving AI memory")
                return
            # Merge our changes with the current DB state (another request may have written since we read)
            db_memory = fresh_channel.ai_memory or {}
            if db_memory:
                merged = self._deep_merge_memory(db_memory, memory)
            else:
                merged = memory
            fresh_channel.ai_memory = merged
            flag_modified(fresh_channel, "ai_memory")
            db.commit()
            # Also update the in-memory object so subsequent reads in the same
            # request see the new data without another DB round-trip.
            channel.ai_memory = merged
            logger.info(f"Saved AI memory for channel {channel.id} - focused_papers: {len(merged.get('focused_papers', []))}")
        except Exception as e:
            logger.error(f"Failed to save AI memory: {e}")
            logger.warning(f"[Memory] Memory save failed and was rolled back - conversation context may be lost")
            db.rollback()
        finally:
            db.close()

    def _summarize_old_messages(
        self,
        old_messages: List[Dict[str, str]],
        existing_summary: Optional[str] = None,
    ) -> str:
        """
        Summarize older messages into a compressed summary.
        Uses recursive summarization to incorporate existing summary.
        """
        if not old_messages:
            return existing_summary or ""

        # Format messages for summarization
        message_text = "\n".join([
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:500]}"
            for m in old_messages
        ])

        # Build summarization prompt
        if existing_summary:
            prompt = f"""You are summarizing a research conversation for context retention.

EXISTING SUMMARY (from earlier in the conversation):
{existing_summary}

NEW MESSAGES TO INCORPORATE:
{message_text}

Create an UPDATED summary that:
1. Preserves key information from the existing summary
2. Incorporates new developments from the messages
3. Focuses on: research topics, papers discussed, decisions made, methodology choices
4. Keeps it under 300 words
5. Uses bullet points for clarity

Updated Summary:"""
        else:
            prompt = f"""Summarize this research conversation for context retention.

MESSAGES:
{message_text}

Create a summary that:
1. Captures the main research topic/focus
2. Lists any papers or references discussed
3. Notes key decisions or preferences expressed
4. Highlights methodology choices if any
5. Keeps it under 300 words
6. Uses bullet points for clarity

Summary:"""

        try:
            client, model = self._get_utility_client()
            if not client:
                return existing_summary or ""

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Failed to summarize messages: {e}")
            return existing_summary or ""

    def _extract_research_facts(
        self,
        user_message: str,
        ai_response: str,
        existing_facts: Dict[str, Any],
        recent_messages: Optional[List[str]] = None,
        existing_key_quotes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Extract structured research facts and key quotes from the latest exchange.
        Updates existing facts with new information.
        Returns merged facts dict (includes 'key_quotes' key for caller to extract).
        """
        recent_ctx = ""
        if recent_messages:
            recent_ctx = "RECENT USER MESSAGES (for context):\n"
            for i, msg in enumerate(recent_messages, 1):
                recent_ctx += f"{i}. {msg[:300]}\n"
            recent_ctx += "\n"

        prompt = f"""Analyze this research conversation exchange and extract key facts.

{recent_ctx}CURRENT USER MESSAGE:
{user_message[:1000]}

AI RESPONSE:
{ai_response[:1500]}

EXISTING FACTS:
{json.dumps(existing_facts, indent=2)}

EXISTING KEY QUOTES:
{json.dumps(existing_key_quotes or [], indent=2)}

Extract and UPDATE the facts JSON. Only include new/changed information.
Return a JSON object with these fields (keep existing values if not changed):
- research_topic: Main research topic (string or null). HIGH PRIORITY. If the user states a research question but no separate topic, derive a concise topic from that question (do not leave null in that case).
- research_question: The user's formal research question if stated or implied. Look carefully for questions like "How does X affect Y?" or statements like "I want to investigate X". This is HIGH PRIORITY — extract it if present in current or recent messages. Set to null ONLY if truly not articulated yet. IMPORTANT: If EXISTING FACTS already has a research_question, KEEP IT unless the user explicitly states a NEW research question. Do NOT replace it with a follow-up/procedural question like "What databases should I use?".
- papers_discussed: Array of {{"title": "...", "author": "...", "relevance": "why discussed", "user_reaction": "positive/negative/neutral"}}
- decisions_made: Array of decision strings (append new ones, don't remove old)
- pending_questions: Array of unanswered questions (can remove if answered)
- methodology_notes: Array of methodology-related notes
- key_quotes: Array of important verbatim user statements worth preserving (goals, decisions, preferences, research focus, requirements). Extract the exact user wording, max 200 chars each. Only include genuinely significant statements, not casual remarks.

Return ONLY valid JSON, no explanation:"""

        try:
            client, model = self._get_utility_client()
            if not client:
                return existing_facts

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.2,
                response_format={"type": "json_object"},
            )

            result_text = response.choices[0].message.content.strip()
            new_facts = json.loads(result_text)

            # Merge with existing facts (append arrays, update scalars)
            merged = existing_facts.copy()
            if new_facts.get("research_topic"):
                merged["research_topic"] = new_facts["research_topic"]
            if new_facts.get("research_question"):
                merged["research_question"] = new_facts["research_question"]

            # Fallback: derive topic from available research question when topic is missing.
            if not merged.get("research_topic"):
                topic_source = (
                    new_facts.get("research_question")
                    or merged.get("research_question")
                )
                derived_topic = self._derive_research_topic_from_text(topic_source)
                if derived_topic:
                    merged["research_topic"] = derived_topic

            # Append new papers (avoid duplicates by title)
            existing_titles = {p.get("title", "").lower() for p in merged.get("papers_discussed", [])}
            for paper in new_facts.get("papers_discussed", []):
                if paper.get("title", "").lower() not in existing_titles:
                    merged.setdefault("papers_discussed", []).append(paper)

            # Append new decisions
            existing_decisions = set(merged.get("decisions_made", []))
            for decision in new_facts.get("decisions_made", []):
                if decision not in existing_decisions:
                    merged.setdefault("decisions_made", []).append(decision)

            # Update pending questions (can add or remove)
            merged["pending_questions"] = new_facts.get("pending_questions", merged.get("pending_questions", []))

            # Append methodology notes
            existing_notes = set(merged.get("methodology_notes", []))
            for note in new_facts.get("methodology_notes", []):
                if note not in existing_notes:
                    merged.setdefault("methodology_notes", []).append(note)

            # Merge key quotes from regex + LLM extraction with normalized dedupe.
            llm_quotes = [str(q)[:200] for q in new_facts.get("key_quotes", []) if isinstance(q, str)]
            merged["_key_quotes"] = self._merge_key_quotes(existing_key_quotes or [], llm_quotes, max_quotes=5)

            return merged

        except Exception as e:
            logger.error(f"Failed to extract research facts: {e}")
            logger.warning(f"[Memory] Fact extraction failed, using existing facts (no new information captured)")
            return existing_facts

    def _extract_key_quotes(self, user_message: str, existing_quotes: List[str]) -> List[str]:
        """
        Extract important verbatim user statements to preserve exact wording.
        Keeps the most recent/important quotes (max 5).
        """
        # Simple heuristic: capture definitive statements
        important_patterns = [
            "I want", "I need", "I decided", "I prefer", "I'm focusing on",
            "my goal is", "the main", "specifically", "must have", "don't want",
            "my research question", "I'm investigating", "I'm exploring",
            "I'm studying", "I'd like to",
        ]

        message_lower = user_message.lower()
        new_quotes: List[str] = []
        for pattern in important_patterns:
            pattern_lower = pattern.lower()
            if pattern_lower in message_lower:
                # Extract sentence while preserving punctuation for canonical display.
                sentences = re.split(r'(?<=[.!?])\s+', user_message)
                for sentence in sentences:
                    if pattern_lower in sentence.lower() and len(sentence.strip()) > 20:
                        quote = sentence.strip()[:200]
                        if quote:
                            new_quotes.append(quote)
                        break

        return self._merge_key_quotes(existing_quotes, new_quotes, max_quotes=5)

    def _normalize_quote_key(self, quote: str) -> str:
        """Normalize quote text for dedupe while keeping original display text."""
        normalized = quote.strip().strip('"').strip("'")
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = normalized.lower()
        normalized = normalized.rstrip(" \t\r\n.,!?;:\"'`")
        return normalized

    def _merge_key_quotes(
        self,
        existing_quotes: List[str],
        candidate_quotes: List[str],
        max_quotes: int = 5,
    ) -> List[str]:
        """Merge quotes with normalization-based dedupe and canonical selection."""
        merged: List[str] = []
        norm_to_index: Dict[str, int] = {}

        def consider_quote(raw_quote: Any) -> None:
            if not isinstance(raw_quote, str):
                return

            quote = raw_quote.strip()[:200]
            if not quote:
                return

            key = self._normalize_quote_key(quote)
            if not key:
                return

            existing_idx = norm_to_index.get(key)
            if existing_idx is None:
                merged.append(quote)
                norm_to_index[key] = len(merged) - 1
                return

            # Prefer richer canonical form for same quote (e.g., keeps terminal punctuation).
            existing_quote = merged[existing_idx]
            existing_has_terminal = existing_quote.rstrip().endswith((".", "!", "?"))
            new_has_terminal = quote.rstrip().endswith((".", "!", "?"))
            if (new_has_terminal and not existing_has_terminal) or len(quote) > len(existing_quote):
                merged[existing_idx] = quote

        for raw_quote in existing_quotes or []:
            consider_quote(raw_quote)
        for raw_quote in candidate_quotes or []:
            consider_quote(raw_quote)

        return merged[-max_quotes:]

    def _extract_research_question_direct(
        self, user_message: str, existing_rq: Optional[str] = None,
    ) -> Optional[str]:
        """Extract research question directly from user message using patterns.

        Returns a new RQ only when high-confidence patterns match.  If the user
        already has an RQ (``existing_rq``), only *explicit markers* (Pattern 1)
        can overwrite it — standalone questions are ignored to avoid replacing a
        real RQ with a procedural follow-up like "What databases should I use?".
        """
        msg = user_message.strip()

        # Pattern 1: Explicit RQ markers (always authoritative — can overwrite)
        rq_markers = [
            r"(?:my |the )?research question\s*(?:is|:)\s*[\"']?(.+?)[\"']?\s*$",
            r"(?:my |the )?(?:rq|r\.q\.)\s*(?:is|:)\s*[\"']?(.+?)[\"']?\s*$",
            r"I(?:'m| am) (?:trying to |wanting to )?(?:investigat|explor|study|examin|research)(?:e|ing)\s+(.+?)(?:\.|$)",
            r"(?:I want to |I'd like to )(?:know|understand|find out|investigate)\s+(.+?)(?:\.|$)",
        ]
        for pattern in rq_markers:
            match = re.search(pattern, msg, re.IGNORECASE | re.MULTILINE)
            if match:
                rq = match.group(1).strip().rstrip(".")
                if len(rq) > 15:  # Skip trivially short matches
                    return rq

        # If an RQ already exists, don't overwrite with a standalone question
        if existing_rq:
            return None

        # Pattern 2: Standalone question sentence (only for first RQ detection)
        if len(msg) < 300 and msg.count("?") == 1:
            sentences = re.split(r'(?<=[.!?])\s+', msg)
            for s in sentences:
                s = s.strip()
                if s.endswith("?") and len(s) > 30:
                    s_lower = s.lower()
                    # Exclude non-research questions
                    non_rq_starts = [
                        "can you", "could you", "will you", "would you",
                        "do you", "are you", "is there", "have you",
                        "what databases", "what tools", "what methods",
                        "what software", "how should i", "how do i",
                        "where can i", "where should i",
                    ]
                    if not any(s_lower.startswith(p) for p in non_rq_starts):
                        return s

        return None

    def _derive_research_topic_from_text(self, text: str) -> Optional[str]:
        """Derive a concise research topic phrase from a question or statement."""
        if not text:
            return None

        topic = text.strip().strip('"').strip("'")
        if not topic:
            return None

        # Remove leading boilerplate declarations.
        lead_patterns = [
            r"^(?:my|the)\s+research\s+question\s*(?:is|:)\s*",
            r"^(?:my|the)\s+research\s+topic\s*(?:is|:)\s*",
            r"^i(?:'m| am)\s+focusing\s+on\s+",
            r"^i(?:'ve| have)\s+decided\s+to\s+focus\s+on\s+",
            r"^i(?:'m| am)\s+(?:investigating|exploring|studying|examining)\s+",
        ]
        for pattern in lead_patterns:
            topic = re.sub(pattern, "", topic, flags=re.IGNORECASE).strip()

        # Convert common question templates into topic phrases.
        conversions = [
            (r"^what\s+is\s+the\s+relationship\s+between\s+(.+)$", r"relationship between \1"),
            (r"^to\s+what\s+extent\s+does\s+(.+)$", r"\1"),
            (r"^how\s+do(?:es)?\s+(.+)$", r"\1"),
            (r"^what\s+is\s+the\s+impact\s+of\s+(.+)$", r"impact of \1"),
            (r"^what\s+are\s+the\s+effects\s+of\s+(.+)$", r"effects of \1"),
        ]
        for pattern, replacement in conversions:
            updated = re.sub(pattern, replacement, topic, flags=re.IGNORECASE).strip()
            if updated != topic:
                topic = updated
                break

        topic = topic.rstrip(".?! ").strip()
        topic = re.sub(r"\s+", " ", topic)

        if len(topic) < 12:
            return None
        return topic[:180]

    def _extract_research_topic_direct(self, user_message: str, direct_rq: Optional[str] = None) -> Optional[str]:
        """Extract topic directly from explicit topic statements or derived research question."""
        msg = user_message.strip()

        topic_markers = [
            r"(?:my|the)\s+research\s+topic\s*(?:is|:)\s*[\"']?(.+?)[\"']?\s*$",
            r"(?:my\s+)?topic\s*(?:is|:)\s*[\"']?(.+?)[\"']?\s*$",
            r"i(?:'m| am)\s+focusing\s+on\s+(.+?)(?:\.|$)",
            r"i(?:'ve| have)\s+decided\s+to\s+focus\s+on\s+(.+?)(?:\.|$)",
        ]
        for pattern in topic_markers:
            match = re.search(pattern, msg, re.IGNORECASE | re.MULTILINE)
            if match:
                topic = self._derive_research_topic_from_text(match.group(1))
                if topic:
                    return topic

        return self._derive_research_topic_from_text(direct_rq or "")

    def _extract_clarification_slot(self, ai_response: str) -> Optional[str]:
        """Detect whether the assistant asked a known clarification slot."""
        if not ai_response:
            return None

        response_lower = ai_response.lower()
        if "?" not in response_lower:
            return None

        scope_markers = (
            "global comparison",
            "global or",
            "specific region",
            "specific country",
            "list of cities",
            "named coastal cities",
            "up to 6 cities",
            "answer \"global\"",
        )
        clarification_starters = (
            "do you want",
            "please answer",
            "please name",
            "quick question",
        )
        if any(marker in response_lower for marker in scope_markers) and any(
            starter in response_lower for starter in clarification_starters
        ):
            return "scope_geography"

        return None

    def _user_answered_clarification_slot(self, user_message: str, slot: Optional[str]) -> bool:
        """Best-effort check whether user answered a pending clarification."""
        if not slot or not user_message:
            return False

        msg = user_message.lower().strip()
        if not msg:
            return False

        if slot == "scope_geography":
            answer_markers = (
                "global",
                "region",
                "country",
                "city",
                "cities",
            )
            return any(marker in msg for marker in answer_markers)

        return False

    def _is_actionable_follow_up(self, user_message: str) -> bool:
        """Return True when user asks to continue work rather than clarifying prior slot."""
        msg = (user_message or "").lower().strip()
        if not msg:
            return False

        actionable_markers = (
            "what", "how", "suggest", "recommend", "draft", "plan",
            "criteria", "keywords", "databases", "analysis", "now", "please", "can you",
        )
        return ("?" in msg) or any(marker in msg for marker in actionable_markers)

    def _update_clarification_state_inline(
        self,
        memory: Dict[str, Any],
        user_message: str,
        ai_response: str,
    ) -> None:
        """Track clarification slots to prevent repeated same-slot loops."""
        state = memory.get("clarification_state") or self._default_clarification_state()
        pending_slot = state.get("pending_slot")

        if self._user_answered_clarification_slot(user_message, pending_slot):
            state = self._default_clarification_state()

        asked_slot = self._extract_clarification_slot(ai_response)
        if asked_slot:
            previous_slot = state.get("pending_slot")
            previous_count = int(state.get("asked_count", 0)) if previous_slot == asked_slot else 0
            state["pending_slot"] = asked_slot
            state["asked_count"] = previous_count + 1
            state["default_value"] = self.CLARIFICATION_DEFAULTS.get(asked_slot)
            state["last_prompt"] = ai_response[:220]

        memory["clarification_state"] = state

    def _build_clarification_guardrail(
        self,
        memory: Dict[str, Any],
        user_message: str,
    ) -> Optional[str]:
        """Return deterministic instruction to avoid repeated clarification loops."""
        state = memory.get("clarification_state") or {}
        pending_slot = state.get("pending_slot")
        asked_count = int(state.get("asked_count", 0) or 0)

        if not pending_slot or asked_count < 1:
            return None
        if self._user_answered_clarification_slot(user_message, pending_slot):
            return None
        if not self._is_actionable_follow_up(user_message):
            return None

        if pending_slot == "scope_geography":
            default_value = state.get("default_value") or "global"
            return (
                "You already asked for geographic scope in the previous turn. "
                f"Do NOT ask for geographic scope again. Assume {default_value} scope and continue with the request."
            )

        return None

    def update_memory_after_exchange(
        self,
        channel: "ProjectDiscussionChannel",
        user_message: str,
        ai_response: str,
        conversation_history: List[Dict[str, str]],
        user_id: Optional[Any] = None,
    ) -> Optional[str]:
        """
        Update AI memory after an exchange. Called after each successful response.
        Handles summarization, fact extraction, quote preservation, and pruning.

        Returns: Optional contradiction warning if detected.
        """
        memory = self._get_ai_memory(channel)
        contradiction_warning = None

        # Regex-based key quote extraction as fallback
        # (LLM-based extraction in _extract_research_facts is the primary source)
        memory["key_quotes"] = self._extract_key_quotes(
            user_message,
            memory.get("key_quotes", [])
        )

        # Direct research question extraction (cheap regex, every exchange)
        existing_rq = memory.get("facts", {}).get("research_question")
        direct_rq = self._extract_research_question_direct(user_message, existing_rq=existing_rq)
        if direct_rq:
            memory.setdefault("facts", {})["research_question"] = direct_rq
            logger.info(f"[Memory] Direct RQ extraction: {direct_rq[:80]}")

        # Direct topic extraction fallback (cheap regex + derivation from RQ)
        direct_topic = self._extract_research_topic_direct(user_message, direct_rq=direct_rq)
        if direct_topic:
            facts = memory.setdefault("facts", {})
            explicit_topic_signal = bool(re.search(
                r"(?:research\s+topic\s*(?:is|:)|(?:my\s+)?topic\s*(?:is|:)|focusing\s+on|decided\s+to\s+focus\s+on)",
                user_message,
                re.IGNORECASE,
            ))
            if not facts.get("research_topic") or explicit_topic_signal:
                facts["research_topic"] = direct_topic
                logger.info(f"[Memory] Direct topic extraction: {direct_topic[:80]}")

        # Check if we need to summarize (conversation exceeds token budget)
        # Use token-based check instead of message count
        from app.services.discussion_ai.token_utils import count_messages_tokens, should_summarize

        if should_summarize(conversation_history, self.model):
            # Get messages that exceed budget for summarization
            # Keep the newest messages that fit in budget, summarize the rest
            total_tokens = count_messages_tokens(conversation_history, self.model)
            logger.info(f"[TokenContext] Conversation at {total_tokens} tokens - triggering summarization")

            # Summarize older half of messages
            midpoint = len(conversation_history) // 2
            messages_to_summarize = conversation_history[:midpoint]
            if messages_to_summarize:
                memory["summary"] = self._summarize_old_messages(
                    messages_to_summarize,
                    memory.get("summary"),
                )

        # Incremental summary for short sessions (no token overflow yet)
        # Count exchanges: history user messages + current exchange (not yet in history)
        exchange_count = sum(1 for m in conversation_history if m.get("role") == "user") + 1
        if not memory.get("summary") and exchange_count >= 6:
            memory["summary"] = self._summarize_old_messages(
                conversation_history,
                None,
            )
            logger.info("[Memory] Generated incremental summary for short session")

        # Rate-limited fact extraction (only every N exchanges or when needed)
        if self.should_update_facts(channel, ai_response, user_message=user_message):
            # Check for contradictions before updating facts
            existing_facts = memory.get("facts", {})
            if existing_facts.get("decisions_made") or existing_facts.get("research_topic"):
                contradiction_warning = self.detect_contradictions(user_message, existing_facts)

            # Gather last 3 user messages from conversation history for context
            recent_user_msgs = [
                m["content"] for m in conversation_history
                if m.get("role") == "user"
            ][-3:]

            # Extract research facts (also extracts key quotes)
            extracted = self._extract_research_facts(
                user_message,
                ai_response,
                existing_facts,
                recent_messages=recent_user_msgs,
                existing_key_quotes=memory.get("key_quotes", []),
            )
            # Pull LLM-extracted key quotes out of facts into memory
            llm_quotes = extracted.pop("_key_quotes", None)
            if llm_quotes is not None:
                memory["key_quotes"] = llm_quotes
            memory["facts"] = extracted
            # Reset counter inline (avoid extra save)
            memory["_exchanges_since_fact_update"] = 0
        else:
            # Increment counter inline (avoid extra save)
            memory["_exchanges_since_fact_update"] = memory.get("_exchanges_since_fact_update", 0) + 1

        # Prune stale data periodically (every 10 exchanges)
        exchange_count = memory.get("_exchanges_since_fact_update", 0)
        if exchange_count % 10 == 0:
            self._prune_stale_memory_inline(memory)

        # Phase 3: Update research state and long-term memory (lightweight, do always)
        try:
            self._update_research_state_inline(memory, user_message, ai_response)
            self._track_unanswered_question_inline(memory, user_message, ai_response)
            self._update_long_term_memory_inline(memory, user_message, ai_response, user_id=user_id)
            self._update_clarification_state_inline(memory, user_message, ai_response)
        except Exception as e:
            logger.error(f"Failed to update Phase 3 memory: {e}")

        # Single save for all memory mutations
        self._save_ai_memory(channel, memory)

        return contradiction_warning

    def _build_memory_context_core(
        self,
        memory: Dict[str, Any],
        include_focused_papers: bool = True,
        include_unanswered_questions: bool = True,
        summary_header: str = "## Previous Conversation Summary",
        phase_descriptions: Optional[Dict[str, str]] = None,
        user_id: Optional[Any] = None,
    ) -> str:
        """
        Core memory context builder shared by public and internal methods.
        Builds context from memory dict with configurable sections.

        Args:
            memory: The AI memory dictionary
            include_focused_papers: Whether to include focused papers section
            include_unanswered_questions: Whether to include unanswered questions
            summary_header: Header text for summary section
            phase_descriptions: Custom phase descriptions (defaults to short form)

        Returns:
            Formatted memory context string
        """
        lines = []

        # Default phase descriptions (short form)
        if phase_descriptions is None:
            phase_descriptions = {
                "exploring": "Initial exploration",
                "refining": "Refining scope",
                "finding_papers": "Literature search",
                "analyzing": "Deep analysis",
                "writing": "Writing phase",
            }

        # Tier 2: Session summary
        if memory.get("summary"):
            lines.append(summary_header)
            lines.append(memory["summary"])
            lines.append("")

        # Focused papers section (if enabled)
        if include_focused_papers:
            focused_papers = memory.get("focused_papers", [])
            if focused_papers:
                lines.append("## FOCUSED PAPERS (Use analyze_across_papers for questions about these)")
                for i, p in enumerate(focused_papers, 1):
                    paper_line = f"[{i}] <paper-title>{sanitize_for_context(p.get('title', 'Untitled'), 300)}</paper-title>"
                    if p.get('authors'):
                        authors = p['authors']
                        if isinstance(authors, list):
                            authors = ', '.join(authors[:2]) + ('...' if len(authors) > 2 else '')
                        paper_line += f" - {sanitize_for_context(str(authors), 200)}"
                    if p.get('year'):
                        paper_line += f" ({p['year']})"
                    if p.get('has_full_text'):
                        paper_line += " [Full Text]"
                    else:
                        paper_line += " [Abstract Only]"
                    lines.append(paper_line)
                lines.append("")
                lines.append("**IMPORTANT:** For ANY question about these papers (compare, summarize, discuss), use the analyze_across_papers tool!")
                lines.append("")

        # Tier 3: Research state
        research_state = memory.get("research_state", {})
        stage = research_state.get("stage", "exploring")
        if stage != "exploring" or research_state.get("stage_confidence", 0) > 0.6:
            lines.append(f"**Research Phase:** {phase_descriptions.get(stage, stage)}")

        # Research facts
        facts = memory.get("facts", {})
        if facts.get("research_topic"):
            lines.append(f"**Research Focus:** {facts['research_topic']}")
        if facts.get("research_question"):
            lines.append(f"**Research Question:** {facts['research_question']}")

        if facts.get("papers_discussed"):
            lines.append("**Papers Discussed:**")
            for p in facts["papers_discussed"][-5:]:
                reaction = f" ({p.get('user_reaction', '')})" if p.get('user_reaction') else ""
                lines.append(f"- {p.get('title', 'Unknown')} by {p.get('author', 'Unknown')}{reaction}")

        if facts.get("decisions_made"):
            lines.append("**Decisions Made:**")
            for d in facts["decisions_made"][-5:]:
                lines.append(f"- {d}")

        if facts.get("pending_questions"):
            lines.append("**Open Questions:**")
            for q in facts["pending_questions"]:
                lines.append(f"- {q}")

        # Unanswered questions (if enabled)
        if include_unanswered_questions and facts.get("unanswered_questions"):
            lines.append("**Previously Unanswered Questions:**")
            for q in facts["unanswered_questions"]:
                lines.append(f"- {q}")

        # Tier 3: Long-term memory
        long_term = self._get_long_term_bucket(memory, user_id=user_id, create_user_profile=False)
        if long_term.get("user_preferences"):
            lines.append("**User Preferences:**")
            for p in long_term["user_preferences"][-3:]:
                lines.append(f"- {p}")

        if long_term.get("rejected_approaches"):
            # Note: Different warning text for internal vs public use
            warning = " (avoid suggesting)" if include_focused_papers else ""
            lines.append(f"**Rejected Approaches{warning}:**")
            for r in long_term["rejected_approaches"][-3:]:
                lines.append(f"- {r}")

        if long_term.get("follow_up_items"):
            lines.append("**Deferred Follow-ups:**")
            for item in long_term["follow_up_items"][-5:]:
                lines.append(f"- {item}")

        # Key quotes
        if memory.get("key_quotes"):
            lines.append("**Key User Statements:**")
            for q in memory["key_quotes"]:
                lines.append(f'- "{q}"')

        return "\n".join(lines) if lines else ""

    def _build_memory_context(
        self,
        channel: "ProjectDiscussionChannel",
        user_id: Optional[Any] = None,
    ) -> str:
        """
        Build context string from AI memory for inclusion in system prompt.
        Includes all three memory tiers: working, session, and long-term.
        """
        memory = self._get_ai_memory(channel)

        # DEBUG: Log what's in memory
        logger.info(f"Building memory context. Memory keys: {list(memory.keys())}")
        logger.info(f"Focused papers in memory: {len(memory.get('focused_papers', []))}")

        # Delegate to core builder with full feature set
        return self._build_memory_context_core(
            memory=memory,
            include_focused_papers=True,
            include_unanswered_questions=True,
            summary_header="## Previous Conversation Summary",
            user_id=user_id,
        )

    def cache_tool_result(
        self,
        channel: "ProjectDiscussionChannel",
        tool_name: str,
        result: Dict[str, Any],
    ) -> None:
        """Cache a tool result in AI memory for session reuse."""
        from datetime import datetime, timezone
        memory = self._get_ai_memory(channel)

        # Only cache certain tools that are worth caching
        cacheable_tools = {"get_project_papers", "get_reference_details", "get_project_references"}
        if tool_name not in cacheable_tools:
            return

        tool_cache = memory.get("tool_cache", {})
        tool_cache[tool_name] = {
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        memory["tool_cache"] = tool_cache

        self._save_ai_memory(channel, memory)

    def get_cached_tool_result(
        self,
        channel: "ProjectDiscussionChannel",
        tool_name: str,
        max_age_seconds: int = 300,  # 5 minutes default
    ) -> Optional[Dict[str, Any]]:
        """Get a cached tool result if still valid."""
        from datetime import datetime, timezone
        memory = self._get_ai_memory(channel)

        tool_cache = memory.get("tool_cache", {})
        cached = tool_cache.get(tool_name)

        if not cached:
            return None

        # Check age
        try:
            cached_time = datetime.fromisoformat(cached["timestamp"])
            # Ensure timezone-aware comparison
            if cached_time.tzinfo is None:
                cached_time = cached_time.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - cached_time).total_seconds()
            if age > max_age_seconds:
                return None
            return cached["result"]
        except (KeyError, ValueError, TypeError) as e:
            logger.debug(f"Tool cache lookup failed for {tool_name}: {e}")
            return None

    def prune_stale_memory(
        self,
        channel: "ProjectDiscussionChannel",
        cache_max_age_seconds: int = 600,  # 10 minutes
        max_papers: int = 10,
        max_decisions: int = 10,
        max_methodology_notes: int = 8,
    ) -> None:
        """
        Prune stale data from AI memory to prevent unbounded growth.
        Called periodically to clean up old cache entries and limit array sizes.
        """
        from datetime import datetime, timezone
        memory = self._get_ai_memory(channel)
        modified = False

        # Prune stale tool cache entries
        tool_cache = memory.get("tool_cache", {})
        stale_keys = []
        for tool_name, cached in tool_cache.items():
            try:
                cached_time = datetime.fromisoformat(cached.get("timestamp", ""))
                if cached_time.tzinfo is None:
                    cached_time = cached_time.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - cached_time).total_seconds()
                if age > cache_max_age_seconds:
                    stale_keys.append(tool_name)
            except (KeyError, ValueError, TypeError):
                stale_keys.append(tool_name)

        for key in stale_keys:
            del tool_cache[key]
            modified = True

        if tool_cache != memory.get("tool_cache", {}):
            memory["tool_cache"] = tool_cache

        # Limit papers_discussed to most recent
        facts = memory.get("facts", {})
        if len(facts.get("papers_discussed", [])) > max_papers:
            facts["papers_discussed"] = facts["papers_discussed"][-max_papers:]
            modified = True

        # Limit decisions_made
        if len(facts.get("decisions_made", [])) > max_decisions:
            facts["decisions_made"] = facts["decisions_made"][-max_decisions:]
            modified = True

        # Limit methodology_notes
        if len(facts.get("methodology_notes", [])) > max_methodology_notes:
            facts["methodology_notes"] = facts["methodology_notes"][-max_methodology_notes:]
            modified = True

        if modified:
            memory["facts"] = facts
            self._save_ai_memory(channel, memory)

    def _prune_stale_memory_inline(
        self,
        memory: Dict[str, Any],
        cache_max_age_seconds: int = 600,
        max_papers: int = 10,
        max_decisions: int = 10,
        max_methodology_notes: int = 8,
        max_focused_papers: int = 20,
    ) -> None:
        """Prune stale data from memory dict in-place (no DB read/save)."""
        from datetime import datetime, timezone

        tool_cache = memory.get("tool_cache", {})
        stale_keys = []
        for tool_name, cached in tool_cache.items():
            try:
                cached_time = datetime.fromisoformat(cached.get("timestamp", ""))
                if cached_time.tzinfo is None:
                    cached_time = cached_time.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - cached_time).total_seconds()
                if age > cache_max_age_seconds:
                    stale_keys.append(tool_name)
            except (KeyError, ValueError, TypeError):
                stale_keys.append(tool_name)

        for key in stale_keys:
            del tool_cache[key]
        memory["tool_cache"] = tool_cache

        facts = memory.get("facts", {})
        if len(facts.get("papers_discussed", [])) > max_papers:
            facts["papers_discussed"] = facts["papers_discussed"][-max_papers:]
        if len(facts.get("decisions_made", [])) > max_decisions:
            facts["decisions_made"] = facts["decisions_made"][-max_decisions:]
        if len(facts.get("methodology_notes", [])) > max_methodology_notes:
            facts["methodology_notes"] = facts["methodology_notes"][-max_methodology_notes:]
        memory["facts"] = facts

        # Cap focused_papers to prevent unbounded context growth
        focused = memory.get("focused_papers", [])
        if len(focused) > max_focused_papers:
            memory["focused_papers"] = focused[-max_focused_papers:]

    def _update_research_state_inline(
        self,
        memory: Dict[str, Any],
        user_message: str,
        ai_response: str,
    ) -> None:
        """Update research state in memory dict in-place (no DB read/save)."""
        from datetime import datetime, timezone

        research_state = memory.get("research_state", {
            "stage": "exploring",
            "stage_confidence": 0.5,
            "stage_history": [],
        })
        current_stage = research_state.get("stage", "exploring")
        new_stage, confidence = self.detect_research_stage(
            user_message, ai_response, current_stage
        )
        if new_stage != current_stage:
            research_state.setdefault("stage_history", []).append({
                "from": current_stage,
                "to": new_stage,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "confidence": confidence,
            })
            research_state["stage_history"] = research_state["stage_history"][-10:]
        research_state["stage"] = new_stage
        research_state["stage_confidence"] = confidence
        memory["research_state"] = research_state

    def _track_unanswered_question_inline(
        self,
        memory: Dict[str, Any],
        user_message: str,
        ai_response: str,
    ) -> None:
        """Track unanswered questions in memory dict in-place (no DB read/save)."""
        msg = user_message.strip()

        # Must contain a question mark and be substantial
        if "?" not in msg or len(msg) < 30:
            return

        # Explicit RQ declarations are facts to store, not unanswered questions.
        if re.search(r"(?:my|the)?\s*research\s+question\s*(?:is|:)", msg, re.IGNORECASE):
            return

        # Check if AI gave a substantive answer
        response_lower = ai_response.lower()
        answered_indicators = [
            "here's", "here is", "i found", "the answer", "based on",
            "according to", "the results show", "this means", "in summary",
            "the key finding", "research shows",
        ]
        if any(phrase in response_lower for phrase in answered_indicators):
            return

        # Extract the actual question sentence (the one with ?)
        sentences = re.split(r'(?<=[.!?])\s+', msg)
        question_sentence = None
        for s in sentences:
            if "?" in s and len(s.strip()) > 20:
                question_sentence = s.strip()
                break

        if not question_sentence:
            return

        # Exclude non-questions (declarations that happen to contain ?)
        q_lower = question_sentence.lower()
        declarative_starts = [
            "i know", "i think", "i believe", "i want", "i need",
            "what i want", "what i need", "what i'm", "my research question is",
            "can you", "could you", "will you", "would you",
            "do you", "are you", "is there", "have you",
        ]
        if any(q_lower.startswith(d) for d in declarative_starts):
            return

        facts = memory.get("facts", {})
        unanswered = facts.get("unanswered_questions", [])
        q = question_sentence[:200]
        if q not in unanswered:
            unanswered.append(q)
            facts["unanswered_questions"] = unanswered[-5:]
            memory["facts"] = facts

    def _update_long_term_memory_inline(
        self,
        memory: Dict[str, Any],
        user_message: str,
        ai_response: str,
        user_id: Optional[Any] = None,
    ) -> None:
        """Update long-term memory in memory dict in-place (no DB read/save)."""
        long_term = self._get_long_term_bucket(
            memory,
            user_id=user_id,
            create_user_profile=user_id is not None,
        )
        message_lower = user_message.lower()

        preference_patterns = [
            "i prefer", "i like", "i want", "let's use", "we should use",
            "i'd rather", "my preference is",
        ]
        for pattern in preference_patterns:
            if pattern in message_lower:
                idx = message_lower.find(pattern)
                end_idx = message_lower.find(".", idx)
                if end_idx == -1:
                    end_idx = min(idx + 100, len(user_message))
                pref = user_message[idx:end_idx].strip()
                if pref and pref not in long_term.get("user_preferences", []):
                    long_term.setdefault("user_preferences", []).append(pref)
                    long_term["user_preferences"] = long_term["user_preferences"][-10:]
                break

        rejection_patterns = [
            "i don't want", "not interested in", "avoid", "don't like",
            "rejected", "ruled out", "won't work", "not suitable",
        ]
        for pattern in rejection_patterns:
            if pattern in message_lower:
                idx = message_lower.find(pattern)
                end_idx = message_lower.find(".", idx)
                if end_idx == -1:
                    end_idx = min(idx + 100, len(user_message))
                rejection = user_message[idx:end_idx].strip()
                if rejection and rejection not in long_term.get("rejected_approaches", []):
                    long_term.setdefault("rejected_approaches", []).append(rejection)
                    long_term["rejected_approaches"] = long_term["rejected_approaches"][-10:]
                break

        # Explicit "save this for later" intent belongs in deferred follow-ups,
        # not in unanswered_questions.
        deferred_item = self._extract_deferred_follow_up_item(user_message)
        if deferred_item:
            existing = {x.lower() for x in long_term.get("follow_up_items", [])}
            if deferred_item.lower() not in existing:
                long_term.setdefault("follow_up_items", []).append(deferred_item)
                long_term["follow_up_items"] = long_term["follow_up_items"][-10:]

        # Bucket is a reference into memory; schema helper keeps container initialized.
        self._ensure_long_term_schema(memory)

    def _extract_deferred_follow_up_item(self, user_message: str) -> Optional[str]:
        """Extract explicit "revisit later" intent as a follow-up item."""
        msg = user_message.strip()
        if not msg:
            return None

        if not re.search(
            r"\b(?:unanswered question|for later|remind me|come back to|revisit)\b",
            msg,
            re.IGNORECASE,
        ):
            return None

        sentences = re.split(r'(?<=[.!?])\s+', msg)
        for sentence in sentences:
            candidate = sentence.strip()
            if "?" in candidate and len(candidate) > 20:
                return candidate[:220]

        return msg[:220]

    def detect_contradictions(
        self,
        user_message: str,
        existing_facts: Dict[str, Any],
    ) -> Optional[str]:
        """
        Detect if new user statement contradicts existing facts.
        Returns a warning message if contradiction detected, None otherwise.
        Uses LLM to analyze semantic contradictions.
        """
        # Only check if we have substantial existing facts
        decisions = existing_facts.get("decisions_made", [])
        topic = existing_facts.get("research_topic")

        if not decisions and not topic:
            return None

        # Build context of existing facts
        facts_summary = []
        if topic:
            facts_summary.append(f"Research topic: {topic}")
        if decisions:
            facts_summary.append(f"Decisions made: {', '.join(decisions[-5:])}")

        prompt = f"""Analyze if the new user statement contradicts any established facts.

ESTABLISHED FACTS:
{chr(10).join(facts_summary)}

NEW USER STATEMENT:
{user_message[:500]}

Does the new statement contradict any established fact? If yes, briefly explain the contradiction.
If no contradiction, respond with exactly: NO_CONTRADICTION

Response:"""

        try:
            client, model = self._get_utility_client()
            if not client:
                return None

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.1,
            )
            result = response.choices[0].message.content.strip()

            result_upper = result.upper()
            # Accept any variation: "NO_CONTRADICTION", "NO CONTRADICTIONS", "NO CONTRADICTION FOUND", etc.
            if "NO_CONTRADICTION" in result_upper or "NO CONTRADICTION" in result_upper:
                return None

            return result
        except Exception as e:
            logger.error(f"Contradiction detection failed: {e}")
            return None

    def should_update_facts(
        self,
        channel: "ProjectDiscussionChannel",
        ai_response: str,
        min_response_length: int = 200,
        min_exchanges_between_updates: int = 3,
        user_message: str = "",
    ) -> bool:
        """
        Determine if we should run fact extraction on this exchange.
        Prevents excessive LLM calls by rate limiting fact extraction.
        """
        # Urgency bypass: force extraction for high-signal user messages,
        # even when assistant response is short.
        if user_message:
            msg_lower = user_message.lower()
            urgent_patterns = [
                "research question", "i want to study", "i'm investigating",
                "my topic is", "i decided", "i've decided", "let's go with",
                "i'm focusing on", "my goal is", "the main question",
                "i want to explore", "my thesis is about",
            ]
            if any(p in msg_lower for p in urgent_patterns):
                return True

        # Otherwise, only extract facts for substantial responses
        if len(ai_response) < min_response_length:
            return False

        memory = self._get_ai_memory(channel)

        # Track exchange count since last fact extraction
        exchange_count = memory.get("_exchanges_since_fact_update", 0)

        # Update every N exchanges or if facts are empty
        has_facts = bool(memory.get("facts", {}).get("research_topic"))

        if not has_facts or exchange_count >= min_exchanges_between_updates:
            return True

        return False

    def increment_exchange_counter(self, channel: "ProjectDiscussionChannel") -> None:
        """Increment the exchange counter for rate limiting fact extraction."""
        memory = self._get_ai_memory(channel)
        memory["_exchanges_since_fact_update"] = memory.get("_exchanges_since_fact_update", 0) + 1
        self._save_ai_memory(channel, memory)

    def reset_exchange_counter(self, channel: "ProjectDiscussionChannel") -> None:
        """Reset the exchange counter after fact extraction."""
        memory = self._get_ai_memory(channel)
        memory["_exchanges_since_fact_update"] = 0
        self._save_ai_memory(channel, memory)

    # =========================================================================
    # Phase 3: Research State Tracking & Long-Term Memory
    # =========================================================================

    def detect_research_stage(
        self,
        user_message: str,
        ai_response: str,
        current_stage: str,
    ) -> tuple[str, float]:
        """
        Detect the user's current research stage based on conversation.
        Returns (stage, confidence) tuple.

        Stages:
        - exploring: Broad questions, "what should I research?"
        - refining: Narrowing scope, comparing approaches
        - finding_papers: Actively searching literature
        - analyzing: Deep dive into specific papers/methods
        - writing: Drafting, synthesizing, asking about citations
        """
        # Heuristic detection based on message patterns
        message_lower = user_message.lower()
        response_lower = ai_response.lower()

        # Stage indicators (patterns that suggest each stage)
        stage_indicators = {
            "exploring": [
                "what should i", "where do i start", "research topic",
                "ideas for", "suggest a topic", "broad overview",
                "what are the main", "introduce me to",
            ],
            "refining": [
                "narrow down", "focus on", "compare", "which approach",
                "between these", "pros and cons", "should i choose",
                "more specific", "scope", "limit to",
            ],
            "finding_papers": [
                "find papers", "search for", "literature on",
                "recent papers", "seminal work", "key papers",
                "who wrote about", "publications on", "references for",
            ],
            "analyzing": [
                "explain this paper", "methodology in", "how does this work",
                "implement", "replicate", "details of", "dive deeper",
                "understand the", "specific technique",
            ],
            "writing": [
                "write", "draft", "summarize for", "citation",
                "how to cite", "literature review", "introduction section",
                "conclusion", "abstract", "thesis statement",
            ],
        }

        # Priority order for tie-breaking (more specific stages win)
        stage_priority = ["writing", "analyzing", "finding_papers", "refining", "exploring"]

        # Count matches for each stage
        # User message gets full weight; AI response gets reduced weight
        # to prevent the AI's suggestions from driving stage detection.
        stage_scores = {}
        for stage, patterns in stage_indicators.items():
            user_score = sum(1 for p in patterns if p in message_lower)
            ai_score = sum(1 for p in patterns if p in response_lower)
            score = user_score + (ai_score * 0.3)
            stage_scores[stage] = score

        # Find the maximum score
        max_score = max(stage_scores.values())

        # If no matches at all, stay at current stage
        if max_score == 0:
            return current_stage, 0.5

        # Get all stages with max score (to handle ties)
        top_stages = [stage for stage, score in stage_scores.items() if score == max_score]

        # If there's a tie, use priority order to pick the most specific stage
        if len(top_stages) > 1:
            for priority_stage in stage_priority:
                if priority_stage in top_stages:
                    best_stage = priority_stage
                    break
            else:
                # Fallback to first in list (shouldn't happen)
                best_stage = top_stages[0]
        else:
            best_stage = top_stages[0]

        best_score = stage_scores[best_stage]

        # Calculate confidence based on score and whether it matches current
        confidence = min(0.9, 0.5 + (best_score * 0.1))

        # Add inertia - prefer to stay in current stage unless strong signal
        # Threshold is 1.3 so one clear user match + partial AI confirmation suffices
        if best_stage != current_stage and best_score < 1.3:
            return current_stage, 0.6

        return best_stage, confidence

    def update_research_state(
        self,
        channel: "ProjectDiscussionChannel",
        user_message: str,
        ai_response: str,
    ) -> Dict[str, Any]:
        """
        Update research state based on current exchange.
        Returns the updated research state.
        """
        from datetime import datetime, timezone

        memory = self._get_ai_memory(channel)
        research_state = memory.get("research_state", {
            "stage": "exploring",
            "stage_confidence": 0.5,
            "stage_history": [],
        })

        current_stage = research_state.get("stage", "exploring")
        new_stage, confidence = self.detect_research_stage(
            user_message, ai_response, current_stage
        )

        # Record stage transition if changed
        if new_stage != current_stage:
            research_state["stage_history"].append({
                "from": current_stage,
                "to": new_stage,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "confidence": confidence,
            })
            # Keep only last 10 transitions
            research_state["stage_history"] = research_state["stage_history"][-10:]

        research_state["stage"] = new_stage
        research_state["stage_confidence"] = confidence

        memory["research_state"] = research_state
        self._save_ai_memory(channel, memory)

        return research_state

    def track_unanswered_question(
        self,
        channel: "ProjectDiscussionChannel",
        user_message: str,
        ai_response: str,
    ) -> None:
        """
        Track questions the AI couldn't fully answer for follow-up.
        """
        # Detect if AI indicated it couldn't answer
        uncertainty_phrases = [
            "i don't have access to",
            "i cannot find",
            "i'm not sure",
            "i don't know",
            "couldn't find information",
            "no results found",
            "unable to locate",
            "you might need to",
            "i recommend checking",
        ]

        response_lower = ai_response.lower()
        is_uncertain = any(phrase in response_lower for phrase in uncertainty_phrases)

        if not is_uncertain:
            return

        # Extract the question from user message
        memory = self._get_ai_memory(channel)
        facts = memory.get("facts", {})
        unanswered = facts.get("unanswered_questions", [])

        # Simple question extraction (first sentence or whole message if short)
        question = user_message.strip()
        if len(question) > 200:
            question = question[:200] + "..."

        # Avoid duplicates
        if question not in unanswered:
            unanswered.append(question)
            # Keep only last 5 unanswered questions
            facts["unanswered_questions"] = unanswered[-5:]
            memory["facts"] = facts
            self._save_ai_memory(channel, memory)

    def resolve_unanswered_question(
        self,
        channel: "ProjectDiscussionChannel",
        resolved_question: str,
    ) -> None:
        """
        Remove a question from unanswered list when resolved.
        """
        memory = self._get_ai_memory(channel)
        facts = memory.get("facts", {})
        unanswered = facts.get("unanswered_questions", [])

        # Remove if found (fuzzy match)
        resolved_lower = resolved_question.lower()
        facts["unanswered_questions"] = [
            q for q in unanswered
            if resolved_lower not in q.lower()
        ]
        memory["facts"] = facts
        self._save_ai_memory(channel, memory)

    def update_long_term_memory(
        self,
        channel: "ProjectDiscussionChannel",
        user_message: str,
        ai_response: str,
        user_id: Optional[Any] = None,
    ) -> None:
        """
        Update long-term memory with persistent learnings.
        Extracts user preferences and rejected approaches.
        """
        memory = self._get_ai_memory(channel)
        long_term = self._get_long_term_bucket(
            memory,
            user_id=user_id,
            create_user_profile=user_id is not None,
        )

        message_lower = user_message.lower()

        # Detect preferences (patterns like "I prefer", "I like", "always use")
        preference_patterns = [
            ("i prefer", "prefers"),
            ("i like", "likes"),
            ("i always", "always"),
            ("i usually", "usually"),
            ("my preference is", "prefers"),
        ]

        for pattern, label in preference_patterns:
            if pattern in message_lower:
                # Extract the preference statement
                idx = message_lower.find(pattern)
                end_idx = message_lower.find(".", idx)
                if end_idx == -1:
                    end_idx = min(idx + 100, len(user_message))
                pref = user_message[idx:end_idx].strip()
                if pref and pref not in long_term["user_preferences"]:
                    long_term["user_preferences"].append(pref)
                    # Keep last 10 preferences
                    long_term["user_preferences"] = long_term["user_preferences"][-10:]
                break

        # Detect rejected approaches
        rejection_patterns = [
            "i don't want", "not interested in", "avoid", "don't like",
            "rejected", "ruled out", "won't work", "not suitable",
        ]

        for pattern in rejection_patterns:
            if pattern in message_lower:
                idx = message_lower.find(pattern)
                end_idx = message_lower.find(".", idx)
                if end_idx == -1:
                    end_idx = min(idx + 100, len(user_message))
                rejection = user_message[idx:end_idx].strip()
                if rejection and rejection not in long_term["rejected_approaches"]:
                    long_term["rejected_approaches"].append(rejection)
                    long_term["rejected_approaches"] = long_term["rejected_approaches"][-10:]
                break

        deferred_item = self._extract_deferred_follow_up_item(user_message)
        if deferred_item:
            existing = {x.lower() for x in long_term.get("follow_up_items", [])}
            if deferred_item.lower() not in existing:
                long_term.setdefault("follow_up_items", []).append(deferred_item)
                long_term["follow_up_items"] = long_term["follow_up_items"][-10:]

        self._ensure_long_term_schema(memory)
        self._save_ai_memory(channel, memory)

    def get_session_context_for_return(
        self,
        channel: "ProjectDiscussionChannel",
        user_id: Optional[Any] = None,
    ) -> str:
        """
        Generate a context summary for when user returns to a session.
        Useful for "welcome back" scenarios.
        """
        memory = self._get_ai_memory(channel)

        lines = []
        lines.append("## Session Context (Welcome Back)")

        # Research state
        research_state = memory.get("research_state", {})
        stage = research_state.get("stage", "exploring")
        stage_labels = {
            "exploring": "exploring research topics",
            "refining": "refining your research scope",
            "finding_papers": "searching for relevant literature",
            "analyzing": "analyzing specific papers/methods",
            "writing": "working on your writing",
        }
        lines.append(f"\n**Current Stage:** You were {stage_labels.get(stage, stage)}.")

        # Research topic
        facts = memory.get("facts", {})
        if facts.get("research_topic"):
            lines.append(f"**Research Topic:** {facts['research_topic']}")

        # Recent decisions
        decisions = facts.get("decisions_made", [])
        if decisions:
            lines.append("\n**Recent Decisions:**")
            for d in decisions[-3:]:
                lines.append(f"- {d}")

        # Pending questions
        pending = facts.get("pending_questions", [])
        if pending:
            lines.append("\n**Open Questions:**")
            for q in pending:
                lines.append(f"- {q}")

        # Unanswered questions
        unanswered = facts.get("unanswered_questions", [])
        if unanswered:
            lines.append("\n**Questions I Couldn't Answer Previously:**")
            for q in unanswered:
                lines.append(f"- {q}")

        # User preferences
        long_term = self._get_long_term_bucket(memory, user_id=user_id, create_user_profile=False)
        prefs = long_term.get("user_preferences", [])
        if prefs:
            lines.append("\n**Your Preferences:**")
            for p in prefs[-3:]:
                lines.append(f"- {p}")

        follow_ups = long_term.get("follow_up_items", [])
        if follow_ups:
            lines.append("\n**Saved Follow-ups:**")
            for item in follow_ups[-5:]:
                lines.append(f"- {item}")

        return "\n".join(lines) if len(lines) > 1 else ""

    def build_full_memory_context(
        self,
        channel: "ProjectDiscussionChannel",
        include_welcome_back: bool = False,
        user_id: Optional[Any] = None,
    ) -> str:
        """
        Build complete memory context including all three tiers:
        1. Working memory (handled in _build_messages)
        2. Session summary
        3. Long-term memory (research state, preferences, etc.)
        """
        memory = self._get_ai_memory(channel)

        # Long-form phase descriptions for public API
        phase_descriptions = {
            "exploring": "Initial exploration phase",
            "refining": "Refining research scope",
            "finding_papers": "Literature search phase",
            "analyzing": "Deep analysis phase",
            "writing": "Writing/synthesis phase",
        }

        # Delegate to core builder without focused papers and unanswered questions
        # (those are internal-only for system prompt optimization)
        return self._build_memory_context_core(
            memory=memory,
            include_focused_papers=False,
            include_unanswered_questions=False,
            summary_header="## Conversation Summary",
            phase_descriptions=phase_descriptions,
            user_id=user_id,
        )
