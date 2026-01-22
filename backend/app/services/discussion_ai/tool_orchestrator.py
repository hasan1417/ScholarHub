"""
Tool-Based Discussion AI Orchestrator

Uses OpenAI function calling to let the AI decide what context it needs.
Instead of hardcoding what data each skill uses, the AI calls tools on-demand.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Generator, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import Project, ProjectDiscussionChannel
    from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

# Tool definitions for OpenAI function calling
DISCUSSION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_recent_search_results",
            "description": "Get papers from the most recent search. Use this FIRST when user says 'these papers', 'these references', 'the 5 papers', 'use them', or refers to papers that were just searched/found. This contains the papers from the last search action.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_references",
            "description": "Get papers/references from the user's project library (permanently saved papers). Use when user mentions 'my library', 'saved papers', 'my collection'. Returns count, ingested_pdf_count, has_pdf_available_count, and paper details. For ingested PDFs, includes summary, key_findings, methodology, limitations. For detailed info about a single paper, use get_reference_details instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_filter": {
                        "type": "string",
                        "description": "Optional keyword to filter references by topic"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of references to return",
                        "default": 10
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_reference_details",
            "description": "Get detailed information about a specific reference from the library by ID. Use when user asks about a specific paper's content, what it's about, key findings, methodology, or wants a summary. Returns full analysis data if PDF was ingested (summary, key_findings, methodology, limitations, page_count).",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference_id": {
                        "type": "string",
                        "description": "The ID of the reference to get details for"
                    }
                },
                "required": ["reference_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_reference",
            "description": "Re-analyze a reference to generate/update its summary, key_findings, methodology, and limitations. Use when get_reference_details returns empty analysis fields (null summary/key_findings) for an ingested PDF, or when user asks to 'analyze', 're-analyze', or 'summarize' a specific reference. Requires the reference to have an ingested PDF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference_id": {
                        "type": "string",
                        "description": "The ID of the reference to analyze"
                    }
                },
                "required": ["reference_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_papers",
            "description": "Search for academic papers online. Returns papers matching the query. Papers with PDF available are marked with 'OA' (Open Access) and can be ingested for AI analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'machine learning transformers'). For recent papers, add year terms like '2023 2024'."
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of papers to find",
                        "default": 5
                    },
                    "open_access_only": {
                        "type": "boolean",
                        "description": "If true, only return papers with PDF available (Open Access). Use when user asks for 'only open access', 'only OA', 'papers with PDF', 'papers I can ingest', etc.",
                        "default": False
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
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
                        "default": False
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_info",
            "description": "Get information about the current research project (title, description, goals, keywords). Use when user asks about 'the project', 'project goals', or needs project context.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_project_info",
            "description": "Update project description and/or objectives. Use when user asks to 'update project description', 'add objective', 'change project goals', 'modify objectives', etc. Objectives are stored as separate items - you can add new ones or replace all.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "New project description (replaces existing). Omit to keep current description unchanged."
                    },
                    "objectives": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of objectives. Each objective should be concise (max 150 chars). Example: ['Analyze ML algorithms', 'Compare performance metrics']"
                    },
                    "objectives_mode": {
                        "type": "string",
                        "enum": ["replace", "append", "remove"],
                        "description": "'replace' = replace all objectives. 'append' = add new objectives. 'remove' = remove specific objectives (match by text or index like 'objective 1', 'objective 2'). Default is 'replace'.",
                        "default": "replace"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_channel_resources",
            "description": "Get papers/references specifically attached to this discussion channel. Use when user mentions 'channel papers' or papers in this specific discussion.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_paper",
            "description": "Create a new paper/document in the project. Use when user asks to 'create a paper', 'write a literature review', 'start a new document'. The paper will be available in the LaTeX editor. IMPORTANT: Content MUST be in LaTeX format, NOT Markdown!",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title of the paper. Use a proper academic title WITHOUT metadata like '(5 References)' or counts. Example: 'Federated Learning for Healthcare: A Literature Review'"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content in LATEX FORMAT ONLY. Use \\section{}, \\subsection{}, \\textbf{}, \\textit{}, \\begin{itemize}, \\cite{}, etc. Do NOT use Markdown (#, ##, **bold**, *italic*). IMPORTANT: Do NOT add a References or Bibliography section - it is created AUTOMATICALLY from \\cite{} commands. Example: \\section{Introduction}\\nThis paper explores..."
                    },
                    "paper_type": {
                        "type": "string",
                        "description": "Type of paper: 'literature_review', 'research', 'summary', 'notes'",
                        "default": "research"
                    },
                    "abstract": {
                        "type": "string",
                        "description": "Optional abstract/summary of the paper"
                    }
                },
                "required": ["title", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_paper",
            "description": "Update an existing paper's content. Content MUST be in LaTeX format! Use section_name to replace a SPECIFIC section (e.g., 'Conclusion'), or append=True to add NEW sections at the end.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "string",
                        "description": "ID of the paper to update (get from get_project_papers)"
                    },
                    "content": {
                        "type": "string",
                        "description": "New content in LATEX FORMAT. Use \\section{}, \\subsection{}, \\textbf{}, \\cite{}, etc. NOT Markdown. NEVER include \\end{document} or a References/Bibliography section - both are handled automatically."
                    },
                    "section_name": {
                        "type": "string",
                        "description": "Name of section to REPLACE (e.g., 'Conclusion', 'Introduction', 'Methods'). Content should be the section only (from \\section{Name} to the content, NOT including \\end{document} or bibliography). Use for 'extend/expand/rewrite section X' requests."
                    },
                    "append": {
                        "type": "boolean",
                        "description": "True = add content at end (for NEW sections). Ignored if section_name is provided.",
                        "default": True
                    }
                },
                "required": ["paper_id", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_artifact",
            "description": "Create a downloadable artifact (document, summary, review) that doesn't get saved to the project. Use when user wants content they can download without cluttering their project papers. Good for literature reviews, summaries, exports.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title/filename for the artifact"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content of the artifact (markdown or LaTeX format)"
                    },
                    "format": {
                        "type": "string",
                        "description": "Format of the artifact: 'markdown', 'latex', 'text', or 'pdf'. Use 'pdf' when user asks for PDF.",
                        "enum": ["markdown", "latex", "text", "pdf"],
                        "default": "markdown"
                    },
                    "artifact_type": {
                        "type": "string",
                        "description": "Type of artifact: 'literature_review', 'summary', 'notes', 'export', 'report'",
                        "default": "document"
                    }
                },
                "required": ["title", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_created_artifacts",
            "description": "Get artifacts (PDFs, documents) that were created in this discussion channel. Use when user asks about 'the PDF I created', 'the file you generated', 'my artifacts', or refers to previously created downloadable content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of artifacts to return",
                        "default": 10
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "discover_topics",
            "description": "Search the web to discover what specific topics/algorithms/methods exist for a broad area. Use when user asks about 'recent X', 'latest trends', 'new algorithms in Y', or vague topics where you don't know what specific things to search for. Returns a list of specific topics you can then search papers for.",
            "parameters": {
                "type": "object",
                "properties": {
                    "area": {
                        "type": "string",
                        "description": "The broad area to discover topics in (e.g., 'AI algorithms 2025', 'computer vision advances 2025', 'NLP breakthroughs')"
                    }
                },
                "required": ["area"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "batch_search_papers",
            "description": "Search for papers on MULTIPLE specific topics at once. Use after discover_topics to search for papers on each discovered topic. Returns papers grouped by topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "description": "List of topics to search for",
                        "items": {
                            "type": "object",
                            "properties": {
                                "topic": {"type": "string", "description": "Display name for the topic"},
                                "query": {"type": "string", "description": "Academic search query for this topic"},
                                "max_results": {"type": "integer", "description": "Max papers per topic", "default": 5}
                            },
                            "required": ["topic", "query"]
                        }
                    }
                },
                "required": ["topics"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_library",
            "description": "Add papers from recent search results to the project library AND ingest their PDFs for full-text AI analysis. IMPORTANT: Use this BEFORE creating a paper so you have full PDF content, not just abstracts. Returns which papers were added and their ingestion status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Indices of papers from recent search results to add (0-based). Use [0,1,2,3,4] to add first 5 papers."
                    },
                    "ingest_pdfs": {
                        "type": "boolean",
                        "description": "Whether to download and ingest PDFs for AI analysis. Default true.",
                        "default": True
                    }
                },
                "required": ["paper_indices"]
            }
        }
    }
]

# System prompt with adaptive workflow based on request clarity
BASE_SYSTEM_PROMPT = """You are a research assistant helping with academic papers.

TOOLS:
- discover_topics: Find what specific topics exist in a broad area (use for vague requests like "recent algorithms")
- search_papers: Search for academic papers on a SPECIFIC topic
- batch_search_papers: Search multiple specific topics at once (grouped results)
- get_recent_search_results: Get papers from last search (for "these papers", "use them")
- add_to_library: Add search results to library AND ingest PDFs (USE BEFORE create_paper!)
- get_project_references: Get user's saved papers (for "my library")
- get_reference_details: Get full content of an ingested reference
- get_project_papers: Get user's draft papers in this project
- create_paper: Create a new paper IN THE PROJECT (LaTeX editor)
- create_artifact: Create downloadable content (doesn't save to project)
- get_created_artifacts: Get previously created artifacts (PDFs, documents) in this channel
- update_paper: Add content to an existing paper
- update_project_info: Update project description and/or objectives (use for "add objective", "update description", "change goals")

WORKFLOW - Choose based on request clarity:

**CLEAR REQUEST** (user mentions specific topic):
  Examples: "papers about BERT", "diffusion models 2025", "federated learning"
  → Call search_papers directly with proper academic terms
  → Show results → ask to create paper → create with found references

**DISCOVERY NEEDED** (user mentions broad/vague area):
  Examples: "recent algorithms in 2025", "latest AI trends", "new methods in NLP"
  → Call discover_topics to find specific topics
  → Show discovered topics: "Found: [Topic1, Topic2, ...]. Search all or pick specific ones?"
  → User confirms → call batch_search_papers for selected topics
  → Show grouped results → create paper using those references

**AMBIGUOUS REQUEST** (missing key info):
  Examples: "write a literature review", "find me some papers"
  → Ask ONE brief question: "On what topic?" or "What area?"
  → After user answers → proceed to CLEAR or DISCOVERY workflow

CRITICAL RULES:
1. NEVER create a paper before having FULL PDF CONTEXT - search → add_to_library → read content → THEN create
2. NEVER ask more than ONE clarifying question
3. NEVER use user's literal words as search query - use proper academic terms
4. NEVER list papers from your training data - you don't have access to real papers!
5. Use discover_topics when you don't know what specific things to search for
6. When displaying paper content in chat, output it as plain markdown (NOT in code blocks) so it renders naturally with proper headings, bold text, etc.
7. NEVER add \\section*{{References}} or \\begin{{thebibliography}} - the References section is created AUTOMATICALLY from \\cite{{}} commands. Just use \\cite{{author2023keyword}} in your text.
8. For LONG content (literature reviews, full papers, multi-section documents):
   - Do NOT write the full content in chat - it's too slow
   - Instead ASK: "Would you like me to create this as a paper in your project? That way you can edit it in the LaTeX editor."
   - If user confirms, use create_paper tool with the content
   - Only provide SHORT summaries (1-2 paragraphs) directly in chat
9. NEVER show IDs (UUIDs, paper_id, artifact_id, etc.) to users - they are meaningless to humans. Just show titles and relevant info.
10. ALWAYS confirm what you created by NAME after using create_paper or create_artifact. Example: "I created a paper titled 'Literature Review: AI in Healthcare' in your project." or "I generated a PDF: 'Drug Discovery Summary.pdf'"
11. To see artifacts you previously created (PDFs, documents), use get_created_artifacts. To see papers you created, use get_project_papers.
12. PAPER CREATION WORKFLOW (REQUIRED for quality papers):
    a) Search for papers (search_papers or batch_search_papers)
    b) Add to library with PDF ingestion: add_to_library(paper_indices=[0,1,2...], ingest_pdfs=True)
    c) Read full content: get_reference_details for each ingested reference
    d) THEN create paper with deep understanding from full PDF content
    This ensures your paper is based on actual paper content, not just abstracts!
13. PROJECT OBJECTIVES: Each objective should be concise (max ~150 chars). Use update_project_info with:
    - objectives_mode="append" to ADD new objectives to existing ones
    - objectives_mode="remove" to REMOVE specific objectives (by index like "1", "2" or text match)
    - objectives_mode="replace" to REPLACE all objectives (use for COMPLEX edits!)

    **COMPLEX EDITS** (remove some + reword some + add new): Use "replace" mode!
    1. Look at current objectives in the Project Overview above
    2. Apply ALL changes (removals, rewordings, additions) to create the final list
    3. Call update_project_info(objectives=[...final list...], objectives_mode="replace")

    Example: User says "remove first two, reword third, add 2 more"
    Current: ["Obj A", "Obj B", "Obj C", "Obj D"]
    → Final: ["Reworded Obj C", "Obj D", "New Obj 1", "New Obj 2"]
    → Call: update_project_info(objectives=["Reworded Obj C", "Obj D", "New Obj 1", "New Obj 2"], objectives_mode="replace")

**WHEN USER CONFIRMS TOPICS OR REQUESTS A SEARCH:**
- You MUST call the search_papers or batch_search_papers tool!
- Say "Searching for papers on [topics]..." and call the tool
- The search results will appear automatically in the chat - you don't receive them directly
- After calling the search tool, just confirm: "I've initiated the search. The papers will appear below."

