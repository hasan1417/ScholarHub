"""
Library and paper management tools mixin for the Discussion AI orchestrator.

Handles paper creation, updates, artifact generation, citation management,
bibliography generation, and library additions.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from app.services.discussion_ai.utils import (
    _escape_latex,
    _normalize_title,
    _normalize_author,
    _CITE_PATTERN,
    AVAILABLE_TEMPLATES,
)

if TYPE_CHECKING:
    from app.models import Project

logger = logging.getLogger(__name__)


class LibraryToolsMixin:
    """Mixin providing library and paper management tools.

    Expects the composed class to provide:
        - self.ai_service: AIService
        - self.db: Session
        - self._get_ai_memory(channel) -> Dict
        - self._save_ai_memory(channel, memory) -> None
    """

    def _latex_to_markdown(self, latex: str) -> str:
        """Convert LaTeX content to readable markdown for chat display."""
        import re

        # Remove document class and preamble
        content = re.sub(r'\\documentclass\{[^}]*\}', '', latex)
        content = re.sub(r'\\usepackage(\[[^\]]*\])?\{[^}]*\}', '', content)
        content = re.sub(r'\\title\{([^}]*)\}', r'# \1', content)
        content = re.sub(r'\\date\{[^}]*\}', '', content)
        content = re.sub(r'\\begin\{document\}', '', content)
        content = re.sub(r'\\end\{document\}', '', content)
        content = re.sub(r'\\maketitle', '', content)

        # Convert sections to markdown headers
        content = re.sub(r'\\section\{([^}]*)\}', r'\n## \1\n', content)
        content = re.sub(r'\\subsection\{([^}]*)\}', r'\n### \1\n', content)
        content = re.sub(r'\\subsubsection\{([^}]*)\}', r'\n#### \1\n', content)
        content = re.sub(r'\\paragraph\{([^}]*)\}', r'\n**\1**\n', content)

        # Convert abstract
        content = re.sub(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', r'\n**Abstract:** \1\n', content, flags=re.DOTALL)

        # Convert text formatting
        content = re.sub(r'\\textbf\{([^}]*)\}', r'**\1**', content)
        content = re.sub(r'\\textit\{([^}]*)\}', r'*\1*', content)
        content = re.sub(r'\\emph\{([^}]*)\}', r'*\1*', content)
        content = re.sub(r'\\underline\{([^}]*)\}', r'__\1__', content)

        # Convert lists
        content = re.sub(r'\\begin\{itemize\}', '', content)
        content = re.sub(r'\\end\{itemize\}', '', content)
        content = re.sub(r'\\begin\{enumerate\}', '', content)
        content = re.sub(r'\\end\{enumerate\}', '', content)
        content = re.sub(r'\\item\s*', '\n- ', content)

        # Convert citations and references
        content = re.sub(r'\\cite\{([^}]*)\}', r'[\1]', content)
        content = re.sub(r'\\ref\{([^}]*)\}', r'[\1]', content)
        content = re.sub(r'\\label\{[^}]*\}', '', content)

        # Clean up extra whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = content.strip()

        return content

    def _link_cited_references(
        self,
        ctx: Dict[str, Any],
        paper_id: str,
        latex_content: str,
    ) -> Dict[str, Any]:
        r"""
        Parse citations from LaTeX content and link matching references to the paper.

        1. Extract \cite{} keys from content
        2. Match keys to recent_search_results AND project library references
        3. Create Reference entries (if not exist)
        4. Add to project library (ProjectReference)
        5. Link to paper (PaperReference)

        Returns summary of linked references.
        """
        import re
        from uuid import UUID
        from app.models import Reference, ProjectReference, PaperReference, ProjectReferenceStatus, ProjectReferenceOrigin

        project = ctx["project"]
        recent_search_results = self._get_recent_papers(ctx)

        # Also get references from the project library
        project_refs = (
            self.db.query(Reference)
            .join(ProjectReference, ProjectReference.reference_id == Reference.id)
            .filter(ProjectReference.project_id == project.id)
            .limit(1000)
            .all()
        )

        # Convert project library refs to same format as search results
        library_papers = []
        for ref in project_refs:
            library_papers.append({
                "title": ref.title,
                "authors": ref.authors if isinstance(ref.authors, str) else ", ".join(ref.authors or []),
                "year": ref.year,
                "doi": ref.doi,
                "url": ref.url,
                "source": ref.source,
                "journal": ref.journal,
                "abstract": ref.abstract,
                "is_open_access": ref.is_open_access,
                "pdf_url": ref.pdf_url,
                "_reference_id": str(ref.id),  # Track existing ref ID
            })

        # Combine recent search results with project library
        all_papers = recent_search_results + library_papers

        if not all_papers:
            return {"linked": 0, "message": "No references available to match against (no recent search results and no project library references)"}

        # Extract all citation keys from \cite{key1, key2} commands
        cite_matches = _CITE_PATTERN.findall(latex_content)

        # Flatten and clean citation keys
        citation_keys = set()
        for match in cite_matches:
            for key in match.split(','):
                citation_keys.add(key.strip())

        if not citation_keys:
            return {"linked": 0, "message": "No citations found in content"}

        # Create lookup by our generated keys for fast exact matching
        paper_by_key = {}
        used_keys: set = set()
        for paper in all_papers:
            key = self._generate_citation_key(paper, used_keys)
            paper_by_key[key] = paper

        # Match citation keys to papers
        linked_count = 0
        linked_refs = []

        try:
            paper_uuid = UUID(paper_id)
        except ValueError:
            return {"linked": 0, "message": "Invalid paper ID"}

        for cite_key in citation_keys:
            # 1. Try exact match with our generated keys first
            matched_paper = paper_by_key.get(cite_key)

            # 2. Use intelligent fuzzy matching on paper metadata
            if not matched_paper:
                matched_paper = self._match_citation_to_paper(cite_key, all_papers)

            if not matched_paper:
                logger.debug(f"[LinkRefs] Could not match citation key: {cite_key}")
                continue

            # Check if reference already exists
            doi = matched_paper.get("doi")
            title = matched_paper.get("title", "")

            existing_ref = None

            # First check if this came from project library (has _reference_id)
            if matched_paper.get("_reference_id"):
                from uuid import UUID as UUIDType
                try:
                    ref_uuid = UUIDType(matched_paper["_reference_id"])
                    existing_ref = self.db.query(Reference).filter(Reference.id == ref_uuid).first()
                except (ValueError, TypeError):
                    pass

            # Otherwise check by DOI or title
            if not existing_ref and doi:
                existing_ref = self.db.query(Reference).filter(
                    Reference.doi == doi,
                    Reference.owner_id == project.created_by
                ).first()

            if not existing_ref and title:
                existing_ref = self.db.query(Reference).filter(
                    Reference.title == title,
                    Reference.owner_id == project.created_by
                ).first()

            # Create Reference if not exists
            is_new_ref = False
            if not existing_ref:
                is_new_ref = True
                authors = matched_paper.get("authors", [])
                if isinstance(authors, str):
                    authors = [a.strip() for a in authors.split(",")]

                try:
                    existing_ref = Reference(
                        owner_id=project.created_by,
                        title=title,
                        authors=authors,
                        year=matched_paper.get("year"),
                        doi=doi,
                        url=matched_paper.get("url"),
                        source=matched_paper.get("source", "ai_discovery"),
                        journal=matched_paper.get("journal"),
                        abstract=matched_paper.get("abstract"),
                        is_open_access=matched_paper.get("is_open_access", False),
                        pdf_url=matched_paper.get("pdf_url"),
                        status="pending",
                    )
                    self.db.add(existing_ref)
                    self.db.flush()
                except IntegrityError:
                    # Race condition: another request created this reference
                    self.db.rollback()
                    # Re-query to get the existing record
                    if doi:
                        existing_ref = self.db.query(Reference).filter(
                            Reference.doi == doi,
                            Reference.owner_id == project.created_by
                        ).first()
                    if not existing_ref and title:
                        existing_ref = self.db.query(Reference).filter(
                            Reference.title == title,
                            Reference.owner_id == project.created_by
                        ).first()
                    if not existing_ref:
                        # Still can't find it - skip this reference
                        logger.warning(f"[LinkRefs] Failed to create or find reference after IntegrityError: {title}")
                        continue

            # NOTE: PDF ingestion is NOT triggered here to avoid:
            # 1. Slow paper creation (PDF download + embedding is expensive)
            # 2. Database session corruption if ingestion fails
            # Users can ingest PDFs later via the library UI or it happens via background tasks

            # Add to project library if not already there
            existing_project_ref = self.db.query(ProjectReference).filter(
                ProjectReference.project_id == project.id,
                ProjectReference.reference_id == existing_ref.id
            ).first()

            if not existing_project_ref:
                project_ref = ProjectReference(
                    project_id=project.id,
                    reference_id=existing_ref.id,
                    status=ProjectReferenceStatus.APPROVED,
                    origin=ProjectReferenceOrigin.AUTO_DISCOVERY,
                )
                self.db.add(project_ref)

            # Link to paper if not already linked
            existing_paper_ref = self.db.query(PaperReference).filter(
                PaperReference.paper_id == paper_uuid,
                PaperReference.reference_id == existing_ref.id
            ).first()

            if not existing_paper_ref:
                paper_ref = PaperReference(
                    paper_id=paper_uuid,
                    reference_id=existing_ref.id,
                )
                self.db.add(paper_ref)
                linked_count += 1
                linked_refs.append(title)

        self.db.commit()

        return {
            "linked": linked_count,
            "references": linked_refs[:5],  # Return first 5 for summary
            "message": f"Linked {linked_count} references to paper and project library"
        }

    def _tool_create_paper(
        self,
        ctx: Dict[str, Any],
        title: str,
        content: str,
        paper_type: str = "research",
        abstract: str = None,
        template: str = "generic",
    ) -> Dict:
        """Create a new paper in the project (always in LaTeX mode)."""
        from app.services.paper_service import create_paper
        from app.utils.slugify import slugify, generate_short_id

        project = ctx["project"]
        # Use the current user (who prompted the AI) as owner, not project creator
        current_user = ctx.get("current_user")
        owner_id = current_user.id if current_user else project.created_by

        # Generate bibliography entries BEFORE creating the document
        # Initialize unmatched citations tracker
        self._last_unmatched_citations = []
        bibliography_entries = self._generate_bibliography_entries(ctx, content)

        # Check for hallucinated/unverified citations
        unverified_citations = getattr(self, '_last_unmatched_citations', [])

        latex_source = self._ensure_latex_document(content, title, abstract, bibliography_entries, template)

        # Auto-generate keywords from title, abstract, and content
        keywords = self._generate_keywords(title, abstract, content)

        # Generate slug and short_id for URL-friendly paper links
        paper_slug = slugify(title) if title else None
        paper_short_id = generate_short_id()

        # Use centralized paper service for creation + member + snapshot
        new_paper = create_paper(
            db=self.db,
            title=title,
            owner_id=owner_id,
            project_id=project.id,
            content_json={
                "authoring_mode": "latex",
                "latex_source": latex_source,
            },
            abstract=abstract,
            paper_type=paper_type,
            status="draft",
            slug=paper_slug,
            short_id=paper_short_id,
            keywords=keywords,
            snapshot_label="AI-generated initial version",
        )

        # Link cited references to paper and project library
        ref_result = self._link_cited_references(ctx, str(new_paper.id), latex_source)
        ref_message = f" {ref_result['message']}" if ref_result.get("linked", 0) > 0 else ""

        # Build warning message for unverified citations
        unverified_warning = ""
        if unverified_citations:
            unverified_warning = f" Warning: {len(unverified_citations)} citation(s) could not be verified against your library ({', '.join(unverified_citations[:3])}{'...' if len(unverified_citations) > 3 else ''})."

        # Build url_id for frontend navigation
        url_id = f"{new_paper.slug}-{new_paper.short_id}" if new_paper.slug and new_paper.short_id else str(new_paper.id)

        return {
            "status": "success",
            "message": f"Created paper '{title}' in the project.{ref_message}{unverified_warning}",
            # Note: paper_id is in action.payload for frontend use - don't show UUIDs to users
            "references_linked": ref_result.get("linked", 0),
            "unverified_citations": unverified_citations,
            "action": {
                "type": "paper_created",
                "payload": {
                    "paper_id": str(new_paper.id),
                    "url_id": url_id,
                    "title": title,
                    "unverified_citations": unverified_citations,
                }
            }
        }

    def _generate_keywords(self, title: str, abstract: str = None, content: str = None) -> list:
        """Generate keywords from title, abstract, and content."""
        import re

        # Common academic stopwords to filter out
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
            'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that',
            'these', 'those', 'which', 'who', 'whom', 'what', 'when', 'where',
            'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most',
            'other', 'some', 'such', 'no', 'not', 'only', 'own', 'same', 'so',
            'than', 'too', 'very', 'just', 'also', 'now', 'here', 'there', 'then',
            'once', 'any', 'many', 'much', 'before', 'after', 'above', 'below',
            'between', 'through', 'during', 'about', 'into', 'over', 'under',
            'again', 'further', 'while', 'because', 'although', 'since', 'until',
            'unless', 'if', 'use', 'used', 'using', 'based', 'paper', 'study',
            'research', 'results', 'show', 'shows', 'shown', 'found', 'work',
            'approach', 'method', 'methods', 'new', 'novel', 'propose', 'proposed',
            'present', 'presented', 'section', 'introduction', 'conclusion',
            'abstract', 'textit', 'textbf', 'cite', 'ref', 'label', 'begin', 'end',
        }

        # Combine text sources (title weighted more heavily)
        combined_text = f"{title} {title} {title}"  # Weight title 3x
        if abstract:
            combined_text += f" {abstract} {abstract}"  # Weight abstract 2x
        if content:
            # Extract text from LaTeX, skip commands
            clean_content = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', ' ', content)
            clean_content = re.sub(r'\\[a-zA-Z]+', ' ', clean_content)
            combined_text += f" {clean_content}"

        # Extract meaningful words (3+ chars, alphabetic only)
        words = re.findall(r'\b[a-zA-Z]{3,}\b', combined_text.lower())

        # Count word frequency, excluding stopwords
        word_counts = {}
        for word in words:
            if word not in stopwords and len(word) >= 4:
                word_counts[word] = word_counts.get(word, 0) + 1

        # Get top keywords by frequency
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)

        # Return top 5-8 keywords, capitalized nicely
        keywords = []
        for word, _ in sorted_words[:8]:
            # Capitalize properly
            keywords.append(word.capitalize())
            if len(keywords) >= 5:
                break

        return keywords

    def _generate_citation_key(self, paper: Dict, used_keys: Optional[set] = None) -> str:
        """Generate a citation key from paper info (authorYYYYword format).

        If *used_keys* is provided the method guarantees uniqueness: when the
        base key already exists in the set a disambiguating letter suffix
        (a, b, c, ...) is appended.  The final key is added to *used_keys*
        before returning so that subsequent calls stay collision-free.
        """
        import re
        authors = paper.get("authors", "unknown")
        if isinstance(authors, list):
            first_author = authors[0] if authors else "unknown"
        else:
            first_author = authors.split(",")[0].strip() if authors else "unknown"

        # Extract last name
        if "," in first_author:
            last_name = first_author.split(",")[0].strip()
        else:
            last_name = first_author.split()[-1] if first_author.split() else "unknown"

        # Clean last name - only lowercase letters
        last_name = re.sub(r'[^a-zA-Z]', '', last_name).lower()

        year = str(paper.get("year", ""))

        # Get first significant word from title
        title = paper.get("title", "")
        title_words = [w for w in re.findall(r'[a-zA-Z]+', title) if len(w) > 3]
        title_word = title_words[0].lower() if title_words else ""

        base_key = f"{last_name}{year}{title_word}"

        # Disambiguate when tracking used keys
        if used_keys is not None:
            if base_key not in used_keys:
                used_keys.add(base_key)
                return base_key
            # Append a, b, c, ... until we find a free slot
            for suffix_ord in range(ord("a"), ord("z") + 1):
                candidate = f"{base_key}{chr(suffix_ord)}"
                if candidate not in used_keys:
                    used_keys.add(candidate)
                    return candidate
            # Extremely unlikely: all 26 letters exhausted, fall back to numeric
            n = 2
            while True:
                candidate = f"{base_key}{n}"
                if candidate not in used_keys:
                    used_keys.add(candidate)
                    return candidate
                n += 1

        return base_key

    def _parse_citation_key(self, cite_key: str) -> Dict[str, str]:
        """Parse a citation key into semantic components (author, year, title_word)."""
        import re

        result = {"author": "", "year": "", "title_word": "", "raw": cite_key}

        # Extract year (4 digits)
        year_match = re.search(r'(\d{4})', cite_key)
        if year_match:
            result["year"] = year_match.group(1)
            # Split on year to get author (before) and title word (after)
            parts = cite_key.split(result["year"])
            result["author"] = re.sub(r'[^a-z]', '', parts[0].lower()) if parts[0] else ""
            result["title_word"] = re.sub(r'[^a-z]', '', parts[1].lower()) if len(parts) > 1 and parts[1] else ""
        else:
            # No year found - treat entire key as author
            result["author"] = re.sub(r'[^a-z]', '', cite_key.lower())

        return result

    def _extract_paper_metadata(self, paper: Dict) -> Dict[str, any]:
        """Extract normalized metadata from a paper for matching."""
        import re

        # Normalize authors
        authors = paper.get("authors", "")
        if isinstance(authors, list):
            authors_str = " ".join(authors)
        else:
            authors_str = authors or ""

        # Extract individual author last names
        author_names = []
        for part in re.split(r'[,;&]', authors_str):
            words = part.strip().split()
            if words:
                # Last word is usually the last name, or first word if "LastName, FirstName" format
                if len(words) >= 2 and '.' in words[-1]:
                    author_names.append(words[0].lower())  # "Smith, J." -> "smith"
                else:
                    author_names.append(words[-1].lower())  # "John Smith" -> "smith"

        # Normalize title words
        title = paper.get("title", "")
        title_words = [w.lower() for w in re.findall(r'[a-zA-Z]+', title) if len(w) > 2]

        return {
            "authors_raw": authors_str.lower(),
            "author_names": author_names,
            "year": str(paper.get("year", "")),
            "title_words": title_words,
            "title_raw": title.lower(),
        }

    def _match_citation_to_paper(self, cite_key: str, papers: List[Dict]) -> Optional[Dict]:
        """
        Match a citation key to a paper using intelligent fuzzy matching.

        Parses the citation key into components and scores each paper
        based on metadata matches. Returns best match above threshold.
        """
        parsed = self._parse_citation_key(cite_key)

        best_match = None
        best_score = 0

        for paper in papers:
            meta = self._extract_paper_metadata(paper)
            score = 0

            # Year match (exact) - strong signal
            if parsed["year"] and meta["year"]:
                if parsed["year"] == meta["year"]:
                    score += 40
                else:
                    # Year mismatch is a strong negative signal
                    score -= 20

            # Author match - check if citation author matches any paper author
            if parsed["author"]:
                author_matched = False
                for author_name in meta["author_names"]:
                    # Check various matching strategies
                    if parsed["author"] == author_name:
                        score += 35  # Exact match
                        author_matched = True
                        break
                    elif parsed["author"] in author_name or author_name in parsed["author"]:
                        score += 25  # Partial match
                        author_matched = True
                        break
                    elif len(parsed["author"]) >= 3 and len(author_name) >= 3:
                        # Check if they share a common prefix (handles typos/variations)
                        common_len = min(len(parsed["author"]), len(author_name))
                        if parsed["author"][:common_len-1] == author_name[:common_len-1]:
                            score += 20
                            author_matched = True
                            break

                # Also check raw authors string for partial matches
                if not author_matched and parsed["author"] in meta["authors_raw"]:
                    score += 15

            # Title word match
            if parsed["title_word"]:
                title_matched = False
                for title_word in meta["title_words"]:
                    if parsed["title_word"] == title_word:
                        score += 30  # Exact match
                        title_matched = True
                        break
                    elif parsed["title_word"] in title_word or title_word in parsed["title_word"]:
                        score += 20  # Partial match
                        title_matched = True
                        break

                # Also check raw title
                if not title_matched and parsed["title_word"] in meta["title_raw"]:
                    score += 10

            if score > best_score:
                best_score = score
                best_match = paper

        # Require minimum score to avoid false positives
        # Score of 50+ means at least year + author or year + title matched
        return best_match if best_score >= 50 else None

    def _generate_bibliography_entries(self, ctx: Dict[str, Any], content: str) -> list:
        """Generate \\bibitem entries for all citations in content.

        Uses intelligent fuzzy matching to match AI-generated citation keys
        to actual papers in the context (recent search results + project library).
        """
        import re
        from app.models import Reference, ProjectReference

        project = ctx["project"]
        recent_search_results = self._get_recent_papers(ctx)

        # Get project library references
        project_refs = (
            self.db.query(Reference)
            .join(ProjectReference, ProjectReference.reference_id == Reference.id)
            .filter(ProjectReference.project_id == project.id)
            .limit(1000)
            .all()
        )

        # Build list of all available papers
        all_papers = []
        for paper in recent_search_results:
            all_papers.append(paper)
        for ref in project_refs:
            all_papers.append({
                "title": ref.title,
                "authors": ref.authors if isinstance(ref.authors, str) else ", ".join(ref.authors or []),
                "year": ref.year,
                "doi": ref.doi,
                "url": ref.url,
                "journal": ref.journal,
            })

        if not all_papers:
            logger.warning("[Bibliography] No papers available for citation matching")
            return []

        # Also create lookup by our generated keys for exact matches
        paper_by_key = {}
        used_keys: set = set()
        for paper in all_papers:
            key = self._generate_citation_key(paper, used_keys)
            paper_by_key[key] = paper

        # Extract citation keys from content
        cite_matches = _CITE_PATTERN.findall(content)
        citation_keys = set()
        for match in cite_matches:
            for key in match.split(','):
                citation_keys.add(key.strip())

        if not citation_keys:
            return []

        # Generate bibitem entries using intelligent matching
        bibliography_entries = []
        matched_count = 0
        unmatched_keys = []

        for cite_key in sorted(citation_keys):
            paper = None

            # 1. Try exact match with our generated keys first
            paper = paper_by_key.get(cite_key)

            # 2. Use intelligent fuzzy matching on paper metadata
            if not paper:
                paper = self._match_citation_to_paper(cite_key, all_papers)

            if paper:
                matched_count += 1
                authors = paper.get("authors", "Unknown")
                if isinstance(authors, list):
                    authors = ", ".join(authors)
                title = paper.get("title", "Untitled")
                year = paper.get("year", "")
                journal = paper.get("journal", "")

                # Escape untrusted text to prevent LaTeX injection (e.g. \write18 RCE)
                safe_authors = _escape_latex(str(authors))
                safe_title = _escape_latex(str(title))
                safe_journal = _escape_latex(str(journal)) if journal else ""
                safe_year = _escape_latex(str(year)) if year else ""

                # Format: \bibitem{key} Author(s). \textit{Title}. Journal, Year.
                entry = f"\\bibitem{{{cite_key}}} {safe_authors}. \\textit{{{safe_title}}}."
                if safe_journal:
                    entry += f" {safe_journal},"
                if safe_year:
                    entry += f" {safe_year}."
                bibliography_entries.append(entry)
            else:
                unmatched_keys.append(cite_key)
                # Generate placeholder for unmatched citation so it doesn't show as [?]
                # Parse the citation key to extract what info we can
                parsed = self._parse_citation_key(cite_key)
                author_hint = parsed["author"].capitalize() if parsed["author"] else "Unknown"
                year_hint = parsed["year"] if parsed["year"] else "n.d."
                # Create a placeholder entry that's clearly marked as unverified
                placeholder = f"\\bibitem{{{cite_key}}} {author_hint} et al. \\textit{{[Reference not found in library]}}. {year_hint}. \\textbf{{[Unverified citation]}}"
                bibliography_entries.append(placeholder)

        if unmatched_keys:
            logger.warning(f"[Bibliography] Could not match {len(unmatched_keys)} citation keys: {unmatched_keys}")

        logger.info(f"[Bibliography] Matched {matched_count}/{len(citation_keys)} citations, {len(unmatched_keys)} unverified")

        # Store unmatched keys in a class attribute for later retrieval
        self._last_unmatched_citations = unmatched_keys

        return bibliography_entries

    def _sanitize_latex_content(self, content: str) -> str:
        """Remove characters that break LaTeX compilation."""
        import re
        # Remove null characters
        content = content.replace('\x00', '')
        # Remove other control characters except newlines and tabs
        content = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', content)
        # Remove smart quotes and replace with regular quotes
        content = content.replace('\u201c', '"').replace('\u201d', '"')
        content = content.replace('\u2018', "'").replace('\u2019', "'")
        # Remove other unicode that might cause issues
        content = content.replace('\u2013', '--').replace('\u2014', '---')
        content = content.replace('\u2026', '...')
        return content

    def _ensure_latex_document(self, content: str, title: str, abstract: str = None, bibliography_entries: list = None, template: str = "generic") -> str:
        """Ensure content is wrapped in a proper LaTeX document structure."""
        import re
        from app.constants.paper_templates import CONFERENCE_TEMPLATES

        # Sanitize content first
        content = self._sanitize_latex_content(content)

        if '\\documentclass' in content:
            return content

        # Check if content already has an abstract section to avoid duplicates
        content_abstract_match = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', content, re.DOTALL)

        abstract_section = ""
        if abstract:
            # Explicit abstract parameter provided - use it and remove any from content
            if content_abstract_match:
                # Remove the abstract from content since we'll add it separately
                content = re.sub(r'\\begin\{abstract\}.*?\\end\{abstract\}\s*', '', content, flags=re.DOTALL)
            abstract_section = f"""
