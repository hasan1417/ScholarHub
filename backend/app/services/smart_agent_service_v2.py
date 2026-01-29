"""
Smart Agent Service V2 - Tool-based orchestration for LaTeX Editor AI.

Simple approach:
- Templates are in the system prompt (authoritative)
- AI uses propose_edit directly for conversions
- No multi-step tool orchestration needed
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

    if _is_valid_uuid(paper_id):
        try:
            paper = db.query(ResearchPaper).filter(ResearchPaper.id == UUID(paper_id)).first()
            if paper:
                return paper.id
        except (ValueError, AttributeError):
            pass

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
            "description": "Propose an edit to the document. Use for any changes: modify, extend, shorten, rewrite, fix, improve, add, remove. NOT for template conversion - use apply_template for that.",
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
                                "start_line": {
                                    "type": "integer",
                                    "description": "Line number where the text to replace STARTS"
                                },
                                "end_line": {
                                    "type": "integer",
                                    "description": "Line number where the text to replace ENDS (inclusive)"
                                },
                                "anchor": {
                                    "type": "string",
                                    "description": "First 30-50 characters from start_line (for verification)"
                                },
                                "proposed": {
                                    "type": "string",
                                    "description": "The new VALID LaTeX text"
                                }
                            },
                            "required": ["description", "start_line", "end_line", "anchor", "proposed"]
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
            "description": "Review the document and provide feedback.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Brief overall assessment"},
                    "strengths": {"type": "array", "items": {"type": "string"}},
                    "improvements": {"type": "array", "items": {"type": "string"}},
                    "offer_edits": {"type": "boolean", "description": "Whether to offer to make changes"}
                },
                "required": ["summary", "strengths", "improvements"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explain_references",
            "description": "Explain or discuss the attached references.",
            "parameters": {
                "type": "object",
                "properties": {
                    "explanation": {"type": "string"},
                    "suggest_discovery": {"type": "boolean", "description": "Suggest using Discovery page for more papers"}
                },
                "required": ["explanation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_templates",
            "description": "List available conference/journal templates. Use ONLY when user asks what formats are available, NOT for conversion.",
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
            "description": "Convert the document to a specific conference/journal format. Use this when user asks to convert, reformat, or change to a specific format like IEEE, ACL, NeurIPS, CVPR, etc. This will return the template structure, then you MUST call propose_edit to apply it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "string",
                        "enum": ["acl", "ieee", "neurips", "aaai", "icml", "generic", "cvpr", "iccv", "eccv", "iclr", "jmlr", "ijcai", "kdd", "lncs", "elsevier", "nature", "pnas", "acm"],
                        "description": "Target template format"
                    }
                },
                "required": ["template_id"]
            }
        }
    }
]


# System prompt
SYSTEM_PROMPT = """You are an expert academic writing assistant for the LaTeX editor in ScholarHub.

## YOUR CAPABILITIES
- Answer questions about the paper
- Propose edits to any part of the document
- Review and provide feedback
- Convert documents to conference formats

## LINE-BASED EDITING
The document shows line numbers like "  15| content here".
Use these EXACT line numbers for start_line and end_line in propose_edit.

## TEMPLATE CONVERSION (TWO-STEP PROCESS)
When user asks to convert (e.g., "convert to ACM", "reformat for IEEE"):
1. FIRST call apply_template with the template_id
2. You will receive the AUTHORITATIVE template structure
3. THEN call propose_edit to replace lines 1 through \\maketitle with the new preamble
4. Extract title, authors, affiliations, emails from the CURRENT document and fill into template

IMPORTANT:
- Use apply_template for conversion, NOT list_available_templates
- After apply_template returns, you MUST call propose_edit to apply the changes

## AVAILABLE TEMPLATE IDs
ieee, acl, neurips, icml, iclr, cvpr, iccv, eccv, nature, pnas, generic, elsevier, lncs, aaai, ijcai, kdd, acm, jmlr

