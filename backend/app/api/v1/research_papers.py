from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import List, Optional, Any
from uuid import UUID
from pathlib import Path
import shutil
import logging
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.research_paper import ResearchPaper
from app.models.paper_version import PaperVersion
from app.models.paper_member import PaperMember, PaperRole
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.schemas.research_paper import ResearchPaperCreate, ResearchPaperUpdate, ResearchPaperResponse, ResearchPaperList
from app.core.config import settings
from app.schemas.paper_member import PaperMemberCreate, PaperMemberResponse
from app.schemas.paper_version import PaperVersionCreate, PaperVersionResponse, PaperVersionList, ContentUpdateRequest
from app.schemas.reference import ReferenceCreate, ReferenceResponse, ReferenceList
from sqlalchemy import func
import re
from app.models.reference import Reference
from app.models.document_snapshot import DocumentSnapshot
from fastapi import BackgroundTasks
from app.database import SessionLocal
from app.services.reference_ingestion_service import ingest_reference_pdf
from app.services.paper_membership_service import ensure_paper_membership_for_project_member
import traceback
from app.services.activity_feed import record_project_activity, preview_text

# Security logging
logger = logging.getLogger(__name__)

router = APIRouter()


def _normalize_title(value: str) -> str:
    trimmed = value.strip()
    normalized_internal = " ".join(trimmed.split())
    return normalized_internal


def _normalize_objective_list(value: Optional[Any]) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        trimmed = value.strip()
        return [trimmed] if trimmed else []
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned
    return []


def _paper_title_exists(
    db: Session,
    *,
    normalized_title: str,
    project_id: Optional[UUID],
    owner_id: UUID,
    exclude_paper_id: Optional[UUID] = None,
) -> bool:
    """Return True when another paper already uses the given title in the scoped collection."""
    normalized_lookup = normalized_title.lower()
    normalized_db_title = func.lower(
        func.regexp_replace(func.trim(ResearchPaper.title), r'\s+', ' ', 'g'),
    )
    query = db.query(ResearchPaper).filter(normalized_db_title == normalized_lookup)
    if exclude_paper_id:
        query = query.filter(ResearchPaper.id != exclude_paper_id)
    if project_id:
        query = query.filter(ResearchPaper.project_id == project_id)
    else:
        query = query.filter(
            ResearchPaper.project_id.is_(None),
            ResearchPaper.owner_id == owner_id,
        )
    return query.first() is not None


def _duplicate_title_error(project_id: Optional[UUID]) -> HTTPException:
    scope = "this project" if project_id else "your workspace"
    return HTTPException(status_code=409, detail=f"A paper with this title already exists in {scope}.")

