"""
Paper Discovery API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
import logging
import time
import aiohttp
import os
import json
from starlette.responses import StreamingResponse
import asyncio
import re
import io

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.research_paper import ResearchPaper
from app.services.paper_discovery_service import PaperDiscoveryService, DiscoveredPaper
from app.services.literature_review_service import LiteratureReviewService, LiteratureReview
from app.services.university_proxy_access import UniversityProxyService
from app.services.enhanced_paper_access import EnhancedPaperAccessService
from app.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


# -------- Informative Context Fusion Helpers --------
_STOPWORDS = {
    'the','and','for','that','with','this','from','are','was','were','been','being','have','has','had',
    'into','onto','about','over','under','between','among','across','after','before','during','without',
    'using','use','used','we','our','their','they','it','its','on','in','of','to','by','at','as','an','a',
    'is','am','be','or','not','no','yes','can','could','may','might','should','would','do','does','did',
    'paper','study','approach','method','methods','result','results','show','shows','showed','present',
    'presented','conclusion','conclusions','based','data'
}

def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _tokenize_words(s: str) -> list[str]:
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    toks = [w for w in s.split() if len(w) > 2 and w not in _STOPWORDS]
    # limit tokens to keep operations light
    return toks[:512]

def _build_focus_tokens(title: str | None, abstract: str | None, keywords: list[str] | None) -> set[str]:
    pool = []
    if title: pool.append(title)
    if abstract: pool.append(abstract)
    if keywords:
        try:
            pool.append(" ".join([k for k in keywords if isinstance(k, str)]))
        except Exception:
            pass
    toks = []
    for part in pool:
        toks.extend(_tokenize_words(part))
    # unique
    return set(toks)

def _split_sentences(text: str) -> list[str]:
    # Basic sentence splitter
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

def _sentence_length_bonus(n_words: int) -> float:
    # Prefer 10-35 words
    if 10 <= n_words <= 35:
        return 0.5
    if 7 <= n_words < 10 or 35 < n_words <= 50:
        return 0.25
    return 0.0

def _contains_signal_phrase(s: str) -> float:
    s = s.lower()
    phrases = [
        'we propose','we present','we introduce','our method','our approach','we show','we demonstrate',
        'in this paper','our contributions','we evaluate','results show','we investigate','we analyze'
    ]
    return 0.3 if any(p in s for p in phrases) else 0.0

def _select_informative_sentences(content_text: str, focus_tokens: set[str], max_chars: int, max_sentences: int = 12) -> str:
    text = _normalize_ws(content_text)
    sentences = _split_sentences(text)
    scored: list[tuple[float, str]] = []
    ft = set(list(focus_tokens)[:256])
    for sent in sentences:
        toks = set(_tokenize_words(sent))
        if not toks:
            continue
        overlap = len(toks & ft)
        if overlap == 0:
            # still allow signal phrases
            base = _contains_signal_phrase(sent)
        else:
            base = float(overlap)
        bonus = _sentence_length_bonus(len(toks)) + _contains_signal_phrase(sent)
        score = base + bonus
        if score > 0:
            scored.append((score, sent))
    if not scored:
        return text[:max_chars]
    scored.sort(key=lambda x: x[0], reverse=True)
    picked: list[str] = []
    total = 0
    for _, s in scored:
        if s in picked:
            continue
        if total + len(s) + 1 > max_chars:
            continue
        picked.append(s)
        total += len(s) + 1
        if len(picked) >= max_sentences:
            break
    return " ".join(picked)[:max_chars]


def _fuse_context(title: Optional[str], abstract: Optional[str], keywords: Optional[List[str]], content_text: Optional[str], max_chars: int) -> str:
    """Fuse title/abstract/keywords/content into a concise context string.
    Uses informative sentence selection for content with focus tokens derived from the metadata.
    """
    parts: List[str] = []
    if title:
        parts.append(f"Title: {title.strip()}")
    if abstract:
        ab = abstract.strip()
        parts.append(f"Abstract: {ab[:1000]}")
    dedup_keywords: Optional[List[str]] = None
    if keywords:
        try:
            uniq: List[str] = []
            seen = set()
            for kw in keywords:
                if isinstance(kw, str):
                    k = kw.strip()
                    if k and k.lower() not in seen:
                        seen.add(k.lower())
                        uniq.append(k)
            if uniq:
                dedup_keywords = uniq[:20]
                parts.append("Keywords: " + ", ".join(dedup_keywords))
        except Exception:
            dedup_keywords = None
    if content_text:
        try:
            focus = _build_focus_tokens(title, abstract, dedup_keywords)
            budget = max(800, min(2000, max_chars - sum(len(p) for p in parts) - 100))
            excerpt = _select_informative_sentences(content_text, focus, budget)
            if excerpt:
                parts.append("Content Excerpt: " + excerpt)
        except Exception:
            # Fallback to normalized slice
            parts.append("Content Excerpt: " + _normalize_ws(content_text)[:min(2000, max_chars)])
    fused = "\n\n".join([p for p in parts if p])
    return fused[:max_chars]


# Request/Response Models
class PaperDiscoveryRequest(BaseModel):
    # Mode selection
    mode: str = Field(default="query", pattern="^(query|paper)$", description="Discovery mode: query or paper")

    # Query mode
    query: Optional[str] = Field(None, min_length=3, max_length=500, description="Search query for papers")
    research_topic: Optional[str] = Field(None, max_length=500, description="Broader research context")

    # Paper mode
    paper_id: Optional[str] = Field(None, description="Source paper ID to find similar papers")
    paper_text: Optional[str] = Field(None, description="Free-form text to use as discovery context")
    use_content: bool = Field(default=True, description="Include paper content/content_json when building context")
    max_context_chars: int = Field(default=4000, ge=500, le=20000, description="Max characters from paper to use in context")

    # Common controls
    max_results: int = Field(20, ge=5, le=100, description="Maximum number of results")
    sources: Optional[List[str]] = Field(
        default=None,
        description="Sources to search: arxiv, semantic_scholar, crossref, pubmed, openalex, sciencedirect"
    )
    include_breakdown: bool = Field(default=False, description="Include per-source result counts for debugging")


class DiscoveredPaperResponse(BaseModel):
    title: str
    authors: List[str]
    abstract: Optional[str] = None
    year: Optional[int]
    doi: Optional[str]
    url: Optional[str]
    source: str
    relevance_score: float
    citations_count: Optional[int]
    journal: Optional[str]
    keywords: Optional[List[str]]
    # Unpaywall data
    is_open_access: bool = False
    open_access_url: Optional[str] = None
    pdf_url: Optional[str] = None


class PaperDiscoveryResponse(BaseModel):
    papers: List[DiscoveredPaperResponse]
    total_found: int
    query: Optional[str] = None
    enhanced_queries: Optional[List[str]] = None
    search_time: float
    sources_raw_counts: Optional[Dict[str, int]] = None
    sources_unique_counts: Optional[Dict[str, int]] = None


class AddPaperFromDiscoveryRequest(BaseModel):
    title: str
    authors: List[str]
    abstract: str = ""
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    source: str
    keywords: Optional[List[str]] = None


class LiteratureReviewRequest(BaseModel):
    paper_ids: List[str] = Field(..., min_items=2, description="Paper IDs to include in review")
    review_topic: str = Field(..., min_length=10, max_length=500, description="Main topic for the review")
    review_type: str = Field(default="systematic", pattern="^(systematic|narrative|scoping)$")
    max_sections: int = Field(default=6, ge=3, le=10, description="Maximum number of main sections")


class LiteratureReviewResponse(BaseModel):
    title: str
    abstract: str
    introduction: str
    methodology: str
    sections: List[dict]  # Will contain ReviewSection data
    synthesis: str
    research_gaps: List[str]
    future_directions: List[str]
    conclusion: str
    references: List[str]
    total_papers: int
    generation_time: float


class SourceDebugRequest(BaseModel):
    source: str = Field(..., pattern="^(semantic_scholar|sciencedirect|openalex)$")
    query: str = Field(..., min_length=3, max_length=500)
    limit: int = Field(5, ge=1, le=25)


class SourceDebugResponse(BaseModel):
    source: str
    status: int | None = None
    elapsed_ms: float | None = None
    api_key_present: bool | None = None
    request_headers_used: Optional[List[str]] = None
    params_used: Optional[dict] = None
    items_count: int | None = None
    sample_titles: Optional[List[str]] = None
    raw_excerpt: str | None = None
    error: str | None = None


class PublisherProbeRequest(BaseModel):
    url: Optional[str] = None
    doi: Optional[str] = None
    title: Optional[str] = None
    with_unpaywall: bool = False

class PublisherProbeResponse(BaseModel):
    target: str
    resolved_url: Optional[str] = None
    proxied_url: Optional[str] = None
    provider_search_urls: Optional[List[Dict[str, str]]] = None
    proxy_fetch: Optional[Dict[str, Optional[str] | int | float]] = None
    unpaywall: Optional[Dict[str, Optional[str] | bool]] = None


class PaperContentRequest(BaseModel):
    url: str = Field(..., description="URL of the paper to fetch content from")
    paper_title: Optional[str] = Field(None, description="Title of the paper for context")


class PaperContentResponse(BaseModel):
    success: bool
    content_type: str  # 'pdf', 'html', 'abstract_only'
    title: Optional[str] = None
    abstract: Optional[str] = None
    full_text: Optional[str] = None
    pdf_url: Optional[str] = None
    html_content: Optional[str] = None
    error: Optional[str] = None


router = APIRouter()


@router.post("/papers/discover", response_model=PaperDiscoveryResponse)
async def discover_papers(
    request: PaperDiscoveryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Discover research papers using multiple academic sources and AI-powered relevance ranking
    """
    # Check subscription limit for paper discovery searches
    allowed, current, limit = SubscriptionService.check_feature_limit(
        db, current_user.id, "paper_discovery_searches"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "limit_exceeded",
                "feature": "paper_discovery_searches",
                "current": current,
                "limit": limit,
                "message": f"You have reached your paper discovery limit ({current}/{limit} searches this month). Upgrade to Pro for more searches.",
            },
        )

    try:
        req_start = time.time()
        logger.info(f"Paper discovery request from user {current_user.id}: '{request.query}'")
        
        # Validate sources
        valid_sources = ['arxiv', 'semantic_scholar', 'crossref', 'pubmed', 'openalex', 'sciencedirect']
        if request.sources:
            invalid_sources = set(request.sources) - set(valid_sources)
            if invalid_sources:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid sources: {list(invalid_sources)}. Valid sources: {valid_sources}"
                )
        
        # Build optional paper context
        target_text: Optional[str] = None
        target_keywords: Optional[List[str]] = None

        if request.mode == 'paper':
            from app.models.paper_member import PaperMember
            
            def _fuse_context(title: Optional[str], abstract: Optional[str], keywords: Optional[List[str]], content_text: Optional[str], max_chars: int) -> str:
                parts: List[str] = []
                if title:
                    parts.append(f"Title: {title.strip()}")
                if abstract:
                    ab = abstract.strip()
                    parts.append(f"Abstract: {ab[:1000]}")
                dedup_keywords: Optional[List[str]] = None
                if keywords:
                    try:
                        uniq = []
                        seen = set()
                        for kw in keywords:
                            if isinstance(kw, str):
                                k = kw.strip()
                                if k and k.lower() not in seen:
                                    seen.add(k.lower())
                                    uniq.append(k)
                        if uniq:
                            dedup_keywords = uniq[:20]
                            parts.append("Keywords: " + ", ".join(dedup_keywords))
                    except Exception:
                        pass
                if content_text:
                    try:
                        focus = _build_focus_tokens(title, abstract, dedup_keywords)
                        budget = max(800, min(2000, max_chars - sum(len(p) for p in parts) - 100))
                        excerpt = _select_informative_sentences(content_text, focus, budget)
                        if excerpt:
                            parts.append("Content Excerpt: " + excerpt)
                    except Exception:
                        # Fallback to normalized slice
                        parts.append("Content Excerpt: " + _normalize_ws(content_text)[:min(2000, max_chars)])
                fused = "\n\n".join([p for p in parts if p])
                return fused[:max_chars]
            # If paper_text provided, use it; otherwise fetch paper by ID
            if request.paper_text and request.paper_text.strip():
                # Treat provided text as content excerpt; we still fuse a header for consistency
                provided = request.paper_text.strip()[: request.max_context_chars]
                target_text = _fuse_context(None, None, None, provided, request.max_context_chars)
            else:
                if not request.paper_id:
                    raise HTTPException(status_code=400, detail="paper_id or paper_text is required in paper mode")
                paper = db.query(ResearchPaper).filter(ResearchPaper.id == request.paper_id).first()
                if not paper:
                    raise HTTPException(status_code=404, detail="Paper not found")
                # Access: owner or accepted member
                if paper.owner_id != current_user.id:
                    member = db.query(PaperMember).filter(
                        PaperMember.paper_id == request.paper_id,
                        PaperMember.user_id == current_user.id,
                        PaperMember.status == "accepted"
                    ).first()
                    if not member:
                        raise HTTPException(status_code=403, detail="Access denied")

                content_text: Optional[str] = None
                if request.use_content:
                    if paper.content:
                        content_text = (paper.content or '')
                    elif paper.content_json:
                        try:
                            def _walk(n):
                                if isinstance(n, dict):
                                    t = []
                                    if 'text' in n and isinstance(n['text'], str):
                                        t.append(n['text'])
                                    for ch in n.get('content', []) or []:
                                        t.append(_walk(ch))
                                    return ' '.join([x for x in t if x])
                                if isinstance(n, list):
                                    return ' '.join([_walk(x) for x in n])
                                return ''
                            content_text = _walk(paper.content_json)
                        except Exception:
                            content_text = None
                if paper.keywords:
                    try:
                        target_keywords = [kw for kw in list(paper.keywords or []) if isinstance(kw, str)]
                    except Exception:
                        target_keywords = None
                target_text = _fuse_context(paper.title, paper.abstract, target_keywords, content_text, request.max_context_chars)

        # Determine effective query for candidate generation
        effective_query = (request.query or '').strip()
        if request.mode == 'paper' and not effective_query:
            # Build a simple seed query from title/keywords/first tokens of context
            if target_keywords:
                effective_query = ' '.join(target_keywords[:6])
            elif target_text:
                try:
                    import re as _re
                    toks = [w for w in _re.sub(r"[^a-zA-Z0-9\s]", " ", target_text).split() if len(w) > 2]
                    effective_query = ' '.join(toks[:8]) if toks else ''
                except Exception:
                    effective_query = ''

        # Perform discovery
        async with PaperDiscoveryService() as discovery_service:
            result = await discovery_service.discover_papers(
                query=effective_query,
                max_results=request.max_results,
                sources=request.sources,
                target_text=target_text or request.research_topic,
                target_keywords=target_keywords
            )
            discovered_papers = result.papers if hasattr(result, 'papers') else result

        # Convert to response format
        paper_responses = []
        for paper in discovered_papers:
            paper_responses.append(DiscoveredPaperResponse(
                title=paper.title,
                authors=paper.authors,
                abstract=paper.abstract,
                year=paper.year,
                doi=paper.doi,
                url=paper.url,
                source=paper.source,
                relevance_score=paper.relevance_score,
                citations_count=paper.citations_count,
                journal=paper.journal,
                keywords=paper.keywords,
                is_open_access=paper.is_open_access,
                open_access_url=paper.open_access_url,
                pdf_url=paper.pdf_url
            ))
        
        elapsed = time.time() - req_start
        logger.info(f"Discovery completed: {len(paper_responses)} papers found in {elapsed:.2f}s")

        # Increment usage counter after successful discovery
        SubscriptionService.increment_usage(db, current_user.id, "paper_discovery_searches")

        return PaperDiscoveryResponse(
            papers=paper_responses,
            total_found=len(paper_responses),
            query=request.query,
            search_time=elapsed,
            sources_raw_counts=discovery_service.last_raw_counts if request.include_breakdown else None,
            sources_unique_counts=discovery_service.last_unique_counts if request.include_breakdown else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in paper discovery: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Paper discovery failed: {str(e)}"
        )


