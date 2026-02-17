import logging
import re
import time
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session

from app.services.reference_summary_service import summarize_paper_references

logger = logging.getLogger(__name__)


class ReferenceChatMixin:

    def chat_with_references(
        self,
        db: Session,
        user_id: str,
        query: str,
        paper_id: Optional[str] = None,
        document_excerpt: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            logger.info(f"Processing reference chat query: '{query}' for user {user_id}")

            if paper_id:
                logger.info(f"Scoped to paper: {paper_id}")
            else:
                logger.info("Scoped to global library")

            if self._is_greeting(query):
                friendly = "Hi there! Ask me about this paper's references and I'll help summarize or answer questions."
                chat_id = f"greet-{int(time.time())}"
                return {
                    "response": friendly,
                    "sources": [],
                    "sources_data": [],
                    "chat_id": chat_id,
                }

            if not self.openai_client:
                raise ValueError("OpenAI client is not configured - cannot chat with references")

            chunks = self.get_relevant_reference_chunks(db, query, user_id, paper_id, limit=8)
            logger.info(f"Found {len(chunks)} relevant chunks")

            if not chunks and not document_excerpt:
                scope_msg = f"for paper '{paper_id}'" if paper_id else "in your library"
                response = (
                    f"I couldn't find relevant content for your query {scope_msg}. "
                    f"Try a more specific question, or ensure your references (with PDFs) are processed."
                )

                chat_id = self._store_reference_chat_session(db, user_id, query, response, [], paper_id)

                if chat_id is None:
                    chat_id = f"no-refs-{int(time.time())}"

                return {
                    "response": response,
                    "sources": [],
                    "sources_data": [],
                    "chat_id": chat_id
                }

            route = self._pick_resources(query, bool(document_excerpt), bool(chunks))
            routed_excerpt = document_excerpt if route["include_doc"] else None
            routed_chunks = chunks if route["include_refs"] else []

            ref_summary_lines: List[str] = []
            ref_sources: List[Dict[str, Any]] = []
            if route.get("include_refs"):
                ref_summary_lines, ref_sources = summarize_paper_references(
                    db,
                    paper_id=paper_id,
                    owner_id=str(user_id) if user_id else None,
                )

            if route.get("doc_requested") and not routed_excerpt:
                response = "I don't have your draft text available to answer this question. Please provide the draft content."
                chat_id = self._store_reference_chat_session(db, user_id, query, response, [], paper_id) or f"no-draft-{int(time.time())}"
                return {
                    "response": response,
                    "sources": [],
                    "sources_data": [],
                    "chat_id": chat_id
                }

            if not routed_chunks and not routed_excerpt and not ref_summary_lines:
                response = "I don't have draft text or references available to answer this yet."
                chat_id = self._store_reference_chat_session(db, user_id, query, response, [], paper_id) or f"no-context-{int(time.time())}"
                return {
                    "response": response,
                    "sources": [],
                    "sources_data": [],
                    "chat_id": chat_id
                }

            logger.info(
                "[route] include_doc=%s include_refs=%s doc_requested=%s routed_chunks=%s ref_summary_count=%s doc_len=%s",
                route.get("include_doc"),
                route.get("include_refs"),
                route.get("doc_requested"),
                len(routed_chunks),
                len(ref_summary_lines),
                len(routed_excerpt or ""),
            )

            response = self.generate_reference_rag_response(
                query,
                routed_chunks,
                document_excerpt=routed_excerpt,
                doc_requested=route["doc_requested"],
                reference_summary=ref_summary_lines,
            )
            logger.info(f"Reference RAG response generated, length: {len(response)}")

            sources = self._prepare_reference_sources(routed_chunks)
            if not sources and ref_sources:
                sources = ref_sources

            chat_id = self._store_reference_chat_session(db, user_id, query, response, sources, paper_id)

            if chat_id is None:
                chat_id = f"ref-chat-{int(time.time())}"

            return {
                "response": response,
                "sources": [s["title"] for s in sources],
                "sources_data": sources,
                "chat_id": chat_id
            }

        except Exception as e:
            logger.error(f"Error in reference chat: {str(e)}")
            return {
                "response": f"Error processing your request: {str(e)}",
                "sources": [],
                "sources_data": [],
                "chat_id": f"error-{int(time.time())}"
            }

    @staticmethod
    def _is_greeting(text: str) -> bool:
        if not text:
            return False
        q = text.strip().lower()
        if len(q) > 24:
            return False
        greetings = {
            "hi", "hey", "hello", "hello there", "hi there", "hey there", "hiya", "howdy",
            "good morning", "good afternoon", "good evening", "yo"
        }
        return q in greetings

    @staticmethod
    def _is_simple_query(text: str) -> bool:
        if not text:
            return False
        q = text.strip().lower()
        words = q.split()
        if len(words) <= 4:
            simple_patterns = {
                "hi", "hey", "hello", "hello there", "hi there", "hey there", "hiya", "howdy",
                "good morning", "good afternoon", "good evening", "yo", "thanks", "thank you",
                "how are you", "what's up", "whats up", "sup", "ok", "okay", "got it",
                "yes", "no", "sure", "help", "what can you do", "who are you"
            }
            if q in simple_patterns:
                return True
            if len(words) <= 2 and not any(w in q for w in ["paper", "draft", "reference", "cite", "section"]):
                return True
        return False

    def _detect_listing_intent(self, query: str) -> Optional[str]:
        try:
            q = (query or "").strip().lower()
            if not q:
                return None
            markers_refs = ["references", "citations", "sources", "refs"]
            markers_papers = ["papers", "paper list", "my papers", "projects"]
            list_verbs = ["what", "which", "list", "show", "how many", "count"]
            if any(v in q for v in list_verbs):
                if any(m in q for m in markers_refs):
                    return "references"
                if any(m in q for m in markers_papers) or "what paper" in q or "what papers" in q:
                    return "papers"
            if "what paper" in q:
                return "papers"
        except Exception:
            pass
        return None

    def _handle_listing_intent(self, db: Session, user_id: str, intent: str, paper_id: Optional[str]) -> Tuple[str, List[Dict[str, Any]]]:
        from app.models.reference import Reference
        from app.models.research_paper import ResearchPaper
        from app.models.paper_reference import PaperReference
        import uuid as _uuid
        try:
            user_uuid = user_id if not isinstance(user_id, str) else _uuid.UUID(user_id)
        except Exception:
            user_uuid = user_id

        if intent == "references":
            if paper_id:
                refs = (
                    db.query(Reference)
                    .join(PaperReference, PaperReference.reference_id == Reference.id)
                    .filter(PaperReference.paper_id == paper_id)
                    .order_by(Reference.created_at.desc())
                    .all()
                )
                title = db.query(ResearchPaper.title).filter(ResearchPaper.id == paper_id).scalar() or "this paper"
                if not refs:
                    return (f"This paper has 0 references.", [])
                lines = []
                sources = []
                for i, r in enumerate(refs, 1):
                    lines.append(f"{i}. {r.title} ({r.year or 'n/a'})")
                    sources.append({"id": str(r.id), "title": r.title})
                resp = f"This paper ('{title}') has {len(refs)} references:\n" + "\n".join(lines)
                return (resp, sources)
            else:
                refs = db.query(Reference).filter(Reference.owner_id == user_uuid).order_by(Reference.created_at.desc()).limit(50).all()
                if not refs:
                    return ("You have 0 references in your library.", [])
                lines = []
                sources = []
                for i, r in enumerate(refs, 1):
                    lines.append(f"{i}. {r.title} ({r.year or 'n/a'}) -- paper: {str(r.paper_id)[:8] if r.paper_id else 'none'}")
                    sources.append({"id": str(r.id), "title": r.title, "paper_id": str(r.paper_id) if r.paper_id else None})
                resp = f"You have {len(refs)} references in your library (showing up to 50):\n" + "\n".join(lines)
                return (resp, sources)

        if intent == "papers":
            papers = db.query(ResearchPaper).filter(ResearchPaper.owner_id == user_uuid).order_by(ResearchPaper.created_at.desc()).limit(50).all()
            if not papers:
                return ("You have 0 papers.", [])
            lines = []
            sources = []
            for i, p in enumerate(papers, 1):
                lines.append(f"{i}. {p.title} -- id: {p.id}")
                sources.append({"id": str(p.id), "title": p.title})
            resp = f"You have {len(papers)} papers (showing up to 50):\n" + "\n".join(lines)
            return (resp, sources)

        return ("I can list your papers or references if you specify.", [])

    def get_relevant_reference_chunks(
        self,
        db: Session,
        query: str,
        user_id: str,
        paper_id: Optional[str] = None,
        limit: int = 8,
        fast_mode: bool = True
    ) -> List[Dict[str, Any]]:
        from app.models.document_chunk import DocumentChunk
        from app.models.reference import Reference
        from app.models.paper_reference import PaperReference

        try:
            import math as _math
            import json as _json
            import uuid as _uuid

            if not isinstance(query, str):
                logger.error(f"Query parameter is not a string! Type: {type(query)}, Value: {repr(query)}")
                if hasattr(query, '__iter__') and not isinstance(query, str):
                    query = ' '.join(str(item) for item in query)
                else:
                    query = str(query)

            try:
                user_uuid = user_id if not isinstance(user_id, str) else _uuid.UUID(user_id)
            except Exception:
                logger.warning(f"Could not parse user_id as UUID: {user_id}")
                user_uuid = user_id

            query_base = db.query(DocumentChunk, Reference).join(
                Reference, DocumentChunk.reference_id == Reference.id
            ).filter(
                Reference.status == 'analyzed',
                DocumentChunk.reference_id.isnot(None)
            )

            if paper_id:
                query_base = query_base.join(
                    PaperReference, PaperReference.reference_id == Reference.id
                ).filter(PaperReference.paper_id == paper_id)
            else:
                query_base = query_base.filter(Reference.owner_id == user_uuid)

            chunk_results = query_base.all()
            if not chunk_results:
                return []

            used_embedding = False
            scored_chunks: List[Dict[str, Any]] = []
            if self.openai_client and not fast_mode:
                try:
                    qemb = self.openai_client.embeddings.create(
                        model=self.embedding_model,
                        input=query
                    ).data[0].embedding

                    def _cos(a, b):
                        try:
                            sa = sum(x*y for x, y in zip(a, b))
                            na = _math.sqrt(sum(x*x for x in a))
                            nb = _math.sqrt(sum(y*y for y in b))
                            return (sa / (na * nb)) if na and nb else 0.0
                        except Exception:
                            return 0.0

                    have_any_emb = False
                    for chunk, reference in chunk_results:
                        emb = getattr(chunk, 'embedding', None)
                        if emb is None:
                            continue
                        if isinstance(emb, str):
                            try:
                                emb = _json.loads(emb)
                            except Exception:
                                emb = None
                        if not emb:
                            continue
                        have_any_emb = True
                        score = float(_cos(qemb, emb))
                        if score > 0:
                            scored_chunks.append({'chunk': chunk, 'reference': reference, 'score': score})
                    if have_any_emb:
                        used_embedding = True
                except Exception as e:
                    logger.warning(f"Embedding-based retrieval failed, falling back to keywords: {e}")

            if not scored_chunks:
                query_terms = [term.lower() for term in query.split() if len(term) > 2]
                for chunk, reference in chunk_results:
                    text = (chunk.chunk_text or '').lower()
                    score = sum(text.count(term) for term in query_terms)
                    if reference.title:
                        title_text = reference.title.lower()
                        score += 2 * sum(title_text.count(term) for term in query_terms)
                    if reference.abstract:
                        abstract_text = reference.abstract.lower()
                        score += 1.5 * sum(abstract_text.count(term) for term in query_terms)
                    if score > 0:
                        scored_chunks.append({'chunk': chunk, 'reference': reference, 'score': float(score)})

            if not scored_chunks:
                logger.info("No matches from embeddings/keywords; falling back to first chunk per reference")
                seen_refs = set()
                for chunk, reference in chunk_results:
                    if reference.id in seen_refs:
                        continue
                    seen_refs.add(reference.id)
                    scored_chunks.append({'chunk': chunk, 'reference': reference, 'score': 0.0})

            scored_chunks.sort(key=lambda x: x['score'], reverse=True)
            top_items = scored_chunks[:max(1, min(limit, 20))]

            seen_refs = {item['reference'].id for item in top_items}
            if len(seen_refs) < len({ref.id for _, ref in chunk_results}):
                missing: Dict[str, Any] = {}
                for chunk, reference in chunk_results:
                    if reference.id in seen_refs or reference.id in missing:
                        continue
                    missing[reference.id] = {'chunk': chunk, 'reference': reference, 'score': -1.0}
                top_items.extend(missing.values())

            results: List[Dict[str, Any]] = []
            for item in top_items:
                chunk = item['chunk']
                reference = item['reference']
                results.append({
                    'text': chunk.chunk_text,
                    'chunk_index': chunk.chunk_index,
                    'reference_id': str(reference.id),
                    'reference_title': reference.title,
                    'reference_authors': reference.authors,
                    'reference_year': reference.year,
                    'reference_journal': reference.journal,
                    'relevance_score': item['score'],
                    'metadata': chunk.chunk_metadata or {},
                })

            return results

        except Exception as e:
            logger.error(f"Error getting relevant reference chunks: {str(e)}")
            return []

    def generate_reference_rag_response(self, query: str, chunks: List[Dict[str, Any]], document_excerpt: Optional[str] = None, doc_requested: bool = False, reference_summary: Optional[List[str]] = None) -> str:
        if not self.openai_client:
            raise ValueError("OpenAI client is not configured - cannot generate response")

        try:
            logger.info(
                "[rag] generating response | chunks=%s ref_summary=%s doc_len=%s",
                len(chunks),
                len(reference_summary or []),
                len(document_excerpt or ""),
            )
            prompt, references_used = self._build_reference_prompt(
                query,
                chunks,
                document_excerpt=document_excerpt,
                doc_requested=doc_requested,
                reference_summary=reference_summary,
            )

            response = self.create_response(
                messages=[
                    {"role": "system", "content": "You are a research assistant helping with academic papers. Respond in plain text. Use bullets only if the user asks for a list. Cite sources as (Title, Year) only when using multiple references. For draft questions, use the paper excerpt first. Never invent references or statistics."},
                    {"role": "user", "content": prompt}
                ],
                max_output_tokens=4000,
                temperature=0.7
            )

            answer = self.extract_response_text(response)

            return answer

        except Exception as e:
            logger.error(f"Error generating reference RAG response: {str(e)}")
            return f"Error generating response: {str(e)}"

    def stream_reference_rag_response(self, query: str, chunks: List[Dict[str, Any]], document_excerpt: Optional[str] = None, paper_id: Optional[str] = None, user_id: Optional[str] = None, db: Optional[Session] = None):
        if not self.openai_client:
            yield "AI service not available. Please try again later."
            return

        try:
            ref_summary_lines: List[str] = []
            ref_sources: List[Dict[str, Any]] = []
            if paper_id and db is not None:
                ref_summary_lines, ref_sources = summarize_paper_references(db, paper_id)

            route = self._pick_resources(query, bool(document_excerpt), bool(chunks) or bool(ref_summary_lines))
            routed_excerpt = document_excerpt if route["include_doc"] else None
            routed_chunks = chunks if route["include_refs"] else []

            if not routed_chunks and not routed_excerpt and not ref_summary_lines:
                if self._is_simple_query(query):
                    messages = [
                        {"role": "system", "content": "You are a helpful research assistant. Be concise."},
                        {"role": "user", "content": query},
                    ]
                    yield from self._stream_chat(messages=messages, model=self.chat_model, temperature=0.7, max_output_tokens=200)
                    return
                yield "I don't have draft text or references available to answer this yet."
                return

            prompt, _ = self._build_reference_prompt(
                query,
                routed_chunks,
                document_excerpt=routed_excerpt,
                doc_requested=route["doc_requested"],
                reference_summary=ref_summary_lines,
            )
            logger.info(
                "[route-stream] include_doc=%s include_refs=%s doc_requested=%s routed_chunks=%s doc_len=%s",
                route.get("include_doc"),
                route.get("include_refs"),
                route.get("doc_requested"),
                len(routed_chunks),
                len(routed_excerpt or ""),
            )
            logger.info(
                "[prompt-stream] len=%s doc_snip=%s ref_summary_snip=%s",
                len(prompt),
                (routed_excerpt or "")[:200],
                (ref_summary_lines or [])[:3],
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a research assistant helping with academic papers. "
                        "Respond in plain text. Use bullets only if the user asks for a list. "
                        "Cite sources as (Title, Year) only when using multiple references. "
                        "For draft questions, use the paper excerpt first. Never invent references or statistics."
                    )
                },
                {"role": "user", "content": prompt},
            ]
            yield from self._stream_chat(
                messages=messages,
                model=self.chat_model,
                temperature=0.7,
                max_output_tokens=4000,
            )
        except Exception as e:
            logger.error(f"Error streaming reference response: {str(e)}")
            yield f"[error streaming response: {str(e)}]"

    def _build_reference_prompt(self, query: str, chunks: List[Dict[str, Any]], document_excerpt: Optional[str] = None, doc_requested: bool = False, reference_summary: Optional[List[str]] = None) -> Tuple[str, Dict[str, Any]]:
        references_used: Dict[str, Any] = {}
        has_refs = bool(chunks) or bool(reference_summary)
        has_doc = bool(document_excerpt)
        summary_text = ""
        if reference_summary:
            summary_text = "\n".join(reference_summary)

        context_parts: List[str] = []
        if has_refs:
            for i, chunk in enumerate(chunks, 1):
                ref_id = chunk['reference_id']
                ref_title = chunk['reference_title'] or f"Reference {ref_id}"

                if ref_id not in references_used:
                    references_used[ref_id] = {
                        'title': ref_title,
                        'authors': chunk.get('reference_authors', []),
                        'year': chunk.get('reference_year'),
                        'journal': chunk.get('reference_journal')
                    }

                context_parts.append(f"From '{ref_title}':\n{chunk['text']}\n---")

        doc_section = ""
        if has_doc:
            doc_section = f"Current paper excerpt (truncated):\n{document_excerpt}\n---\n"

        instructions: List[str] = [
            "Respond concisely in plain text. Use bullets only if the user asks for a list.",
            "When using multiple references, add brief source labels like (Title, Year); skip labels for a single reference.",
            "For draft-related questions, use the paper excerpt first. Note if it appears truncated.",
            "Bring in reference details only when asked for literature context or supporting evidence.",
            "If information is missing, say so clearly. Never invent references or statistics.",
        ]

        if not has_refs:
            instructions.append("No reference chunks are provided; do not mention or invent references, citations, statistics, or sources. If the user asks about references, state that no reference context was supplied.")
        if not has_doc:
            if doc_requested:
                instructions.append("The user asked about draft content but no draft text was supplied. Say that no draft text is available and do not infer draft content from references or elsewhere.")
            else:
                instructions.append("No paper excerpt is provided; if asked about draft content, state that no draft text was supplied.")

        context_block = "\n\n".join(context_parts) if has_refs else ""

        instructions_text = "- " + "\n- ".join(instructions)
        prompt_parts = [
            "You are an AI research assistant helping a user. Answer the user's question using only the provided context.",
            "",
            f"Question: {query}",
            "",
        ]
        if doc_section:
            prompt_parts.append(doc_section.rstrip())
        if summary_text:
            prompt_parts.append("Reference list (titles/years):")
            prompt_parts.append(summary_text)
            prompt_parts.append("Summarize each listed reference separately if the user asks about references. If no content is available for a listed reference, say so without inventing details.")
        if context_block:
            prompt_parts.append("Reference content chunks:")
            prompt_parts.append(context_block)
        prompt_parts.append("Instructions:")
        prompt_parts.append(instructions_text)
        prompt = "\n".join(prompt_parts) + "\n"
        return prompt, references_used

    @staticmethod
    def _has_cue(query: str, cues: List[str]) -> bool:
        q = query.lower()
        for c in cues:
            if ' ' in c:
                if c in q:
                    return True
            else:
                if re.search(rf'\b{re.escape(c)}\b', q):
                    return True
        return False

    def _pick_resources(self, query: str, has_doc: bool, has_refs: bool) -> Dict[str, Any]:
        if self._is_simple_query(query):
            return {"include_doc": False, "include_refs": False, "doc_requested": False}

        doc_cues = ["draft", "section", "paragraph", "my paper", "my document", "in my paper", "what is in my paper"]
        ref_cues = ["reference", "citation", "literature", "related work", "cite", "sources"]
        compare_cues = ["compare", "versus", "vs", "difference", "survey", "review"]

        doc_requested = self._has_cue(query, doc_cues)
        ref_requested = self._has_cue(query, ref_cues)
        compare_requested = self._has_cue(query, compare_cues)

        if doc_requested and not ref_requested and not compare_requested:
            return {
                "include_doc": has_doc,
                "include_refs": False,
                "doc_requested": True,
            }

        def _fallback() -> Dict[str, Any]:
            route = self._route_context(query, has_doc, has_refs)
            return {
                "include_doc": route.get("include_doc", False),
                "include_refs": route.get("include_refs", False),
                "doc_requested": route.get("doc_requested", False),
            }

        return _fallback()

    @classmethod
    def _route_context(cls, query: str, has_doc: bool, has_refs: bool) -> Dict[str, bool]:
        doc_cues = ["draft", "section", "paragraph", "my paper", "my document", "in my paper", "what is in my paper"]
        ref_cues = ["reference", "citation", "literature", "related work", "cite", "sources"]
        compare_cues = ["compare", "versus", "vs", "difference", "survey", "review"]

        doc_requested = cls._has_cue(query, doc_cues)
        ref_requested = cls._has_cue(query, ref_cues)
        compare_focus = cls._has_cue(query, compare_cues)

        if doc_requested and not ref_requested and not compare_focus:
            wants_doc = has_doc
            wants_refs = False
        elif compare_focus and has_doc and has_refs:
            wants_doc = True
            wants_refs = True
        elif ref_requested:
            wants_doc = False
            wants_refs = has_refs
        else:
            wants_doc = has_doc
            wants_refs = has_refs and not has_doc

        return {"include_doc": wants_doc, "include_refs": wants_refs, "doc_requested": doc_requested}

    def _list_references_summary(self, db: Session, paper_id: Optional[str], user_id: str) -> Tuple[str, List[Dict[str, Any]]]:
        from app.models.reference import Reference
        from app.models.paper_reference import PaperReference
        from app.models.research_paper import ResearchPaper
        import uuid as _uuid

        try:
            user_uuid = user_id if not isinstance(user_id, str) else _uuid.UUID(user_id)
        except Exception:
            user_uuid = user_id

        if paper_id:
            refs = (
                db.query(Reference)
                .join(PaperReference, PaperReference.reference_id == Reference.id)
                .filter(PaperReference.paper_id == paper_id)
                .order_by(Reference.created_at.desc())
                .all()
            )
            title = db.query(ResearchPaper.title).filter(ResearchPaper.id == paper_id).scalar() or "this paper"
            if not refs:
                return (f"This paper ('{title}') has 0 references.", [])
            lines = []
            sources = []
            for i, r in enumerate(refs, 1):
                lines.append(f"{i}. {r.title or 'Untitled reference'} ({r.year or 'n/a'})")
                sources.append({"id": str(r.id), "title": r.title, "year": r.year})
            resp = f"This paper ('{title}') has {len(refs)} references:\n" + "\n".join(lines)
            return (resp, sources)

        refs = (
            db.query(Reference)
            .filter(Reference.owner_id == user_uuid)
            .order_by(Reference.created_at.desc())
            .limit(50)
            .all()
        )
        if not refs:
            return ("You have 0 references in your library.", [])
        lines = []
        sources = []
        for i, r in enumerate(refs, 1):
            lines.append(f"{i}. {r.title or 'Untitled reference'} ({r.year or 'n/a'})")
            sources.append({"id": str(r.id), "title": r.title, "year": r.year})
        resp = f"You have {len(refs)} references in your library (showing up to 50):\n" + "\n".join(lines)
        return (resp, sources)

    def _prepare_reference_sources(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sources = {}

        for chunk in chunks:
            ref_id = chunk['reference_id']
            if ref_id not in sources:
                sources[ref_id] = {
                    'id': ref_id,
                    'title': chunk['reference_title'] or f"Reference {ref_id}",
                    'authors': chunk.get('reference_authors', []),
                    'year': chunk.get('reference_year'),
                    'journal': chunk.get('reference_journal'),
                    'chunk_count': 1
                }
            else:
                sources[ref_id]['chunk_count'] += 1

        return list(sources.values())

    def _store_reference_chat_session(
        self,
        db: Session,
        user_id: str,
        query: str,
        response: str,
        sources: List[Dict[str, Any]],
        paper_id: Optional[str] = None
    ) -> Optional[str]:
        try:
            return self._store_chat_session(db, user_id, query, response, sources)
        except Exception as e:
            logger.error(f"Error storing reference chat session: {str(e)}")
            return None