\\begin{{abstract}}
{abstract}
\\end{{abstract}}
"""
        elif content_abstract_match:
            # No explicit abstract but content has one - extract it and remove from content
            # so we can place it in the correct position (after maketitle, before sections)
            extracted_abstract = content_abstract_match.group(1).strip()
            content = re.sub(r'\\begin\{abstract\}.*?\\end\{abstract\}\s*', '', content, flags=re.DOTALL)
            abstract_section = f"""
\\begin{{abstract}}
{extracted_abstract}
\\end{{abstract}}
"""

        # Check if content has citations
        has_citations = '\\cite{' in content

        # Bibliography section - generate inline bibitem entries
        bibliography_section = ""
        if has_citations and bibliography_entries:
            bib_items = "\n".join(bibliography_entries)
            bibliography_section = f"""

\\begin{{thebibliography}}{{99}}
{bib_items}
\\end{{thebibliography}}
"""

        # Get template preamble if specified
        template_info = CONFERENCE_TEMPLATES.get(template, CONFERENCE_TEMPLATES.get("generic"))

        if template_info and template != "generic":
            import re
            # Use template preamble and inject title
            preamble = template_info["preamble_example"]
            # Replace placeholder title with actual title
            preamble = preamble.replace("Your Paper Title", title)
            preamble = preamble.replace("Your Full Paper Title", title)

            # Simplify author block to avoid template-specific issues
            # Replace complex multi-author blocks with simple anonymous author
            # Pattern matches \author{...} including nested braces
            author_pattern = r'\\author\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            if re.search(author_pattern, preamble, re.DOTALL):
                preamble = re.sub(author_pattern, r'\\author{Anonymous}', preamble, flags=re.DOTALL)

            latex_template = f"""{preamble}
{abstract_section}
{content}
{bibliography_section}
\\end{{document}}
"""
        else:
            # Default generic template
            latex_template = f"""\\documentclass{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{amsmath}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}

