"""
Paper focus and analysis tools mixin for the Discussion AI orchestrator.

Handles paper focusing, cross-paper analysis using RAG, deep search,
and section generation from discussion insights.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from app.services.discussion_ai.utils import sanitize_for_context

if TYPE_CHECKING:
    from app.models import Project

logger = logging.getLogger(__name__)


class AnalysisToolsMixin:
    """Mixin providing paper focus and analysis tools.

    Expects the composed class to provide:
        - self.ai_service: AIService
        - self.db: Session
        - self._get_ai_memory(channel) -> Dict
        - self._save_ai_memory(channel, memory) -> None
    """

    def _tool_trigger_search_ui(
        self,
        ctx: Dict[str, Any],
        research_question: str,
        max_papers: int = 10,
    ) -> Dict:
        """
        Trigger the frontend search UI for a research question.

        This tool does NOT perform an actual search - it sends an action to the frontend
        to display a search interface where the user can execute and review the search results.
        """
        # Store the research question in memory for context
        channel = ctx.get("channel")
        if channel:
            memory = self._get_ai_memory(channel)
            memory.setdefault("search_ui_trigger", {})["last_question"] = research_question
            self._save_ai_memory(channel, memory)

        # Trigger the frontend search UI
        return {
            "status": "success",
            "message": f"Opening search interface for: '{research_question}'",
            "research_question": research_question,
            "action": {
                "type": "deep_search_references",
                "payload": {
                    "query": research_question,
                    "max_results": max_papers,
                    "synthesis_mode": True,
                },
            },
            "next_step": (
                "The search interface will appear below. Once the search completes, "
                "I can help synthesize the results or you can focus on specific papers for deeper discussion."
            ),
        }

    def _tool_focus_on_papers(
        self,
        ctx: Dict[str, Any],
        paper_indices: Optional[List[int]] = None,
        reference_ids: Optional[List[str]] = None,
    ) -> Dict:
        """
        Load papers into focus context for detailed discussion.
        Papers can come from search results (by index) or library (by reference ID).
        """
        from app.models import Reference, ProjectReference

        project = ctx["project"]
        channel = ctx.get("channel")
        recent_search_results = ctx.get("recent_search_results", [])

        focused_papers = []
        errors = []

        # Build lookup for existing library references (to check if search results are already ingested)
        library_refs_by_doi = {}
        library_refs_by_title = {}
        if paper_indices:
            # Pre-fetch library references for matching
            library_refs = self.db.query(Reference).join(
                ProjectReference, ProjectReference.reference_id == Reference.id
            ).filter(ProjectReference.project_id == project.id).limit(1000).all()

            for ref in library_refs:
                if ref.doi:
                    library_refs_by_doi[ref.doi.lower().replace("https://doi.org/", "").strip()] = ref
                if ref.title:
                    library_refs_by_title[ref.title.lower().strip()] = ref

        # Get papers from search results by index
        if paper_indices:
            for idx in paper_indices:
                if idx < 0 or idx >= len(recent_search_results):
                    errors.append(f"Index {idx} out of range (have {len(recent_search_results)} results)")
                    continue

                paper = recent_search_results[idx]

                # Check if this paper is already in the library (by DOI or title)
                matched_ref = None
                paper_doi = paper.get("doi", "")
                if paper_doi:
                    matched_ref = library_refs_by_doi.get(paper_doi.lower().replace("https://doi.org/", "").strip())
                if not matched_ref and paper.get("title"):
                    matched_ref = library_refs_by_title.get(paper["title"].lower().strip())

                if matched_ref and matched_ref.status in ("ingested", "analyzed"):
                    # Paper is already in library with ingested PDF - use that data!
                    logger.info(f"Focus: Found '{paper.get('title', '')[:50]}' already ingested in library")
                    focused_papers.append({
                        "source": "library",  # Mark as library source since we're using library data
                        "reference_id": str(matched_ref.id),
                        "index": idx,
                        "title": matched_ref.title,
                        "authors": matched_ref.authors if isinstance(matched_ref.authors, str) else ", ".join(matched_ref.authors or []),
                        "year": matched_ref.year,
                        "abstract": matched_ref.abstract or paper.get("abstract", ""),
                        "doi": matched_ref.doi,
                        "url": matched_ref.url,
                        "pdf_url": paper.get("pdf_url"),
                        "is_open_access": paper.get("is_open_access", False),
                        "summary": matched_ref.summary,
                        "key_findings": matched_ref.key_findings,
                        "methodology": matched_ref.methodology,
                        "limitations": matched_ref.limitations,
                        "has_full_text": True,  # Already ingested!
                    })
                else:
                    # Paper not in library or not ingested - use search result data
                    focused_papers.append({
                        "source": "search_result",
                        "index": idx,
                        "title": paper.get("title", "Untitled"),
                        "authors": paper.get("authors", "Unknown"),
                        "year": paper.get("year"),
                        "abstract": paper.get("abstract", ""),
                        "doi": paper.get("doi"),
                        "url": paper.get("url"),
                        "pdf_url": paper.get("pdf_url"),
                        "is_open_access": paper.get("is_open_access", False),
                        "has_full_text": False,  # Search results only have abstracts
                    })

        # Get papers from library by reference ID
        if reference_ids:
            import uuid as uuid_module
            for ref_id in reference_ids:
                try:
                    # Validate UUID format
                    try:
                        uuid_module.UUID(str(ref_id))
                    except (ValueError, AttributeError):
                        errors.append(f"Invalid reference ID format: '{ref_id}'. Use get_project_references to see valid IDs.")
                        continue

                    ref = self.db.query(Reference).join(
                        ProjectReference,
                        ProjectReference.reference_id == Reference.id
                    ).filter(
                        ProjectReference.project_id == project.id,
                        Reference.id == ref_id
                    ).first()

                    if ref:
                        paper_info = {
                            "source": "library",
                            "reference_id": str(ref.id),
                            "title": ref.title,
                            "authors": ref.authors if isinstance(ref.authors, str) else ", ".join(ref.authors or []),
                            "year": ref.year,
                            "abstract": ref.abstract or "",
                            "doi": ref.doi,
                            "url": ref.url,
                        }

                        # Include analysis if PDF was ingested
                        if ref.status in ("ingested", "analyzed"):
                            paper_info["summary"] = ref.summary
                            paper_info["key_findings"] = ref.key_findings
                            paper_info["methodology"] = ref.methodology
                            paper_info["limitations"] = ref.limitations
                            paper_info["has_full_text"] = True
                        else:
                            paper_info["has_full_text"] = False

                        focused_papers.append(paper_info)
                    else:
                        errors.append(f"Reference {ref_id} not found in project library")
                except Exception as e:
                    errors.append(f"Error loading reference {ref_id}: {str(e)}")

        if not focused_papers:
            return {
                "status": "error",
                "message": "No papers could be focused. " + " ".join(errors),
                "errors": errors,
            }

        # Store focused papers in channel memory
        if channel:
            memory = self._get_ai_memory(channel)
            memory["focused_papers"] = focused_papers
            self._save_ai_memory(channel, memory)
            logger.info(f"✅ Saved {len(focused_papers)} focused papers to channel memory (channel_id: {channel.id})")

        # Build summary for response and count full-text papers
        paper_summaries = []
        full_text_count = 0
        abstract_only_count = 0
        papers_with_pdf_url = []

        for i, p in enumerate(focused_papers, 1):
            has_full = p.get("has_full_text", False)
            if has_full:
                full_text_count += 1
                status = "📄"  # Full PDF analyzed
                depth = "(full text available)"
            else:
                abstract_only_count += 1
                status = "📋"  # Abstract only
                depth = "(abstract only)"
                # Track papers that have PDF URLs but aren't ingested yet
                if p.get("pdf_url") or p.get("is_open_access"):
                    papers_with_pdf_url.append(i)

            paper_summaries.append(f"{i}. {status} **{sanitize_for_context(p['title'], 300)}** ({p.get('year', 'N/A')}) {depth}")
            if p.get("authors"):
                authors = p["authors"]
                if isinstance(authors, list):
                    authors = ", ".join(authors[:3]) + ("..." if len(authors) > 3 else "")
                paper_summaries.append(f"   Authors: {sanitize_for_context(str(authors), 300)}")

        # Build depth analysis message
        depth_info = {}
        if abstract_only_count > 0:
            depth_info["abstract_only_papers"] = abstract_only_count
            depth_info["full_text_papers"] = full_text_count

            if abstract_only_count == len(focused_papers):
                depth_info["analysis_depth"] = "shallow"
                depth_info["limitation"] = (
                    "All focused papers have only abstracts available. "
                    "Analysis will be limited to high-level information. "
                    "For deeper discussion (methodology details, specific findings, limitations), "
                    "you'll need to add papers to your library and ingest their PDFs."
                )
            else:
                depth_info["analysis_depth"] = "mixed"
                depth_info["limitation"] = (
                    f"{abstract_only_count} paper(s) have only abstracts. "
                    f"{full_text_count} paper(s) have full PDF analysis available. "
                    "Detailed questions will be better answered for papers with full text."
                )

            # Suggest how to get full text
            if papers_with_pdf_url:
                depth_info["suggestion"] = (
                    f"Papers {', '.join(map(str, papers_with_pdf_url))} have PDFs available. "
                    "To enable deeper analysis: add them to your library using add_to_library, "
                    "or upload the PDFs manually through the Library page."
                )
            else:
                depth_info["suggestion"] = (
                    "To enable deeper analysis, upload PDFs for these papers through the Library page, "
                    "or search for open-access versions."
                )
        else:
            depth_info["analysis_depth"] = "deep"
            depth_info["full_text_papers"] = full_text_count

        result = {
            "status": "success",
            "message": f"Focused on {len(focused_papers)} paper(s)",
            "focused_count": len(focused_papers),
            "papers": paper_summaries,
            "depth_info": depth_info,
            "errors": errors if errors else None,
            "capabilities": [
                "Ask detailed questions about these papers",
                "Use analyze_across_papers to compare them",
                "Use generate_section_from_discussion to create content",
            ] if full_text_count > 0 else [
                "Ask high-level questions about these papers (based on abstracts)",
                "Use analyze_across_papers for broad comparisons",
                "For detailed methodology/findings discussion, add papers to library first",
            ],
        }

        # If there are OA papers without full text, suggest adding them to library
        # and return indices so AI can offer to ingest them
        if papers_with_pdf_url:
            result["oa_papers_available"] = papers_with_pdf_url
            result["auto_ingest_suggestion"] = (
                f"Papers {', '.join(map(str, papers_with_pdf_url))} have PDFs available (Open Access). "
                "Would you like me to add them to your library and ingest the PDFs for deeper analysis? "
                "This will give me access to full methodology, results, and detailed findings."
            )

        return result

    def _tool_analyze_across_papers(
        self,
        ctx: Dict[str, Any],
        analysis_question: str,
    ) -> Dict:
        """
        Cross-paper analysis using RAG (Retrieval Augmented Generation).
        Dynamically retrieves relevant chunks based on the analysis question.
        """
        from app.models import Reference, ProjectReference
        from app.models.document_chunk import DocumentChunk

        channel = ctx.get("channel")
        project = ctx.get("project")
        if not channel:
            return {
                "status": "error",
                "message": "Channel context not available.",
            }

        memory = self._get_ai_memory(channel)
        focused_papers = memory.get("focused_papers", [])

        if not focused_papers:
            return {
                "status": "error",
                "message": "No papers in focus. Use focus_on_papers first to load papers for analysis.",
                "suggestion": "Try: 'Focus on papers 1 and 2' or 'Focus on the first three papers from the search'",
            }

        # Map focused papers to their reference IDs (if they exist in library)
        paper_to_ref_id = {}
        papers_with_chunks = []
        papers_abstract_only = []

        if project:
            # Get all project references for matching
            references = self.db.query(Reference).join(
                ProjectReference, ProjectReference.reference_id == Reference.id
            ).filter(ProjectReference.project_id == project.id).limit(1000).all()

            # Build lookup maps
            doi_to_ref = {}
            title_to_ref = {}
            url_to_ref = {}
            for ref in references:
                if ref.doi:
                    doi_to_ref[ref.doi.lower().replace("https://doi.org/", "").strip()] = ref
                if ref.title:
                    title_to_ref[ref.title.lower().strip()] = ref
                if ref.url:
                    url_to_ref[ref.url] = ref

            # Match focused papers to references
            for i, paper in enumerate(focused_papers):
                matched_ref = None
                paper_doi = paper.get("doi", "")
                if paper_doi:
                    matched_ref = doi_to_ref.get(paper_doi.lower().replace("https://doi.org/", "").strip())
                if not matched_ref and paper.get("title"):
                    matched_ref = title_to_ref.get(paper["title"].lower().strip())
                if not matched_ref and paper.get("url"):
                    matched_ref = url_to_ref.get(paper["url"])

                if matched_ref and matched_ref.document_id:
                    paper_to_ref_id[i] = matched_ref
                    papers_with_chunks.append((i, paper, matched_ref))
                else:
                    papers_abstract_only.append((i, paper))

        # Use RAG to find relevant chunks for papers that have been ingested
        rag_context_by_paper = {}

        if papers_with_chunks and self.ai_service and self.ai_service.openai_client:
            try:
                # Create embedding for the analysis question
                embedding_response = self.ai_service.openai_client.embeddings.create(
                    model=self.ai_service.embedding_model,
                    input=analysis_question
                )
                query_embedding = embedding_response.data[0].embedding

                # Convert embedding to pgvector format
                from sqlalchemy import text
                embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

                # For each paper with chunks, find the most relevant chunks using pgvector SQL
                for paper_idx, paper, ref in papers_with_chunks:
                    # Use pgvector to find top chunks directly in the database
                    sql = text("""
                        SELECT id, chunk_text, 1 - (embedding <=> :query_embedding) as similarity
                        FROM document_chunks
                        WHERE document_id = :document_id
                            AND embedding IS NOT NULL
                        ORDER BY embedding <=> :query_embedding
                        LIMIT :limit
                    """)

                    result = self.db.execute(
                        sql,
                        {
                            "query_embedding": embedding_str,
                            "document_id": str(ref.document_id),
                            "limit": 4,
                        }
                    )
                    rows = result.fetchall()

                    if rows:
                        # Build context from relevant chunks
                        chunk_texts = []
                        top_score = 0.0
                        for row in rows:
                            chunk_text = row.chunk_text
                            similarity = row.similarity
                            if not top_score:
                                top_score = similarity
                            # Truncate very long chunks
                            text = chunk_text[:1500] if len(chunk_text) > 1500 else chunk_text
                            chunk_texts.append(text)

                        rag_context_by_paper[paper_idx] = {
                            "chunks": chunk_texts,
                            "chunk_count": len(rows),
                            "top_score": top_score,
                        }
                        logger.info(f"RAG: Found {len(rows)} relevant chunks for paper {paper_idx + 1} (top score: {top_score:.3f})")
                    else:
                        papers_abstract_only.append((paper_idx, paper))

            except Exception as e:
                logger.error(f"RAG embedding search failed: {e}")
                logger.warning(f"[RAG] Full-text search failed, falling back to abstract-only for {len(papers_with_chunks)} papers")
                # Fall back to treating all as abstract-only
                for paper_idx, paper, ref in papers_with_chunks:
                    papers_abstract_only.append((paper_idx, paper))

        # Build the full context for the AI
        paper_contexts = []
        full_text_count = 0
        abstract_only_count = 0

        for i, paper in enumerate(focused_papers):
            if i in rag_context_by_paper:
                # Paper has RAG-retrieved content
                full_text_count += 1
                rag_data = rag_context_by_paper[i]

                context_parts = [f"### Paper {i + 1}: <paper-title>{sanitize_for_context(paper.get('title', 'Untitled'), 300)}</paper-title> [Full Text - RAG Retrieved]"]
                context_parts.append(f"**Authors:** <paper-authors>{sanitize_for_context(str(paper.get('authors', 'Unknown')), 300)}</paper-authors>")
                context_parts.append(f"**Year:** {paper.get('year', 'N/A')}")

                # Include abstract for context
                if paper.get("abstract"):
                    context_parts.append(f"**Abstract:** <paper-abstract>{sanitize_for_context(paper['abstract'], 400)}</paper-abstract>")

                # Include RAG-retrieved relevant content
                context_parts.append(f"\n**Relevant Content ({rag_data['chunk_count']} passages retrieved for your question):**")
                for j, chunk_text in enumerate(rag_data["chunks"], 1):
                    context_parts.append(f"\n[Passage {j}]\n{chunk_text}")

                paper_contexts.append("\n".join(context_parts))
            elif paper.get("has_full_text") and (paper.get("summary") or paper.get("key_findings") or paper.get("methodology")):
                # Paper has inline analysis data (from library ingestion) but no RAG chunks
                full_text_count += 1
                context_parts = [f"### Paper {i + 1}: <paper-title>{sanitize_for_context(paper.get('title', 'Untitled'), 300)}</paper-title> [Full Text]"]
                context_parts.append(f"**Authors:** <paper-authors>{sanitize_for_context(str(paper.get('authors', 'Unknown')), 300)}</paper-authors>")
                context_parts.append(f"**Year:** {paper.get('year', 'N/A')}")

                if paper.get("abstract"):
                    context_parts.append(f"**Abstract:** <paper-abstract>{sanitize_for_context(paper['abstract'], 400)}</paper-abstract>")

                if paper.get("summary"):
                    context_parts.append(f"**Summary:** {sanitize_for_context(paper['summary'], 1000)}")
                if paper.get("key_findings"):
                    findings = paper["key_findings"]
                    if isinstance(findings, list):
                        context_parts.append("**Key Findings:**")
                        for f in findings:
                            context_parts.append(f"- {f}")
                    else:
                        context_parts.append(f"**Key Findings:** {findings}")
                if paper.get("methodology"):
                    context_parts.append(f"**Methodology:** {paper['methodology']}")
                if paper.get("limitations"):
                    limitations = paper["limitations"]
                    if isinstance(limitations, list):
                        context_parts.append("**Limitations:**")
                        for lim in limitations:
                            context_parts.append(f"- {lim}")
                    else:
                        context_parts.append(f"**Limitations:** {limitations}")

                paper_contexts.append("\n".join(context_parts))
            else:
                # Abstract only
                abstract_only_count += 1
                context_parts = [f"### Paper {i + 1}: <paper-title>{sanitize_for_context(paper.get('title', 'Untitled'), 300)}</paper-title> [Abstract Only]"]
                context_parts.append(f"**Authors:** <paper-authors>{sanitize_for_context(str(paper.get('authors', 'Unknown')), 300)}</paper-authors>")
                context_parts.append(f"**Year:** {paper.get('year', 'N/A')}")

                if paper.get("abstract"):
                    context_parts.append(f"**Abstract:** <paper-abstract>{sanitize_for_context(paper['abstract'], 800)}</paper-abstract>")

                paper_contexts.append("\n".join(context_parts))

        full_context = "\n\n" + "=" * 50 + "\n\n".join(paper_contexts)

        # Build depth info
        depth_warning = None
        if abstract_only_count > 0:
            if abstract_only_count == len(focused_papers):
                depth_warning = (
                    "⚠️ **Limited Analysis:** All papers have only abstracts available. "
                    "For detailed analysis, add papers to library and ingest PDFs."
                )
            else:
                depth_warning = (
                    f"📊 **Mixed Depth:** {full_text_count} paper(s) have full-text RAG retrieval, "
                    f"{abstract_only_count} paper(s) have abstracts only."
                )

        # Add RAG failure warning if applicable
        if rag_failed:
            rag_warning = " (Note: Full-text search failed, using abstracts only for papers that would normally have full-text)"
            if depth_warning:
                depth_warning += rag_warning
            else:
                depth_warning = "⚠️ " + rag_warning

        # Store analysis info in memory
        memory.setdefault("cross_paper_analysis", {})["last_question"] = analysis_question
        memory["cross_paper_analysis"]["paper_count"] = len(focused_papers)
        memory["cross_paper_analysis"]["rag_papers"] = full_text_count
        memory["cross_paper_analysis"]["abstract_only"] = abstract_only_count
        self._save_ai_memory(channel, memory)

        # Build instruction
        instruction = (
            f"Analyze the following question across all {len(focused_papers)} papers:\n\n"
            f"**Question:** {analysis_question}\n\n"
            "**Instructions:**\n"
            "1. For [Full Text - RAG Retrieved] papers, use the retrieved passages to provide specific, detailed answers\n"
            "2. Quote or reference specific content from the passages when relevant\n"
            "3. For [Abstract Only] papers, provide high-level analysis based on the abstract\n"
            "4. Compare and contrast across papers where applicable\n"
            "5. Identify common themes and patterns across papers\n"
            "6. Cite papers by number (e.g., [Paper 1], [Paper 2])\n"
        )

        return {
            "status": "success",
            "message": f"Analyzing across {len(focused_papers)} papers using RAG",
            "analysis_question": analysis_question,
            "paper_count": len(focused_papers),
            "rag_papers": full_text_count,
            "abstract_only_papers": abstract_only_count,
            "depth_info": depth_warning,
            "papers_context": full_context,
            "instruction": instruction,
            "retrieval_method": "semantic_search" if full_text_count > 0 else "abstracts_only",
        }

    def _tool_generate_section_from_discussion(
        self,
        ctx: Dict[str, Any],
        section_type: str,
        target_paper_id: Optional[str] = None,
        custom_instructions: Optional[str] = None,
    ) -> Dict:
        """
        Generate a paper section based on discussion insights and focused papers.
        Can either add to an existing paper or create a standalone artifact.
        """
        channel = ctx.get("channel")
        if not channel:
            return {
                "status": "error",
                "message": "Channel context not available.",
            }

        memory = self._get_ai_memory(channel)
        focused_papers = memory.get("focused_papers", [])
        session_summary = memory.get("summary", "")
        facts = memory.get("facts", {})
        # Support both old and new memory keys for backward compatibility
        search_ui_trigger = memory.get("search_ui_trigger", memory.get("deep_search", {}))
        cross_analysis = memory.get("cross_paper_analysis", {})

        # Build context from all available sources
        context_parts = []

        # Add focused papers context
        if focused_papers:
            context_parts.append(f"**Focused Papers ({len(focused_papers)}):**")
            for i, p in enumerate(focused_papers, 1):
                paper_info = f"- [{i}] <paper-title>{sanitize_for_context(p.get('title', 'Untitled'), 300)}</paper-title> ({p.get('year', 'N/A')})"
                if p.get("key_findings"):
                    findings = p["key_findings"]
                    if isinstance(findings, list) and findings:
                        paper_info += f"\n  Key finding: {findings[0]}"
                context_parts.append(paper_info)

        # Add session context
        if session_summary:
            context_parts.append(f"\n**Discussion Summary:**\n{session_summary[:500]}")

        # Add research topic
        if facts.get("research_topic"):
            context_parts.append(f"\n**Research Topic:** {facts['research_topic']}")

        # Add decisions made
        if facts.get("decisions_made"):
            context_parts.append(f"\n**Decisions Made:**")
            for d in facts["decisions_made"][-5:]:
                context_parts.append(f"- {d}")

        # Add search UI trigger question if available
        if search_ui_trigger.get("last_question"):
            context_parts.append(f"\n**Research Question:** {search_ui_trigger['last_question']}")

        # Add cross-analysis context
        if cross_analysis.get("last_question"):
            context_parts.append(f"\n**Cross-paper Analysis:** {cross_analysis['last_question']}")

        full_context = "\n".join(context_parts) if context_parts else "No prior context available."

        # Section-specific instructions
        section_instructions = {
            "methodology": (
                "Generate a Methodology section that:\n"
                "- Describes the research approach\n"
                "- References methods from the discussed papers\n"
                "- Uses proper academic language\n"
                "- Cites sources appropriately"
            ),
            "related_work": (
                "Generate a Related Work section that:\n"
                "- Reviews the key papers discussed\n"
                "- Groups them by theme or approach\n"
                "- Identifies gaps and opportunities\n"
                "- Uses proper citation format"
            ),
            "introduction": (
                "Generate an Introduction section that:\n"
                "- Motivates the research problem\n"
                "- Provides background context\n"
                "- States the research objectives\n"
                "- Outlines the paper structure"
            ),
            "results": (
                "Generate a Results section that:\n"
                "- Summarizes key findings from the discussion\n"
                "- Presents comparisons across papers\n"
                "- Uses clear, objective language"
            ),
            "discussion": (
                "Generate a Discussion section that:\n"
                "- Interprets the findings\n"
                "- Compares with existing literature\n"
                "- Addresses limitations\n"
                "- Suggests future directions"
            ),
            "conclusion": (
                "Generate a Conclusion section that:\n"
                "- Summarizes the main contributions\n"
                "- Restates key findings\n"
                "- Provides final thoughts"
            ),
            "abstract": (
                "Generate an Abstract that:\n"
                "- Summarizes the research in 150-250 words\n"
                "- States the problem, approach, and findings\n"
                "- Is self-contained and informative"
            ),
        }

        section_prompt = section_instructions.get(
            section_type,
            f"Generate a {section_type} section based on the discussion context."
        )

        if custom_instructions:
            section_prompt += f"\n\n**Additional Instructions:** {custom_instructions}"

        # If target paper specified, update it
        if target_paper_id:
            return {
                "status": "success",
                "message": f"Ready to generate {section_type} section for existing paper",
                "section_type": section_type,
                "target_paper_id": target_paper_id,
                "context": full_context,
                "generation_prompt": section_prompt,
                "instruction": (
                    f"Generate a {section_type.replace('_', ' ')} section in LaTeX format based on the context provided. "
                    f"Use \\section{{{section_type.replace('_', ' ').title()}}} for the heading. "
                    "Include \\cite{} commands for references. "
                    "After generating, use update_paper to add it to the target paper."
                ),
            }

        # Otherwise, return context for creating an artifact
        return {
            "status": "success",
            "message": f"Ready to generate {section_type} section",
            "section_type": section_type,
            "context": full_context,
            "generation_prompt": section_prompt,
            "focused_paper_count": len(focused_papers),
            "instruction": (
                f"Generate a {section_type.replace('_', ' ')} section in LaTeX format based on the context provided. "
                f"Use \\section{{{section_type.replace('_', ' ').title()}}} for the heading. "
                "Include \\cite{} commands for references to the focused papers. "
                "After generating the content, use create_artifact or create_paper to save it."
            ),
        }
