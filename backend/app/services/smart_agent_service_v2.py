"""
Smart Agent Service V2 - Tool-based orchestration (like Discussion AI)

Instead of keyword matching, we let the AI decide what action to take using function calling.
"""
import os
import json
import logging
import re
from typing import Optional, Dict, Any, Generator
from uuid import UUID
from sqlalchemy.orm import Session
from openai import OpenAI

logger = logging.getLogger(__name__)


def _is_valid_uuid(val: str) -> bool:
    """Check if string is a valid UUID."""
    try:
        UUID(val)
        return True
    except (ValueError, TypeError):
        return False


def _parse_short_id(url_id: str) -> str | None:
    """Extract short_id from url_id (e.g., 'slug-abc123' -> 'abc123')."""
    if not url_id:
        return None
    parts = url_id.rsplit("-", 1)
    if len(parts) == 2 and re.match(r"^[a-z0-9]{6,12}$", parts[1]):
        return parts[1]
    if re.match(r"^[a-z0-9]{6,12}$", url_id):
        return url_id
    return None


def _resolve_paper_id(db: Session, paper_id: str) -> Optional[UUID]:
    """Resolve paper_id (UUID or slug) to actual UUID."""
    from app.models.research_paper import ResearchPaper

    # Try UUID lookup first
    if _is_valid_uuid(paper_id):
        try:
            paper = db.query(ResearchPaper).filter(ResearchPaper.id == UUID(paper_id)).first()
            if paper:
                return paper.id
        except (ValueError, AttributeError):
            pass

    # Try short_id lookup
    short_id = _parse_short_id(paper_id)
    if short_id:
        paper = db.query(ResearchPaper).filter(ResearchPaper.short_id == short_id).first()
        if paper:
            return paper.id

    return None


# Tools available to the LaTeX Editor AI
EDITOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "answer_question",
            "description": "Answer a question about the paper, its content, structure, or writing. Use this for general questions that don't require editing the document.",
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                        "description": "Your answer to the user's question"
                    }
                },
                "required": ["answer"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_edit",
            "description": "Propose an edit to the document. Use this when the user asks you to change, modify, extend, shorten, rewrite, fix, improve, add, remove, or otherwise edit any part of their paper. IMPORTANT: All proposed text MUST be valid LaTeX that compiles without errors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "explanation": {
                        "type": "string",
                        "description": "Brief explanation of what you're changing and why"
                    },
                    "edits": {
                        "type": "array",
                        "description": "List of edits to make",
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {
                                    "type": "string",
                                    "description": "Brief description of this specific edit"
                                },
                                "original": {
                                    "type": "string",
                                    "description": "The EXACT text from the document to replace (copy verbatim including whitespace and LaTeX commands)"
                                },
                                "proposed": {
                                    "type": "string",
                                    "description": "The new VALID LaTeX text. Must compile without errors. Use proper apostrophes ('), escape special chars (%, &, #, $, _), match braces, preserve LaTeX commands."
                                }
                            },
                            "required": ["description", "original", "proposed"]
                        }
                    }
                },
                "required": ["explanation", "edits"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "review_document",
            "description": "Review the document and provide feedback. Use this when the user asks for review, feedback, evaluation, suggestions, or wants to know what you think about their writing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Brief overall assessment"
                    },
                    "strengths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of strengths in the document"
                    },
                    "improvements": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of suggested improvements"
                    },
                    "offer_edits": {
                        "type": "boolean",
                        "description": "Whether to offer to make the suggested changes"
                    }
                },
                "required": ["summary", "strengths", "improvements"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explain_references",
            "description": "Explain or discuss the attached references. Use when user asks about citations, references, or what sources are available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "explanation": {
                        "type": "string",
                        "description": "Explanation about the references"
                    },
                    "suggest_discovery": {
                        "type": "boolean",
                        "description": "Whether to suggest using Discussion AI or Discovery page to find more papers"
                    }
                },
                "required": ["explanation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_templates",
            "description": "List available conference/journal templates for formatting papers. Use when user asks about available formats, templates, or wants to know what conference styles are supported.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_template",
            "description": "Convert the document to a specific conference format. This will reformat the preamble, author block, sections, and citations to match the target template requirements. Use when user asks to convert, reformat, or change their paper to a specific conference format like ACL, IEEE, NeurIPS, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "string",
                        "enum": ["acl", "ieee", "neurips", "aaai", "icml", "generic"],
                        "description": "Target template format to convert to"
                    },
                    "preserve_content": {
                        "type": "boolean",
                        "default": True,
                        "description": "Keep all content while changing formatting (default: true)"
                    }
                },
                "required": ["template_id"]
            }
        }
    }
]


