from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from app.api.deps import get_db, get_current_user
from app.models import Branch, Commit, MergeRequest, User, ResearchPaper
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
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


def calculate_changes_from_html(previous_content: str, new_content: str) -> List[dict]:
    """Calculate changes between two HTML content versions"""
    from bs4 import BeautifulSoup
    import re
    
    def html_to_text(html: str) -> str:
        soup = BeautifulSoup(html, 'html.parser')
        return soup.get_text(strip=True, separator=' ')
    
    def extract_sections(html: str) -> List[dict]:
        soup = BeautifulSoup(html, 'html.parser')
        sections = []
        
        # Extract headings
        for i, heading in enumerate(soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])):
            sections.append({
                'type': f'Heading ({heading.name.upper()})',
                'content': heading.get_text(strip=True)
            })
        
        # Extract paragraphs
        for i, p in enumerate(soup.find_all('p')):
            text = p.get_text(strip=True)
            if text and len(text) > 10:
                sections.append({
                    'type': f'Paragraph {i + 1}',
                    'content': text[:150] + '...' if len(text) > 150 else text
                })
        
        # If no sections found, return full text
        if not sections:
            text = html_to_text(html)
            if text:
                sections.append({
                    'type': 'Content',
                    'content': text[:200] + '...' if len(text) > 200 else text
                })
        
        return sections
    
    changes = []
    
    if previous_content != new_content:
        old_sections = extract_sections(previous_content)
        new_sections = extract_sections(new_content)
        
        if not old_sections and new_sections:
            # New content added
            for i, section in enumerate(new_sections):
                changes.append({
                    'type': 'insert',
                    'section': section['type'],
                    'newContent': section['content'],
                    'position': i
                })
        elif old_sections and not new_sections:
            # Content deleted
            for i, section in enumerate(old_sections):
                changes.append({
                    'type': 'delete',
                    'section': section['type'],
                    'oldContent': section['content'],
                    'position': i
                })
        else:
            # Content modified
            max_sections = max(len(old_sections), len(new_sections))
            
            for i in range(max_sections):
                old_section = old_sections[i] if i < len(old_sections) else None
                new_section = new_sections[i] if i < len(new_sections) else None
                
                if not old_section and new_section:
                    changes.append({
                        'type': 'insert',
                        'section': new_section['type'],
                        'newContent': new_section['content'],
                        'position': i
                    })
                elif old_section and not new_section:
                    changes.append({
                        'type': 'delete',
                        'section': old_section['type'],
                        'oldContent': old_section['content'],
                        'position': i
                    })
                elif old_section and new_section and old_section['content'] != new_section['content']:
                    changes.append({
                        'type': 'update',
                        'section': new_section['type'],
                        'oldContent': old_section['content'],
                        'newContent': new_section['content'],
                        'position': i
                    })
        
        # If no changes detected, add general update
        if not changes:
            old_text = html_to_text(previous_content)
            new_text = html_to_text(new_content)
            
            changes.append({
                'type': 'update',
                'section': 'Document Content',
                'oldContent': old_text[:100] + '...' if len(old_text) > 100 else old_text,
                'newContent': new_text[:100] + '...' if len(new_text) > 100 else new_text,
                'position': 0
            })
    
    return changes if changes else [{
        'type': 'insert',
        'section': 'Initial Content',
        'newContent': 'Document created with initial content',
        'position': 0
    }]


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
    # Check if paper exists and user has access
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == branch.paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Check if branch name already exists for this paper
    existing_branch = db.query(Branch).filter(
        Branch.paper_id == branch.paper_id,
        Branch.name == branch.name
    ).first()
    if existing_branch:
        raise HTTPException(status_code=400, detail="Branch name already exists")
    
    # Create the branch
    db_branch = Branch(
        name=branch.name,
        paper_id=branch.paper_id,
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
    # Check if paper exists and user has access
    paper = _get_paper_or_404(db, paper_id)

    # Get branches with author info
    branches = db.query(Branch, User).join(User, Branch.author_id == User.id).filter(
        Branch.paper_id == paper.id
    ).all()

    # If no branches exist, create a main branch
    if not branches:
        main_branch = Branch(
            name='main',
            paper_id=paper.id,
            author_id=current_user.id,
            is_main=True,
            last_commit_message='Initial commit'
        )
        db.add(main_branch)
        db.commit()
        db.refresh(main_branch)
        
        # Create initial commit — respect LaTeX vs Rich
        pj = getattr(paper, 'content_json', None)
        is_latex = False
        try:
            is_latex = bool(isinstance(pj, dict) and pj.get('authoring_mode') == 'latex')
        except Exception:
            is_latex = False
        initial_commit = Commit(
            branch_id=main_branch.id,
            message='Initial commit',
            content='' if is_latex else (paper.content or ''),
            content_json=pj if is_latex else getattr(paper, 'content_json', None),
            author_id=current_user.id,
            changes=[{
                'type': 'insert',
                'section': 'Initial Content',
                'newContent': 'Document created',
                'position': 0
            }]
        )
        db.add(initial_commit)
        db.commit()
        
        branches = [(main_branch, current_user)]
    
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
    
    # Get the latest commit content for this branch (prefer LaTeX source if applicable)
    latest_commit = db.query(Commit).filter(
        Commit.branch_id == branch_id
    ).order_by(desc(Commit.timestamp)).first()
    content = ''
    if latest_commit:
        try:
            cj = latest_commit.content_json if isinstance(latest_commit.content_json, dict) else None
            if cj and cj.get('authoring_mode') == 'latex':
                content = cj.get('latex_source') or ''
            else:
                content = latest_commit.content or ''
        except Exception:
            content = latest_commit.content or ''
    else:
        content = ''
    
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
    
    # Get previous commit to calculate changes
    previous_commit = db.query(Commit).filter(
        Commit.branch_id == branch_id
    ).order_by(desc(Commit.timestamp)).first()
    
    previous_content = previous_commit.content if previous_commit else ''
    # For LaTeX payloads, do not attempt HTML diff
    is_latex = False
    try:
        is_latex = bool(commit.content_json and isinstance(commit.content_json, dict) and commit.content_json.get('authoring_mode') == 'latex')
    except Exception:
        is_latex = False
    changes = [] if is_latex else calculate_changes_from_html(previous_content, commit.content)
    
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
    # For simplicity: allow author or any paper collaborator (omitted full checks)
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
    # Verify branches exist
    source_branch = db.query(Branch).filter(Branch.id == merge_request.source_branch_id).first()
    target_branch = db.query(Branch).filter(Branch.id == merge_request.target_branch_id).first()
    
    if not source_branch or not target_branch:
        raise HTTPException(status_code=404, detail="Source or target branch not found")
    
    db_merge_request = MergeRequest(
        source_branch_id=merge_request.source_branch_id,
        target_branch_id=merge_request.target_branch_id,
        paper_id=merge_request.paper_id,
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
    paper = _get_paper_or_404(db, paper_id)

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
