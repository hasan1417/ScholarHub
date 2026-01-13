"""
Explain Skill - Handles questions and explanations about papers, concepts, and project.

Uses multiple context sources based on the question:
1. Discovered references - Papers from recent search results
2. Project references - Papers saved in project library
3. Project papers - Papers being written by the user
4. Project info - Project objectives, description, scope
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .base import BaseSkill, Intent, SkillContext, SkillResult, SkillState


class ExplainSkill(BaseSkill):
    """
    Handles explanation and analysis requests.

    Context Selection Logic (per use case doc):
    - "discovered/found/above papers" → use recent_search_results
    - "my paper/our paper" → use project_papers
    - "project/objectives/goals" → use project_info
    - specific paper title → find in all sources
    - else → use all available context
    """

    name = "explain"
    description = "Explain papers, concepts, and project info"
    handles_intents = [Intent.EXPLAIN]

    # Needs all context sources for flexible answering
    needs_search_results = True
    needs_project_references = True
    needs_project_papers = True

    # Prompt templates for different source types
    PROMPT_WITH_CONTEXT = """You are a research assistant helping with the project "{project_title}".

Answer the user's question based on the following context. Be clear and concise.

{context}

If you don't have enough information to answer, say so clearly."""

    PROMPT_GENERAL = """You are a research assistant helping with the project "{project_title}".

Answer the user's question. If you need specific papers or references to answer accurately,
explain what additional context would help."""

    def handle(self, ctx: SkillContext) -> SkillResult:
        """Handle an explanation request."""

        # Select which context sources to use
        sources = self._select_context_sources(ctx)

        # Build context string
        context = self._build_context_string(sources)

        # Choose prompt based on available context
        if context.strip():
            prompt = self.PROMPT_WITH_CONTEXT.format(
                project_title=ctx.project_title,
                context=context,
            )
        else:
            prompt = self.PROMPT_GENERAL.format(
                project_title=ctx.project_title,
            )

        # Generate response
        response = self._call_llm(
            system_prompt=prompt,
            user_message=ctx.user_message,
            reasoning_effort="low",
            max_tokens=1500,
        )

        return SkillResult(
            message=response,
            next_state=SkillState.COMPLETE,
            actions=[],  # Explain doesn't have actions
        )

    def _select_context_sources(self, ctx: SkillContext) -> Dict[str, Optional[List]]:
        """
        Select which context sources to use based on the question.

        Returns dict with keys for each source type that should be used.
        """
        message_lower = ctx.user_message.lower()
        sources = {}

        # Check for discovered/search result references
        discovered_patterns = [
            r"\b(above|discovered|found|search|result)\s*(paper|ref|result)s?\b",
            r"\b(first|second|third|1st|2nd|3rd|\d+)\s*(paper|reference)\b",
            r"\bpaper\s*(\d+|one|two|three)\b",
            r"\bthe\s*(papers|references)\s*(above|you found)\b",
        ]
        for pattern in discovered_patterns:
            if re.search(pattern, message_lower):
                sources["discovered_refs"] = ctx.recent_search_results
                break

        # Check for user's own paper
        own_paper_patterns = [
            r"\b(my|our)\s*paper\b",
            r"\bwhat\s+(does|do)\s+(my|our)\s+(paper|writing)\b",
            r"\b(my|our)\s+(introduction|methodology|conclusion|abstract)\b",
        ]
        for pattern in own_paper_patterns:
            if re.search(pattern, message_lower):
                sources["project_papers"] = ctx.project_papers
                break

        # Check for project info
        project_info_patterns = [
            r"\bproject\s*(objective|goal|scope|description)s?\b",
            r"\b(our|this)\s*project\b",
            r"\bwhat\s+are\s+we\s+(trying|doing|working)\b",
            r"\bproject\s+goals?\b",
        ]
        for pattern in project_info_patterns:
            if re.search(pattern, message_lower):
                sources["project_info"] = getattr(ctx, 'project_info', None)
                break

        # Check for saved references
        saved_refs_patterns = [
            r"\b(my|saved|library)\s*references?\b",
            r"\bfrom\s*(my|the)\s*library\b",
        ]
        for pattern in saved_refs_patterns:
            if re.search(pattern, message_lower):
                sources["project_refs"] = ctx.project_references
                break

        # If no specific source matched, use all available
        if not sources:
            if ctx.recent_search_results:
                sources["discovered_refs"] = ctx.recent_search_results
            if ctx.project_references:
                sources["project_refs"] = ctx.project_references
            if ctx.project_papers:
                sources["project_papers"] = ctx.project_papers
            if hasattr(ctx, 'project_info') and ctx.project_info:
                sources["project_info"] = ctx.project_info

        return sources

    def _build_context_string(self, sources: Dict[str, Optional[List]]) -> str:
        """Build a context string from selected sources."""
        sections = []

        if sources.get("discovered_refs"):
            lines = ["## Recently Found Papers"]
            for i, paper in enumerate(sources["discovered_refs"][:10], 1):
                title = paper.get("title", "Untitled")
                authors = paper.get("authors", "Unknown")
                year = paper.get("year", "")
                abstract = paper.get("abstract", "")[:500]
                lines.append(f"\n### Paper {i}: {title}")
                lines.append(f"Authors: {authors}")
                if year:
                    lines.append(f"Year: {year}")
                if abstract:
                    lines.append(f"Abstract: {abstract}")
            sections.append("\n".join(lines))

        if sources.get("project_refs"):
            lines = ["## Saved Project References"]
            for i, ref in enumerate(sources["project_refs"][:10], 1):
                title = ref.get("title", "Untitled")
                authors = ref.get("authors", "Unknown")
                abstract = ref.get("abstract", "")[:300]
                lines.append(f"\n{i}. {title}")
                lines.append(f"   Authors: {authors}")
                if abstract:
                    lines.append(f"   Abstract: {abstract}")
            sections.append("\n".join(lines))

        if sources.get("project_papers"):
            lines = ["## Your Project Papers"]
            for paper in sources["project_papers"][:5]:
                title = paper.get("title", "Untitled")
                content = paper.get("content", "")[:1000]
                lines.append(f"\n### {title}")
                lines.append(content)
            sections.append("\n".join(lines))

        if sources.get("project_info"):
            info = sources["project_info"]
            lines = ["## Project Information"]
            if isinstance(info, dict):
                if info.get("objectives"):
                    lines.append(f"Objectives: {info['objectives']}")
                if info.get("scope"):
                    lines.append(f"Scope: {info['scope']}")
                if info.get("description"):
                    lines.append(f"Description: {info['description']}")
            elif isinstance(info, str):
                lines.append(info)
            sections.append("\n".join(lines))

        return "\n\n".join(sections)