SYSTEM_PROMPT = """You are an expert academic writing assistant for the LaTeX editor in ScholarHub.

You have access to:
1. The user's FULL LaTeX document
2. References attached to this specific paper

YOUR CAPABILITIES:
- Answer questions about the paper's content, structure, or writing
- Propose edits to any part of the document
- Review and provide feedback on the writing
- Discuss attached references
- Convert documents between conference formats (ACL, IEEE, NeurIPS, AAAI, ICML, etc.)

SCOPE LIMITATIONS (IMPORTANT):
- You can ONLY use references already attached to THIS paper
- You CANNOT search for new papers or references online
- If user asks to find/search for papers, use explain_references and set suggest_discovery=true to tell them:
  "To discover new papers, use the **Discussion AI** in your project sidebar or the **Discovery page** in your project."

WHEN TO USE EACH TOOL:
- answer_question: General questions ("what is...", "how does...", "explain...", "summarize...")
- propose_edit: Any request to change the document ("extend", "shorten", "rewrite", "fix", "improve", "add", "remove", "modify", etc.)
- review_document: Feedback requests ("review this", "what do you think", "any suggestions", "how does this look")
- explain_references: Questions about citations or requests to find papers
- list_available_templates: When user asks what formats/templates are available
- apply_template: When user asks to convert to a specific conference format (ACL, IEEE, NeurIPS, etc.)

TEMPLATE CONVERSION:
When applying a template:
1. Replace the document preamble (\\documentclass through \\begin{document}) with the appropriate format
2. Reformat the author block to match the template's author_format
3. Ensure section names match the template conventions
4. Note any bibliography style changes needed
5. Preserve ALL user content while reformatting structure
6. Use propose_edit to make the actual changes after calling apply_template

FOR EDITS - CRITICAL LATEX REQUIREMENTS:
- Your proposed text MUST be valid LaTeX that compiles without errors
- Copy the EXACT original text from the document (including whitespace and LaTeX commands)
- Use proper characters: apostrophes ('), quotes (""), not smart quotes or unusual characters
- Escape special LaTeX characters when needed: %, &, #, $, _, {, }, ~, ^, \\
- Preserve existing LaTeX structure (commands, environments, braces)
- Do NOT introduce unmatched braces, broken commands, or invalid syntax
- If extending content, match the style and formatting of the surrounding text
- Test mentally that your proposed text would compile in LaTeX

Be concise and helpful. Focus on academic writing quality."""


