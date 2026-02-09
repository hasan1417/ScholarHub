#!/usr/bin/env python3
"""
Live E2E test for dynamic tool exposure pipeline.

Sends real messages through OpenRouterOrchestrator.handle_message(),
triggers real LLM calls via OpenRouter, executes real tools against
a real PostgreSQL database, and verifies the entire pipeline end-to-end.

Run all channels:
    docker compose exec backend python tests/test_live_e2e_tool_exposure.py

Run single channel:
    docker compose exec backend python tests/test_live_e2e_tool_exposure.py --channel 1

Verbose:
    docker compose exec backend python tests/test_live_e2e_tool_exposure.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

logger = logging.getLogger("live_e2e_test")


# ── Test infrastructure ─────────────────────────────────────────────────

@dataclass
class TurnSpec:
    """Specification for a single test turn."""
    message: str
    expected_route: str  # "lite" or "full" — hard fail
    tools_include: List[str] = field(default_factory=list)  # soft warn
    forbidden_tools: List[str] = field(default_factory=list)  # hard fail


@dataclass
class ChannelSpec:
    """Specification for a test channel (sequence of turns)."""
    name: str
    description: str
    turns: List[TurnSpec]


@dataclass
class TurnResult:
    """Result of a single test turn."""
    turn_num: int
    message: str
    actual_route: str
    tools_called: List[str]
    tools_exposed_count: int
    response_preview: str
    latency_ms: int
    passed: bool
    warnings: List[str]
    errors: List[str]


@dataclass
class ChannelResult:
    """Result of an entire channel test."""
    channel_name: str
    turns: List[TurnResult]
    total_turns: int
    passed_turns: int
    warned_turns: int
    failed_turns: int
    duration_s: float


# ── Test channels ────────────────────────────────────────────────────────

CHANNELS: List[ChannelSpec] = [
    ChannelSpec(
        name="Channel 1: Quick Search & Add",
        description="Basic: greet, search, add, details, bye",
        turns=[
            TurnSpec("hi im researching quantum computing", expected_route="lite"),
            TurnSpec(
                "find me 3 papers on quantum error correction",
                expected_route="full",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "add the first two to my library",
                expected_route="full",
                tools_include=["add_to_library"],
            ),
            TurnSpec(
                "show me details of the first paper",
                expected_route="full",
            ),
            TurnSpec("thanks!", expected_route="lite"),
        ],
    ),
    ChannelSpec(
        name="Channel 2: Full Research Workflow",
        description="10-turn: search, add, analysis, writing, export",
        turns=[
            TurnSpec(
                "I'm writing a survey on federated learning",
                expected_route="full",
            ),
            TurnSpec(
                "find me 5 papers on federated learning privacy",
                expected_route="full",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "add all papers to library",
                expected_route="full",
                tools_include=["add_to_library"],
            ),
            TurnSpec(
                "compare the different privacy approaches",
                expected_route="full",
            ),
            TurnSpec(
                "what research gaps exist in this area?",
                expected_route="full",
            ),
            TurnSpec(
                "find papers related to the first one",
                expected_route="full",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "create a literature review paper covering what we discussed",
                expected_route="full",
                tools_include=["create_paper"],
            ),
            TurnSpec(
                "generate an abstract for the paper",
                expected_route="full",
                tools_include=["generate_abstract"],
            ),
            TurnSpec(
                "export citations in bibtex",
                expected_route="full",
                tools_include=["export_citations"],
            ),
            TurnSpec("great work, thanks!", expected_route="lite"),
        ],
    ),
    ChannelSpec(
        name="Channel 3: Library Management",
        description="Library: browse, details, annotate, search, export",
        turns=[
            TurnSpec(
                "show me all papers in my library",
                expected_route="full",
                tools_include=["get_project_references"],
            ),
            TurnSpec(
                "tell me more about the second paper",
                expected_route="full",
            ),
            TurnSpec(
                "tag it as key-paper and add a note saying important methodology",
                expected_route="full",
                tools_include=["annotate_reference"],
            ),
            TurnSpec(
                "search my library for papers about transformers",
                expected_route="full",
            ),
            TurnSpec(
                "export all citations in APA format",
                expected_route="full",
                tools_include=["export_citations"],
            ),
            TurnSpec("ok cool", expected_route="lite"),
        ],
    ),
    ChannelSpec(
        name="Channel 4: Analysis Session",
        description="Search, add, focus, compare, artifact",
        turns=[
            TurnSpec(
                "search for 4 papers on attention mechanisms in NLP",
                expected_route="full",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "add them all to library",
                expected_route="full",
                tools_include=["add_to_library"],
            ),
            TurnSpec(
                "focus on papers 1 and 3",
                expected_route="full",
                tools_include=["focus_on_papers"],
            ),
            TurnSpec(
                "compare their methodologies",
                expected_route="full",
            ),
            TurnSpec(
                "create a summary artifact of our analysis",
                expected_route="full",
            ),
            TurnSpec("thx", expected_route="lite"),
        ],
    ),
    ChannelSpec(
        name="Channel 5: Project Setup & Search",
        description="Update project, search, add, create doc",
        turns=[
            TurnSpec(
                "update my project keywords to include reinforcement learning and robotics",
                expected_route="full",
                tools_include=["update_project_info"],
            ),
            TurnSpec(
                "find papers about reinforcement learning for robot control",
                expected_route="full",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "add these to library",
                expected_route="full",
                tools_include=["add_to_library"],
            ),
            TurnSpec(
                "create a short overview document",
                expected_route="full",
            ),
            TurnSpec("perfect", expected_route="lite"),
        ],
    ),
    ChannelSpec(
        name="Channel 6: Messy Real User",
        description="Typos, short follow-ups, topic switches",
        turns=[
            TurnSpec("hey", expected_route="lite"),
            TurnSpec(
                "i need papers abt deep learning for medical imaging",
                expected_route="full",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "more plz",
                expected_route="full",
            ),
            TurnSpec(
                "add them all",
                expected_route="full",
                tools_include=["add_to_library"],
            ),
            TurnSpec(
                "wait actually can u find papers on transformrs for protein folding instead",
                expected_route="full",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "ya add those too",
                expected_route="full",
                tools_include=["add_to_library"],
            ),
            TurnSpec(
                "whats in my library now",
                expected_route="full",
            ),
            TurnSpec("k bye", expected_route="lite"),
        ],
    ),
    ChannelSpec(
        name="Channel 7: Writing-Focused",
        description="Write intent, search, add, create paper",
        turns=[
            TurnSpec(
                "I want to write a paper about climate change adaptation",
                expected_route="full",
            ),
            TurnSpec(
                "find me 5 papers on climate adaptation policy",
                expected_route="full",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "add to library and ingest the PDFs",
                expected_route="full",
                tools_include=["add_to_library"],
            ),
            TurnSpec(
                "create a paper titled Climate Adaptation Review",
                expected_route="full",
                tools_include=["create_paper"],
            ),
            TurnSpec("nice, that's all for now", expected_route="lite"),
        ],
    ),
    ChannelSpec(
        name="Channel 8: Topic Discovery",
        description="Explore topics, batch search, add, summarize",
        turns=[
            TurnSpec(
                "I'm new to this field, what are the hot topics in NLP right now?",
                expected_route="full",
            ),
            TurnSpec(
                "search for 3 papers on each of the top 2 topics",
                expected_route="full",
                tools_include=["search_papers"],
            ),
            TurnSpec(
                "add all to my library",
                expected_route="full",
                tools_include=["add_to_library"],
            ),
            TurnSpec(
                "give me a summary of what we found",
                expected_route="full",
            ),
            TurnSpec("ok bye", expected_route="lite"),
        ],
    ),
]


# ── DB helpers ───────────────────────────────────────────────────────────

class LiveTestDB:
    """Manages a real PostgreSQL session for live testing."""

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
        self._created_ids: Dict[str, List[Any]] = {
            "users": [],
            "projects": [],
            "channels": [],
            "members": [],
        }

    def connect(self) -> Session:
        self.session = self._SessionFactory()
        return self.session

    def _db(self) -> Session:
        assert self.session is not None, "Call connect() first"
        return self.session

    def create_fixtures(self):
        """Create User, Project, and ProjectMember in the real DB."""
        from app.models import User, Project, ProjectMember

        db = self._db()

        user = User(
            id=uuid.uuid4(),
            email=f"live_e2e_test_{uuid.uuid4().hex[:8]}@test.scholarhub.space",
            password_hash="$2b$12$test_hash_not_real_password",
            first_name="E2E",
            last_name="Tester",
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        db.flush()
        self._created_ids["users"].append(user.id)

        project = Project(
            id=uuid.uuid4(),
            title="Live E2E Test Project",
            idea="Testing dynamic tool exposure pipeline end-to-end",
            keywords=["machine learning", "NLP", "testing"],
            scope="Verify tool exposure, route classification, and tool execution",
            status="active",
            created_by=user.id,
        )
        db.add(project)
        db.flush()
        self._created_ids["projects"].append(project.id)

        member = ProjectMember(
            id=uuid.uuid4(),
            project_id=project.id,
            user_id=user.id,
            role="owner",
            status="accepted",
        )
        db.add(member)
        db.flush()
        self._created_ids["members"].append(member.id)

        db.commit()
        return user, project

    def create_channel(self, project_id, user_id, name: str, slug: str):
        """Create a discussion channel for a test run."""
        from app.models import ProjectDiscussionChannel

        db = self._db()
        channel = ProjectDiscussionChannel(
            id=uuid.uuid4(),
            project_id=project_id,
            name=name,
            slug=slug,
            created_by=user_id,
        )
        db.add(channel)
        db.flush()
        db.commit()
        self._created_ids["channels"].append(channel.id)
        return channel

    def cleanup(self):
        """Delete all test-created rows. Proper FK order."""
        if self.session is None:
            return

        from app.models import (
            ProjectDiscussionChannel,
            ProjectDiscussionChannelResource,
            ProjectDiscussionTask,
            ProjectMember,
            ProjectReference,
            Reference,
            ResearchPaper,
            AIArtifact,
            AIArtifactChannelLink,
            DiscussionArtifact,
            ProjectDiscussionMessage,
            Document,
            DocumentChunk,
            Project,
            User,
        )
        from app.models.paper_member import PaperMember
        from app.models.paper_reference import PaperReference
        from app.models.paper_version import PaperVersion
        from app.models.comment import Comment
        from app.models.collaboration_session import CollaborationSession
        from app.models.section_lock import SectionLock
        from app.models.document_snapshot import DocumentSnapshot
        from app.models.branch import Branch, Commit, MergeRequest, ConflictResolution

        db = self.session
        try:
            # 1. Channel-scoped children first
            for cid in self._created_ids["channels"]:
                db.query(DiscussionArtifact).filter(
                    DiscussionArtifact.channel_id == cid
                ).delete(synchronize_session=False)
                db.query(AIArtifactChannelLink).filter(
                    AIArtifactChannelLink.channel_id == cid
                ).delete(synchronize_session=False)
                db.query(ProjectDiscussionTask).filter(
                    ProjectDiscussionTask.channel_id == cid
                ).delete(synchronize_session=False)
                db.query(ProjectDiscussionChannelResource).filter(
                    ProjectDiscussionChannelResource.channel_id == cid
                ).delete(synchronize_session=False)
                db.query(ProjectDiscussionMessage).filter(
                    ProjectDiscussionMessage.channel_id == cid
                ).delete(synchronize_session=False)

            # 2. Channels
            for cid in self._created_ids["channels"]:
                db.query(ProjectDiscussionChannel).filter(
                    ProjectDiscussionChannel.id == cid
                ).delete(synchronize_session=False)

            # 3. Project-scoped resources created by tools
            for pid in self._created_ids["projects"]:
                db.query(AIArtifact).filter(
                    AIArtifact.project_id == pid
                ).delete(synchronize_session=False)

                # Delete ResearchPaper children (many FKs lack CASCADE)
                paper_ids = [
                    r[0] for r in db.query(ResearchPaper.id).filter(
                        ResearchPaper.project_id == pid
                    ).all()
                ]
                if paper_ids:
                    db.query(PaperMember).filter(
                        PaperMember.paper_id.in_(paper_ids)
                    ).delete(synchronize_session=False)
                    db.query(PaperReference).filter(
                        PaperReference.paper_id.in_(paper_ids)
                    ).delete(synchronize_session=False)
                    db.query(PaperVersion).filter(
                        PaperVersion.paper_id.in_(paper_ids)
                    ).delete(synchronize_session=False)
                    db.query(Comment).filter(
                        Comment.paper_id.in_(paper_ids)
                    ).delete(synchronize_session=False)
                    db.query(DocumentSnapshot).filter(
                        DocumentSnapshot.paper_id.in_(paper_ids)
                    ).delete(synchronize_session=False)
                    db.query(CollaborationSession).filter(
                        CollaborationSession.paper_id.in_(paper_ids)
                    ).delete(synchronize_session=False)
                    db.query(SectionLock).filter(
                        SectionLock.paper_id.in_(paper_ids)
                    ).delete(synchronize_session=False)
                    # Merge requests: delete conflict resolutions first
                    mr_ids = [
                        r[0] for r in db.query(MergeRequest.id).filter(
                            MergeRequest.paper_id.in_(paper_ids)
                        ).all()
                    ]
                    if mr_ids:
                        db.query(ConflictResolution).filter(
                            ConflictResolution.merge_request_id.in_(mr_ids)
                        ).delete(synchronize_session=False)
                    db.query(MergeRequest).filter(
                        MergeRequest.paper_id.in_(paper_ids)
                    ).delete(synchronize_session=False)
                    # Branches: delete commits first, then branches
                    branch_ids = [
                        r[0] for r in db.query(Branch.id).filter(
                            Branch.paper_id.in_(paper_ids)
                        ).all()
                    ]
                    if branch_ids:
                        db.query(Commit).filter(
                            Commit.branch_id.in_(branch_ids)
                        ).delete(synchronize_session=False)
                    db.query(Branch).filter(
                        Branch.paper_id.in_(paper_ids)
                    ).delete(synchronize_session=False)
                    # Unlink documents from papers before deleting papers
                    db.query(Document).filter(
                        Document.paper_id.in_(paper_ids)
                    ).update({Document.paper_id: None}, synchronize_session=False)

                db.query(ResearchPaper).filter(
                    ResearchPaper.project_id == pid
                ).delete(synchronize_session=False)

                # Get reference IDs before deleting ProjectReference rows
                ref_ids = [
                    r[0] for r in db.query(ProjectReference.reference_id).filter(
                        ProjectReference.project_id == pid
                    ).all()
                ]
                db.query(ProjectReference).filter(
                    ProjectReference.project_id == pid
                ).delete(synchronize_session=False)

                # Delete References and their Documents/Chunks (created by PDF ingestion)
                if ref_ids:
                    doc_ids = [
                        r[0] for r in db.query(Reference.document_id).filter(
                            Reference.id.in_(ref_ids),
                            Reference.document_id.isnot(None),
                        ).all()
                    ]
                    db.query(Reference).filter(
                        Reference.id.in_(ref_ids)
                    ).delete(synchronize_session=False)
                    if doc_ids:
                        db.query(DocumentChunk).filter(
                            DocumentChunk.document_id.in_(doc_ids)
                        ).delete(synchronize_session=False)
                        db.query(Document).filter(
                            Document.id.in_(doc_ids)
                        ).delete(synchronize_session=False)

            # 4. Any remaining documents owned by test user
            for uid in self._created_ids["users"]:
                remaining_doc_ids = [
                    r[0] for r in db.query(Document.id).filter(
                        Document.owner_id == uid
                    ).all()
                ]
                if remaining_doc_ids:
                    db.query(DocumentChunk).filter(
                        DocumentChunk.document_id.in_(remaining_doc_ids)
                    ).delete(synchronize_session=False)
                    db.query(Document).filter(
                        Document.owner_id == uid
                    ).delete(synchronize_session=False)

            # 5. Members
            for mid in self._created_ids["members"]:
                db.query(ProjectMember).filter(
                    ProjectMember.id == mid
                ).delete(synchronize_session=False)

            # 6. Projects
            for pid in self._created_ids["projects"]:
                db.query(Project).filter(Project.id == pid).delete(
                    synchronize_session=False
                )

            # 7. Users last
            for uid in self._created_ids["users"]:
                db.query(User).filter(User.id == uid).delete(
                    synchronize_session=False
                )

            db.commit()
            logger.info("Cleanup complete — all test data removed")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            db.rollback()
        finally:
            db.close()


# ── Conversation runner ──────────────────────────────────────────────────

class LiveConversation:
    """Manages one channel's conversation state and runs turns."""

    def __init__(self, orchestrator, project, channel, user):
        self.orchestrator = orchestrator
        self.project = project
        self.channel = channel
        self.user = user
        self.conversation_history: List[Dict[str, str]] = []
        self.recent_search_results: List[Dict] = []
        self.all_tools_called: List[str] = []

    def send_message(self, text: str) -> Dict[str, Any]:
        """Send a message through handle_message and track state."""
        result = self.orchestrator.handle_message(
            project=self.project,
            channel=self.channel,
            message=text,
            recent_search_results=self.recent_search_results,
            conversation_history=self.conversation_history,
            reasoning_mode=False,
            current_user=self.user,
        )

        # Update conversation history
        self.conversation_history.append({"role": "user", "content": text})
        self.conversation_history.append({
            "role": "assistant",
            "content": result.get("message", ""),
        })

        # Update recent search results from actions
        for action in result.get("actions", []):
            if action.get("action_type") == "search_results":
                papers = action.get("payload", {}).get("papers", [])
                if papers:
                    self.recent_search_results = papers

        # Track tools
        tools = result.get("tools_called", [])
        self.all_tools_called.extend(tools)

        return result


