"""
Smart Agent Service - Intelligent routing for fast + quality responses
"""
import os
import logging
import time
from typing import Optional, List, Dict, Any, Generator
from sqlalchemy.orm import Session
from openai import OpenAI

logger = logging.getLogger(__name__)


class SmartAgentService:
    """
    Smart agent that routes queries to appropriate model/context combinations:
    - SIMPLE: Greetings, help → gpt-5-mini, no context
    - PAPER: Draft questions → gpt-5-mini, doc excerpt only
    - RESEARCH: Reference queries → gpt-5.2 (low reasoning), attached refs
    - REVIEW: Feedback requests → gpt-5.2 (low reasoning)
    - EDIT: Document modifications → gpt-5.2 (low reasoning)
    - REASONING: Complex analysis → gpt-5.2 (high reasoning)
    """

    # Models for different tiers
    FAST_MODEL = "gpt-5-mini"   # Fast, cheap, good for simple tasks
    QUALITY_MODEL = "gpt-5.2"   # Quality model with controlled reasoning
    REASONING_MODEL = "gpt-5.2"  # Same model, higher reasoning effort

    # Reasoning effort levels for gpt-5.2 (minimal, low, medium, high)
    QUALITY_REASONING_EFFORT = "low"      # For quality route - fast but smart
    FULL_REASONING_EFFORT = "high"        # For reasoning mode - full power

    # Route patterns
    SIMPLE_PATTERNS = {
        "hi", "hey", "hello", "thanks", "thank you", "ok", "okay", "yes", "no",
        "what can you do", "help", "how are you", "good morning", "good afternoon",
        "who are you", "what are you"
    }

    PAPER_KEYWORDS = {
        "draft", "my paper", "this paper", "my document", "the document",
        "introduction", "conclusion", "abstract", "methodology", "results",
        "section", "paragraph", "sentence", "rewrite", "rephrase", "expand",
        "summarize this", "fix this", "improve this", "what does this mean",
        "thesis", "argument", "flow"
    }

    RESEARCH_KEYWORDS = {
        "reference", "references", "citation", "cite", "literature",
        "papers", "studies", "research", "sources", "find", "search",
        "what do the", "according to", "evidence", "support", "related work",
        "compare", "contrast", "gap"
    }

    # Keywords that indicate user wants edits made to their document
    EDIT_KEYWORDS = {
        "change", "modify", "update", "fix", "rewrite", "improve", "edit",
        "add", "remove", "delete", "replace", "insert", "make it", "rephrase",
        "shorten", "expand", "extend", "lengthen", "correct", "revise", "adjust", "refine",
        "elaborate", "enhance", "strengthen", "clarify", "simplify", "condense",
        "can you change", "can you fix", "can you improve", "can you rewrite",
        "can you extend", "can you expand", "can you add", "can you remove",
        "please change", "please fix", "please improve", "please rewrite",
        "could you change", "could you fix", "could you improve", "could you extend",
        "make this", "write me", "write a", "add a", "add section",
        "add paragraph", "remove this", "delete this", "extend the", "expand the",
        "make the", "rewrite the", "improve the", "fix the", "shorten the"
    }

    # Keywords that indicate user wants feedback/review (offer edits after)
    REVIEW_KEYWORDS = {
        "review", "feedback", "check", "evaluate", "assess", "critique",
        "what do you think", "how does this look", "is this good",
        "any suggestions", "any improvements", "thoughts on", "opinion on",
        "does this make sense", "is this clear", "look over", "proofread"
    }

    # Keywords that confirm user wants edits after review
    CONFIRMATION_KEYWORDS = {
        "yes", "yeah", "yep", "sure", "ok", "okay", "go ahead", "please",
        "do it", "make the changes", "apply", "sounds good", "let's do it",
        "yes please", "please do", "yes, please"
    }

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key) if api_key else None
        if not self.client:
            logger.warning("OpenAI client not initialized - no API key")

    def _quick_classify(self, query: str, has_doc: bool = False) -> Optional[str]:
        """
        Fast classification for obvious simple queries - no DB calls needed.
        Returns 'simple' for obvious cases, None if full classification needed.
        """
        q = query.lower().strip()
        words = q.split()

        # Very short queries without paper/research keywords are simple
        if len(words) <= 2:
            if not any(kw in q for kw in self.PAPER_KEYWORDS | self.RESEARCH_KEYWORDS):
                return "simple"

        # Exact match on simple patterns
        if q in self.SIMPLE_PATTERNS:
            return "simple"

        # Needs full classification
        return None

    def detect_edit_intent(self, query: str, has_doc: bool = False) -> Dict[str, Any]:
        """
        Detect the user's intent regarding edits.
        Returns a dict with:
          - intent: "edit" | "review" | "question" | "confirmation" | "none"
          - should_propose_edits: bool - whether to propose edit blocks
          - explanation: str - brief reason for the classification
        """
        if not has_doc:
            return {
                "intent": "none",
                "should_propose_edits": False,
                "explanation": "No document content available"
            }

        q = query.lower().strip()

        # Check for confirmation (user responding to review feedback)
        if q in self.CONFIRMATION_KEYWORDS or any(conf in q for conf in self.CONFIRMATION_KEYWORDS):
            # Short confirmation messages trigger edit mode
            if len(q.split()) <= 5:
                return {
                    "intent": "confirmation",
                    "should_propose_edits": True,
                    "explanation": "User confirmed they want changes made"
                }

        # Check for direct edit requests
        for kw in self.EDIT_KEYWORDS:
            if kw in q:
                return {
                    "intent": "edit",
                    "should_propose_edits": True,
                    "explanation": f"Direct edit request detected: '{kw}'"
                }

        # Check for review/feedback requests (give feedback, then offer to make changes)
        for kw in self.REVIEW_KEYWORDS:
            if kw in q:
                return {
                    "intent": "review",
                    "should_propose_edits": False,  # Give feedback first, don't propose yet
                    "explanation": f"Review request detected: '{kw}'"
                }

        # Default: treat as a question (no edit proposals)
        return {
            "intent": "question",
            "should_propose_edits": False,
            "explanation": "General question about the document"
        }

    def classify_query(self, query: str, has_doc: bool = False, has_refs: bool = False) -> str:
        """
        Classify query into route: 'simple', 'paper', or 'research'
        Uses keyword matching for speed (no LLM call needed).
        """
        q = query.lower().strip()
        words = q.split()

        # Check for simple patterns (exact match or very short)
        if q in self.SIMPLE_PATTERNS or len(words) <= 2:
            # But if it mentions paper/research terms, escalate
            if not any(kw in q for kw in self.PAPER_KEYWORDS | self.RESEARCH_KEYWORDS):
                return "simple"

        # Check for research keywords (higher priority than paper)
        if any(kw in q for kw in self.RESEARCH_KEYWORDS):
            return "research"

        # Check for paper keywords
        if any(kw in q for kw in self.PAPER_KEYWORDS):
            return "paper" if has_doc else "simple"

        # Default: if we have doc context, treat as paper question
        if has_doc:
            return "paper"

        # Fallback to simple for unknown short queries
        if len(words) <= 5:
            return "simple"

        # Longer queries default to research
        return "research"

    def process_query(
        self,
        db: Session,
        user_id: str,
        query: str,
        paper_id: Optional[str] = None,
        project_id: Optional[str] = None,
        document_excerpt: Optional[str] = None,
        reasoning_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Process query with smart routing. Returns full response (non-streaming).
        """
        if not self.client:
            return {
                "response": "AI service not available.",
                "route": "error",
                "model": "none",
                "tools_called": []
            }

        start = time.time()
        has_doc = bool(document_excerpt and document_excerpt.strip())

        # Fast path: check if query is simple BEFORE any DB calls
        route = self._quick_classify(query, has_doc)
        if route != "simple":
            # Only check references if we might need research route
            has_refs = self._has_references(db, user_id, paper_id)
            route = self.classify_query(query, has_doc, has_refs)
        logger.info(f"[SmartAgent] Query classified as: {route}, reasoning_mode={reasoning_mode}")

        # If reasoning mode is enabled, use the reasoning model
        if reasoning_mode:
            result = self._handle_reasoning(db, query, user_id, paper_id, document_excerpt)
        # Route to appropriate handler
        elif route == "simple":
            result = self._handle_simple(query)
        elif route == "paper":
            result = self._handle_paper(query, document_excerpt)
        else:  # research
            result = self._handle_research(db, query, user_id, paper_id, document_excerpt)

        elapsed = int((time.time() - start) * 1000)
        logger.info(f"[SmartAgent] Route={route}, Model={result['model']}, Time={elapsed}ms")

        return result

    def stream_query(
        self,
        db: Session,
        user_id: str,
        query: str,
        paper_id: Optional[str] = None,
        project_id: Optional[str] = None,
        document_excerpt: Optional[str] = None,
        reasoning_mode: bool = False,
        edit_mode: bool = False  # Now used as override only, auto-detection is primary
    ) -> Generator[str, None, None]:
        """
        Stream query response with smart routing and automatic edit detection.
        The AI automatically detects when to propose edits based on user intent.
        """
        if not self.client:
            yield "AI service not available."
            return

        has_doc = bool(document_excerpt and document_excerpt.strip())

        # If reasoning mode is enabled, use reasoning model directly
        if reasoning_mode:
            print(f"[SmartAgent-Stream] Reasoning mode enabled, using {self.REASONING_MODEL}")
            yield from self._stream_reasoning(db, query, user_id, paper_id, document_excerpt)
            return

        # Auto-detect edit intent (this is the smart part!)
        edit_intent = self.detect_edit_intent(query, has_doc)
        print(f"[SmartAgent-Stream] Edit intent: {edit_intent}")

        # Edit mode override from frontend OR auto-detected edit intent
        if (edit_mode or edit_intent["should_propose_edits"]) and has_doc:
            print(f"[SmartAgent-Stream] Edit mode (auto={edit_intent['intent']}, manual={edit_mode}), using {self.QUALITY_MODEL}")
            yield from self._stream_edit(db, query, user_id, paper_id, document_excerpt)
            return

        # Review intent: give feedback and offer to make changes
        if edit_intent["intent"] == "review" and has_doc:
            print(f"[SmartAgent-Stream] Review mode detected, using {self.QUALITY_MODEL}")
            yield from self._stream_review(db, query, user_id, paper_id, document_excerpt)
            return

        # Fast path: check if query is simple BEFORE any DB calls
        route = self._quick_classify(query, has_doc)
        if route == "simple":
            print(f"[SmartAgent-Stream] Fast path: simple query, using {self.FAST_MODEL}")
            yield from self._stream_simple(query)
            return

        # Only check references if we might need research route
        has_refs = self._has_references(db, user_id, paper_id)
        route = self.classify_query(query, has_doc, has_refs)
        print(f"[SmartAgent-Stream] Query classified as: {route}")

        # Route to appropriate streaming handler
        if route == "simple":
            print(f"[SmartAgent-Stream] Using simple route with {self.FAST_MODEL}")
            yield from self._stream_simple(query)
        elif route == "paper":
            print(f"[SmartAgent-Stream] Using paper route with {self.FAST_MODEL}")
            yield from self._stream_paper(query, document_excerpt)
        else:  # research
            print(f"[SmartAgent-Stream] Using research route with {self.QUALITY_MODEL}")
            yield from self._stream_research(db, query, user_id, paper_id, document_excerpt)

    def _has_references(self, db: Session, user_id: str, paper_id: Optional[str]) -> bool:
        """Check if user has any references available."""
        try:
            from app.models.reference import Reference
            from app.models.paper_reference import PaperReference

            if paper_id:
                count = db.query(Reference).join(
                    PaperReference, PaperReference.reference_id == Reference.id
                ).filter(PaperReference.paper_id == paper_id).count()
            else:
                count = db.query(Reference).filter(Reference.owner_id == user_id).count()
            return count > 0
        except Exception as e:
            logger.warning(f"Error checking references: {e}")
            return False

    # ==================== SIMPLE ROUTE ====================

    def _handle_simple(self, query: str) -> Dict[str, Any]:
        """Handle simple queries with fast model, no context."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful research assistant for ScholarHub, a platform for academic paper writing. "
                    "Be concise and friendly. If asked what you can do, mention you can help with: "
                    "paper writing, finding references, answering questions about drafts, and literature review."
                )
            },
            {"role": "user", "content": query}
        ]

        response = self.client.chat.completions.create(
            model=self.FAST_MODEL,
            messages=messages,
            max_completion_tokens=300,
        )

        return {
            "response": response.choices[0].message.content,
            "route": "simple",
            "model": self.FAST_MODEL,
            "tools_called": []
        }

    def _stream_simple(self, query: str) -> Generator[str, None, None]:
        """Stream simple query response."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful writing assistant for the LaTeX editor in ScholarHub. "
                    "You help users with their current paper/document. Be concise and friendly.\n\n"
                    "IMPORTANT SCOPE LIMITATION: You can ONLY help with:\n"
                    "- The current paper/document the user is editing\n"
                    "- References already attached to this paper\n\n"
                    "You CANNOT search for new papers or references. If the user asks to find/search for papers, "
                    "tell them: 'To discover new papers, you can either use the **Discussion AI** in your project sidebar, "
                    "or visit the **Discovery page** in your project to search and add references.'"
                )
            },
            {"role": "user", "content": query}
        ]

        stream = self.client.chat.completions.create(
            model=self.FAST_MODEL,
            messages=messages,
            max_completion_tokens=300,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    # ==================== PAPER ROUTE ====================

    def _handle_paper(self, query: str, document_excerpt: Optional[str]) -> Dict[str, Any]:
        """Handle paper-specific queries with doc context."""
        doc_context = document_excerpt or ""  # Send full document - models have large context

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a research writing assistant. Help the user with their academic paper. "
                    "Be concise and actionable. Reference specific parts of their draft when relevant."
                )
            },
            {
                "role": "user",
                "content": f"Here is my current draft:\n\n{doc_context}\n\n---\n\nQuestion: {query}"
            }
        ]

        response = self.client.chat.completions.create(
            model=self.FAST_MODEL,
            messages=messages,
            max_completion_tokens=1000,
        )

        return {
            "response": response.choices[0].message.content,
            "route": "paper",
            "model": self.FAST_MODEL,
            "tools_called": []
        }

    def _stream_paper(self, query: str, document_excerpt: Optional[str]) -> Generator[str, None, None]:
        """Stream paper query response."""
        doc_context = document_excerpt or ""  # Send full document

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an academic writing assistant helping with the user's LaTeX paper. "
                    "You can see their FULL document content. Be concise and actionable.\n\n"
                    "SCOPE: You can ONLY help with this specific paper and its attached references. "
                    "You CANNOT search for new papers online. If asked to find papers, tell them: "
                    "'To discover new papers, use the **Discussion AI** in your project sidebar or "
                    "the **Discovery page** in your project.'"
                )
            },
            {
                "role": "user",
                "content": f"My draft:\n\n{doc_context}\n\n---\n\nQuestion: {query}"
            }
        ]

        stream = self.client.chat.completions.create(
            model=self.FAST_MODEL,
            messages=messages,
            max_completion_tokens=1000,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    # ==================== RESEARCH ROUTE ====================

    def _handle_research(
        self,
        db: Session,
        query: str,
        user_id: str,
        paper_id: Optional[str],
        document_excerpt: Optional[str]
    ) -> Dict[str, Any]:
        """Handle queries with attached references only (no external search)."""
        # Get reference context - only attached to this paper
        ref_context = self._get_reference_context(db, user_id, paper_id, query)
        doc_context = document_excerpt or ""  # Send full document

        context_parts = []
        if ref_context:
            context_parts.append(
                "=== ATTACHED REFERENCES ===\n"
                "(Papers/sources attached to THIS paper for citation)\n\n"
                f"{ref_context}"
            )
        if doc_context:
            context_parts.append(
                "=== USER'S PAPER DRAFT ===\n"
                "(The paper the user is currently writing)\n\n"
                f"{doc_context}"
            )

        full_context = "\n\n".join(context_parts) if context_parts else "No references attached to this paper."

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert writing assistant helping with an academic paper in the LaTeX editor.\n\n"
                    "YOUR SCOPE IS LIMITED TO:\n"
                    "1. ATTACHED REFERENCES: Only papers/sources already attached to THIS paper\n"
                    "2. USER'S PAPER DRAFT: The current paper being edited\n\n"
                    "IMPORTANT LIMITATIONS:\n"
                    "- You CANNOT search for new papers or references online\n"
                    "- You can ONLY use references already attached to this paper\n"
                    "- If user asks to 'find papers', 'search for references', or 'look up literature', "
                    "tell them: 'I can only work with references already attached to this paper. "
                    "To discover new papers, use the **Discussion AI** in your project sidebar or "
                    "the **Discovery page** in your project.'\n\n"
                    "When referencing attached sources, cite by title/author. Be thorough but concise."
                )
            },
            {
                "role": "user",
                "content": f"{full_context}\n\n---\n\nQuestion: {query}"
            }
        ]

        response = self.client.chat.completions.create(
            model=self.QUALITY_MODEL,
            messages=messages,
            max_completion_tokens=2000,
            reasoning_effort=self.QUALITY_REASONING_EFFORT
        )

        return {
            "response": response.choices[0].message.content,
            "route": "research",
            "model": f"{self.QUALITY_MODEL} (effort: {self.QUALITY_REASONING_EFFORT})",
            "tools_called": ["get_references"] if ref_context else []
        }

    def _stream_research(
        self,
        db: Session,
        query: str,
        user_id: str,
        paper_id: Optional[str],
        document_excerpt: Optional[str]
    ) -> Generator[str, None, None]:
        """Stream research query response with attached references only."""
        ref_context = self._get_reference_context(db, user_id, paper_id, query)
        doc_context = document_excerpt or ""  # Send full document

        context_parts = []
        if ref_context:
            context_parts.append(
                "=== ATTACHED REFERENCES ===\n"
                "(Papers/sources attached to THIS paper for citation)\n\n"
                f"{ref_context}"
            )
        if doc_context:
            context_parts.append(
                "=== USER'S PAPER DRAFT ===\n"
                "(The paper the user is currently writing)\n\n"
                f"{doc_context}"
            )

        full_context = "\n\n".join(context_parts) if context_parts else "No references attached to this paper."

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert writing assistant helping with an academic paper in the LaTeX editor.\n\n"
                    "YOUR SCOPE IS LIMITED TO:\n"
                    "1. ATTACHED REFERENCES: Only papers/sources already attached to THIS paper\n"
                    "2. USER'S PAPER DRAFT: The current paper being edited\n\n"
                    "IMPORTANT LIMITATIONS:\n"
                    "- You CANNOT search for new papers or references online\n"
                    "- You can ONLY use references already attached to this paper\n"
                    "- If user asks to 'find papers', 'search for references', or 'look up literature', "
                    "tell them: 'I can only work with references already attached to this paper. "
                    "To discover new papers, use the **Discussion AI** in your project sidebar or "
                    "the **Discovery page** in your project.'\n\n"
                    "When referencing attached sources, cite by title/author. Be thorough but concise."
                )
            },
            {
                "role": "user",
                "content": f"{full_context}\n\n---\n\nQuestion: {query}"
            }
        ]

        stream = self.client.chat.completions.create(
            model=self.QUALITY_MODEL,
            messages=messages,
            max_completion_tokens=2000,
            reasoning_effort=self.QUALITY_REASONING_EFFORT,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _get_reference_context(
        self,
        db: Session,
        user_id: str,
        paper_id: Optional[str],
        query: str,
        max_refs: int = 5
    ) -> str:
        """Get relevant reference summaries for context."""
        try:
            from app.models.reference import Reference
            from app.models.paper_reference import PaperReference

            if paper_id:
                refs = db.query(Reference).join(
                    PaperReference, PaperReference.reference_id == Reference.id
                ).filter(
                    PaperReference.paper_id == paper_id
                ).limit(max_refs).all()
            else:
                refs = db.query(Reference).filter(
                    Reference.owner_id == user_id
                ).limit(max_refs).all()

            if not refs:
                return ""

            lines = []
            for i, ref in enumerate(refs, 1):
                title = ref.title or "Untitled"
                year = ref.year or "n.d."
                abstract = (ref.abstract or "")[:300]
                lines.append(f"{i}. {title} ({year})")
                if abstract:
                    lines.append(f"   Abstract: {abstract}...")

            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error getting reference context: {e}")
            return ""

    # ==================== REASONING ROUTE ====================

    def _handle_reasoning(
        self,
        db: Session,
        query: str,
        user_id: str,
        paper_id: Optional[str],
        document_excerpt: Optional[str]
    ) -> Dict[str, Any]:
        """Handle queries with chain-of-thought reasoning using o3-mini."""
        ref_context = self._get_reference_context(db, user_id, paper_id, query)
        doc_context = document_excerpt or ""  # Send full document

        context_parts = []
        if ref_context:
            context_parts.append(
                "=== ATTACHED REFERENCES ===\n"
                "(Papers/sources attached to THIS paper)\n\n"
                f"{ref_context}"
            )
        if doc_context:
            context_parts.append(
                "=== USER'S PAPER DRAFT ===\n"
                "(The paper being written)\n\n"
                f"{doc_context}"
            )

        full_context = "\n\n".join(context_parts) if context_parts else ""

        # Build the user message with context and scope reminder
        scope_note = (
            "IMPORTANT: You can ONLY use the attached references shown above. "
            "You CANNOT search for new papers. If asked to find papers, tell them: "
            "'To discover new papers, use the Discussion AI in your project sidebar or the Discovery page.'\n\n"
        )
        user_content = query
        if full_context:
            user_content = f"{full_context}\n\n---\n\n{scope_note}Question: {query}"
        else:
            user_content = f"{scope_note}Question: {query}"

        messages = [
            {
                "role": "user",
                "content": user_content
            }
        ]

        response = self.client.chat.completions.create(
            model=self.REASONING_MODEL,
            messages=messages,
            max_completion_tokens=4000,
            reasoning_effort=self.FULL_REASONING_EFFORT
        )

        return {
            "response": response.choices[0].message.content,
            "route": "reasoning",
            "model": f"{self.REASONING_MODEL} (effort: {self.FULL_REASONING_EFFORT})",
            "tools_called": ["chain_of_thought"]
        }

    def _stream_reasoning(
        self,
        db: Session,
        query: str,
        user_id: str,
        paper_id: Optional[str],
        document_excerpt: Optional[str]
    ) -> Generator[str, None, None]:
        """Stream reasoning query response with gpt-5.2."""
        ref_context = self._get_reference_context(db, user_id, paper_id, query)
        doc_context = document_excerpt or ""  # Send full document

        context_parts = []
        if ref_context:
            context_parts.append(
                "=== ATTACHED REFERENCES ===\n"
                "(Papers/sources attached to THIS paper)\n\n"
                f"{ref_context}"
            )
        if doc_context:
            context_parts.append(
                "=== USER'S PAPER DRAFT ===\n"
                "(The paper being written)\n\n"
                f"{doc_context}"
            )

        full_context = "\n\n".join(context_parts) if context_parts else ""

        # Build the user message with context and scope reminder
        scope_note = (
            "IMPORTANT: You can ONLY use the attached references shown above. "
            "You CANNOT search for new papers. If asked to find papers, tell them: "
            "'To discover new papers, use the Discussion AI in your project sidebar or the Discovery page.'\n\n"
        )
        user_content = query
        if full_context:
            user_content = f"{full_context}\n\n---\n\n{scope_note}Question: {query}"
        else:
            user_content = f"{scope_note}Question: {query}"

        messages = [
            {
                "role": "user",
                "content": user_content
            }
        ]

        stream = self.client.chat.completions.create(
            model=self.REASONING_MODEL,
            messages=messages,
            max_completion_tokens=4000,
            reasoning_effort=self.FULL_REASONING_EFFORT,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    # ==================== REVIEW MODE ROUTE ====================

    def _stream_review(
        self,
        db: Session,
        query: str,
        user_id: str,
        paper_id: Optional[str],
        document_excerpt: str
    ) -> Generator[str, None, None]:
        """
        Stream review/feedback for the document.
        Provides constructive feedback and offers to make changes.
        """
        ref_context = self._get_reference_context(db, user_id, paper_id, query)

        context_parts = []
        if ref_context:
            context_parts.append(
                "=== ATTACHED REFERENCES ===\n"
                "(Papers/sources attached to THIS paper)\n\n"
                f"{ref_context}"
            )

        ref_section = "\n\n".join(context_parts) if context_parts else ""

        system_prompt = """You are an expert academic writing reviewer and editor in the LaTeX editor. The user wants feedback on their document.

