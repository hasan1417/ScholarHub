from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError, OperationalError
from typing import Optional, List
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.reference import Reference
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.research_paper import ResearchPaper
from app.models import ProjectReference, ProjectMember, ProjectRole, Project
from app.services.document_service import DocumentService
from app.services.document_processing_service import DocumentProcessingService
from app.services.reference_ingestion_service import ingest_reference_pdf
from app.services.subscription_service import SubscriptionService
from pydantic import BaseModel
from app.schemas.reference import ReferenceResponse, ReferenceList
import aiohttp
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import re

class PDFResolveRequest(BaseModel):
    url: str
    title: Optional[str] = None

class PDFResolveResponse(BaseModel):
    url: str
    pmc_url: Optional[str] = None
    pmcid: Optional[str] = None
    pdf_candidates: Optional[List[str]] = None
    chosen_pdf: Optional[str] = None
    is_open_access: Optional[bool] = None
    detail: Optional[str] = None

router = APIRouter()


class ReferenceCreateRequest(BaseModel):
    title: str
    authors: Optional[List[str]] = []
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    journal: Optional[str] = None
    abstract: Optional[str] = None
    is_open_access: Optional[bool] = False
    pdf_url: Optional[str] = None
    paper_id: Optional[str] = None  # optional immediate attachment


def _ensure_reference_permissions(
    db: Session,
    reference_id: str,
    user: User,
    *,
    allow_project_roles: bool = False,
) -> Reference:
    ref = db.query(Reference).filter(Reference.id == reference_id).first()
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")

    if ref.owner_id == user.id:
        return ref

    if not allow_project_roles:
        raise HTTPException(status_code=403, detail="Not authorized to modify this reference")

    project_links = (
        db.query(ProjectReference, Project)
        .join(Project, ProjectReference.project_id == Project.id)
        .filter(ProjectReference.reference_id == reference_id)
        .all()
    )

    for project_ref, project in project_links:
        if project.created_by == user.id:
            return ref

        member = (
            db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_ref.project_id,
                ProjectMember.user_id == user.id,
                ProjectMember.status == 'accepted',
            )
            .first()
        )
        if member:
            role_value = member.role.value if hasattr(member.role, 'value') else member.role
            if role_value in {ProjectRole.ADMIN.value, ProjectRole.EDITOR.value, ProjectRole.OWNER.value, 'admin', 'editor', 'owner'}:
                return ref

    raise HTTPException(status_code=403, detail="Not authorized to modify this reference")


@router.get("/", response_model=ReferenceList)
async def list_my_references(
    skip: int = 0,
    limit: int = 100,
    q: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        _ensure_references_schema(db)
        query = db.query(Reference).filter(Reference.owner_id == current_user.id)
        if q:
            like = f"%{q}%"
            query = query.filter(Reference.title.ilike(like))
        total = query.count()
        refs = query.order_by(Reference.created_at.desc()).offset(skip).limit(limit).all()

        # Best-effort normalization: if a reference has an uploaded document but legacy status/pdf_url
        updated = False
        for r in refs:
            try:
                if r.document_id:
                    # Ensure pdf_url present
                    if (not r.pdf_url) or r.pdf_url.strip() == "":
                        r.pdf_url = f"/api/v1/documents/{r.document_id}/download"
                        updated = True
                    # Upgrade status based on document processing state
                    try:
                        doc = db.query(Document).filter(Document.id == r.document_id).first()
                        if doc and doc.status == DocumentStatus.PROCESSED:
                            if r.status != 'analyzed':
                                r.status = 'analyzed'
                                updated = True
                        else:
                            if r.status == 'pending':
                                r.status = 'ingested'
                                updated = True
                    except Exception:
                        pass
            except Exception:
                pass
        if updated:
            db.commit()
        return ReferenceList(references=refs, total=total)
    except (ProgrammingError, OperationalError) as e:
        # Likely missing migration for owner_id or altered schema
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="References schema mismatch. Please run database migrations (alembic upgrade head)."
        )


