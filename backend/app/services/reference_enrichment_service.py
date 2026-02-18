"""Post-creation enrichment for references added via browser extension, BibTeX import, etc.

Fills in missing metadata (authors, year, abstract, OA status, PDF URL) using
CrossRef, Unpaywall, and Semantic Scholar — the same APIs the discovery system uses.
Then triggers PDF ingestion if a PDF URL is available.
"""

from __future__ import annotations

import logging
import re

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.reference import Reference

logger = logging.getLogger(__name__)

CROSSREF_TIMEOUT = 10
UNPAYWALL_TIMEOUT = 10
SEMANTIC_SCHOLAR_TIMEOUT = 10


def _needs_enrichment(ref: Reference) -> bool:
    """Return True if this reference is missing key metadata fields."""
    missing_authors = not ref.authors or len(ref.authors) == 0
    missing_year = ref.year is None
    missing_abstract = not ref.abstract
    missing_pdf = not ref.pdf_url
    return missing_authors or missing_year or missing_abstract or missing_pdf


def _enrich_from_semantic_scholar(title: str) -> dict:
    """Search Semantic Scholar by title and return metadata dict."""
    try:
        with httpx.Client(timeout=SEMANTIC_SCHOLAR_TIMEOUT) as client:
            headers = {}
            if settings.SEMANTIC_SCHOLAR_API_KEY:
                headers["x-api-key"] = settings.SEMANTIC_SCHOLAR_API_KEY
            resp = client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": title, "limit": "1", "fields": "externalIds,title,authors,year,abstract,isOpenAccess,openAccessPdf,venue"},
                headers=headers,
            )
            if resp.status_code != 200:
                return {}
            data = resp.json()
            papers = data.get("data") or []
            if not papers:
                return {}
            paper = papers[0]
            result = {}
            external_ids = paper.get("externalIds") or {}
            if external_ids.get("DOI"):
                result["doi"] = external_ids["DOI"]
            authors = paper.get("authors") or []
            if authors:
                result["authors"] = [a.get("name") for a in authors if a.get("name")]
            if paper.get("year"):
                result["year"] = paper["year"]
            if paper.get("abstract"):
                result["abstract"] = paper["abstract"]
            if paper.get("isOpenAccess"):
                result["is_open_access"] = True
            oa_pdf = paper.get("openAccessPdf") or {}
            if oa_pdf.get("url"):
                result["pdf_url"] = oa_pdf["url"]
            if paper.get("venue"):
                result["journal"] = paper["venue"]
            return result
    except Exception as e:
        logger.debug("Semantic Scholar enrichment failed for '%s': %s", title[:80], e)
        return {}


def _enrich_from_crossref(doi: str) -> dict:
    """Fetch metadata from CrossRef by DOI."""
    result = {}
    try:
        with httpx.Client(timeout=CROSSREF_TIMEOUT) as client:
            resp = client.get(f"https://api.crossref.org/works/{doi}")
            if resp.status_code != 200:
                return result
            item = resp.json().get("message", {})

            # Authors
            cr_authors = item.get("author") or []
            if cr_authors:
                names = []
                for a in cr_authors:
                    given = a.get("given", "")
                    family = a.get("family", "")
                    name = f"{given} {family}".strip()
                    if name:
                        names.append(name)
                if names:
                    result["authors"] = names

            # Year
            for date_field in ("published-print", "published-online", "created"):
                date_parts = (item.get(date_field) or {}).get("date-parts")
                if date_parts and date_parts[0] and date_parts[0][0]:
                    result["year"] = date_parts[0][0]
                    break

            # Journal
            container = item.get("container-title")
            if container and isinstance(container, list) and container[0]:
                result["journal"] = container[0]

            # Abstract (CrossRef sometimes has it, wrapped in HTML)
            if item.get("abstract"):
                result["abstract"] = re.sub(r"<[^>]+>", "", item["abstract"]).strip()

            # URL
            if item.get("URL"):
                result["url"] = item["URL"]

    except Exception as e:
        logger.debug("CrossRef enrichment failed for DOI %s: %s", doi, e)
    return result


def _enrich_from_unpaywall(doi: str) -> dict:
    """Fetch OA status and PDF URL from Unpaywall."""
    email = settings.UNPAYWALL_EMAIL
    if not email:
        return {}
    result = {}
    try:
        with httpx.Client(timeout=UNPAYWALL_TIMEOUT) as client:
            resp = client.get(
                f"https://api.unpaywall.org/v2/{doi}",
                params={"email": email},
            )
            if resp.status_code != 200:
                return result
            data = resp.json()

            if data.get("is_oa"):
                result["is_open_access"] = True

            best_location = data.get("best_oa_location") or {}
            if best_location:
                pdf_url = best_location.get("url_for_pdf")
                if pdf_url:
                    result["pdf_url"] = pdf_url
    except Exception as e:
        logger.debug("Unpaywall enrichment failed for DOI %s: %s", doi, e)
    return result