@router.post("/", response_model=ResearchPaperResponse, status_code=status.HTTP_201_CREATED)
async def create_research_paper(
    paper_data: ResearchPaperCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new research paper."""
    project: Optional[Project] = None
    normalized_title = _normalize_title(paper_data.title)
    paper_data.title = normalized_title
    objectives = _normalize_objective_list(paper_data.objectives)

    if paper_data.project_id:
        if not settings.PROJECTS_API_ENABLED:
            raise HTTPException(status_code=400, detail="Project support is disabled")
        project = db.query(Project).filter(Project.id == paper_data.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Parent project not found")
        if project.created_by != current_user.id:
            project_member = db.query(ProjectMember).filter(
                ProjectMember.project_id == paper_data.project_id,
                ProjectMember.user_id == current_user.id,
                ProjectMember.status == "accepted",
            ).first()
            if not project_member:
                raise HTTPException(status_code=403, detail="Project access denied")
        if not objectives:
            raise HTTPException(status_code=400, detail="Please select or create at least one project objective for this paper.")

    paper_data.objectives = objectives or None

    if _paper_title_exists(
        db,
        normalized_title=normalized_title,
        project_id=paper_data.project_id,
        owner_id=current_user.id,
    ):
        raise _duplicate_title_error(paper_data.project_id)

    paper = ResearchPaper(
        **paper_data.dict(),
        owner_id=current_user.id
    )
    
    db.add(paper)
    db.commit()
    db.refresh(paper)

    # Add owner as member with owner role and accepted status
    owner_member = PaperMember(
        paper_id=paper.id,
        user_id=current_user.id,
        role=PaperRole.OWNER,
        status="accepted"  # Owners should automatically be accepted
    )
    db.add(owner_member)

    if project:
        record_project_activity(
            db=db,
            project=project,
            actor=current_user,
            event_type="paper.created",
            payload={
                "category": "paper",
                "action": "created",
                "paper_id": str(paper.id),
                "paper_title": preview_text(paper.title, 160) if getattr(paper, "title", None) else None,
            },
        )

    db.commit()

    return paper

@router.get("/", response_model=ResearchPaperList)
async def get_research_papers(
    skip: int = 0,
    limit: int = 100,
    project_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get research papers available to the current user."""

    try:
        if project_id:
            if not settings.PROJECTS_API_ENABLED:
                raise HTTPException(status_code=400, detail="Project support is disabled")
            try:
                project_uuid = UUID(project_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid project id")

            project = db.query(Project).filter(Project.id == project_uuid).first()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            if project.created_by != current_user.id:
                project_member = db.query(ProjectMember).filter(
                    ProjectMember.project_id == project_uuid,
                    ProjectMember.user_id == current_user.id,
                    ProjectMember.status == "accepted",
                ).first()
                if not project_member:
                    raise HTTPException(status_code=403, detail="Project access denied")

            query = db.query(ResearchPaper).filter(ResearchPaper.project_id == project_uuid)
            total = query.count()
            papers = query.offset(skip).limit(limit).all()

            logger.info(
                "User %s (ID: %s) accessed %s project papers (project: %s)",
                current_user.email,
                current_user.id,
                total,
                project_uuid,
            )

            return ResearchPaperList(papers=papers, total=total, skip=skip, limit=limit)

        # No project specified: return owned + shared papers
        owned_query = db.query(ResearchPaper).filter(ResearchPaper.owner_id == current_user.id)
        shared_query = (
            db.query(ResearchPaper)
            .join(PaperMember)
            .filter(
                PaperMember.user_id == current_user.id,
                PaperMember.status == "accepted",
                ResearchPaper.owner_id != current_user.id,
            )
        )

        papers_map = {}
        for paper in owned_query.all():
            papers_map[paper.id] = paper
        for paper in shared_query.all():
            papers_map[paper.id] = paper

        all_papers = list(papers_map.values())
        total = len(all_papers)
        papers = all_papers[skip:skip + limit]

        logger.info(
            "User %s (ID: %s) accessed %s personal/shared papers",
            current_user.email,
            current_user.id,
            total,
        )

        return ResearchPaperList(papers=papers, total=total, skip=skip, limit=limit)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting papers for user {current_user.email}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{paper_id}", response_model=ResearchPaperResponse)
async def get_research_paper(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific research paper."""
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    
    # Check if user has access
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id,
            PaperMember.status == "accepted",
        ).first()

        if not member:
            member = ensure_paper_membership_for_project_member(db, paper, current_user)

        if not member:
            logger.warning(
                "User %s (ID: %s) attempted unauthorized access to paper %s",
                current_user.email,
                current_user.id,
                paper_id,
            )
            raise HTTPException(status_code=403, detail="Access denied")
        elif member.status != "accepted":
            logger.warning(
                "User %s (ID: %s) attempted access to paper %s with status: %s",
                current_user.email,
                current_user.id,
                paper_id,
                member.status,
            )
            raise HTTPException(status_code=403, detail="Access denied - invitation not accepted")
    
    # Security logging for successful access
    logger.info(f"User {current_user.email} (ID: {current_user.id}) accessed paper {paper_id} (title: {paper.title})")
    
    return paper

@router.put("/{paper_id}", response_model=ResearchPaperResponse)
async def update_research_paper(
    paper_id: str,
    paper_update: ResearchPaperUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a research paper."""
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    
    # Check if user is owner or has edit permissions
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id
        ).first()
        if not member:
            member = ensure_paper_membership_for_project_member(db, paper, current_user)
        if not member or member.role not in [PaperRole.OWNER, PaperRole.ADMIN, PaperRole.EDITOR]:
            raise HTTPException(status_code=403, detail="Edit access denied")
    
    update_data = paper_update.dict(exclude_unset=True)
    normalized_new_title: Optional[str] = None
    if "title" in update_data and update_data["title"] is not None:
        normalized_new_title = _normalize_title(update_data["title"])
        if not normalized_new_title:
            raise HTTPException(status_code=400, detail="Title cannot be empty.")
        update_data["title"] = normalized_new_title

    if "objectives" in update_data:
        normalized_objectives = _normalize_objective_list(update_data["objectives"])
        update_data["objectives"] = normalized_objectives or None

    target_project_id = update_data.get("project_id", paper.project_id)
    title_to_check = normalized_new_title or _normalize_title(paper.title or "")

    requires_duplicate_check = False
    if normalized_new_title is not None:
        if normalized_new_title.lower() != (paper.title or "").strip().lower():
            requires_duplicate_check = True
    if "project_id" in update_data and target_project_id != paper.project_id:
        requires_duplicate_check = True

    if requires_duplicate_check and _paper_title_exists(
        db,
        normalized_title=title_to_check,
        project_id=target_project_id,
        owner_id=paper.owner_id,
        exclude_paper_id=paper.id,
    ):
        raise _duplicate_title_error(target_project_id)

    if target_project_id and not (update_data.get("objectives") or paper.objectives):
        raise HTTPException(status_code=400, detail="Project papers must reference at least one objective.")
    for field, value in update_data.items():
        setattr(paper, field, value)

    project: Optional[Project] = None
    if paper.project_id:
        project = db.query(Project).filter(Project.id == paper.project_id).first()
        if project:
            record_project_activity(
                db=db,
                project=project,
                actor=current_user,
                event_type="paper.updated",
                payload={
                    "category": "paper",
                    "action": "updated",
                    "paper_id": str(paper.id),
                    "paper_title": preview_text(paper.title, 160) if getattr(paper, "title", None) else None,
                    "updated_fields": sorted(update_data.keys()),
                },
            )

    db.commit()
    db.refresh(paper)
    return paper

@router.delete("/{paper_id}")
async def delete_research_paper(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a research paper."""
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    
    # Only owner can delete
    if paper.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can delete this paper")
    
    db.delete(paper)
    db.commit()
    
    return {"message": "Research paper deleted successfully"}

@router.put("/{paper_id}/content")
async def update_paper_content(
    paper_id: str,
    content_update: ContentUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update content of a research paper with optional versioning."""
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    
    # Check if user is owner or has edit permissions
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id
        ).first()
        if not member:
            member = ensure_paper_membership_for_project_member(db, paper, current_user)
        if not member or member.role not in [PaperRole.OWNER, PaperRole.ADMIN, PaperRole.EDITOR]:
            raise HTTPException(status_code=403, detail="Edit access denied")
    
    # If saving as a version, create a new version first
    if content_update.save_as_version:
        # Get the next version number
        latest_version = db.query(PaperVersion).filter(
            PaperVersion.paper_id == paper_id
        ).order_by(PaperVersion.created_at.desc()).first()
        
        if latest_version:
            # Simple increment logic for versions (1.0 -> 1.1 -> 1.2 etc)
            try:
                major, minor = map(int, latest_version.version_number.split('.'))
                new_version = f"{major}.{minor + 1}"
            except ValueError:
                new_version = "1.1"
        else:
            new_version = "1.1"  # First version after initial
        
        # Create version
        version = PaperVersion(
            paper_id=paper.id,
            version_number=new_version,
            title=paper.title,
            content=content_update.content or paper.content,
            content_json=content_update.content_json or paper.content_json,
            abstract=paper.abstract,
            keywords=paper.keywords,
            references=paper.references,
            change_summary=content_update.version_summary or "Content updated",
            created_by=current_user.id
        )
        db.add(version)
        
        # Update paper's current version
        paper.current_version = new_version
    
    # Update paper content
    prev_html = paper.content or ''
    prev_len = len(prev_html)
    try:
        import hashlib as _hashlib
        prev_hash = _hashlib.sha256(prev_html.encode('utf-8', errors='ignore')).hexdigest()[:12]
    except Exception:
        prev_hash = 'n/a'
    if content_update.content is not None:
        paper.content = content_update.content
    if content_update.content_json is not None:
        # Preserve authoring_mode if caller omitted it (prevents LaTeX→rich flips)
        try:
            incoming = content_update.content_json
            existing = paper.content_json
            try:
                incoming_latex = ''
                if isinstance(incoming, dict):
                    candidate = incoming.get('latex_source')
                    incoming_latex = candidate if isinstance(candidate, str) else ''
                logger.warning(
                    "PUT paper content: paper=%s latex_len=%s head=%s",
                    paper_id,
                    len(incoming_latex),
                    (incoming_latex[:40] if incoming_latex else ''),
                )
            except Exception:
                logger.exception("Failed to log incoming latex payload for paper %s", paper_id)
            # Optionally prevent authoring_mode changes after creation (Phase 0 flag; default off)
            try:
                if settings.COLLAB_LOCK_AUTHORING_MODE:
                    if isinstance(existing, dict) and isinstance(incoming, dict):
                        old_mode = existing.get('authoring_mode')
                        new_mode = incoming.get('authoring_mode')
                        if old_mode and new_mode and str(old_mode) != str(new_mode):
                            raise HTTPException(status_code=400, detail="authoring_mode cannot be changed once set")
            except Exception:
                # Best-effort guard; do not block if settings or compare fails
                pass
            if isinstance(existing, dict) and isinstance(incoming, dict):
                if 'authoring_mode' in existing and 'authoring_mode' not in incoming:
                    incoming['authoring_mode'] = existing['authoring_mode']
            # If LaTeX mode, ensure latex_source remains a string (avoid accidental object overwrite)
            if isinstance(incoming, dict) and incoming.get('authoring_mode') == 'latex':
                ls = incoming.get('latex_source')
                if ls is None:
                    # Keep previous latex_source if missing in payload
                    if isinstance(existing, dict) and isinstance(existing.get('latex_source'), str):
                        incoming['latex_source'] = existing['latex_source']
                elif not isinstance(ls, str):
                    try:
                        incoming['latex_source'] = str(ls)
                    except Exception:
                        incoming['latex_source'] = ''
        except Exception:
            pass
        paper.content_json = content_update.content_json
    new_html = paper.content or ''
    new_len = len(new_html)
    try:
        import hashlib as _hashlib
        new_hash = _hashlib.sha256(new_html.encode('utf-8', errors='ignore')).hexdigest()[:12]
    except Exception:
        new_hash = 'n/a'
    
    paper.updated_at = func.now()
    
    # Log save summary to help diagnose overwrites
    try:
        logger.info(
            "Content update: paper=%s user=%s prev_len=%s prev_hash=%s new_len=%s new_hash=%s",
            paper_id, getattr(current_user, 'email', '?'), prev_len, prev_hash, new_len, new_hash
        )
        try:
            import hashlib as _hash
            cj = paper.content_json if isinstance(paper.content_json, dict) else {}
            mode = cj.get('authoring_mode')
            ls_len = len(cj.get('latex_source', '') or '') if isinstance(cj.get('latex_source', ''), str) else 0
            logger.info(
                "Content JSON: mode=%s latex_len=%s keys=%s",
                mode, ls_len, sorted(list(cj.keys())) if isinstance(cj, dict) else 'n/a'
            )
        except Exception:
            pass
    except Exception:
        pass

    db.commit()
    db.refresh(paper)

    # Create a snapshot on save (with deduplication to prevent spam)
    try:
        from datetime import datetime, timedelta

        # Get the latex source for materialized text
        materialized_text = ""
        if isinstance(paper.content_json, dict):
            materialized_text = paper.content_json.get("latex_source", "") or ""
        if not materialized_text and paper.content:
            materialized_text = paper.content

        # Only create snapshot if there's actual content
        if materialized_text and len(materialized_text.strip()) > 0:
            current_length = len(materialized_text)

            # Check the last snapshot for deduplication
            last_snapshot = db.query(DocumentSnapshot).filter(
                DocumentSnapshot.paper_id == paper.id
            ).order_by(DocumentSnapshot.sequence_number.desc()).first()

            should_create_snapshot = True
            skip_reason = None

            # Manual saves always create a snapshot (user clicked save button)
            is_manual_save = getattr(content_update, 'manual_save', False)

            if last_snapshot and not is_manual_save:
                time_since_last = datetime.utcnow() - last_snapshot.created_at
                length_diff = abs(current_length - (last_snapshot.text_length or 0))

                # Skip if less than 30 seconds AND less than 50 character change (only for auto-saves)
                if time_since_last < timedelta(seconds=30) and length_diff < 50:
                    should_create_snapshot = False
                    skip_reason = f"Too soon ({time_since_last.seconds}s) and small change ({length_diff} chars)"

            if should_create_snapshot:
                # Get next sequence number
                max_seq = db.query(func.max(DocumentSnapshot.sequence_number)).filter(
                    DocumentSnapshot.paper_id == paper.id
                ).scalar()
                next_seq = (max_seq or 0) + 1

                # Create snapshot
                snapshot = DocumentSnapshot(
                    paper_id=paper.id,
                    yjs_state=b"",  # No Yjs state when saving from API
                    materialized_text=materialized_text,
                    snapshot_type="save",
                    label=None,
                    created_by=current_user.id,
                    sequence_number=next_seq,
                    text_length=current_length,
                )
                db.add(snapshot)
                db.commit()
                logger.info("Created save snapshot for paper %s, seq=%s, len=%s", paper_id, next_seq, current_length)
            else:
                logger.debug("Skipped duplicate snapshot for paper %s: %s", paper_id, skip_reason)
        else:
            logger.debug("Skipped empty snapshot for paper %s", paper_id)
    except Exception as e:
        logger.warning("Failed to create save snapshot for paper %s: %s", paper_id, str(e))
        # Don't fail the save operation if snapshot creation fails

    return {
        "message": "Content updated successfully",
        "content": paper.content,
        "content_json": paper.content_json,
        "current_version": paper.current_version,
        "version_created": content_update.save_as_version
    }

# References endpoints
@router.post("/{paper_id}/references", response_model=ReferenceResponse, status_code=status.HTTP_201_CREATED)
async def add_reference(
    paper_id: str,
    ref: ReferenceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    # Access check: owner or accepted member
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id,
            PaperMember.status == "accepted"
        ).first()
        if not member:
            raise HTTPException(status_code=403, detail="Access denied")
    # Prevent duplicates: check DOI first, then normalized title+year within this paper
    def _normalize_title(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip()).lower()

    try:
        dup = None
        norm_in = _normalize_title(ref.title)
        existing = db.query(Reference).filter(
            Reference.owner_id == current_user.id,
            Reference.paper_id == paper.id
        ).all()
        for er in existing:
            # DOI exact (case-insensitive)
            if ref.doi and er.doi and er.doi.strip().lower() == ref.doi.strip().lower():
                dup = er
                break
            # Title normalized (and optionally same year if provided)
            if _normalize_title(er.title) == norm_in and (not ref.year or not er.year or er.year == ref.year):
                dup = er
                break
        if dup:
            # Soft-update any missing metadata on the existing reference
            updated = False
            if not dup.journal and ref.journal:
                dup.journal = ref.journal; updated = True
            if (not dup.year) and ref.year:
                dup.year = ref.year; updated = True
            if (not dup.authors) and (ref.authors or []):
                dup.authors = ref.authors; updated = True
            if (not dup.abstract) and ref.abstract:
                dup.abstract = ref.abstract; updated = True
            if (not dup.doi) and ref.doi:
                dup.doi = ref.doi; updated = True
            if (not dup.pdf_url) and ref.pdf_url:
                dup.pdf_url = ref.pdf_url; updated = True
            if updated:
                db.commit()
                db.refresh(dup)
            return dup
    except Exception:
        # Best-effort duplicate prevention; continue to create if check fails
        pass

    reference = Reference(
        paper_id=paper.id,
        owner_id=current_user.id,
        title=ref.title,
        authors=ref.authors or [],
        year=ref.year,
        doi=ref.doi,
        url=ref.url,
        source=ref.source,
        journal=ref.journal,
        abstract=ref.abstract,
        is_open_access=bool(ref.is_open_access),
        pdf_url=ref.pdf_url,
        status="pending"
    )
    db.add(reference)
    db.commit()
    db.refresh(reference)
    # Kick off background analysis
    try:
        if background_tasks is not None:
            from app.api.v1.research_papers import analyze_reference_task
            background_tasks.add_task(analyze_reference_task, str(reference.id))
    except Exception as e:
        logger.error(f"Failed to enqueue analysis task for reference {reference.id}: {e}")
    return reference

@router.get("/{paper_id}/references", response_model=ReferenceList)
async def list_references(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id,
            PaperMember.status == "accepted"
        ).first()
        if not member:
            raise HTTPException(status_code=403, detail="Access denied")
    refs = db.query(Reference).filter(Reference.paper_id == paper_id).order_by(Reference.created_at.desc()).all()
    return ReferenceList(references=refs, total=len(refs))

@router.delete("/{paper_id}/references/{reference_id}")
async def delete_reference(
    paper_id: str,
    reference_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ref = db.query(Reference).filter(Reference.id == reference_id, Reference.paper_id == paper_id).first()
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id,
            PaperMember.status == "accepted"
        ).first()
        if not member:
            raise HTTPException(status_code=403, detail="Access denied")
    db.delete(ref)
    db.commit()
    return {"message": "Reference deleted"}


def analyze_reference_task(reference_id: str):
    """Background analysis: ingest OA PDF if available; generate a simple profile."""
    db = SessionLocal()
    try:
        ref = db.query(Reference).filter(Reference.id == reference_id).first()
        if not ref:
            return
        # Fetch parent paper to assign ownership for ingested documents
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == ref.paper_id).first()
        # Step 1: Ingest OA PDF if pdf_url present and not yet ingested
        if ref.pdf_url and not ref.document_id:
            owner_override = str(paper.owner_id) if paper and paper.owner_id else None
            try:
                if not ingest_reference_pdf(db, ref, owner_id=owner_override):
                    logger.info("Reference %s PDF ingestion skipped or unavailable", ref.id)
            except Exception as exc:  # pragma: no cover - ingestion best effort
                logger.warning("Reference %s PDF ingestion failed: %s", ref.id, exc)
        # Step 2: Build profile text
        profile_text = ''
        if ref.abstract:
            profile_text = ref.abstract
        if not profile_text and ref.document_id:
            # get some chunks
            from app.models.document_chunk import DocumentChunk
            chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == ref.document_id).order_by(DocumentChunk.chunk_index).limit(5).all()
            if chunks:
                profile_text = '\n'.join([c.chunk_text for c in chunks if c.chunk_text])
        if not profile_text and ref.url:
            profile_text = f"{ref.title or ''}"
        # Step 3: Simple analysis (heuristic) — optional: use OpenAI if available
        try:
            import os
            from openai import OpenAI
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key and profile_text:
                client = OpenAI(api_key=api_key)
                prompt = f"""Title: {ref.title or ''}\n\nText:\n{profile_text[:3000]}\n\nGenerate:\n- 3-5 key findings\n- 1-2 sentence methodology\n- 2-3 limitations\nProvide as JSON with keys: summary, key_findings, methodology, limitations."""
                resp = client.responses.create(
                    model="gpt-3.5-turbo",
                    input=[{"role": "user", "content": prompt}],
                    max_output_tokens=300,
                    temperature=0.3
                )
                content = resp.output_text or ''
                # naive JSON parse fallback
                import json as _json
                try:
                    data = _json.loads(content)
                    ref.summary = data.get('summary')
                    ref.key_findings = data.get('key_findings')
                    ref.methodology = data.get('methodology')
                    ref.limitations = data.get('limitations')
                except Exception:
                    # fallback: set summary only
                    ref.summary = content[:800]
            else:
                if profile_text:
                    # heuristic summary: first 2-3 sentences
                    import re as _re
                    sentences = _re.split(r'(?<=[.!?])\s+', profile_text)
                    ref.summary = ' '.join(sentences[:3])[:800]
        except Exception:
            logger.error(f"Analysis failed for reference {reference_id}: {traceback.format_exc()}")
        # Step 4: finalize
        ref.status = 'analyzed'
        db.commit()
    except Exception:
        logger.error(f"analyze_reference_task error: {traceback.format_exc()}")
    finally:
        db.close()

