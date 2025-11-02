"""Utility script to migrate existing papers into a single dummy project.

Usage examples:

    python -m app.scripts.migrate_to_projects --dry-run
    python -m app.scripts.migrate_to_projects --execute --owner-email admin@example.com

The script creates (or reuses) a project named "Legacy Migration" and links every
existing research paper to it. Paper owners and collaborators are added to the
project membership roster, and references tied directly to papers are backfilled
into the new linking tables with `approved` status.
"""

from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Project,
    ProjectMember,
    ProjectReference,
    ProjectReferenceStatus,
    ProjectRole,
    ResearchPaper,
    PaperMember,
    PaperReference,
    Reference,
    User,
)


logger = logging.getLogger(__name__)


DEFAULT_PROJECT_NAME = "Legacy Migration"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill papers into a dummy project")
    parser.add_argument("--execute", action="store_true", help="Persist changes (otherwise dry run)")
    parser.add_argument("--dry-run", action="store_true", help="Alias for leaving execute=false")
    parser.add_argument("--owner-email", help="Email of the user that should own the dummy project")
    parser.add_argument("--dummy-project-name", default=DEFAULT_PROJECT_NAME, help="Name for the dummy project")
    return parser.parse_args()


def resolve_owner(session: Session, owner_email: Optional[str]) -> User:
    if owner_email:
        owner = session.execute(select(User).where(User.email == owner_email)).scalar_one_or_none()
        if not owner:
            raise ValueError(f"No user found with email {owner_email}")
        return owner

    owner = (
        session.execute(select(User).order_by(User.created_at.asc())).scalars().first()
        or session.execute(select(User).order_by(User.email.asc())).scalars().first()
    )
    if not owner:
        raise ValueError("No users found in the database to own the dummy project")
    return owner


def ensure_dummy_project(session: Session, name: str, owner: User) -> Project:
    project = session.execute(select(Project).where(Project.title == name)).scalar_one_or_none()
    if project:
        return project

    project = Project(
        title=name,
        idea="Legacy project holding existing papers",
        scope="migration",
        created_by=owner.id,
    )
    session.add(project)
    session.flush()

    membership = ProjectMember(
        project_id=project.id,
        user_id=owner.id,
        role=ProjectRole.ADMIN,
        status="accepted",
    )
    session.add(membership)
    session.flush()
    return project


def ensure_membership(session: Session, project_id, user_id, role=ProjectRole.EDITOR) -> None:
    existing = session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    ).scalar_one_or_none()
    if existing:
        return

    membership = ProjectMember(
        project_id=project_id,
        user_id=user_id,
        role=role,
        status="accepted",
    )
    session.add(membership)
    session.flush()


def backfill_references(session: Session, project_id, paper_id) -> int:
    refs = session.execute(
        select(Reference).where(Reference.paper_id == paper_id)
    ).scalars().all()

    inserted = 0
    for ref in refs:
        # Create project-level link
        existing_project = session.execute(
            select(ProjectReference).where(
                ProjectReference.project_id == project_id,
                ProjectReference.reference_id == ref.id,
            )
        ).scalar_one_or_none()
        if not existing_project:
            session.add(
                ProjectReference(
                    project_id=project_id,
                    reference_id=ref.id,
                    status=ProjectReferenceStatus.APPROVED,
                    decided_at=datetime.utcnow(),
                )
            )
            inserted += 1

        # Create paper-level link
        existing_paper = session.execute(
            select(PaperReference).where(
                PaperReference.paper_id == paper_id,
                PaperReference.reference_id == ref.id,
            )
        ).scalar_one_or_none()
        if not existing_paper:
            session.add(
                PaperReference(
                    paper_id=paper_id,
                    reference_id=ref.id,
                )
            )
    return inserted


def migrate(session: Session, project: Project, execute: bool) -> None:
    papers = session.execute(select(ResearchPaper)).scalars().all()
    if not papers:
        logger.info("No research papers found; nothing to migrate")
        return

    stats = defaultdict(int)
    member_cache: Set[tuple] = set()

    for paper in papers:
        if paper.project_id == project.id:
            continue

        stats['papers_seen'] += 1
        original_project = paper.project_id
        paper.project_id = project.id

        # Ensure owner membership
    ensure_membership(session, project.id, paper.owner_id, role=ProjectRole.EDITOR)
        member_cache.add((project.id, paper.owner_id))

        # Ensure collaborator memberships
        members = session.execute(
            select(PaperMember).where(PaperMember.paper_id == paper.id)
        ).scalars().all()
        for member in members:
            ensure_membership(session, project.id, member.user_id, role=ProjectRole.EDITOR)
            member_cache.add((project.id, member.user_id))

        inserted_refs = backfill_references(session, project.id, paper.id)
        stats['references_linked'] += inserted_refs

        if original_project and original_project != project.id:
            stats['reassigned'] += 1
        else:
            stats['assigned'] += 1

    stats['members_added'] = len(member_cache)

    if execute:
        session.commit()
        logger.info("Migration committed: %s", dict(stats))
    else:
        session.rollback()
        logger.info("Dry run complete (no changes committed): %s", dict(stats))


def main() -> None:
    args = parse_args()
    execute = bool(args.execute and not args.dry_run)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    session = SessionLocal()
    try:
        owner = resolve_owner(session, args.owner_email)
        project = ensure_dummy_project(session, args.dummy_project_name, owner)
        session.flush()

        if not execute:
            logger.info("Running in dry-run mode. Use --execute to persist changes.")

        migrate(session, project, execute)
    finally:
        session.close()


if __name__ == "__main__":
    main()
