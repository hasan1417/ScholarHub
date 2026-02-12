import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.encryption import decrypt_api_key
from app.database import get_db
from app.models.user import User
from app.models.reference import Reference
from app.models.project_reference import (
    ProjectReference,
    ProjectReferenceOrigin,
    ProjectReferenceStatus,
)
from app.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_zotero_client(user: User):
    """Return a pyzotero Zotero instance for the given user."""
    from pyzotero import zotero as pyzotero

    if not user.zotero_api_key or not user.zotero_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zotero credentials not configured. Add them in Settings.",
        )
    api_key = decrypt_api_key(user.zotero_api_key)
    return pyzotero.Zotero(user.zotero_user_id, "user", api_key)


def _parse_zotero_year(date_str: Optional[str]) -> Optional[int]:
    """Extract a 4-digit year from a free-text Zotero date field."""
    if not date_str:
        return None
    m = re.search(r"\b(\d{4})\b", date_str)
    return int(m.group(1)) if m else None


def _normalize_title(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _find_duplicate(
    db: Session,
    owner_id,
    title: str,
    doi: Optional[str],
    year: Optional[int],
) -> Optional[Reference]:
    """Find existing reference by DOI or normalized title+year."""
    existing = db.query(Reference).filter(Reference.owner_id == owner_id).all()
    norm_title = _normalize_title(title)
    for ref in existing:
        if doi and ref.doi and ref.doi.strip().lower() == doi.strip().lower():
            return ref
        if _normalize_title(ref.title) == norm_title and (
            not year or not ref.year or ref.year == year
        ):
            return ref
    return None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ImportRequest(BaseModel):
    item_keys: list[str]
    project_id: Optional[str] = None


class ImportResult(BaseModel):
    imported: int
    skipped: int
    reference_ids: list[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/collections")
async def list_collections(
    current_user: User = Depends(get_current_user),
):
    """List the user's Zotero collections."""
    zot = _get_zotero_client(current_user)
    try:
        raw = zot.collections()
    except Exception as exc:
        logger.error("Zotero collections error: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to fetch Zotero collections")

    collections = []
    for c in raw:
        data = c.get("data", {})
        meta = c.get("meta", {})
        collections.append({
            "key": data.get("key"),
            "name": data.get("name"),
            "num_items": meta.get("numItems", 0),
        })
    return {"collections": collections}


@router.get("/items")
async def list_items(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    collection_key: Optional[str] = Query(None),
    limit: int = Query(100, le=200),
):
    """Preview items from a Zotero collection (or all items). Includes dedup flag."""
    zot = _get_zotero_client(current_user)
    try:
        if collection_key:
            raw = zot.collection_items(collection_key, limit=limit, itemType="-attachment || note")
        else:
            raw = zot.top(limit=limit)
    except Exception as exc:
        logger.error("Zotero items error: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to fetch Zotero items")

    items = []
    for entry in raw:
        data = entry.get("data", {})
        item_type = data.get("itemType", "")
        if item_type in ("attachment", "note"):
            continue

        title = data.get("title", "")
        doi = data.get("DOI", "") or None
        year = _parse_zotero_year(data.get("date"))

        creators = data.get("creators", [])
        authors = [
            " ".join(filter(None, [c.get("firstName"), c.get("lastName")]))
            for c in creators
            if c.get("creatorType") == "author"
        ]

        already_imported = _find_duplicate(db, current_user.id, title, doi, year) is not None

        items.append({
            "key": data.get("key"),
            "title": title,
            "authors": authors,
            "year": year,
            "doi": doi,
            "journal": data.get("publicationTitle"),
            "abstract": (data.get("abstractNote") or "")[:500],
            "url": data.get("url"),
            "item_type": item_type,
            "already_imported": already_imported,
        })

    return {"items": items, "total": len(items)}


@router.post("/import", response_model=ImportResult)
async def import_items(
    payload: ImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import selected Zotero items as references."""
    # Subscription limit check
    allowed, current_count, limit = SubscriptionService.check_resource_limit(
        db, current_user.id, "references_total"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "limit_exceeded",
                "feature": "references_total",
                "current": current_count,
                "limit": limit,
                "message": f"Reference library limit reached ({current_count}/{limit}). Upgrade for more.",
            },
        )

    zot = _get_zotero_client(current_user)

    # Fetch items by keys
    try:
        raw = zot.items(itemKey=",".join(payload.item_keys))
    except Exception as exc:
        logger.error("Zotero fetch items error: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to fetch items from Zotero")

    imported = 0
    skipped = 0
    reference_ids: list[str] = []

    for entry in raw:
        data = entry.get("data", {})
        title = data.get("title", "")
        if not title:
            skipped += 1
            continue

        doi = data.get("DOI") or None
        year = _parse_zotero_year(data.get("date"))
        creators = data.get("creators", [])
        authors = [
            " ".join(filter(None, [c.get("firstName"), c.get("lastName")]))
            for c in creators
            if c.get("creatorType") == "author"
        ]

        dup = _find_duplicate(db, current_user.id, title, doi, year)
        if dup:
            skipped += 1
            reference_ids.append(str(dup.id))
            # Still link to project if requested
            if payload.project_id:
                _link_to_project(db, dup, payload.project_id, current_user.id)
            continue

        # Check remaining capacity
        remaining = limit - (current_count + imported)
        if remaining <= 0:
            break

        ref = Reference(
            owner_id=current_user.id,
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            url=data.get("url"),
            source="zotero",
            journal=data.get("publicationTitle"),
            abstract=data.get("abstractNote"),
            is_open_access=False,
        )
        db.add(ref)
        db.flush()

        if payload.project_id:
            _link_to_project(db, ref, payload.project_id, current_user.id)

        reference_ids.append(str(ref.id))
        imported += 1

    db.commit()
    return ImportResult(imported=imported, skipped=skipped, reference_ids=reference_ids)


def _link_to_project(db: Session, ref: Reference, project_id: str, user_id) -> None:
    """Create a ProjectReference link if it doesn't already exist."""
    import uuid as _uuid

    pid = _uuid.UUID(project_id) if isinstance(project_id, str) else project_id
    exists = (
        db.query(ProjectReference)
        .filter(
            ProjectReference.project_id == pid,
            ProjectReference.reference_id == ref.id,
        )
        .first()
    )
    if exists:
        return
    pr = ProjectReference(
        project_id=pid,
        reference_id=ref.id,
        status=ProjectReferenceStatus.APPROVED,
        origin=ProjectReferenceOrigin.IMPORT,
        added_by_user_id=user_id,
    )
    db.add(pr)
