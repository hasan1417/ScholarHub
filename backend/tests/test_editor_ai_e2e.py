#!/usr/bin/env python3
"""
Live E2E test for Editor AI features (SmartAgentServiceV2OR).

Creates real data, sends real chat messages through stream_query(),
and verifies tools, persistence, collaboration, and rolling summary
end-to-end with dynamic, human-like conversation patterns.

Run all channels:
    docker compose exec backend python tests/test_editor_ai_e2e.py

Run single channel:
    docker compose exec backend python tests/test_editor_ai_e2e.py --channel 3

Cheap model (default):
    docker compose exec backend python tests/test_editor_ai_e2e.py --model openai/gpt-4o-mini

Summary only:
    docker compose exec backend python tests/test_editor_ai_e2e.py --quiet
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, List, Optional

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text as sa_text
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

logger = logging.getLogger("editor_ai_e2e")


# ── ANSI colors ───────────────────────────────────────────────────────────

class C:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


# ── Test data ─────────────────────────────────────────────────────────────

LATEX_DOCUMENT = r"""\documentclass[12pt]{article}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}

\title{Adaptive Gradient Methods for Efficient Training of Large Language Models}
\author{Alice Chen\textsuperscript{1} \and Bob Martinez\textsuperscript{2}}
\date{January 2026}

\begin{document}
\maketitle

\begin{abstract}
Large language models (LLMs) have achieved remarkable performance across a wide range of natural language tasks. However, training these models remain computationally expensive. In this work, we propose AdaptGrad, an adaptive gradient method that dynamicaly adjusts learning rates per-parameter based on gradient statistics. Our experiments on GPT-scale models demonstrate a 23\% reduction in training time while maintaining comparable perplexity scores ($\Delta < 0.3$).
\end{abstract}

\section{Introduction}
The scaling of language models from millions to billions of parameters has led to significant advances in natural language understanding and generation \cite{brown2020language}. However, this scaling comes at a steep computational cost: training GPT-3 required approximately 3,640 petaflop-days of compute \cite{kaplan2020scaling}.

Traditional optimization methods such as Adam \cite{kingma2014adam} and its variants have been the workhorses of deep learning. Yet, their fixed hyperparameter schedules may not be optimal for the non-stationary loss landscapes encountered during LLM training.

\section{Related Work}
Prior work on adaptive learning rates includes AdaGrad, RMSProp, and Adam. Recent efforts have explored layer-wise learning rate adaptation and gradient noise scaling for large-scale training.

\section{Method}
We introduce AdaptGrad, which computes per-parameter learning rates as:
\begin{equation}
\eta_i^{(t)} = \eta_0 \cdot \frac{\sqrt{1 - \beta_2^t}}{1 - \beta_1^t} \cdot \frac{1}{\sqrt{\hat{v}_i^{(t)}} + \epsilon} \cdot \alpha_i^{(t)}
\end{equation}
where $\alpha_i^{(t)}$ is our novel adaptation factor computed from second-order gradient statistics.

\section{Experiments}
We evaluate AdaptGrad on three model scales:
\begin{itemize}
  \item Small (125M parameters): trained on WikiText-103
  \item Medium (1.3B parameters): trained on The Pile
  \item Large (6.7B parameters): trained on a curated web corpus
\end{itemize}

Results show consistent improvements across all scales, with the largest gains observed at the 6.7B scale (23\% wall-clock reduction).

\section{Results}
Our main findings are summarized in Table~\ref{tab:results}. AdaptGrad achieves lower perplexity at every checkpoint compared to Adam and AdaFactor baselines. The adaptation factor $\alpha_i^{(t)}$ converges within the first 5\% of training.

\section{Conclusion}
We have presented AdaptGrad, a simple yet effective adaptive gradient method for LLM training. Future work will explore extending this approach to distributed training settings and investigating the interaction with gradient compression techniques.

\bibliographystyle{plain}
\bibliography{references}

