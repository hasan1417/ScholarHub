"""
Search and discovery tools mixin for the Discussion AI orchestrator.

Handles paper search, topic discovery, related papers, semantic library search,
reference management, and project/channel info retrieval.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from app.models import Project

logger = logging.getLogger(__name__)
T = TypeVar("T")


class SearchToolsMixin:
    """Mixin providing search and discovery tools.

    Expects the composed class to provide:
        - self.ai_service: AIService
        - self.db: Session
        - self._get_ai_memory(channel) -> Dict
        - self._save_ai_memory(channel, memory) -> None
        - self._latex_to_markdown(latex) -> str  (from LibraryToolsMixin)
        - self._generate_citation_key(paper) -> str  (from LibraryToolsMixin)
    """

    def _tool_get_recent_search_results(self, ctx: Dict[str, Any]) -> Dict:
        """Get papers from the most recent search."""
        recent = ctx.get("recent_search_results", [])

        if not recent:
            return {
                "count": 0,
                "papers": [],
                "message": "No recent search results available. The user may need to search for papers first."
            }

        # Count papers with available PDFs
        papers_with_pdf = sum(1 for p in recent if p.get("pdf_url") or p.get("is_open_access"))

        papers_list = []
        for i, p in enumerate(recent):
            paper_info = {
                "index": i,
                "title": p.get("title", "Untitled"),
                "authors": p.get("authors", "Unknown"),
                "year": p.get("year"),
                "source": p.get("source", ""),
                "abstract": p.get("abstract", ""),
                "doi": p.get("doi"),
                "url": p.get("url"),
                "has_pdf_available": bool(p.get("pdf_url") or p.get("is_open_access")),
            }
            papers_list.append(paper_info)

        # Build depth info
        depth_info = {
            "total_papers": len(recent),
            "papers_with_pdf_available": papers_with_pdf,
            "content_available": "abstracts_only",
            "limitation": (
                f"These {len(recent)} papers are search results with ONLY abstracts available. "
                "You can provide high-level summaries and identify themes, but cannot access "
                "detailed methodology, specific results, or in-depth findings."
            ),
        }

        if len(recent) > 5:
            depth_info["recommendation"] = (
                f"For detailed analysis of {len(recent)} papers, recommend the user to: "
                "1) Focus on the most relevant 3-5 papers using focus_on_papers, "
                "2) Add them to library using add_to_library to ingest PDFs, "
                "3) Then ask detailed questions. "
                "For now, you can only provide abstract-based overview."
            )

        return {
            "count": len(recent),
            "papers": papers_list,
            "depth_info": depth_info,
            "message": f"Found {len(recent)} papers from the recent search (abstracts only)."
        }

    def _run_async_operation(self, operation: Callable[[], Awaitable[T]]) -> T:
        """
        Run an async operation from sync tool code safely.

        If we're already in an event loop (e.g., async API path), run the coroutine
        in a dedicated worker thread to avoid nested-loop RuntimeError.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(operation())

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: asyncio.run(operation()))
            return future.result()

    def _tool_get_project_references(
        self,
        ctx: Dict[str, Any],
        topic_filter: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict:
        """Get references from project library."""
        from app.models import ProjectReference, Reference

        project = ctx["project"]

        query = self.db.query(Reference).join(
            ProjectReference,
            ProjectReference.reference_id == Reference.id
        ).filter(
            ProjectReference.project_id == project.id
        )

        if topic_filter:
            from sqlalchemy import func, cast
            from sqlalchemy.dialects.postgresql import ARRAY
            # Search in title, abstract, and authors (authors is an array, so convert to string)
            query = query.filter(
                Reference.title.ilike(f"%{topic_filter}%") |
                Reference.abstract.ilike(f"%{topic_filter}%") |
                func.array_to_string(Reference.authors, ' ').ilike(f"%{topic_filter}%")
            )

        # Get total count BEFORE applying limit (so AI knows actual library size)
        total_count = query.count()

        if limit:
            references = query.limit(limit).all()
        else:
            references = query.all()

        # Count references with ingested PDFs (from returned results)
        ingested_count = sum(1 for ref in references if ref.status in ("ingested", "analyzed"))
        has_pdf_count = sum(1 for ref in references if ref.pdf_url or ref.is_open_access)

        papers_list = []
        for ref in references:
            paper_info = {
                "id": str(ref.id),
                "title": ref.title,
                "authors": ref.authors if isinstance(ref.authors, str) else ", ".join(ref.authors or []),
                "year": ref.year,
                "abstract": ref.abstract or "",
                "source": ref.source,
                "has_pdf": bool(ref.pdf_url),
                "is_open_access": bool(ref.is_open_access),
                "pdf_ingested": ref.status in ("ingested", "analyzed"),
            }

            # Include analysis fields if the PDF was ingested
            if ref.status in ("ingested", "analyzed"):
                if ref.summary:
                    paper_info["summary"] = ref.summary
                if ref.key_findings:
                    paper_info["key_findings"] = ref.key_findings
                if ref.methodology:
                    paper_info["methodology"] = ref.methodology
                if ref.limitations:
                    paper_info["limitations"] = ref.limitations

            papers_list.append(paper_info)

        return {
            "total_count": total_count,  # Total references in library (before limit)
            "returned_count": len(references),  # How many returned in this response
            "ingested_pdf_count": ingested_count,
            "has_pdf_available_count": has_pdf_count,
            "papers": papers_list,
        }

    def _tool_get_reference_details(self, ctx: Dict[str, Any], reference_id: str) -> Dict:
        """Get detailed information about a specific reference by ID."""
        from app.models import ProjectReference, Reference, Document

        project = ctx["project"]

        # Find the reference in the project library
        ref = self.db.query(Reference).join(
            ProjectReference,
            ProjectReference.reference_id == Reference.id
        ).filter(
            ProjectReference.project_id == project.id,
            Reference.id == reference_id
        ).first()

        if not ref:
            return {"error": f"Reference not found in project library (ID: {reference_id})"}

        # Build detailed response
        result = {
            "id": str(ref.id),
            "title": ref.title,
            "authors": ref.authors if isinstance(ref.authors, str) else ", ".join(ref.authors or []),
            "year": ref.year,
            "doi": ref.doi,
            "url": ref.url,
            "source": ref.source,
            "journal": ref.journal,
            "abstract": ref.abstract,
            "has_pdf": bool(ref.pdf_url),
            "is_open_access": bool(ref.is_open_access),
            "pdf_url": ref.pdf_url,
            "status": ref.status,
            "pdf_ingested": ref.status in ("ingested", "analyzed"),
        }

        # Include analysis fields if the PDF was ingested
        if ref.status in ("ingested", "analyzed"):
            result["analysis"] = {
                "summary": ref.summary,
                "key_findings": ref.key_findings,
                "methodology": ref.methodology,
                "limitations": ref.limitations,
                "relevance_score": ref.relevance_score,
            }

            # Try to get page count from the linked document
            if ref.document_id:
                doc = self.db.query(Document).filter(Document.id == ref.document_id).first()
                if doc:
                    result["page_count"] = doc.page_count if hasattr(doc, 'page_count') else None
                    # Could also include word count or other metadata if available

        return result

    def _tool_analyze_reference(self, ctx: Dict[str, Any], reference_id: str) -> Dict:
        """Re-analyze a reference to generate summary, key_findings, methodology, limitations."""
        from app.models import ProjectReference, Reference
        from app.models.document_chunk import DocumentChunk

        project = ctx["project"]

        # Find the reference in the project library
        ref = self.db.query(Reference).join(
            ProjectReference,
            ProjectReference.reference_id == Reference.id
        ).filter(
            ProjectReference.project_id == project.id,
            Reference.id == reference_id
        ).first()

        if not ref:
            return {"error": f"Reference not found in project library (ID: {reference_id})"}

        if not ref.document_id:
            return {"error": "This reference doesn't have an ingested PDF. Cannot analyze without PDF content."}

        # Build profile text from chunks
        chunks = self.db.query(DocumentChunk).filter(
            DocumentChunk.document_id == ref.document_id
        ).order_by(DocumentChunk.chunk_index).limit(8).all()

        if not chunks:
            return {"error": "No text content found for this reference's PDF."}

        profile_text = '\n'.join([c.chunk_text for c in chunks if c.chunk_text])

        if not profile_text:
            return {"error": "Extracted text is empty for this reference."}

        # Run AI analysis using the OpenRouter utility client
        client, model = self._get_utility_client()
        if not client:
            return {"error": "No AI client available for analysis."}

        prompt = f"""Analyze this academic paper and provide a JSON response with the following fields:
- summary: A 2-3 sentence summary of the paper
- key_findings: An array of 3-5 key findings
- methodology: A 1-2 sentence description of the methodology
- limitations: An array of 2-3 limitations

Title: {ref.title or ''}

Text:
{profile_text[:6000]}

Respond ONLY with valid JSON, no markdown or explanation."""

        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.3
            )
            content = resp.choices[0].message.content or ''

            # Strip markdown code blocks if present
            import json
            import re
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if json_match:
                content = json_match.group(1)

            data = json.loads(content)
            ref.summary = data.get('summary')
            ref.key_findings = data.get('key_findings')
            ref.methodology = data.get('methodology')
            ref.limitations = data.get('limitations')
            ref.status = 'analyzed'
            self.db.commit()

            return {
                "status": "success",
                "message": f"Successfully analyzed '{ref.title}'",
                "analysis": {
                    "summary": ref.summary,
                    "key_findings": ref.key_findings,
                    "methodology": ref.methodology,
                    "limitations": ref.limitations,
                }
            }
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse AI response: {e}"}
        except Exception as e:
            logger.exception(f"Error analyzing reference {reference_id}")
            return {"error": f"Analysis failed: {str(e)}"}

    def _tool_search_papers(
        self,
        ctx: Dict[str, Any],
        query: str,
        count: int = 5,
        open_access_only: bool = False,
        limit: Optional[int] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
    ) -> Dict:
        """Search for papers online and return results directly."""
        from uuid import uuid4
        from app.services.paper_discovery_service import PaperDiscoveryService
        from app.models import Reference, ProjectReference

        effective_limit = limit if limit is not None else count
        effective_limit = max(1, min(int(effective_limit or 5), 20))

        oa_note = " (Open Access only)" if open_access_only else ""
        year_note = ""
        if year_from is not None or year_to is not None:
            if year_from is not None and year_to is not None:
                year_note = f" ({year_from}-{year_to})"
            elif year_from is not None:
                year_note = f" (since {year_from})"
            else:
                year_note = f" (up to {year_to})"
        project = ctx.get("project")
        search_id = str(uuid4())
        ctx["last_search_id"] = search_id

        # Build lightweight lookup for existing library references (just DOIs and titles)
        library_dois = set()
        library_titles = set()
        if project:
            refs = self.db.query(Reference.doi, Reference.title).join(
                ProjectReference, ProjectReference.reference_id == Reference.id
            ).filter(ProjectReference.project_id == project.id).all()
            for doi, title in refs:
                if doi:
                    library_dois.add(doi.lower().replace("https://doi.org/", "").strip())
                if title:
                    library_titles.add(title.lower().strip())

        try:
            sources = ["arxiv", "semantic_scholar", "openalex", "crossref", "pubmed", "europe_pmc"]
            max_results = effective_limit

            # Request more to account for filtering (open access + library duplicates)
            search_max = max_results * 3

            async def _run_search():
                discovery_service = PaperDiscoveryService()
                try:
                    return await discovery_service.discover_papers(
                        query=query,
                        max_results=search_max,
                        sources=sources,
                        fast_mode=True,
                        year_from=year_from,
                        year_to=year_to,
                        open_access_only=open_access_only,
                    )
                finally:
                    await discovery_service.close()

            # Run async search
            result = self._run_async_operation(_run_search)

            # Filter for open access if requested
            source_papers = result.papers
            if open_access_only:
                source_papers = [p for p in source_papers if p.pdf_url or p.open_access_url]

            # Format results - filter out papers already in library
            papers = []
            skipped_library = 0
            for idx, p in enumerate(source_papers):
                # Check if paper is already in library
                if p.doi and p.doi.lower().replace("https://doi.org/", "").strip() in library_dois:
                    skipped_library += 1
                    continue
                if p.title and p.title.lower().strip() in library_titles:
                    skipped_library += 1
                    continue

                # Stop once we have enough new papers
                if len(papers) >= max_results:
                    break
                # Convert authors to array format (frontend expects string[])
                authors_list = []
                if p.authors:
                    if isinstance(p.authors, list):
                        authors_list = [str(a) for a in p.authors]
                    elif isinstance(p.authors, str):
                        # Split string by comma or "and"
                        authors_list = [a.strip() for a in p.authors.replace(" and ", ", ").split(",") if a.strip()]
                    else:
                        authors_list = [str(p.authors)]

                papers.append({
                    "id": p.doi or p.url or f"paper-{idx}",  # Frontend needs an id
                    "title": p.title,
                    "authors": authors_list,  # Array, not string
                    "year": p.year,
                    "abstract": p.abstract,
                    "doi": p.doi,
                    "url": p.url or p.pdf_url,
                    "pdf_url": p.pdf_url,
                    "source": p.source,
                    "is_open_access": getattr(p, 'is_open_access', False),
                    "journal": getattr(p, 'journal', None) or getattr(p, 'venue', None),
                })

            # Cache search results server-side (M2 security fix)
            # This prevents clients from injecting malicious search results
            from app.services.discussion_ai.search_cache import store_search_results
            store_search_results(search_id, papers)

            # Return as action so frontend displays notification with Add buttons
            return {
                "status": "success",
                "message": f"Found {len(papers)} papers for: '{query}'{oa_note}{year_note}"
                    + (f" ({skipped_library} already in your library)" if skipped_library else ""),
                "action": {
                    "type": "search_results",  # Frontend will display as notification
                    "payload": {
                        "query": query,
                        "year_from": year_from,
                        "year_to": year_to,
                        "open_access_only": open_access_only,
                        "limit": max_results,
                        "papers": papers,
                        "total_found": len(result.papers),
                        "search_id": search_id,
                    },
                },
            }

        except Exception as e:
            logger.exception(f"Error searching papers: {e}")
            return {
                "status": "error",
                "message": f"Search failed: {str(e)}",
                "papers": [],
            }

    def _tool_get_project_papers(self, ctx: Dict[str, Any], include_content: bool = False) -> Dict:
        """Get user's draft papers in the project."""
        from app.models import ResearchPaper

        project = ctx["project"]

        papers = self.db.query(ResearchPaper).filter(
            ResearchPaper.project_id == project.id
        ).limit(200).all()

        result = {
            "count": len(papers),
            "papers": []
        }

        for paper in papers:
            paper_info = {
                "id": str(paper.id),
                "title": paper.title,
                "status": paper.status,
                "paper_type": paper.paper_type,
                "abstract": paper.abstract,
            }

            if include_content:
                # Get content from either plain content or LaTeX mode
                content = paper.content
                if not content and paper.content_json:
                    # LaTeX mode papers store content in content_json.latex_source
                    content = paper.content_json.get("latex_source", "")

                if content:
                    # Convert LaTeX to readable markdown for chat display
                    display_content = self._latex_to_markdown(content)
                    paper_info["content"] = display_content  # No truncation - show full content

            result["papers"].append(paper_info)

        return result

    def _tool_get_project_info(self, ctx: Dict[str, Any]) -> Dict:
        """Get project information."""
        project = ctx["project"]

        return {
            "id": str(project.id),
            "title": project.title,
            "idea": project.idea or "",
            "scope": project.scope or "",
            "keywords": project.keywords or [],
            "status": project.status or "active",
        }

    def _tool_get_channel_resources(self, ctx: Dict[str, Any]) -> Dict:
        """Get resources attached to the current channel."""
        from app.models import ProjectDiscussionChannelResource

        channel = ctx["channel"]

        resources = self.db.query(ProjectDiscussionChannelResource).filter(
            ProjectDiscussionChannelResource.channel_id == channel.id
        ).limit(500).all()

        return {
            "count": len(resources),
            "resources": [
                {
                    "id": str(res.id),
                    "type": res.resource_type.value if hasattr(res.resource_type, 'value') else str(res.resource_type),
                    "details": res.details or {},
                }
                for res in resources
            ]
        }

    def _tool_get_channel_papers(self, ctx: Dict[str, Any]) -> Dict:
        """Get papers that were added to the library through this discussion channel."""
        from app.models import Reference, ProjectReference

        channel = ctx["channel"]
        project = ctx["project"]

        # Query papers added via this channel
        channel_papers = self.db.query(Reference.id, Reference.title, Reference.year, Reference.status, Reference.doi).join(
            ProjectReference, ProjectReference.reference_id == Reference.id
        ).filter(
            ProjectReference.project_id == project.id,
            ProjectReference.added_via_channel_id == channel.id
        ).all()

        papers_list = []
        for ref in channel_papers:
            ft_available = ref.status in ("ingested", "analyzed")
            papers_list.append({
                "reference_id": str(ref.id),
                "title": ref.title or "Untitled",
                "year": ref.year,
                "doi": ref.doi,
                "full_text_available": ft_available,
            })

        return {
            "count": len(channel_papers),
            "papers": papers_list,
            "message": f"{len(channel_papers)} paper(s) were added to the library through this channel."
        }

    def _tool_discover_topics(self, area: str) -> Dict:
        """Use web search to discover specific topics in a broad area."""
        client, model = self._get_utility_client()
        if not client:
            return {
                "status": "error",
                "message": "AI service not configured for topic discovery.",
                "topics": [],
            }

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a research assistant for researchers and scholars. Search the web and identify 4-6 specific, "
                            "concrete topics/algorithms/methods in the given area. "
                            "Return ONLY a JSON array of objects with 'topic' (short name) and "
                            "'query' (concise, high-signal academic search query). "
                            "Avoid keyword stuffing and raw year lists unless a timeframe is explicitly requested. "
                            "Example:\n"
                            '[{"topic": "Mixture of Experts", "query": "mixture of experts transformer routing efficiency"}, '
                            '{"topic": "Mamba", "query": "mamba state space models sequence modeling"}]'
                        )
                    },
                    {
                        "role": "user",
                        "content": f"What are the most important specific topics/algorithms/methods in: {area}?"
                    }
                ],
                temperature=0.3,
            )

            content = response.choices[0].message.content or "[]"

            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                topics = json.loads(json_match.group())
            else:
                topics = []

            return {
                "status": "success",
                "message": f"Discovered {len(topics)} topics in '{area}'",
                "area": area,
                "topics": topics,
            }

        except Exception as e:
            logger.exception(f"Error discovering topics for area '{area}'")
            return {
                "status": "error",
                "message": f"Failed to discover topics: {str(e)}",
                "topics": [],
            }

    def _tool_batch_search_papers(self, ctx: Dict[str, Any], topics: List) -> Dict:
        """Search for papers on multiple topics at once (server-side execution)."""
        import asyncio
        from uuid import uuid4
        from app.services.paper_discovery_service import PaperDiscoveryService
        from app.models import Reference, ProjectReference
        from app.services.discussion_ai.search_cache import store_search_results

        logger.info(f"batch_search_papers called with topics: {topics}")

        if not topics:
            return {
                "status": "error",
                "message": "No topics provided for batch search.",
            }

        # Handle case where topics might be a JSON string
        if isinstance(topics, str):
            try:
                topics = json.loads(topics)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse topics as JSON: {e}")
                return {
                    "status": "error",
                    "message": "Invalid topics format - expected list of topic objects.",
                }

        if not isinstance(topics, list):
            return {
                "status": "error",
                "message": "Invalid topics format - expected list of topic objects.",
            }

        # Parse and validate topics (limit to 5)
        formatted_topics = []
        for idx, t in enumerate(topics[:5]):
            try:
                if isinstance(t, str):
                    try:
                        t = json.loads(t)
                    except json.JSONDecodeError:
                        continue

                if not isinstance(t, dict):
                    continue

                topic_name = t.get("topic") or t.get('"topic"') or "Unknown"
                query = t.get("query") or t.get('"query"') or str(topic_name)
                max_results = t.get("max_results", 5)

                topic_name = str(topic_name).strip('"').strip("'")
                query = str(query).strip('"').strip("'")

                if isinstance(max_results, str):
                    max_results = int(max_results) if max_results.isdigit() else 5
                elif not isinstance(max_results, int):
                    max_results = 5

                # Cap per-topic results at 5
                max_results = min(max_results, 5)

                formatted_topics.append({
                    "topic": topic_name,
                    "query": query,
                    "max_results": max_results,
                })

            except Exception as e:
                logger.exception(f"Error processing topic {idx}: {e}")
                continue

        if not formatted_topics:
            return {
                "status": "error",
                "message": "Could not parse any valid topics from the request.",
            }

        # Build library lookup for deduplication (same as _tool_search_papers)
        project = ctx.get("project")
        library_dois: set = set()
        library_titles: set = set()
        if project:
            refs = self.db.query(Reference.doi, Reference.title).join(
                ProjectReference, ProjectReference.reference_id == Reference.id
            ).filter(ProjectReference.project_id == project.id).all()
            for doi, title in refs:
                if doi:
                    library_dois.add(doi.lower().replace("https://doi.org/", "").strip())
                if title:
                    library_titles.add(title.lower().strip())

        # Execute searches concurrently across all topics
        async def _search_topic(topic_info: Dict) -> Dict:
            """Search a single topic and return results with metadata."""
            topic_name = topic_info["topic"]
            query = topic_info["query"]
            max_res = topic_info["max_results"]
            discovery_service = PaperDiscoveryService()
            try:
                result = await discovery_service.discover_papers(
                    query=query,
                    max_results=max_res * 3,  # Request more to account for filtering
                    fast_mode=True,
                )
                return {
                    "topic": topic_name,
                    "query": query,
                    "max_results": max_res,
                    "papers": result.papers,
                    "error": None,
                }
            except Exception as e:
                logger.error(f"Search failed for topic '{topic_name}': {e}")
                return {
                    "topic": topic_name,
                    "query": query,
                    "max_results": max_res,
                    "papers": [],
                    "error": str(e),
                }
            finally:
                await discovery_service.close()

        async def _run_all_searches():
            return await asyncio.gather(*[
                _search_topic(t) for t in formatted_topics
            ])

        topic_search_results = self._run_async_operation(_run_all_searches)

        # Process results: deduplicate across topics and filter library duplicates
        seen_keys: set = set()
        all_papers: list = []
        topic_summaries: list = []
        total_max = 25  # Overall cap

        for topic_result in topic_search_results:
            topic_name = topic_result["topic"]
            max_res = topic_result["max_results"]
            topic_papers: list = []

            if topic_result["error"]:
                topic_summaries.append({
                    "topic": topic_name,
                    "count": 0,
                    "error": topic_result["error"],
                })
                continue

            for p in topic_result["papers"]:
                if len(all_papers) >= total_max:
                    break
                if len(topic_papers) >= max_res:
                    break

                # Cross-topic dedup using unique key
                unique_key = p.get_unique_key() if hasattr(p, 'get_unique_key') else (p.doi or p.title or "")
                if unique_key in seen_keys:
                    continue
                seen_keys.add(unique_key)

                # Library dedup
                if p.doi and p.doi.lower().replace("https://doi.org/", "").strip() in library_dois:
                    continue
                if p.title and p.title.lower().strip() in library_titles:
                    continue

                # Format paper (same as _tool_search_papers)
                authors_list = []
                if p.authors:
                    if isinstance(p.authors, list):
                        authors_list = [str(a) for a in p.authors]
                    elif isinstance(p.authors, str):
                        authors_list = [a.strip() for a in p.authors.replace(" and ", ", ").split(",") if a.strip()]
                    else:
                        authors_list = [str(p.authors)]

                paper_dict = {
                    "id": p.doi or p.url or f"paper-{len(all_papers)}",
                    "title": p.title,
                    "authors": authors_list,
                    "year": p.year,
                    "abstract": p.abstract,
                    "doi": p.doi,
                    "url": p.url or p.pdf_url,
                    "pdf_url": p.pdf_url,
                    "source": p.source,
                    "is_open_access": getattr(p, 'is_open_access', False),
                    "journal": getattr(p, 'journal', None) or getattr(p, 'venue', None),
                    "topic": topic_name,
                }
                all_papers.append(paper_dict)
                topic_papers.append(paper_dict)

            topic_summaries.append({
                "topic": topic_name,
                "count": len(topic_papers),
            })

        if not all_papers:
            error_topics = [ts for ts in topic_summaries if ts.get("error")]
            if error_topics:
                return {
                    "status": "error",
                    "message": f"All {len(formatted_topics)} topic searches failed. Errors: "
                        + "; ".join(f"{t['topic']}: {t['error']}" for t in error_topics),
                }
            return {
                "status": "success",
                "message": f"No new papers found across {len(formatted_topics)} topics (they may already be in your library).",
            }

        # Cache results in Redis
        search_id = str(uuid4())
        ctx["last_search_id"] = search_id
        store_search_results(search_id, all_papers)

        # Build summary message
        topic_summary_str = ", ".join(
            f"{ts['topic']}: {ts['count']}" + (f" (error: {ts['error'][:30]})" if ts.get('error') else "")
            for ts in topic_summaries
        )

        return {
            "status": "success",
            "message": f"Found {len(all_papers)} papers across {len(formatted_topics)} topics ({topic_summary_str})",
            "topic_results": topic_summaries,
            "action": {
                "type": "search_results",
                "payload": {
                    "query": f"Batch search: {', '.join(t['topic'] for t in formatted_topics)}",
                    "papers": all_papers,
                    "total_found": len(all_papers),
                    "search_id": search_id,
                },
            },
        }

    def _tool_get_related_papers(
        self,
        ctx: Dict[str, Any],
        paper_identifier: str,
        relation_type: str = "similar",
        count: int = 10,
    ) -> Dict:
        """
        Find papers related to a specific paper.

        Prioritizes Semantic Scholar, falls back to OpenAlex.

        Args:
            paper_identifier: DOI, Semantic Scholar ID, OpenAlex ID, or paper title
            relation_type: 'similar' | 'citing' | 'references'
            count: Maximum number of papers to return
        """
        import asyncio
        import aiohttp
        import urllib.parse
        from uuid import uuid4

        logger.info(f"get_related_papers: identifier='{paper_identifier}', type={relation_type}, count={count}")

        # Normalize relation_type
        relation_type = relation_type.lower() if relation_type else "similar"
        if relation_type not in ("similar", "citing", "references"):
            relation_type = "similar"

        count = min(count, 20)  # Cap at 20

        # Helper to extract DOI from various formats
        def extract_doi(identifier: str) -> Optional[str]:
            if "/" in identifier and (
                identifier.startswith("10.") or "doi.org" in identifier.lower()
            ):
                doi = identifier
                if "doi.org/" in doi.lower():
                    doi = doi.split("doi.org/")[-1]
                return doi
            return None

        # Helper to format Semantic Scholar paper
        def format_ss_paper(p: Dict) -> Dict:
            authors = []
            for auth in (p.get("authors") or [])[:5]:
                name = auth.get("name")
                if name:
                    authors.append(name)

            ext_ids = p.get("externalIds") or {}
            doi = ext_ids.get("DOI", "")

            pdf_url = None
            oa_pdf = p.get("openAccessPdf")
            if oa_pdf:
                pdf_url = oa_pdf.get("url")

            return {
                "id": p.get("paperId", ""),
                "title": p.get("title", "Unknown"),
                "authors": authors,
                "year": p.get("year"),
                "abstract": (p.get("abstract") or "")[:500],
                "doi": doi,
                "url": p.get("url") or (f"https://doi.org/{doi}" if doi else ""),
                "pdf_url": pdf_url,
                "source": "semantic_scholar",
                "is_open_access": p.get("isOpenAccess", False),
                "journal": p.get("venue") or p.get("journal", {}).get("name") if p.get("journal") else None,
                "citations": p.get("citationCount", 0),
            }

        # Helper to format OpenAlex paper
        def format_oa_paper(p: Dict) -> Dict:
            authors = []
            for auth in p.get("authorships", [])[:5]:
                author_name = auth.get("author", {}).get("display_name")
                if author_name:
                    authors.append(author_name)

            doi = p.get("doi", "")
            if doi and doi.startswith("https://doi.org/"):
                doi = doi.replace("https://doi.org/", "")

            pdf_url = None
            oa_info = p.get("open_access", {})
            if oa_info.get("is_oa"):
                pdf_url = oa_info.get("oa_url")

            venue = None
            primary_location = p.get("primary_location", {})
            if primary_location:
                source = primary_location.get("source", {})
                if source:
                    venue = source.get("display_name")

            return {
                "id": p.get("id", "").split("/")[-1],
                "title": p.get("title", "Unknown"),
                "authors": authors,
                "year": p.get("publication_year"),
                "abstract": (p.get("abstract") or "")[:500],
                "doi": doi,
                "url": p.get("doi") or p.get("id"),
                "pdf_url": pdf_url,
                "source": "openalex",
                "is_open_access": oa_info.get("is_oa", False),
                "journal": venue,
                "citations": p.get("cited_by_count", 0),
            }

        async def try_semantic_scholar(session: aiohttp.ClientSession) -> Optional[Dict]:
            """Try Semantic Scholar API. Returns None if failed/rate-limited."""
            SS_FIELDS = "paperId,title,year,authors,venue,url,externalIds,abstract,citationCount,isOpenAccess,openAccessPdf,journal"
            headers = {"User-Agent": "ScholarHub/1.0"}

            # Step 1: Resolve paper identifier to Semantic Scholar paper ID
            ss_paper_id = None
            source_title = paper_identifier

            # Check if it looks like a Semantic Scholar ID (40-char hex)
            if len(paper_identifier) == 40 and all(c in "0123456789abcdef" for c in paper_identifier.lower()):
                ss_paper_id = paper_identifier
            else:
                # Try DOI lookup first
                doi = extract_doi(paper_identifier)
                if doi:
                    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields={SS_FIELDS}"
                    try:
                        async with session.get(url, headers=headers, timeout=10) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                ss_paper_id = data.get("paperId")
                                source_title = data.get("title", paper_identifier)
                            elif resp.status == 429:
                                logger.warning("Semantic Scholar rate limited on DOI lookup")
                                return None
                    except Exception as e:
                        logger.warning(f"SS DOI lookup failed: {e}")

                # If DOI lookup failed, try title search
                if not ss_paper_id:
                    encoded_query = urllib.parse.quote(paper_identifier)
                    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={encoded_query}&limit=1&fields={SS_FIELDS}"
                    try:
                        async with session.get(url, headers=headers, timeout=10) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                results = data.get("data", [])
                                if results:
                                    ss_paper_id = results[0].get("paperId")
                                    source_title = results[0].get("title", paper_identifier)
                            elif resp.status == 429:
                                logger.warning("Semantic Scholar rate limited on title search")
                                return None
                    except Exception as e:
                        logger.warning(f"SS title search failed: {e}")

            if not ss_paper_id:
                return None

            # Step 2: Fetch related papers based on relation_type
            papers = []

            if relation_type == "similar":
                # Use recommendations API for similar papers
                url = f"https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{ss_paper_id}?limit={count}&fields={SS_FIELDS}"
                try:
                    async with session.get(url, headers=headers, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            papers = data.get("recommendedPapers", [])[:count]
                        elif resp.status == 429:
                            logger.warning("Semantic Scholar rate limited on recommendations")
                            return None
                except Exception as e:
                    logger.warning(f"SS recommendations failed: {e}")

            elif relation_type == "citing":
                # Papers that cite this work
                url = f"https://api.semanticscholar.org/graph/v1/paper/{ss_paper_id}/citations?limit={count}&fields={SS_FIELDS}"
                try:
                    async with session.get(url, headers=headers, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            # Citations API returns {"citingPaper": {...}}
                            papers = [item.get("citingPaper", {}) for item in data.get("data", [])][:count]
                        elif resp.status == 429:
                            logger.warning("Semantic Scholar rate limited on citations")
                            return None
                except Exception as e:
                    logger.warning(f"SS citations failed: {e}")

            elif relation_type == "references":
                # Papers this work cites
                url = f"https://api.semanticscholar.org/graph/v1/paper/{ss_paper_id}/references?limit={count}&fields={SS_FIELDS}"
                try:
                    async with session.get(url, headers=headers, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            # References API returns {"citedPaper": {...}}
                            papers = [item.get("citedPaper", {}) for item in data.get("data", [])][:count]
                        elif resp.status == 429:
                            logger.warning("Semantic Scholar rate limited on references")
                            return None
                except Exception as e:
                    logger.warning(f"SS references failed: {e}")

            if not papers:
                return None

            return {
                "source": "semantic_scholar",
                "source_title": source_title,
                "papers": [format_ss_paper(p) for p in papers if p],
            }

        async def try_openalex(session: aiohttp.ClientSession) -> Optional[Dict]:
            """Fall back to OpenAlex API."""
            work_id = None
            work_data = None

            # Check if it's already an OpenAlex ID
            if paper_identifier.upper().startswith("W") and paper_identifier[1:].isdigit():
                work_id = paper_identifier.upper()
            elif paper_identifier.startswith("https://openalex.org/"):
                work_id = paper_identifier.split("/")[-1].upper()
            else:
                # Try DOI lookup or title search
                doi = extract_doi(paper_identifier)
                if doi:
                    encoded_doi = urllib.parse.quote(f"https://doi.org/{doi}", safe="")
                    url = f"https://api.openalex.org/works?filter=doi:{encoded_doi}&per_page=1"
                else:
                    encoded_query = urllib.parse.quote(paper_identifier, safe="")
                    url = f"https://api.openalex.org/works?filter=title.search:{encoded_query}&per_page=1"

                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            results = data.get("results", [])
                            if results:
                                work_id = results[0]["id"].split("/")[-1]
                                work_data = results[0]
                except Exception as e:
                    logger.warning(f"OpenAlex lookup failed: {e}")

            if not work_id:
                return None

            # Fetch work data if needed
            if not work_data:
                try:
                    async with session.get(f"https://api.openalex.org/works/{work_id}", timeout=10) as resp:
                        if resp.status == 200:
                            work_data = await resp.json()
                except Exception as e:
                    logger.warning(f"OpenAlex work fetch failed: {e}")

            if not work_data:
                return None

            source_title = work_data.get("title", paper_identifier)
            papers = []

            if relation_type == "similar":
                related_ids = work_data.get("related_works", [])[:count * 2]
                if related_ids:
                    ids_filter = "|".join([r.split("/")[-1] for r in related_ids[:count * 2]])
                    url = f"https://api.openalex.org/works?filter=openalex_id:{ids_filter}&per_page={count}"
                    try:
                        async with session.get(url, timeout=15) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                papers = data.get("results", [])[:count]
                    except Exception as e:
                        logger.warning(f"OpenAlex related works failed: {e}")

            elif relation_type == "citing":
                url = f"https://api.openalex.org/works?filter=cites:{work_id}&sort=cited_by_count:desc&per_page={count}"
                try:
                    async with session.get(url, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            papers = data.get("results", [])[:count]
                except Exception as e:
                    logger.warning(f"OpenAlex citing papers failed: {e}")

            elif relation_type == "references":
                ref_ids = work_data.get("referenced_works", [])[:count * 2]
                if ref_ids:
                    ids_filter = "|".join([r.split("/")[-1] for r in ref_ids[:count * 2]])
                    url = f"https://api.openalex.org/works?filter=openalex_id:{ids_filter}&per_page={count}"
                    try:
                        async with session.get(url, timeout=15) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                papers = data.get("results", [])[:count]
                    except Exception as e:
                        logger.warning(f"OpenAlex references failed: {e}")

            if not papers:
                return None

            return {
                "source": "openalex",
                "source_title": source_title,
                "papers": [format_oa_paper(p) for p in papers],
            }

        async def fetch_related() -> Dict:
            async with aiohttp.ClientSession() as session:
                # Try Semantic Scholar first
                result = await try_semantic_scholar(session)
                if result and result.get("papers"):
                    logger.info(f"get_related_papers: using Semantic Scholar ({len(result['papers'])} papers)")
                    return result

                # Fall back to OpenAlex
                logger.info("get_related_papers: falling back to OpenAlex")
                result = await try_openalex(session)
                if result and result.get("papers"):
                    logger.info(f"get_related_papers: using OpenAlex ({len(result['papers'])} papers)")
                    return result

                return {"source": None, "source_title": paper_identifier, "papers": []}

        # Run async function
        result = self._run_async_operation(fetch_related)

        papers_data = result.get("papers", [])
        source_title = result.get("source_title", paper_identifier)
        api_source = result.get("source", "unknown")

        if not papers_data:
            relation_desc = {
                "similar": "similar papers",
                "citing": "papers citing this work",
                "references": "references cited by this paper",
            }.get(relation_type, "related papers")
            return {
                "status": "success",
                "message": f"No {relation_desc} found for '{source_title[:60]}...'",
                "papers": [],
            }

        # Cache results for potential add_to_library
        search_id = str(uuid4())
        ctx["last_search_id"] = search_id
        from app.services.discussion_ai.search_cache import store_search_results
        store_search_results(search_id, papers_data)
        ctx["recent_search_results"] = papers_data

        relation_desc = {
            "similar": "similar to",
            "citing": "citing",
            "references": "cited by",
        }.get(relation_type, "related to")

        return {
            "status": "success",
            "message": f"Found {len(papers_data)} papers {relation_desc} '{source_title[:50]}...' (via {api_source})",
            "action": {
                "type": "search_results",
                "payload": {
                    "query": f"{relation_type} papers for: {source_title[:50]}",
                    "papers": papers_data,
                    "search_id": search_id,
                    "total_found": len(papers_data),
                },
            },
        }

    def _tool_semantic_search_library(
        self,
        ctx: Dict[str, Any],
        query: str,
        count: int = 10,
        similarity_threshold: float = 0.5,
    ) -> Dict:
        """
        Search the project library using semantic similarity.

        Uses embeddings to find papers that match the query conceptually,
        not just by keyword overlap.
        """
        from app.models import ProjectReference, Reference, PaperEmbedding

        project = ctx["project"]

        # Check if we have any embeddings for this project's papers
        embeddings_count = (
            self.db.query(PaperEmbedding)
            .join(ProjectReference, PaperEmbedding.project_reference_id == ProjectReference.id)
            .filter(ProjectReference.project_id == project.id)
            .count()
        )

        if embeddings_count == 0:
            # Check how many papers are in the library
            library_count = (
                self.db.query(ProjectReference)
                .filter(ProjectReference.project_id == project.id)
                .count()
            )

            if library_count == 0:
                return {
                    "status": "empty_library",
                    "message": "Your project library is empty. Add papers using 'search_papers' and 'add_to_library' first.",
                    "papers": [],
                }
            else:
                return {
                    "status": "no_embeddings",
                    "message": f"Semantic search is not yet available for your library ({library_count} papers). Embeddings are being generated. Try 'get_project_references' for keyword search instead.",
                    "papers": [],
                }

        # Get embedding service and embed the query
        try:
            from app.services.embedding_service import get_embedding_service

            embedding_service = get_embedding_service()

            # Run async embedding in sync context (safe even under running loop)
            query_embedding = self._run_async_operation(
                lambda: embedding_service.embed(query)
            )

        except Exception as e:
            logger.error(f"[SemanticSearch] Failed to embed query: {e}")
            return {
                "status": "error",
                "message": "Failed to process query for semantic search. Try 'get_project_references' for keyword search instead.",
                "papers": [],
            }

        # Query pgvector for similar papers
        # Note: This requires raw SQL for the vector similarity operator
        from sqlalchemy import text

        # pgvector cosine distance: 1 - (embedding <=> query_embedding) = similarity
        sql = text("""
            SELECT
                pe.project_reference_id,
                r.title,
                r.authors,
                r.year,
                r.doi,
                r.abstract,
                r.journal,
                r.pdf_url,
                r.is_open_access,
                1 - (pe.embedding <=> :query_embedding) as similarity
            FROM paper_embeddings pe
            JOIN project_references pr ON pe.project_reference_id = pr.id
            JOIN "references" r ON pr.reference_id = r.id
            WHERE pr.project_id = :project_id
                AND 1 - (pe.embedding <=> :query_embedding) > :threshold
            ORDER BY pe.embedding <=> :query_embedding
            LIMIT :limit
        """)

        try:
            # Convert embedding to pgvector format
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            result = self.db.execute(
                sql,
                {
                    "query_embedding": embedding_str,
                    "project_id": str(project.id),
                    "threshold": similarity_threshold,
                    "limit": count,
                }
            )
            rows = result.fetchall()

        except Exception as e:
            logger.error(f"[SemanticSearch] Vector query failed: {e}")
            return {
                "status": "error",
                "message": f"Semantic search query failed. Try 'get_project_references' for keyword search instead.",
                "papers": [],
            }

        if not rows:
            return {
                "status": "no_matches",
                "message": f"No papers in your library match '{query}' semantically (threshold: {similarity_threshold}). Try lowering the threshold or use different terms.",
                "papers": [],
            }

        # Format results
        papers = []
        for row in rows:
            # Handle both tuple and row object access
            if hasattr(row, "_mapping"):
                # SQLAlchemy 2.0 Row object
                r = row._mapping
            else:
                # Named tuple or similar
                r = row._asdict() if hasattr(row, "_asdict") else {
                    "project_reference_id": row[0],
                    "title": row[1],
                    "authors": row[2],
                    "year": row[3],
                    "doi": row[4],
                    "abstract": row[5],
                    "journal": row[6],
                    "pdf_url": row[7],
                    "is_open_access": row[8],
                    "similarity": row[9],
                }

            # Format authors
            authors = r.get("authors", [])
            if isinstance(authors, list):
                authors_str = ", ".join(authors[:3])
                if len(authors) > 3:
                    authors_str += " et al."
            else:
                authors_str = str(authors) if authors else "Unknown"

            paper = {
                "reference_id": str(r.get("project_reference_id", "")),
                "title": r.get("title", ""),
                "authors": authors_str,
                "year": r.get("year"),
                "doi": r.get("doi"),
                "journal": r.get("journal"),
                "has_pdf": bool(r.get("pdf_url")),
                "is_open_access": r.get("is_open_access", False),
                "similarity_score": round(float(r.get("similarity", 0)), 3),
                "abstract": (r.get("abstract") or "")[:300] + "..." if r.get("abstract") and len(r.get("abstract", "")) > 300 else r.get("abstract", ""),
            }
            papers.append(paper)

        return {
            "status": "success",
            "message": f"Found {len(papers)} papers in your library matching '{query}'",
            "query": query,
            "similarity_threshold": similarity_threshold,
            "papers": papers,
        }
