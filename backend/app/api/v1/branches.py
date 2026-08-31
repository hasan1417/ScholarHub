from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from app.api.deps import get_db, get_current_user
from app.api._paper_access import require_paper_access, require_paper_editor
from app.models import Branch, Commit, MergeRequest, User
from app.schemas.branch import (
    Branch as BranchSchema,
    BranchCreate,
    BranchUpdate,
    BranchWithAuthor,
    BranchSwitchRequest,
    BranchSwitchResponse,
    Commit as CommitSchema,
    CommitCreate,
    CommitUpdate,
    CommitWithAuthor,
    MergeRequest as MergeRequestSchema,
    MergeRequestCreate,
    MergeRequestWithDetails,
    MergeBranchesRequest,
    MergeBranchesResponse,
    ConflictAnalysisRequest,
    Conflict
)

router = APIRouter()


def _display_name(user: User) -> str:
    """Return a safe display name for a user (first + last or email)."""
    first = getattr(user, 'first_name', None) or ''
    last = getattr(user, 'last_name', None) or ''
    name = f"{first} {last}".strip()
    return name or getattr(user, 'email', 'Unknown User')


def _serialize_branch(b: Branch, author: User) -> BranchWithAuthor:
    """Safely serialize a Branch model to BranchWithAuthor schema."""
    return BranchWithAuthor(
        id=b.id,
        name=b.name,
        paper_id=b.paper_id,
        parent_branch_id=b.parent_branch_id,
        created_at=b.created_at,
        updated_at=b.updated_at,
        status=b.status,
        author_id=b.author_id,
        last_commit_message=b.last_commit_message or '',
        is_main=b.is_main or False,
        author_name=_display_name(author)
    )


