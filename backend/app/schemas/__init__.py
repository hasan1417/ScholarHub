from .user import UserCreate, UserUpdate, UserResponse, UserInDB
from .research_paper import ResearchPaperCreate, ResearchPaperUpdate, ResearchPaperResponse, ResearchPaperList
from .project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectSummary,
    ProjectDetail,
    ProjectList,
    ProjectMemberCreate,
    ProjectMemberUpdate,
    ProjectMemberResponse,
)
from .paper_member import PaperMemberCreate, PaperMemberResponse
from .document import DocumentCreate, DocumentUpdate, DocumentResponse, DocumentList, DocumentUpload
from .tag import TagCreate, TagResponse
from .branch import (
    BranchCreate, BranchUpdate, Branch, BranchWithAuthor, BranchWithCommits,
    CommitCreate, Commit, CommitWithAuthor,
    MergeRequestCreate, MergeRequest, MergeRequestWithDetails,
    Conflict, Change, BranchSwitchRequest, BranchSwitchResponse,
    MergeBranchesRequest, MergeBranchesResponse
)
from .ai import (
    ChatQuery, ChatResponse, DocumentProcessingResponse, 
    DocumentChunkResponse, DocumentChunksResponse,
    ChatSessionResponse, ChatHistoryResponse, AIServiceStatusResponse
)

__all__ = [
    "UserCreate",
    "UserUpdate", 
    "UserResponse",
    "UserInDB",
    "ResearchPaperCreate",
    "ResearchPaperUpdate",
    "ResearchPaperResponse",
    "ResearchPaperList",
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectSummary",
    "ProjectDetail",
    "ProjectList",
    "ProjectMemberCreate",
    "ProjectMemberUpdate",
    "ProjectMemberResponse",
    "PaperMemberCreate",
    "PaperMemberResponse",
    "DocumentCreate",
    "DocumentUpdate",
    "DocumentResponse",
    "DocumentList",
    "DocumentUpload",
    "TagCreate",
    "TagResponse",
    # Branch Schemas
    "BranchCreate",
    "BranchUpdate",
    "Branch",
    "BranchWithAuthor",
    "BranchWithCommits",
    "CommitCreate",
    "Commit",
    "CommitWithAuthor",
    "MergeRequestCreate",
    "MergeRequest",
    "MergeRequestWithDetails",
    "Conflict",
    "Change",
    "BranchSwitchRequest",
    "BranchSwitchResponse",
    "MergeBranchesRequest",
    "MergeBranchesResponse",
    # AI Schemas
    "ChatQuery",
    "ChatResponse", 
    "DocumentProcessingResponse",
    "DocumentChunkResponse",
    "DocumentChunksResponse",
    "ChatSessionResponse",
    "ChatHistoryResponse",
    "AIServiceStatusResponse"
]