Be concise and helpful. Focus on academic writing quality."""


class SmartAgentServiceV2:
    """
    Tool-based agent for LaTeX Editor AI.
    Templates are in the system prompt - AI uses propose_edit directly.
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
        self._current_document = None

    def _add_line_numbers(self, text: str) -> str:
        """Add line numbers to text for line-based editing."""
        lines = text.split('\n')
        width = max(len(str(len(lines))), 3)
        numbered_lines = [f"{i:>{width}}| {line}" for i, line in enumerate(lines, 1)]
        return '\n'.join(numbered_lines)

    def stream_query(
        self,
        db: Session,
        user_id: str,
        query: str,
        paper_id: Optional[str] = None,
        document_excerpt: Optional[str] = None,
        reasoning_mode: bool = False,
    ) -> Generator[str, None, None]:
        """Stream a response using tool-based orchestration with multi-turn support."""
        if not self.client:
            yield "AI service not configured."
            return

        # Store document for template conversion
        self._current_document = document_excerpt

        # Get reference context
        ref_context = self._get_reference_context(db, user_id, paper_id, query)

        # Build context with line numbers
        context_parts = []
        if document_excerpt:
            numbered_doc = self._add_line_numbers(document_excerpt)
            context_parts.append(f"=== USER'S LATEX DOCUMENT (with line numbers) ===\n{numbered_doc}")
        if ref_context:
            context_parts.append(f"=== ATTACHED REFERENCES ===\n{ref_context}")

        full_context = "\n\n".join(context_parts) if context_parts else "No document provided."

        model = self.QUALITY_MODEL
        reasoning_effort = self.FULL_REASONING_EFFORT if reasoning_mode else self.QUALITY_REASONING_EFFORT

        print(f"[SmartAgentV2] Using {model} with reasoning_effort={reasoning_effort}")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{full_context}\n\n---\n\nUser request: {query}"}
        ]

        # Multi-turn for template conversion (apply_template → propose_edit)
        max_turns = 3
        turn = 0

        try:
            while turn < max_turns:
                turn += 1

                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=EDITOR_TOOLS,
                    tool_choice="required" if turn == 1 else "auto",
                    max_completion_tokens=4000,
                    reasoning_effort=reasoning_effort,
                )

                choice = response.choices[0]

                if choice.message.tool_calls:
                    tool_call = choice.message.tool_calls[0]
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    print(f"[SmartAgentV2] Turn {turn}: {tool_name}")

                    # Intermediate tools - return info to AI for further processing
                    if tool_name == "apply_template":
                        template_info = "".join(self._handle_apply_template(tool_args.get("template_id", "")))
                        messages.append(choice.message)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": template_info
                        })
                        continue  # AI will call propose_edit next

                    # Final action tools - format and return
                    yield from self._format_tool_response(tool_name, tool_args)
                    return
                else:
                    if choice.message.content:
                        yield choice.message.content
                    else:
                        yield "I'm not sure how to help with that. Could you rephrase?"
                    return

            yield "Could not complete the request. Please try again."

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
                yield "<<<EDIT>>>\n"
                yield f"{edit.get('description', 'Edit')}\n"
                yield "<<<LINES>>>\n"
                yield f"{edit.get('start_line', 1)}-{edit.get('end_line', 1)}\n"
                yield "<<<ANCHOR>>>\n"
                yield f"{edit.get('anchor', '')}\n"
                yield "<<<PROPOSED>>>\n"
                yield f"{edit.get('proposed', '')}\n"
                yield "<<<END>>>\n\n"

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
                yield "Would you like me to make any of these suggested changes?"

        elif tool_name == "explain_references":
            yield args.get("explanation", "")
            if args.get("suggest_discovery"):
                yield "\n\nTo discover new papers, use the **Discussion AI** or **Discovery page**."

        elif tool_name == "list_available_templates":
            yield from self._handle_list_templates()

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

            lines = [f"({len(refs)} references attached):\n"]
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
        """Return formatted list of available templates."""
        yield "## Available Conference Templates\n\n"
        yield "| Template | ID | Notes |\n"
        yield "|----------|-----|-------|\n"
        yield "| IEEE Conference | `ieee` | Two-column, IEEEtran class |\n"
        yield "| ACL/EMNLP/NAACL | `acl` | NLP conferences, natbib citations |\n"
        yield "| NeurIPS | `neurips` | ML conference, single-column |\n"
        yield "| ICML | `icml` | ML conference |\n"
        yield "| ICLR | `iclr` | ML conference |\n"
        yield "| CVPR/ICCV | `cvpr` | Computer vision, two-column |\n"
        yield "| ECCV | `eccv` | Computer vision |\n"
        yield "| Nature/Science | `nature` | High-impact journals |\n"
        yield "| PNAS | `pnas` | Two-column journal |\n"
        yield "| Elsevier | `elsevier` | Journal format |\n"
        yield "| LNCS (Springer) | `lncs` | Conference proceedings |\n"
        yield "| AAAI | `aaai` | AI conference |\n"
        yield "| IJCAI | `ijcai` | AI conference |\n"
        yield "| KDD | `kdd` | Data mining |\n"
        yield "| ACM CHI | `acm` | HCI conference |\n"
        yield "| Generic Article | `generic` | Simple format |\n"
        yield "\nTo convert, say: \"Convert to IEEE format\" or \"Reformat for NeurIPS\"\n"

    def _handle_apply_template(self, template_id: str) -> Generator[str, None, None]:
        """Return template info for AI to use with propose_edit."""
        from app.constants.paper_templates import CONFERENCE_TEMPLATES

        if template_id not in CONFERENCE_TEMPLATES:
            yield f"Unknown template: `{template_id}`. Available: {', '.join(CONFERENCE_TEMPLATES.keys())}"
            return

        template = CONFERENCE_TEMPLATES[template_id]

        yield f"## Template: {template['name']}\n\n"
        yield f"{template['description']}\n\n"

        yield "### EXACT Preamble Structure to Use\n\n"
        yield "Copy this structure and fill in the actual title/authors from the document:\n\n"
        yield f"```latex\n{template['preamble_example']}\n```\n\n"

        yield f"### Author Format: `{template['author_format']}`\n\n"
        yield f"### Bibliography: `\\bibliographystyle{{{template['bib_style']}}}`\n\n"
        yield f"### Notes: {template['notes']}\n\n"

        yield "---\n\n"
        yield "**NOW call propose_edit** to replace lines 1 through \\maketitle with this template.\n"
        yield "Extract the title, authors, affiliations, and emails from the current document and plug them into the template structure above.\n"