@router.post("/{paper_id}/members", response_model=PaperMemberResponse)
async def add_paper_member(
    paper_id: str,
    member_data: PaperMemberCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a member to a research paper."""
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    
    # Only owner can add members
    if paper.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can add members")
    
    # Check if member already exists
    existing_member = db.query(PaperMember).filter(
        PaperMember.paper_id == paper_id,
        PaperMember.user_id == member_data.user_id
    ).first()
    
    if existing_member:
        raise HTTPException(status_code=400, detail="User is already a member of this paper")
    
    member = PaperMember(**member_data.dict())
    db.add(member)
    db.commit()
    db.refresh(member)
    
    return member

@router.post("/{paper_id}/members/{member_id}/accept")
async def accept_paper_invitation(
    paper_id: str,
    member_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Accept an invitation to join a research paper."""
    # Check if the current user is the invited member
    if current_user.id != member_id:
        raise HTTPException(status_code=403, detail="You can only accept your own invitations")
    
    member = db.query(PaperMember).filter(
        PaperMember.paper_id == paper_id,
        PaperMember.user_id == member_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Invitation not found")
    
    if member.status != "invited":
        raise HTTPException(status_code=400, detail="Invitation has already been processed")
    
    member.status = "accepted"
    member.joined_at = func.now()
    db.commit()
    db.refresh(member)
    
    return {"message": "Invitation accepted successfully"}

@router.post("/{paper_id}/members/{member_id}/decline")
async def decline_paper_invitation(
    paper_id: str,
    member_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Decline an invitation to join a research paper."""
    # Check if the current user is the invited member
    if current_user.id != member_id:
        raise HTTPException(status_code=403, detail="You can only decline your own invitations")
    
    member = db.query(PaperMember).filter(
        PaperMember.paper_id == paper_id,
        PaperMember.user_id == member_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Invitation not found")
    
    if member.status != "invited":
        raise HTTPException(status_code=400, detail="Invitation has already been processed")
    
    member.status = "declined"
    db.commit()
    
    return {"message": "Invitation declined successfully"}

@router.delete("/{paper_id}/members/{member_id}")
async def remove_paper_member(
    paper_id: str,
    member_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a member from a research paper."""
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    
    # Only owner can remove members
    if paper.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can remove members")
    
    # Cannot remove yourself as owner
    if member_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself as owner")
    
    member = db.query(PaperMember).filter(
        PaperMember.paper_id == paper_id,
        PaperMember.user_id == member_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    db.delete(member)
    db.commit()
    
    return {"message": "Member removed successfully"}

@router.get("/invitations/pending")
async def get_pending_invitations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get pending invitations for the current user."""
    pending_invitations = db.query(PaperMember).filter(
        PaperMember.user_id == current_user.id,
        PaperMember.status == "invited"
    ).all()
    
    return {
        "pending_invitations": [
            {
                "id": str(inv.id),
                "paper_id": str(inv.paper_id),
                "role": inv.role,
                "invited_at": inv.invited_at,
                "paper_title": db.query(ResearchPaper.title).filter(
                    ResearchPaper.id == inv.paper_id
                ).scalar()
            }
            for inv in pending_invitations
        ]
    }


# Versioning endpoints
@router.get("/{paper_id}/versions", response_model=PaperVersionList)
async def get_paper_versions(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all versions of a research paper."""
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    
    # Check if user has access
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id,
            PaperMember.status == "accepted"
        ).first()
        if not member:
            member = ensure_paper_membership_for_project_member(db, paper, current_user)
        if not member:
            raise HTTPException(status_code=403, detail="Access denied")
    
    versions = db.query(PaperVersion).filter(
        PaperVersion.paper_id == paper_id
    ).order_by(PaperVersion.created_at.desc()).all()
    
    return PaperVersionList(
        versions=versions,
        total=len(versions),
        current_version=paper.current_version or "1.0"
    )


@router.get("/{paper_id}/versions/{version_number}", response_model=PaperVersionResponse)
async def get_paper_version(
    paper_id: str,
    version_number: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific version of a research paper."""
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    
    # Check if user has access
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id,
            PaperMember.status == "accepted"
        ).first()
        if not member:
            member = ensure_paper_membership_for_project_member(db, paper, current_user)
        if not member:
            raise HTTPException(status_code=403, detail="Access denied")
    
    version = db.query(PaperVersion).filter(
        PaperVersion.paper_id == paper_id,
        PaperVersion.version_number == version_number
    ).first()
    
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    return version


@router.post("/{paper_id}/versions", response_model=PaperVersionResponse)
async def create_paper_version(
    paper_id: str,
    version_data: PaperVersionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new version of a research paper."""
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    
    # Check if user has edit access
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id,
            PaperMember.status == "accepted"
        ).first()
        if not member:
            member = ensure_paper_membership_for_project_member(db, paper, current_user)
        if not member or member.role not in [PaperRole.OWNER, PaperRole.ADMIN, PaperRole.EDITOR]:
            raise HTTPException(status_code=403, detail="Edit access denied")
    
    # Check if version number already exists
    existing_version = db.query(PaperVersion).filter(
        PaperVersion.paper_id == paper_id,
        PaperVersion.version_number == version_data.version_number
    ).first()
    
    if existing_version:
        raise HTTPException(status_code=400, detail="Version number already exists")
    
    # Create version with current paper content as fallback
    version = PaperVersion(
        paper_id=paper.id,
        version_number=version_data.version_number,
        title=version_data.title,
        content=version_data.content or paper.content,
        content_json=version_data.content_json or paper.content_json,
        abstract=version_data.abstract or paper.abstract,
        keywords=version_data.keywords or paper.keywords,
        references=version_data.references or paper.references,
        change_summary=version_data.change_summary,
        created_by=current_user.id
    )
    
    db.add(version)
    db.commit()
    db.refresh(version)

    if not paper.current_version:
        paper.current_version = version_data.version_number
        db.commit()
    
    return version


@router.put("/{paper_id}/versions/{version_number}/restore")
async def restore_paper_version(
    paper_id: str,
    version_number: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Restore a paper to a specific version."""
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    
    # Check if user has edit access
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id,
            PaperMember.status == "accepted"
        ).first()
        if not member:
            member = ensure_paper_membership_for_project_member(db, paper, current_user)
        if not member or member.role not in [PaperRole.OWNER, PaperRole.ADMIN, PaperRole.EDITOR]:
            raise HTTPException(status_code=403, detail="Edit access denied")
    
    version = db.query(PaperVersion).filter(
        PaperVersion.paper_id == paper_id,
        PaperVersion.version_number == version_number
    ).first()
    
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    # Restore paper content from version
    paper.title = version.title
    paper.content = version.content
    paper.content_json = version.content_json
    paper.abstract = version.abstract
    paper.keywords = version.keywords
    paper.references = version.references
    paper.current_version = version_number
    paper.updated_at = func.now()
    
    db.commit()
    db.refresh(paper)
    
    return {"message": f"Paper restored to version {version_number}", "current_version": paper.current_version}


@router.post("/{paper_id}/figures")
async def upload_figure(
    paper_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload a figure/image for a research paper."""
    import os
    import shutil
    from pathlib import Path

    # Check paper exists and user has access
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Check permissions
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id,
            PaperMember.status == "accepted"
        ).first()
        if not member or member.role not in {PaperRole.OWNER, PaperRole.ADMIN, PaperRole.EDITOR}:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Validate file type
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.pdf'}
    file_ext = Path(file.filename).suffix.lower() if file.filename else ''
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )

    # Create upload directory
    upload_dir = Path("uploads") / "papers" / str(paper_id) / "figures"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    import uuid
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    safe_filename = f"{timestamp}_{unique_id}{file_ext}"
    file_path = upload_dir / safe_filename

    # Save file
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save figure: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")

    # Return relative path for LaTeX
    relative_path = f"figures/{safe_filename}"

    return {
        "url": relative_path,
        "filename": safe_filename,
        "original_filename": file.filename,
        "size": file_path.stat().st_size
    }


@router.post("/{paper_id}/upload-bib")
async def upload_bib_file(
    paper_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a .bib (BibTeX) file for a research paper.
    """
    # Get paper and verify ownership
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    owner_identifier = getattr(paper, "owner_id", None)
    if owner_identifier is None:
        owner_identifier = getattr(paper, "author_id", None)

    if owner_identifier != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Validate file extension
    if not file.filename or not file.filename.endswith('.bib'):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only .bib files allowed"
        )

    # Create upload directory (same as paper root)
    upload_dir = Path("uploads") / "papers" / str(paper_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Save file with original name (typically main.bib)
    file_path = upload_dir / file.filename

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save .bib file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")

    return {
        "filename": file.filename,
        "size": file_path.stat().st_size
    }
