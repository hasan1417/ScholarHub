from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.api.deps import get_db, get_current_user
from app.api._paper_access import require_paper_access, require_paper_editor
from app.models import Branch, Comment, Commit, User

router = APIRouter()


@router.get("/comments/paper/{paper_id}")
async def list_comments(paper_id: str, commit_id: Optional[UUID] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    paper = require_paper_access(db, paper_id, current_user)
    q = db.query(Comment).filter(Comment.paper_id == paper.id)
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
    paper = require_paper_access(db, str(paper_id), current_user)
    if commit_id:
        cm = db.query(Commit).join(
            Branch, Commit.branch_id == Branch.id
        ).filter(
            Commit.id == commit_id,
            Branch.paper_id == paper.id,
        ).first()
        if not cm:
            raise HTTPException(status_code=404, detail="Commit not found")
    c = Comment(
        paper_id=paper.id,
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
    paper = require_paper_access(db, c.paper_id, current_user)
    if c.user_id != current_user.id:
        require_paper_editor(db, paper.id, current_user)
    c.resolved = bool(resolved)
    db.commit()
    return { "ok": True }
