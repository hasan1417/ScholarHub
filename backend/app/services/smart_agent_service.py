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
    - SIMPLE: Greetings, help → gpt-4o-mini, no context
    - PAPER: Draft questions → gpt-4o-mini, doc excerpt only
    - RESEARCH: Reference/literature → gpt-4o, full RAG
    """

    # Models for different tiers
    FAST_MODEL = "gpt-4o-mini"  # Fast, cheap, good for simple tasks
    QUALITY_MODEL = "gpt-4o"    # Balanced speed/quality for research
    REASONING_MODEL = "gpt-5.2"  # Advanced reasoning model

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
        "compare", "contrast", "gap", "review"
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
        edit_mode: bool = False
    ) -> Generator[str, None, None]:
        """
        Stream query response with smart routing.
        """
        if not self.client:
            yield "AI service not available."
            return

        has_doc = bool(document_excerpt and document_excerpt.strip())

        # Edit mode: AI can suggest document modifications
        if edit_mode and has_doc:
            print(f"[SmartAgent-Stream] Edit mode enabled, using {self.QUALITY_MODEL}")
            yield from self._stream_edit(db, query, user_id, paper_id, document_excerpt)
            return

        # If reasoning mode is enabled, use reasoning model directly
        if reasoning_mode:
            print(f"[SmartAgent-Stream] Reasoning mode enabled, using {self.REASONING_MODEL}")
            yield from self._stream_reasoning(db, query, user_id, paper_id, document_excerpt)
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
            max_tokens=300,
            temperature=0.7
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
                    "You are a helpful research assistant for ScholarHub. "
                    "Be concise and friendly."
                )
            },
            {"role": "user", "content": query}
        ]

        stream = self.client.chat.completions.create(
            model=self.FAST_MODEL,
            messages=messages,
            max_tokens=300,
            temperature=0.7,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    # ==================== PAPER ROUTE ====================

    def _handle_paper(self, query: str, document_excerpt: Optional[str]) -> Dict[str, Any]:
        """Handle paper-specific queries with doc context."""
        doc_context = (document_excerpt or "")[:4000]  # Limit context size

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
            max_tokens=1000,
            temperature=0.7
        )

        return {
            "response": response.choices[0].message.content,
            "route": "paper",
            "model": self.FAST_MODEL,
            "tools_called": []
        }

    def _stream_paper(self, query: str, document_excerpt: Optional[str]) -> Generator[str, None, None]:
        """Stream paper query response."""
        doc_context = (document_excerpt or "")[:4000]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a research writing assistant. Help with academic paper writing. "
                    "Be concise and actionable."
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
            max_tokens=1000,
            temperature=0.7,
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
        """Handle research queries with full RAG."""
        # Get reference context
        ref_context = self._get_reference_context(db, user_id, paper_id, query)
        doc_context = (document_excerpt or "")[:2000] if document_excerpt else ""

        context_parts = []
        if ref_context:
            context_parts.append(
                "=== REFERENCE LIBRARY ===\n"
                "(These are academic papers/sources the user has saved for citation)\n\n"
                f"{ref_context}"
            )
        if doc_context:
            context_parts.append(
                "=== USER'S PAPER DRAFT ===\n"
                "(This is the paper the user is currently writing)\n\n"
                f"{doc_context}"
            )

        full_context = "\n\n".join(context_parts) if context_parts else "No context available."

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert research assistant helping a user write an academic paper. "
                    "You have access to two types of context:\n"
                    "1. REFERENCE LIBRARY: Academic papers/sources the user has saved - use these to cite and support arguments\n"
                    "2. USER'S PAPER DRAFT: The paper the user is currently writing - this is THEIR work in progress\n\n"
                    "IMPORTANT: Do NOT confuse these. References are external sources to cite. "
                    "The draft is the user's own writing. When asked about 'my references', refer to the Reference Library. "
                    "When asked about 'my paper' or 'my draft', refer to the User's Paper Draft.\n"
                    "Cite sources by title/author when using reference information. Be thorough but concise."
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
            max_tokens=2000,
            temperature=0.7
        )

        return {
            "response": response.choices[0].message.content,
            "route": "research",
            "model": self.QUALITY_MODEL,
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
        """Stream research query response with RAG."""
        ref_context = self._get_reference_context(db, user_id, paper_id, query)
        doc_context = (document_excerpt or "")[:2000] if document_excerpt else ""

        context_parts = []
        if ref_context:
            context_parts.append(
                "=== REFERENCE LIBRARY ===\n"
                "(These are academic papers/sources the user has saved for citation)\n\n"
                f"{ref_context}"
            )
        if doc_context:
            context_parts.append(
                "=== USER'S PAPER DRAFT ===\n"
                "(This is the paper the user is currently writing)\n\n"
                f"{doc_context}"
            )

        full_context = "\n\n".join(context_parts) if context_parts else "No context available."

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert research assistant helping a user write an academic paper. "
                    "You have access to two types of context:\n"
                    "1. REFERENCE LIBRARY: Academic papers/sources the user has saved - use these to cite and support arguments\n"
                    "2. USER'S PAPER DRAFT: The paper the user is currently writing - this is THEIR work in progress\n\n"
                    "IMPORTANT: Do NOT confuse these. References are external sources to cite. "
                    "The draft is the user's own writing. When asked about 'my references', refer to the Reference Library. "
                    "When asked about 'my paper' or 'my draft', refer to the User's Paper Draft.\n"
                    "Cite sources by title/author when using reference information. Be thorough but concise."
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
            max_tokens=2000,
            temperature=0.7,
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
        doc_context = (document_excerpt or "")[:3000] if document_excerpt else ""

        context_parts = []
        if ref_context:
            context_parts.append(
                "=== REFERENCE LIBRARY ===\n"
                "(Academic papers/sources for citation)\n\n"
                f"{ref_context}"
            )
        if doc_context:
            context_parts.append(
                "=== USER'S PAPER DRAFT ===\n"
                "(The paper being written)\n\n"
                f"{doc_context}"
            )

        full_context = "\n\n".join(context_parts) if context_parts else ""

        # Build the user message with context
        user_content = query
        if full_context:
            user_content = f"{full_context}\n\n---\n\nQuestion: {query}"

        messages = [
            {
                "role": "user",
                "content": user_content
            }
        ]

        response = self.client.chat.completions.create(
            model=self.REASONING_MODEL,
            messages=messages,
            max_completion_tokens=4000
        )

        return {
            "response": response.choices[0].message.content,
            "route": "reasoning",
            "model": self.REASONING_MODEL,
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
        """Stream reasoning query response with o3-mini."""
        ref_context = self._get_reference_context(db, user_id, paper_id, query)
        doc_context = (document_excerpt or "")[:3000] if document_excerpt else ""

        context_parts = []
        if ref_context:
            context_parts.append(
                "=== REFERENCE LIBRARY ===\n"
                "(Academic papers/sources for citation)\n\n"
                f"{ref_context}"
            )
        if doc_context:
            context_parts.append(
                "=== USER'S PAPER DRAFT ===\n"
                "(The paper being written)\n\n"
                f"{doc_context}"
            )

        full_context = "\n\n".join(context_parts) if context_parts else ""

        # Build the user message with context
        user_content = query
        if full_context:
            user_content = f"{full_context}\n\n---\n\nQuestion: {query}"

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
                "=== REFERENCE LIBRARY ===\n"
                "(Academic papers/sources for citation)\n\n"
                f"{ref_context}"
            )

        ref_section = "\n\n".join(context_parts) if context_parts else ""

        system_prompt = """You are an expert academic writing editor. The user is asking you to modify their document.

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
            max_tokens=3000,
            temperature=0.7,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