def _apply_enrichment(ref: Reference, enrichment: dict) -> bool:
    """Apply enrichment dict to reference, only filling in missing fields. Returns True if anything changed."""
    changed = False
    if enrichment.get("authors") and (not ref.authors or len(ref.authors) == 0):
        ref.authors = enrichment["authors"]
        changed = True
    if enrichment.get("year") and not ref.year:
        ref.year = enrichment["year"]
        changed = True
    if enrichment.get("abstract") and not ref.abstract:
        ref.abstract = enrichment["abstract"]
        changed = True
    if enrichment.get("doi") and not ref.doi:
        ref.doi = enrichment["doi"]
        changed = True
    if enrichment.get("journal") and not ref.journal:
        ref.journal = enrichment["journal"]
        changed = True
    if enrichment.get("url") and not ref.url:
        ref.url = enrichment["url"]
        changed = True
    if enrichment.get("is_open_access") and not ref.is_open_access:
        ref.is_open_access = True
        changed = True
    if enrichment.get("pdf_url"):
        # Prefer Unpaywall/S2 direct PDF URLs over extension-scraped viewer URLs
        # (e.g. IEEE stamp URLs return 502 when fetched server-side)
        current = ref.pdf_url or ""
        new_url = enrichment["pdf_url"]
        is_current_direct = current.lower().endswith(".pdf") or "/pdf/" in current.lower()
        is_new_direct = new_url.lower().endswith(".pdf") or "/pdf/" in new_url.lower()
        if not current or (not is_current_direct and is_new_direct):
            ref.pdf_url = new_url
            changed = True
    return changed


def enrich_and_ingest_reference(reference_id: str) -> None:
    """Background task: enrich a reference with external APIs, then ingest its PDF.

    Fully synchronous — runs in Starlette's background task thread pool.
    Uses a fresh DB session since this runs outside the request lifecycle.
    """
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        ref = db.query(Reference).filter(Reference.id == reference_id).first()
        if not ref:
            logger.warning("Enrichment: reference %s not found", reference_id)
            return

        logger.info("Enrichment: starting for reference %s ('%s')", reference_id, (ref.title or "")[:80])

        if not _needs_enrichment(ref):
            # Already has full metadata — just try PDF ingestion
            if ref.pdf_url and not ref.document_id:
                logger.info("Enrichment: reference %s already complete, attempting PDF ingestion", reference_id)
                _try_ingest_pdf(db, ref)
            else:
                logger.info("Enrichment: reference %s already complete, nothing to do", reference_id)
            return

        enrichment = {}

        # Step 1: If we have a DOI, use CrossRef + Unpaywall
        if ref.doi:
            cr_data = _enrich_from_crossref(ref.doi)
            enrichment.update(cr_data)
            uw_data = _enrich_from_unpaywall(ref.doi)
            enrichment.update(uw_data)

        # Step 2: If no DOI, try Semantic Scholar title search
        if not ref.doi and ref.title:
            s2_data = _enrich_from_semantic_scholar(ref.title)
            enrichment.update(s2_data)
            # If we found a DOI from S2, now hit CrossRef + Unpaywall too
            if s2_data.get("doi"):
                cr_data = _enrich_from_crossref(s2_data["doi"])
                for k, v in cr_data.items():
                    if k not in enrichment:
                        enrichment[k] = v
                uw_data = _enrich_from_unpaywall(s2_data["doi"])
                for k, v in uw_data.items():
                    if k not in enrichment:
                        enrichment[k] = v

        # Step 3: Even with a DOI, if still missing fields, try Semantic Scholar
        if ref.doi and ref.title and (not enrichment.get("authors") or not enrichment.get("abstract")):
            s2_data = _enrich_from_semantic_scholar(ref.title)
            for k, v in s2_data.items():
                if k not in enrichment:
                    enrichment[k] = v

        # Apply to reference and commit
        changed = _apply_enrichment(ref, enrichment)
        if changed:
            db.commit()
            db.refresh(ref)
            logger.info(
                "Enriched reference %s: added %s",
                reference_id,
                [k for k in enrichment if enrichment[k]],
            )
        else:
            logger.info(
                "Enrichment: no new data found for reference %s (APIs returned nothing usable)",
                reference_id,
            )

        # Step 4: Ingest PDF if we have a URL and no document yet
        # Done separately so enrichment commit is preserved even if ingestion fails
        if ref.pdf_url and not ref.document_id:
            _try_ingest_pdf(db, ref)
        elif not ref.pdf_url:
            logger.info("Enrichment: no PDF URL for reference %s, skipping ingestion", reference_id)

    except Exception as e:
        db.rollback()
        logger.error("Reference enrichment failed for %s: %s", reference_id, e)
    finally:
        db.close()


def _try_ingest_pdf(db: Session, ref: Reference) -> None:
    """Best-effort PDF ingestion using the existing ingestion service."""
    try:
        from app.services.reference_ingestion_service import ingest_reference_pdf

        success = ingest_reference_pdf(db, ref, owner_id=str(ref.owner_id))
        if success:
            logger.info("PDF ingested for reference %s", ref.id)
        else:
            logger.info("PDF ingestion returned false for reference %s (may be paywalled)", ref.id)
    except Exception as e:
        logger.warning("PDF ingestion failed for reference %s: %s", ref.id, e)
