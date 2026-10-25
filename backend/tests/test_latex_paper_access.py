"""LaTeX routes verify access to request.paper_id, and the .bib matches the editor's keys."""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.v1 import latex as latex_api
from app.models import PaperReference, ProjectReference, Reference, ResearchPaper
from app.models.paper_member import PaperMember, PaperRole
from app.models.project_member import ProjectMember
from app.models.project_reference import ProjectReferenceStatus
from app.models.user import User
from app.services.citation_filter import scope_citation_keys
from app.services.submission_builder import _generate_bibtex


@pytest.fixture
def other_users_paper(db: Session):
    """A paper owned by a user who shares nothing with the test user."""
    other = User(
        id=uuid.uuid4(), email=f"latex_access_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", first_name="Other", last_name="Owner", is_active=True, is_verified=True,
    )
    db.add(other)
    db.flush()
    paper = ResearchPaper(
        id=uuid.uuid4(), title="Private paper", owner_id=other.id, project_id=None, format="latex",
        content_json={"latex_source": "\\documentclass{article}\\begin{document}secret\\end{document}"},
    )
    db.add(paper)
    db.flush()
    try:
        yield paper
    finally:
        db.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["compile_latex", "compile_latex_stream", "export_docx", "export_source_zip"])
async def test_paper_id_of_another_users_paper_is_denied_before_any_fallback(db, test_user, other_users_paper, route) -> None:
    handler = getattr(latex_api, route)
    request_model = latex_api.CompileRequest if route.startswith("compile") else (
        latex_api.ExportDocxRequest if route == "export_docx" else latex_api.ExportSourceZipRequest
    )
    request = request_model(latex_source="", paper_id=str(other_users_paper.id))
    kwargs = {"request": request, "current_user": test_user, "db": db}
    if route.startswith("compile"):
        kwargs["save_version"] = False
    with pytest.raises(HTTPException) as excinfo:
        await handler(**kwargs)
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_fix_errors_and_build_submission_are_guarded_too(db, test_user, other_users_paper) -> None:
    paper_id = str(other_users_paper.id)
    with pytest.raises(HTTPException) as fix:
        await latex_api.fix_latex_errors(
            request=latex_api.FixErrorsRequest(latex_source="x", error_log="e", paper_id=paper_id),
            model="openai/gpt-5.4-mini", current_user=test_user, db=db,
        )
    with pytest.raises(HTTPException) as build:
        await latex_api.build_submission(
            request=latex_api.SubmissionBuildRequest(latex_source="\\documentclass{article} body", venue="ieee", paper_id=paper_id),
            current_user=test_user, db=db,
        )
    assert fix.value.status_code == 403 and build.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["compile_latex", "compile_latex_stream"])
async def test_viewer_may_compile_but_not_save_a_version(db, test_user, route) -> None:
    """A viewer passes the read guard (then fails on the empty source) and is refused as an editor."""
    other = User(
        id=uuid.uuid4(), email=f"latex_viewer_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", first_name="Paper", last_name="Owner", is_active=True, is_verified=True,
    )
    db.add(other)
    db.flush()
    paper = ResearchPaper(id=uuid.uuid4(), title="Empty paper", owner_id=other.id, project_id=None, format="latex")
    db.add(paper)
    db.flush()
    db.add(PaperMember(paper_id=paper.id, user_id=test_user.id, role=PaperRole.VIEWER, status="accepted"))
    db.flush()
    handler = getattr(latex_api, route)
    request = latex_api.CompileRequest(latex_source="", paper_id=str(paper.id))
    try:
        with pytest.raises(HTTPException) as read:
            await handler(request=request, current_user=test_user, save_version=False, db=db)
        assert read.value.status_code == 400  # guard passed; the paper has no source to fall back to
        with pytest.raises(HTTPException) as write:
            await handler(request=request, current_user=test_user, save_version=True, db=db)
        assert write.value.status_code == 403 and write.value.detail == "Edit access denied"
    finally:
        db.rollback()


@pytest.mark.asyncio
async def test_project_member_who_is_not_a_paper_member_can_compile(db, test_user, test_project) -> None:
    member = User(
        id=uuid.uuid4(), email=f"latex_member_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", first_name="Project", last_name="Member", is_active=True, is_verified=True,
    )
    db.add(member)
    db.flush()
    db.add(ProjectMember(id=uuid.uuid4(), project_id=test_project.id, user_id=member.id, role="editor"))
    paper = ResearchPaper(id=uuid.uuid4(), title="Shared paper", owner_id=test_user.id, project_id=test_project.id, format="latex")
    db.add(paper)
    db.flush()
    try:
        with pytest.raises(HTTPException) as excinfo:
            await latex_api.compile_latex(
                request=latex_api.CompileRequest(latex_source="", paper_id=str(paper.id)),
                current_user=member, save_version=False, db=db,
            )
        assert excinfo.value.status_code == 400  # auto-joined through the project, then no source
    finally:
        # The auto-join commits its membership row, so remove everything explicitly.
        db.rollback()
        try:
            db.query(PaperMember).filter(PaperMember.paper_id == paper.id).delete(synchronize_session=False)
            db.query(ResearchPaper).filter(ResearchPaper.id == paper.id).delete(synchronize_session=False)
            db.query(ProjectMember).filter(ProjectMember.user_id == member.id).delete(synchronize_session=False)
            db.query(User).filter(User.id == member.id).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()


@pytest.mark.asyncio
async def test_unknown_paper_id_is_404_not_a_silent_compile(db, test_user) -> None:
    request = latex_api.ExportDocxRequest(latex_source="\\documentclass{article}", paper_id=str(uuid.uuid4()))
    with pytest.raises(HTTPException) as excinfo:
        await latex_api.export_docx(request=request, current_user=test_user, db=db)
    assert excinfo.value.status_code == 404


def test_bibtex_covers_linked_references_and_uses_the_editors_keys(db: Session, test_user, test_project) -> None:
    other = User(
        id=uuid.uuid4(), email=f"latex_bib_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", first_name="Co", last_name="Author", is_active=True, is_verified=True,
    )
    db.add(other)
    db.flush()
    paper = ResearchPaper(id=uuid.uuid4(), title="Bib test", owner_id=test_user.id, project_id=test_project.id, format="latex")
    db.add(paper)
    db.flush()
    # A library reference owned by the co-author, attached to the paper only through PaperReference.
    linked = Reference(id=uuid.uuid4(), owner_id=other.id, title="Deep learning for X", authors=["Jane Smith"], year=2020)
    # A direct reference owned by the compiling user, colliding on author and year.
    direct = Reference(id=uuid.uuid4(), owner_id=test_user.id, paper_id=paper.id, title="Deep learning for Y", authors=["Jane Smith"], year=2020)
    db.add_all([linked, direct])
    db.flush()
    db.add(ProjectReference(project_id=test_project.id, reference_id=linked.id, status=ProjectReferenceStatus.APPROVED))
    db.add(PaperReference(paper_id=paper.id, reference_id=linked.id))
    db.flush()
    try:
        bib = _generate_bibtex(db, test_user.id, str(paper.id))
        keys = scope_citation_keys(db, project_id=test_project.id, paper_id=paper.id, owner_id=test_user.id)
        assert f"{{{keys[linked.id]}," in bib and f"{{{keys[direct.id]}," in bib
        assert keys[linked.id] != keys[direct.id]
        assert "Deep learning for X" in bib and "Deep learning for Y" in bib
        assert _generate_bibtex(db, test_user.id, str(uuid.uuid4())) == "% No references found."
    finally:
        db.rollback()
