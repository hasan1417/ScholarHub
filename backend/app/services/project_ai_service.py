from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from sqlalchemy.orm import Session, joinedload

from app.models import (
    AIArtifact,
    AIArtifactStatus,
    AIArtifactType,
    Project,
    PaperReference,
    ProjectReference,
    ProjectReferenceStatus,
    ResearchPaper,
    User,
)
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


@dataclass
class ProjectContext:
    project_summary: str
    approved_references: Sequence[str]


@dataclass
class PaperContext(ProjectContext):
    paper_summary: str
    paper_references: Sequence[str]


class ProjectAIContextBuilder:
    """Utility to build project and paper scoped context prompts."""

    def __init__(self, db: Session):
        self.db = db

    def load_project(self, project: Project) -> Project:
        """Ensure we have a fully populated project instance with relationships."""
        if "references" in project.__dict__ and "papers" in project.__dict__:
            # Assume object already hydrated when relationships attached
            return project

        return (
            self.db.query(Project)
            .options(
                joinedload(Project.references).joinedload(ProjectReference.reference),
                joinedload(Project.papers)
                .joinedload(ResearchPaper.reference_links)
                .joinedload(PaperReference.reference),
            )
            .filter(Project.id == project.id)
            .first()
        ) or project

    def _format_reference(self, ref: ProjectReference) -> Optional[str]:
        reference = ref.reference
        if not reference:
            return None
        pieces = []
        if reference.title:
            pieces.append(reference.title)
        if reference.authors:
            pieces.append(", ".join(reference.authors))
        if reference.year:
            pieces.append(str(reference.year))
        if reference.journal:
            pieces.append(reference.journal)
        return " — ".join(pieces) if pieces else None

    def build_project_context(self, project: Project) -> ProjectContext:
        hydrated = self.load_project(project)
        approved = [
            formatted
            for link in hydrated.references
            if link.status == ProjectReferenceStatus.APPROVED
            for formatted in [self._format_reference(link)]
            if formatted
        ]

        summary_lines = [f"Project: {hydrated.title}"]
        if hydrated.idea:
            summary_lines.append(f"Idea: {hydrated.idea.strip()}")
        if hydrated.scope:
            summary_lines.append(f"Scope: {hydrated.scope.strip()}")
        if hydrated.keywords:
            summary_lines.append(f"Keywords: {', '.join(hydrated.keywords)}")

        return ProjectContext(
            project_summary="\n".join(summary_lines),
            approved_references=approved,
        )

    def build_paper_context(self, paper: ResearchPaper) -> PaperContext:
        project_context = self.build_project_context(paper.project)
        references = []
        for link in paper.reference_links:
            ref = link.reference
            if not ref:
                continue
            project_link = next(
                (pl for pl in ref.project_links if pl.project_id == paper.project_id),
                None,
            )
            if project_link:
                formatted = self._format_reference(project_link)
            else:
                pieces = [ref.title]
                if ref.authors:
                    pieces.append(", ".join(ref.authors))
                if ref.year:
                    pieces.append(str(ref.year))
                formatted = " — ".join(filter(None, pieces))
            if formatted:
                references.append(formatted)

        paper_summary_lines = [f"Paper: {paper.title}"]
        if paper.abstract:
            paper_summary_lines.append(f"Abstract: {paper.abstract.strip()}")
        if paper.summary:
            paper_summary_lines.append(f"Summary: {paper.summary.strip()}")
        if paper.keywords:
            paper_summary_lines.append(f"Keywords: {', '.join(paper.keywords)}")

        return PaperContext(
            project_summary=project_context.project_summary,
            approved_references=project_context.approved_references,
            paper_summary="\n".join(paper_summary_lines),
            paper_references=references,
        )


