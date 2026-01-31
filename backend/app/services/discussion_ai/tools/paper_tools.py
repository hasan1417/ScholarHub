from __future__ import annotations

from typing import Any, Dict, List

from .registry import ToolRegistry, ToolSpec


GET_PROJECT_PAPERS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_project_papers",
        "description": "Get the user's own draft papers/documents in this project. Use when user mentions 'my paper', 'my draft', 'the paper I'm writing'. When displaying content to user, output it directly as markdown (NOT in a code block) so it renders nicely.",
        "parameters": {
            "type": "object",
            "properties": {
                "include_content": {
                    "type": "boolean",
                    "description": "Whether to include full paper content",
                    "default": False,
                },
            },
        },
    },
}

CREATE_PAPER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_paper",
        "description": "Create a new paper/document in the project. Use when user asks to 'create a paper', 'write a literature review', 'start a new document'. The paper will be available in the LaTeX editor. IMPORTANT: Content MUST be in LaTeX format, NOT Markdown! CRITICAL: Before calling this, ensure you have papers to cite - either from recent search, library, or call search_papers first!",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the paper. Use a proper academic title WITHOUT metadata like '(5 References)' or counts. Example: 'Federated Learning for Healthcare: A Literature Review'",
                },
                "content": {
                    "type": "string",
                    "description": "Content in LATEX FORMAT ONLY. Use ONLY basic LaTeX: \\section{}, \\subsection{}, \\textbf{}, \\textit{}, \\begin{itemize}, \\cite{}. Do NOT use Markdown. MUST INCLUDE CITATIONS: Use \\cite{authorYYYYword} format where author=first author's last name (lowercase), YYYY=year, word=first significant word from title (lowercase). Example: \\cite{mcmahan2017communication} for 'Communication-Efficient Learning' by McMahan (2017). Every academic paper needs citations - do not create papers without \\cite{} commands! Do NOT add References section - it's auto-generated from your citations.",
                },
                "paper_type": {
                    "type": "string",
                    "description": "Type of paper: 'literature_review', 'research', 'summary', 'notes'",
                    "default": "research",
                },
                "abstract": {
                    "type": "string",
                    "description": "Optional abstract/summary of the paper",
                },
                "template": {
                    "type": "string",
                    "enum": ["generic", "ieee", "acl", "neurips", "icml", "iclr", "aaai", "cvpr", "iccv", "eccv", "nature", "elsevier", "acm", "lncs", "jmlr", "ijcai", "kdd", "pnas"],
                    "description": "Conference/journal template format. Use when user specifies a format like 'IEEE format', 'ACL style', 'Nature template'. Default is 'generic' (simple article).",
                    "default": "generic",
                },
            },
            "required": ["title", "content"],
        },
    },
}

UPDATE_PAPER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "update_paper",
        "description": "Update an existing paper's content. Content MUST be in LaTeX format! Use section_name to replace a SPECIFIC section (e.g., 'Conclusion'), or append=True to add NEW sections at the end.",
        "parameters": {
            "type": "object",
            "properties": {
                "paper_id": {
                    "type": "string",
                    "description": "ID of the paper to update (get from get_project_papers)",
                },
                "content": {
                    "type": "string",
                    "description": "New content in LATEX FORMAT. Use \\section{}, \\subsection{}, \\textbf{}, \\cite{}, etc. NOT Markdown. NEVER include \\end{document} or a References/Bibliography section - both are handled automatically.",
                },
                "section_name": {
                    "type": "string",
                    "description": "Name of section to REPLACE (e.g., 'Conclusion', 'Introduction', 'Methods'). Content should be the section only (from \\section{Name} to the content, NOT including \\end{document} or bibliography). Use for 'extend/expand/rewrite section X' requests.",
                },
                "append": {
                    "type": "boolean",
                    "description": "True = add content at end (for NEW sections). Ignored if section_name is provided.",
                    "default": True,
                },
            },
            "required": ["paper_id", "content"],
        },
    },
}

GENERATE_SECTION_FROM_DISCUSSION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_section_from_discussion",
        "description": "Generate a paper section based on the discussion insights and focused papers. Use when user asks to 'write a methodology section', 'create related work', 'draft an introduction based on our discussion'.",
        "parameters": {
            "type": "object",
            "properties": {
                "section_type": {
                    "type": "string",
                    "enum": ["methodology", "related_work", "introduction", "results", "discussion", "conclusion", "abstract"],
                    "description": "Type of section to generate",
                },
                "target_paper_id": {
                    "type": "string",
                    "description": "Optional: ID of paper to add section to. If not provided, creates an artifact.",
                },
                "custom_instructions": {
                    "type": "string",
                    "description": "Optional: Custom instructions for the section (e.g., 'focus on transformer methods', 'emphasize practical applications')",
                },
            },
            "required": ["section_type"],
        },
    },
}


def _handle_get_project_papers(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_get_project_papers(ctx, **args)


def _handle_create_paper(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_create_paper(ctx, **args)


def _handle_update_paper(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_update_paper(ctx, **args)


def _handle_generate_section_from_discussion(orchestrator: Any, ctx: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    return orchestrator._tool_generate_section_from_discussion(ctx, **args)


TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="get_project_papers",
        schema=GET_PROJECT_PAPERS_SCHEMA,
        handler=_handle_get_project_papers,
    ),
    ToolSpec(
        name="create_paper",
        schema=CREATE_PAPER_SCHEMA,
        handler=_handle_create_paper,
    ),
    ToolSpec(
        name="update_paper",
        schema=UPDATE_PAPER_SCHEMA,
        handler=_handle_update_paper,
    ),
    ToolSpec(
        name="generate_section_from_discussion",
        schema=GENERATE_SECTION_FROM_DISCUSSION_SCHEMA,
        handler=_handle_generate_section_from_discussion,
    ),
]


def register(registry: ToolRegistry) -> None:
    for spec in TOOL_SPECS:
        registry.register(spec)