@router.post("/", response_model=ReferenceResponse, status_code=status.HTTP_201_CREATED)
async def create_reference(
    payload: ReferenceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    # Check subscription limit for total references
    allowed, current, limit = SubscriptionService.check_resource_limit(
        db, current_user.id, "references_total"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "limit_exceeded",
                "feature": "references_total",
                "current": current,
                "limit": limit,
                "message": f"You have reached your reference library limit ({current}/{limit}). Upgrade to Pro for more references.",
            },
        )

    try:
        _ensure_references_schema(db)
        # Prevent duplicates in the target scope (paper-specific or user library)
        def _normalize_title(s: str) -> str:
            return re.sub(r"\s+", " ", (s or "").strip()).lower()

        try:
            dup = None
            norm_in = _normalize_title(payload.title)
            base_q = db.query(Reference).filter(Reference.owner_id == current_user.id)
            if payload.paper_id:
                base_q = base_q.filter(Reference.paper_id == payload.paper_id)
            existing = base_q.all()
            for er in existing:
                if payload.doi and er.doi and er.doi.strip().lower() == payload.doi.strip().lower():
                    dup = er
                    break
                if _normalize_title(er.title) == norm_in and (not payload.year or not er.year or er.year == payload.year):
                    dup = er
                    break
            if dup:
                # Soft-update missing fields on duplicate
                updated = False
                if not dup.journal and payload.journal:
                    dup.journal = payload.journal; updated = True
                if (not dup.year) and payload.year:
                    dup.year = payload.year; updated = True
                if (not dup.authors) and (payload.authors or []):
                    dup.authors = payload.authors; updated = True
                if (not dup.abstract) and payload.abstract:
                    dup.abstract = payload.abstract; updated = True
                if (not dup.doi) and payload.doi:
                    dup.doi = payload.doi; updated = True
                if (not dup.pdf_url) and payload.pdf_url:
                    dup.pdf_url = payload.pdf_url; updated = True
                if (not dup.paper_id) and payload.paper_id:
                    dup.paper_id = payload.paper_id; updated = True
                if updated:
                    db.commit(); db.refresh(dup)
                return dup
        except Exception:
            # Non-fatal; proceed with creation
            pass

        ref = Reference(
            owner_id=current_user.id,
            paper_id=payload.paper_id,
            title=payload.title,
            authors=payload.authors or [],
            year=payload.year,
            doi=payload.doi,
            url=payload.url,
            source=payload.source,
            journal=payload.journal,
            abstract=payload.abstract,
            is_open_access=bool(payload.is_open_access),
            pdf_url=payload.pdf_url,
            status="pending",
        )
        db.add(ref)
        db.commit()
        db.refresh(ref)

        # If the reference has a PDF URL, enqueue background ingestion using existing system
        try:
            if (payload.pdf_url or ref.pdf_url):
                if background_tasks is not None:
                    from app.api.v1.research_papers import analyze_reference_task
                    background_tasks.add_task(analyze_reference_task, str(ref.id))
        except Exception:
            # best-effort
            pass

        return ref
    except (ProgrammingError, OperationalError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="References schema mismatch. Please run database migrations (alembic upgrade head)."
        )