\\title{{{title}}}
\\date{{\\today}}

\\begin{{document}}

\\maketitle
{abstract_section}
{content}
{bibliography_section}
\\end{{document}}
"""
        return latex_template.strip()

    def _tool_update_paper(
        self,
        ctx: Dict[str, Any],
        paper_id: str,
        content: str,
        section_name: Optional[str] = None,
        append: bool = True,
    ) -> Dict:
        """Update an existing paper's content."""
        from app.models import ResearchPaper
        from uuid import UUID
        import re

        try:
            paper_uuid = UUID(paper_id)
        except ValueError:
            return {"status": "error", "message": "Invalid paper ID format"}

        paper = self.db.query(ResearchPaper).filter(
            ResearchPaper.id == paper_uuid
        ).first()

        if not paper:
            return {"status": "error", "message": "Paper not found"}

        # Check if paper is in LaTeX mode (content stored in content_json)
        is_latex_mode = paper.content_json and paper.content_json.get("authoring_mode") == "latex"

        if is_latex_mode:
            current_latex = paper.content_json.get("latex_source", "")

            # Safety: strip \end{document} from content if AI accidentally includes it
            content = re.sub(r'\\end\{document\}.*$', '', content, flags=re.DOTALL).strip()

            if section_name:
                # Replace a specific section by name
                # Pattern matches \section{Name} through to next \section{, bibliography, or \end{document}
                # Must preserve bibliography sections that come after
                escaped_name = re.escape(section_name)
                pattern = rf"(\\section\{{{escaped_name}\}}.*?)(?=\\section\{{|\\begin\{{thebibliography\}}|\\printbibliography|\\bibliography\{{|\\end\{{document\}}|$)"

                if re.search(pattern, current_latex, re.DOTALL | re.IGNORECASE):
                    # Replace the section with new content (use lambda to avoid escape issues with \section)
                    new_latex = re.sub(pattern, lambda m: content + "\n\n", current_latex, count=1, flags=re.DOTALL | re.IGNORECASE)
                else:
                    # Section not found, append instead
                    if "\\end{document}" in current_latex:
                        new_latex = current_latex.replace("\\end{document}", f"\n\n{content}\n\n\\end{{document}}")
                    else:
                        new_latex = current_latex + "\n\n" + content
            elif append and current_latex:
                # Insert before \end{document} if present
                if "\\end{document}" in current_latex:
                    new_latex = current_latex.replace("\\end{document}", f"\n\n{content}\n\n\\end{{document}}")
                else:
                    new_latex = current_latex + "\n\n" + content
            else:
                new_latex = content

            # Update content_json (make a copy to trigger SQLAlchemy change detection)
            updated_json = dict(paper.content_json)
            updated_json["latex_source"] = new_latex
            paper.content_json = updated_json
        else:
            # Plain content mode
            if append and paper.content:
                paper.content = paper.content + "\n\n" + content
            else:
                paper.content = content

        self.db.commit()

        # Link any new cited references to paper and project library
        latex_to_check = new_latex if is_latex_mode else content
        ref_result = self._link_cited_references(ctx, paper_id, latex_to_check)
        ref_message = f" {ref_result['message']}" if ref_result.get("linked", 0) > 0 else ""

        section_msg = f" (replaced section '{section_name}')" if section_name else ""

        # Build url_id for frontend navigation
        url_id = f"{paper.slug}-{paper.short_id}" if paper.slug and paper.short_id else str(paper.id)

        return {
            "status": "success",
            "message": f"Updated paper '{paper.title}'{section_msg}.{ref_message}",
            # Note: paper_id is in action.payload for frontend use - don't show UUIDs to users
            "references_linked": ref_result.get("linked", 0),
            "action": {
                "type": "paper_updated",
                "payload": {
                    "paper_id": paper_id,
                    "url_id": url_id,
                    "title": paper.title,
                }
            }
        }

    def _tool_create_artifact(
        self,
        ctx: Dict[str, Any],
        title: str,
        content: str,
        format: str = "markdown",
        artifact_type: str = "document",
        _fallback_depth: int = 0,
    ) -> Dict:
        """Create a downloadable artifact and save to database."""
        import base64
        import subprocess
        import tempfile
        import os
        from app.models import DiscussionArtifact

        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()

        # Handle PDF generation with proper cleanup
        if format == "pdf":
            md_path = None
            pdf_path = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as md_file:
                    md_file.write(content)
                    md_path = md_file.name

                pdf_path = md_path.replace('.md', '.pdf')

                result = subprocess.run(
                    ['pandoc', md_path, '-o', pdf_path, '--pdf-engine=tectonic'],
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode != 0:
                    logger.error(f"Pandoc error: {result.stderr}")
                    # Fall back to markdown (with depth guard to prevent infinite recursion)
                    if _fallback_depth >= 1:
                        return {"status": "error", "message": "PDF generation failed and fallback also failed."}
                    return self._tool_create_artifact(ctx, title, content, "markdown", artifact_type, _fallback_depth=_fallback_depth + 1)

                with open(pdf_path, 'rb') as pdf_file:
                    pdf_bytes = pdf_file.read()
                    content_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                    file_size_bytes = len(pdf_bytes)

                filename = f"{safe_title}.pdf"
                mime_type = "application/pdf"

            except Exception as e:
                logger.error(f"PDF generation failed: {e}")
                if _fallback_depth >= 1:
                    return {"status": "error", "message": f"PDF generation failed: {e}"}
                return self._tool_create_artifact(ctx, title, content, "markdown", artifact_type, _fallback_depth=_fallback_depth + 1)
            finally:
                # Always clean up temp files
                if md_path and os.path.exists(md_path):
                    os.unlink(md_path)
                if pdf_path and os.path.exists(pdf_path):
                    os.unlink(pdf_path)
        else:
            # Text-based formats
            extensions = {"markdown": ".md", "latex": ".tex", "text": ".txt"}
            extension = extensions.get(format, ".txt")
            filename = f"{safe_title}{extension}"

            content_bytes = content.encode('utf-8')
            content_base64 = base64.b64encode(content_bytes).decode('utf-8')
            file_size_bytes = len(content_bytes)

            mime_types = {"markdown": "text/markdown", "latex": "application/x-tex", "text": "text/plain"}
            mime_type = mime_types.get(format, "text/plain")

        # Calculate human-readable file size
        if file_size_bytes < 1024:
            file_size = f"{file_size_bytes} B"
        elif file_size_bytes < 1024 * 1024:
            file_size = f"{file_size_bytes / 1024:.1f} KB"
        else:
            file_size = f"{file_size_bytes / (1024 * 1024):.1f} MB"

        # Save artifact to database
        channel = ctx.get("channel")
        project = ctx.get("project")

        if not channel:
            logger.warning("Cannot save artifact: channel not found in context")
            return {
                "status": "success",
                "message": f"Created downloadable artifact: '{title}' (not persisted)",
                "action": {
                    "type": "artifact_created",
                    "summary": f"Download: {title}",
                    "payload": {
                        "artifact_id": None,
                        "title": title,
                        "filename": filename,
                        "content_base64": content_base64,
                        "format": format,
                        "artifact_type": artifact_type,
                        "mime_type": mime_type,
                        "file_size": file_size,
                    }
                }
            }

        artifact = DiscussionArtifact(
            channel_id=channel.id,
            title=title,
            filename=filename,
            format=format,
            artifact_type=artifact_type,
            content_base64=content_base64,
            mime_type=mime_type,
            file_size=file_size,
            created_by=project.created_by if project else None,
        )
        self.db.add(artifact)
        self.db.commit()
        self.db.refresh(artifact)

        return {
            "status": "success",
            "message": f"Created downloadable artifact: '{title}'",
            "action": {
                "type": "artifact_created",
                "summary": f"Download: {title}",
                "payload": {
                    "artifact_id": str(artifact.id),
                    "title": title,
                    "filename": filename,
                    "content_base64": content_base64,
                    "format": format,
                    "artifact_type": artifact_type,
                    "mime_type": mime_type,
                    "file_size": file_size,
                }
            }
        }

    def _tool_get_created_artifacts(
        self,
        ctx: Dict[str, Any],
        limit: int = 10,
    ) -> Dict:
        """Get artifacts that were created in this discussion channel."""
        from app.models import DiscussionArtifact

        channel = ctx.get("channel")
        if not channel:
            return {
                "status": "error",
                "message": "Channel context not available.",
                "artifacts": [],
            }

        try:
            artifacts = (
                self.db.query(DiscussionArtifact)
                .filter(DiscussionArtifact.channel_id == channel.id)
                .order_by(DiscussionArtifact.created_at.desc())
                .limit(limit)
                .all()
            )

            if not artifacts:
                return {
                    "status": "success",
                    "message": "No artifacts have been created in this channel yet.",
                    "artifacts": [],
                    "count": 0,
                }

            artifact_list = []
            for artifact in artifacts:
                artifact_list.append({
                    "title": artifact.title,
                    "filename": artifact.filename,
                    "format": artifact.format,
                    "artifact_type": artifact.artifact_type,
                    "file_size": artifact.file_size,
                    "mime_type": artifact.mime_type,
                    "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
                })

            return {
                "status": "success",
                "message": f"Found {len(artifact_list)} artifact(s) in this channel.",
                "artifacts": artifact_list,
                "count": len(artifact_list),
            }

        except Exception as e:
            logger.exception(f"Error fetching created artifacts: {e}")
            return {
                "status": "error",
                "message": f"Failed to retrieve artifacts: {str(e)}",
                "artifacts": [],
            }

    def _tool_add_to_library(
        self,
        ctx: Dict[str, Any],
        paper_indices: List[int],
        ingest_pdfs: bool = True,
    ) -> Dict:
        """
        Add papers from recent search results to the project library and optionally ingest PDFs.
        This allows the AI to have full PDF context before creating papers.
        """
        from app.models import Reference, ProjectReference, ProjectReferenceStatus, ProjectReferenceOrigin
        from app.services.reference_ingestion_service import ingest_reference_pdf

        project = ctx["project"]
        recent_search_results = self._get_recent_papers(ctx)

        # Fallback: if no recent search results, use focused papers from AI memory
        if not recent_search_results:
            channel = ctx.get("channel")
            if channel:
                memory = self._get_ai_memory(channel)
                focused = memory.get("focused_papers", [])
                if focused:
                    logger.info(f"[AddToLibrary] No search results, falling back to {len(focused)} focused papers")
                    recent_search_results = focused

        if not recent_search_results:
            return {
                "status": "error",
                "message": "No recent search results or focused papers. Search for papers first using search_papers.",
            }

        if not paper_indices:
            return {
                "status": "error",
                "message": "No paper indices provided. Specify which papers to add (e.g., [0,1,2] for first 3 papers).",
            }

        # Cap batch size to prevent excessive operations
        if len(paper_indices) > 25:
            paper_indices = paper_indices[:25]

        added_papers = []
        failed_papers = []
        ingestion_results = []
        used_keys: set = set()

        for idx in paper_indices:
            if idx < 0 or idx >= len(recent_search_results):
                failed_papers.append({"index": idx, "error": "Index out of range"})
                continue

            paper = recent_search_results[idx]
            title = paper.get("title", "Untitled")

            try:
                # Check if reference already exists by DOI or normalized title+authors
                doi = paper.get("doi")
                existing_ref = None
                paper_year = paper.get("year")
                paper_authors = paper.get("authors", [])
                if isinstance(paper_authors, str):
                    paper_authors = [a.strip() for a in paper_authors.split(",")]

                normalized_title = _normalize_title(title)
                normalized_authors = set(_normalize_author(a) for a in paper_authors if a)

                # 1. Check by DOI first (most reliable)
                if doi:
                    existing_ref = self.db.query(Reference).filter(
                        Reference.doi == doi,
                        Reference.owner_id == project.created_by
                    ).first()

                # 2. Check by normalized title + author overlap
                if not existing_ref:
                    all_refs = self.db.query(Reference).filter(
                        Reference.owner_id == project.created_by
                    ).limit(5000).all()
                    for ref in all_refs:
                        ref_normalized_title = _normalize_title(ref.title or "")
                        # Title must match
                        if ref_normalized_title != normalized_title:
                            continue
                        # Check author overlap (at least one author in common)
                        ref_authors = ref.authors or []
                        ref_normalized_authors = set(_normalize_author(a) for a in ref_authors if a)
                        if normalized_authors & ref_normalized_authors:  # Intersection
                            existing_ref = ref
                            logger.info(f"[Dedup] Found duplicate by title+author: '{title}' matches '{ref.title}'")
                            break
                        # If no authors to compare but titles match exactly, also consider duplicate
                        if not normalized_authors and not ref_normalized_authors:
                            existing_ref = ref
                            logger.info(f"[Dedup] Found duplicate by title (no authors): '{title}'")
                            break

                # Create Reference if not exists
                if not existing_ref:
                    authors = paper.get("authors", [])
                    if isinstance(authors, str):
                        authors = [a.strip() for a in authors.split(",")]

                    try:
                        existing_ref = Reference(
                            owner_id=project.created_by,
                            title=title,
                            authors=authors,
                            year=paper.get("year"),
                            doi=doi,
                            url=paper.get("url"),
                            source=paper.get("source", "ai_discovery"),
                            journal=paper.get("journal"),
                            abstract=paper.get("abstract"),
                            is_open_access=paper.get("is_open_access", False),
                            pdf_url=paper.get("pdf_url"),
                            status="pending",
                        )
                        self.db.add(existing_ref)
                        self.db.flush()
                    except IntegrityError:
                        # Race condition: another request created this reference
                        self.db.rollback()
                        # Re-query to get the existing record
                        if doi:
                            existing_ref = self.db.query(Reference).filter(
                                Reference.doi == doi,
                                Reference.owner_id == project.created_by
                            ).first()
                        # Try normalized title+author match if DOI failed
                        if not existing_ref:
                            all_refs = self.db.query(Reference).filter(
                                Reference.owner_id == project.created_by
                            ).limit(5000).all()
                            for ref in all_refs:
                                ref_normalized_title = _normalize_title(ref.title or "")
                                if ref_normalized_title != normalized_title:
                                    continue
                                ref_authors = ref.authors or []
                                ref_normalized_authors = set(_normalize_author(a) for a in ref_authors if a)
                                if normalized_authors & ref_normalized_authors:
                                    existing_ref = ref
                                    break
                                if not normalized_authors and not ref_normalized_authors:
                                    existing_ref = ref
                                    break
                        if not existing_ref:
                            # Still can't find it - add to failed_papers and continue
                            logger.warning(f"[AddToLibrary] Failed to create or find reference after IntegrityError: {title}")
                            failed_papers.append({"index": idx, "title": title, "error": "Failed to create reference (race condition)"})
                            continue

                # Check if already in project library
                existing_project_ref = self.db.query(ProjectReference).filter(
                    ProjectReference.project_id == project.id,
                    ProjectReference.reference_id == existing_ref.id
                ).first()

                already_in_library = existing_project_ref is not None
                channel = ctx.get("channel")

                if not existing_project_ref:
                    current_user = ctx.get("current_user")
                    project_ref = ProjectReference(
                        project_id=project.id,
                        reference_id=existing_ref.id,
                        status=ProjectReferenceStatus.APPROVED,
                        origin=ProjectReferenceOrigin.AUTO_DISCOVERY,
                        added_via_channel_id=channel.id if channel else None,
                        added_by_user_id=current_user.id if current_user else None,
                    )
                    self.db.add(project_ref)
                elif channel and not existing_project_ref.added_via_channel_id:
                    # Update existing reference to track the channel if not already set
                    existing_project_ref.added_via_channel_id = channel.id

                # Commit changes before attempting PDF ingestion
                self.db.commit()
                # Refresh to ensure the object is attached to the session after commit
                self.db.refresh(existing_ref)

                # Queue embedding job for new library additions
                if not existing_project_ref:
                    try:
                        from app.services.embedding_worker import queue_library_paper_embedding_sync
                        # Get the project_ref we just created
                        new_project_ref = self.db.query(ProjectReference).filter(
                            ProjectReference.project_id == project.id,
                            ProjectReference.reference_id == existing_ref.id
                        ).first()
                        if new_project_ref:
                            queue_library_paper_embedding_sync(
                                reference_id=new_project_ref.id,
                                project_id=project.id,
                                db=self.db
                            )
                    except Exception as e:
                        # Don't fail the add_to_library if embedding queue fails
                        logger.warning(f"[AddToLibrary] Failed to queue embedding job: {e}")

                # Generate citation key for this paper
                cite_key = self._generate_citation_key(paper, used_keys)

                added_info = {
                    "index": idx,
                    "title": title,
                    "reference_id": str(existing_ref.id),
                    "has_pdf": bool(existing_ref.pdf_url),
                    "cite_key": cite_key,  # Use this in \cite{} commands
                    "already_in_library": already_in_library,  # Was it already there?
                }

                # Attempt PDF ingestion if requested and PDF is available
                # Reference is already committed, so PDF ingestion failures won't affect it
                if ingest_pdfs and existing_ref.pdf_url:
                    try:
                        success = ingest_reference_pdf(
                            self.db,
                            existing_ref,
                            owner_id=str(project.created_by)
                        )
                        if success:
                            added_info["ingestion_status"] = "success"
                            ingestion_results.append({"title": title, "status": "ingested"})
                        else:
                            added_info["ingestion_status"] = "failed"
                            ingestion_results.append({"title": title, "status": "failed"})
                    except Exception as e:
                        logger.warning(f"PDF ingestion failed for {title}: {e}")
                        added_info["ingestion_status"] = "error"
                        added_info["ingestion_error"] = str(e)
                        ingestion_results.append({"title": title, "status": "error", "error": str(e)})
                        # Don't rollback - the Reference was already committed successfully
                        # Just expire the specific ref to clear any stale state
                        self.db.expire(existing_ref)
                elif not existing_ref.pdf_url:
                    added_info["ingestion_status"] = "no_pdf_available"
                else:
                    added_info["ingestion_status"] = "skipped"

                added_papers.append(added_info)

            except Exception as e:
                logger.exception(f"Error adding paper at index {idx}")
                # Rollback uncommitted changes for THIS paper (e.g. failed Reference creation)
                # Previously committed papers are safe since each iteration commits independently
                self.db.rollback()
                failed_papers.append({"index": idx, "title": title, "error": str(e)})

        # Summary
        ingested_count = sum(1 for p in added_papers if p.get("ingestion_status") == "success")
        no_pdf_count = sum(1 for p in added_papers if p.get("ingestion_status") == "no_pdf_available")
        already_existed_count = sum(1 for p in added_papers if p.get("already_in_library"))
        newly_added_count = len(added_papers) - already_existed_count
        search_id = ctx.get("recent_search_id") or ctx.get("last_search_id")

        message_parts = []
        if newly_added_count > 0:
            message_parts.append(f"Added {newly_added_count} new papers to your library.")
        if already_existed_count > 0:
            message_parts.append(f"{already_existed_count} papers were already in your library.")
        if ingested_count > 0:
            message_parts.append(f"{ingested_count} PDFs ingested for full-text analysis.")
        if no_pdf_count > 0:
            message_parts.append(f"{no_pdf_count} papers have no PDF available (abstract only).")
        if failed_papers:
            message_parts.append(f"{len(failed_papers)} papers failed to add.")
        if not message_parts:
            message_parts.append("No papers to add.")

        # Build library_update action so frontend can update search results UI
        library_updates = []
        for paper in added_papers:
            # Map backend ingestion_status to frontend IngestionStatus type
            status_map = {
                "success": "success",
                "failed": "failed",
                "error": "failed",
                "no_pdf_available": "no_pdf",
                "skipped": "success",  # Already processed
            }
            frontend_status = status_map.get(paper.get("ingestion_status", ""), "pending")
            library_updates.append({
                "index": paper.get("index"),
                "reference_id": paper.get("reference_id"),
                "ingestion_status": frontend_status,
            })

        return {
            "status": "success" if added_papers else "error",
            "message": " ".join(message_parts),
            "added_papers": added_papers,
            "failed_papers": failed_papers,
            "summary": {
                "total_processed": len(added_papers),
                "newly_added": newly_added_count,
                "already_in_library": already_existed_count,
                "pdfs_ingested": ingested_count,
                "no_pdf_available": no_pdf_count,
                "failed": len(failed_papers),
            },
            "next_step": "Use get_reference_details(reference_id) to read the full content of ingested papers before creating your paper." if ingested_count > 0 else "Papers added with abstract only. You can create a paper based on abstracts, but full PDF analysis is not available.",
            "citation_instructions": "When creating the paper, use \\cite{cite_key} with the cite_key values provided for each paper above. This ensures references are properly linked.",
            # Action to update frontend search results UI with ingestion status
            "action": {
                "type": "library_update",
                "payload": {
                    "search_id": search_id,
                    "updates": library_updates,
                },
            },
        }

    def _tool_generate_abstract(
        self,
        ctx: Dict[str, Any],
        paper_id: str,
        max_words: int = 250,
    ) -> Dict:
        """Generate a structured abstract for an existing paper based on its content."""
        from app.models import ResearchPaper
        from uuid import UUID

        project = ctx["project"]

        try:
            paper_uuid = UUID(paper_id)
        except ValueError:
            return {"status": "error", "message": "Invalid paper ID format."}

        paper = self.db.query(ResearchPaper).filter(
            ResearchPaper.id == paper_uuid,
            ResearchPaper.project_id == project.id,
        ).first()

        if not paper:
            return {"status": "error", "message": "Paper not found in this project."}

        # Extract content from content_json or plain content
        content = ""
        if paper.content_json and paper.content_json.get("latex_source"):
            content = paper.content_json["latex_source"]
        elif paper.content:
            content = paper.content

        if not content or len(content.strip()) < 50:
            return {
                "status": "error",
                "message": "Paper has insufficient content to generate an abstract.",
            }

        # Strip LaTeX commands for readability
        readable = self._latex_to_markdown(content)
        # Truncate to ~8000 chars to fit context limits
        if len(readable) > 8000:
            readable = readable[:8000] + "\n\n[Content truncated...]"

        content_preview = readable[:500]

        instruction = (
            f"Generate a structured abstract (background, methods, results, conclusion) "
            f"in {max_words} words for this paper. "
            "Base the abstract ONLY on the content provided below. "
            "Do not invent findings or methods not present in the text."
        )

        return {
            "status": "success",
            "paper_title": paper.title,
            "content_preview": content_preview,
            "full_content": readable,
            "instruction": instruction,
        }

    def _tool_update_project_info(
        self,
        ctx: Dict[str, Any],
        preview: bool = False,
        description: Optional[str] = None,
        objectives: Optional[List[str]] = None,
        objectives_mode: str = "replace",
        keywords: Optional[List[str]] = None,
        keywords_mode: str = "replace",
    ) -> Dict:
        """
        Update project description, objectives, and/or keywords.

        Objectives are stored as newline-separated string in the 'scope' field.
        Keywords are stored as a string array in the 'keywords' field.
        Each objective should be concise (max 150 chars recommended).
        """
        from app.models import Project

        project_in_ctx = ctx.get("project")
        project_id = getattr(project_in_ctx, "id", None)
        project = (
            self.db.query(Project).filter(Project.id == project_id).first()
            if project_id is not None
            else None
        )
        if not project:
            return {
                "status": "error",
                "message": "Project not found in current session.",
            }
        updated_fields = []

        # Update description if provided
        if description is not None:
            if not description.strip():
                pass  # skip — empty string is never an intentional clear via chat
            elif len(description) > 2000:
                return {
                    "status": "error",
                    "message": "Description is too long. Maximum 2000 characters allowed.",
                }
            else:
                project.idea = description.strip()
                updated_fields.append("description")

        # Update objectives if provided
        if objectives is not None:
            if not isinstance(objectives, list):
                return {
                    "status": "error",
                    "message": "Objectives must be a list of strings.",
                }
            if objectives == [] and objectives_mode == "replace":
                pass  # skip — empty replace is never intentional via chat
            else:
                # Validate each objective
                validated_objectives = []
                for i, obj in enumerate(objectives):
                    if not isinstance(obj, str):
                        continue
                    obj = obj.strip()
                    if not obj:
                        continue
                    # Truncate if too long (max 150 chars per objective)
                    if len(obj) > 150:
                        obj = obj[:147] + "..."
                    validated_objectives.append(obj)

                if objectives_mode == "append":
                    # Append to existing objectives
                    existing = project.scope or ""
                    existing_list = [o.strip() for o in existing.split("\n") if o.strip()]
                    # Don't add duplicates
                    added_count = 0
                    for new_obj in validated_objectives:
                        if new_obj not in existing_list:
                            existing_list.append(new_obj)
                            added_count += 1
                    project.scope = "\n".join(existing_list)
                    if added_count > 0:
                        updated_fields.append(f"objectives (added {added_count})")
                    else:
                        # All objectives were duplicates
                        pass
                elif objectives_mode == "remove":
                    # Remove specific objectives
                    existing = project.scope or ""
                    existing_list = [o.strip() for o in existing.split("\n") if o.strip()]
                    removed = []

                    for to_remove in validated_objectives:
                        to_remove_lower = to_remove.lower()
                        # Check if it's an index reference like "objective 1", "1", "first"
                        index_to_remove = None
                        if to_remove_lower.startswith("objective "):
                            try:
                                index_to_remove = int(to_remove_lower.replace("objective ", "")) - 1
                            except ValueError:
                                pass
                        elif to_remove.isdigit():
                            index_to_remove = int(to_remove) - 1

                        if index_to_remove is not None and 0 <= index_to_remove < len(existing_list):
                            removed.append(existing_list[index_to_remove])
                            existing_list[index_to_remove] = None  # Mark for removal
                        else:
                            # Match by text (partial match, case-insensitive)
                            for i, existing_obj in enumerate(existing_list):
                                if existing_obj and to_remove_lower in existing_obj.lower():
                                    removed.append(existing_obj)
                                    existing_list[i] = None  # Mark for removal
                                    break

                    # Filter out removed items
                    existing_list = [o for o in existing_list if o is not None]
                    project.scope = "\n".join(existing_list)

                    if removed:
                        updated_fields.append(f"objectives (removed {len(removed)})")
                    else:
                        return {
                            "status": "error",
                            "message": "Could not find objectives to remove. Provide the objective text or index (e.g., 'objective 1' or '1').",
                            "current_objectives": existing_list,
                        }
                else:
                    # Replace all objectives
                    project.scope = "\n".join(validated_objectives)
                    updated_fields.append("objectives")

        # Update keywords if provided
        if keywords is not None:
            if not isinstance(keywords, list):
                return {
                    "status": "error",
                    "message": "Keywords must be a list of strings.",
                }
            if keywords == [] and keywords_mode == "replace":
                pass  # skip — empty replace is never intentional via chat
            else:
                # Validate and clean keywords
                validated_keywords = []
                for kw in keywords:
                    if not isinstance(kw, str):
                        continue
                    kw = kw.strip().lower()
                    if not kw:
                        continue
                    # Truncate if too long (max 50 chars per keyword)
                    if len(kw) > 50:
                        kw = kw[:50]
                    validated_keywords.append(kw)

                existing_keywords = project.keywords or []

                if keywords_mode == "append":
                    # Append new keywords (avoid duplicates)
                    added_count = 0
                    for new_kw in validated_keywords:
                        if new_kw not in existing_keywords:
                            existing_keywords.append(new_kw)
                            added_count += 1
                    project.keywords = existing_keywords
                    if added_count > 0:
                        updated_fields.append(f"keywords (added {added_count})")
                elif keywords_mode == "remove":
                    # Remove specific keywords
                    removed = []
                    for to_remove in validated_keywords:
                        if to_remove in existing_keywords:
                            existing_keywords.remove(to_remove)
                            removed.append(to_remove)
                    project.keywords = existing_keywords
                    if removed:
                        updated_fields.append(f"keywords (removed {len(removed)})")
                    else:
                        return {
                            "status": "error",
                            "message": "Could not find keywords to remove.",
                            "current_keywords": existing_keywords,
                        }
                else:
                    # Replace all keywords
                    project.keywords = validated_keywords
                    updated_fields.append("keywords")

        if not updated_fields:
            return {
                "status": "error",
                "message": "No fields to update. Provide description and/or objectives.",
            }

        if preview:
            # Capture the would-be state before rolling back
            preview_desc = project.idea
            preview_objectives = [o.strip() for o in (project.scope or "").split("\n") if o.strip()]
            preview_keywords = list(project.keywords or [])
            preview_title = project.title
            self.db.rollback()
            return {
                "status": "preview",
                "message": f"Preview of changes to: {', '.join(updated_fields)}. NOT saved yet — confirm to apply.",
                "would_update": updated_fields,
                "preview_state": {
                    "title": preview_title,
                    "description": preview_desc,
                    "objectives": preview_objectives,
                    "keywords": preview_keywords,
                },
            }

        try:
            self.db.commit()
            self.db.refresh(project)

            # Parse current objectives for response
            current_objectives = [o.strip() for o in (project.scope or "").split("\n") if o.strip()]

            return {
                "status": "success",
                "message": f"Updated project {', '.join(updated_fields)}.",
                "updated_fields": updated_fields,
                "current_state": {
                    "title": project.title,
                    "description": project.idea,
                    "objectives": current_objectives,
                    "objectives_count": len(current_objectives),
                    "keywords": project.keywords or [],
                    "keywords_count": len(project.keywords or []),
                }
            }
        except Exception as e:
            self.db.rollback()
            logger.exception("Error updating project info")
            return {
                "status": "error",
                "message": f"Failed to update project: {str(e)}",
            }

    def _tool_export_citations(
        self,
        ctx: Dict[str, Any],
        reference_ids: Optional[List[str]] = None,
        format: str = "bibtex",
        scope: str = "all",
    ) -> Dict:
        """Export citations from the project library in a specific format."""
        from uuid import UUID
        from app.models import Reference, ProjectReference

        project = ctx["project"]
        references: List[Any] = []

        if scope == "selected" and reference_ids:
            # Query specific references by ID, ensuring they belong to the project
            for ref_id_str in reference_ids:
                try:
                    ref_uuid = UUID(ref_id_str)
                except ValueError:
                    continue
                ref = (
                    self.db.query(Reference)
                    .join(ProjectReference, ProjectReference.reference_id == Reference.id)
                    .filter(
                        ProjectReference.project_id == project.id,
                        Reference.id == ref_uuid,
                    )
                    .first()
                )
                if ref:
                    references.append(ref)

        elif scope == "focused":
            # Get focused papers from AI memory
            channel = ctx.get("channel")
            if channel:
                memory = self._get_ai_memory(channel)
                focused_papers = memory.get("focused_papers", [])
                for fp in focused_papers:
                    ref_id_str = fp.get("reference_id")
                    if not ref_id_str:
                        continue
                    try:
                        ref_uuid = UUID(ref_id_str)
                    except ValueError:
                        continue
                    ref = (
                        self.db.query(Reference)
                        .join(ProjectReference, ProjectReference.reference_id == Reference.id)
                        .filter(
                            ProjectReference.project_id == project.id,
                            Reference.id == ref_uuid,
                        )
                        .first()
                    )
                    if ref:
                        references.append(ref)

            if not references:
                return {
                    "status": "error",
                    "message": "No focused papers found. Use focus_on_papers first, or use scope='all' to export all library references.",
                }

        elif scope == "all":
            references = (
                self.db.query(Reference)
                .join(ProjectReference, ProjectReference.reference_id == Reference.id)
                .filter(ProjectReference.project_id == project.id)
                .limit(100)
                .all()
            )

        else:
            return {
                "status": "error",
                "message": "No references specified. Provide reference_ids with scope='selected', or use scope='focused' or scope='all'.",
            }

        if not references:
            return {
                "status": "error",
                "message": "No references found to export. Make sure your library has papers added.",
            }

        # Format citations
        used_keys: set = set()
        formatted_entries = []

        for ref in references:
            authors_str = (
                ref.authors
                if isinstance(ref.authors, str)
                else ", ".join(ref.authors or [])
            )
            title = ref.title or "Untitled"
            year = str(ref.year) if ref.year else "n.d."
            journal = ref.journal or ""
            doi = ref.doi or ""
            url = ref.url or ""

            paper_dict = {
                "title": title,
                "authors": authors_str,
                "year": ref.year,
            }
            cite_key = self._generate_citation_key(paper_dict, used_keys)

            if format == "bibtex":
                # Build BibTeX entry
                lines = [f"@article{{{cite_key},"]
                lines.append(f"  title = {{{title}}},")
                lines.append(f"  author = {{{authors_str}}},")
                lines.append(f"  year = {{{year}}},")
                if journal:
                    lines.append(f"  journal = {{{journal}}},")
                if doi:
                    lines.append(f"  doi = {{{doi}}},")
                if url:
                    lines.append(f"  url = {{{url}}},")
                lines.append("}")
                formatted_entries.append("\n".join(lines))

            elif format == "apa":
                # APA: Authors (Year). Title. Journal. doi
                parts = [f"{authors_str} ({year}). {title}."]
                if journal:
                    parts.append(f" *{journal}*.")
                if doi:
                    parts.append(f" https://doi.org/{doi}")
                formatted_entries.append("".join(parts))

            elif format == "mla":
                # MLA: Authors. "Title." Journal, Year.
                parts = [f'{authors_str}. "{title}."']
                if journal:
                    parts.append(f" *{journal}*,")
                parts.append(f" {year}.")
                formatted_entries.append("".join(parts))

            elif format == "chicago":
                # Chicago: Authors. "Title." Journal (Year). doi
                parts = [f'{authors_str}. "{title}."']
                if journal:
                    parts.append(f" *{journal}*")
                parts.append(f" ({year}).")
                if doi:
                    parts.append(f" https://doi.org/{doi}")
                formatted_entries.append("".join(parts))

        separator = "\n\n" if format == "bibtex" else "\n"
        citations_text = separator.join(formatted_entries)

        return {
            "status": "success",
            "format": format,
            "count": len(formatted_entries),
            "citations": citations_text,
        }

    def _tool_annotate_reference(
        self,
        ctx: Dict[str, Any],
        reference_id: str,
        note: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict:
        """Add a note or tags to a library reference for organization."""
        from datetime import datetime, timezone
        from uuid import UUID
        from app.models import Reference, ProjectReference

        project = ctx["project"]

        try:
            ref_uuid = UUID(reference_id)
        except ValueError:
            return {"status": "error", "message": "Invalid reference ID format."}

        # Query the ProjectReference (where annotations live) joined with Reference
        project_ref = (
            self.db.query(ProjectReference)
            .join(Reference, ProjectReference.reference_id == Reference.id)
            .filter(
                ProjectReference.project_id == project.id,
                ProjectReference.reference_id == ref_uuid,
            )
            .first()
        )

        if not project_ref:
            return {
                "status": "error",
                "message": "Reference not found in this project's library.",
            }

        if not note and not tags:
            return {
                "status": "error",
                "message": "Provide a note and/or tags to add to the reference.",
            }

        # Load or initialize annotations
        annotations = dict(project_ref.annotations or {})
        if "notes" not in annotations:
            annotations["notes"] = []
        if "tags" not in annotations:
            annotations["tags"] = []

        # Append note with timestamp
        if note:
            annotations["notes"].append({
                "text": note,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        # Merge tags (dedup)
        if tags:
            existing_tags = set(annotations["tags"])
            for tag in tags:
                tag = tag.strip().lower()
                if tag and tag not in existing_tags:
                    annotations["tags"].append(tag)
                    existing_tags.add(tag)

        # Save - assign new dict to trigger SQLAlchemy change detection
        project_ref.annotations = annotations

        try:
            self.db.commit()
            self.db.refresh(project_ref)

            # Get the reference title for the response
            ref = self.db.query(Reference).filter(Reference.id == ref_uuid).first()
            ref_title = ref.title if ref else "Unknown"

            return {
                "status": "success",
                "message": f"Annotated reference '{ref_title}'.",
                "annotations": {
                    "notes": annotations["notes"],
                    "tags": annotations["tags"],
                    "notes_count": len(annotations["notes"]),
                    "tags_count": len(annotations["tags"]),
                },
            }
        except Exception as e:
            self.db.rollback()
            logger.exception("Error annotating reference")
            return {
                "status": "error",
                "message": f"Failed to annotate reference: {str(e)}",
            }
