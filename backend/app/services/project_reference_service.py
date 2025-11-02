from __future__ import annotations

import logging
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models import (
    PaperReference,
    Project,
    ProjectReference,
    ProjectReferenceStatus,
    Reference,
    User,
)
from app.services.activity_feed import record_project_activity, preview_text

logger = logging.getLogger(__name__)


class ProjectReferenceSuggestionService:
    """Populate project-level reference suggestions based on attached paper references."""

    def __init__(self, db: Session):
        self.db = db

    def generate_suggestions(self, project: Project, actor: Optional[User] = None) -> Tuple[int, int]:
        """Return counts of (created, skipped) suggestions for the project."""
        existing_links = {
            (str(link.reference_id))
            for link in self.db.query(ProjectReference)
            .filter(ProjectReference.project_id == project.id)
            .all()
        }

        created = 0
        skipped = 0

        paper_refs = (
            self.db.query(PaperReference)
            .join(Reference, Reference.id == PaperReference.reference_id)
            .filter(PaperReference.paper.has(project_id=project.id))
            .all()
        )

        for link in paper_refs:
            ref_id = str(link.reference_id)
            if ref_id in existing_links:
                skipped += 1
                continue

            project_ref = ProjectReference(
                project_id=project.id,
                reference_id=link.reference_id,
                status=ProjectReferenceStatus.PENDING,
                confidence=link.reference.relevance_score,
            )
            self.db.add(project_ref)
            self.db.flush()

            record_project_activity(
                db=self.db,
                project=project,
                actor=actor,
                event_type="project-reference.suggested",
                payload={
                    "category": "project-reference",
                    "action": "suggested",
                    "project_reference_id": str(project_ref.id),
                    "reference_id": str(link.reference_id),
                    "reference_title": preview_text(link.reference.title if link.reference else None, 160),
                    "confidence": link.reference.relevance_score,
                    "source": "discovery",
                },
            )

            existing_links.add(ref_id)
            created += 1

        if created:
            self.db.commit()

        return created, skipped