**AFTER showing topics + user confirms:**
User: "all 6 please" or "search all" or "yes"
→ Call batch_search_papers with the topics you listed
→ Format your response like: "Searching for papers on Vision Transformers, RLHF, etc. The results will appear below."
→ Construct the tool call with topics array like this:
   batch_search_papers(topics=[
     {{"topic": "Diffusion Models", "query": "diffusion models 2025"}},
     {{"topic": "RLHF", "query": "reinforcement learning human feedback 2025"}},
     ...
   ])

IMPORTANT: search_papers and batch_search_papers TRIGGER searches - they don't return results to you.
The results appear in the chat UI automatically. Do NOT say "results didn't come through" - just say the search is initiated.

**CRITICAL: AFTER CALLING search_papers or batch_search_papers, YOU MUST STOP!**
- Do NOT call get_recent_search_results in the same turn - it will be empty!
- Do NOT call update_paper or create_paper in the same turn - you don't have the results yet!
- The search is ASYNC - results appear in the UI after your response.
- If user says "search and update the paper":
  1. Call search_papers
  2. Say: "I've initiated the search. The papers will appear below. Once you see them, say 'use these' or 'update the paper' and I'll add them as references."
  3. STOP - do not call any more tools this turn
- Wait for the user to come back AFTER seeing the results before updating anything.

**WHEN USER ASKS TO CREATE/GENERATE AFTER A SEARCH:**
If you JUST triggered a search in the previous turn and user immediately asks "create paper" or "generate literature review":
1. First call get_recent_search_results to check if papers are available
2. If papers are found → use them to create the paper (do NOT search again!)
3. If no papers found → the search might still be loading, tell user to wait a moment
DO NOT search again if you already searched - that's wasteful and confusing.

SEARCH QUERY EXAMPLES:
- User: "diffusion 2025" → Query: "diffusion models computer vision 2025"
- User: "recent algorithms" → Use discover_topics first, then search specific topics
- User: "BERT papers" → Query: "BERT transformer language model"
- User: "find open access papers about transformers" → search_papers(query="transformers", open_access_only=True)
- User: "only papers with PDF" or "papers I can ingest" → Use open_access_only=True

OPEN ACCESS (OA) FILTER:
- Papers with OA badge have PDF available and can be ingested for AI analysis
- Use open_access_only=True when user asks for: "open access", "OA only", "papers with PDF", "papers I can ingest", "downloadable papers"