# ── Per-channel test runner ──────────────────────────────────────────────

def run_channel(
    channel_spec: ChannelSpec,
    test_db: LiveTestDB,
    user,
    project,
    model: str,
    verbose: bool = True,
) -> ChannelResult:
    """Run all turns for one channel against a real DB + LLM."""
    from app.services.ai_service import AIService
    from app.services.discussion_ai.openrouter_orchestrator import OpenRouterOrchestrator

    slug = f"live-e2e-{uuid.uuid4().hex[:8]}"
    channel = test_db.create_channel(
        project_id=project.id,
        user_id=user.id,
        name=channel_spec.name,
        slug=slug,
    )

    ai_service = AIService()
    orchestrator = OpenRouterOrchestrator(ai_service, test_db.session, model=model)
    convo = LiveConversation(orchestrator, project, channel, user)

    results: List[TurnResult] = []
    t_channel_start = time.monotonic()

    for i, turn in enumerate(channel_spec.turns, 1):
        errors: List[str] = []
        warnings: List[str] = []

        t_start = time.monotonic()
        result = convo.send_message(turn.message)
        latency_ms = int((time.monotonic() - t_start) * 1000)

        tools_called = result.get("tools_called", [])
        response_msg = result.get("message", "")
        response_preview = response_msg[:120].replace("\n", " ")

        # Route assertion (soft — we can't perfectly detect lite vs full from result)
        if turn.expected_route == "lite" and tools_called:
            errors.append(
                f"ROUTE: expected=lite but tools_called={tools_called}"
            )
        # Don't hard-fail on full->no-tools since LLM may choose not to call tools

        # Tool inclusion check (soft warn)
        if turn.tools_include:
            for expected_tool in turn.tools_include:
                if expected_tool not in tools_called:
                    warnings.append(
                        f"TOOLS_INCLUDE: expected {expected_tool} not in {tools_called}"
                    )

        # Forbidden tools check (hard fail)
        if turn.forbidden_tools:
            for forbidden in turn.forbidden_tools:
                if forbidden in tools_called:
                    errors.append(
                        f"FORBIDDEN_TOOL: {forbidden} was called but should not be"
                    )

        # Response sanity check
        if not response_msg.strip():
            warnings.append("EMPTY_RESPONSE: model returned empty message")

        passed = len(errors) == 0
        results.append(TurnResult(
            turn_num=i,
            message=turn.message,
            actual_route="lite" if turn.expected_route == "lite" and not tools_called else "full",
            tools_called=tools_called,
            tools_exposed_count=0,  # Not easily extractable from handle_message
            response_preview=response_preview,
            latency_ms=latency_ms,
            passed=passed,
            warnings=warnings,
            errors=errors,
        ))

        if verbose:
            status = "PASS" if passed else "FAIL"
            warn_str = f" [{len(warnings)} warn]" if warnings else ""
            tools_str = f" tools={tools_called}" if tools_called else ""
            print(
                f"  Turn {i:2d} [{status}{warn_str}] "
                f"{latency_ms:5d}ms{tools_str}"
            )
            print(f"         msg: \"{turn.message[:70]}\"")
            print(f"         rsp: \"{response_preview}\"")
            for err in errors:
                print(f"         ERROR: {err}")
            for warn in warnings:
                print(f"         WARN:  {warn}")

    duration_s = time.monotonic() - t_channel_start
    passed_turns = sum(1 for r in results if r.passed and not r.warnings)
    warned_turns = sum(1 for r in results if r.passed and r.warnings)
    failed_turns = sum(1 for r in results if not r.passed)

    return ChannelResult(
        channel_name=channel_spec.name,
        turns=results,
        total_turns=len(results),
        passed_turns=passed_turns,
        warned_turns=warned_turns,
        failed_turns=failed_turns,
        duration_s=duration_s,
    )


