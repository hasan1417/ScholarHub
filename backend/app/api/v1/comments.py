from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.api.deps import get_db, get_current_user
from app.models import Comment, ResearchPaper, Commit, User

router = APIRouter()


@router.get("/comments/paper/{paper_id}")
async def list_comments(paper_id: UUID, commit_id: Optional[UUID] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Verify paper access
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    # TODO: enforce membership access if needed
    q = db.query(Comment).filter(Comment.paper_id == paper_id)
    if commit_id:
        q = q.filter(Comment.commit_id == commit_id)
    items = q.order_by(Comment.created_at.asc()).all()
    return [
        {
            "id": str(c.id),
            "paper_id": str(c.paper_id),
            "commit_id": str(c.commit_id) if c.commit_id else None,
            "user_id": str(c.user_id),
            "text": c.text,
            "line_number": c.line_number,
            "resolved": bool(c.resolved),
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in items
    ]


@router.post("/comments/")
async def create_comment(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    paper_id = payload.get("paper_id")
    commit_id = payload.get("commit_id")
    text = (payload.get("text") or "").strip()
    line_number = payload.get("line_number")
    if not paper_id or not text:
        raise HTTPException(status_code=400, detail="paper_id and text are required")
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if commit_id:
        cm = db.query(Commit).filter(Commit.id == commit_id).first()
        if not cm:
            raise HTTPException(status_code=404, detail="Commit not found")
    c = Comment(
        paper_id=paper_id,
        commit_id=commit_id,
        user_id=current_user.id,
        text=text,
        line_number=int(line_number) if line_number is not None else None
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {
        "id": str(c.id),
        "paper_id": str(c.paper_id),
        "commit_id": str(c.commit_id) if c.commit_id else None,
        "user_id": str(c.user_id),
        "text": c.text,
        "line_number": c.line_number,
        "resolved": bool(c.resolved),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.put("/comments/{comment_id}/resolve")
async def resolve_comment(comment_id: UUID, resolved: bool = True, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    c = db.query(Comment).filter(Comment.id == comment_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")
    # Simple: allow comment owner or paper owner
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == c.paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if c.user_id != current_user.id and paper.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    c.resolved = bool(resolved)
    db.commit()
    return { "ok": True }