@router.post("/papers/add-from-discovery", response_model=dict)
async def add_paper_from_discovery(
    request: AddPaperFromDiscoveryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a discovered paper to user's research library
    """
    try:
        logger.info(f"Adding discovered paper to library for user {current_user.id}: '{request.title}'")
        
        # Check if paper already exists (by DOI or title similarity)
        existing_paper = None
        if request.doi:
            existing_paper = db.query(ResearchPaper).filter(
                ResearchPaper.doi == request.doi,
                ResearchPaper.owner_id == current_user.id
            ).first()
        
        if not existing_paper:
            # Simple title similarity check
            similar_paper = db.query(ResearchPaper).filter(
                ResearchPaper.title.ilike(f"%{request.title[:50]}%"),
                ResearchPaper.owner_id == current_user.id
            ).first()
            
            if similar_paper:
                existing_paper = similar_paper
        
        if existing_paper:
            return {
                "success": False,
                "message": "Paper already exists in your library",
                "paper_id": existing_paper.id
            }
        
        # Create new paper
        new_paper = ResearchPaper(
            title=request.title,
            description=request.abstract[:500] if request.abstract else "",  # Use abstract as description
            owner_id=current_user.id,
            year=request.year,
            doi=request.doi,
            url=request.url,
            source=request.source,
            authors=request.authors,
            abstract=request.abstract,
            keywords=request.keywords or []
        )
        
        db.add(new_paper)
        db.commit()
        db.refresh(new_paper)
        
        logger.info(f"Successfully added paper {new_paper.id} to user {current_user.id}'s library")
        
        return {
            "success": True,
            "message": "Paper successfully added to your library",
            "paper_id": new_paper.id
        }
        
    except Exception as e:
        logger.error(f"Failed to add paper from discovery for user {current_user.id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add paper to library"
        )


@router.post("/debug/test-source", response_model=SourceDebugResponse)
async def debug_test_source(
    request: SourceDebugRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        async with PaperDiscoveryService() as svc:
            result = await svc.debug_source(request.source, request.query, request.limit)
            if 'error' in result and not result.get('status'):
                # Normalize error-only cases
                return SourceDebugResponse(
                    source=request.source,
                    error=result.get('error')
                )
            return SourceDebugResponse(**result)
    except Exception as e:
        logger.error(f"Debug test for source {request.source} failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/literature-review/generate", response_model=LiteratureReviewResponse)
async def generate_literature_review(
    request: LiteratureReviewRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate an automated literature review from selected papers
    """
    try:
        logger.info(f"Literature review generation request from user {current_user.id}")
        logger.info(f"Papers: {len(request.paper_ids)}, Topic: '{request.review_topic}', Type: {request.review_type}")
        
        # Verify user has access to all requested papers
        accessible_papers = db.query(ResearchPaper).filter(
            ResearchPaper.id.in_(request.paper_ids),
            ResearchPaper.owner_id == current_user.id
        ).all()
        
        if len(accessible_papers) != len(request.paper_ids):
            missing_count = len(request.paper_ids) - len(accessible_papers)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{missing_count} paper(s) not found or not accessible"
            )
        
        if len(accessible_papers) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least 2 papers are required for literature review generation"
            )
        
        # Generate literature review
        review_service = LiteratureReviewService()
        literature_review = await review_service.generate_literature_review(
            db=db,
            paper_ids=request.paper_ids,
            review_topic=request.review_topic,
            user_id=str(current_user.id),
            review_type=request.review_type,
            max_sections=request.max_sections
        )
        
        # Convert sections to dict format
        sections_dict = []
        for section in literature_review.sections:
            sections_dict.append({
                "title": section.title,
                "content": section.content,
                "papers_cited": section.papers_cited,
                "themes": section.themes
            })
        
        logger.info(f"Literature review generated successfully in {literature_review.generation_time:.2f}s")
        
        return LiteratureReviewResponse(
            title=literature_review.title,
            abstract=literature_review.abstract,
            introduction=literature_review.introduction,
            methodology=literature_review.methodology,
            sections=sections_dict,
            synthesis=literature_review.synthesis,
            research_gaps=literature_review.research_gaps,
            future_directions=literature_review.future_directions,
            conclusion=literature_review.conclusion,
            references=literature_review.references,
            total_papers=literature_review.total_papers,
            generation_time=literature_review.generation_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating literature review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Literature review generation failed: {str(e)}"
        )