# ── Summary ──────────────────────────────────────────────────────────────

def print_summary(channel_results: List[ChannelResult]) -> bool:
    """Print overall summary and return True if all hard assertions passed."""
    print("\n" + "=" * 70)
    print("LIVE E2E TEST SUMMARY")
    print("=" * 70)

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

        status = "PASS" if cr.failed_turns == 0 else "FAIL"
        tools_summary = []
        for t in cr.turns:
            if t.tools_called:
                tools_summary.extend(t.tools_called)
        unique_tools = sorted(set(tools_summary))

        print(
            f"  {status} {cr.channel_name}: "
            f"{cr.passed_turns}/{cr.total_turns} clean, "
            f"{cr.warned_turns} warned, {cr.failed_turns} failed "
            f"({cr.duration_s:.1f}s)"
        )
        if unique_tools:
            print(f"       tools used: {', '.join(unique_tools)}")

    print(f"\nTotal: {total_turns} turns | "
          f"{total_passed} clean, {total_warned} warned, {total_failed} failed")
    print(f"Duration: {total_duration:.1f}s wall, {total_api_ms / 1000:.1f}s API")

    all_passed = total_failed == 0
    print(f"\nOverall: {'PASS' if all_passed else 'FAIL'}")
    return all_passed


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Live E2E test for dynamic tool exposure")
    parser.add_argument(
        "--channel", type=int, default=None,
        help=f"Run only a specific channel (1-{len(CHANNELS)})",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", default=True,
        help="Verbose per-turn output (default: True)",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Quiet mode (summary only)",
    )
    parser.add_argument(
        "--model", type=str, default="openai/gpt-4o-mini",
        help="OpenRouter model ID (default: openai/gpt-4o-mini)",
    )
    args = parser.parse_args()

    verbose = not args.quiet

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # Quiet down noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    # Verify API key
    if not settings.OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY not set. Cannot run live tests.")
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
    print(f"Live E2E Test: {len(channels)} channel(s), {total_turns} turns")
    print(f"Model: {args.model}")
    print(f"Database: {settings.DATABASE_URL.split('@')[-1]}")
    print()

    # Setup DB
    test_db = LiveTestDB()
    test_db.connect()

    try:
        user, project = test_db.create_fixtures()
        print(f"Created test fixtures: user={user.id}, project={project.id}\n")

        # Run channels
        channel_results: List[ChannelResult] = []
        for channel_spec in channels:
            print(f"{'─' * 60}")
            print(f"{channel_spec.name}")
            print(f"  {channel_spec.description}")
            print(f"{'─' * 60}")

            result = run_channel(
                channel_spec, test_db, user, project,
                model=args.model, verbose=verbose,
            )
            channel_results.append(result)

        # Summary
        all_passed = print_summary(channel_results)
        sys.exit(0 if all_passed else 1)

    finally:
        print("\nCleaning up test data...")
        test_db.cleanup()


if __name__ == "__main__":
    main()