class ProjectAIOrchestrator:
    """Generate scoped AI artifacts (project vs paper)."""

    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service

    def _mock_response(
        self,
        artifact_type: AIArtifactType,
        context: ProjectContext,
        paper_context: Optional[PaperContext],
        *,
        focus: Optional[str] = None,
        channel_context: Optional[str] = None,
    ) -> str:
        lines = [f"[Mock] Generated {artifact_type.value}."]
        lines.append("Context summary:")
        lines.append(context.project_summary)
        if paper_context:
            lines.append("\nPaper details:")
            lines.append(paper_context.paper_summary)
        if context.approved_references:
            lines.append("\nReferences considered:")
            for ref in context.approved_references[:5]:
                lines.append(f"- {ref}")
        if channel_context:
            lines.append("\nChannel context:")
            lines.append(channel_context)
        if focus:
            lines.append(f"\nFocus: {focus}")
        return "\n".join(lines)

    def _mock_channel_artifact(
        self,
        request: str,
        context: ProjectContext,
        channel_context: Optional[str],
    ) -> str:
        lines = ["[Mock] Channel artifact response."]
        lines.append(f"Request: {request}")
        lines.append("\nProject snapshot:")
        lines.append(context.project_summary)
        if channel_context:
            lines.append("\nChannel context:")
            lines.append(channel_context)
        if context.approved_references:
            lines.append("\nReferences:")
            for ref in context.approved_references[:5]:
                lines.append(f"- {ref}")
        return "\n".join(lines)

    def _call_llm(self, prompt: str) -> str:
        if not self.ai_service.openai_client:
            return prompt  # Should not happen; caller handles mock case

        response = self.ai_service.openai_client.chat.completions.create(
            model=self.ai_service.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an AI assistant that helps researchers summarize projects and papers."
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1200,
            temperature=0.4,
        )
        return response.choices[0].message.content

    def _build_prompt(
        self,
        artifact_type: AIArtifactType,
        context: ProjectContext,
        paper_context: Optional[PaperContext],
        focus: Optional[str],
        channel_context: Optional[str] = None,
    ) -> str:
        sections = [context.project_summary]
        if context.approved_references:
            sections.append("Approved references:\n" + "\n".join(f"- {ref}" for ref in context.approved_references))
        if paper_context:
            sections.append(paper_context.paper_summary)
            if paper_context.paper_references:
                sections.append("Paper references:\n" + "\n".join(f"- {ref}" for ref in paper_context.paper_references))
        if channel_context:
            sections.append("Recent discussion context:\n" + channel_context)

        directive_map = {
            AIArtifactType.SUMMARY: "Write a concise, structured summary (objective, approach, findings, next steps).",
            AIArtifactType.LIT_REVIEW: "Produce a literature review outline highlighting the most relevant references and gaps.",
            AIArtifactType.OUTLINE: "Draft an outline for the next paper deliverable, incorporating project goals.",
            AIArtifactType.DIRECTORY_HELP: "List documentation sections and assets the team should prepare, referencing scope and keywords.",
            AIArtifactType.INTENT: "Extract action items and intents the team should pursue next.",
        }
        directive = directive_map.get(artifact_type, "Provide helpful analysis.")
        if focus:
            directive += f" Focus on: {focus}."

        sections.append(f"Instructions: {directive}")
        return "\n\n".join(sections)

    def generate_artifact(
        self,
        db: Session,
        project: Project,
        user: User,
        artifact_type: AIArtifactType,
        *,
        paper: Optional[ResearchPaper] = None,
        focus: Optional[str] = None,
    ) -> AIArtifact:
        if paper and paper.project_id != project.id:
            raise ValueError("Paper does not belong to project")

        context_builder = ProjectAIContextBuilder(db)
        project_context = context_builder.build_project_context(project)
        paper_context = context_builder.build_paper_context(paper) if paper else None

        artifact = AIArtifact(
            project_id=project.id,
            paper_id=paper.id if paper else None,
            type=artifact_type,
            status=AIArtifactStatus.RUNNING,
            payload={},
            created_by=user.id,
        )
        db.add(artifact)
        db.flush()

        try:
            prompt = self._build_prompt(
                artifact_type,
                project_context,
                paper_context,
                focus,
                None,
            )
            if not self.ai_service.openai_client:
                result = self._mock_response(
                    artifact_type,
                    project_context,
                    paper_context,
                    focus=focus,
                    channel_context=None,
                )
            else:
                result = self._call_llm(prompt)

            artifact.status = AIArtifactStatus.SUCCEEDED
            artifact.payload = {
                "prompt": prompt,
                "result": result,
                "focus": focus,
            }
        except Exception as exc:  # pragma: no cover (LLM error handling)
            logger.exception("AI generation failed: %s", exc)
            artifact.status = AIArtifactStatus.FAILED
            artifact.payload = {
                "error": str(exc),
                "focus": focus,
            }
        finally:
            db.commit()
            db.refresh(artifact)

        return artifact