@router.post("/{reference_id}/attach-to-paper", response_model=ReferenceResponse)
async def attach_reference_to_paper(
    reference_id: str,
    paper_id: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ref = _ensure_reference_permissions(db, reference_id, current_user, allow_project_roles=False)
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot attach to a paper you don't own")
    ref.paper_id = paper_id
    db.commit()
    db.refresh(ref)
    return ref


@router.post("/{reference_id}/upload-pdf", response_model=ReferenceResponse)
async def upload_reference_pdf(
    reference_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ref = _ensure_reference_permissions(db, reference_id, current_user, allow_project_roles=True)
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    content = await file.read()
    ds = DocumentService()
    file_path = await ds.save_uploaded_file(content, file.filename)
    document = Document(
        filename=file.filename,
        original_filename=file.filename,
        file_path=file_path,
        file_size=len(content),
        mime_type='application/pdf',
        document_type=DocumentType.PDF,
        file_hash=ds.duplicate_detector.calculate_file_hash(content),
        title=ref.title,
        doi=ref.doi,
        journal=ref.journal,
        owner_id=current_user.id,
        paper_id=ref.paper_id,
        status=DocumentStatus.PROCESSING,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    # process + embed using existing system (best-effort)
    try:
        await ds.process_document(db, document, content, None)
        DocumentProcessingService().embed_document_chunks(db, str(document.id))
        
        # Link document chunks to this reference for reference-based RAG
        try:
            from app.models.document_chunk import DocumentChunk
            chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).all()
            for chunk in chunks:
                chunk.reference_id = str(ref.id)
            db.commit()
            logger.info(f"Linked {len(chunks)} chunks to reference {ref.id}")
        except Exception as e:
            logger.error(f"Failed to link chunks to reference {ref.id}: {e}")
        
        # Mark document processed
        document.status = DocumentStatus.PROCESSED
        # update reference status to analyzed when processing completes
        ref.status = 'analyzed'
    except Exception:
        # Leave status as PROCESSING on failure
        ref.status = 'ingested'
        
    # update reference
    ref.document_id = document.id
    # Provide a direct API download link for the uploaded PDF
    ref.pdf_url = f"/api/v1/documents/{document.id}/download"
    ref.is_open_access = True
    db.commit()
    db.refresh(ref)
    return ref


@router.post("/{reference_id}/ingest-pdf", response_model=ReferenceResponse)
async def ingest_reference_pdf_endpoint(
    reference_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ref = _ensure_reference_permissions(db, reference_id, current_user, allow_project_roles=True)

    if not ref.pdf_url:
        raise HTTPException(status_code=400, detail="Reference does not have a PDF URL to ingest")

    success = ingest_reference_pdf(db, ref, owner_id=str(current_user.id))
    if not success:
        raise HTTPException(status_code=400, detail="Unable to ingest PDF for this reference")

    db.refresh(ref)
    return ref


@router.delete("/{reference_id}", response_model=dict)
async def delete_reference(
    reference_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ref = db.query(Reference).filter(Reference.id == reference_id, Reference.owner_id == current_user.id).first()
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")
    db.delete(ref)
    db.commit()
    return {"message": "Reference deleted"}


# Removed: resolve-pdf-by-id endpoint for references (feature deprecated)


@router.post("/debug/resolve-pdf", response_model=PDFResolveResponse)
async def resolve_pdf_from_url(
    payload: PDFResolveRequest,
    current_user: User = Depends(get_current_user),
):
    """Debug resolver that attempts to extract a PDF link from a generic URL without creating a reference."""
    if not payload.url:
        raise HTTPException(status_code=400, detail="url is required")

    import asyncio
    start_url = payload.url
    timeout = aiohttp.ClientTimeout(total=8, connect=3)
    headers = {"User-Agent": "ScholarHub/1.0 (PDF resolver)"}

    async def fetch_html(url: str, referer: Optional[str] = None) -> str:
        h = headers.copy()
        if referer:
            h['Referer'] = referer
        async with aiohttp.ClientSession(timeout=timeout, headers=h) as s:
            async with s.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=400, detail=f"Failed to fetch page: {resp.status}")
                # Prefer text; if not text/html, still try to read as text for scraping
                try:
                    return await resp.text()
                except Exception:
                    # Fallback to bytes -> decode best-effort
                    data = await resp.read()
                    try:
                        return data.decode('utf-8', errors='ignore')
                    except Exception:
                        raise HTTPException(status_code=400, detail="Unable to read page body")

    def find_pdf_candidates(html: str, base_url: str) -> List[str]:
        soup = BeautifulSoup(html, 'html.parser')
        pdfs: List[str] = []
        meta = soup.find('meta', attrs={'name': 'citation_pdf_url'})
        if meta and meta.get('content'):
            pdfs.append(meta['content'])
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = (a.text or '').lower()
            if href.lower().endswith('.pdf') or '/pdf' in href.lower() or 'pdf=' in href.lower() or 'download=' in href.lower() or 'full text' in text or 'free' in text:
                pdfs.append(urljoin(base_url, href))
        # Dedup
        seen: set[str] = set()
        out: List[str] = []
        for u in pdfs:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    async def _do_resolve() -> PDFResolveResponse:
        if 'pubmed.ncbi.nlm.nih.gov' in start_url:
            # Extract PMID early for E-utilities fallback
            import re as _re
            m = _re.search(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?', start_url)
            pmid_from_url = m.group(1) if m else None
            html = None
            try:
                html = await fetch_html(start_url)
            except HTTPException as e:
                # If PubMed blocks fetch, try E-utilities to get PMCID or publisher link from PMID
                pmcid_via_eutils = None
                ext_publisher_url = None
                if pmid_from_url:
                    try:
                        elink = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pubmed&db=pmc&id={pmid_from_url}&retmode=json"
                        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as s:
                            async with s.get(elink, allow_redirects=True) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    # Try to locate a PMCID in linksets
                                    linksets = (data or {}).get('linksets') or []
                                    if linksets:
                                        for db in (linksets[0].get('linksetdbs') or []):
                                            if (db.get('dbto') or '').lower() == 'pmc':
                                                links = db.get('links') or []
                                                if links:
                                                    val = links[0].get('id') or links[0].get('value')
                                                    if val:
                                                        pmcid_via_eutils = ('PMC' + str(val)) if not str(val).startswith('PMC') else str(val)
                                                        break
                        # Also attempt prlinks to get publisher full text URL directly
                        pr = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pubmed&id={pmid_from_url}&cmd=prlinks"
                        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as s:
                            async with s.get(pr, allow_redirects=True) as resp2:
                                if resp2.status in (200, 302, 303):
                                    ext_publisher_url = str(resp2.url)
                    except Exception:
                        pmcid_via_eutils = None
                if pmcid_via_eutils:
                    pmc_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid_via_eutils}/"
                    pdf_guess = pmc_url + 'pdf'
                    return PDFResolveResponse(url=start_url, pmc_url=pmc_url, pmcid=pmcid_via_eutils, pdf_candidates=[pdf_guess], chosen_pdf=pdf_guess, is_open_access=True, detail=e.detail)
                if ext_publisher_url:
                    try:
                        ext_html = await fetch_html(ext_publisher_url)
                        pdf_candidates = find_pdf_candidates(ext_html, ext_publisher_url)
                        if pdf_candidates:
                            return PDFResolveResponse(url=start_url, pdf_candidates=pdf_candidates, chosen_pdf=pdf_candidates[0])
                    except Exception:
                        pass
                # If prlinks returned XML (no redirect), parse for first external URL
                if pmid_from_url and not ext_publisher_url:
                    try:
                        pr = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pubmed&id={pmid_from_url}&cmd=prlinks"
                        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as s:
                            async with s.get(pr, allow_redirects=True) as prr:
                                pr_text = await prr.text()
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(pr_text)
                        ext = None
                        for obj in root.findall('.//IdUrlList//IdUrlSet//ObjUrl'):
                            u = obj.find('Url')
                            if u is not None and u.text:
                                ext = u.text.strip(); break
                        if ext:
                            ext_html = await fetch_html(ext)
                            pdf_candidates = find_pdf_candidates(ext_html, ext)
                            if pdf_candidates:
                                return PDFResolveResponse(url=start_url, pdf_candidates=pdf_candidates, chosen_pdf=pdf_candidates[0])
                    except Exception:
                        pass
                # No PMCID found; return informative response
                return PDFResolveResponse(url=start_url, detail=str(e.detail))
            # Proceed with HTML parsing if available
            soup = BeautifulSoup(html, 'html.parser')
            pmc_url = None
            pmcid = None
            for a in soup.find_all('a', href=True):
                if 'Free PMC article' in (a.text or '') or 'pmc/articles' in a['href']:
                    pmc_url = urljoin(start_url, a['href'])
                    break
                if 'pmc.ncbi.nlm.nih.gov/articles/PMC' in a['href']:
                    pmcid = a['href'].split('/articles/')[1].strip('/').split('/')[0]
            if not pmcid:
                meta_kw = soup.find('meta', attrs={'name': 'keywords'})
                if meta_kw and meta_kw.get('content'):
                    import re as _re
                    m = _re.search(r'(PMC\d+)', meta_kw['content'])
                    if m:
                        pmcid = m.group(1)
            pdf_candidates: List[str] = []
            if pmc_url:
                try:
                    pmc_html = await fetch_html(pmc_url, referer=start_url)
                    pdf_candidates = find_pdf_candidates(pmc_html, pmc_url)
                    if pdf_candidates:
                        return PDFResolveResponse(url=start_url, pmc_url=pmc_url, pmcid=pmcid, pdf_candidates=pdf_candidates, chosen_pdf=pdf_candidates[0], is_open_access=True)
                except HTTPException as e:
                    # Best-effort fallback: synthesize /pdf
                    pdf_guess = pmc_url.rstrip('/') + '/pdf'
                    return PDFResolveResponse(url=start_url, pmc_url=pmc_url, pmcid=pmcid, pdf_candidates=[pdf_guess], chosen_pdf=pdf_guess, is_open_access=True, detail=e.detail)
            if pmcid:
                guessed = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf"
                return PDFResolveResponse(url=start_url, pmc_url=f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/", pmcid=pmcid, pdf_candidates=[guessed], chosen_pdf=guessed, is_open_access=True)
            # Fallback on PubMed page itself
            # Also attempt external "Full text" outlinks
            pdf_candidates = find_pdf_candidates(html, start_url)
            # Collect external links that may be full text
            ext_links: list[str] = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                txt = (a.text or '').lower()
                ref_attr = (a.get('ref') or '')
                if href.startswith('http') and 'ncbi.nlm.nih.gov' not in href and 'pubmed.ncbi.nlm.nih.gov' not in href:
                    if 'full text' in txt or 'fulltext' in txt or 'journal' in txt:
                        ext_links.append(href)
                    elif 'fulltext' in ref_attr or 'journal_fulltext' in ref_attr:
                        ext_links.append(href)
            for ext in ext_links[:3]:
                try:
                    ext_html = await fetch_html(ext, referer=start_url)
                    cands = find_pdf_candidates(ext_html, ext)
                    for c in cands:
                        pdf_candidates.append(c)
                except Exception:
                    continue
            # Dedup candidates
            seen: set[str] = set(); dedup: list[str] = []
            for u in pdf_candidates:
                if u not in seen:
                    seen.add(u); dedup.append(u)
            chosen = dedup[0] if dedup else None
            return PDFResolveResponse(url=start_url, pmc_url=pmc_url, pmcid=pmcid, pdf_candidates=dedup, chosen_pdf=chosen)
        else:
            try:
                html = await fetch_html(start_url)
                pdf_candidates = find_pdf_candidates(html, start_url)
                return PDFResolveResponse(url=start_url, pdf_candidates=pdf_candidates, chosen_pdf=pdf_candidates[0] if pdf_candidates else None)
            except HTTPException as e:
                # Return detail instead of raising
                return PDFResolveResponse(url=start_url, detail=str(e.detail))
    try:
        # Hard cap the whole resolver to 10 seconds
        return await asyncio.wait_for(_do_resolve(), timeout=10.0)
    except asyncio.TimeoutError:
        return PDFResolveResponse(url=start_url, detail="Resolver timed out")
    except HTTPException as e:
        return PDFResolveResponse(url=start_url, detail=str(e.detail))
    except Exception as e:
        return PDFResolveResponse(url=start_url, detail=f"Resolver error: {str(e)}")


def _ensure_references_schema(db: Session) -> None:
    """Best-effort runtime schema alignment to prevent 500s when migrations weren't applied.
    Safe to call on every request; no-op if schema already correct.
    """
    try:
        engine = db.get_bind()
        insp = inspect(engine)
        tables = insp.get_table_names()
        if 'references' not in tables:
            # Create table if it doesn't exist (minimal set of columns used by API)
            engine.execute(text(
                'CREATE TABLE IF NOT EXISTS "references" ('
                'id uuid PRIMARY KEY,'
                'paper_id uuid NULL REFERENCES research_papers(id) ON DELETE CASCADE,'
                'owner_id uuid NULL REFERENCES users(id) ON DELETE CASCADE,'
                'title VARCHAR(500) NOT NULL,'
                'authors TEXT[],'
                'year INTEGER,'
                'doi VARCHAR(255),'
                'url VARCHAR(1000),'
                'source VARCHAR(100),'
                'journal VARCHAR(500),'
                'abstract TEXT,'
                'is_open_access BOOLEAN DEFAULT FALSE,'
                'pdf_url VARCHAR(1000),'
                'status VARCHAR(50) DEFAULT '"'"'pending'"'"','
                'document_id uuid NULL REFERENCES documents(id),'
                'summary TEXT,'
                'key_findings TEXT[],'
                'methodology TEXT,'
                'limitations TEXT[],'
                'relevance_score FLOAT,'
                'created_at TIMESTAMPTZ DEFAULT now(),'
                'updated_at TIMESTAMPTZ DEFAULT now()'
                ')'
            ))
            return
        # Table exists; ensure required columns/properties
        cols = {c['name']: c for c in insp.get_columns('references')}
        if 'owner_id' not in cols:
            engine.execute(text('ALTER TABLE "references" ADD COLUMN owner_id uuid'))
        # Ensure paper_id nullable
        if 'paper_id' in cols and not cols['paper_id'].get('nullable', True):
            engine.execute(text('ALTER TABLE "references" ALTER COLUMN paper_id DROP NOT NULL'))
    except Exception:
        # Silent best-effort; fall back to API-level error messaging if DB still mismatched
        pass
