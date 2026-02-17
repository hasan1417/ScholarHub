from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.database import get_db
from app.models import (
    PaperMember,
    ProjectReference,
    Reference,
    ProjectRole,
    ResearchPaper,
    User,
)
from app.schemas.project_discussion import (
    BatchSearchRequest,
    BatchSearchResponse,
    DiscoveredPaperResponse,
    PaperActionRequest,
    PaperActionResponse,
    SearchReferencesRequest,
    SearchReferencesResponse,
    TopicResult,
)

router = APIRouter()

logger = logging.getLogger(__name__)


@router.post("/projects/{project_id}/discussion/paper-action")
def execute_paper_action(
    project_id: str,
    request: PaperActionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaperActionResponse:
    """Execute a paper action suggested by the discussion AI."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    if request.action_type == "create_paper":
        return _handle_create_paper(db, project, current_user, request.payload)
    elif request.action_type == "edit_paper":
        return _handle_edit_paper(db, project, current_user, request.payload)
    elif request.action_type == "add_reference":
        return _handle_add_reference(db, project, current_user, request.payload, background_tasks)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown action type: {request.action_type}"
        )


def _handle_create_paper(
    db: Session,
    project,
    user: User,
    payload: Dict[str, Any],
) -> PaperActionResponse:
    """Create a new paper from AI suggestion."""
    from app.constants.paper_templates import PAPER_TEMPLATES

    title = str(payload.get("title", "Untitled Paper")).strip()
    paper_type = str(payload.get("paper_type", "research")).strip()
    authoring_mode = str(payload.get("authoring_mode", "rich")).strip()  # Default to rich for AI content
    abstract = payload.get("abstract")
    objectives = payload.get("objectives", [])
    keywords = payload.get("keywords", [])
    initial_content = payload.get("content")  # AI-generated content

    # Ensure objectives is a list
    if not isinstance(objectives, list):
        objectives = []
    objectives = [str(obj).strip() for obj in objectives if obj]

    # Ensure keywords is a list
    if not isinstance(keywords, list):
        keywords = []
    keywords = [str(kw).strip() for kw in keywords if kw]

    # Validate paper_type
    valid_types = {"research", "review", "case_study"}
    if paper_type not in valid_types:
        paper_type = "research"

    # Validate authoring_mode
    if authoring_mode not in {"latex", "rich"}:
        authoring_mode = "rich"

    content = None
    content_json: Dict[str, Any] = {}

    # If AI provided initial content, use it directly
    if initial_content:
        if authoring_mode == "latex":
            content_json = {
                "authoring_mode": "latex",
                "latex_source": initial_content
            }
        else:
            content = initial_content
            content_json = {"authoring_mode": "rich"}
    else:
        # Fall back to template
        template = next(
            (t for t in PAPER_TEMPLATES if t["id"] == paper_type),
            PAPER_TEMPLATES[0] if PAPER_TEMPLATES else None
        )

        if template:
            if authoring_mode == "latex":
                content_json = {
                    "authoring_mode": "latex",
                    "latex_source": template.get("latexTemplate", "")
                }
            else:
                content = template.get("richTemplate", "")
                content_json = {"authoring_mode": "rich"}
        else:
            # Fallback if no template found
            if authoring_mode == "latex":
                content_json = {
                    "authoring_mode": "latex",
                    "latex_source": "\\documentclass{article}\n\\begin{document}\n\n\\end{document}"
                }
            else:
                content = "# " + title + "\n\n"
                content_json = {"authoring_mode": "rich"}

    # Use centralized paper service for creation + member + initial snapshot
    from app.services.paper_service import create_paper

    paper = create_paper(
        db=db,
        title=title,
        owner_id=user.id,
        project_id=project.id,
        content=content,
        content_json=content_json,
        abstract=abstract if abstract else None,
        paper_type=paper_type,
        status="draft",
        objectives=objectives if objectives else None,
        keywords=keywords if keywords else None,
        snapshot_label="AI-generated initial version",
    )

    logger.info(
        "Paper created via discussion AI: paper_id=%s title=%s type=%s mode=%s",
        paper.id, title, paper_type, authoring_mode
    )

    return PaperActionResponse(
        success=True,
        paper_id=str(paper.id),
        message=f"Created '{title}' ({paper_type}, {authoring_mode})"
    )


def _handle_edit_paper(
    db: Session,
    project,
    user: User,
    payload: Dict[str, Any],
) -> PaperActionResponse:
    """Apply an edit to an existing paper from AI suggestion."""
    paper_id = payload.get("paper_id")
    original = str(payload.get("original", "")).strip()
    proposed = str(payload.get("proposed", "")).strip()

    if not paper_id:
        return PaperActionResponse(success=False, message="Missing paper_id")
    if not original:
        return PaperActionResponse(success=False, message="Missing original text")
    if not proposed:
        return PaperActionResponse(success=False, message="Missing proposed text")
    if original == proposed:
        return PaperActionResponse(success=False, message="Original and proposed text are identical")

    # Find paper
    try:
        paper_uuid = UUID(str(paper_id))
    except ValueError:
        return PaperActionResponse(success=False, message="Invalid paper_id format")

    paper = db.query(ResearchPaper).filter(
        ResearchPaper.id == paper_uuid,
        ResearchPaper.project_id == project.id
    ).first()

    if not paper:
        return PaperActionResponse(success=False, message="Paper not found in project")

    # Check user has edit permission
    member = db.query(PaperMember).filter(
        PaperMember.paper_id == paper_uuid,
        PaperMember.user_id == user.id
    ).first()
    if not member and paper.owner_id != user.id:
        return PaperActionResponse(success=False, message="No permission to edit this paper")

    # Apply edit based on authoring mode
    if isinstance(paper.content_json, dict) and paper.content_json.get("authoring_mode") == "latex":
        latex_source = paper.content_json.get("latex_source", "")
        if original not in latex_source:
            return PaperActionResponse(
                success=False,
                message="Original text not found in paper. The content may have changed."
            )

        new_latex = latex_source.replace(original, proposed, 1)
        paper.content_json = {
            **paper.content_json,
            "latex_source": new_latex
        }
    else:
        if not paper.content or original not in paper.content:
            return PaperActionResponse(
                success=False,
                message="Original text not found in paper. The content may have changed."
            )

        paper.content = paper.content.replace(original, proposed, 1)

    db.commit()

    logger.info(
        "Paper edited via discussion AI: paper_id=%s original_len=%d proposed_len=%d",
        paper_id, len(original), len(proposed)
    )

    return PaperActionResponse(
        success=True,
        paper_id=str(paper.id),
        message="Edit applied successfully"
    )


def _handle_add_reference(
    db: Session,
    project,
    user: User,
    payload: Dict[str, Any],
    background_tasks: Optional[BackgroundTasks] = None,
) -> PaperActionResponse:
    """Add a discovered paper as a project reference."""
    title = payload.get("title")
    authors = payload.get("authors", [])
    year = payload.get("year")
    doi = payload.get("doi")
    url = payload.get("url")
    abstract = payload.get("abstract")
    source = payload.get("source")
    pdf_url = payload.get("pdf_url")
    is_open_access = payload.get("is_open_access", False)

    if not title:
        return PaperActionResponse(success=False, message="Title is required")

    # Normalize authors to list (Reference model expects ARRAY)
    authors_list = []
    if isinstance(authors, list):
        authors_list = [str(a) for a in authors if a]
    elif isinstance(authors, str) and authors:
        authors_list = [a.strip() for a in authors.split(",") if a.strip()]

    # Check for existing reference by DOI for this user
    existing_ref = None
    if doi:
        existing_ref = db.query(Reference).filter(
            Reference.doi == doi,
            Reference.owner_id == user.id
        ).first()

    if existing_ref:
        ref = existing_ref
        # Update pdf_url if not set and we have one now
        if pdf_url and not ref.pdf_url:
            ref.pdf_url = pdf_url
            ref.is_open_access = is_open_access
    else:
        # Create new reference with owner_id (required field)
        ref = Reference(
            title=title,
            authors=authors_list,
            year=year,
            doi=doi,
            url=url,
            abstract=abstract,
            source=source or "discussion_ai",
            owner_id=user.id,
            pdf_url=pdf_url,
            is_open_access=is_open_access
        )
        db.add(ref)
        db.flush()

    # Check if already linked to project
    existing_link = db.query(ProjectReference).filter(
        ProjectReference.project_id == project.id,
        ProjectReference.reference_id == ref.id
    ).first()

    if existing_link:
        return PaperActionResponse(
            success=True,  # Still success - reference exists
            reference_id=str(ref.id),
            message="Reference already exists in project"
        )

    # Link to project
    from app.models.project_reference import ProjectReferenceStatus, ProjectReferenceOrigin
    project_ref = ProjectReference(
        project_id=project.id,
        reference_id=ref.id,
        status=ProjectReferenceStatus.APPROVED,
        origin=ProjectReferenceOrigin.MANUAL_ADD
    )
    db.add(project_ref)
    db.commit()

    # Truncate title for message
    short_title = title[:50] + "..." if len(title) > 50 else title
    message = f"Added '{short_title}' to references"
    ingestion_status = None

    # Run PDF ingestion synchronously to return actual status
    if pdf_url:
        try:
            from app.services.reference_ingestion_service import ingest_reference_pdf
            success = ingest_reference_pdf(db, ref, owner_id=str(user.id))
            if success:
                ingestion_status = "success"
                message += " (PDF ingested for full-text analysis)"
            else:
                ingestion_status = "failed"
                message += " (PDF ingestion failed - you can upload manually)"
            logger.info("PDF ingestion for reference %s: %s", ref.id, ingestion_status)
        except Exception as e:
            logger.warning("PDF ingestion failed for reference %s: %s", ref.id, e)
            ingestion_status = "failed"
            message += " (PDF ingestion failed - you can upload manually)"
    else:
        ingestion_status = "no_pdf"
        message += " (no PDF available - abstract only)"

    logger.info(
        "Reference added via discussion AI: ref_id=%s title=%s project_id=%s ingestion=%s",
        ref.id, title[:50], project.id, ingestion_status
    )

    return PaperActionResponse(
        success=True,
        paper_id=str(ref.id),
        reference_id=str(ref.id),
        message=message,
        ingestion_status=ingestion_status
    )


@router.post("/projects/{project_id}/discussion/search-references")
async def search_references(
    project_id: str,
    request: SearchReferencesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SearchReferencesResponse:
    """Search for academic papers using the paper discovery service."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    from app.services.paper_discovery_service import PaperDiscoveryService

    # Default sources for discussion AI search (fast, reliable sources)
    sources = request.sources or ["arxiv", "semantic_scholar", "openalex", "crossref", "pubmed", "europe_pmc"]
    max_results = min(request.max_results, 20)  # Cap at 20 results

    # Create discovery service and search
    discovery_service = PaperDiscoveryService()

    try:
        # Request more results if filtering for open access, to ensure we get enough
        search_max = max_results * 3 if request.open_access_only else max_results

        result = await discovery_service.discover_papers(
            query=request.query,
            max_results=search_max,
            sources=sources,
            fast_mode=True,  # Use fast mode for chat responsiveness
        )

        # Filter for open access if requested
        source_papers = result.papers
        if request.open_access_only:
            source_papers = [p for p in source_papers if p.pdf_url or p.open_access_url]

        # Convert to response format
        papers = []
        for idx, p in enumerate(source_papers[:max_results]):
            # Create unique ID for frontend tracking using DOI or index
            unique_key = p.get_unique_key() if hasattr(p, 'get_unique_key') else str(idx)
            paper_id = f"{p.source}:{unique_key}"

            # Parse authors
            authors_list = []
            if p.authors:
                if isinstance(p.authors, list):
                    authors_list = [str(a) for a in p.authors]
                elif isinstance(p.authors, str):
                    authors_list = [a.strip() for a in p.authors.split(",")]

            papers.append(DiscoveredPaperResponse(
                id=paper_id,
                title=p.title,
                authors=authors_list,
                year=p.year,
                abstract=p.abstract[:500] if p.abstract else None,
                doi=p.doi,
                url=p.url,
                source=p.source,
                relevance_score=p.relevance_score,
                pdf_url=p.pdf_url or p.open_access_url,
                is_open_access=p.is_open_access,
                journal=p.journal,
            ))

        # Ensure we never return more than requested (defensive limit)
        final_papers = papers[:max_results]

        return SearchReferencesResponse(
            papers=final_papers,
            total_found=len(result.papers),
            query=request.query
        )
    finally:
        await discovery_service.close()


@router.post("/projects/{project_id}/discussion/batch-search-references")
async def batch_search_references(
    project_id: str,
    request: BatchSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchSearchResponse:
    """
    Search for academic papers across multiple topics in one call.
    Returns results grouped by topic for easy consumption.
    """
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    from app.services.paper_discovery_service import PaperDiscoveryService

    # Limit to 5 topics max per request
    queries = request.queries[:5]
    sources = ["arxiv", "semantic_scholar", "openalex", "crossref", "pubmed", "europe_pmc"]

    results: List[TopicResult] = []
    total_found = 0

    # Track seen papers across topics for deduplication
    seen_keys: set = set()

    discovery_service = PaperDiscoveryService()

    try:
        for topic_query in queries:
            max_results = min(topic_query.max_results, 10)  # Cap per topic
            search_max = max_results * 2 if request.open_access_only else max_results

            result = await discovery_service.discover_papers(
                query=topic_query.query,
                max_results=search_max,
                sources=sources,
                fast_mode=True,
            )

            # Filter for open access if requested
            source_papers = result.papers
            if request.open_access_only:
                source_papers = [p for p in source_papers if p.pdf_url or p.open_access_url]

            # Convert to response format with cross-topic deduplication
            papers = []
            for idx, p in enumerate(source_papers[:max_results]):
                unique_key = p.get_unique_key() if hasattr(p, 'get_unique_key') else f"{topic_query.topic}:{idx}"

                # Skip if already seen in another topic
                if unique_key in seen_keys:
                    continue
                seen_keys.add(unique_key)

                paper_id = f"{p.source}:{unique_key}"

                # Parse authors
                authors_list = []
                if p.authors:
                    if isinstance(p.authors, list):
                        authors_list = [str(a) for a in p.authors]
                    elif isinstance(p.authors, str):
                        authors_list = [a.strip() for a in p.authors.split(",")]

                papers.append(DiscoveredPaperResponse(
                    id=paper_id,
                    title=p.title,
                    authors=authors_list,
                    year=p.year,
                    abstract=p.abstract[:500] if p.abstract else None,
                    doi=p.doi,
                    url=p.url,
                    source=p.source,
                    relevance_score=p.relevance_score,
                    pdf_url=p.pdf_url or p.open_access_url,
                    is_open_access=p.is_open_access,
                    journal=p.journal,
                ))

            results.append(TopicResult(
                topic=topic_query.topic,
                query=topic_query.query,
                papers=papers,
                count=len(papers)
            ))
            total_found += len(papers)

        return BatchSearchResponse(
            results=results,
            total_found=total_found
        )
    finally:
        await discovery_service.close()
