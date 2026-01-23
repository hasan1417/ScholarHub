from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from app.api.deps import get_db, get_current_user
from app.models import SectionLock, ResearchPaper, User

router = APIRouter()


def _is_valid_uuid(val: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False


def _parse_short_id(url_id: str) -> Optional[str]:
    """Extract short_id from a URL identifier (slug-shortid or just shortid)."""
    if not url_id or _is_valid_uuid(url_id):
        return None
    if len(url_id) == 8 and url_id.isalnum():
        return url_id
    last_hyphen = url_id.rfind('-')
    if last_hyphen > 0:
        potential_short_id = url_id[last_hyphen + 1:]
        if len(potential_short_id) == 8 and potential_short_id.isalnum():
            return potential_short_id
    return None


def _get_paper_or_404(db: Session, paper_id: str) -> ResearchPaper:
    """Get paper by UUID or slug-shortid format."""
    paper = None
    if _is_valid_uuid(paper_id):
        try:
            paper = db.query(ResearchPaper).filter(ResearchPaper.id == UUID(paper_id)).first()
        except (ValueError, AttributeError):
            pass
    if not paper:
        short_id = _parse_short_id(paper_id)
        if short_id:
            paper = db.query(ResearchPaper).filter(ResearchPaper.short_id == short_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail='Paper not found')
    return paper


@router.get('/section-locks/paper/{paper_id}')
async def list_section_locks(paper_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    paper = _get_paper_or_404(db, paper_id)
    now = datetime.now(timezone.utc)
    locks = db.query(SectionLock).filter(SectionLock.paper_id == paper.id, SectionLock.expires_at > now).all()
    return [
        {
            'id': str(l.id),
            'paper_id': str(l.paper_id),
            'section_key': l.section_key,
            'user_id': str(l.user_id),
            'expires_at': l.expires_at.isoformat(),
        } for l in locks
    ]


@router.post('/section-locks/lock')
async def lock_section(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    paper_id = payload.get('paper_id')
    section_key = (payload.get('section_key') or '').strip()
    duration_sec = int(payload.get('duration_sec') or 300)
    if not paper_id or not section_key:
        raise HTTPException(status_code=400, detail='paper_id and section_key are required')
    paper = _get_paper_or_404(db, str(paper_id))
    now = datetime.now(timezone.utc)
    # Check existing lock
    existing = db.query(SectionLock).filter(SectionLock.paper_id == paper.id, SectionLock.section_key == section_key, SectionLock.expires_at > now).first()
    if existing and existing.user_id != current_user.id:
        raise HTTPException(status_code=409, detail='Section already locked')
    if existing and existing.user_id == current_user.id:
        existing.expires_at = now + timedelta(seconds=duration_sec)
        db.commit()
        return { 'id': str(existing.id), 'paper_id': str(existing.paper_id), 'section_key': existing.section_key, 'user_id': str(existing.user_id), 'expires_at': existing.expires_at.isoformat() }
    lock = SectionLock(paper_id=paper.id, section_key=section_key, user_id=current_user.id, expires_at=now + timedelta(seconds=duration_sec))
    db.add(lock)
    db.commit()
    db.refresh(lock)
    return { 'id': str(lock.id), 'paper_id': str(lock.paper_id), 'section_key': lock.section_key, 'user_id': str(lock.user_id), 'expires_at': lock.expires_at.isoformat() }


@router.post('/section-locks/unlock')
async def unlock_section(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    paper_id = payload.get('paper_id')
    section_key = (payload.get('section_key') or '').strip()
    if not paper_id or not section_key:
        raise HTTPException(status_code=400, detail='paper_id and section_key are required')
    paper = _get_paper_or_404(db, str(paper_id))
    lock = db.query(SectionLock).filter(SectionLock.paper_id == paper.id, SectionLock.section_key == section_key).first()
    if not lock:
        return { 'ok': True }
    if lock.user_id != current_user.id:
        raise HTTPException(status_code=403, detail='Not lock owner')
    db.delete(lock)
    db.commit()
    return { 'ok': True }