@router.post("/", response_model=BranchWithAuthor)
def create_branch(
    branch: BranchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new branch"""
    paper = require_paper_editor(db, branch.paper_id, current_user)
    
    # Check if branch name already exists for this paper
    existing_branch = db.query(Branch).filter(
        Branch.paper_id == paper.id,
        Branch.name == branch.name
    ).first()
    if existing_branch:
        raise HTTPException(status_code=400, detail="Branch name already exists")
    
    # Create the branch
    db_branch = Branch(
        name=branch.name,
        paper_id=paper.id,
        parent_branch_id=branch.parent_branch_id,
        author_id=current_user.id,
        is_main=branch.name.lower() == 'main'
    )
    
    db.add(db_branch)
    db.commit()
    db.refresh(db_branch)
    
    # Create response with author name
    response = _serialize_branch(db_branch, current_user)
    
    return response


@router.get("/paper/{paper_id}", response_model=List[BranchWithAuthor])
def get_branches(
    paper_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all branches for a paper"""
    paper = require_paper_access(db, paper_id, current_user)

    # Get branches with author info
    branches = db.query(Branch, User).join(User, Branch.author_id == User.id).filter(
        Branch.paper_id == paper.id
    ).all()

    return [_serialize_branch(branch, author) for branch, author in branches]


@router.post("/{branch_id}/switch", response_model=BranchSwitchResponse)
def switch_branch(
    branch_id: UUID,
    request: BranchSwitchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Switch to a specific branch"""
    branch = db.query(Branch, User).join(User, Branch.author_id == User.id).filter(
        Branch.id == branch_id
    ).first()
    
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    
    branch_obj, author = branch
    require_paper_access(db, branch_obj.paper_id, current_user)
    
    # Get the latest commit content for this branch (prefer LaTeX source if applicable)
    latest_commit = db.query(Commit).filter(
        Commit.branch_id == branch_id
    ).order_by(desc(Commit.timestamp)).first()
    content = ''
    if latest_commit:
        try:
            cj = latest_commit.content_json if isinstance(latest_commit.content_json, dict) else None
            if cj:
                content = cj.get('latex_source') or ''
            else:
                content = latest_commit.content or ''
        except Exception:
            content = latest_commit.content or ''
    
    return BranchSwitchResponse(
        branch=_serialize_branch(branch_obj, author),
        content=content
    )


@router.delete("/{branch_id}")
def delete_branch(
    branch_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a branch"""
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    require_paper_editor(db, branch.paper_id, current_user)
    
    if branch.is_main:
        raise HTTPException(status_code=400, detail="Cannot delete main branch")
    
    # Check if user is the author or has permission
    if branch.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this branch")
    
    db.delete(branch)
    db.commit()
    
    return {"message": "Branch deleted successfully"}


@router.post("/{branch_id}/commit", response_model=CommitWithAuthor)
def commit_changes(
    branch_id: UUID,
    commit: CommitCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a commit in a branch"""
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    require_paper_editor(db, branch.paper_id, current_user)
    
    # All papers are LaTeX — no HTML diff needed
    changes = []
    
    # Create the commit
    db_commit = Commit(
        branch_id=branch_id,
        message=commit.message,
        content=commit.content,
        content_json=commit.content_json,
        author_id=current_user.id,
        changes=changes,
        compilation_status=(commit.compilation_status or 'not_compiled'),
        pdf_url=commit.pdf_url,
        compile_logs=commit.compile_logs,
        state=(commit.state or 'draft')
    )
    
    db.add(db_commit)
    
    # Update branch last commit message
    branch.last_commit_message = commit.message
    db.commit()
    db.refresh(db_commit)
    
    return CommitWithAuthor(
        **db_commit.__dict__,
        author_name=_display_name(current_user)
    )


@router.get("/{branch_id}/commits", response_model=List[CommitWithAuthor])
def get_commit_history(
    branch_id: UUID,
    state: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get commit history for a branch"""
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    require_paper_access(db, branch.paper_id, current_user)
    
    # Get commits with author info, ordered by timestamp desc (newest first)
    q = db.query(Commit, User).join(User, Commit.author_id == User.id).filter(
        Commit.branch_id == branch_id
    )
    if state:
        q = q.filter(Commit.state == state)
    commits = q.order_by(desc(Commit.timestamp)).all()
    
    return [
        CommitWithAuthor(
            **commit.__dict__,
            author_name=_display_name(author)
        )
        for commit, author in commits
    ]


@router.put("/commit/{commit_id}", response_model=CommitWithAuthor)
def update_commit(
    commit_id: UUID,
    payload: CommitUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    c = db.query(Commit).filter(Commit.id == commit_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Commit not found")
    require_paper_editor(db, c.branch.paper_id, current_user)
    if payload.message is not None:
        c.message = payload.message
    if payload.content is not None:
        c.content = payload.content
    if payload.content_json is not None:
        c.content_json = payload.content_json
    # Allow status/state updates via payload.message field? Use state in content_json? Better to accept via query
    if hasattr(payload, 'state') and getattr(payload, 'state') is not None:  # type: ignore[attr-defined]
        try:
            c.state = getattr(payload, 'state')  # type: ignore[attr-defined]
        except Exception:
            pass
    db.commit()
    # Join author
    author = db.query(User).filter(User.id == c.author_id).first()
    return CommitWithAuthor(
        **c.__dict__,
        author_name=_display_name(author) if author else 'Unknown'
    )


@router.post("/merge-requests", response_model=MergeRequestWithDetails)
def create_merge_request(
    merge_request: MergeRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a merge request"""
    paper = require_paper_editor(db, merge_request.paper_id, current_user)

    # Verify branches exist
    source_branch = db.query(Branch).filter(
        Branch.id == merge_request.source_branch_id,
        Branch.paper_id == paper.id,
    ).first()
    target_branch = db.query(Branch).filter(
        Branch.id == merge_request.target_branch_id,
        Branch.paper_id == paper.id,
    ).first()
    
    if not source_branch or not target_branch:
        raise HTTPException(status_code=404, detail="Source or target branch not found")
    
    db_merge_request = MergeRequest(
        source_branch_id=merge_request.source_branch_id,
        target_branch_id=merge_request.target_branch_id,
        paper_id=paper.id,
        title=merge_request.title,
        description=merge_request.description,
        author_id=current_user.id
    )
    
    db.add(db_merge_request)
    db.commit()
    db.refresh(db_merge_request)
    
    return MergeRequestWithDetails(
        **db_merge_request.__dict__,
        author_name=_display_name(current_user),
        source_branch_name=source_branch.name,
        target_branch_name=target_branch.name
    )


@router.get("/merge-requests/paper/{paper_id}", response_model=List[MergeRequestWithDetails])
def get_merge_requests(
    paper_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get merge requests for a paper"""
    paper = require_paper_access(db, paper_id, current_user)

    merge_requests = db.query(
        MergeRequest,
        User,
        Branch.alias('source_branch'),
        Branch.alias('target_branch')
    ).join(
        User, MergeRequest.author_id == User.id
    ).join(
        Branch.alias('source_branch'), MergeRequest.source_branch_id == Branch.alias('source_branch').id
    ).join(
        Branch.alias('target_branch'), MergeRequest.target_branch_id == Branch.alias('target_branch').id
    ).filter(
        MergeRequest.paper_id == paper.id
    ).all()
    
    return [
        MergeRequestWithDetails(
            **mr.__dict__,
            author_name=_display_name(author),
            source_branch_name=source_branch.name,
            target_branch_name=target_branch.name
        )
        for mr, author, source_branch, target_branch in merge_requests
    ]


@router.post("/merge", response_model=MergeBranchesResponse)
def merge_branches(
    request: MergeBranchesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Merge branches"""
    # For demo, return successful merge
    source_branch = db.query(Branch).filter(Branch.id == request.source_branch_id).first()
    target_branch = db.query(Branch).filter(Branch.id == request.target_branch_id).first()
    
    if not source_branch or not target_branch:
        raise HTTPException(status_code=404, detail="Source or target branch not found")
    paper = require_paper_editor(db, target_branch.paper_id, current_user)
    if source_branch.paper_id != paper.id or target_branch.paper_id != paper.id:
        raise HTTPException(
            status_code=400,
            detail="Source and target branches must belong to the same paper",
        )
    
    # Get latest commits from both branches
    source_commit = db.query(Commit).filter(
        Commit.branch_id == request.source_branch_id
    ).order_by(desc(Commit.timestamp)).first()
    
    target_commit = db.query(Commit).filter(
        Commit.branch_id == request.target_branch_id
    ).order_by(desc(Commit.timestamp)).first()
    
    # Simple merge - in production you'd want sophisticated conflict detection
    merged_content = source_commit.content if source_commit else target_commit.content if target_commit else ""
    
    # Create merge commit in target branch
    if merged_content:
        merge_commit = Commit(
            branch_id=request.target_branch_id,
            message=f"Merge {source_branch.name} into {target_branch.name}",
            content=merged_content,
            content_json=source_commit.content_json if source_commit else None,
            author_id=current_user.id,
            changes=[{
                'type': 'update',
                'section': 'Merge',
                'newContent': f'Merged content from {source_branch.name}',
                'position': 0
            }]
        )
        db.add(merge_commit)
        
        # Update source branch status, but keep system 'draft' branch active
        try:
            if (source_branch.name or '').lower() != 'draft':
                source_branch.status = 'merged'
        except Exception:
            source_branch.status = 'merged'
        db.commit()
    
    return MergeBranchesResponse(
        success=True,
        merged_content=merged_content
    )


@router.post("/analyze-conflicts", response_model=List[Conflict])
def analyze_conflicts(
    request: ConflictAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Analyze conflicts between branches"""
    source_branch = db.query(Branch).filter(Branch.id == request.source_branch_id).first()
    target_branch = db.query(Branch).filter(Branch.id == request.target_branch_id).first()
    if not source_branch or not target_branch:
        raise HTTPException(status_code=404, detail="Source or target branch not found")
    require_paper_access(db, source_branch.paper_id, current_user)
    if target_branch.paper_id != source_branch.paper_id:
        require_paper_access(db, target_branch.paper_id, current_user)

    # For demo, return mock conflicts
    return [
        Conflict(
            id=UUID('12345678-1234-5678-9abc-123456789abc'),
            merge_request_id=UUID('12345678-1234-5678-9abc-123456789abc'),
            section='Introduction',
            source_content='This is the source content for the introduction.',
            target_content='This is the target content for the introduction.',
            status='unresolved',
            resolution_strategy='manual'
        )
    ]
