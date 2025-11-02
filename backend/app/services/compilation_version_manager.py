from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import SessionLocal
from app.models import Branch, Commit, ResearchPaper


class CompilationVersionManager:
    def saveCompiledVersion(
        self,
        paper_id: UUID | str,
        author_id: UUID | str,
        content: str,
        pdf_url: str,
        logs: str,
        branch_name: str = 'main',
        db: Optional[Session] = None,
    ) -> Optional[Commit]:
        owns = False
        if db is None:
            db = SessionLocal()
            owns = True
        try:
            paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
            if not paper:
                return None
            # Find or create branch
            branch = (
                db.query(Branch)
                .filter(Branch.paper_id == paper_id, Branch.name == branch_name)
                .first()
            )
            if not branch:
                branch = Branch(name=branch_name, paper_id=paper_id, author_id=author_id, is_main=(branch_name.lower() == 'main'))
                db.add(branch)
                db.commit()
                db.refresh(branch)

            # Create commit with compilation metadata
            commit = Commit(
                branch_id=branch.id,
                message='Auto-save on successful compile',
                content=content or '',
                content_json={'authoring_mode': 'latex', 'latex_source': content or ''},
                author_id=author_id,
                changes=[],
                compilation_status='success',
                pdf_url=pdf_url,
                compile_logs=logs,
            )
            db.add(commit)
            branch.last_commit_message = commit.message
            db.commit()
            db.refresh(commit)
            return commit
        finally:
            if owns:
                db.close()

    def getLastSuccessfulVersion(self, paper_id: UUID | str, db: Optional[Session] = None) -> Optional[Commit]:
        owns = False
        if db is None:
            db = SessionLocal()
            owns = True
        try:
            q = (
                db.query(Commit)
                .join(Branch, Branch.id == Commit.branch_id)
                .filter(Branch.paper_id == paper_id, Commit.compilation_status == 'success')
                .order_by(desc(Commit.timestamp))
            )
            return q.first()
        finally:
            if owns:
                db.close()


compilation_version_manager = CompilationVersionManager()

