from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from app.api.deps import get_db, get_current_user
from app.models import SectionLock, ResearchPaper, User

router = APIRouter()


@router.get('/section-locks/paper/{paper_id}')
async def list_section_locks(paper_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail='Paper not found')
    now = datetime.now(timezone.utc)
    locks = db.query(SectionLock).filter(SectionLock.paper_id == paper_id, SectionLock.expires_at > now).all()
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
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail='Paper not found')
    now = datetime.now(timezone.utc)
    # Check existing lock
    existing = db.query(SectionLock).filter(SectionLock.paper_id == paper_id, SectionLock.section_key == section_key, SectionLock.expires_at > now).first()
    if existing and existing.user_id != current_user.id:
        raise HTTPException(status_code=409, detail='Section already locked')
    if existing and existing.user_id == current_user.id:
        existing.expires_at = now + timedelta(seconds=duration_sec)
        db.commit()
        return { 'id': str(existing.id), 'paper_id': str(existing.paper_id), 'section_key': existing.section_key, 'user_id': str(existing.user_id), 'expires_at': existing.expires_at.isoformat() }
    lock = SectionLock(paper_id=paper_id, section_key=section_key, user_id=current_user.id, expires_at=now + timedelta(seconds=duration_sec))
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
    lock = db.query(SectionLock).filter(SectionLock.paper_id == paper_id, SectionLock.section_key == section_key).first()
    if not lock:
        return { 'ok': True }
    if lock.user_id != current_user.id:
        raise HTTPException(status_code=403, detail='Not lock owner')
    db.delete(lock)
    db.commit()
    return { 'ok': True }

