"""The reference list endpoints serve exactly the key the citation filter accepts."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.api.v1 import project_references as project_refs_api
from app.api.v1.research_papers import list_references as list_paper_references
from app.models import PaperReference, ProjectReference, Reference, ResearchPaper
from app.models.project_reference import ProjectReferenceStatus
from app.services.citation_filter import build_allowed_citation_keys


@pytest.fixture
def colliding_paper(db: Session, test_user, test_project):
    """A project paper citing two references by the same first author and year."""
    paper = ResearchPaper(id=uuid.uuid4(), title="Key test paper", owner_id=test_user.id, project_id=test_project.id, format="latex")
    db.add(paper)
    db.flush()
    refs = []
    base_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    for offset, title in enumerate(("Deep learning for X", "Deep learning for Y")):
        entered = base_time + timedelta(minutes=offset)  # explicit: rows flushed together share now()
        ref = Reference(
            id=uuid.uuid4(), owner_id=test_user.id, paper_id=paper.id,
            title=title, authors=["Jane Smith"], year=2020, created_at=entered,
        )
        db.add(ref)
        db.flush()
        db.add(ProjectReference(
            project_id=test_project.id, reference_id=ref.id,
            status=ProjectReferenceStatus.APPROVED, created_at=entered,
        ))
        db.add(PaperReference(paper_id=paper.id, reference_id=ref.id))
        refs.append(ref)
    db.flush()
    try:
        yield paper, refs
    finally:
        # One endpoint commits while syncing legacy links, so remove the rows explicitly.
        db.rollback()
        ref_ids = [ref.id for ref in refs]
        try:
            db.query(PaperReference).filter(PaperReference.reference_id.in_(ref_ids)).delete(synchronize_session=False)
            db.query(ProjectReference).filter(ProjectReference.reference_id.in_(ref_ids)).delete(synchronize_session=False)
            db.query(Reference).filter(Reference.id.in_(ref_ids)).delete(synchronize_session=False)
            db.query(ResearchPaper).filter(ResearchPaper.id == paper.id).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()


@pytest.mark.asyncio
async def test_all_list_endpoints_serve_the_filters_collision_aware_keys(db: Session, test_user, test_project, colliding_paper) -> None:
    paper, (first, second) = colliding_paper

    with patch.object(project_refs_api.settings, "PROJECT_REFERENCE_SUGGESTIONS_ENABLED", True):
        project_list = project_refs_api.list_project_references(
            project_id=str(test_project.id), status_filter=None, db=db, current_user=test_user,
        )
        paper_list = project_refs_api.list_references_for_paper(
            project_id=str(test_project.id), paper_id=str(paper.id), db=db, current_user=test_user,
        )
    legacy_list = await list_paper_references(paper_id=str(paper.id), current_user=test_user, db=db)

    from_project = {r["reference"]["id"]: r["reference"]["citation_key"] for r in project_list["references"]}
    from_paper = {r["reference_id"]: r["citation_key"] for r in paper_list["references"]}
    from_legacy = {str(r.id): r.citation_key for r in legacy_list.references}

    ids = {str(first.id), str(second.id)}
    assert set(from_project) >= ids and set(from_paper) >= ids and set(from_legacy) == ids
    assert {k: from_project[k] for k in ids} == from_legacy == {k: from_paper[k] for k in ids}

    # The earlier-added reference keeps the base key; the collision gets the "a" suffix.
    assert from_legacy[str(second.id)] == from_legacy[str(first.id)] + "a"
    assert from_legacy[str(first.id)].startswith("smith2020")

    allowed = build_allowed_citation_keys(db, project_id=test_project.id, paper_id=paper.id, owner_id=test_user.id)
    assert set(from_legacy.values()) <= allowed


@pytest.mark.asyncio
async def test_paper_only_reference_never_takes_a_library_key(db: Session, test_user, test_project, colliding_paper) -> None:
    """An older reference that belongs only to the paper allocates after the library."""
    paper, (first, second) = colliding_paper
    older = datetime.now(timezone.utc) - timedelta(days=30)
    paper_only = Reference(
        id=uuid.uuid4(), owner_id=test_user.id, paper_id=paper.id,
        title="Deep learning for Z", authors=["Jane Smith"], year=2020, created_at=older,
    )
    db.add(paper_only)
    db.flush()
    db.add(PaperReference(paper_id=paper.id, reference_id=paper_only.id))
    db.flush()
    try:
        with patch.object(project_refs_api.settings, "PROJECT_REFERENCE_SUGGESTIONS_ENABLED", True):
            project_list = project_refs_api.list_project_references(
                project_id=str(test_project.id), status_filter=None, db=db, current_user=test_user,
            )
            paper_list = project_refs_api.list_references_for_paper(
                project_id=str(test_project.id), paper_id=str(paper.id), db=db, current_user=test_user,
            )
        legacy_list = await list_paper_references(paper_id=str(paper.id), current_user=test_user, db=db)

        from_project = {r["reference"]["id"]: r["reference"]["citation_key"] for r in project_list["references"]}
        from_paper = {r["reference_id"]: r["citation_key"] for r in paper_list["references"]}
        from_legacy = {str(r.id): r.citation_key for r in legacy_list.references}

        # Library keys are identical on the project page and inside the paper.
        for ref in (first, second):
            assert from_project[str(ref.id)] == from_paper[str(ref.id)] == from_legacy[str(ref.id)]
        base = from_project[str(first.id)]
        assert from_project[str(second.id)] == base + "a"
        assert str(paper_only.id) not in from_project
        assert from_paper[str(paper_only.id)] == from_legacy[str(paper_only.id)] == base + "b"
        allowed = build_allowed_citation_keys(db, project_id=test_project.id, paper_id=paper.id, owner_id=test_user.id)
        assert {base, base + "a", base + "b"} <= allowed
    finally:
        db.rollback()
        try:
            db.query(PaperReference).filter(PaperReference.reference_id == paper_only.id).delete(synchronize_session=False)
            db.query(Reference).filter(Reference.id == paper_only.id).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
