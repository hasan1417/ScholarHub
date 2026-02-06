"""
Memory management mixin for the Discussion AI orchestrator.

Handles AI memory persistence, summarization, fact extraction, research state
tracking, long-term memory, and tool result caching.
"""

from __future__ import annotations

import json
import logging
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
                    "successful_searches": [],
                }
            if "unanswered_questions" not in memory.get("facts", {}):
                memory.setdefault("facts", {})["unanswered_questions"] = []
            return memory
        return {
            "summary": None,
            "facts": {
                "research_topic": None,
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
                "successful_searches": [],      # Search queries that yielded good results
            },
            "key_quotes": [],
            "last_summarized_exchange_id": None,
            "tool_cache": {},
        }

    def _save_ai_memory(self, channel: "ProjectDiscussionChannel", memory: Dict[str, Any]) -> None:
        """Save AI memory to channel."""
        try:
            channel.ai_memory = memory
            # CRITICAL: Flag the JSON column as modified so SQLAlchemy detects the change
            # Without this, mutating a JSON dict in-place won't be persisted
            if hasattr(channel, "_sa_instance_state"):
                flag_modified(channel, "ai_memory")
            self.db.commit()
            logger.info(f"Saved AI memory for channel {channel.id} - focused_papers: {len(memory.get('focused_papers', []))}")
        except Exception as e:
            logger.error(f"Failed to save AI memory: {e}")
            self.db.rollback()

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
            client = self.ai_service.openai_client
            if not client:
                return existing_summary or ""

            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Use faster/cheaper model for summarization
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
    ) -> Dict[str, Any]:
        """
        Extract structured research facts from the latest exchange.
        Updates existing facts with new information.
        """
        prompt = f"""Analyze this research conversation exchange and extract key facts.

USER MESSAGE:
{user_message[:1000]}

AI RESPONSE:
{ai_response[:1500]}

EXISTING FACTS:
{json.dumps(existing_facts, indent=2)}

Extract and UPDATE the facts JSON. Only include new/changed information.
Return a JSON object with these fields (keep existing values if not changed):
- research_topic: Main research topic (string or null)
- papers_discussed: Array of {{"title": "...", "author": "...", "relevance": "why discussed", "user_reaction": "positive/negative/neutral"}}
- decisions_made: Array of decision strings (append new ones, don't remove old)
- pending_questions: Array of unanswered questions (can remove if answered)
- methodology_notes: Array of methodology-related notes

Return ONLY valid JSON, no explanation:"""

        try:
            client = self.ai_service.openai_client
            if not client:
                return existing_facts

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.2,
            )

            result_text = response.choices[0].message.content.strip()
            # Try to parse JSON from response
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]

            new_facts = json.loads(result_text)

            # Merge with existing facts (append arrays, update scalars)
            merged = existing_facts.copy()
            if new_facts.get("research_topic"):
                merged["research_topic"] = new_facts["research_topic"]

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

            return merged

        except Exception as e:
            logger.error(f"Failed to extract research facts: {e}")
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
        ]

        message_lower = user_message.lower()
        for pattern in important_patterns:
            pattern_lower = pattern.lower()
            if pattern_lower in message_lower:
                # Extract the sentence containing the pattern
                sentences = user_message.replace("!", ".").replace("?", ".").split(".")
                for sentence in sentences:
                    if pattern_lower in sentence.lower() and len(sentence.strip()) > 20:
                        quote = sentence.strip()[:200]
                        if quote not in existing_quotes:
                            existing_quotes.append(quote)
                        break

        # Keep only the last 5 quotes
        return existing_quotes[-5:]

    def update_memory_after_exchange(
        self,
        channel: "ProjectDiscussionChannel",
        user_message: str,
        ai_response: str,
        conversation_history: List[Dict[str, str]],
    ) -> Optional[str]:
        """
        Update AI memory after an exchange. Called after each successful response.
        Handles summarization, fact extraction, quote preservation, and pruning.

        Returns: Optional contradiction warning if detected.
        """
        memory = self._get_ai_memory(channel)
        contradiction_warning = None

        # Extract key quotes from user message (cheap, do always)
        memory["key_quotes"] = self._extract_key_quotes(
            user_message,
            memory.get("key_quotes", [])
        )

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

        # Rate-limited fact extraction (only every N exchanges or when needed)
        if self.should_update_facts(channel, ai_response):
            # Check for contradictions before updating facts
            existing_facts = memory.get("facts", {})
            if existing_facts.get("decisions_made") or existing_facts.get("research_topic"):
                contradiction_warning = self.detect_contradictions(user_message, existing_facts)

            # Extract research facts
            memory["facts"] = self._extract_research_facts(
                user_message,
                ai_response,
                existing_facts,
            )
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
            self._update_long_term_memory_inline(memory, user_message, ai_response)
        except Exception as e:
            logger.error(f"Failed to update Phase 3 memory: {e}")

        # Single save for all memory mutations
        self._save_ai_memory(channel, memory)

        return contradiction_warning

    def _build_memory_context(self, channel: "ProjectDiscussionChannel") -> str:
        """
        Build context string from AI memory for inclusion in system prompt.
        Includes all three memory tiers: working, session, and long-term.
        """
        memory = self._get_ai_memory(channel)
        lines = []

        # DEBUG: Log what's in memory
        logger.info(f"Building memory context. Memory keys: {list(memory.keys())}")
        logger.info(f"Focused papers in memory: {len(memory.get('focused_papers', []))}")

        # Tier 2: Session summary
        if memory.get("summary"):
            lines.append("## Previous Conversation Summary")
            lines.append(memory["summary"])
            lines.append("")

        # CRITICAL: Include focused papers so AI knows to use analyze_across_papers
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

        # Tier 3: Research state (Phase 3)
        research_state = memory.get("research_state", {})
        stage = research_state.get("stage", "exploring")
        if stage != "exploring" or research_state.get("stage_confidence", 0) > 0.6:
            stage_desc = {
                "exploring": "Initial exploration",
                "refining": "Refining scope",
                "finding_papers": "Literature search",
                "analyzing": "Deep analysis",
                "writing": "Writing phase",
            }
            lines.append(f"**Research Phase:** {stage_desc.get(stage, stage)}")

        # Research facts
        facts = memory.get("facts", {})
        if facts.get("research_topic"):
            lines.append(f"**Research Focus:** {facts['research_topic']}")

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

        # Tier 3: Unanswered questions (Phase 3)
        if facts.get("unanswered_questions"):
            lines.append("**Previously Unanswered Questions:**")
            for q in facts["unanswered_questions"]:
                lines.append(f"- {q}")

        # Tier 3: Long-term memory (Phase 3)
        long_term = memory.get("long_term", {})
        if long_term.get("user_preferences"):
            lines.append("**User Preferences:**")
            for p in long_term["user_preferences"][-3:]:
                lines.append(f"- {p}")

        if long_term.get("rejected_approaches"):
            lines.append("**Rejected Approaches (avoid suggesting):**")
            for r in long_term["rejected_approaches"][-3:]:
                lines.append(f"- {r}")

        # Key quotes
        if memory.get("key_quotes"):
            lines.append("**Key User Statements:**")
            for q in memory["key_quotes"]:
                lines.append(f'- "{q}"')

        return "\n".join(lines) if lines else ""

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
        indicators = ["?", "how", "what", "why", "when", "where", "which", "can you", "could you"]
        response_lower = ai_response.lower()
        is_answered = any(phrase in response_lower for phrase in [
            "here's", "here is", "i found", "the answer", "based on",
            "according to", "the results show",
        ])
        if is_answered:
            return

        message_lower = user_message.lower()
        is_question = any(ind in message_lower for ind in indicators)
        if not is_question:
            return

        facts = memory.get("facts", {})
        unanswered = facts.get("unanswered_questions", [])
        question = user_message.strip()
        if len(question) > 200:
            question = question[:200] + "..."
        if question not in unanswered:
            unanswered.append(question)
            facts["unanswered_questions"] = unanswered[-5:]
            memory["facts"] = facts

    def _update_long_term_memory_inline(
        self,
        memory: Dict[str, Any],
        user_message: str,
        ai_response: str,
    ) -> None:
        """Update long-term memory in memory dict in-place (no DB read/save)."""
        long_term = memory.get("long_term", {
            "user_preferences": [],
            "rejected_approaches": [],
            "successful_strategies": [],
        })
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

        memory["long_term"] = long_term

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
            client = self.ai_service.openai_client
            if not client:
                return None

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.1,
            )
            result = response.choices[0].message.content.strip()

            if "NO_CONTRADICTION" in result.upper():
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
    ) -> bool:
        """
        Determine if we should run fact extraction on this exchange.
        Prevents excessive LLM calls by rate limiting fact extraction.
        """
        # Only extract facts for substantial responses
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

        # Count matches for each stage
        stage_scores = {}
        for stage, patterns in stage_indicators.items():
            score = sum(1 for p in patterns if p in message_lower or p in response_lower)
            stage_scores[stage] = score

        # Find best matching stage
        best_stage = max(stage_scores, key=stage_scores.get)
        best_score = stage_scores[best_stage]

        # Calculate confidence based on score and whether it matches current
        if best_score == 0:
            # No clear indicators, stay at current stage
            return current_stage, 0.5

        confidence = min(0.9, 0.5 + (best_score * 0.1))

        # Add inertia - prefer to stay in current stage unless strong signal
        if best_stage != current_stage and best_score < 2:
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
    ) -> None:
        """
        Update long-term memory with persistent learnings.
        Extracts user preferences and rejected approaches.
        """
        memory = self._get_ai_memory(channel)
        long_term = memory.get("long_term", {
            "user_preferences": [],
            "rejected_approaches": [],
            "successful_searches": [],
        })

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

        memory["long_term"] = long_term
        self._save_ai_memory(channel, memory)

    def get_session_context_for_return(
        self,
        channel: "ProjectDiscussionChannel",
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
        long_term = memory.get("long_term", {})
        prefs = long_term.get("user_preferences", [])
        if prefs:
            lines.append("\n**Your Preferences:**")
            for p in prefs[-3:]:
                lines.append(f"- {p}")

        return "\n".join(lines) if len(lines) > 1 else ""

    def build_full_memory_context(
        self,
        channel: "ProjectDiscussionChannel",
        include_welcome_back: bool = False,
    ) -> str:
        """
        Build complete memory context including all three tiers:
        1. Working memory (handled in _build_messages)
        2. Session summary
        3. Long-term memory (research state, preferences, etc.)
        """
        memory = self._get_ai_memory(channel)
        lines = []

        # Session summary (Tier 2)
        if memory.get("summary"):
            lines.append("## Conversation Summary")
            lines.append(memory["summary"])
            lines.append("")

        # Research state
        research_state = memory.get("research_state", {})
        stage = research_state.get("stage", "exploring")
        if stage != "exploring" or research_state.get("stage_confidence", 0) > 0.6:
            stage_desc = {
                "exploring": "Initial exploration phase",
                "refining": "Refining research scope",
                "finding_papers": "Literature search phase",
                "analyzing": "Deep analysis phase",
                "writing": "Writing/synthesis phase",
            }
            lines.append(f"**Research Phase:** {stage_desc.get(stage, stage)}")

        # Research facts
        facts = memory.get("facts", {})
        if facts.get("research_topic"):
            lines.append(f"**Research Focus:** {facts['research_topic']}")

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

        # Long-term memory
        long_term = memory.get("long_term", {})
        if long_term.get("user_preferences"):
            lines.append("**User Preferences:**")
            for p in long_term["user_preferences"][-3:]:
                lines.append(f"- {p}")

        if long_term.get("rejected_approaches"):
            lines.append("**Rejected Approaches:**")
            for r in long_term["rejected_approaches"][-3:]:
                lines.append(f"- {r}")

        # Key quotes
        if memory.get("key_quotes"):
            lines.append("**Key User Statements:**")
            for q in memory["key_quotes"]:
                lines.append(f'- "{q}"')

        return "\n".join(lines) if lines else ""