class SmartAgentServiceV2:
    """
    Tool-based agent that lets the AI decide what action to take.
    No keyword matching - the AI chooses the appropriate tool.
    """

    FAST_MODEL = "gpt-5-mini"
    QUALITY_MODEL = "gpt-5.2"

    QUALITY_REASONING_EFFORT = "low"
    FULL_REASONING_EFFORT = "high"

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)
        # Store current document for template conversion
        self._current_document: Optional[str] = None

    def stream_query(
        self,
        db: Session,
        user_id: str,
        query: str,
        paper_id: Optional[str] = None,
        document_excerpt: Optional[str] = None,
        reasoning_mode: bool = False,
    ) -> Generator[str, None, None]:
        """Stream a response using tool-based orchestration."""
        if not self.client:
            yield "AI service not configured."
            return

        # Store document for template conversion use
        self._current_document = document_excerpt

        # Get reference context
        ref_context = self._get_reference_context(db, user_id, paper_id, query)

        # Build context
        context_parts = []
        if document_excerpt:
            context_parts.append(f"=== USER'S LATEX DOCUMENT ===\n{document_excerpt}")
        if ref_context:
            context_parts.append(f"=== ATTACHED REFERENCES ===\n{ref_context}")

        full_context = "\n\n".join(context_parts) if context_parts else "No document provided."

        # Choose model and reasoning effort
        model = self.QUALITY_MODEL
        reasoning_effort = self.FULL_REASONING_EFFORT if reasoning_mode else self.QUALITY_REASONING_EFFORT

        print(f"[SmartAgentV2] Using {model} with reasoning_effort={reasoning_effort}")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{full_context}\n\n---\n\nUser request: {query}"}
        ]

        try:
            # First call - let AI decide which tool to use
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                tools=EDITOR_TOOLS,
                tool_choice="required",  # Must use a tool
                max_completion_tokens=4000,
                reasoning_effort=reasoning_effort,
            )

            choice = response.choices[0]

            if choice.message.tool_calls:
                tool_call = choice.message.tool_calls[0]
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                print(f"[SmartAgentV2] AI chose tool: {tool_name}")

                # Format response based on tool
                yield from self._format_tool_response(tool_name, tool_args)
            else:
                # Fallback if no tool called
                if choice.message.content:
                    yield choice.message.content
                else:
                    yield "I'm not sure how to help with that. Could you rephrase your request?"

        except Exception as e:
            logger.error(f"[SmartAgentV2] Error: {e}")
            yield f"Sorry, an error occurred: {str(e)}"

    def _format_tool_response(self, tool_name: str, args: Dict[str, Any]) -> Generator[str, None, None]:
        """Format the tool response for the frontend."""

        if tool_name == "answer_question":
            yield args.get("answer", "")

        elif tool_name == "propose_edit":
            explanation = args.get("explanation", "")
            edits = args.get("edits", [])

            yield f"{explanation}\n\n"

            for edit in edits:
                yield f"<<<EDIT>>>\n"
                yield f"{edit.get('description', 'Edit')}\n"
                yield f"<<<ORIGINAL>>>\n"
                yield f"{edit.get('original', '')}\n"
                yield f"<<<PROPOSED>>>\n"
                yield f"{edit.get('proposed', '')}\n"
                yield f"<<<END>>>\n\n"

        elif tool_name == "review_document":
            summary = args.get("summary", "")
            strengths = args.get("strengths", [])
            improvements = args.get("improvements", [])
            offer_edits = args.get("offer_edits", True)

            yield f"## Review\n\n{summary}\n\n"

            if strengths:
                yield "### Strengths\n"
                for s in strengths:
                    yield f"- {s}\n"
                yield "\n"

            if improvements:
                yield "### Suggested Improvements\n"
                for i in improvements:
                    yield f"- {i}\n"
                yield "\n"

            if offer_edits:
                yield "Would you like me to make any of these suggested changes to your document?"

        elif tool_name == "explain_references":
            explanation = args.get("explanation", "")
            suggest_discovery = args.get("suggest_discovery", False)

            yield explanation

            if suggest_discovery:
                yield "\n\nTo discover new papers, use the **Discussion AI** in your project sidebar or the **Discovery page** in your project."

        elif tool_name == "list_available_templates":
            yield from self._handle_list_templates()

        elif tool_name == "apply_template":
            template_id = args.get("template_id", "")
            yield from self._handle_apply_template(template_id)

        else:
            yield f"Unknown tool: {tool_name}"

    def _get_reference_context(
        self,
        db: Session,
        user_id: str,
        paper_id: Optional[str],
        query: str,
        max_refs: int = 10
    ) -> str:
        """Get relevant reference summaries for context."""
        try:
            from app.models.reference import Reference
            from app.models.paper_reference import PaperReference

            if paper_id:
                # Resolve paper_id (could be UUID or slug)
                resolved_id = _resolve_paper_id(db, paper_id)
                if not resolved_id:
                    return "Paper not found."

                refs = db.query(Reference).join(
                    PaperReference, PaperReference.reference_id == Reference.id
                ).filter(
                    PaperReference.paper_id == resolved_id
                ).limit(max_refs).all()
            else:
                return ""

            if not refs:
                return "No references attached to this paper."

            lines = [f"({len(refs)} references attached to this paper):\n"]
            for i, ref in enumerate(refs, 1):
                authors = ", ".join(ref.authors[:2]) + (" et al." if len(ref.authors) > 2 else "") if ref.authors else "Unknown"
                lines.append(f"{i}. {ref.title} ({authors}, {ref.year or 'n.d.'})")
                if ref.abstract:
                    lines.append(f"   Abstract: {ref.abstract[:200]}...")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Error getting references: {e}")
            return ""

    def _handle_list_templates(self) -> Generator[str, None, None]:
        """Return formatted list of available conference templates."""
        from app.constants.paper_templates import CONFERENCE_TEMPLATES

        yield "## Available Conference Templates\n\n"
        yield "You can convert your paper to any of these formats:\n\n"

        for tid, template in CONFERENCE_TEMPLATES.items():
            yield f"**{template['name']}** (`{tid}`)\n"
            yield f"- {template['description']}\n"
            yield f"- {template['notes']}\n\n"

        yield "---\n\n"
        yield "To convert your document, say something like:\n"
        yield '- "Convert this to ACL format"\n'
        yield '- "Reformat for IEEE conference"\n'
        yield '- "Change to NeurIPS style"\n'

    def _handle_apply_template(self, template_id: str) -> Generator[str, None, None]:
        """Generate edit proposals for template conversion."""
        import re
        from app.constants.paper_templates import CONFERENCE_TEMPLATES

        if template_id not in CONFERENCE_TEMPLATES:
            yield f"Unknown template: `{template_id}`. "
            yield "Use `list_available_templates` to see available formats."
            return

        template = CONFERENCE_TEMPLATES[template_id]
        doc = self._current_document or ""

        yield f"## Converting to {template['name']}\n\n"
        yield f"{template['description']}\n\n"
        yield f"**Notes:** {template['notes']}\n\n"

        # If we have a document, generate actual edit proposals
        if doc:
            yield "Here are the edits to convert your document:\n\n"

            # Extract preamble (from start through \maketitle if present, otherwise just \begin{document})
            # This ensures we replace \maketitle too, avoiding duplicates
            preamble_match = re.search(
                r'^(.*?\\begin\{document\}\s*\\maketitle)',
                doc,
                re.DOTALL
            )
            if not preamble_match:
                # Fallback: just to \begin{document}
                preamble_match = re.search(
                    r'^(.*?\\begin\{document\})',
                    doc,
                    re.DOTALL
                )

            if preamble_match:
                original_preamble = preamble_match.group(1).strip()

                # Extract title from original document
                title_match = re.search(r'\\title\{([^}]*)\}', doc)
                title = title_match.group(1) if title_match else "Your Paper Title"

                # Extract authors from original document
                author_match = re.search(r'\\author\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', doc, re.DOTALL)
                original_authors = author_match.group(1) if author_match else ""

                # Build new preamble with extracted title
                new_preamble = template['preamble_example'].replace(
                    "Your Paper Title", title
                ).replace(
                    "Your Full Paper Title", title
                )

                yield "<<<EDIT>>>\n"
                yield "Replace preamble with conference format\n"
                yield "<<<ORIGINAL>>>\n"
                yield f"{original_preamble}\n"
                yield "<<<PROPOSED>>>\n"
                yield f"{new_preamble}\n"
                yield "<<<END>>>\n\n"

            # Check if bibliography style needs updating
            bib_match = re.search(r'\\bibliographystyle\{([^}]*)\}', doc)
            if bib_match:
                old_style = bib_match.group(0)
                new_style = f"\\bibliographystyle{{{template['bib_style']}}}"
                if old_style != new_style:
                    yield "<<<EDIT>>>\n"
                    yield f"Update bibliography style to {template['bib_style']}\n"
                    yield "<<<ORIGINAL>>>\n"
                    yield f"{old_style}\n"
                    yield "<<<PROPOSED>>>\n"
                    yield f"{new_style}\n"
                    yield "<<<END>>>\n\n"

            yield "---\n\n"
            yield "### Recommended Sections\n\n"
            yield "For this format, consider organizing with these sections:\n"
            for section in template['sections']:
                yield f"- {section}\n"
            yield "\n"

        else:
            # No document provided, just show template info
            yield "### Required Preamble\n\n"
            yield "Replace your document preamble with:\n\n"
            yield f"```latex\n{template['preamble_example']}\n```\n\n"
            yield "### Author Format\n\n"
            yield f"Use this author block format:\n`{template['author_format']}`\n\n"
            yield "### Recommended Sections\n\n"
            for section in template['sections']:
                yield f"- {section}\n"
            yield f"\n### Bibliography Style\n\n"
            yield f"Use `{template['bib_style']}` for your bibliography.\n"