\end{document}
"""

TEST_REFERENCES = [
    {
        "title": "Language Models are Few-Shot Learners",
        "authors": ["Tom Brown", "Benjamin Mann", "Nick Ryder"],
        "year": 2020,
        "doi": "10.5555/3495724.3495883",
        "abstract": "We demonstrate that scaling up language models greatly improves task-agnostic, few-shot performance.",
    },
    {
        "title": "Adam: A Method for Stochastic Optimization",
        "authors": ["Diederik P. Kingma", "Jimmy Ba"],
        "year": 2014,
        "doi": "10.48550/arXiv.1412.6980",
        "abstract": "We introduce Adam, an algorithm for first-order gradient-based optimization of stochastic objective functions.",
    },
    {
        "title": "Scaling Laws for Neural Language Models",
        "authors": ["Jared Kaplan", "Sam McCandlish", "Tom Henighan"],
        "year": 2020,
        "doi": "10.48550/arXiv.2001.08361",
        "abstract": "We study empirical scaling laws for language model performance on the cross-entropy loss.",
    },
]


# ── Spec dataclasses ──────────────────────────────────────────────────────

@dataclass
class TurnSpec:
    message: str
    expected_tools: List[str] = field(default_factory=list)  # OR logic — at least one must appear
    forbidden_tools: List[str] = field(default_factory=list)
    content_must_contain: List[str] = field(default_factory=list)  # hard fail
    content_should_contain: List[str] = field(default_factory=list)  # soft warn (case-insensitive)
    allow_no_tool: bool = False  # allow empty _last_tools_called
    user_index: int = 0  # 0 = User A, 1 = User B (Channel 6)
    min_length: int = 10
    max_length: int = 20000


@dataclass
class ChannelSpec:
    name: str
    description: str
    turns: List[TurnSpec]
    check_persistence: bool = True
    expected_message_count: Optional[int] = None  # user + assistant messages
    check_tools_in_context: bool = False
    check_multi_user: bool = False
    check_summary: bool = False


@dataclass
class TurnResult:
    turn_num: int
    message: str
    tools_called: List[str]
    response_preview: str
    latency_ms: int
    passed: bool
    warnings: List[str]
    errors: List[str]


@dataclass
class ChannelResult:
    channel_name: str
    turns: List[TurnResult]
    total_turns: int
    passed_turns: int
    warned_turns: int
    failed_turns: int
    duration_s: float
    post_check_errors: List[str] = field(default_factory=list)
    post_check_warnings: List[str] = field(default_factory=list)


# ── 7 Test Channels ──────────────────────────────────────────────────────

CHANNELS: List[ChannelSpec] = [
    # Channel 1: Quick Questions (4 turns) — all answer_question
    ChannelSpec(
        name="Channel 1: Quick Questions",
        description="Short factual queries — all answer_question",
        expected_message_count=8,
        turns=[
            TurnSpec(
                message="What is the title of this paper?",
                expected_tools=["answer_question"],
                content_should_contain=["adaptive gradient", "large language"],
            ),
            TurnSpec(
                message="How many sections does this document have?",
                expected_tools=["answer_question"],
                content_should_contain=["6", "section"],
            ),
            TurnSpec(
                message="What optimization method does the paper propose?",
                expected_tools=["answer_question"],
                content_should_contain=["adaptgrad"],
            ),
            TurnSpec(
                message="Who are the authors?",
                expected_tools=["answer_question"],
                content_should_contain=["alice", "bob"],
            ),
        ],
    ),

    # Channel 2: Editing Flow (5 turns) — all propose_edit
    ChannelSpec(
        name="Channel 2: Editing Flow",
        description="Grammar fixes, rewrites, additions — all propose_edit",
        expected_message_count=10,
        turns=[
            TurnSpec(
                message='Fix the grammar error: "remain" should be "remains" in the abstract.',
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
                content_should_contain=["remains"],
            ),
            TurnSpec(
                message="Shorten the introduction to 2 concise sentences.",
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
            TurnSpec(
                message="Add a concluding paragraph to the Conclusion section about potential impact on AI research costs.",
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
            TurnSpec(
                message='Rewrite the sentence about GPT-3 compute requirements to be more precise. Use "approximately 3,640 petaflop-days".',
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
            TurnSpec(
                message='Change the title to "AdaptGrad: Efficient Adaptive Gradient Methods for LLM Training".',
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
                content_should_contain=["adaptgrad"],
            ),
        ],
    ),

    # Channel 3: Review & Improve (4 turns)
    # NOTE: review_document is an INTERMEDIATE tool — the AI sees the review
    # output, then generates its own response. Subsequent turns must use
    # very specific phrasing to avoid re-triggering review_document.
    ChannelSpec(
        name="Channel 3: Review & Improve",
        description="review_document → specific edit → fix typo → question",
        expected_message_count=8,
        turns=[
            TurnSpec(
                message="Review this paper and give me detailed feedback.",
                expected_tools=["review_document"],
                content_should_contain=["suggest"],
            ),
            TurnSpec(
                message='Fix the word "remain" to "remains" in the abstract.',
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
            TurnSpec(
                message='Fix the typo "dynamicaly" to "dynamically" in the abstract.',
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
                content_should_contain=["dynamically"],
            ),
            TurnSpec(
                message="How many citations are used in the introduction section?",
                expected_tools=["answer_question"],
            ),
        ],
    ),

    # Channel 4: Template Conversion (3 turns)
    ChannelSpec(
        name="Channel 4: Template Conversion",
        description="list_available_templates → convert to IEEE → switch to ACL",
        expected_message_count=6,
        turns=[
            TurnSpec(
                message="What conference formats are available?",
                expected_tools=["list_available_templates"],
                content_should_contain=["ieee", "acl"],
            ),
            TurnSpec(
                message="Convert this paper to IEEE format.",
                expected_tools=["apply_template", "propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
            TurnSpec(
                message="Actually, convert it to ACL format instead.",
                expected_tools=["apply_template", "propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
        ],
    ),

    # Channel 5: Messy Real User (7 turns)
    ChannelSpec(
        name="Channel 5: Messy Real User",
        description="Vague, typos, topic switches, short acks",
        expected_message_count=14,
        turns=[
            TurnSpec(
                message="improve this",
                allow_no_tool=True,
                content_must_contain=["<<<CLARIFY>>>"],
            ),
            TurnSpec(
                message="Clarification: the abstract, make it more concise",
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
            TurnSpec(
                message="also fix grammar everwhere",
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
            TurnSpec(
                message="whats the best way to cite papers in this LaTeX format?",
                expected_tools=["answer_question"],
                content_should_contain=["cite", "bibliography"],
            ),
            TurnSpec(
                message="tell me about the attached references",
                expected_tools=["explain_references"],
                content_should_contain=["brown", "kaplan"],
            ),
            TurnSpec(
                message="thx",
                allow_no_tool=True,
                min_length=1,
                max_length=500,
            ),
            TurnSpec(
                message="wait one more thing, expand the results section with more detail about the 6.7B model experiments",
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
        ],
    ),

    # Channel 6: Collaboration Persistence (5 turns, alternating users)
    ChannelSpec(
        name="Channel 6: Collaboration Persistence",
        description="Alternating User A / User B on same paper",
        expected_message_count=10,
        check_tools_in_context=True,
        check_multi_user=True,
        turns=[
            TurnSpec(
                message="What is the main contribution of this paper?",
                expected_tools=["answer_question"],
                user_index=0,
            ),
            TurnSpec(
                message="Can you explain the AdaptGrad equation in simpler terms?",
                expected_tools=["answer_question"],
                user_index=1,
            ),
            TurnSpec(
                message="Fix the typo 'dynamicaly' in the abstract.",
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
                user_index=0,
            ),
            TurnSpec(
                message="Add a sentence to the related work section about LAMB optimizer.",
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
                user_index=1,
            ),
            TurnSpec(
                message="Who are the two authors listed in this paper?",
                expected_tools=["answer_question"],
                content_should_contain=["alice", "bob"],
                user_index=0,
            ),
        ],
    ),

    # Channel 7: Long Intensive Session (11 turns) — pushes past summary threshold
    ChannelSpec(
        name="Channel 7: Long Intensive Session",
        description="11 turns, triggers rolling summary after turn 8",
        expected_message_count=22,
        check_summary=True,
        turns=[
            TurnSpec(
                message="What is the paper about?",
                expected_tools=["answer_question"],
            ),
            TurnSpec(
                message="Review the abstract for clarity.",
                expected_tools=["review_document", "answer_question", "propose_edit"],
            ),
            TurnSpec(
                message='Fix "remain" to "remains" in the abstract.',
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
            TurnSpec(
                message='Fix the typo "dynamicaly" to "dynamically".',
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
            TurnSpec(
                message="Add a paragraph about computational efficiency to the Method section.",
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
            TurnSpec(
                message="What are the three model scales tested?",
                expected_tools=["answer_question"],
                content_should_contain=["125m", "1.3b", "6.7b"],
            ),
            TurnSpec(
                message="Shorten the Related Work section to 2 sentences.",
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
            TurnSpec(
                message="Expand the Conclusion with future work directions about multi-GPU training.",
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
            # Turns 9-11: past the 16-message summary threshold
            TurnSpec(
                message="What improvements does AdaptGrad offer over Adam?",
                expected_tools=["answer_question"],
            ),
            TurnSpec(
                message="Rewrite the first sentence of the introduction to be more concise and engaging.",
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
            TurnSpec(
                message="Add a limitations subsection at the end of the paper discussing potential drawbacks of the approach.",
                expected_tools=["propose_edit"],
                content_must_contain=["<<<EDIT>>>"],
            ),
        ],
    ),
]


# ── DB helper ─────────────────────────────────────────────────────────────

class EditorTestDB:
    """Manages a real PostgreSQL session and test fixtures."""

    def __init__(self):
        self.engine = create_engine(
            settings.DATABASE_URL,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5},
        )
        self._SessionFactory = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine,
        )
        self.session: Session = None  # type: ignore[assignment]

        # Track all created IDs for cleanup
        self._user_ids: List[Any] = []
        self._project_ids: List[Any] = []
        self._member_ids: List[Any] = []
        self._paper_ids: List[Any] = []
        self._reference_ids: List[Any] = []
        self._paper_ref_ids: List[Any] = []
        self._paper_member_ids: List[Any] = []

    def connect(self) -> Session:
        self.session = self._SessionFactory()
        return self.session

    def _db(self) -> Session:
        assert self.session is not None, "Call connect() first"
        return self.session

    def create_fixtures(self):
        """Create users, project, paper, references."""
        from app.models import User, Project, ProjectMember, ResearchPaper, Reference
        from app.models.paper_member import PaperMember, PaperRole
        from app.models.paper_reference import PaperReference

        db = self._db()

        # User A (primary)
        user_a = User(
            id=uuid.uuid4(),
            email=f"editor_e2e_a_{uuid.uuid4().hex[:8]}@test.scholarhub.space",
            password_hash="$2b$12$test_hash_not_real_password",
            first_name="E2E",
            last_name="Tester",
            is_active=True,
            is_verified=True,
        )
        db.add(user_a)
        db.flush()
        self._user_ids.append(user_a.id)

        # User B (collaborator)
        user_b = User(
            id=uuid.uuid4(),
            email=f"editor_e2e_b_{uuid.uuid4().hex[:8]}@test.scholarhub.space",
            password_hash="$2b$12$test_hash_not_real_password",
            first_name="Bob",
            last_name="Collab",
            is_active=True,
            is_verified=True,
        )
        db.add(user_b)
        db.flush()
        self._user_ids.append(user_b.id)

        # Project
        project = Project(
            id=uuid.uuid4(),
            title="Editor AI E2E Test Project",
            idea="Testing Editor AI E2E pipeline",
            keywords=["machine learning", "optimization", "testing"],
            scope="E2E test scope",
            status="active",
            created_by=user_a.id,
        )
        db.add(project)
        db.flush()
        self._project_ids.append(project.id)

        pm_a = ProjectMember(
            id=uuid.uuid4(),
            project_id=project.id,
            user_id=user_a.id,
            role="owner",
            status="accepted",
        )
        db.add(pm_a)
        db.flush()
        self._member_ids.append(pm_a.id)

        pm_b = ProjectMember(
            id=uuid.uuid4(),
            project_id=project.id,
            user_id=user_b.id,
            role="editor",
            status="accepted",
        )
        db.add(pm_b)
        db.flush()
        self._member_ids.append(pm_b.id)

        # Paper
        paper = ResearchPaper(
            id=uuid.uuid4(),
            title="Adaptive Gradient Methods for Efficient Training of LLMs",
            content=LATEX_DOCUMENT,
            format="latex",
            status="draft",
            project_id=project.id,
            owner_id=user_a.id,
            editor_ai_context={},
        )
        db.add(paper)
        db.flush()
        self._paper_ids.append(paper.id)

        # Paper members
        pam_a = PaperMember(
            id=uuid.uuid4(),
            paper_id=paper.id,
            user_id=user_a.id,
            role=PaperRole.OWNER,
            status="accepted",
        )
        db.add(pam_a)
        db.flush()
        self._paper_member_ids.append(pam_a.id)

        pam_b = PaperMember(
            id=uuid.uuid4(),
            paper_id=paper.id,
            user_id=user_b.id,
            role=PaperRole.EDITOR,
            status="accepted",
        )
        db.add(pam_b)
        db.flush()
        self._paper_member_ids.append(pam_b.id)

        # References
        for ref_data in TEST_REFERENCES:
            ref = Reference(
                id=uuid.uuid4(),
                owner_id=user_a.id,
                title=ref_data["title"],
                authors=ref_data["authors"],
                year=ref_data["year"],
                doi=ref_data["doi"],
                abstract=ref_data["abstract"],
                status="ingested",
            )
            db.add(ref)
            db.flush()
            self._reference_ids.append(ref.id)

            pref = PaperReference(
                id=uuid.uuid4(),
                paper_id=paper.id,
                reference_id=ref.id,
            )
            db.add(pref)
            db.flush()
            self._paper_ref_ids.append(pref.id)

        db.commit()
        return user_a, user_b, project, paper

    def reset_paper_state(self, paper_id):
        """Delete chat messages and reset editor_ai_context for a paper (between channels)."""
        db = self._db()
        from app.models.editor_chat_message import EditorChatMessage

        db.query(EditorChatMessage).filter(
            EditorChatMessage.paper_id == str(paper_id)
        ).delete(synchronize_session=False)

        db.execute(
            sa_text("""
                UPDATE research_papers
                SET editor_ai_context = '{}'::jsonb
                WHERE id = CAST(:pid AS uuid)
            """),
            {"pid": str(paper_id)},
        )
        db.commit()

    def get_message_count(self, paper_id) -> int:
        from app.models.editor_chat_message import EditorChatMessage
        return self._db().query(EditorChatMessage).filter(
            EditorChatMessage.paper_id == str(paper_id)
        ).count()

    def get_distinct_user_ids(self, paper_id) -> List[str]:
        from app.models.editor_chat_message import EditorChatMessage
        rows = (
            self._db()
            .query(EditorChatMessage.user_id)
            .filter(EditorChatMessage.paper_id == str(paper_id))
            .distinct()
            .all()
        )
        return [str(r[0]) for r in rows]

    def get_message_roles(self, paper_id) -> List[str]:
        from app.models.editor_chat_message import EditorChatMessage
        rows = (
            self._db()
            .query(EditorChatMessage.role)
            .filter(EditorChatMessage.paper_id == str(paper_id))
            .distinct()
            .all()
        )
        return [r[0] for r in rows]

    def get_editor_ai_context(self, paper_id) -> dict:
        from app.models.research_paper import ResearchPaper
        paper = self._db().query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
        if paper:
            return paper.editor_ai_context or {}
        return {}

    def get_author_names_for_messages(self, paper_id) -> List[str]:
        """Get distinct first_name values from users who sent messages on this paper."""
        from app.models.editor_chat_message import EditorChatMessage
        from app.models.user import User
        rows = (
            self._db()
            .query(User.first_name)
            .join(EditorChatMessage, EditorChatMessage.user_id == User.id)
            .filter(EditorChatMessage.paper_id == str(paper_id))
            .distinct()
            .all()
        )
        return [r[0] for r in rows if r[0]]

    def cleanup(self):
        """Delete all test-created rows in FK-safe order."""
        if self.session is None:
            return

        from app.models.editor_chat_message import EditorChatMessage
        from app.models.paper_reference import PaperReference
        from app.models.paper_member import PaperMember
        from app.models.reference import Reference
        from app.models.research_paper import ResearchPaper
        from app.models.project_member import ProjectMember
        from app.models.project import Project
        from app.models.user import User

        db = self.session
        try:
            # 1. Chat messages
            for pid in self._paper_ids:
                db.query(EditorChatMessage).filter(
                    EditorChatMessage.paper_id == str(pid)
                ).delete(synchronize_session=False)

            # 2. Paper references
            for prid in self._paper_ref_ids:
                db.query(PaperReference).filter(
                    PaperReference.id == prid
                ).delete(synchronize_session=False)

            # 3. References
            for rid in self._reference_ids:
                db.query(Reference).filter(
                    Reference.id == rid
                ).delete(synchronize_session=False)

            # 4. Paper members
            for pmid in self._paper_member_ids:
                db.query(PaperMember).filter(
                    PaperMember.id == pmid
                ).delete(synchronize_session=False)

            # 5. Papers
            for pid in self._paper_ids:
                db.query(ResearchPaper).filter(
                    ResearchPaper.id == pid
                ).delete(synchronize_session=False)

            # 6. Project members
            for mid in self._member_ids:
                db.query(ProjectMember).filter(
                    ProjectMember.id == mid
                ).delete(synchronize_session=False)

            # 7. Projects
            for pid in self._project_ids:
                db.query(Project).filter(
                    Project.id == pid
                ).delete(synchronize_session=False)

            # 8. Users
            for uid in self._user_ids:
                db.query(User).filter(
                    User.id == uid
                ).delete(synchronize_session=False)

            db.commit()
            logger.info("Cleanup complete — all test data removed")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            db.rollback()
        finally:
            db.close()


# ── Per-turn executor ─────────────────────────────────────────────────────

def run_turn(
    turn_spec: TurnSpec,
    turn_num: int,
    db: Session,
    user_id: str,
    user_name: str,
    paper_id: str,
    project_id: str,
    model: str,
    api_key: Optional[str],
) -> TurnResult:
    """Execute a single turn against SmartAgentServiceV2OR."""
    from app.services.smart_agent_service_v2_or import SmartAgentServiceV2OR

    errors: List[str] = []
    warnings: List[str] = []

    agent = SmartAgentServiceV2OR(model=model, user_api_key=api_key)

    t_start = time.monotonic()
    try:
        response = "".join(agent.stream_query(
            db=db,
            user_id=user_id,
            user_name=user_name,
            query=turn_spec.message,
            paper_id=paper_id,
            project_id=project_id,
            document_excerpt=LATEX_DOCUMENT,
        ))
    except Exception as e:
        response = ""
        errors.append(f"EXCEPTION: {e}")

    latency_ms = int((time.monotonic() - t_start) * 1000)
    tools_called = getattr(agent, "_last_tools_called", [])
    response_preview = response[:150].replace("\n", " ")

    # ── Hard assertions ──
    if not response.strip() and not turn_spec.allow_no_tool:
        errors.append("EMPTY_RESPONSE")

    # Tool check (OR logic)
    if turn_spec.expected_tools and not turn_spec.allow_no_tool:
        if not any(t in tools_called for t in turn_spec.expected_tools):
            errors.append(
                f"TOOL_MISMATCH: expected one of {turn_spec.expected_tools}, got {tools_called}"
            )

    # Forbidden tools
    for ft in turn_spec.forbidden_tools:
        if ft in tools_called:
            errors.append(f"FORBIDDEN_TOOL: {ft} was called")

    # content_must_contain (hard)
    for pattern in turn_spec.content_must_contain:
        if pattern not in response:
            errors.append(f"MUST_CONTAIN missing: '{pattern}'")

    # ── Soft assertions ──
    for keyword in turn_spec.content_should_contain:
        if keyword.lower() not in response.lower():
            warnings.append(f"SHOULD_CONTAIN missing: '{keyword}'")

    if len(response) < turn_spec.min_length and not turn_spec.allow_no_tool:
        warnings.append(f"SHORT_RESPONSE: {len(response)} chars (min {turn_spec.min_length})")

    if len(response) > turn_spec.max_length:
        warnings.append(f"LONG_RESPONSE: {len(response)} chars (max {turn_spec.max_length})")

    if latency_ms > 30000:
        warnings.append(f"SLOW: {latency_ms}ms > 30000ms")

    return TurnResult(
        turn_num=turn_num,
        message=turn_spec.message,
        tools_called=tools_called,
        response_preview=response_preview,
        latency_ms=latency_ms,
        passed=len(errors) == 0,
        warnings=warnings,
        errors=errors,
    )


# ── Per-channel runner ────────────────────────────────────────────────────

def run_channel(
    channel_spec: ChannelSpec,
    test_db: EditorTestDB,
    users: List,  # [user_a, user_b]
    paper,
    project,
    model: str,
    api_key: Optional[str],
    verbose: bool = True,
) -> ChannelResult:
    """Run all turns for one channel, then verify post-conditions."""

    # Reset state between channels
    test_db.reset_paper_state(paper.id)

    results: List[TurnResult] = []
    t_start = time.monotonic()

    for i, turn in enumerate(channel_spec.turns, 1):
        user = users[turn.user_index]
        user_name = user.first_name or "User"

        result = run_turn(
            turn_spec=turn,
            turn_num=i,
            db=test_db.session,
            user_id=str(user.id),
            user_name=user_name,
            paper_id=str(paper.id),
            project_id=str(project.id),
            model=model,
            api_key=api_key,
        )
        results.append(result)

        if verbose:
            status_color = C.GREEN if result.passed and not result.warnings else (C.YELLOW if result.passed else C.RED)
            status_text = "PASS" if result.passed else "FAIL"
            warn_str = f" {C.YELLOW}[{len(result.warnings)} warn]{C.RESET}" if result.warnings else ""
            tools_str = f" tools={result.tools_called}" if result.tools_called else ""
            print(
                f"  {status_color}{status_text}{C.RESET}{warn_str} "
                f"Turn {i:2d} {C.DIM}{result.latency_ms:5d}ms{C.RESET}{tools_str}"
            )
            print(f"       {C.DIM}msg: \"{turn.message[:80]}\"{C.RESET}")
            print(f"       {C.DIM}rsp: \"{result.response_preview[:100]}\"{C.RESET}")
            for err in result.errors:
                print(f"       {C.RED}ERROR: {err}{C.RESET}")
            for warn in result.warnings:
                print(f"       {C.YELLOW}WARN:  {warn}{C.RESET}")

    duration_s = time.monotonic() - t_start

    # ── Post-channel persistence checks ──
    post_errors: List[str] = []
    post_warnings: List[str] = []

    if channel_spec.check_persistence:
        # Message count
        actual_count = test_db.get_message_count(paper.id)
        if channel_spec.expected_message_count is not None:
            if actual_count != channel_spec.expected_message_count:
                post_warnings.append(
                    f"MESSAGE_COUNT: expected {channel_spec.expected_message_count}, got {actual_count}"
                )

        # Roles present
        roles = test_db.get_message_roles(paper.id)
        if "user" not in roles:
            post_errors.append("MISSING_ROLE: 'user' not in message roles")
        if "assistant" not in roles:
            post_errors.append("MISSING_ROLE: 'assistant' not in message roles")

    if channel_spec.check_tools_in_context:
        ctx = test_db.get_editor_ai_context(paper.id)
        if "_last_tools_called" not in ctx:
            post_errors.append("CONTEXT: _last_tools_called not in editor_ai_context")

    if channel_spec.check_multi_user:
        distinct_uids = test_db.get_distinct_user_ids(paper.id)
        if len(distinct_uids) < 2:
            post_errors.append(f"MULTI_USER: expected 2 distinct user_ids, got {len(distinct_uids)}")

        author_names = test_db.get_author_names_for_messages(paper.id)
        if "E2E" not in author_names:
            post_warnings.append(f"AUTHOR_NAME: 'E2E' not found in {author_names}")
        if "Bob" not in author_names:
            post_warnings.append(f"AUTHOR_NAME: 'Bob' not found in {author_names}")

    if channel_spec.check_summary:
        # Give background summary thread time to complete
        if verbose:
            print(f"  {C.DIM}Waiting 5s for background summary thread...{C.RESET}")
        time.sleep(5)
        # Refresh the session to see background thread's commit
        test_db.session.expire_all()
        ctx = test_db.get_editor_ai_context(paper.id)
        if "summary" not in ctx or not ctx.get("summary"):
            post_warnings.append("SUMMARY: rolling summary not found in editor_ai_context after 11 turns")
        else:
            if verbose:
                preview = ctx["summary"][:100].replace("\n", " ")
                print(f"  {C.GREEN}SUMMARY found:{C.RESET} {C.DIM}\"{preview}...\"{C.RESET}")

    if verbose and (post_errors or post_warnings):
        print(f"  {C.BOLD}Post-channel checks:{C.RESET}")
        for err in post_errors:
            print(f"    {C.RED}ERROR: {err}{C.RESET}")
        for warn in post_warnings:
            print(f"    {C.YELLOW}WARN:  {warn}{C.RESET}")

    passed_turns = sum(1 for r in results if r.passed and not r.warnings)
    warned_turns = sum(1 for r in results if r.passed and r.warnings)
    failed_turns = sum(1 for r in results if not r.passed)

    # Post-check errors count as failures at the channel level
    if post_errors:
        failed_turns += 1

    return ChannelResult(
        channel_name=channel_spec.name,
        turns=results,
        total_turns=len(results),
        passed_turns=passed_turns,
        warned_turns=warned_turns,
        failed_turns=failed_turns,
        duration_s=duration_s,
        post_check_errors=post_errors,
        post_check_warnings=post_warnings,
    )


# ── Summary ───────────────────────────────────────────────────────────────

def print_summary(channel_results: List[ChannelResult]) -> bool:
    print(f"\n{C.BOLD}{'=' * 70}{C.RESET}")
    print(f"{C.BOLD}EDITOR AI E2E TEST SUMMARY{C.RESET}")
    print(f"{'=' * 70}")

    total_turns = 0
    total_passed = 0
    total_warned = 0
    total_failed = 0
    total_duration = 0.0
    total_api_ms = 0

    for cr in channel_results:
        total_turns += cr.total_turns
        total_passed += cr.passed_turns
        total_warned += cr.warned_turns
        total_failed += cr.failed_turns
        total_duration += cr.duration_s
        channel_api_ms = sum(t.latency_ms for t in cr.turns)
        total_api_ms += channel_api_ms

        has_failure = cr.failed_turns > 0 or len(cr.post_check_errors) > 0
        status_color = C.RED if has_failure else (C.YELLOW if cr.warned_turns > 0 else C.GREEN)
        status = "FAIL" if has_failure else "PASS"

        tools_used = sorted({t for r in cr.turns for t in r.tools_called})
        print(
            f"  {status_color}{status}{C.RESET} {cr.channel_name}: "
            f"{cr.passed_turns}/{cr.total_turns} clean, "
            f"{cr.warned_turns} warned, {cr.failed_turns} failed "
            f"({cr.duration_s:.1f}s)"
        )
        if tools_used:
            print(f"       {C.DIM}tools: {', '.join(tools_used)}{C.RESET}")
        if cr.post_check_errors:
            print(f"       {C.RED}post-check errors: {len(cr.post_check_errors)}{C.RESET}")

    print(f"\n{C.BOLD}Total:{C.RESET} {total_turns} turns | "
          f"{C.GREEN}{total_passed} clean{C.RESET}, "
          f"{C.YELLOW}{total_warned} warned{C.RESET}, "
          f"{C.RED}{total_failed} failed{C.RESET}")
    print(f"Duration: {total_duration:.1f}s wall, {total_api_ms / 1000:.1f}s API")

    all_passed = total_failed == 0
    overall_color = C.GREEN if all_passed else C.RED
    print(f"\n{overall_color}{C.BOLD}Overall: {'PASS' if all_passed else 'FAIL'}{C.RESET}")
    return all_passed


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Live E2E test for Editor AI (SmartAgentServiceV2OR)")
    parser.add_argument(
        "--channel", type=int, default=None,
        help=f"Run only a specific channel (1-{len(CHANNELS)})",
    )
    parser.add_argument(
        "--model", type=str, default="openai/gpt-4o-mini",
        help="OpenRouter model ID (default: openai/gpt-4o-mini)",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Summary only (no per-turn output)",
    )
    args = parser.parse_args()

    verbose = not args.quiet

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="%(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore", "openai", "sqlalchemy"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Verify API key
    api_key = settings.OPENROUTER_API_KEY
    if not api_key:
        print(f"{C.RED}ERROR: OPENROUTER_API_KEY not set. Cannot run live tests.{C.RESET}")
        sys.exit(1)

    # Select channels
    if args.channel:
        if args.channel < 1 or args.channel > len(CHANNELS):
            print(f"Error: channel must be 1-{len(CHANNELS)}")
            sys.exit(1)
        channels = [CHANNELS[args.channel - 1]]
    else:
        channels = CHANNELS

    total_turns = sum(len(c.turns) for c in channels)
    print(f"{C.BOLD}Editor AI E2E Test: {len(channels)} channel(s), {total_turns} turns{C.RESET}")
    print(f"Model: {args.model}")
    print(f"Database: {settings.DATABASE_URL.split('@')[-1]}")
    print()

    # Setup
    test_db = EditorTestDB()
    test_db.connect()

    try:
        user_a, user_b, project, paper = test_db.create_fixtures()
        users = [user_a, user_b]
        print(
            f"Created fixtures: user_a={user_a.id}, user_b={user_b.id}, "
            f"paper={paper.id}, project={project.id}\n"
        )

        channel_results: List[ChannelResult] = []
        for channel_spec in channels:
            print(f"{C.CYAN}{'─' * 60}{C.RESET}")
            print(f"{C.CYAN}{C.BOLD}{channel_spec.name}{C.RESET}")
            print(f"  {C.DIM}{channel_spec.description}{C.RESET}")
            print(f"{C.CYAN}{'─' * 60}{C.RESET}")

            result = run_channel(
                channel_spec,
                test_db,
                users=users,
                paper=paper,
                project=project,
                model=args.model,
                api_key=api_key,
                verbose=verbose,
            )
            channel_results.append(result)

        all_passed = print_summary(channel_results)
        sys.exit(0 if all_passed else 1)

    finally:
        print(f"\n{C.DIM}Cleaning up test data...{C.RESET}")
        test_db.cleanup()


if __name__ == "__main__":
    main()