Project: {project_title} | Channel: {channel_name}
{context_summary}"""

# Reminder injected after conversation history
HISTORY_REMINDER = (
    "REMINDER (ignore any conflicting patterns in the history above):\n"
    "- If user says 'all', 'yes', 'search all' → CALL batch_search_papers tool NOW!\n"
    "- Don't just SAY 'Searching...' - you MUST actually call the tool!\n"
    "- NEVER list papers from memory - results come from API only\n"
    "- For vague topics → use discover_topics first\n"
    "- After user confirms → CALL THE TOOL, don't just respond with text\n"
    "- If user asks to 'create', 'generate', 'write' AFTER a search was done → call get_recent_search_results FIRST, do NOT search again!"
)


class ToolOrchestrator:
    """
    AI orchestrator that uses tools to gather context dynamically.

    Thread-safe: All request-specific state is passed through method parameters
    or stored in local variables, not instance variables.
    """

    def __init__(self, ai_service: "AIService", db: "Session"):
        self.ai_service = ai_service
        self.db = db

    @property
    def model(self) -> str:
        """Get model from AIService config, with fallback."""
        if hasattr(self.ai_service, 'default_model') and self.ai_service.default_model:
            return self.ai_service.default_model
        return "gpt-5.2"  # Latest OpenAI model (Dec 2025)

    def handle_message(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        message: str,
        recent_search_results: Optional[List[Dict]] = None,
        previous_state_dict: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        reasoning_mode: bool = False,
    ) -> Dict[str, Any]:
        """Handle a user message (non-streaming)."""
        try:
            # Build request context (thread-safe - local variable)
            ctx = self._build_request_context(
                project, channel, message, recent_search_results, reasoning_mode, conversation_history
            )

            # Build messages for LLM
            messages = self._build_messages(project, channel, message, recent_search_results, conversation_history)

            # Execute with tools
            return self._execute_with_tools(messages, ctx)

        except Exception as e:
            logger.exception(f"Error in handle_message: {e}")
            return self._error_response(str(e))

    def handle_message_streaming(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        message: str,
        recent_search_results: Optional[List[Dict]] = None,
        previous_state_dict: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        reasoning_mode: bool = False,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Handle a user message with streaming response.

        Yields:
            dict: Either {"type": "token", "content": "..."} for content tokens,
                  or {"type": "result", "data": {...}} at the end with full response.
        """
        try:
            # Build request context (thread-safe - local variable)
            ctx = self._build_request_context(
                project, channel, message, recent_search_results, reasoning_mode, conversation_history
            )

            # Build messages for LLM
            messages = self._build_messages(project, channel, message, recent_search_results, conversation_history)

            # Execute with streaming
            yield from self._execute_with_tools_streaming(messages, ctx)

        except Exception as e:
            logger.exception(f"Error in handle_message_streaming: {e}")
            yield {"type": "result", "data": self._error_response(str(e))}

    def _build_request_context(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        message: str,
        recent_search_results: Optional[List[Dict]],
        reasoning_mode: bool,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Build thread-safe request context."""
        import re

        # Extract count from message (e.g., "find 5 papers" → 5)
        count_match = re.search(r"(\d+)\s*(?:papers?|references?|articles?)", message, re.IGNORECASE)
        extracted_count = int(count_match.group(1)) if count_match else None

        return {
            "project": project,
            "channel": channel,
            "recent_search_results": recent_search_results or [],
            "reasoning_mode": reasoning_mode,
            "max_papers": extracted_count if extracted_count else 999,
            "papers_requested": 0,
            "user_message": message,  # Store for memory update
            "conversation_history": conversation_history or [],  # Store for memory update
        }

    def _build_messages(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        message: str,
        recent_search_results: Optional[List[Dict]],
        conversation_history: Optional[List[Dict[str, str]]],
    ) -> List[Dict]:
        """Build the messages array for the LLM with smart memory management."""
        context_summary = self._build_context_summary(project, channel, recent_search_results)

        # Build memory context from AI memory (summary + facts)
        memory_context = self._build_memory_context(channel)

        # Combine context and memory
        full_context = context_summary
        if memory_context:
            full_context = f"{context_summary}\n\n{memory_context}"

        system_prompt = BASE_SYSTEM_PROMPT.format(
            project_title=project.title,
            channel_name=channel.name,
            context_summary=full_context,
        )

        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history with sliding window
        if conversation_history:
            # Use sliding window: keep last SLIDING_WINDOW_SIZE messages in full
            window_messages = conversation_history[-self.SLIDING_WINDOW_SIZE:]
            for msg in window_messages:
                messages.append({"role": msg["role"], "content": msg["content"]})

            # Add reminder after history to override old patterns
            messages.append({"role": "system", "content": HISTORY_REMINDER})

        messages.append({"role": "user", "content": message})
        return messages

    def _error_response(self, error_msg: str = "") -> Dict[str, Any]:
        """Build a standard error response."""
        return {
            "message": "I'm sorry, I encountered an error while processing your request. Please try again.",
            "actions": [],
            "citations": [],
            "model_used": self.model,
            "reasoning_used": False,
            "tools_called": [],
            "conversation_state": {},
        }

    def _get_tool_status_message(self, tool_name: str) -> str:
        """Return a human-readable status message for a tool being called."""
        tool_messages = {
            "get_recent_search_results": "Reviewing search results",
            "get_project_references": "Checking your library",
            "get_reference_details": "Reading paper details",
            "analyze_reference": "Analyzing paper content",
            "search_papers": "Searching for papers",
            "get_project_papers": "Loading your drafts",
            "get_project_info": "Getting project info",
            "get_channel_resources": "Checking channel resources",
            "create_paper": "Creating paper",
            "update_paper": "Updating paper",
            "create_artifact": "Generating document",
            "discover_topics": "Discovering topics",
            "batch_search_papers": "Searching multiple topics",
            "add_to_library": "Adding papers to library & ingesting PDFs",
            "update_project_info": "Updating project info",
        }
        return tool_messages.get(tool_name, "Processing")

    def _execute_with_tools_streaming(
        self,
        messages: List[Dict],
        ctx: Dict[str, Any],
    ) -> Generator[Dict[str, Any], None, None]:
        """Execute with tool calling and streaming."""
        max_iterations = 5
        iteration = 0
        all_tool_results = []
        accumulated_content = []

        print(f"\n[STREAMING] Starting tool execution with model: {self.model}\n")

        while iteration < max_iterations:
            iteration += 1
            print(f"\n[STREAMING] Tool orchestrator iteration {iteration}\n")

            # Stream the AI response
            response_content = ""
            tool_calls = []

            for event in self._call_ai_with_tools_streaming(messages):
                if event["type"] == "token":
                    accumulated_content.append(event["content"])
                    yield event  # Stream token to client
                elif event["type"] == "result":
                    response_content = event["content"]
                    tool_calls = event.get("tool_calls", [])

            print(f"\n[STREAMING] AI returned {len(tool_calls)} tool calls: {[tc.get('name') for tc in tool_calls]}\n")

            if not tool_calls:
                # No more tool calls, we're done
                print("\n[STREAMING] No tool calls, finishing\n")
                break

            # Send status event for each tool call so frontend can show dynamic loading
            for tc in tool_calls:
                tool_name = tc.get("name", "")
                status_message = self._get_tool_status_message(tool_name)
                yield {"type": "status", "tool": tool_name, "message": status_message}

            # Execute tool calls (not streamed, but usually fast)
            tool_results = self._execute_tool_calls(tool_calls, ctx)
            all_tool_results.extend(tool_results)

            # Add assistant message with tool calls
            formatted_tool_calls = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]),
                    }
                }
                for tc in tool_calls
            ]

            messages.append({
                "role": "assistant",
                "content": response_content or "",
                "tool_calls": formatted_tool_calls,
            })

            # Add tool results
            for tool_call, result in zip(tool_calls, tool_results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, default=str),
                })

        # Build final result
        final_message = "".join(accumulated_content)
        print(f"\n[STREAMING] All tool results: {all_tool_results}\n")
        actions = self._extract_actions(final_message, all_tool_results)
        print(f"\n[STREAMING] Extracted actions: {actions}\n")

        # Update AI memory after successful response
        contradiction_warning = None
        try:
            contradiction_warning = self.update_memory_after_exchange(
                ctx["channel"],
                ctx["user_message"],
                final_message,
                ctx.get("conversation_history", []),
            )
            if contradiction_warning:
                logger.info(f"Contradiction detected: {contradiction_warning}")
        except Exception as mem_err:
            logger.error(f"Failed to update AI memory: {mem_err}")

        yield {
            "type": "result",
            "data": {
                "message": final_message,
                "actions": actions,
                "citations": [],
                "model_used": self.model,
                "reasoning_used": ctx.get("reasoning_mode", False),
                "tools_called": [t["name"] for t in all_tool_results] if all_tool_results else [],
                "conversation_state": {},
                "memory_warning": contradiction_warning,  # Include contradiction warning
            }
        }

    def _execute_with_tools(
        self,
        messages: List[Dict],
        ctx: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute with tool calling (non-streaming)."""
        try:
            max_iterations = 5
            iteration = 0
            all_tool_results = []
            response = {"content": "", "tool_calls": []}

            while iteration < max_iterations:
                iteration += 1
                logger.info(f"Tool orchestrator iteration {iteration}")

                response = self._call_ai_with_tools(messages)
                tool_calls = response.get("tool_calls", [])

                if not tool_calls:
                    break

                # Execute tool calls
                tool_results = self._execute_tool_calls(tool_calls, ctx)
                all_tool_results.extend(tool_results)

                # Add assistant message with tool calls
                formatted_tool_calls = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        }
                    }
                    for tc in tool_calls
                ]

                messages.append({
                    "role": "assistant",
                    "content": response.get("content") or "",
                    "tool_calls": formatted_tool_calls,
                })

                # Add tool results
                for tool_call, result in zip(tool_calls, tool_results):
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result, default=str),
                    })

            final_message = response.get("content", "")
            actions = self._extract_actions(final_message, all_tool_results)

            # Update AI memory after successful response (async in background)
            contradiction_warning = None
            try:
                contradiction_warning = self.update_memory_after_exchange(
                    ctx["channel"],
                    ctx["user_message"],
                    final_message,
                    ctx.get("conversation_history", []),
                )
                if contradiction_warning:
                    logger.info(f"Contradiction detected: {contradiction_warning}")
            except Exception as mem_err:
                logger.error(f"Failed to update AI memory: {mem_err}")

            return {
                "message": final_message,
                "actions": actions,
                "citations": [],
                "model_used": self.model,
                "reasoning_used": ctx.get("reasoning_mode", False),
                "tools_called": [t["name"] for t in all_tool_results] if all_tool_results else [],
                "conversation_state": {},
                "memory_warning": contradiction_warning,  # Include contradiction warning
            }

        except Exception as e:
            logger.exception(f"Error in _execute_with_tools: {e}")
            return self._error_response(str(e))

    def _build_context_summary(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        recent_search_results: Optional[List[Dict]],
    ) -> str:
        """Build a lightweight summary of available context."""
        from app.models import ProjectReference, ResearchPaper, ProjectDiscussionChannelResource, ProjectDiscussionTask

        lines = []

        # Project info - always include so AI knows the context
        lines.append("## Project Overview")
        lines.append(f"**Title:** {project.title or 'Untitled Project'}")
        if project.idea:
            # Truncate long descriptions
            idea_preview = project.idea[:500] + "..." if len(project.idea) > 500 else project.idea
            lines.append(f"**Description:** {idea_preview}")
        if project.scope:
            lines.append(f"**Objectives:** {project.scope}")
        if project.keywords:
            lines.append(f"**Keywords:** {project.keywords}")
        lines.append("")  # Empty line separator

        # Discussion tasks - show open and in-progress tasks
        active_tasks = self.db.query(ProjectDiscussionTask).filter(
            ProjectDiscussionTask.project_id == project.id,
            ProjectDiscussionTask.status.in_(["open", "in_progress"])
        ).order_by(ProjectDiscussionTask.created_at.desc()).limit(10).all()

        if active_tasks:
            lines.append("## Active Tasks")
            for task in active_tasks:
                status_icon = "🔄" if task.status == "in_progress" else "📋"
                due_str = f" (due: {task.due_date.strftime('%Y-%m-%d')})" if task.due_date else ""
                lines.append(f"- {status_icon} **{task.title}**{due_str}")
                if task.description:
                    desc_preview = task.description[:100] + "..." if len(task.description) > 100 else task.description
                    lines.append(f"  {desc_preview}")
            lines.append("")  # Empty line separator

        lines.append("## Available Resources")

        # Count project references
        ref_count = self.db.query(ProjectReference).filter(
            ProjectReference.project_id == project.id
        ).count()
        if ref_count > 0:
            lines.append(f"- Project library: {ref_count} saved references")

        # Count project papers
        paper_count = self.db.query(ResearchPaper).filter(
            ResearchPaper.project_id == project.id
        ).count()
        if paper_count > 0:
            lines.append(f"- Project papers: {paper_count} drafts")

        # Recent search results - show what's available
        if recent_search_results:
            lines.append(f"- Recent search results: {len(recent_search_results)} papers available:")
            for i, p in enumerate(recent_search_results[:5], 1):
                title = p.get("title", "Untitled")[:60]
                year = p.get("year", "")
                lines.append(f"    {i}. {title}{'...' if len(p.get('title', '')) > 60 else ''} ({year})")

        # Channel resources
        resource_count = self.db.query(ProjectDiscussionChannelResource).filter(
            ProjectDiscussionChannelResource.channel_id == channel.id
        ).count()
        if resource_count > 0:
            lines.append(f"- Channel resources: {resource_count} attached")

        # If no resources at all, add a note
        if ref_count == 0 and paper_count == 0 and not recent_search_results and resource_count == 0:
            lines.append("- No papers or references loaded yet")

        return "\n".join(lines)

    def _call_ai_with_tools(self, messages: List[Dict]) -> Dict[str, Any]:
        """Call OpenAI with tool definitions (non-streaming)."""
        try:
            client = self.ai_service.openai_client

            if not client:
                return {"content": "AI service not configured. Please check your OpenAI API key.", "tool_calls": []}

            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=DISCUSSION_TOOLS,
                tool_choice="auto",
            )

            choice = response.choices[0]
            message = choice.message

            result = {
                "content": message.content or "",
                "tool_calls": [],
            }

            if message.tool_calls:
                for tc in message.tool_calls:
                    result["tool_calls"].append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    })

            return result

        except Exception as e:
            logger.exception("Error calling AI with tools")
            return {"content": f"Error: {str(e)}", "tool_calls": []}

    def _call_ai_with_tools_streaming(self, messages: List[Dict]) -> Generator[Dict[str, Any], None, None]:
        """Call OpenAI with tool definitions (streaming)."""
        try:
            client = self.ai_service.openai_client

            if not client:
                yield {"type": "result", "content": "AI service not configured.", "tool_calls": []}
                return

            stream = client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=DISCUSSION_TOOLS,
                tool_choice="auto",
                stream=True,
            )

            content_chunks = []
            tool_calls_data = {}  # {index: {"id": ..., "name": ..., "arguments": ...}}

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # Handle content tokens
                if delta.content:
                    content_chunks.append(delta.content)
                    yield {"type": "token", "content": delta.content}

                # Handle tool calls (accumulated across chunks)
                if delta.tool_calls:
                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {"id": "", "name": "", "arguments": ""}

                        if tc_chunk.id:
                            tool_calls_data[idx]["id"] = tc_chunk.id
                        if tc_chunk.function:
                            if tc_chunk.function.name:
                                tool_calls_data[idx]["name"] = tc_chunk.function.name
                            if tc_chunk.function.arguments:
                                tool_calls_data[idx]["arguments"] += tc_chunk.function.arguments

            # Parse accumulated tool calls
            tool_calls = []
            for idx in sorted(tool_calls_data.keys()):
                tc = tool_calls_data[idx]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "id": tc["id"],
                    "name": tc["name"],
                    "arguments": args,
                })

            yield {
                "type": "result",
                "content": "".join(content_chunks),
                "tool_calls": tool_calls,
            }

        except Exception as e:
            logger.exception("Error in streaming AI call with tools")
            yield {"type": "result", "content": f"Error: {str(e)}", "tool_calls": []}

    def _execute_tool_calls(self, tool_calls: List[Dict], ctx: Dict[str, Any]) -> List[Dict]:
        """Execute the tool calls and return results."""
        results = []

        for tc in tool_calls:
            name = tc["name"]
            args = tc["arguments"]

            logger.info(f"Executing tool: {name} with args: {args}")

            try:
                # Enforce paper limit for search_papers
                if name == "search_papers":
                    max_papers = ctx.get("max_papers", 100)
                    papers_so_far = ctx.get("papers_requested", 0)
                    requested_count = args.get("count", 1)

                    if papers_so_far >= max_papers:
                        logger.debug(f"Paper limit reached: {papers_so_far}/{max_papers}")
                        result = {
                            "status": "blocked",
                            "message": f"Paper limit reached ({max_papers}). No more searches.",
                        }
                        results.append({"name": name, "result": result})
                        continue

                    # Reduce count if it would exceed limit
                    remaining = max_papers - papers_so_far
                    if requested_count > remaining:
                        args["count"] = remaining
                        logger.debug(f"Reduced search count from {requested_count} to {remaining}")

                    # Track papers requested
                    ctx["papers_requested"] = papers_so_far + args.get("count", 1)

                # Check cache for cacheable tools
                channel = ctx.get("channel")
                cached_result = None
                if name in {"get_project_references", "get_project_papers"} and channel:
                    cached_result = self.get_cached_tool_result(channel, name, max_age_seconds=300)
                    if cached_result:
                        logger.info(f"Using cached result for {name}")
                        results.append({"name": name, "result": cached_result})
                        continue

                # Route to appropriate tool handler
                if name == "get_recent_search_results":
                    result = self._tool_get_recent_search_results(ctx)
                elif name == "get_project_references":
                    result = self._tool_get_project_references(ctx, **args)
                    # Cache the result
                    if channel and result.get("count", 0) > 0:
                        self.cache_tool_result(channel, name, result)
                elif name == "get_reference_details":
                    result = self._tool_get_reference_details(ctx, **args)
                elif name == "analyze_reference":
                    result = self._tool_analyze_reference(ctx, **args)
                elif name == "search_papers":
                    result = self._tool_search_papers(**args)
                elif name == "get_project_papers":
                    result = self._tool_get_project_papers(ctx, **args)
                    # Cache the result
                    if channel and result.get("count", 0) > 0:
                        self.cache_tool_result(channel, name, result)
                elif name == "get_project_info":
                    result = self._tool_get_project_info(ctx)
                elif name == "get_channel_resources":
                    result = self._tool_get_channel_resources(ctx)
                elif name == "create_paper":
                    result = self._tool_create_paper(ctx, **args)
                elif name == "update_paper":
                    result = self._tool_update_paper(ctx, **args)
                elif name == "create_artifact":
                    result = self._tool_create_artifact(ctx, **args)
                elif name == "get_created_artifacts":
                    result = self._tool_get_created_artifacts(ctx, **args)
                elif name == "discover_topics":
                    result = self._tool_discover_topics(**args)
                elif name == "batch_search_papers":
                    result = self._tool_batch_search_papers(**args)
                elif name == "add_to_library":
                    result = self._tool_add_to_library(ctx, **args)
                elif name == "update_project_info":
                    result = self._tool_update_project_info(ctx, **args)
                else:
                    result = {"error": f"Unknown tool: {name}"}

                results.append({"name": name, "result": result})

            except Exception as e:
                logger.exception(f"Error executing tool {name}")
                results.append({"name": name, "error": str(e)})

        return results

    # -------------------------------------------------------------------------
    # Tool Implementations
    # -------------------------------------------------------------------------

    def _tool_get_recent_search_results(self, ctx: Dict[str, Any]) -> Dict:
        """Get papers from the most recent search."""
        recent = ctx.get("recent_search_results", [])

        if not recent:
            return {
                "count": 0,
                "papers": [],
                "message": "No recent search results available. The user may need to search for papers first."
            }

        return {
            "count": len(recent),
            "papers": [
                {
                    "title": p.get("title", "Untitled"),
                    "authors": p.get("authors", "Unknown"),
                    "year": p.get("year"),
                    "source": p.get("source", ""),
                    "abstract": p.get("abstract", "")[:500] if p.get("abstract") else "",
                    "doi": p.get("doi"),
                    "url": p.get("url"),
                }
                for p in recent
            ],
            "message": f"Found {len(recent)} papers from the recent search."
        }

    def _tool_get_project_references(
        self,
        ctx: Dict[str, Any],
        topic_filter: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict:
        """Get references from project library."""
        from app.models import ProjectReference, Reference

        project = ctx["project"]

        query = self.db.query(Reference).join(
            ProjectReference,
            ProjectReference.reference_id == Reference.id
        ).filter(
            ProjectReference.project_id == project.id
        )

        if topic_filter:
            from sqlalchemy import func, cast
            from sqlalchemy.dialects.postgresql import ARRAY
            # Search in title, abstract, and authors (authors is an array, so convert to string)
            query = query.filter(
                Reference.title.ilike(f"%{topic_filter}%") |
                Reference.abstract.ilike(f"%{topic_filter}%") |
                func.array_to_string(Reference.authors, ' ').ilike(f"%{topic_filter}%")
            )

        if limit:
            references = query.limit(limit).all()
        else:
            references = query.all()

        # Count references with ingested PDFs
        ingested_count = sum(1 for ref in references if ref.status in ("ingested", "analyzed"))
        has_pdf_count = sum(1 for ref in references if ref.pdf_url or ref.is_open_access)

        papers_list = []
        for ref in references:
            paper_info = {
                "id": str(ref.id),
                "title": ref.title,
                "authors": ref.authors if isinstance(ref.authors, str) else ", ".join(ref.authors or []),
                "year": ref.year,
                "abstract": (ref.abstract or "")[:300],
                "source": ref.source,
                "has_pdf": bool(ref.pdf_url),
                "is_open_access": bool(ref.is_open_access),
                "pdf_ingested": ref.status in ("ingested", "analyzed"),
            }

            # Include analysis fields if the PDF was ingested
            if ref.status in ("ingested", "analyzed"):
                if ref.summary:
                    paper_info["summary"] = ref.summary
                if ref.key_findings:
                    paper_info["key_findings"] = ref.key_findings
                if ref.methodology:
                    paper_info["methodology"] = ref.methodology[:500] if ref.methodology else None
                if ref.limitations:
                    paper_info["limitations"] = ref.limitations

            papers_list.append(paper_info)

        return {
            "count": len(references),
            "ingested_pdf_count": ingested_count,
            "has_pdf_available_count": has_pdf_count,
            "papers": papers_list,
        }

    def _tool_get_reference_details(self, ctx: Dict[str, Any], reference_id: str) -> Dict:
        """Get detailed information about a specific reference by ID."""
        from app.models import ProjectReference, Reference, Document

        project = ctx["project"]

        # Find the reference in the project library
        ref = self.db.query(Reference).join(
            ProjectReference,
            ProjectReference.reference_id == Reference.id
        ).filter(
            ProjectReference.project_id == project.id,
            Reference.id == reference_id
        ).first()

        if not ref:
            return {"error": f"Reference not found in project library (ID: {reference_id})"}

        # Build detailed response
        result = {
            "id": str(ref.id),
            "title": ref.title,
            "authors": ref.authors if isinstance(ref.authors, str) else ", ".join(ref.authors or []),
            "year": ref.year,
            "doi": ref.doi,
            "url": ref.url,
            "source": ref.source,
            "journal": ref.journal,
            "abstract": ref.abstract,
            "has_pdf": bool(ref.pdf_url),
            "is_open_access": bool(ref.is_open_access),
            "pdf_url": ref.pdf_url,
            "status": ref.status,
            "pdf_ingested": ref.status in ("ingested", "analyzed"),
        }

        # Include analysis fields if the PDF was ingested
        if ref.status in ("ingested", "analyzed"):
            result["analysis"] = {
                "summary": ref.summary,
                "key_findings": ref.key_findings,
                "methodology": ref.methodology,
                "limitations": ref.limitations,
                "relevance_score": ref.relevance_score,
            }

            # Try to get page count from the linked document
            if ref.document_id:
                doc = self.db.query(Document).filter(Document.id == ref.document_id).first()
                if doc:
                    result["page_count"] = doc.page_count if hasattr(doc, 'page_count') else None
                    # Could also include word count or other metadata if available

        return result

    def _tool_analyze_reference(self, ctx: Dict[str, Any], reference_id: str) -> Dict:
        """Re-analyze a reference to generate summary, key_findings, methodology, limitations."""
        from app.models import ProjectReference, Reference
        from app.models.document_chunk import DocumentChunk

        project = ctx["project"]

        # Find the reference in the project library
        ref = self.db.query(Reference).join(
            ProjectReference,
            ProjectReference.reference_id == Reference.id
        ).filter(
            ProjectReference.project_id == project.id,
            Reference.id == reference_id
        ).first()

        if not ref:
            return {"error": f"Reference not found in project library (ID: {reference_id})"}

        if not ref.document_id:
            return {"error": "This reference doesn't have an ingested PDF. Cannot analyze without PDF content."}

        # Build profile text from chunks
        chunks = self.db.query(DocumentChunk).filter(
            DocumentChunk.document_id == ref.document_id
        ).order_by(DocumentChunk.chunk_index).limit(8).all()

        if not chunks:
            return {"error": "No text content found for this reference's PDF."}

        profile_text = '\n'.join([c.chunk_text for c in chunks if c.chunk_text])

        if not profile_text:
            return {"error": "Extracted text is empty for this reference."}

        # Run AI analysis
        import os
        from openai import OpenAI

        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return {"error": "OpenAI API key not configured."}

        client = OpenAI(api_key=api_key)
        prompt = f"""Analyze this academic paper and provide a JSON response with the following fields:
- summary: A 2-3 sentence summary of the paper
- key_findings: An array of 3-5 key findings
- methodology: A 1-2 sentence description of the methodology
- limitations: An array of 2-3 limitations

Title: {ref.title or ''}

Text:
{profile_text[:6000]}

Respond ONLY with valid JSON, no markdown or explanation."""

        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.3
            )
            content = resp.choices[0].message.content or ''

            # Strip markdown code blocks if present
            import json
            import re
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if json_match:
                content = json_match.group(1)

            data = json.loads(content)
            ref.summary = data.get('summary')
            ref.key_findings = data.get('key_findings')
            ref.methodology = data.get('methodology')
            ref.limitations = data.get('limitations')
            ref.status = 'analyzed'
            self.db.commit()

            return {
                "status": "success",
                "message": f"Successfully analyzed '{ref.title}'",
                "analysis": {
                    "summary": ref.summary,
                    "key_findings": ref.key_findings,
                    "methodology": ref.methodology,
                    "limitations": ref.limitations,
                }
            }
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse AI response: {e}"}
        except Exception as e:
            logger.exception(f"Error analyzing reference {reference_id}")
            return {"error": f"Analysis failed: {str(e)}"}

    def _tool_search_papers(self, query: str, count: int = 5, open_access_only: bool = False) -> Dict:
        """Search for papers online - returns action for frontend to execute."""
        oa_note = " (Open Access only)" if open_access_only else ""
        return {
            "status": "success",
            "message": f"Searching for papers: '{query}'{oa_note}",
            "action": {
                "type": "search_references",
                "payload": {"query": query, "max_results": count, "open_access_only": open_access_only},
            },
        }

    def _tool_get_project_papers(self, ctx: Dict[str, Any], include_content: bool = False) -> Dict:
        """Get user's draft papers in the project."""
        from app.models import ResearchPaper

        project = ctx["project"]

        papers = self.db.query(ResearchPaper).filter(
            ResearchPaper.project_id == project.id
        ).all()

        result = {
            "count": len(papers),
            "papers": []
        }

        for paper in papers:
            paper_info = {
                "id": str(paper.id),
                "title": paper.title,
                "status": paper.status,
                "paper_type": paper.paper_type,
                "abstract": paper.abstract,
            }

            if include_content:
                # Get content from either plain content or LaTeX mode
                content = paper.content
                if not content and paper.content_json:
                    # LaTeX mode papers store content in content_json.latex_source
                    content = paper.content_json.get("latex_source", "")

                if content:
                    # Convert LaTeX to readable markdown for chat display
                    display_content = self._latex_to_markdown(content)
                    paper_info["content"] = display_content  # No truncation - show full content

            result["papers"].append(paper_info)

        return result

    def _latex_to_markdown(self, latex: str) -> str:
        """Convert LaTeX content to readable markdown for chat display."""
        import re

        # Remove document class and preamble
        content = re.sub(r'\\documentclass\{[^}]*\}', '', latex)
        content = re.sub(r'\\usepackage(\[[^\]]*\])?\{[^}]*\}', '', content)
        content = re.sub(r'\\title\{([^}]*)\}', r'# \1', content)
        content = re.sub(r'\\date\{[^}]*\}', '', content)
        content = re.sub(r'\\begin\{document\}', '', content)
        content = re.sub(r'\\end\{document\}', '', content)
        content = re.sub(r'\\maketitle', '', content)

        # Convert sections to markdown headers
        content = re.sub(r'\\section\{([^}]*)\}', r'\n## \1\n', content)
        content = re.sub(r'\\subsection\{([^}]*)\}', r'\n### \1\n', content)
        content = re.sub(r'\\subsubsection\{([^}]*)\}', r'\n#### \1\n', content)
        content = re.sub(r'\\paragraph\{([^}]*)\}', r'\n**\1**\n', content)

        # Convert abstract
        content = re.sub(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', r'\n**Abstract:** \1\n', content, flags=re.DOTALL)

        # Convert text formatting
        content = re.sub(r'\\textbf\{([^}]*)\}', r'**\1**', content)
        content = re.sub(r'\\textit\{([^}]*)\}', r'*\1*', content)
        content = re.sub(r'\\emph\{([^}]*)\}', r'*\1*', content)
        content = re.sub(r'\\underline\{([^}]*)\}', r'__\1__', content)

        # Convert lists
        content = re.sub(r'\\begin\{itemize\}', '', content)
        content = re.sub(r'\\end\{itemize\}', '', content)
        content = re.sub(r'\\begin\{enumerate\}', '', content)
        content = re.sub(r'\\end\{enumerate\}', '', content)
        content = re.sub(r'\\item\s*', '\n- ', content)

        # Convert citations and references
        content = re.sub(r'\\cite\{([^}]*)\}', r'[\1]', content)
        content = re.sub(r'\\ref\{([^}]*)\}', r'[\1]', content)
        content = re.sub(r'\\label\{[^}]*\}', '', content)

        # Clean up extra whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = content.strip()

        return content

    def _tool_get_project_info(self, ctx: Dict[str, Any]) -> Dict:
        """Get project information."""
        project = ctx["project"]

        return {
            "id": str(project.id),
            "title": project.title,
            "idea": project.idea or "",
            "scope": project.scope or "",
            "keywords": project.keywords or [],
            "status": project.status or "active",
        }

    def _tool_get_channel_resources(self, ctx: Dict[str, Any]) -> Dict:
        """Get resources attached to the current channel."""
        from app.models import ProjectDiscussionChannelResource

        channel = ctx["channel"]

        resources = self.db.query(ProjectDiscussionChannelResource).filter(
            ProjectDiscussionChannelResource.channel_id == channel.id
        ).all()

        return {
            "count": len(resources),
            "resources": [
                {
                    "id": str(res.id),
                    "type": res.resource_type.value if hasattr(res.resource_type, 'value') else str(res.resource_type),
                    "details": res.details or {},
                }
                for res in resources
            ]
        }

    def _link_cited_references(
        self,
        ctx: Dict[str, Any],
        paper_id: str,
        latex_content: str,
    ) -> Dict[str, Any]:
        r"""
        Parse citations from LaTeX content and link matching references to the paper.

        1. Extract \cite{} keys from content
        2. Match keys to recent_search_results AND project library references
        3. Create Reference entries (if not exist)
        4. Add to project library (ProjectReference)
        5. Link to paper (PaperReference)

        Returns summary of linked references.
        """
        import re
        from uuid import UUID
        from app.models import Reference, ProjectReference, PaperReference, ProjectReferenceStatus, ProjectReferenceOrigin

        project = ctx["project"]
        recent_search_results = ctx.get("recent_search_results", [])

        # Also get references from the project library
        project_refs = (
            self.db.query(Reference)
            .join(ProjectReference, ProjectReference.reference_id == Reference.id)
            .filter(ProjectReference.project_id == project.id)
            .all()
        )

        # Convert project library refs to same format as search results
        library_papers = []
        for ref in project_refs:
            library_papers.append({
                "title": ref.title,
                "authors": ref.authors if isinstance(ref.authors, str) else ", ".join(ref.authors or []),
                "year": ref.year,
                "doi": ref.doi,
                "url": ref.url,
                "source": ref.source,
                "journal": ref.journal,
                "abstract": ref.abstract,
                "is_open_access": ref.is_open_access,
                "pdf_url": ref.pdf_url,
                "_reference_id": str(ref.id),  # Track existing ref ID
            })

        # Combine recent search results with project library
        all_papers = recent_search_results + library_papers

        if not all_papers:
            return {"linked": 0, "message": "No references available to match against (no recent search results and no project library references)"}

        # Extract all citation keys from \cite{key1, key2} commands
        cite_pattern = r'\\cite\{([^}]+)\}'
        cite_matches = re.findall(cite_pattern, latex_content)

        # Flatten and clean citation keys
        citation_keys = set()
        for match in cite_matches:
            for key in match.split(','):
                citation_keys.add(key.strip())

        if not citation_keys:
            return {"linked": 0, "message": "No citations found in content"}

        # Build lookup from recent search results
        # Try to match citation keys (e.g., "vaswani2017attention") to papers
        def normalize_for_matching(text: str) -> str:
            """Normalize text for fuzzy matching."""
            return re.sub(r'[^a-z0-9]', '', text.lower())

        def get_author_year_key(paper: Dict) -> str:
            """Generate a citation-like key from paper info."""
            authors = paper.get("authors", "")
            if isinstance(authors, list):
                first_author = authors[0] if authors else "unknown"
            else:
                first_author = authors.split(",")[0].strip() if authors else "unknown"

            # Extract last name - handle both "LastName, Initial." and "First Last" formats
            if "," in first_author:
                # Format: "LastName, Initial." - take part before comma
                last_name = first_author.split(",")[0].strip()
            else:
                # Format: "First Last" - take last word
                last_name = first_author.split()[-1] if first_author else "unknown"
            year = str(paper.get("year", ""))

            # Get first significant word from title for disambiguation
            title = paper.get("title", "")
            title_words = [w for w in re.findall(r'[a-z]+', title.lower()) if len(w) > 3]
            title_word = title_words[0] if title_words else ""

            return normalize_for_matching(f"{last_name}{year}{title_word}")

        # Create lookup mapping from all available papers (search results + library)
        paper_lookup = {}
        for paper in all_papers:
            key = get_author_year_key(paper)
            paper_lookup[key] = paper
            # Also add by normalized title for fallback matching
            title_key = normalize_for_matching(paper.get("title", ""))
            if title_key:
                paper_lookup[title_key] = paper

        # Match citation keys to papers
        linked_count = 0
        linked_refs = []

        try:
            paper_uuid = UUID(paper_id)
        except ValueError:
            return {"linked": 0, "message": "Invalid paper ID"}

        for cite_key in citation_keys:
            normalized_key = normalize_for_matching(cite_key)

            # Try exact match first
            matched_paper = paper_lookup.get(normalized_key)

            # Try partial match if no exact match
            if not matched_paper:
                for lookup_key, paper in paper_lookup.items():
                    if normalized_key in lookup_key or lookup_key in normalized_key:
                        matched_paper = paper
                        break

            if not matched_paper:
                continue

            # Check if reference already exists
            doi = matched_paper.get("doi")
            title = matched_paper.get("title", "")

            existing_ref = None

            # First check if this came from project library (has _reference_id)
            if matched_paper.get("_reference_id"):
                from uuid import UUID as UUIDType
                try:
                    ref_uuid = UUIDType(matched_paper["_reference_id"])
                    existing_ref = self.db.query(Reference).filter(Reference.id == ref_uuid).first()
                except (ValueError, TypeError):
                    pass

            # Otherwise check by DOI or title
            if not existing_ref and doi:
                existing_ref = self.db.query(Reference).filter(
                    Reference.doi == doi,
                    Reference.owner_id == project.created_by
                ).first()

            if not existing_ref and title:
                existing_ref = self.db.query(Reference).filter(
                    Reference.title == title,
                    Reference.owner_id == project.created_by
                ).first()

            # Create Reference if not exists
            is_new_ref = False
            if not existing_ref:
                is_new_ref = True
                authors = matched_paper.get("authors", [])
                if isinstance(authors, str):
                    authors = [a.strip() for a in authors.split(",")]

                existing_ref = Reference(
                    owner_id=project.created_by,
                    title=title,
                    authors=authors,
                    year=matched_paper.get("year"),
                    doi=doi,
                    url=matched_paper.get("url"),
                    source=matched_paper.get("source", "ai_discovery"),
                    journal=matched_paper.get("journal"),
                    abstract=matched_paper.get("abstract"),
                    is_open_access=matched_paper.get("is_open_access", False),
                    pdf_url=matched_paper.get("pdf_url"),
                    status="pending",
                )
                self.db.add(existing_ref)
                self.db.flush()

            # NOTE: PDF ingestion is NOT triggered here to avoid:
            # 1. Slow paper creation (PDF download + embedding is expensive)
            # 2. Database session corruption if ingestion fails
            # Users can ingest PDFs later via the library UI or it happens via background tasks

            # Add to project library if not already there
            existing_project_ref = self.db.query(ProjectReference).filter(
                ProjectReference.project_id == project.id,
                ProjectReference.reference_id == existing_ref.id
            ).first()

            if not existing_project_ref:
                project_ref = ProjectReference(
                    project_id=project.id,
                    reference_id=existing_ref.id,
                    status=ProjectReferenceStatus.ACCEPTED,
                    origin=ProjectReferenceOrigin.AI_SUGGESTED,
                )
                self.db.add(project_ref)

            # Link to paper if not already linked
            existing_paper_ref = self.db.query(PaperReference).filter(
                PaperReference.paper_id == paper_uuid,
                PaperReference.reference_id == existing_ref.id
            ).first()

            if not existing_paper_ref:
                paper_ref = PaperReference(
                    paper_id=paper_uuid,
                    reference_id=existing_ref.id,
                )
                self.db.add(paper_ref)
                linked_count += 1
                linked_refs.append(title)

        self.db.commit()

        return {
            "linked": linked_count,
            "references": linked_refs[:5],  # Return first 5 for summary
            "message": f"Linked {linked_count} references to paper and project library"
        }

    def _tool_create_paper(
        self,
        ctx: Dict[str, Any],
        title: str,
        content: str,
        paper_type: str = "research",
        abstract: str = None,
    ) -> Dict:
        """Create a new paper in the project (always in LaTeX mode)."""
        from app.models import ResearchPaper

        project = ctx["project"]
        owner_id = project.created_by

        latex_source = self._ensure_latex_document(content, title, abstract)

        new_paper = ResearchPaper(
            title=title,
            content=None,
            content_json={
                "authoring_mode": "latex",
                "latex_source": latex_source,
            },
            abstract=abstract,
            paper_type=paper_type,
            status="draft",
            project_id=project.id,
            owner_id=owner_id,
        )

        self.db.add(new_paper)
        self.db.commit()
        self.db.refresh(new_paper)

        # Link cited references to paper and project library
        ref_result = self._link_cited_references(ctx, str(new_paper.id), latex_source)
        ref_message = f" {ref_result['message']}" if ref_result.get("linked", 0) > 0 else ""

        return {
            "status": "success",
            "message": f"Created paper '{title}' in the project.{ref_message}",
            "paper_id": str(new_paper.id),
            "references_linked": ref_result.get("linked", 0),
            "action": {
                "type": "paper_created",
                "payload": {
                    "paper_id": str(new_paper.id),
                    "title": title,
                }
            }
        }

    def _ensure_latex_document(self, content: str, title: str, abstract: str = None) -> str:
        """Ensure content is wrapped in a proper LaTeX document structure."""
        if '\\documentclass' in content:
            return content

        abstract_section = ""
        if abstract:
            abstract_section = f"""
\\begin{{abstract}}
{abstract}
\\end{{abstract}}
"""

        # Check if content has citations
        has_citations = '\\cite{' in content

        # Bibliography section - only include if citations are used
        bibliography_section = ""
        if has_citations:
            bibliography_section = """

\\bibliographystyle{plain}
\\bibliography{references}
"""

        latex_template = f"""\\documentclass{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{amsmath}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}
\\usepackage{{natbib}}

\\title{{{title}}}
\\date{{\\today}}

\\begin{{document}}

\\maketitle
{abstract_section}
{content}
{bibliography_section}
\\end{{document}}
"""
        return latex_template.strip()

    def _tool_update_paper(
        self,
        ctx: Dict[str, Any],
        paper_id: str,
        content: str,
        section_name: Optional[str] = None,
        append: bool = True,
    ) -> Dict:
        """Update an existing paper's content."""
        from app.models import ResearchPaper
        from uuid import UUID
        import re

        try:
            paper_uuid = UUID(paper_id)
        except ValueError:
            return {"status": "error", "message": "Invalid paper ID format"}

        paper = self.db.query(ResearchPaper).filter(
            ResearchPaper.id == paper_uuid
        ).first()

        if not paper:
            return {"status": "error", "message": "Paper not found"}

        # Check if paper is in LaTeX mode (content stored in content_json)
        is_latex_mode = paper.content_json and paper.content_json.get("authoring_mode") == "latex"

        if is_latex_mode:
            current_latex = paper.content_json.get("latex_source", "")

            # Safety: strip \end{document} from content if AI accidentally includes it
            content = re.sub(r'\\end\{document\}.*$', '', content, flags=re.DOTALL).strip()

            if section_name:
                # Replace a specific section by name
                # Pattern matches \section{Name} through to next \section{, bibliography, or \end{document}
                # Must preserve bibliography sections that come after
                escaped_name = re.escape(section_name)
                pattern = rf"(\\section\{{{escaped_name}\}}.*?)(?=\\section\{{|\\begin\{{thebibliography\}}|\\printbibliography|\\bibliography\{{|\\end\{{document\}}|$)"

                if re.search(pattern, current_latex, re.DOTALL | re.IGNORECASE):
                    # Replace the section with new content (use lambda to avoid escape issues with \section)
                    new_latex = re.sub(pattern, lambda m: content + "\n\n", current_latex, count=1, flags=re.DOTALL | re.IGNORECASE)
                else:
                    # Section not found, append instead
                    if "\\end{document}" in current_latex:
                        new_latex = current_latex.replace("\\end{document}", f"\n\n{content}\n\n\\end{{document}}")
                    else:
                        new_latex = current_latex + "\n\n" + content
            elif append and current_latex:
                # Insert before \end{document} if present
                if "\\end{document}" in current_latex:
                    new_latex = current_latex.replace("\\end{document}", f"\n\n{content}\n\n\\end{{document}}")
                else:
                    new_latex = current_latex + "\n\n" + content
            else:
                new_latex = content

            # Update content_json (make a copy to trigger SQLAlchemy change detection)
            updated_json = dict(paper.content_json)
            updated_json["latex_source"] = new_latex
            paper.content_json = updated_json
        else:
            # Plain content mode
            if append and paper.content:
                paper.content = paper.content + "\n\n" + content
            else:
                paper.content = content

        self.db.commit()

        # Link any new cited references to paper and project library
        latex_to_check = new_latex if is_latex_mode else content
        ref_result = self._link_cited_references(ctx, paper_id, latex_to_check)
        ref_message = f" {ref_result['message']}" if ref_result.get("linked", 0) > 0 else ""

        section_msg = f" (replaced section '{section_name}')" if section_name else ""
        return {
            "status": "success",
            "message": f"Updated paper '{paper.title}'{section_msg}.{ref_message}",
            "paper_id": paper_id,
            "references_linked": ref_result.get("linked", 0),
            "action": {
                "type": "paper_updated",
                "payload": {
                    "paper_id": paper_id,
                    "title": paper.title,
                }
            }
        }

    def _tool_create_artifact(
        self,
        ctx: Dict[str, Any],
        title: str,
        content: str,
        format: str = "markdown",
        artifact_type: str = "document",
    ) -> Dict:
        """Create a downloadable artifact and save to database."""
        import base64
        import subprocess
        import tempfile
        import os
        from app.models import DiscussionArtifact

        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()

        # Handle PDF generation with proper cleanup
        if format == "pdf":
            md_path = None
            pdf_path = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as md_file:
                    md_file.write(content)
                    md_path = md_file.name

                pdf_path = md_path.replace('.md', '.pdf')

                result = subprocess.run(
                    ['pandoc', md_path, '-o', pdf_path, '--pdf-engine=tectonic'],
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode != 0:
                    logger.error(f"Pandoc error: {result.stderr}")
                    # Fall back to markdown
                    return self._tool_create_artifact(ctx, title, content, "markdown", artifact_type)

                with open(pdf_path, 'rb') as pdf_file:
                    pdf_bytes = pdf_file.read()
                    content_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                    file_size_bytes = len(pdf_bytes)

                filename = f"{safe_title}.pdf"
                mime_type = "application/pdf"

            except Exception as e:
                logger.error(f"PDF generation failed: {e}")
                return self._tool_create_artifact(ctx, title, content, "markdown", artifact_type)
            finally:
                # Always clean up temp files
                if md_path and os.path.exists(md_path):
                    os.unlink(md_path)
                if pdf_path and os.path.exists(pdf_path):
                    os.unlink(pdf_path)
        else:
            # Text-based formats
            extensions = {"markdown": ".md", "latex": ".tex", "text": ".txt"}
            extension = extensions.get(format, ".txt")
            filename = f"{safe_title}{extension}"

            content_bytes = content.encode('utf-8')
            content_base64 = base64.b64encode(content_bytes).decode('utf-8')
            file_size_bytes = len(content_bytes)

            mime_types = {"markdown": "text/markdown", "latex": "application/x-tex", "text": "text/plain"}
            mime_type = mime_types.get(format, "text/plain")

        # Calculate human-readable file size
        if file_size_bytes < 1024:
            file_size = f"{file_size_bytes} B"
        elif file_size_bytes < 1024 * 1024:
            file_size = f"{file_size_bytes / 1024:.1f} KB"
        else:
            file_size = f"{file_size_bytes / (1024 * 1024):.1f} MB"

        # Save artifact to database
        channel = ctx.get("channel")
        project = ctx.get("project")

        if not channel:
            logger.warning("Cannot save artifact: channel not found in context")
            return {
                "status": "success",
                "message": f"Created downloadable artifact: '{title}' (not persisted)",
                "action": {
                    "type": "artifact_created",
                    "summary": f"Download: {title}",
                    "payload": {
                        "artifact_id": None,
                        "title": title,
                        "filename": filename,
                        "content_base64": content_base64,
                        "format": format,
                        "artifact_type": artifact_type,
                        "mime_type": mime_type,
                        "file_size": file_size,
                    }
                }
            }

        artifact = DiscussionArtifact(
            channel_id=channel.id,
            title=title,
            filename=filename,
            format=format,
            artifact_type=artifact_type,
            content_base64=content_base64,
            mime_type=mime_type,
            file_size=file_size,
            created_by=project.created_by if project else None,
        )
        self.db.add(artifact)
        self.db.commit()
        self.db.refresh(artifact)

        return {
            "status": "success",
            "message": f"Created downloadable artifact: '{title}'",
            "action": {
                "type": "artifact_created",
                "summary": f"Download: {title}",
                "payload": {
                    "artifact_id": str(artifact.id),
                    "title": title,
                    "filename": filename,
                    "content_base64": content_base64,
                    "format": format,
                    "artifact_type": artifact_type,
                    "mime_type": mime_type,
                    "file_size": file_size,
                }
            }
        }

    def _tool_get_created_artifacts(
        self,
        ctx: Dict[str, Any],
        limit: int = 10,
    ) -> Dict:
        """Get artifacts that were created in this discussion channel."""
        from app.models import DiscussionArtifact

        channel = ctx.get("channel")
        if not channel:
            return {
                "status": "error",
                "message": "Channel context not available.",
                "artifacts": [],
            }

        try:
            artifacts = (
                self.db.query(DiscussionArtifact)
                .filter(DiscussionArtifact.channel_id == channel.id)
                .order_by(DiscussionArtifact.created_at.desc())
                .limit(limit)
                .all()
            )

            if not artifacts:
                return {
                    "status": "success",
                    "message": "No artifacts have been created in this channel yet.",
                    "artifacts": [],
                    "count": 0,
                }

            artifact_list = []
            for artifact in artifacts:
                artifact_list.append({
                    "title": artifact.title,
                    "filename": artifact.filename,
                    "format": artifact.format,
                    "artifact_type": artifact.artifact_type,
                    "file_size": artifact.file_size,
                    "mime_type": artifact.mime_type,
                    "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
                })

            return {
                "status": "success",
                "message": f"Found {len(artifact_list)} artifact(s) in this channel.",
                "artifacts": artifact_list,
                "count": len(artifact_list),
            }

        except Exception as e:
            logger.exception(f"Error fetching created artifacts: {e}")
            return {
                "status": "error",
                "message": f"Failed to retrieve artifacts: {str(e)}",
                "artifacts": [],
            }

    def _tool_discover_topics(self, area: str) -> Dict:
        """Use web search to discover specific topics in a broad area."""
        client = self.ai_service.openai_client
        if not client:
            return {
                "status": "error",
                "message": "AI service not configured for topic discovery.",
                "topics": [],
            }

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a research assistant. Search the web and identify 4-6 specific, "
                            "concrete topics/algorithms/methods in the given area. "
                            "Return ONLY a JSON array of objects with 'topic' (short name) and "
                            "'query' (academic search query). Example:\n"
                            '[{"topic": "Mixture of Experts", "query": "mixture of experts transformers 2025"}, '
                            '{"topic": "Mamba", "query": "mamba state space models 2025"}]'
                        )
                    },
                    {
                        "role": "user",
                        "content": f"What are the most important specific topics/algorithms/methods in: {area}?"
                    }
                ],
                temperature=0.3,
            )

            content = response.choices[0].message.content or "[]"

            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                topics = json.loads(json_match.group())
            else:
                topics = []

            return {
                "status": "success",
                "message": f"Discovered {len(topics)} topics in '{area}'",
                "area": area,
                "topics": topics,
            }

        except Exception as e:
            logger.exception(f"Error discovering topics for area '{area}'")
            return {
                "status": "error",
                "message": f"Failed to discover topics: {str(e)}",
                "topics": [],
            }

    def _tool_batch_search_papers(self, topics: List) -> Dict:
        """Search for papers on multiple topics at once."""
        logger.info(f"batch_search_papers called with topics: {topics}")

        if not topics:
            return {
                "status": "error",
                "message": "No topics provided for batch search.",
            }

        # Handle case where topics might be a JSON string
        if isinstance(topics, str):
            try:
                topics = json.loads(topics)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse topics as JSON: {e}")
                return {
                    "status": "error",
                    "message": "Invalid topics format - expected list of topic objects.",
                }

        if not isinstance(topics, list):
            return {
                "status": "error",
                "message": "Invalid topics format - expected list of topic objects.",
            }

        # Format topics for the batch search API
        formatted_topics = []
        for idx, t in enumerate(topics[:5]):  # Limit to 5 topics
            try:
                if isinstance(t, str):
                    try:
                        t = json.loads(t)
                    except json.JSONDecodeError:
                        continue

                if not isinstance(t, dict):
                    continue

                # Get values with flexible key matching
                topic_name = t.get("topic") or t.get('"topic"') or "Unknown"
                query = t.get("query") or t.get('"query"') or str(topic_name)
                max_results = t.get("max_results", 5)

                # Clean up values
                topic_name = str(topic_name).strip('"').strip("'")
                query = str(query).strip('"').strip("'")

                if isinstance(max_results, str):
                    max_results = int(max_results) if max_results.isdigit() else 5
                elif not isinstance(max_results, int):
                    max_results = 5

                formatted_topics.append({
                    "topic": topic_name,
                    "query": query,
                    "max_results": max_results,
                })

            except Exception as e:
                logger.exception(f"Error processing topic {idx}: {e}")
                continue

        if not formatted_topics:
            return {
                "status": "error",
                "message": "Could not parse any valid topics from the request.",
            }

        return {
            "status": "success",
            "message": f"Searching for papers on {len(formatted_topics)} topics",
            "action": {
                "type": "batch_search_references",
                "payload": {
                    "queries": formatted_topics,
                },
            },
        }

    def _tool_add_to_library(
        self,
        ctx: Dict[str, Any],
        paper_indices: List[int],
        ingest_pdfs: bool = True,
    ) -> Dict:
        """
        Add papers from recent search results to the project library and optionally ingest PDFs.
        This allows the AI to have full PDF context before creating papers.
        """
        from app.models import Reference, ProjectReference, ProjectReferenceStatus, ProjectReferenceOrigin
        from app.services.reference_ingestion_service import ingest_reference_pdf

        project = ctx["project"]
        recent_search_results = ctx.get("recent_search_results", [])

        if not recent_search_results:
            return {
                "status": "error",
                "message": "No recent search results. Search for papers first using search_papers.",
            }

        if not paper_indices:
            return {
                "status": "error",
                "message": "No paper indices provided. Specify which papers to add (e.g., [0,1,2] for first 3 papers).",
            }

        added_papers = []
        failed_papers = []
        ingestion_results = []

        for idx in paper_indices:
            if idx < 0 or idx >= len(recent_search_results):
                failed_papers.append({"index": idx, "error": "Index out of range"})
                continue

            paper = recent_search_results[idx]
            title = paper.get("title", "Untitled")

            try:
                # Check if reference already exists by DOI or title
                doi = paper.get("doi")
                existing_ref = None

                if doi:
                    existing_ref = self.db.query(Reference).filter(
                        Reference.doi == doi,
                        Reference.owner_id == project.created_by
                    ).first()

                if not existing_ref:
                    existing_ref = self.db.query(Reference).filter(
                        Reference.title == title,
                        Reference.owner_id == project.created_by
                    ).first()

                # Create Reference if not exists
                if not existing_ref:
                    authors = paper.get("authors", [])
                    if isinstance(authors, str):
                        authors = [a.strip() for a in authors.split(",")]

                    existing_ref = Reference(
                        owner_id=project.created_by,
                        title=title,
                        authors=authors,
                        year=paper.get("year"),
                        doi=doi,
                        url=paper.get("url"),
                        source=paper.get("source", "ai_discovery"),
                        journal=paper.get("journal"),
                        abstract=paper.get("abstract"),
                        is_open_access=paper.get("is_open_access", False),
                        pdf_url=paper.get("pdf_url"),
                        status="pending",
                    )
                    self.db.add(existing_ref)
                    self.db.flush()

                # Add to project library if not already there
                existing_project_ref = self.db.query(ProjectReference).filter(
                    ProjectReference.project_id == project.id,
                    ProjectReference.reference_id == existing_ref.id
                ).first()

                if not existing_project_ref:
                    project_ref = ProjectReference(
                        project_id=project.id,
                        reference_id=existing_ref.id,
                        status=ProjectReferenceStatus.ACCEPTED,
                        origin=ProjectReferenceOrigin.AI_SUGGESTED,
                    )
                    self.db.add(project_ref)

                # Commit changes before attempting PDF ingestion
                self.db.commit()

                added_info = {
                    "index": idx,
                    "title": title,
                    "reference_id": str(existing_ref.id),
                    "has_pdf": bool(existing_ref.pdf_url),
                }

                # Attempt PDF ingestion if requested and PDF is available
                if ingest_pdfs and existing_ref.pdf_url:
                    try:
                        # Use a fresh session for ingestion to avoid transaction issues
                        success = ingest_reference_pdf(
                            self.db,
                            existing_ref,
                            owner_id=str(project.created_by)
                        )
                        if success:
                            added_info["ingestion_status"] = "success"
                            ingestion_results.append({"title": title, "status": "ingested"})
                        else:
                            added_info["ingestion_status"] = "failed"
                            ingestion_results.append({"title": title, "status": "failed"})
                    except Exception as e:
                        logger.warning(f"PDF ingestion failed for {title}: {e}")
                        added_info["ingestion_status"] = "error"
                        added_info["ingestion_error"] = str(e)
                        ingestion_results.append({"title": title, "status": "error", "error": str(e)})
                        # Rollback ingestion failure but keep the reference
                        self.db.rollback()
                elif not existing_ref.pdf_url:
                    added_info["ingestion_status"] = "no_pdf_available"
                else:
                    added_info["ingestion_status"] = "skipped"

                added_papers.append(added_info)

            except Exception as e:
                logger.exception(f"Error adding paper at index {idx}")
                self.db.rollback()
                failed_papers.append({"index": idx, "title": title, "error": str(e)})

        # Summary
        ingested_count = sum(1 for p in added_papers if p.get("ingestion_status") == "success")
        no_pdf_count = sum(1 for p in added_papers if p.get("ingestion_status") == "no_pdf_available")

        message_parts = [f"Added {len(added_papers)} papers to your library."]
        if ingested_count > 0:
            message_parts.append(f"{ingested_count} PDFs ingested for full-text analysis.")
        if no_pdf_count > 0:
            message_parts.append(f"{no_pdf_count} papers have no PDF available (abstract only).")
        if failed_papers:
            message_parts.append(f"{len(failed_papers)} papers failed to add.")

        return {
            "status": "success" if added_papers else "error",
            "message": " ".join(message_parts),
            "added_papers": added_papers,
            "failed_papers": failed_papers,
            "summary": {
                "total_added": len(added_papers),
                "pdfs_ingested": ingested_count,
                "no_pdf_available": no_pdf_count,
                "failed": len(failed_papers),
            },
            "next_step": "Use get_reference_details(reference_id) to read the full content of ingested papers before creating your paper." if ingested_count > 0 else "Papers added with abstract only. You can create a paper based on abstracts, but full PDF analysis is not available.",
        }

    def _tool_update_project_info(
        self,
        ctx: Dict[str, Any],
        description: Optional[str] = None,
        objectives: Optional[List[str]] = None,
        objectives_mode: str = "replace",
    ) -> Dict:
        """
        Update project description and/or objectives.

        Objectives are stored as newline-separated string in the 'scope' field.
        Each objective should be concise (max 150 chars recommended).
        """
        from app.models import Project

        project = ctx["project"]
        updated_fields = []

        # Update description if provided
        if description is not None:
            # Validate description length
            if len(description) > 2000:
                return {
                    "status": "error",
                    "message": "Description is too long. Maximum 2000 characters allowed.",
                }
            project.idea = description.strip()
            updated_fields.append("description")

        # Update objectives if provided
        if objectives is not None:
            if not isinstance(objectives, list):
                return {
                    "status": "error",
                    "message": "Objectives must be a list of strings.",
                }

            # Validate each objective
            validated_objectives = []
            for i, obj in enumerate(objectives):
                if not isinstance(obj, str):
                    continue
                obj = obj.strip()
                if not obj:
                    continue
                # Truncate if too long (max 150 chars per objective)
                if len(obj) > 150:
                    obj = obj[:147] + "..."
                validated_objectives.append(obj)

            if objectives_mode == "append":
                # Append to existing objectives
                existing = project.scope or ""
                existing_list = [o.strip() for o in existing.split("\n") if o.strip()]
                # Don't add duplicates
                added_count = 0
                for new_obj in validated_objectives:
                    if new_obj not in existing_list:
                        existing_list.append(new_obj)
                        added_count += 1
                project.scope = "\n".join(existing_list)
                if added_count > 0:
                    updated_fields.append(f"objectives (added {added_count})")
                else:
                    # All objectives were duplicates
                    pass
            elif objectives_mode == "remove":
                # Remove specific objectives
                existing = project.scope or ""
                existing_list = [o.strip() for o in existing.split("\n") if o.strip()]
                removed = []

                for to_remove in validated_objectives:
                    to_remove_lower = to_remove.lower()
                    # Check if it's an index reference like "objective 1", "1", "first"
                    index_to_remove = None
                    if to_remove_lower.startswith("objective "):
                        try:
                            index_to_remove = int(to_remove_lower.replace("objective ", "")) - 1
                        except ValueError:
                            pass
                    elif to_remove.isdigit():
                        index_to_remove = int(to_remove) - 1

                    if index_to_remove is not None and 0 <= index_to_remove < len(existing_list):
                        removed.append(existing_list[index_to_remove])
                        existing_list[index_to_remove] = None  # Mark for removal
                    else:
                        # Match by text (partial match, case-insensitive)
                        for i, existing_obj in enumerate(existing_list):
                            if existing_obj and to_remove_lower in existing_obj.lower():
                                removed.append(existing_obj)
                                existing_list[i] = None  # Mark for removal
                                break

                # Filter out removed items
                existing_list = [o for o in existing_list if o is not None]
                project.scope = "\n".join(existing_list)

                if removed:
                    updated_fields.append(f"objectives (removed {len(removed)})")
                else:
                    return {
                        "status": "error",
                        "message": "Could not find objectives to remove. Provide the objective text or index (e.g., 'objective 1' or '1').",
                        "current_objectives": existing_list,
                    }
            else:
                # Replace all objectives
                project.scope = "\n".join(validated_objectives)
                updated_fields.append("objectives")

        if not updated_fields:
            return {
                "status": "error",
                "message": "No fields to update. Provide description and/or objectives.",
            }

        try:
            self.db.commit()
            self.db.refresh(project)

            # Parse current objectives for response
            current_objectives = [o.strip() for o in (project.scope or "").split("\n") if o.strip()]

            return {
                "status": "success",
                "message": f"Updated project {', '.join(updated_fields)}.",
                "updated_fields": updated_fields,
                "current_state": {
                    "title": project.title,
                    "description": project.idea,
                    "objectives": current_objectives,
                    "objectives_count": len(current_objectives),
                }
            }
        except Exception as e:
            self.db.rollback()
            logger.exception("Error updating project info")
            return {
                "status": "error",
                "message": f"Failed to update project: {str(e)}",
            }

    def _extract_actions(
        self,
        message: str,
        tool_results: List[Dict],
    ) -> List[Dict]:
        """Extract actions that should be sent to the frontend."""
        # Action types that are notifications (already executed), not suggestions
        COMPLETED_ACTION_TYPES = {
            "paper_created",
            "paper_updated",
            "artifact_created",
        }

        actions = []

        for tr in tool_results:
            result = tr.get("result", {})
            if isinstance(result, dict) and result.get("action"):
                action = result["action"]
                action_type = action.get("type", "")

                # Skip completed/notification actions
                if action_type in COMPLETED_ACTION_TYPES:
                    logger.debug(f"Skipping completed action: {action_type}")
                    continue

                actions.append(action)

        return actions

    # ============================================================
    # AI Memory Management Methods
    # ============================================================

    # Token budget allocation (approximate)
    MEMORY_TOKEN_BUDGET = {
        "working_memory": 4000,    # Last 20 messages (full text)
        "session_summary": 1000,   # Compressed older messages
        "research_facts": 500,     # Structured facts
        "key_quotes": 300,         # Important verbatim statements
    }
    SLIDING_WINDOW_SIZE = 20  # Number of recent messages to keep in full

    # Research stages for state tracking
    RESEARCH_STAGES = [
        "exploring",      # Initial exploration, broad questions
        "refining",       # Narrowing down scope, comparing options
        "finding_papers", # Actively searching for literature
        "analyzing",      # Deep dive into specific papers/methods
        "writing",        # Drafting, synthesizing findings
    ]

    def _get_ai_memory(self, channel: "ProjectDiscussionChannel") -> Dict[str, Any]:
        """Get AI memory from channel, with defaults."""
        if channel.ai_memory:
            # Ensure new fields exist in old memory structures
            memory = channel.ai_memory
            if "research_state" not in memory:
                memory["research_state"] = {
                    "stage": "exploring",
                    "stage_confidence": 0.5,
                    "stage_history": [],
                }
            if "long_term" not in memory:
                memory["long_term"] = {
                    "user_preferences": [],
                    "rejected_approaches": [],
                    "successful_searches": [],
                }
            if "unanswered_questions" not in memory.get("facts", {}):
                memory.setdefault("facts", {})["unanswered_questions"] = []
            return memory
        return {
            "summary": None,
            "facts": {
                "research_topic": None,
                "papers_discussed": [],
                "decisions_made": [],
                "pending_questions": [],
                "unanswered_questions": [],  # Questions AI couldn't answer
                "methodology_notes": [],
            },
            "research_state": {
                "stage": "exploring",           # Current research stage
                "stage_confidence": 0.5,        # How confident we are (0-1)
                "stage_history": [],            # Track stage transitions
            },
            "long_term": {
                "user_preferences": [],         # Learned preferences (e.g., "prefers recent papers")
                "rejected_approaches": [],      # Approaches user explicitly rejected
                "successful_searches": [],      # Search queries that yielded good results
            },
            "key_quotes": [],
            "last_summarized_exchange_id": None,
            "tool_cache": {},
        }

    def _save_ai_memory(self, channel: "ProjectDiscussionChannel", memory: Dict[str, Any]) -> None:
        """Save AI memory to channel."""
        try:
            channel.ai_memory = memory
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to save AI memory: {e}")
            self.db.rollback()

    def _summarize_old_messages(
        self,
        old_messages: List[Dict[str, str]],
        existing_summary: Optional[str] = None,
    ) -> str:
        """
        Summarize older messages into a compressed summary.
        Uses recursive summarization to incorporate existing summary.
        """
        if not old_messages:
            return existing_summary or ""

        # Format messages for summarization
        message_text = "\n".join([
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:500]}"
            for m in old_messages
        ])

        # Build summarization prompt
        if existing_summary:
            prompt = f"""You are summarizing a research conversation for context retention.

EXISTING SUMMARY (from earlier in the conversation):
{existing_summary}

NEW MESSAGES TO INCORPORATE:
{message_text}

Create an UPDATED summary that:
1. Preserves key information from the existing summary
2. Incorporates new developments from the messages
3. Focuses on: research topics, papers discussed, decisions made, methodology choices
4. Keeps it under 300 words
5. Uses bullet points for clarity

Updated Summary:"""
        else:
            prompt = f"""Summarize this research conversation for context retention.

MESSAGES:
{message_text}

Create a summary that:
1. Captures the main research topic/focus
2. Lists any papers or references discussed
3. Notes key decisions or preferences expressed
4. Highlights methodology choices if any
5. Keeps it under 300 words
6. Uses bullet points for clarity

Summary:"""

        try:
            client = self.ai_service.openai_client
            if not client:
                return existing_summary or ""

            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Use faster/cheaper model for summarization
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Failed to summarize messages: {e}")
            return existing_summary or ""

    def _extract_research_facts(
        self,
        user_message: str,
        ai_response: str,
        existing_facts: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Extract structured research facts from the latest exchange.
        Updates existing facts with new information.
        """
        prompt = f"""Analyze this research conversation exchange and extract key facts.

USER MESSAGE:
{user_message[:1000]}

AI RESPONSE:
{ai_response[:1500]}

EXISTING FACTS:
{json.dumps(existing_facts, indent=2)}

Extract and UPDATE the facts JSON. Only include new/changed information.
Return a JSON object with these fields (keep existing values if not changed):
- research_topic: Main research topic (string or null)
- papers_discussed: Array of {{"title": "...", "author": "...", "relevance": "why discussed", "user_reaction": "positive/negative/neutral"}}
- decisions_made: Array of decision strings (append new ones, don't remove old)
- pending_questions: Array of unanswered questions (can remove if answered)
- methodology_notes: Array of methodology-related notes

Return ONLY valid JSON, no explanation:"""

        try:
            client = self.ai_service.openai_client
            if not client:
                return existing_facts

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.2,
            )

            result_text = response.choices[0].message.content.strip()
            # Try to parse JSON from response
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]

            new_facts = json.loads(result_text)

            # Merge with existing facts (append arrays, update scalars)
            merged = existing_facts.copy()
            if new_facts.get("research_topic"):
                merged["research_topic"] = new_facts["research_topic"]

            # Append new papers (avoid duplicates by title)
            existing_titles = {p.get("title", "").lower() for p in merged.get("papers_discussed", [])}
            for paper in new_facts.get("papers_discussed", []):
                if paper.get("title", "").lower() not in existing_titles:
                    merged.setdefault("papers_discussed", []).append(paper)

            # Append new decisions
            existing_decisions = set(merged.get("decisions_made", []))
            for decision in new_facts.get("decisions_made", []):
                if decision not in existing_decisions:
                    merged.setdefault("decisions_made", []).append(decision)

            # Update pending questions (can add or remove)
            merged["pending_questions"] = new_facts.get("pending_questions", merged.get("pending_questions", []))

            # Append methodology notes
            existing_notes = set(merged.get("methodology_notes", []))
            for note in new_facts.get("methodology_notes", []):
                if note not in existing_notes:
                    merged.setdefault("methodology_notes", []).append(note)

            return merged

        except Exception as e:
            logger.error(f"Failed to extract research facts: {e}")
            return existing_facts

    def _extract_key_quotes(self, user_message: str, existing_quotes: List[str]) -> List[str]:
        """
        Extract important verbatim user statements to preserve exact wording.
        Keeps the most recent/important quotes (max 5).
        """
        # Simple heuristic: capture definitive statements
        important_patterns = [
            "I want", "I need", "I decided", "I prefer", "I'm focusing on",
            "my goal is", "the main", "specifically", "must have", "don't want",
        ]

        message_lower = user_message.lower()
        for pattern in important_patterns:
            pattern_lower = pattern.lower()
            if pattern_lower in message_lower:
                # Extract the sentence containing the pattern
                sentences = user_message.replace("!", ".").replace("?", ".").split(".")
                for sentence in sentences:
                    if pattern_lower in sentence.lower() and len(sentence.strip()) > 20:
                        quote = sentence.strip()[:200]
                        if quote not in existing_quotes:
                            existing_quotes.append(quote)
                        break

        # Keep only the last 5 quotes
        return existing_quotes[-5:]

    def update_memory_after_exchange(
        self,
        channel: "ProjectDiscussionChannel",
        user_message: str,
        ai_response: str,
        conversation_history: List[Dict[str, str]],
    ) -> Optional[str]:
        """
        Update AI memory after an exchange. Called after each successful response.
        Handles summarization, fact extraction, quote preservation, and pruning.

        Returns: Optional contradiction warning if detected.
        """
        memory = self._get_ai_memory(channel)
        contradiction_warning = None

        # Extract key quotes from user message (cheap, do always)
        memory["key_quotes"] = self._extract_key_quotes(
            user_message,
            memory.get("key_quotes", [])
        )

        # Check if we need to summarize (conversation exceeds sliding window)
        total_messages = len(conversation_history) + 2  # +2 for current exchange
        if total_messages > self.SLIDING_WINDOW_SIZE:
            # Get messages that need to be summarized
            messages_to_summarize = conversation_history[:-self.SLIDING_WINDOW_SIZE + 2]
            if messages_to_summarize:
                memory["summary"] = self._summarize_old_messages(
                    messages_to_summarize,
                    memory.get("summary"),
                )

        # Rate-limited fact extraction (only every N exchanges or when needed)
        if self.should_update_facts(channel, ai_response):
            # Check for contradictions before updating facts
            existing_facts = memory.get("facts", {})
            if existing_facts.get("decisions_made") or existing_facts.get("research_topic"):
                contradiction_warning = self.detect_contradictions(user_message, existing_facts)

            # Extract research facts
            memory["facts"] = self._extract_research_facts(
                user_message,
                ai_response,
                existing_facts,
            )
            self.reset_exchange_counter(channel)
        else:
            # Increment counter for rate limiting
            self.increment_exchange_counter(channel)

        # Prune stale data periodically (every 10 exchanges)
        exchange_count = memory.get("_exchanges_since_fact_update", 0)
        if exchange_count % 10 == 0:
            self.prune_stale_memory(channel)

        # Save updated memory
        self._save_ai_memory(channel, memory)

        # Phase 3: Update research state and long-term memory (lightweight, do always)
        try:
            self.update_research_state(channel, user_message, ai_response)
            self.track_unanswered_question(channel, user_message, ai_response)
            self.update_long_term_memory(channel, user_message, ai_response)
        except Exception as e:
            logger.error(f"Failed to update Phase 3 memory: {e}")

        return contradiction_warning

    def _build_memory_context(self, channel: "ProjectDiscussionChannel") -> str:
        """
        Build context string from AI memory for inclusion in system prompt.
        Includes all three memory tiers: working, session, and long-term.
        """
        memory = self._get_ai_memory(channel)
        lines = []

        # Tier 2: Session summary
        if memory.get("summary"):
            lines.append("## Previous Conversation Summary")
            lines.append(memory["summary"])
            lines.append("")

        # Tier 3: Research state (Phase 3)
        research_state = memory.get("research_state", {})
        stage = research_state.get("stage", "exploring")
        if stage != "exploring" or research_state.get("stage_confidence", 0) > 0.6:
            stage_desc = {
                "exploring": "Initial exploration",
                "refining": "Refining scope",
                "finding_papers": "Literature search",
                "analyzing": "Deep analysis",
                "writing": "Writing phase",
            }
            lines.append(f"**Research Phase:** {stage_desc.get(stage, stage)}")

        # Research facts
        facts = memory.get("facts", {})
        if facts.get("research_topic"):
            lines.append(f"**Research Focus:** {facts['research_topic']}")

        if facts.get("papers_discussed"):
            lines.append("**Papers Discussed:**")
            for p in facts["papers_discussed"][-5:]:
                reaction = f" ({p.get('user_reaction', '')})" if p.get('user_reaction') else ""
                lines.append(f"- {p.get('title', 'Unknown')} by {p.get('author', 'Unknown')}{reaction}")

        if facts.get("decisions_made"):
            lines.append("**Decisions Made:**")
            for d in facts["decisions_made"][-5:]:
                lines.append(f"- {d}")

        if facts.get("pending_questions"):
            lines.append("**Open Questions:**")
            for q in facts["pending_questions"]:
                lines.append(f"- {q}")

        # Tier 3: Unanswered questions (Phase 3)
        if facts.get("unanswered_questions"):
            lines.append("**Previously Unanswered Questions:**")
            for q in facts["unanswered_questions"]:
                lines.append(f"- {q}")

        # Tier 3: Long-term memory (Phase 3)
        long_term = memory.get("long_term", {})
        if long_term.get("user_preferences"):
            lines.append("**User Preferences:**")
            for p in long_term["user_preferences"][-3:]:
                lines.append(f"- {p}")

        if long_term.get("rejected_approaches"):
            lines.append("**Rejected Approaches (avoid suggesting):**")
            for r in long_term["rejected_approaches"][-3:]:
                lines.append(f"- {r}")

        # Key quotes
        if memory.get("key_quotes"):
            lines.append("**Key User Statements:**")
            for q in memory["key_quotes"]:
                lines.append(f'- "{q}"')

        return "\n".join(lines) if lines else ""

    def cache_tool_result(
        self,
        channel: "ProjectDiscussionChannel",
        tool_name: str,
        result: Dict[str, Any],
    ) -> None:
        """Cache a tool result in AI memory for session reuse."""
        from datetime import datetime, timezone
        memory = self._get_ai_memory(channel)

        # Only cache certain tools that are worth caching
        cacheable_tools = {"get_project_references", "get_project_papers", "get_reference_details"}
        if tool_name not in cacheable_tools:
            return

        tool_cache = memory.get("tool_cache", {})
        tool_cache[tool_name] = {
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        memory["tool_cache"] = tool_cache

        self._save_ai_memory(channel, memory)

    def get_cached_tool_result(
        self,
        channel: "ProjectDiscussionChannel",
        tool_name: str,
        max_age_seconds: int = 300,  # 5 minutes default
    ) -> Optional[Dict[str, Any]]:
        """Get a cached tool result if still valid."""
        from datetime import datetime, timezone
        memory = self._get_ai_memory(channel)

        tool_cache = memory.get("tool_cache", {})
        cached = tool_cache.get(tool_name)

        if not cached:
            return None

        # Check age
        try:
            cached_time = datetime.fromisoformat(cached["timestamp"])
            # Ensure timezone-aware comparison
            if cached_time.tzinfo is None:
                cached_time = cached_time.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - cached_time).total_seconds()
            if age > max_age_seconds:
                return None
            return cached["result"]
        except Exception:
            return None

    def prune_stale_memory(
        self,
        channel: "ProjectDiscussionChannel",
        cache_max_age_seconds: int = 600,  # 10 minutes
        max_papers: int = 10,
        max_decisions: int = 10,
        max_methodology_notes: int = 8,
    ) -> None:
        """
        Prune stale data from AI memory to prevent unbounded growth.
        Called periodically to clean up old cache entries and limit array sizes.
        """
        from datetime import datetime, timezone
        memory = self._get_ai_memory(channel)
        modified = False

        # Prune stale tool cache entries
        tool_cache = memory.get("tool_cache", {})
        stale_keys = []
        for tool_name, cached in tool_cache.items():
            try:
                cached_time = datetime.fromisoformat(cached.get("timestamp", ""))
                if cached_time.tzinfo is None:
                    cached_time = cached_time.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - cached_time).total_seconds()
                if age > cache_max_age_seconds:
                    stale_keys.append(tool_name)
            except Exception:
                stale_keys.append(tool_name)

        for key in stale_keys:
            del tool_cache[key]
            modified = True

        if tool_cache != memory.get("tool_cache", {}):
            memory["tool_cache"] = tool_cache

        # Limit papers_discussed to most recent
        facts = memory.get("facts", {})
        if len(facts.get("papers_discussed", [])) > max_papers:
            facts["papers_discussed"] = facts["papers_discussed"][-max_papers:]
            modified = True

        # Limit decisions_made
        if len(facts.get("decisions_made", [])) > max_decisions:
            facts["decisions_made"] = facts["decisions_made"][-max_decisions:]
            modified = True

        # Limit methodology_notes
        if len(facts.get("methodology_notes", [])) > max_methodology_notes:
            facts["methodology_notes"] = facts["methodology_notes"][-max_methodology_notes:]
            modified = True

        if modified:
            memory["facts"] = facts
            self._save_ai_memory(channel, memory)

    def detect_contradictions(
        self,
        user_message: str,
        existing_facts: Dict[str, Any],
    ) -> Optional[str]:
        """
        Detect if new user statement contradicts existing facts.
        Returns a warning message if contradiction detected, None otherwise.
        Uses LLM to analyze semantic contradictions.
        """
        # Only check if we have substantial existing facts
        decisions = existing_facts.get("decisions_made", [])
        topic = existing_facts.get("research_topic")

        if not decisions and not topic:
            return None

        # Build context of existing facts
        facts_summary = []
        if topic:
            facts_summary.append(f"Research topic: {topic}")
        if decisions:
            facts_summary.append(f"Decisions made: {', '.join(decisions[-5:])}")

        prompt = f"""Analyze if the new user statement contradicts any established facts.

ESTABLISHED FACTS:
{chr(10).join(facts_summary)}

NEW USER STATEMENT:
{user_message[:500]}

Does the new statement contradict any established fact? If yes, briefly explain the contradiction.
If no contradiction, respond with exactly: NO_CONTRADICTION

Response:"""

        try:
            client = self.ai_service.openai_client
            if not client:
                return None

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.1,
            )
            result = response.choices[0].message.content.strip()

            if "NO_CONTRADICTION" in result.upper():
                return None

            return result
        except Exception as e:
            logger.error(f"Contradiction detection failed: {e}")
            return None

    def should_update_facts(
        self,
        channel: "ProjectDiscussionChannel",
        ai_response: str,
        min_response_length: int = 200,
        min_exchanges_between_updates: int = 3,
    ) -> bool:
        """
        Determine if we should run fact extraction on this exchange.
        Prevents excessive LLM calls by rate limiting fact extraction.
        """
        # Only extract facts for substantial responses
        if len(ai_response) < min_response_length:
            return False

        memory = self._get_ai_memory(channel)

        # Track exchange count since last fact extraction
        exchange_count = memory.get("_exchanges_since_fact_update", 0)

        # Update every N exchanges or if facts are empty
        has_facts = bool(memory.get("facts", {}).get("research_topic"))

        if not has_facts or exchange_count >= min_exchanges_between_updates:
            return True

        return False

    def increment_exchange_counter(self, channel: "ProjectDiscussionChannel") -> None:
        """Increment the exchange counter for rate limiting fact extraction."""
        memory = self._get_ai_memory(channel)
        memory["_exchanges_since_fact_update"] = memory.get("_exchanges_since_fact_update", 0) + 1
        self._save_ai_memory(channel, memory)

    def reset_exchange_counter(self, channel: "ProjectDiscussionChannel") -> None:
        """Reset the exchange counter after fact extraction."""
        memory = self._get_ai_memory(channel)
        memory["_exchanges_since_fact_update"] = 0
        self._save_ai_memory(channel, memory)

    # =========================================================================
    # Phase 3: Research State Tracking & Long-Term Memory
    # =========================================================================

    def detect_research_stage(
        self,
        user_message: str,
        ai_response: str,
        current_stage: str,
    ) -> tuple[str, float]:
        """
        Detect the user's current research stage based on conversation.
        Returns (stage, confidence) tuple.

        Stages:
        - exploring: Broad questions, "what should I research?"
        - refining: Narrowing scope, comparing approaches
        - finding_papers: Actively searching literature
        - analyzing: Deep dive into specific papers/methods
        - writing: Drafting, synthesizing, asking about citations
        """
        # Heuristic detection based on message patterns
        message_lower = user_message.lower()
        response_lower = ai_response.lower()

        # Stage indicators (patterns that suggest each stage)
        stage_indicators = {
            "exploring": [
                "what should i", "where do i start", "research topic",
                "ideas for", "suggest a topic", "broad overview",
                "what are the main", "introduce me to",
            ],
            "refining": [
                "narrow down", "focus on", "compare", "which approach",
                "between these", "pros and cons", "should i choose",
                "more specific", "scope", "limit to",
            ],
            "finding_papers": [
                "find papers", "search for", "literature on",
                "recent papers", "seminal work", "key papers",
                "who wrote about", "publications on", "references for",
            ],
            "analyzing": [
                "explain this paper", "methodology in", "how does this work",
                "implement", "replicate", "details of", "dive deeper",
                "understand the", "specific technique",
            ],
            "writing": [
                "write", "draft", "summarize for", "citation",
                "how to cite", "literature review", "introduction section",
                "conclusion", "abstract", "thesis statement",
            ],
        }

        # Count matches for each stage
        stage_scores = {}
        for stage, patterns in stage_indicators.items():
            score = sum(1 for p in patterns if p in message_lower or p in response_lower)
            stage_scores[stage] = score

        # Find best matching stage
        best_stage = max(stage_scores, key=stage_scores.get)
        best_score = stage_scores[best_stage]

        # Calculate confidence based on score and whether it matches current
        if best_score == 0:
            # No clear indicators, stay at current stage
            return current_stage, 0.5

        confidence = min(0.9, 0.5 + (best_score * 0.1))

        # Add inertia - prefer to stay in current stage unless strong signal
        if best_stage != current_stage and best_score < 2:
            return current_stage, 0.6

        return best_stage, confidence

    def update_research_state(
        self,
        channel: "ProjectDiscussionChannel",
        user_message: str,
        ai_response: str,
    ) -> Dict[str, Any]:
        """
        Update research state based on current exchange.
        Returns the updated research state.
        """
        from datetime import datetime, timezone

        memory = self._get_ai_memory(channel)
        research_state = memory.get("research_state", {
            "stage": "exploring",
            "stage_confidence": 0.5,
            "stage_history": [],
        })

        current_stage = research_state.get("stage", "exploring")
        new_stage, confidence = self.detect_research_stage(
            user_message, ai_response, current_stage
        )

        # Record stage transition if changed
        if new_stage != current_stage:
            research_state["stage_history"].append({
                "from": current_stage,
                "to": new_stage,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "confidence": confidence,
            })
            # Keep only last 10 transitions
            research_state["stage_history"] = research_state["stage_history"][-10:]

        research_state["stage"] = new_stage
        research_state["stage_confidence"] = confidence

        memory["research_state"] = research_state
        self._save_ai_memory(channel, memory)

        return research_state

    def track_unanswered_question(
        self,
        channel: "ProjectDiscussionChannel",
        user_message: str,
        ai_response: str,
    ) -> None:
        """
        Track questions the AI couldn't fully answer for follow-up.
        """
        # Detect if AI indicated it couldn't answer
        uncertainty_phrases = [
            "i don't have access to",
            "i cannot find",
            "i'm not sure",
            "i don't know",
            "couldn't find information",
            "no results found",
            "unable to locate",
            "you might need to",
            "i recommend checking",
        ]

        response_lower = ai_response.lower()
        is_uncertain = any(phrase in response_lower for phrase in uncertainty_phrases)

        if not is_uncertain:
            return

        # Extract the question from user message
        memory = self._get_ai_memory(channel)
        facts = memory.get("facts", {})
        unanswered = facts.get("unanswered_questions", [])

        # Simple question extraction (first sentence or whole message if short)
        question = user_message.strip()
        if len(question) > 200:
            question = question[:200] + "..."

        # Avoid duplicates
        if question not in unanswered:
            unanswered.append(question)
            # Keep only last 5 unanswered questions
            facts["unanswered_questions"] = unanswered[-5:]
            memory["facts"] = facts
            self._save_ai_memory(channel, memory)

    def resolve_unanswered_question(
        self,
        channel: "ProjectDiscussionChannel",
        resolved_question: str,
    ) -> None:
        """
        Remove a question from unanswered list when resolved.
        """
        memory = self._get_ai_memory(channel)
        facts = memory.get("facts", {})
        unanswered = facts.get("unanswered_questions", [])

        # Remove if found (fuzzy match)
        resolved_lower = resolved_question.lower()
        facts["unanswered_questions"] = [
            q for q in unanswered
            if resolved_lower not in q.lower()
        ]
        memory["facts"] = facts
        self._save_ai_memory(channel, memory)

    def update_long_term_memory(
        self,
        channel: "ProjectDiscussionChannel",
        user_message: str,
        ai_response: str,
    ) -> None:
        """
        Update long-term memory with persistent learnings.
        Extracts user preferences and rejected approaches.
        """
        memory = self._get_ai_memory(channel)
        long_term = memory.get("long_term", {
            "user_preferences": [],
            "rejected_approaches": [],
            "successful_searches": [],
        })

        message_lower = user_message.lower()

        # Detect preferences (patterns like "I prefer", "I like", "always use")
        preference_patterns = [
            ("i prefer", "prefers"),
            ("i like", "likes"),
            ("i always", "always"),
            ("i usually", "usually"),
            ("my preference is", "prefers"),
        ]

        for pattern, label in preference_patterns:
            if pattern in message_lower:
                # Extract the preference statement
                idx = message_lower.find(pattern)
                end_idx = message_lower.find(".", idx)
                if end_idx == -1:
                    end_idx = min(idx + 100, len(user_message))
                pref = user_message[idx:end_idx].strip()
                if pref and pref not in long_term["user_preferences"]:
                    long_term["user_preferences"].append(pref)
                    # Keep last 10 preferences
                    long_term["user_preferences"] = long_term["user_preferences"][-10:]
                break

        # Detect rejected approaches
        rejection_patterns = [
            "i don't want", "not interested in", "avoid", "don't like",
            "rejected", "ruled out", "won't work", "not suitable",
        ]

        for pattern in rejection_patterns:
            if pattern in message_lower:
                idx = message_lower.find(pattern)
                end_idx = message_lower.find(".", idx)
                if end_idx == -1:
                    end_idx = min(idx + 100, len(user_message))
                rejection = user_message[idx:end_idx].strip()
                if rejection and rejection not in long_term["rejected_approaches"]:
                    long_term["rejected_approaches"].append(rejection)
                    long_term["rejected_approaches"] = long_term["rejected_approaches"][-10:]
                break

        memory["long_term"] = long_term
        self._save_ai_memory(channel, memory)

    def get_session_context_for_return(
        self,
        channel: "ProjectDiscussionChannel",
    ) -> str:
        """
        Generate a context summary for when user returns to a session.
        Useful for "welcome back" scenarios.
        """
        memory = self._get_ai_memory(channel)

        lines = []
        lines.append("## Session Context (Welcome Back)")

        # Research state
        research_state = memory.get("research_state", {})
        stage = research_state.get("stage", "exploring")
        stage_labels = {
            "exploring": "exploring research topics",
            "refining": "refining your research scope",
            "finding_papers": "searching for relevant literature",
            "analyzing": "analyzing specific papers/methods",
            "writing": "working on your writing",
        }
        lines.append(f"\n**Current Stage:** You were {stage_labels.get(stage, stage)}.")

        # Research topic
        facts = memory.get("facts", {})
        if facts.get("research_topic"):
            lines.append(f"**Research Topic:** {facts['research_topic']}")

        # Recent decisions
        decisions = facts.get("decisions_made", [])
        if decisions:
            lines.append("\n**Recent Decisions:**")
            for d in decisions[-3:]:
                lines.append(f"- {d}")

        # Pending questions
        pending = facts.get("pending_questions", [])
        if pending:
            lines.append("\n**Open Questions:**")
            for q in pending:
                lines.append(f"- {q}")

        # Unanswered questions
        unanswered = facts.get("unanswered_questions", [])
        if unanswered:
            lines.append("\n**Questions I Couldn't Answer Previously:**")
            for q in unanswered:
                lines.append(f"- {q}")

        # User preferences
        long_term = memory.get("long_term", {})
        prefs = long_term.get("user_preferences", [])
        if prefs:
            lines.append("\n**Your Preferences:**")
            for p in prefs[-3:]:
                lines.append(f"- {p}")

        return "\n".join(lines) if len(lines) > 1 else ""

    def build_full_memory_context(
        self,
        channel: "ProjectDiscussionChannel",
        include_welcome_back: bool = False,
    ) -> str:
        """
        Build complete memory context including all three tiers:
        1. Working memory (handled in _build_messages)
        2. Session summary
        3. Long-term memory (research state, preferences, etc.)
        """
        memory = self._get_ai_memory(channel)
        lines = []

        # Session summary (Tier 2)
        if memory.get("summary"):
            lines.append("## Conversation Summary")
            lines.append(memory["summary"])
            lines.append("")

        # Research state
        research_state = memory.get("research_state", {})
        stage = research_state.get("stage", "exploring")
        if stage != "exploring" or research_state.get("stage_confidence", 0) > 0.6:
            stage_desc = {
                "exploring": "Initial exploration phase",
                "refining": "Refining research scope",
                "finding_papers": "Literature search phase",
                "analyzing": "Deep analysis phase",
                "writing": "Writing/synthesis phase",
            }
            lines.append(f"**Research Phase:** {stage_desc.get(stage, stage)}")

        # Research facts
        facts = memory.get("facts", {})
        if facts.get("research_topic"):
            lines.append(f"**Research Focus:** {facts['research_topic']}")

        if facts.get("papers_discussed"):
            lines.append("**Papers Discussed:**")
            for p in facts["papers_discussed"][-5:]:
                reaction = f" ({p.get('user_reaction', '')})" if p.get('user_reaction') else ""
                lines.append(f"- {p.get('title', 'Unknown')} by {p.get('author', 'Unknown')}{reaction}")

        if facts.get("decisions_made"):
            lines.append("**Decisions Made:**")
            for d in facts["decisions_made"][-5:]:
                lines.append(f"- {d}")

        if facts.get("pending_questions"):
            lines.append("**Open Questions:**")
            for q in facts["pending_questions"]:
                lines.append(f"- {q}")

        # Long-term memory
        long_term = memory.get("long_term", {})
        if long_term.get("user_preferences"):
            lines.append("**User Preferences:**")
            for p in long_term["user_preferences"][-3:]:
                lines.append(f"- {p}")

        if long_term.get("rejected_approaches"):
            lines.append("**Rejected Approaches:**")
            for r in long_term["rejected_approaches"][-3:]:
                lines.append(f"- {r}")

        # Key quotes
        if memory.get("key_quotes"):
            lines.append("**Key User Statements:**")
            for q in memory["key_quotes"]:
                lines.append(f'- "{q}"')

        return "\n".join(lines) if lines else ""
