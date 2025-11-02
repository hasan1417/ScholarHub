from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel
from uuid import UUID


class ChangeBase(BaseModel):
    type: str  # 'insert', 'delete', 'update'
    section: str
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    position: int


class Change(ChangeBase):
    pass


class CommitBase(BaseModel):
    message: str
    content: str
    content_json: Optional[Dict[str, Any]] = None
    compilation_status: Optional[str] = None  # 'success' | 'failed' | 'not_compiled'
    pdf_url: Optional[str] = None
    compile_logs: Optional[str] = None
    state: Optional[str] = None  # 'draft' | 'ready_for_review' | 'published'


class CommitCreate(CommitBase):
    pass


class CommitUpdate(BaseModel):
    message: Optional[str] = None
    content: Optional[str] = None
    content_json: Optional[Dict[str, Any]] = None
    state: Optional[str] = None


class Commit(CommitBase):
    id: UUID
    branch_id: UUID
    author_id: UUID
    timestamp: datetime
    changes: List[Change] = []
    compilation_status: str
    pdf_url: Optional[str] = None
    compile_logs: Optional[str] = None
    state: str

    class Config:
        from_attributes = True


class CommitWithAuthor(Commit):
    author_name: str


class BranchBase(BaseModel):
    name: str
    paper_id: UUID
    parent_branch_id: Optional[UUID] = None


class BranchCreate(BranchBase):
    pass


class BranchUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    last_commit_message: Optional[str] = None


class Branch(BranchBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    status: str
    author_id: UUID
    last_commit_message: str
    is_main: bool

    class Config:
        from_attributes = True


class BranchWithAuthor(Branch):
    author_name: str


class BranchWithCommits(BranchWithAuthor):
    commits: List[CommitWithAuthor] = []


class ConflictBase(BaseModel):
    section: str
    source_content: Optional[str] = None
    target_content: Optional[str] = None
    resolved_content: Optional[str] = None
    status: str = "unresolved"
    resolution_strategy: str = "manual"


class ConflictCreate(ConflictBase):
    merge_request_id: UUID


class ConflictUpdate(BaseModel):
    resolved_content: Optional[str] = None
    status: Optional[str] = None
    resolution_strategy: Optional[str] = None


class Conflict(ConflictBase):
    id: UUID
    merge_request_id: UUID
    resolved_by: Optional[UUID] = None
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MergeRequestBase(BaseModel):
    source_branch_id: UUID
    target_branch_id: UUID
    paper_id: UUID
    title: str
    description: Optional[str] = None


class MergeRequestCreate(MergeRequestBase):
    pass


class MergeRequestUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class MergeRequest(MergeRequestBase):
    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    author_id: UUID
    conflicts: Optional[List[Dict[str, Any]]] = []

    class Config:
        from_attributes = True


class MergeRequestWithDetails(MergeRequest):
    author_name: str
    source_branch_name: str
    target_branch_name: str


class BranchSwitchRequest(BaseModel):
    paper_id: UUID


class BranchSwitchResponse(BaseModel):
    branch: BranchWithAuthor
    content: str


class MergeBranchesRequest(BaseModel):
    source_branch_id: UUID
    target_branch_id: UUID
    strategy: str = "auto"  # 'auto', 'manual'


class MergeBranchesResponse(BaseModel):
    success: bool
    conflicts: Optional[List[Conflict]] = []
    merged_content: Optional[str] = None


class ConflictAnalysisRequest(BaseModel):
    source_branch_id: UUID
    target_branch_id: UUID


class ConflictResolutionRequest(BaseModel):
    conflicts: List[Dict[str, Any]]
    strategy: str  # 'source-wins', 'target-wins', 'smart'