SCOPE LIMITATION: You can ONLY reference papers already attached to this document (shown in ATTACHED REFERENCES).
You CANNOT search for new papers. If you think the paper needs more references, tell the user: "To discover and add more papers, use the **Discussion AI** in your project sidebar or the **Discovery page** in your project."

IMPORTANT: Your response should:
1. Provide specific, actionable feedback on the content
2. Identify strengths and areas for improvement
3. Be constructive and encouraging
4. At the END of your feedback, always ask: "Would you like me to make any of these suggested changes to your document?"

Focus on:
- Clarity and flow of arguments
- Academic writing style and tone
- Structure and organization
- Grammar and word choice (if relevant)
- Completeness of ideas

Keep your feedback focused and concise. Use bullet points for specific suggestions."""

        user_content = f"=== DOCUMENT TO REVIEW ===\n{document_excerpt}\n\n"
        if ref_section:
            user_content += f"{ref_section}\n\n"
        user_content += f"---\n\nUser request: {query}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        stream = self.client.chat.completions.create(
            model=self.QUALITY_MODEL,
            messages=messages,
            max_completion_tokens=2000,
            reasoning_effort=self.QUALITY_REASONING_EFFORT,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    # ==================== EDIT MODE ROUTE ====================

    def _stream_edit(
        self,
        db: Session,
        query: str,
        user_id: str,
        paper_id: Optional[str],
        document_excerpt: str
    ) -> Generator[str, None, None]:
        """
        Stream edit suggestions for the document.
        Returns structured edit proposals that the frontend can parse.
        """
        ref_context = self._get_reference_context(db, user_id, paper_id, query)

        context_parts = []
        if ref_context:
            context_parts.append(
                "=== ATTACHED REFERENCES ===\n"
                "(Papers/sources attached to THIS paper)\n\n"
                f"{ref_context}"
            )

        ref_section = "\n\n".join(context_parts) if context_parts else ""

        system_prompt = """You are an expert academic writing editor in the LaTeX editor. The user is asking you to modify their document.