@router.get("/papers/trending")
async def get_trending_papers(
    field: Optional[str] = None,
    days: int = 30,
    limit: int = 10,
    current_user: User = Depends(get_current_user)
):
    """
    Get trending papers in a specific field (future enhancement)
    """
    # Placeholder for trending papers functionality
    return {
        "message": "Trending papers feature coming soon",
        "field": field,
        "days": days,
        "limit": limit
    }


@router.post("/papers/discover/stream")
async def discover_papers_stream(
    request: PaperDiscoveryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Stream discovered papers incrementally as they are returned from sources.
    Emits Server-Sent Events (SSE) with events of the form:
      data: {"type":"final","papers":[...],"total": N,"search_time": seconds}\n\n
    This endpoint delegates to the orchestrated PaperDiscoveryService to ensure
    consistent source filtering and ranking.
    """
    # Check subscription limit for paper discovery searches
    allowed, current, limit = SubscriptionService.check_feature_limit(
        db, current_user.id, "paper_discovery_searches"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "limit_exceeded",
                "feature": "paper_discovery_searches",
                "current": current,
                "limit": limit,
                "message": f"You have reached your paper discovery limit ({current}/{limit} searches this month). Upgrade to Pro for more searches.",
            },
        )

    async def event_stream():
        start_ts = time.time()
        try:
            # Handle case where query might be None but research_topic exists
            effective_query = request.query or request.research_topic or ''
            logger.info(f"🎯 Discovery stream called with query='{request.query}', research_topic='{request.research_topic}', sources={request.sources}, mode={request.mode}")
            logger.info(f"📋 Sources breakdown: {', '.join(request.sources) if request.sources else 'NO SOURCES'}")

            async with PaperDiscoveryService() as svc:
                discovery_result = await svc.discover_papers(
                    query=effective_query,
                    max_results=request.max_results,
                    target_text=request.paper_text or request.research_topic,
                    sources=request.sources,
                    debug=False # Consider making this configurable
                )
                papers = discovery_result.papers if hasattr(discovery_result, 'papers') else discovery_result

                # Stream results as a single batch
                batch = []
                for p in papers:
                    batch.append({
                        'title': p.title,
                        'authors': p.authors,
                        'abstract': p.abstract or '',
                        'year': p.year,
                        'doi': p.doi,
                        'url': p.url,
                        'source': p.source,
                        'relevance_score': p.relevance_score,
                        'citations_count': p.citations_count,
                        'journal': p.journal,
                        'keywords': p.keywords,
                        'is_open_access': getattr(p, 'is_open_access', False),
                        'open_access_url': getattr(p, 'open_access_url', None),
                        'pdf_url': getattr(p, 'pdf_url', None),
                    })

                payload = {'type': 'final', 'papers': batch, 'total': len(batch), 'search_time': time.time() - start_ts}
                yield f"data: {json.dumps(payload)}\n\n"

                # Increment usage counter after successful discovery (streaming)
                try:
                    from app.database import SessionLocal
                    streaming_db = SessionLocal()
                    SubscriptionService.increment_usage(streaming_db, current_user.id, "paper_discovery_searches")
                    streaming_db.close()
                except Exception as e:
                    logger.error(f"Failed to increment discovery usage for user {current_user.id}: {e}")

        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'done', 'total': 0, 'timeout': True})}\n\n"
        except Exception as e:
            logger.error(f"Discovery stream failed: {str(e)}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


class ScoreDebugItem(BaseModel):
    title: str
    source: str
    year: Optional[int] = None
    citations_count: Optional[int] = None
    service_score: float
    lexical_score: float
    components: Dict[str, float]


class ScoreDebugResponse(BaseModel):
    items: List[ScoreDebugItem]
    count: int
    query_used: Optional[str] = None


@router.post("/papers/score-debug", response_model=ScoreDebugResponse)
async def score_debug(
    request: PaperDiscoveryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return lexical relevance components for discovered papers to inspect scoring reliability."""
    # Build effective context as in non-stream path
    target_text: Optional[str] = None
    target_keywords: Optional[List[str]] = None
    effective_query = (request.query or '').strip()

    if request.mode == 'paper':
        if request.paper_text and request.paper_text.strip():
            provided = request.paper_text.strip()
            target_text = _normalize_ws(provided)[: request.max_context_chars]
        elif request.paper_id:
            paper = db.query(ResearchPaper).filter(ResearchPaper.id == request.paper_id).first()
            if paper:
                # Access control (best-effort)
                from app.models.paper_member import PaperMember
                if paper.owner_id != current_user.id:
                    member = db.query(PaperMember).filter(
                        PaperMember.paper_id == request.paper_id,
                        PaperMember.user_id == current_user.id,
                        PaperMember.status == "accepted"
                    ).first()
                    if not member:
                        paper = None
                if paper:
                    content_text = None
                    if request.use_content:
                        try:
                            if paper.content:
                                content_text = paper.content
                            elif paper.content_json:
                                def _walk(n):
                                    if isinstance(n, dict):
                                        if n.get('type') == 'text' and 'text' in n:
                                            return n['text']
                                        return ' '.join(_walk(v) for v in n.values())
                                    if isinstance(n, list):
                                        return ' '.join(_walk(x) for x in n)
                                    return ''
                                content_text = _walk(paper.content_json)
                        except Exception:
                            content_text = None
                    if paper.keywords:
                        try:
                            target_keywords = [kw for kw in list(paper.keywords or []) if isinstance(kw, str)]
                        except Exception:
                            target_keywords = None
                    target_text = _fuse_context(paper.title, paper.abstract, target_keywords, content_text, request.max_context_chars)
        # Build a seed query if none provided
        if not effective_query:
            if target_keywords:
                effective_query = ' '.join(target_keywords[:6])
            elif target_text:
                try:
                    toks = [w for w in re.sub(r"[^a-zA-Z0-9\s]", " ", target_text).split() if len(w) > 2]
                    effective_query = ' '.join(toks[:8]) if toks else ''
                except Exception:
                    effective_query = ''

    # Run discovery (non-stream)
    async with PaperDiscoveryService() as svc:
        discovery_result = await svc.discover_papers(
            query=effective_query,
            max_results=request.max_results,
            sources=request.sources,
            target_text=target_text or request.research_topic,
            target_keywords=target_keywords
        )
        papers = discovery_result.papers if hasattr(discovery_result, 'papers') else discovery_result

    # Compute lexical components
    def _tokenize_set(s: str) -> set:
        s2 = (s or '').lower()
        s2 = re.sub(r"[^a-z0-9\s]", " ", s2)
        return set([w for w in s2.split() if len(w) > 2])

    if target_text and target_text.strip():
        qset = _tokenize_set(target_text)
    else:
        qset = _tokenize_set(effective_query or '')
    kwset = set([kw.lower() for kw in (target_keywords or []) if isinstance(kw, str)])

    items: List[ScoreDebugItem] = []
    for p in papers:
        title_set = _tokenize_set(getattr(p, 'title', '') or '')
        abs_set = _tokenize_set(getattr(p, 'abstract', '') or '')
        title_overlap = (len(title_set & qset) / max(1, len(title_set))) if title_set and qset else 0.0
        abs_overlap = (len(abs_set & qset) / max(1, len(abs_set))) if abs_set and qset else 0.0
        kw_title = (len(title_set & kwset) / max(1, len(kwset))) if kwset else 0.0
        kw_body = (len(abs_set & kwset) / max(1, len(kwset))) if kwset else 0.0
        # recency/citations small boosts
        recency = 0.0
        try:
            if getattr(p, 'year', None):
                age = max(0, time.gmtime().tm_year - int(getattr(p, 'year')))
                recency = max(0.0, min(0.10, 0.10 * (2.71828 ** (-age/6.0))))
        except Exception:
            recency = 0.0
        citations = 0.0
        try:
            c = getattr(p, 'citations_count', None)
            if c and c > 0:
                import math as _m
                citations = min(0.08, 0.02 * _m.log(1.0 + float(c)))
        except Exception:
            citations = 0.0
        pdf = 0.01 if getattr(p, 'pdf_url', None) else 0.0

        lex = 0.5*title_overlap + 0.3*abs_overlap + 0.1*kw_title + 0.05*kw_body + recency + citations + pdf
        lex = max(0.0, min(1.0, lex))
        items.append(ScoreDebugItem(
            title=p.title,
            source=p.source,
            year=p.year,
            citations_count=p.citations_count,
            service_score=float(getattr(p, 'relevance_score', 0.0) or 0.0),
            lexical_score=lex,
            components={
                "title_overlap": round(title_overlap, 4),
                "abstract_overlap": round(abs_overlap, 4),
                "kw_title": round(kw_title, 4),
                "kw_body": round(kw_body, 4),
                "recency": round(recency, 4),
                "citations": round(citations, 4),
                "pdf": round(pdf, 4)
            }
        ))

    return ScoreDebugResponse(items=items, count=len(items), query_used=effective_query or None)


# ===== Deep Rescore PDFs =====

class RescoreItem(BaseModel):
    title: str
    authors: Optional[List[str]] = None
    abstract: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    pdf_url: Optional[str] = None
    relevance_score: Optional[float] = None
    citations_count: Optional[int] = None
    journal: Optional[str] = None
    keywords: Optional[List[str]] = None

class DeepRescoreRequest(BaseModel):
    mode: str = Field(default="query", pattern="^(query|paper)$")
    query: Optional[str] = None
    paper_id: Optional[str] = None
    paper_text: Optional[str] = None
    use_content: bool = True
    max_context_chars: int = 4000
    items: List[RescoreItem]
    top_n: int = 10

class DeepRescoreResponse(BaseModel):
    items: List[Dict]
    rescored: int
    method: str


@router.post("/papers/deep-rescore", response_model=DeepRescoreResponse)
async def deep_rescore_pdfs(
    request: DeepRescoreRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deep rescore top-N items using PDF content similarity (embeddings when available)."""
    # Build fused context
    target_text: Optional[str] = None
    target_keywords: Optional[List[str]] = None
    effective_query = (request.query or '').strip()

    if request.mode == 'paper':
        if request.paper_text and request.paper_text.strip():
            provided = request.paper_text.strip()
            target_text = _normalize_ws(provided)[: request.max_context_chars]
        elif request.paper_id:
            paper = db.query(ResearchPaper).filter(ResearchPaper.id == request.paper_id).first()
            if paper:
                # access check best-effort
                from app.models.paper_member import PaperMember
                if paper.owner_id != current_user.id:
                    member = db.query(PaperMember).filter(
                        PaperMember.paper_id == request.paper_id,
                        PaperMember.user_id == current_user.id,
                        PaperMember.status == "accepted"
                    ).first()
                    if not member:
                        paper = None
                if paper:
                    content_text = None
                    if request.use_content:
                        try:
                            if paper.content:
                                content_text = paper.content
                            elif paper.content_json:
                                def _walk(n):
                                    if isinstance(n, dict):
                                        if n.get('type') == 'text' and 'text' in n:
                                            return n['text']
                                        return ' '.join(_walk(v) for v in n.values())
                                    if isinstance(n, list):
                                        return ' '.join(_walk(x) for x in n)
                                    return ''
                                content_text = _walk(paper.content_json)
                        except Exception:
                            content_text = None
                    if paper.keywords:
                        try:
                            target_keywords = [kw for kw in list(paper.keywords or []) if isinstance(kw, str)]
                        except Exception:
                            target_keywords = None
                    target_text = _fuse_context(paper.title, paper.abstract, target_keywords, content_text, request.max_context_chars)
        if not effective_query:
            if target_keywords:
                effective_query = ' '.join(target_keywords[:6])
            elif target_text:
                try:
                    toks = [w for w in re.sub(r"[^a-zA-Z0-9\s]", " ", target_text).split() if len(w) > 2]
                    effective_query = ' '.join(toks[:8]) if toks else ''
                except Exception:
                    effective_query = ''

    # Helper tokenizers
    def _tokenize_set(s: str) -> set:
        s2 = (s or '').lower()
        s2 = re.sub(r"[^a-z0-9\s]", " ", s2)
        return set([w for w in s2.split() if len(w) > 2])

    qset = _tokenize_set(target_text or effective_query or '')
    kwset = set([kw.lower() for kw in (target_keywords or []) if isinstance(kw, str)])

    # Limit to top-N with pdf_url
    items = [i for i in request.items if i.pdf_url]
    items = items[: max(1, min(request.top_n, len(items)))]
    if not items:
        return DeepRescoreResponse(items=[i.dict() for i in request.items], rescored=0, method="lexical")

    async with PaperDiscoveryService() as svc:
        # Build target embedding if available
        target_vec = None
        if getattr(svc, 'openai_client', None) and (target_text or effective_query):
            try:
                target_vec = await svc._get_embedding_cached("__deep__target__", target_text or effective_query)
            except Exception:
                target_vec = None

        # Download and extract PDFs concurrently
        timeout = aiohttp.ClientTimeout(total=12)
        headers = {"User-Agent": "ScholarHub/1.0 (Deep Rescore)"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async def fetch_and_extract(url: str) -> str:
                try:
                    async with session.get(url, allow_redirects=True) as resp:
                        if resp.status != 200:
                            return ''
                        ctype = (resp.headers.get('content-type') or '').lower()
                        data = await resp.read()
                        # Cap size ~15 MB
                        if len(data) > 15 * 1024 * 1024:
                            data = data[: 15 * 1024 * 1024]
                        # Parse PDF regardless of header
                        try:
                            import PyPDF2
                            reader = PyPDF2.PdfReader(io.BytesIO(data))
                            texts = []
                            for pg in reader.pages[:25]:  # limit pages for speed
                                try:
                                    t = pg.extract_text() or ''
                                    texts.append(t)
                                except Exception:
                                    continue
                            return '\n'.join(texts)
                        except Exception:
                            return ''
                except Exception:
                    return ''

            tasks = [fetch_and_extract(i.pdf_url) for i in items]
            texts = await asyncio.gather(*tasks, return_exceptions=True)

        # Compute scores
        def lexical_score(title: str, abstract: str) -> float:
            title_set = _tokenize_set(title)
            abs_set = _tokenize_set(abstract)
            title_overlap = (len(title_set & qset) / max(1, len(title_set))) if title_set and qset else 0.0
            abs_overlap = (len(abs_set & qset) / max(1, len(abs_set))) if abs_set and qset else 0.0
            kw_title = (len(title_set & kwset) / max(1, len(kwset))) if kwset else 0.0
            kw_body = (len(abs_set & kwset) / max(1, len(kwset))) if kwset else 0.0
            return max(0.0, min(1.0, 0.5*title_overlap + 0.3*abs_overlap + 0.1*kw_title + 0.05*kw_body))

        # Embed candidate texts if available
        vecs = [None] * len(items)
        if target_vec is not None:
            try:
                # Prepare clamped texts
                prepped = []
                idxs = []
                for idx, txt in enumerate(texts):
                    if isinstance(txt, str) and txt.strip():
                        t = txt.strip()
                        if len(t) > 6000:
                            t = t[:6000]
                        prepped.append(t)
                        idxs.append(idx)
                if prepped:
                    emb = await svc._embed_texts(prepped)
                    for j, v in enumerate(emb):
                        vecs[idxs[j]] = v
            except Exception:
                pass

        updated: List[Dict] = []
        rescored = 0
        for i, it in enumerate(items):
            base_lex = lexical_score(it.title or '', it.abstract or '')
            combined = base_lex
            if target_vec is not None and vecs[i] is not None:
                try:
                    sim = svc._cosine_similarity(target_vec, vecs[i])
                except Exception:
                    sim = 0.0
                # Combine semantic + lexical
                combined = 0.75 * sim + 0.25 * base_lex
                rescored += 1
            d = it.dict()
            d['relevance_score'] = float(max(0.0, min(1.0, combined)))
            d['content_scored'] = True
            updated.append(d)

        # Merge back into full list preserving non-rescored items
        full = []
        # Build key by title|source
        rescored_map = {f"{d.get('title','')}|{d.get('source','')}": d for d in updated}
        for orig in request.items:
            key = f"{orig.title}|{orig.source or ''}"
            full.append(rescored_map.get(key, orig.dict()))

        # Final sort by updated relevance
        full_sorted = sorted(full, key=lambda x: float(x.get('relevance_score') or 0.0), reverse=True)
        return DeepRescoreResponse(items=full_sorted, rescored=rescored, method="embeddings" if rescored > 0 else "lexical")


@router.post("/papers/recommend")
async def recommend_papers(
    based_on_paper_ids: List[str],
    max_results: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Recommend similar papers based on user's existing papers (future enhancement)
    """
    # Placeholder for recommendation functionality
    return {
        "message": "Paper recommendation feature coming soon",
        "based_on_papers": len(based_on_paper_ids),
        "max_results": max_results
    }


@router.post("/debug/probe-publisher", response_model=PublisherProbeResponse)
async def probe_publisher(
    request: PublisherProbeRequest,
    current_user: User = Depends(get_current_user),
):
    """Probe publisher page and KFUPM proxy without scraping paywalled content."""
    try:
        if not request.url and not request.doi:
            raise HTTPException(status_code=400, detail="Provide url or doi")

        # Resolve DOI to URL if needed
        target = request.url
        if not target and request.doi:
            doi_url = f"https://doi.org/{request.doi}"
            # Resolve with aiohttp GET (HEAD sometimes not redirected)
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
                try:
                    async with s.get(doi_url, allow_redirects=True) as resp:
                        target = str(resp.url)
                except Exception:
                    target = doi_url

        if not target:
            raise HTTPException(status_code=400, detail="Unable to resolve target URL")

        uni = UniversityProxyService()
        enhanced = EnhancedPaperAccessService()

        proxied = uni.generate_university_url(target)
        # If the user already provided a proxied KFUPM/SDL URL, treat it as proxied
        try:
            from urllib.parse import urlparse as _urlparse
            _host = _urlparse(target).netloc.lower()
            if (not proxied) and ("idm.oclc.org" in _host):
                proxied = target
        except Exception:
            pass
        provider_search = uni.build_provider_search_urls(request.title or None, None)

        proxy_fetch = None
        if proxied:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                    async with s.get(proxied, allow_redirects=True) as resp:
                        ctype = resp.headers.get('content-type', '').lower()
                        html_title = None
                        sso_login_url = None
                        html_excerpt = None
                        if 'text/html' in ctype:
                            body = await resp.text()
                            import re as _re
                            m = _re.search(r"<title[^>]*>(.*?)</title>", body, _re.IGNORECASE | _re.DOTALL)
                            if m:
                                html_title = m.group(1).strip()[:300]
                            try:
                                sso_login_url = await enhanced._detect_sso_authentication(body, str(resp.url))
                            except Exception:
                                sso_login_url = None
                            html_excerpt = body[:800]
                        proxy_fetch = {
                            'status': resp.status,
                            'final_url': str(resp.url),
                            'content_type': ctype,
                            'html_title': html_title,
                            'sso_login_url': sso_login_url,
                            'html_excerpt': html_excerpt,
                        }
            except Exception as e:
                proxy_fetch = {'error': str(e)}

        # Optional Unpaywall OA lookup if DOI provided
        unpaywall = None
        if request.with_unpaywall and request.doi:
            email = os.getenv('UNPAYWALL_EMAIL')
            if email:
                try:
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
                        async with s.get(f"https://api.unpaywall.org/v2/{request.doi}", params={'email': email}) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                best = data.get('best_oa_location') or {}
                                unpaywall = {
                                    'is_oa': bool(data.get('is_oa')),
                                    'oa_url': best.get('url') or best.get('url_for_pdf') or best.get('url_for_landing_page'),
                                    'host_type': best.get('host_type'),
                                }
                except Exception:
                    unpaywall = None

        return PublisherProbeResponse(
            target=request.doi or request.url or '',
            resolved_url=target,
            proxied_url=proxied,
            provider_search_urls=provider_search,
            proxy_fetch=proxy_fetch,
            unpaywall=unpaywall,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Probe publisher failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# DUPLICATE FUNCTION REMOVED - see line 672 for the active stream endpoint
@router.post("/papers/content", response_model=PaperContentResponse)
async def fetch_paper_content(
    request: PaperContentRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Enhanced paper content fetching with university SSO detection and multi-tier fallbacks
    """
    try:
        from app.services.enhanced_paper_access import EnhancedPaperAccessService
        
        logger.info(f"🔍 Enhanced paper access for: {request.url}")
        
        # Use the enhanced paper access service
        access_service = EnhancedPaperAccessService()
        result = await access_service.access_paper(request.url, request.paper_title or "")
        
        # Convert enhanced result to our response format
        if result.success:
            return PaperContentResponse(
                success=True,
                content_type=result.content_type,
                pdf_url=result.pdf_url,
                title=result.title,
                error=result.error
            )
        elif result.authentication_required and result.sso_login_url:
            # University SSO detected
            return PaperContentResponse(
                success=False,
                content_type="authenticated_access",
                title=result.title,
                error=f"University SSO authentication required. Login URL: {result.sso_login_url}"
            )
        else:
            # Access failed - return suggestions
            suggestions_text = ""
            if result.suggestions:
                suggestions_text = f" Suggestions: {'; '.join(result.suggestions[:3])}"
            
            return PaperContentResponse(
                success=False,
                content_type=result.content_type,
                title=result.title,
                error=f"{result.error}{suggestions_text}"
            )
                    
    except Exception as e:
        logger.error(f"Error in enhanced paper access: {str(e)}")
        return PaperContentResponse(
            success=False,
            content_type="error",
            error=f"Failed to fetch content: {str(e)}"
        )


async def _try_alternative_access(url: str, title: str) -> Optional[PaperContentResponse]:
    """
    Try alternative access methods as fallback when direct access fails.
    Note: This is for demonstration purposes only - in production, use only legal sources.
    """
    from app.core.config import settings
    
    # Only enable if explicitly configured for demonstration
    if not settings.ENABLE_ALTERNATIVE_ACCESS:
        logger.warning("Alternative access disabled - use ENABLE_ALTERNATIVE_ACCESS=true to enable for demonstration")
        return None
    
    logger.info(f"Alternative access enabled - searching for: URL={url[:50]}... Title={title[:50] if title else 'None'}...")
    
    import re
    
    # Extract DOI from URL and title with comprehensive patterns
    doi = _extract_doi(url, title)
    
    # If no DOI found, try with title
    search_query = doi if doi else title
    if not search_query:
        return None
    
    try:
        # Shorter timeout for alternative access to prevent frontend timeouts
        alt_timeout = aiohttp.ClientTimeout(total=20)  # 20 seconds max for alternative access
        async with aiohttp.ClientSession(timeout=alt_timeout) as session:
            # Headers that look more like a regular browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Define source priorities and mirrors for rotation
            sources = [
                {
                    'name': 'LibGen',
                    'mirrors': [
                        'https://libgen.is/scimag/?q=',
                        'https://libgen.st/scimag/?q=',
                        'https://libgen.li/scimag/?q=',
                        'https://libgen.me/scimag/?q=',
                    ],
                    'extractor': '_extract_libgen_pdf_url'
                },
                {
                    'name': 'Anna\'s Archive', 
                    'mirrors': [
                        'https://annas-archive.org/search?q=',
                        'https://annas-archive.se/search?q=',
                    ],
                    'extractor': '_extract_annas_pdf_url'
                }
            ]
            
            # Prepare multiple search strategies
            search_queries = [search_query]
            
            # If we have a DOI, also try title-based search
            if doi and title:
                # Clean up title for better searching
                clean_title = re.sub(r'[^\w\s]', ' ', title)
                clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                if len(clean_title) > 10:  # Only add if title is meaningful
                    search_queries.append(clean_title)
            
            # Try all sources with priority rotation
            for source in sources:
                for query in search_queries:
                    encoded_q = urllib.parse.quote(query)
                    
                    # Try all mirrors for this source
                    for mirror_url in source['mirrors']:
                        full_url = f"{mirror_url}{encoded_q}"
                        
                        try:
                            # Shorter timeout for faster response
                            async with session.get(full_url, headers=headers, timeout=8) as response:
                                if response.status == 200:
                                    content = await response.text()
                                    
                                    # Use the appropriate extractor for this source
                                    logger.info(f"🔍 Searching {source['name']} with query: '{query}'")
                                    
                                    if source['extractor'] == '_extract_libgen_pdf_url':
                                        pdf_url = await _extract_libgen_pdf_url(content, session, headers)
                                    else:  # Anna's Archive
                                        pdf_url = await _extract_annas_pdf_url(content, session, headers)
                                    
                                    if pdf_url:
                                        query_type = "DOI" if query == doi else "title"
                                        mirror_name = mirror_url.split('//')[1].split('/')[0]  # Extract domain
                                        logger.info(f"✅ Found PDF via {source['name']}: {pdf_url[:100]}...")
                                        return PaperContentResponse(
                                            success=True,
                                            content_type="pdf",
                                            pdf_url=pdf_url,
                                            title=title,
                                            error=f"Found via {source['name']} ({mirror_name}) using {query_type} search (demonstration only)"
                                        )
                                    else:
                                        logger.debug(f"No PDF found in {source['name']} for query: {query}")
                        except asyncio.TimeoutError:
                            logger.debug(f"{source['name']} timeout for {full_url}")
                            continue
                        except Exception as e:
                            logger.debug(f"{source['name']} access failed for {full_url}: {e}")
                            continue
                        
                        # Reduced delay between mirror attempts for faster response
                        import asyncio
                        await asyncio.sleep(0.1)
                    
    except Exception as e:
        logger.debug(f"Alternative access failed: {e}")
        
    return None


async def _extract_libgen_pdf_url(html_content: str, session, headers: dict) -> Optional[str]:
    """
    Extract direct PDF download URL from LibGen search results.
    """
    import re
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("BeautifulSoup not available, using regex fallback")
        return _extract_pdf_url_regex(html_content, 'libgen')
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # LibGen typically shows results in a table with download links
        # Look for links that contain 'download', 'pdf', or point to mirrors
        
        # Method 1: Look for direct download links
        download_links = soup.find_all('a', href=True)
        for link in download_links:
            href = link.get('href', '')
            text = link.get_text().lower()
            
            # Look for download indicators
            if any(indicator in text for indicator in ['download', 'pdf', 'get']):
                if href.startswith('http') and ('pdf' in href or 'download' in href):
                    return href
                elif href.startswith('/'):
                    # Relative URL - construct full URL
                    return f"https://libgen.is{href}"
        
        # Method 2: Look for mirror links that lead to PDFs
        mirror_patterns = [
            r'href="([^"]*(?:library\.lol|libgen\.lc|download\.library1\.org)[^"]*)"',
            r'href="([^"]*mirror[^"]*)"',
            r'href="([^"]*download[^"]*\.php[^"]*)"'
        ]
        
        for pattern in mirror_patterns:
            matches = re.findall(pattern, html_content)
            for match in matches:
                if match.startswith('http'):
                    # Try to follow the mirror link to get the actual PDF
                    try:
                        async with session.get(match, headers=headers, timeout=10) as mirror_response:
                            if mirror_response.status == 200:
                                # Check if it's a direct PDF or has PDF download links
                                content_type = mirror_response.headers.get('content-type', '').lower()
                                if 'pdf' in content_type:
                                    return match
                                
                                # If it's HTML, look for PDF download links
                                mirror_content = await mirror_response.text()
                                pdf_links = re.findall(r'href="([^"]*\.pdf[^"]*)"', mirror_content)
                                if pdf_links:
                                    pdf_url = pdf_links[0]
                                    if pdf_url.startswith('http'):
                                        return pdf_url
                                    else:
                                        return f"https://libgen.is{pdf_url}"
                    except Exception:
                        continue
                        
    except Exception as e:
        logger.debug(f"LibGen PDF extraction failed: {e}")
    
    return None


async def _extract_annas_pdf_url(html_content: str, session, headers: dict) -> Optional[str]:
    """
    Extract direct PDF download URL from Anna's Archive search results.
    """
    import re
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("BeautifulSoup not available, using regex fallback")
        return _extract_pdf_url_regex(html_content, 'annas')
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Anna's Archive has a different structure
        # Look for download links or book/paper result links
        
        # Method 1: Look for direct download buttons/links
        download_elements = soup.find_all(['a', 'button'], class_=re.compile(r'download|btn'))
        for element in download_elements:
            href = element.get('href', '')
            text = element.get_text().lower()
            
            if 'download' in text and href:
                if href.startswith('http'):
                    return href
                elif href.startswith('/'):
                    return f"https://annas-archive.org{href}"
        
        # Method 2: Look for paper/book result links that lead to download pages
        result_links = soup.find_all('a', href=re.compile(r'/(md5|doi|isbn)/'))
        for link in result_links:
            href = link.get('href', '')
            if href:
                full_url = href if href.startswith('http') else f"https://annas-archive.org{href}"
                
                # Follow the result link to get to the download page
                try:
                    async with session.get(full_url, headers=headers, timeout=10) as detail_response:
                        if detail_response.status == 200:
                            detail_content = await detail_response.text()
                            detail_soup = BeautifulSoup(detail_content, 'html.parser')
                            
                            # Look for download buttons on the detail page
                            download_buttons = detail_soup.find_all(['a', 'button'], 
                                                                  text=re.compile(r'download|pdf', re.I))
                            for button in download_buttons:
                                download_href = button.get('href', '')
                                if download_href:
                                    if download_href.startswith('http'):
                                        return download_href
                                    elif download_href.startswith('/'):
                                        return f"https://annas-archive.org{download_href}"
                except Exception:
                    continue
        
        # Method 3: Look for embedded PDF viewers or direct links
        pdf_patterns = [
            r'href="([^"]*\.pdf[^"]*)"',
            r'src="([^"]*\.pdf[^"]*)"',
            r'"(https?://[^"]*(?:pdf|download)[^"]*)"'
        ]
        
        for pattern in pdf_patterns:
            matches = re.findall(pattern, html_content)
            for match in matches:
                if 'annas-archive.org' in match or 'libgen' in match:
                    return match
                    
    except Exception as e:
        logger.debug(f"Anna's Archive PDF extraction failed: {e}")
    
    return None


def _extract_pdf_url_regex(html_content: str, source: str) -> Optional[str]:
    """
    Fallback regex-based PDF URL extraction for when BeautifulSoup is not available.
    """
    import re
    
    # For testing purposes, create functional demonstration links
    if source == 'libgen':
        # Look for common LibGen download patterns
        patterns = [
            r'href="([^"]*download[^"]*\.php[^"]*)"',
            r'href="([^"]*library\.lol[^"]*)"',
            r'href="([^"]*libgen\.lc[^"]*)"',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content)
            if matches:
                return matches[0] if matches[0].startswith('http') else f"https://libgen.is{matches[0]}"
    
    elif source == 'annas':
        # Look for Anna's Archive download patterns
        patterns = [
            r'href="([^"]*annas-archive\.org[^"]*download[^"]*)"',
            r'href="([^"]*/md5/[^"]*)"',
            r'href="([^"]*/doi/[^"]*)"',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content)
            if matches:
                url = matches[0] if matches[0].startswith('http') else f"https://annas-archive.org{matches[0]}"
                return url
    
    return None


def _extract_doi(url: str, title: str) -> Optional[str]:
    """
    Comprehensive DOI extraction from URL and title.
    """
    import re
    
    # Try URL patterns first (most reliable)
    url_patterns = [
        r'doi\.org/(.+)',
        r'dx\.doi\.org/(.+)', 
        r'doi\.acm\.org/(.+)',
        r'link\.springer\.com/.*?/(10\.\d+/[^/?]+)',
        r'ieeexplore\.ieee\.org/.*?arnumber=(\d+)',  # IEEE has special handling
        r'nature\.com/articles/([^/?]+)',
        r'science\.org/doi/(10\.\d+/[^/?]+)',
        r'cell\.com/.*?/([^/?]+)',
        r'sciencedirect\.com/.*?pii/([^/?]+)',
        r'arxiv\.org/abs/(\d+\.\d+)',
        r'/doi/abs?/?(10\.\d+/[^/?]+)',
        r'/doi/full/?(10\.\d+/[^/?]+)',
        r'wiley\.com/doi/abs/(10\.\d+/[^/?]+)',
        r'tandfonline\.com/doi/abs/(10\.\d+/[^/?]+)',
    ]
    
    for pattern in url_patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            doi_candidate = match.group(1)
            # Validate DOI format
            if _is_valid_doi_format(doi_candidate):
                return doi_candidate
    
    # Try title patterns (less reliable but useful fallback)
    if title:
        title_patterns = [
            r'DOI:?\s*(10\.\d+/[^\s,;]+)',
            r'doi:?\s*(10\.\d+/[^\s,;]+)',
            r'https?://doi\.org/(10\.\d+/[^\s,;]+)',
            r'(10\.\d+/[^\s,;]+)',  # Generic DOI pattern
        ]
        
        for pattern in title_patterns:
            matches = re.findall(pattern, title, re.IGNORECASE)
            for match in matches:
                if _is_valid_doi_format(match):
                    return match
    
    return None


def _is_valid_doi_format(doi: str) -> bool:
    """
    Validate that a string looks like a proper DOI.
    """
    import re
    
    # Basic DOI validation
    if not doi or len(doi) < 7:  # Minimum viable DOI length
        return False
    
    # Special case for ArXiv IDs (not traditional DOIs but useful identifiers)
    arxiv_pattern = r'^\d{4}\.\d{4,5}(v\d+)?$'
    if re.match(arxiv_pattern, doi):
        return True
    
    # Must start with 10.
    if not doi.startswith('10.'):
        return False
    
    # Must have registrant code and suffix separated by /
    if '/' not in doi:
        return False
    
    # Check for reasonable length and characters
    if len(doi) > 200:  # Extremely long DOIs are suspicious
        return False
    
    # Basic pattern check
    doi_pattern = r'^10\.\d+/.+$'
    return bool(re.match(doi_pattern, doi))
