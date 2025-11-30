from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session
from app.models import Reference, PaperReference


def summarize_paper_references(db: Session, paper_id: Optional[str] = None, owner_id: Optional[str] = None) -> Tuple[List[str], List[Dict[str, str]]]:
    """
    Return a lightweight list of reference titles/years attached to a paper (or a user's library when owner_id is provided).
    """
    query = db.query(Reference)
    if paper_id:
        query = query.join(PaperReference, PaperReference.reference_id == Reference.id).filter(PaperReference.paper_id == paper_id)
    elif owner_id:
        query = query.filter(Reference.owner_id == owner_id)
    else:
        return [], []

    refs = query.order_by(Reference.created_at.desc()).all()

    lines: List[str] = []
    sources: List[Dict[str, str]] = []
    for i, ref in enumerate(refs, 1):
        title = ref.title or "Untitled reference"
        year = ref.year or "n/a"
        lines.append(f"{i}. {title} ({year})")
        sources.append({"id": str(ref.id), "title": title, "year": year})
    return lines, sources