SCOPE LIMITATION: You can ONLY use references already attached to this document (shown in ATTACHED REFERENCES).
You CANNOT search for new papers. If you need to add citations, only cite papers from the ATTACHED REFERENCES.
If the user asks to add references you don't have, tell them: "I can only cite references already attached to this paper. To discover and add more papers, use the **Discussion AI** in your project sidebar or the **Discovery page** in your project."

IMPORTANT: You MUST format any suggested changes using this EXACT structure:

<<<EDIT>>>
Brief description of this edit
<<<ORIGINAL>>>
The exact text from the document that should be replaced (copy it EXACTLY as it appears)
<<<PROPOSED>>>
The new text that should replace the original
<<<END>>>

RULES:
1. The ORIGINAL text must be copied EXACTLY from the document - including all whitespace, punctuation, and formatting
2. Keep each edit focused on a specific change
3. You can suggest multiple edits for different parts of the document
4. Before the edits, briefly explain your overall approach
5. If the user's request is unclear, ask for clarification instead of guessing
6. For LaTeX documents, preserve all LaTeX commands and formatting
7. Make sure the ORIGINAL text is long enough to be uniquely identifiable in the document

Example format:
"I'll improve the clarity of your introduction and strengthen the thesis statement.

<<<EDIT>>>
Improve opening sentence clarity
<<<ORIGINAL>>>
The study investigates the thing.
<<<PROPOSED>>>
This study investigates the relationship between X and Y, providing novel insights into...
<<<END>>>

<<<EDIT>>>
Strengthen thesis statement
<<<ORIGINAL>>>
We think this is important.
<<<PROPOSED>>>
This research demonstrates the critical importance of X in understanding Y, with implications for...
<<<END>>>"
"""

        user_content = f"=== DOCUMENT TO EDIT ===\n{document_excerpt}\n\n"
        if ref_section:
            user_content += f"{ref_section}\n\n"
        user_content += f"---\n\nUser request: {query}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        stream = self.client.chat.completions.create(
            model=self.QUALITY_MODEL,
            messages=messages,
            max_completion_tokens=3000,
            reasoning_effort=self.QUALITY_REASONING_EFFORT,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
