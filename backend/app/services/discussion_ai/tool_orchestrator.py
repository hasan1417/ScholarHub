"""
Tool-Based Discussion AI Orchestrator

Uses OpenAI function calling to let the AI decide what context it needs.
Instead of hardcoding what data each skill uses, the AI calls tools on-demand.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Generator, List, Optional, TYPE_CHECKING

from sqlalchemy.orm.attributes import flag_modified

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import Project, ProjectDiscussionChannel, User
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
            "description": "Get files/documents specifically attached to this discussion channel (uploaded PDFs, etc). NOT for papers added to library via this channel.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_channel_papers",
            "description": "Get papers that were added to the library through this discussion channel. Use when user asks 'how many papers added to/through this channel', 'papers we discussed', 'references added here'.",
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
                        "description": "Content in LATEX FORMAT ONLY. Use \\section{}, \\subsection{}, \\textbf{}, \\textit{}, \\begin{itemize}, \\cite{}, etc. Do NOT use Markdown. CITATION FORMAT: Use \\cite{authorYYYYword} where author=first author's last name (lowercase), YYYY=year, word=first significant word from title (lowercase). Example: For 'Self-Attention as Distributional Projection' by Mehta (2025) use \\cite{mehta2025self}. Do NOT add References section - it's auto-generated."
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
    },
    # ========== DEEP SEARCH & PAPER FOCUS TOOLS ==========
    {
        "type": "function",
        "function": {
            "name": "deep_search_papers",
            "description": "Search papers and synthesize an answer to a complex research question. Returns synthesized answer with supporting papers. Use this for questions like 'What are the main approaches to X?', 'How do researchers typically handle Y?', 'What's the state of the art in Z?'",
            "parameters": {
                "type": "object",
                "properties": {
                    "research_question": {
                        "type": "string",
                        "description": "The research question to answer (e.g., 'What are the main approaches to attention in transformers?')"
                    },
                    "max_papers": {
                        "type": "integer",
                        "description": "Maximum number of papers to analyze",
                        "default": 10
                    }
                },
                "required": ["research_question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "focus_on_papers",
            "description": "Load specific papers into focus for detailed discussion. For SEARCH RESULTS use paper_indices (0-based). For LIBRARY papers, you MUST first call get_project_references to get real UUIDs, then pass those UUIDs to reference_ids. NEVER invent or guess IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Indices from recent search results (0-based). 'paper 1' = index 0, 'paper 2' = index 1, etc."
                    },
                    "reference_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "REAL UUID reference IDs from get_project_references. NEVER make up IDs like 'ref1' or 'paper1' - always get real UUIDs first!"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_across_papers",
            "description": "Analyze a topic across all focused papers, finding patterns, agreements, and disagreements. Use when user asks to compare papers, find commonalities, or synthesize findings across multiple papers. Requires papers to be focused first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis_question": {
                        "type": "string",
                        "description": "The analysis question (e.g., 'How do their methodologies compare?', 'What are the common findings?', 'Where do they disagree?')"
                    }
                },
                "required": ["analysis_question"]
            }
        }
    },
    {
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
                        "description": "Type of section to generate"
                    },
                    "target_paper_id": {
                        "type": "string",
                        "description": "Optional: ID of paper to add section to. If not provided, creates an artifact."
                    },
                    "custom_instructions": {
                        "type": "string",
                        "description": "Optional: Custom instructions for the section (e.g., 'focus on transformer methods', 'emphasize practical applications')"
                    }
                },
                "required": ["section_type"]
            }
        }
    }
]

# System prompt with adaptive workflow based on request clarity
BASE_SYSTEM_PROMPT = """You are a research assistant helping with academic papers.

TOOLS:
**Discovery & Search:**
- discover_topics: Find what specific topics exist in a broad area (use for vague requests like "recent algorithms")
- search_papers: Search for academic papers on a SPECIFIC topic
- batch_search_papers: Search multiple specific topics at once (grouped results)
- deep_search_papers: Search and synthesize an answer to complex research questions

**Paper Management:**
- get_recent_search_results: Get papers from last search (for "these papers", "use them")
- add_to_library: Add search results to library AND ingest PDFs (USE BEFORE create_paper!)
- get_project_references: Get user's saved papers (for "my library")
- get_reference_details: Get full content of an ingested reference

**Paper Focus & Analysis:**
- focus_on_papers: Load specific papers into focus for detailed discussion
- analyze_across_papers: Compare and analyze across focused papers - USE THIS when papers are focused!

**CRITICAL - FOCUSED PAPERS RULE:**
When you see "FOCUSED PAPERS" in the context above, you MUST use analyze_across_papers for:
- "Compare the methodologies" → analyze_across_papers
- "What are the key findings?" → analyze_across_papers
- "How do they differ?" → analyze_across_papers
- "Summarize what we discussed" → analyze_across_papers
- ANY question about the focused papers → analyze_across_papers
DO NOT search again when papers are already focused!

**Content Creation:**
- get_project_papers: Get user's draft papers in this project
- create_paper: Create a new paper IN THE PROJECT (LaTeX editor)
- create_artifact: Create downloadable content (doesn't save to project)
- get_created_artifacts: Get previously created artifacts (PDFs, documents) in this channel
- update_paper: Add content to an existing paper
- generate_section_from_discussion: Create paper sections from discussion insights
- update_project_info: Update project description and/or objectives

## CORE PRINCIPLE: BE CONTEXT-AWARE

You are a smart research assistant. Use common sense and conversation context.

**THE GOLDEN RULE**: Use what you already have before searching for new things.
- If you just searched/discussed/analyzed papers → those ARE the context
- If user says "create a paper" or "write a review" → use papers already in context
- If user says "use these" or "based on this" → use current context
- ONLY search when user explicitly asks for NEW/DIFFERENT papers, or when there's nothing in context

**THREE LAYERS OF PAPER CONTEXT** (in order of priority):

1. **RECENT SEARCH RESULTS** (highest priority for "first paper", "paper 1", etc.):
   - These are the papers from the MOST RECENT search in this conversation
   - Numbered list (1., 2., 3...) - "first paper" = paper #1, "second paper" = paper #2
   - This is what user refers to with "these papers", "them", "the papers you found"
   - Changes with each new search

2. **CHANNEL PAPER HISTORY** (for "papers we added", "papers from earlier"):
   - All papers added to library THROUGH THIS SPECIFIC CHANNEL
   - User may say: "the paper we added earlier", "papers from our discussion", "papers we've been working with"
   - These persist across searches - they're the channel's discussion history
   - Marked with bullet points (•) in context under "PAPERS ADDED IN THIS CHANNEL"

3. **PROJECT LIBRARY** (for "my library", "all my papers"):
   - All papers in the project from ANY source (all channels, manual adds, imports)
   - User may say: "my library", "all my references", "papers in my project"
   - Use get_project_references tool to access full library

**INTERPRETING USER REFERENCES**:
- "first paper", "paper 1", "paper 2" → RECENT SEARCH RESULTS (numbered list)
- "the paper we added", "papers from earlier" → CHANNEL PAPER HISTORY (bullet list)
- "my library", "all my papers" → PROJECT LIBRARY (use tool)
- If ambiguous, prefer recent search results, then channel history

**THINK LIKE A HUMAN ASSISTANT**:
- User searches for papers → you show results
- User says "create a paper with these" → you use THOSE results (don't search again!)
- User discusses papers with you → you remember them
- User says "write a literature review" → you use what you were discussing (don't search again!)
- User asks "what is the first paper about" → you answer about paper #1 from the recent search!
- User asks "what about the paper we added earlier" → check CHANNEL PAPER HISTORY

**WHEN TO SEARCH**:
- User explicitly says "find papers about X", "search for Y", "I need new references"
- There are NO papers in context and user wants content
- User asks about a DIFFERENT topic than what's in context

**WHEN NOT TO SEARCH**:
- You just showed search results and user wants to use them
- You were just discussing specific papers
- User says "create", "write", "summarize" without mentioning a new topic

GUIDELINES:
1. Be dynamic and contextual - don't follow rigid scripts
2. Never ask more than ONE clarifying question
3. **SEARCH QUERY BEST PRACTICES**:
   - Use proper academic terminology (e.g., "sentiment analysis" not "feelings detection")
   - DO NOT include years in the query (e.g., "NLP" not "NLP 2024 2025")
   - Keep queries focused: 2-5 key terms work best
   - Avoid redundancy (e.g., "natural language processing" not "natural language processing NLP")
   - Examples of GOOD queries: "transformer attention mechanisms", "large language models evaluation"
   - Examples of BAD queries: "NLP 2024 2025", "transformers AI recent papers", "machine learning new"
4. Don't invent papers from your training data - only use search results
5. For general knowledge questions, answer from knowledge first, then offer to search
6. Output markdown naturally (not in code blocks)
7. References section is auto-generated from \\cite{{}} - never add it manually
8. For long content, offer to create as a paper instead of dumping in chat
9. Never show UUIDs to users - just titles and relevant info
10. Always confirm what you created by name
11. **DEPTH AWARENESS & AUTO-INGESTION**:
    - Search results = ABSTRACTS ONLY (no full text)
    - Library papers with ingested PDFs = FULL TEXT available

    **FOR CONTENT-HEAVY REQUESTS (literature reviews, methodology comparisons, detailed analysis):**
    1. FIRST: Call add_to_library with ingest_pdfs=True to add papers and ingest their PDFs
    2. WAIT for ingestion results - note which papers were successfully ingested
    3. THEN: Write the content based on full-text access
    4. If some papers couldn't be ingested (not open access), mention this limitation

    **DON'T write literature reviews from abstracts alone** - always try to ingest first!

    **WHEN ASKED ABOUT A SPECIFIC PAPER:**
    STOP! Before answering from the abstract, CHECK THE LIBRARY FIRST!

    Look at the "Papers with FULL TEXT available" list in the context above.
    If the paper is listed there → You MUST call get_reference_details(reference_id) to get the full analysis!

    WRONG: Answering from abstract then offering "I can add/ingest the PDF..."
    RIGHT: Calling get_reference_details first, then answering with full-text details

    Only offer to add/ingest if the paper is NOT in the library with full text.
12. PROJECT OBJECTIVES: Each objective should be concise (max ~150 chars). Use update_project_info with:
    - objectives_mode="append" to ADD new objectives to existing ones (KEEP existing + add new)
    - objectives_mode="remove" to REMOVE specific objectives (by index like "1", "2" or text match)
    - objectives_mode="replace" to REPLACE all objectives (DELETE existing, set new ones)

    **CRITICAL - "ADD" MEANS APPEND:**
    When user says "add these", "add the first 3", "include these objectives" → use objectives_mode="append"!
    This KEEPS existing objectives and adds new ones on top.

    Example: User lists 10 suggestions, then says "add only the first 3"
    → Call: update_project_info(objectives=["Suggestion 1", "Suggestion 2", "Suggestion 3"], objectives_mode="append")
    This ADDS those 3 to whatever objectives already exist.

    **REPLACE vs APPEND:**
    - "set objectives to X" or "change objectives to X" → replace
    - "add X" or "include X" or "also add X" → append

    **COMPLEX EDITS** (remove some + reword some + add new): Use "replace" mode!
    1. Look at current objectives in the Project Overview above
    2. Apply ALL changes (removals, rewordings, additions) to create the final list
    3. Call update_project_info(objectives=[...final list...], objectives_mode="replace")

**WHEN USER REQUESTS A SEARCH:**
- Call the search_papers tool with the query
- The tool searches and returns results that will be displayed as cards in the UI
- Just confirm: "I found X papers on [topic]. You can review them below and click 'Add' to save any to your library."
- Do NOT list all papers in your message - the UI shows them as interactive cards

**AFTER showing topics + user confirms multiple searches:**
User: "all 6 please" or "search all" or "yes"
→ Call batch_search_papers with the topics you listed
→ Confirm: "I'm searching for papers on all topics. Results will appear as cards below."

IMPORTANT: Papers appear as visual cards with Add buttons - don't duplicate them in your text response.

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
    "- If user asks to 'create', 'generate', 'write' AFTER a search was done → call get_recent_search_results FIRST, do NOT search again!\n"
    "- For research questions ('What are the approaches to X?', 'overview of Y') → answer from knowledge, then OFFER to search for papers\n"
    "- Only call deep_search_papers when user explicitly asks for papers, references, citations, or recent/2024/2025 literature"
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
        current_user: Optional["User"] = None,
    ) -> Dict[str, Any]:
        """Handle a user message (non-streaming)."""
        try:
            # Build request context (thread-safe - local variable)
            ctx = self._build_request_context(
                project, channel, message, recent_search_results, reasoning_mode, conversation_history, current_user
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
        current_user: Optional["User"] = None,
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
                project, channel, message, recent_search_results, reasoning_mode, conversation_history, current_user
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
        current_user: Optional["User"] = None,
    ) -> Dict[str, Any]:
        """Build thread-safe request context."""
        import re

        # Extract count from message (e.g., "find 5 papers" → 5)
        count_match = re.search(r"(\d+)\s*(?:papers?|references?|articles?)", message, re.IGNORECASE)
        extracted_count = int(count_match.group(1)) if count_match else None

        return {
            "project": project,
            "channel": channel,
            "current_user": current_user,  # User who sent the prompt
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
            logger.info(f"Memory context added to prompt. Length: {len(memory_context)}")
            if "FOCUSED PAPERS" in memory_context:
                logger.info("✅ FOCUSED PAPERS section is in the context!")
            else:
                logger.info("❌ FOCUSED PAPERS section NOT in the context")

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
            # Deep search & paper focus tools
            "deep_search_papers": "Searching and synthesizing papers",
            "focus_on_papers": "Loading papers into focus",
            "analyze_across_papers": "Analyzing across focused papers",
            "generate_section_from_discussion": "Generating section from discussion",
        }
        return tool_messages.get(tool_name, "Processing")

    def _execute_with_tools_streaming(
        self,
        messages: List[Dict],
        ctx: Dict[str, Any],
    ) -> Generator[Dict[str, Any], None, None]:
        """Execute with tool calling and streaming."""
        max_iterations = 8
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
            max_iterations = 8
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

        # Get project references with full text info using JOIN (optimized - single query)
        from app.models import Reference
        refs_with_status = self.db.query(Reference.id, Reference.title, Reference.status).join(
            ProjectReference, ProjectReference.reference_id == Reference.id
        ).filter(ProjectReference.project_id == project.id).limit(50).all()

        ref_count = len(refs_with_status)
        if ref_count > 0:
            ingested_refs = [(r.id, r.title) for r in refs_with_status if r.status in ("ingested", "analyzed")]
            lines.append(f"- Project library: {ref_count} saved references ({len(ingested_refs)} with full text)")
            if ingested_refs:
                lines.append("  **Papers with FULL TEXT available** - USE get_reference_details(reference_id) to read:")
                for ref_id, title in ingested_refs[:5]:
                    title_preview = (title[:50] if title else "Untitled")
                    lines.append(f"    • {title_preview}... (reference_id: {ref_id})")

        # Count project papers
        paper_count = self.db.query(ResearchPaper).filter(
            ResearchPaper.project_id == project.id
        ).count()
        if paper_count > 0:
            lines.append(f"- Project papers: {paper_count} drafts")

        # Recent search results - show prominently
        if recent_search_results:
            lines.append(f"\n**RECENT SEARCH RESULTS** (user's 'first paper', 'paper 2', etc. refer to these!):")
            for i, p in enumerate(recent_search_results, 1):
                title = p.get("title", "Untitled")[:80]
                year = p.get("year", "")
                authors = p.get("authors", "")
                if isinstance(authors, list):
                    authors = ", ".join(authors[:2]) + ("..." if len(authors) > 2 else "")
                lines.append(f"  {i}. \"{title}{'...' if len(p.get('title', '')) > 80 else ''}\" ({authors}, {year})")

        # Papers added through this channel (optimized JOIN query)
        channel_papers = self.db.query(Reference.id, Reference.title, Reference.year, Reference.status).join(
            ProjectReference, ProjectReference.reference_id == Reference.id
        ).filter(
            ProjectReference.project_id == project.id,
            ProjectReference.added_via_channel_id == channel.id
        ).limit(20).all()

        if channel_papers:
            lines.append(f"\n**PAPERS ADDED IN THIS CHANNEL** ({len(channel_papers)} papers discussed/added here):")
            for ref in channel_papers:
                title = (ref.title[:60] if ref.title else "Untitled")
                ft_marker = " [FULL TEXT]" if ref.status in ("ingested", "analyzed") else ""
                lines.append(f"  • \"{title}...\" ({ref.year or 'n/a'}){ft_marker} - ref_id: {ref.id}")
            lines.append("  → User can refer to these as 'papers we added', 'papers from earlier'")

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
                    result = self._tool_search_papers(ctx, **args)
                elif name == "get_project_papers":
                    result = self._tool_get_project_papers(ctx, **args)
                    # Cache the result
                    if channel and result.get("count", 0) > 0:
                        self.cache_tool_result(channel, name, result)
                elif name == "get_project_info":
                    result = self._tool_get_project_info(ctx)
                elif name == "get_channel_resources":
                    result = self._tool_get_channel_resources(ctx)
                elif name == "get_channel_papers":
                    result = self._tool_get_channel_papers(ctx)
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
                # Deep search & paper focus tools
                elif name == "deep_search_papers":
                    result = self._tool_deep_search_papers(ctx, **args)
                elif name == "focus_on_papers":
                    result = self._tool_focus_on_papers(ctx, **args)
                elif name == "analyze_across_papers":
                    result = self._tool_analyze_across_papers(ctx, **args)
                elif name == "generate_section_from_discussion":
                    result = self._tool_generate_section_from_discussion(ctx, **args)
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

        # Count papers with available PDFs
        papers_with_pdf = sum(1 for p in recent if p.get("pdf_url") or p.get("is_open_access"))

        papers_list = []
        for i, p in enumerate(recent):
            paper_info = {
                "index": i,
                "title": p.get("title", "Untitled"),
                "authors": p.get("authors", "Unknown"),
                "year": p.get("year"),
                "source": p.get("source", ""),
                "abstract": p.get("abstract", "")[:500] if p.get("abstract") else "",
                "doi": p.get("doi"),
                "url": p.get("url"),
                "has_pdf_available": bool(p.get("pdf_url") or p.get("is_open_access")),
            }
            papers_list.append(paper_info)

        # Build depth info
        depth_info = {
            "total_papers": len(recent),
            "papers_with_pdf_available": papers_with_pdf,
            "content_available": "abstracts_only",
            "limitation": (
                f"These {len(recent)} papers are search results with ONLY abstracts available. "
                "You can provide high-level summaries and identify themes, but cannot access "
                "detailed methodology, specific results, or in-depth findings."
            ),
        }

        if len(recent) > 5:
            depth_info["recommendation"] = (
                f"For detailed analysis of {len(recent)} papers, recommend the user to: "
                "1) Focus on the most relevant 3-5 papers using focus_on_papers, "
                "2) Add them to library using add_to_library to ingest PDFs, "
                "3) Then ask detailed questions. "
                "For now, you can only provide abstract-based overview."
            )

        return {
            "count": len(recent),
            "papers": papers_list,
            "depth_info": depth_info,
            "message": f"Found {len(recent)} papers from the recent search (abstracts only)."
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

    def _tool_search_papers(self, ctx: Dict[str, Any], query: str, count: int = 5, open_access_only: bool = False) -> Dict:
        """Search for papers online and return results directly."""
        import asyncio
        from app.services.paper_discovery_service import PaperDiscoveryService
        from app.models import Reference, ProjectReference

        oa_note = " (Open Access only)" if open_access_only else ""
        project = ctx.get("project")

        # Build lightweight lookup for existing library references (just DOIs and titles)
        library_dois = set()
        library_titles = set()
        if project:
            refs = self.db.query(Reference.doi, Reference.title).join(
                ProjectReference, ProjectReference.reference_id == Reference.id
            ).filter(ProjectReference.project_id == project.id).all()
            for doi, title in refs:
                if doi:
                    library_dois.add(doi.lower().replace("https://doi.org/", "").strip())
                if title:
                    library_titles.add(title.lower().strip())

        # Create event loop FIRST before any async objects
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Create discovery service (needs event loop to exist)
            discovery_service = PaperDiscoveryService()
            sources = ["arxiv", "semantic_scholar", "openalex", "crossref"]
            max_results = min(count, 20)  # Cap at 20 results

            # Request more to account for filtering (open access + library duplicates)
            search_max = max_results * 3

            # Run async search
            result = loop.run_until_complete(discovery_service.discover_papers(
                query=query,
                max_results=search_max,
                sources=sources,
                fast_mode=True,
            ))

            # Filter for open access if requested
            source_papers = result.papers
            if open_access_only:
                source_papers = [p for p in source_papers if p.pdf_url or p.open_access_url]

            # Format results - filter out papers already in library
            papers = []
            for idx, p in enumerate(source_papers):
                # Check if paper is already in library - skip silently
                if p.doi and p.doi.lower().replace("https://doi.org/", "").strip() in library_dois:
                    continue
                if p.title and p.title.lower().strip() in library_titles:
                    continue

                # Stop once we have enough new papers
                if len(papers) >= max_results:
                    break
                # Convert authors to array format (frontend expects string[])
                authors_list = []
                if p.authors:
                    if isinstance(p.authors, list):
                        authors_list = [str(a) for a in p.authors]
                    elif isinstance(p.authors, str):
                        # Split string by comma or "and"
                        authors_list = [a.strip() for a in p.authors.replace(" and ", ", ").split(",") if a.strip()]
                    else:
                        authors_list = [str(p.authors)]

                papers.append({
                    "id": p.doi or p.url or f"paper-{idx}",  # Frontend needs an id
                    "title": p.title,
                    "authors": authors_list,  # Array, not string
                    "year": p.year,
                    "abstract": p.abstract[:300] + "..." if p.abstract and len(p.abstract) > 300 else p.abstract,
                    "doi": p.doi,
                    "url": p.url or p.pdf_url,
                    "pdf_url": p.pdf_url,
                    "source": p.source,
                    "is_open_access": getattr(p, 'is_open_access', False),
                    "journal": getattr(p, 'journal', None) or getattr(p, 'venue', None),
                })

            # Return as action so frontend displays cards with Add buttons
            return {
                "status": "success",
                "message": f"Found {len(papers)} papers for: '{query}'{oa_note}",
                "action": {
                    "type": "search_results",  # Frontend will display as cards
                    "payload": {
                        "query": query,
                        "papers": papers,
                        "total_found": len(result.papers),
                    },
                },
            }

        except Exception as e:
            logger.exception(f"Error searching papers: {e}")
            return {
                "status": "error",
                "message": f"Search failed: {str(e)}",
                "papers": [],
            }
        finally:
            loop.close()

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

    def _tool_get_channel_papers(self, ctx: Dict[str, Any]) -> Dict:
        """Get papers that were added to the library through this discussion channel."""
        from app.models import Reference, ProjectReference

        channel = ctx["channel"]
        project = ctx["project"]

        # Query papers added via this channel
        channel_papers = self.db.query(Reference.id, Reference.title, Reference.year, Reference.status, Reference.doi).join(
            ProjectReference, ProjectReference.reference_id == Reference.id
        ).filter(
            ProjectReference.project_id == project.id,
            ProjectReference.added_via_channel_id == channel.id
        ).all()

        papers_list = []
        for ref in channel_papers:
            ft_available = ref.status in ("ingested", "analyzed")
            papers_list.append({
                "reference_id": str(ref.id),
                "title": ref.title or "Untitled",
                "year": ref.year,
                "doi": ref.doi,
                "full_text_available": ft_available,
            })

        return {
            "count": len(channel_papers),
            "papers": papers_list,
            "message": f"{len(channel_papers)} paper(s) were added to the library through this channel."
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
        from app.models import ResearchPaper, PaperMember, PaperRole
        from datetime import datetime, timezone
        import re

        project = ctx["project"]
        # Use the current user (who prompted the AI) as owner, not project creator
        current_user = ctx.get("current_user")
        owner_id = current_user.id if current_user else project.created_by

        # Generate bibliography entries BEFORE creating the document
        bibliography_entries = self._generate_bibliography_entries(ctx, content)

        latex_source = self._ensure_latex_document(content, title, abstract, bibliography_entries)

        # Auto-generate keywords from title, abstract, and content
        keywords = self._generate_keywords(title, abstract, content)

        # Generate slug and short_id for URL-friendly paper links
        from app.utils.slugify import slugify, generate_short_id
        paper_slug = slugify(title) if title else None
        paper_short_id = generate_short_id()

        new_paper = ResearchPaper(
            title=title,
            slug=paper_slug,
            short_id=paper_short_id,
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
            keywords=keywords,
        )

        self.db.add(new_paper)
        self.db.commit()
        self.db.refresh(new_paper)

        # Add owner as a paper member with OWNER role
        owner_member = PaperMember(
            paper_id=new_paper.id,
            user_id=owner_id,
            role=PaperRole.OWNER,
            status="accepted",
            joined_at=datetime.now(timezone.utc),
        )
        self.db.add(owner_member)
        self.db.commit()

        # Link cited references to paper and project library
        ref_result = self._link_cited_references(ctx, str(new_paper.id), latex_source)
        ref_message = f" {ref_result['message']}" if ref_result.get("linked", 0) > 0 else ""

        # Build url_id for frontend navigation
        url_id = f"{new_paper.slug}-{new_paper.short_id}" if new_paper.slug and new_paper.short_id else str(new_paper.id)

        return {
            "status": "success",
            "message": f"Created paper '{title}' in the project.{ref_message}",
            # Note: paper_id is in action.payload for frontend use - don't show UUIDs to users
            "references_linked": ref_result.get("linked", 0),
            "action": {
                "type": "paper_created",
                "payload": {
                    "paper_id": str(new_paper.id),
                    "url_id": url_id,
                    "title": title,
                }
            }
        }

    def _generate_keywords(self, title: str, abstract: str = None, content: str = None) -> list:
        """Generate keywords from title, abstract, and content."""
        import re

        # Common academic stopwords to filter out
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
            'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that',
            'these', 'those', 'which', 'who', 'whom', 'what', 'when', 'where',
            'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most',
            'other', 'some', 'such', 'no', 'not', 'only', 'own', 'same', 'so',
            'than', 'too', 'very', 'just', 'also', 'now', 'here', 'there', 'then',
            'once', 'any', 'many', 'much', 'before', 'after', 'above', 'below',
            'between', 'through', 'during', 'about', 'into', 'over', 'under',
            'again', 'further', 'while', 'because', 'although', 'since', 'until',
            'unless', 'if', 'use', 'used', 'using', 'based', 'paper', 'study',
            'research', 'results', 'show', 'shows', 'shown', 'found', 'work',
            'approach', 'method', 'methods', 'new', 'novel', 'propose', 'proposed',
            'present', 'presented', 'section', 'introduction', 'conclusion',
            'abstract', 'textit', 'textbf', 'cite', 'ref', 'label', 'begin', 'end',
        }

        # Combine text sources (title weighted more heavily)
        combined_text = f"{title} {title} {title}"  # Weight title 3x
        if abstract:
            combined_text += f" {abstract} {abstract}"  # Weight abstract 2x
        if content:
            # Extract text from LaTeX, skip commands
            clean_content = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', ' ', content)
            clean_content = re.sub(r'\\[a-zA-Z]+', ' ', clean_content)
            combined_text += f" {clean_content}"

        # Extract meaningful words (3+ chars, alphabetic only)
        words = re.findall(r'\b[a-zA-Z]{3,}\b', combined_text.lower())

        # Count word frequency, excluding stopwords
        word_counts = {}
        for word in words:
            if word not in stopwords and len(word) >= 4:
                word_counts[word] = word_counts.get(word, 0) + 1

        # Get top keywords by frequency
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)

        # Return top 5-8 keywords, capitalized nicely
        keywords = []
        for word, _ in sorted_words[:8]:
            # Capitalize properly
            keywords.append(word.capitalize())
            if len(keywords) >= 5:
                break

        return keywords

    def _generate_citation_key(self, paper: Dict) -> str:
        """Generate a citation key from paper info (authorYYYYword format)."""
        import re
        authors = paper.get("authors", "unknown")
        if isinstance(authors, list):
            first_author = authors[0] if authors else "unknown"
        else:
            first_author = authors.split(",")[0].strip() if authors else "unknown"

        # Extract last name
        if "," in first_author:
            last_name = first_author.split(",")[0].strip()
        else:
            last_name = first_author.split()[-1] if first_author.split() else "unknown"

        # Clean last name - only lowercase letters
        last_name = re.sub(r'[^a-zA-Z]', '', last_name).lower()

        year = str(paper.get("year", ""))

        # Get first significant word from title
        title = paper.get("title", "")
        title_words = [w for w in re.findall(r'[a-zA-Z]+', title) if len(w) > 3]
        title_word = title_words[0].lower() if title_words else ""

        return f"{last_name}{year}{title_word}"

    def _generate_bibliography_entries(self, ctx: Dict[str, Any], content: str) -> list:
        """Generate \\bibitem entries for all citations in content."""
        import re
        from app.models import Reference, ProjectReference

        project = ctx["project"]
        recent_search_results = ctx.get("recent_search_results", [])

        # Get project library references
        project_refs = (
            self.db.query(Reference)
            .join(ProjectReference, ProjectReference.reference_id == Reference.id)
            .filter(ProjectReference.project_id == project.id)
            .all()
        )

        # Build lookup of all available papers by citation key
        all_papers = []
        for paper in recent_search_results:
            all_papers.append(paper)
        for ref in project_refs:
            all_papers.append({
                "title": ref.title,
                "authors": ref.authors if isinstance(ref.authors, str) else ", ".join(ref.authors or []),
                "year": ref.year,
                "doi": ref.doi,
                "url": ref.url,
                "journal": ref.journal,
            })

        # Create lookup by citation key
        paper_by_key = {}
        for paper in all_papers:
            key = self._generate_citation_key(paper)
            paper_by_key[key] = paper

        # Extract citation keys from content
        cite_pattern = r'\\cite\{([^}]+)\}'
        cite_matches = re.findall(cite_pattern, content)
        citation_keys = set()
        for match in cite_matches:
            for key in match.split(','):
                citation_keys.add(key.strip())

        # Generate bibitem entries
        bibliography_entries = []
        for cite_key in sorted(citation_keys):
            # Try exact match first
            paper = paper_by_key.get(cite_key)

            # Try partial match
            if not paper:
                normalized_key = re.sub(r'[^a-z0-9]', '', cite_key.lower())
                for lookup_key, p in paper_by_key.items():
                    normalized_lookup = re.sub(r'[^a-z0-9]', '', lookup_key.lower())
                    if normalized_key in normalized_lookup or normalized_lookup in normalized_key:
                        paper = p
                        break

            if paper:
                authors = paper.get("authors", "Unknown")
                if isinstance(authors, list):
                    authors = ", ".join(authors)
                title = paper.get("title", "Untitled")
                year = paper.get("year", "")
                journal = paper.get("journal", "")

                # Format: \bibitem{key} Author(s). \textit{Title}. Journal, Year.
                entry = f"\\bibitem{{{cite_key}}} {authors}. \\textit{{{title}}}."
                if journal:
                    entry += f" {journal},"
                if year:
                    entry += f" {year}."
                bibliography_entries.append(entry)

        return bibliography_entries

    def _sanitize_latex_content(self, content: str) -> str:
        """Remove characters that break LaTeX compilation."""
        import re
        # Remove null characters
        content = content.replace('\x00', '')
        # Remove other control characters except newlines and tabs
        content = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', content)
        # Remove smart quotes and replace with regular quotes
        content = content.replace('"', '"').replace('"', '"')
        content = content.replace(''', "'").replace(''', "'")
        # Remove other unicode that might cause issues
        content = content.replace('–', '--').replace('—', '---')
        content = content.replace('…', '...')
        return content

    def _ensure_latex_document(self, content: str, title: str, abstract: str = None, bibliography_entries: list = None) -> str:
        """Ensure content is wrapped in a proper LaTeX document structure."""
        # Sanitize content first
        content = self._sanitize_latex_content(content)

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

        # Bibliography section - generate inline bibitem entries
        bibliography_section = ""
        if has_citations and bibliography_entries:
            bib_items = "\n".join(bibliography_entries)
            bibliography_section = f"""

\\begin{{thebibliography}}{{99}}
{bib_items}
\\end{{thebibliography}}
"""

        latex_template = f"""\\documentclass{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{amsmath}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}

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

        # Build url_id for frontend navigation
        url_id = f"{paper.slug}-{paper.short_id}" if paper.slug and paper.short_id else str(paper.id)

        return {
            "status": "success",
            "message": f"Updated paper '{paper.title}'{section_msg}.{ref_message}",
            # Note: paper_id is in action.payload for frontend use - don't show UUIDs to users
            "references_linked": ref_result.get("linked", 0),
            "action": {
                "type": "paper_updated",
                "payload": {
                    "paper_id": paper_id,
                    "url_id": url_id,
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

                # Check if already in project library
                existing_project_ref = self.db.query(ProjectReference).filter(
                    ProjectReference.project_id == project.id,
                    ProjectReference.reference_id == existing_ref.id
                ).first()

                already_in_library = existing_project_ref is not None
                channel = ctx.get("channel")

                if not existing_project_ref:
                    project_ref = ProjectReference(
                        project_id=project.id,
                        reference_id=existing_ref.id,
                        status=ProjectReferenceStatus.APPROVED,
                        origin=ProjectReferenceOrigin.AUTO_DISCOVERY,
                        added_via_channel_id=channel.id if channel else None,
                    )
                    self.db.add(project_ref)
                elif channel and not existing_project_ref.added_via_channel_id:
                    # Update existing reference to track the channel if not already set
                    existing_project_ref.added_via_channel_id = channel.id

                # Commit changes before attempting PDF ingestion
                self.db.commit()
                # Refresh to ensure the object is attached to the session after commit
                self.db.refresh(existing_ref)

                # Generate citation key for this paper
                cite_key = self._generate_citation_key(paper)

                added_info = {
                    "index": idx,
                    "title": title,
                    "reference_id": str(existing_ref.id),
                    "has_pdf": bool(existing_ref.pdf_url),
                    "cite_key": cite_key,  # Use this in \cite{} commands
                    "already_in_library": already_in_library,  # Was it already there?
                }

                # Attempt PDF ingestion if requested and PDF is available
                # Reference is already committed, so PDF ingestion failures won't affect it
                if ingest_pdfs and existing_ref.pdf_url:
                    try:
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
                        # Don't rollback - the Reference was already committed successfully
                        # Just expire the session to clear any stale state
                        self.db.expire_all()
                elif not existing_ref.pdf_url:
                    added_info["ingestion_status"] = "no_pdf_available"
                else:
                    added_info["ingestion_status"] = "skipped"

                added_papers.append(added_info)

            except Exception as e:
                logger.exception(f"Error adding paper at index {idx}")
                # Only rollback uncommitted changes for THIS paper
                # Don't use rollback() as it could affect previously committed papers
                self.db.expire_all()
                failed_papers.append({"index": idx, "title": title, "error": str(e)})

        # Summary
        ingested_count = sum(1 for p in added_papers if p.get("ingestion_status") == "success")
        no_pdf_count = sum(1 for p in added_papers if p.get("ingestion_status") == "no_pdf_available")
        already_existed_count = sum(1 for p in added_papers if p.get("already_in_library"))
        newly_added_count = len(added_papers) - already_existed_count

        message_parts = []
        if newly_added_count > 0:
            message_parts.append(f"Added {newly_added_count} new papers to your library.")
        if already_existed_count > 0:
            message_parts.append(f"{already_existed_count} papers were already in your library.")
        if ingested_count > 0:
            message_parts.append(f"{ingested_count} PDFs ingested for full-text analysis.")
        if no_pdf_count > 0:
            message_parts.append(f"{no_pdf_count} papers have no PDF available (abstract only).")
        if failed_papers:
            message_parts.append(f"{len(failed_papers)} papers failed to add.")
        if not message_parts:
            message_parts.append("No papers to add.")

        # Build library_update action so frontend can update search results UI
        library_updates = []
        for paper in added_papers:
            # Map backend ingestion_status to frontend IngestionStatus type
            status_map = {
                "success": "success",
                "failed": "failed",
                "error": "failed",
                "no_pdf_available": "no_pdf",
                "skipped": "success",  # Already processed
            }
            frontend_status = status_map.get(paper.get("ingestion_status", ""), "pending")
            library_updates.append({
                "index": paper.get("index"),
                "reference_id": paper.get("reference_id"),
                "ingestion_status": frontend_status,
            })

        return {
            "status": "success" if added_papers else "error",
            "message": " ".join(message_parts),
            "added_papers": added_papers,
            "failed_papers": failed_papers,
            "summary": {
                "total_processed": len(added_papers),
                "newly_added": newly_added_count,
                "already_in_library": already_existed_count,
                "pdfs_ingested": ingested_count,
                "no_pdf_available": no_pdf_count,
                "failed": len(failed_papers),
            },
            "next_step": "Use get_reference_details(reference_id) to read the full content of ingested papers before creating your paper." if ingested_count > 0 else "Papers added with abstract only. You can create a paper based on abstracts, but full PDF analysis is not available.",
            "citation_instructions": "When creating the paper, use \\cite{cite_key} with the cite_key values provided for each paper above. This ensures references are properly linked.",
            # Action to update frontend search results UI with ingestion status
            "action": {
                "type": "library_update",
                "payload": {
                    "updates": library_updates,
                },
            },
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

    # -------------------------------------------------------------------------
    # Deep Search & Paper Focus Tools
    # -------------------------------------------------------------------------

    def _tool_deep_search_papers(
        self,
        ctx: Dict[str, Any],
        research_question: str,
        max_papers: int = 10,
    ) -> Dict:
        """
        Deep search with synthesis context.
        Searches for papers and provides them in a format optimized for AI synthesis.
        """
        # Store the research question in memory for context
        channel = ctx.get("channel")
        if channel:
            memory = self._get_ai_memory(channel)
            memory.setdefault("deep_search", {})["last_question"] = research_question
            self._save_ai_memory(channel, memory)

        # Trigger the search (frontend will execute it)
        # Use "search_references" action type which frontend already handles
        return {
            "status": "success",
            "message": f"Deep searching for: '{research_question}'",
            "research_question": research_question,
            "action": {
                "type": "search_references",
                "payload": {
                    "query": research_question,
                    "count": max_papers,
                },
            },
            "next_step": (
                "The search results will appear below. I'll synthesize an answer "
                "citing specific papers. You can then focus on specific papers for deeper discussion."
            ),
        }

    def _tool_focus_on_papers(
        self,
        ctx: Dict[str, Any],
        paper_indices: Optional[List[int]] = None,
        reference_ids: Optional[List[str]] = None,
    ) -> Dict:
        """
        Load papers into focus context for detailed discussion.
        Papers can come from search results (by index) or library (by reference ID).
        """
        from app.models import Reference, ProjectReference

        project = ctx["project"]
        channel = ctx.get("channel")
        recent_search_results = ctx.get("recent_search_results", [])

        focused_papers = []
        errors = []

        # Build lookup for existing library references (to check if search results are already ingested)
        library_refs_by_doi = {}
        library_refs_by_title = {}
        if paper_indices:
            # Pre-fetch library references for matching
            library_refs = self.db.query(Reference).join(
                ProjectReference, ProjectReference.reference_id == Reference.id
            ).filter(ProjectReference.project_id == project.id).all()

            for ref in library_refs:
                if ref.doi:
                    library_refs_by_doi[ref.doi.lower().replace("https://doi.org/", "").strip()] = ref
                if ref.title:
                    library_refs_by_title[ref.title.lower().strip()] = ref

        # Get papers from search results by index
        if paper_indices:
            for idx in paper_indices:
                if idx < 0 or idx >= len(recent_search_results):
                    errors.append(f"Index {idx} out of range (have {len(recent_search_results)} results)")
                    continue

                paper = recent_search_results[idx]

                # Check if this paper is already in the library (by DOI or title)
                matched_ref = None
                paper_doi = paper.get("doi", "")
                if paper_doi:
                    matched_ref = library_refs_by_doi.get(paper_doi.lower().replace("https://doi.org/", "").strip())
                if not matched_ref and paper.get("title"):
                    matched_ref = library_refs_by_title.get(paper["title"].lower().strip())

                if matched_ref and matched_ref.status in ("ingested", "analyzed"):
                    # Paper is already in library with ingested PDF - use that data!
                    logger.info(f"Focus: Found '{paper.get('title', '')[:50]}' already ingested in library")
                    focused_papers.append({
                        "source": "library",  # Mark as library source since we're using library data
                        "reference_id": str(matched_ref.id),
                        "index": idx,
                        "title": matched_ref.title,
                        "authors": matched_ref.authors if isinstance(matched_ref.authors, str) else ", ".join(matched_ref.authors or []),
                        "year": matched_ref.year,
                        "abstract": matched_ref.abstract or paper.get("abstract", ""),
                        "doi": matched_ref.doi,
                        "url": matched_ref.url,
                        "pdf_url": paper.get("pdf_url"),
                        "is_open_access": paper.get("is_open_access", False),
                        "summary": matched_ref.summary,
                        "key_findings": matched_ref.key_findings,
                        "methodology": matched_ref.methodology,
                        "limitations": matched_ref.limitations,
                        "has_full_text": True,  # Already ingested!
                    })
                else:
                    # Paper not in library or not ingested - use search result data
                    focused_papers.append({
                        "source": "search_result",
                        "index": idx,
                        "title": paper.get("title", "Untitled"),
                        "authors": paper.get("authors", "Unknown"),
                        "year": paper.get("year"),
                        "abstract": paper.get("abstract", ""),
                        "doi": paper.get("doi"),
                        "url": paper.get("url"),
                        "pdf_url": paper.get("pdf_url"),
                        "is_open_access": paper.get("is_open_access", False),
                        "has_full_text": False,  # Search results only have abstracts
                    })

        # Get papers from library by reference ID
        if reference_ids:
            import uuid as uuid_module
            for ref_id in reference_ids:
                try:
                    # Validate UUID format
                    try:
                        uuid_module.UUID(str(ref_id))
                    except (ValueError, AttributeError):
                        errors.append(f"Invalid reference ID format: '{ref_id}'. Use get_project_references to see valid IDs.")
                        continue

                    ref = self.db.query(Reference).join(
                        ProjectReference,
                        ProjectReference.reference_id == Reference.id
                    ).filter(
                        ProjectReference.project_id == project.id,
                        Reference.id == ref_id
                    ).first()

                    if ref:
                        paper_info = {
                            "source": "library",
                            "reference_id": str(ref.id),
                            "title": ref.title,
                            "authors": ref.authors if isinstance(ref.authors, str) else ", ".join(ref.authors or []),
                            "year": ref.year,
                            "abstract": ref.abstract or "",
                            "doi": ref.doi,
                            "url": ref.url,
                        }

                        # Include analysis if PDF was ingested
                        if ref.status in ("ingested", "analyzed"):
                            paper_info["summary"] = ref.summary
                            paper_info["key_findings"] = ref.key_findings
                            paper_info["methodology"] = ref.methodology
                            paper_info["limitations"] = ref.limitations
                            paper_info["has_full_text"] = True
                        else:
                            paper_info["has_full_text"] = False

                        focused_papers.append(paper_info)
                    else:
                        errors.append(f"Reference {ref_id} not found in project library")
                except Exception as e:
                    errors.append(f"Error loading reference {ref_id}: {str(e)}")

        if not focused_papers:
            return {
                "status": "error",
                "message": "No papers could be focused. " + " ".join(errors),
                "errors": errors,
            }

        # Store focused papers in channel memory
        if channel:
            memory = self._get_ai_memory(channel)
            memory["focused_papers"] = focused_papers
            self._save_ai_memory(channel, memory)
            logger.info(f"✅ Saved {len(focused_papers)} focused papers to channel memory (channel_id: {channel.id})")

        # Build summary for response and count full-text papers
        paper_summaries = []
        full_text_count = 0
        abstract_only_count = 0
        papers_with_pdf_url = []

        for i, p in enumerate(focused_papers, 1):
            has_full = p.get("has_full_text", False)
            if has_full:
                full_text_count += 1
                status = "📄"  # Full PDF analyzed
                depth = "(full text available)"
            else:
                abstract_only_count += 1
                status = "📋"  # Abstract only
                depth = "(abstract only)"
                # Track papers that have PDF URLs but aren't ingested yet
                if p.get("pdf_url") or p.get("is_open_access"):
                    papers_with_pdf_url.append(i)

            paper_summaries.append(f"{i}. {status} **{p['title']}** ({p.get('year', 'N/A')}) {depth}")
            if p.get("authors"):
                authors = p["authors"]
                if isinstance(authors, list):
                    authors = ", ".join(authors[:3]) + ("..." if len(authors) > 3 else "")
                paper_summaries.append(f"   Authors: {authors}")

        # Build depth analysis message
        depth_info = {}
        if abstract_only_count > 0:
            depth_info["abstract_only_papers"] = abstract_only_count
            depth_info["full_text_papers"] = full_text_count

            if abstract_only_count == len(focused_papers):
                depth_info["analysis_depth"] = "shallow"
                depth_info["limitation"] = (
                    "All focused papers have only abstracts available. "
                    "Analysis will be limited to high-level information. "
                    "For deeper discussion (methodology details, specific findings, limitations), "
                    "you'll need to add papers to your library and ingest their PDFs."
                )
            else:
                depth_info["analysis_depth"] = "mixed"
                depth_info["limitation"] = (
                    f"{abstract_only_count} paper(s) have only abstracts. "
                    f"{full_text_count} paper(s) have full PDF analysis available. "
                    "Detailed questions will be better answered for papers with full text."
                )

            # Suggest how to get full text
            if papers_with_pdf_url:
                depth_info["suggestion"] = (
                    f"Papers {', '.join(map(str, papers_with_pdf_url))} have PDFs available. "
                    "To enable deeper analysis: add them to your library using add_to_library, "
                    "or upload the PDFs manually through the Library page."
                )
            else:
                depth_info["suggestion"] = (
                    "To enable deeper analysis, upload PDFs for these papers through the Library page, "
                    "or search for open-access versions."
                )
        else:
            depth_info["analysis_depth"] = "deep"
            depth_info["full_text_papers"] = full_text_count

        result = {
            "status": "success",
            "message": f"Focused on {len(focused_papers)} paper(s)",
            "focused_count": len(focused_papers),
            "papers": paper_summaries,
            "depth_info": depth_info,
            "errors": errors if errors else None,
            "capabilities": [
                "Ask detailed questions about these papers",
                "Use analyze_across_papers to compare them",
                "Use generate_section_from_discussion to create content",
            ] if full_text_count > 0 else [
                "Ask high-level questions about these papers (based on abstracts)",
                "Use analyze_across_papers for broad comparisons",
                "For detailed methodology/findings discussion, add papers to library first",
            ],
        }

        # If there are OA papers without full text, suggest adding them to library
        # and return indices so AI can offer to ingest them
        if papers_with_pdf_url:
            result["oa_papers_available"] = papers_with_pdf_url
            result["auto_ingest_suggestion"] = (
                f"Papers {', '.join(map(str, papers_with_pdf_url))} have PDFs available (Open Access). "
                "Would you like me to add them to your library and ingest the PDFs for deeper analysis? "
                "This will give me access to full methodology, results, and detailed findings."
            )

        return result

    def _tool_analyze_across_papers(
        self,
        ctx: Dict[str, Any],
        analysis_question: str,
    ) -> Dict:
        """
        Cross-paper analysis using RAG (Retrieval Augmented Generation).
        Dynamically retrieves relevant chunks based on the analysis question.
        """
        import math
        from app.models import Reference, ProjectReference
        from app.models.document_chunk import DocumentChunk

        channel = ctx.get("channel")
        project = ctx.get("project")
        if not channel:
            return {
                "status": "error",
                "message": "Channel context not available.",
            }

        memory = self._get_ai_memory(channel)
        focused_papers = memory.get("focused_papers", [])

        if not focused_papers:
            return {
                "status": "error",
                "message": "No papers in focus. Use focus_on_papers first to load papers for analysis.",
                "suggestion": "Try: 'Focus on papers 1 and 2' or 'Focus on the first three papers from the search'",
            }

        # Map focused papers to their reference IDs (if they exist in library)
        paper_to_ref_id = {}
        papers_with_chunks = []
        papers_abstract_only = []

        if project:
            # Get all project references for matching
            references = self.db.query(Reference).join(
                ProjectReference, ProjectReference.reference_id == Reference.id
            ).filter(ProjectReference.project_id == project.id).all()

            # Build lookup maps
            doi_to_ref = {}
            title_to_ref = {}
            url_to_ref = {}
            for ref in references:
                if ref.doi:
                    doi_to_ref[ref.doi.lower().replace("https://doi.org/", "").strip()] = ref
                if ref.title:
                    title_to_ref[ref.title.lower().strip()] = ref
                if ref.url:
                    url_to_ref[ref.url] = ref

            # Match focused papers to references
            for i, paper in enumerate(focused_papers):
                matched_ref = None
                paper_doi = paper.get("doi", "")
                if paper_doi:
                    matched_ref = doi_to_ref.get(paper_doi.lower().replace("https://doi.org/", "").strip())
                if not matched_ref and paper.get("title"):
                    matched_ref = title_to_ref.get(paper["title"].lower().strip())
                if not matched_ref and paper.get("url"):
                    matched_ref = url_to_ref.get(paper["url"])

                if matched_ref and matched_ref.document_id:
                    paper_to_ref_id[i] = matched_ref
                    papers_with_chunks.append((i, paper, matched_ref))
                else:
                    papers_abstract_only.append((i, paper))

        # Use RAG to find relevant chunks for papers that have been ingested
        rag_context_by_paper = {}

        if papers_with_chunks and self.ai_service and self.ai_service.openai_client:
            try:
                # Create embedding for the analysis question
                embedding_response = self.ai_service.openai_client.embeddings.create(
                    model=self.ai_service.embedding_model,
                    input=analysis_question
                )
                query_embedding = embedding_response.data[0].embedding

                def cosine_similarity(a, b):
                    try:
                        dot = sum(x * y for x, y in zip(a, b))
                        norm_a = math.sqrt(sum(x * x for x in a))
                        norm_b = math.sqrt(sum(y * y for y in b))
                        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
                    except:
                        return 0.0

                # For each paper with chunks, find the most relevant chunks
                for paper_idx, paper, ref in papers_with_chunks:
                    chunks = self.db.query(DocumentChunk).filter(
                        DocumentChunk.document_id == ref.document_id
                    ).all()

                    if not chunks:
                        papers_abstract_only.append((paper_idx, paper))
                        continue

                    # Score chunks by relevance to the question
                    scored_chunks = []
                    for chunk in chunks:
                        if not chunk.chunk_text:
                            continue

                        emb = chunk.embedding
                        if emb is not None:
                            # Handle different embedding formats
                            if isinstance(emb, str):
                                try:
                                    import json as _json
                                    emb = _json.loads(emb)
                                except:
                                    emb = None

                            if emb:
                                score = cosine_similarity(query_embedding, emb)
                                scored_chunks.append((chunk, score))
                        else:
                            # Fallback: keyword matching
                            query_terms = [t.lower() for t in analysis_question.split() if len(t) > 2]
                            text_lower = chunk.chunk_text.lower()
                            score = sum(text_lower.count(term) for term in query_terms) / 100.0
                            if score > 0:
                                scored_chunks.append((chunk, score))

                    # Sort by relevance and take top chunks (up to 4 per paper)
                    scored_chunks.sort(key=lambda x: x[1], reverse=True)
                    top_chunks = scored_chunks[:4]

                    if top_chunks:
                        # Build context from relevant chunks
                        chunk_texts = []
                        for chunk, score in top_chunks:
                            # Truncate very long chunks
                            text = chunk.chunk_text[:1500] if len(chunk.chunk_text) > 1500 else chunk.chunk_text
                            chunk_texts.append(text)

                        rag_context_by_paper[paper_idx] = {
                            "chunks": chunk_texts,
                            "chunk_count": len(top_chunks),
                            "top_score": top_chunks[0][1] if top_chunks else 0,
                        }
                        logger.info(f"RAG: Found {len(top_chunks)} relevant chunks for paper {paper_idx + 1} (top score: {top_chunks[0][1]:.3f})")
                    else:
                        papers_abstract_only.append((paper_idx, paper))

            except Exception as e:
                logger.error(f"RAG embedding search failed: {e}")
                # Fall back to treating all as abstract-only
                for paper_idx, paper, ref in papers_with_chunks:
                    papers_abstract_only.append((paper_idx, paper))

        # Build the full context for the AI
        paper_contexts = []
        full_text_count = 0
        abstract_only_count = 0

        for i, paper in enumerate(focused_papers):
            if i in rag_context_by_paper:
                # Paper has RAG-retrieved content
                full_text_count += 1
                rag_data = rag_context_by_paper[i]

                context_parts = [f"### Paper {i + 1}: {paper.get('title', 'Untitled')} [Full Text - RAG Retrieved]"]
                context_parts.append(f"**Authors:** {paper.get('authors', 'Unknown')}")
                context_parts.append(f"**Year:** {paper.get('year', 'N/A')}")

                # Include abstract for context
                if paper.get("abstract"):
                    context_parts.append(f"**Abstract:** {paper['abstract'][:400]}...")

                # Include RAG-retrieved relevant content
                context_parts.append(f"\n**Relevant Content ({rag_data['chunk_count']} passages retrieved for your question):**")
                for j, chunk_text in enumerate(rag_data["chunks"], 1):
                    context_parts.append(f"\n[Passage {j}]\n{chunk_text}")

                paper_contexts.append("\n".join(context_parts))
            else:
                # Abstract only
                abstract_only_count += 1
                context_parts = [f"### Paper {i + 1}: {paper.get('title', 'Untitled')} [Abstract Only]"]
                context_parts.append(f"**Authors:** {paper.get('authors', 'Unknown')}")
                context_parts.append(f"**Year:** {paper.get('year', 'N/A')}")

                if paper.get("abstract"):
                    context_parts.append(f"**Abstract:** {paper['abstract']}")

                paper_contexts.append("\n".join(context_parts))

        full_context = "\n\n" + "=" * 50 + "\n\n".join(paper_contexts)

        # Build depth info
        depth_warning = None
        if abstract_only_count > 0:
            if abstract_only_count == len(focused_papers):
                depth_warning = (
                    "⚠️ **Limited Analysis:** All papers have only abstracts available. "
                    "For detailed analysis, add papers to library and ingest PDFs."
                )
            else:
                depth_warning = (
                    f"📊 **Mixed Depth:** {full_text_count} paper(s) have full-text RAG retrieval, "
                    f"{abstract_only_count} paper(s) have abstracts only."
                )

        # Store analysis info in memory
        memory.setdefault("cross_paper_analysis", {})["last_question"] = analysis_question
        memory["cross_paper_analysis"]["paper_count"] = len(focused_papers)
        memory["cross_paper_analysis"]["rag_papers"] = full_text_count
        memory["cross_paper_analysis"]["abstract_only"] = abstract_only_count
        self._save_ai_memory(channel, memory)

        # Build instruction
        instruction = (
            f"Analyze the following question across all {len(focused_papers)} papers:\n\n"
            f"**Question:** {analysis_question}\n\n"
            "**Instructions:**\n"
            "1. For [Full Text - RAG Retrieved] papers, use the retrieved passages to provide specific, detailed answers\n"
            "2. Quote or reference specific content from the passages when relevant\n"
            "3. For [Abstract Only] papers, provide high-level analysis based on the abstract\n"
            "4. Compare and contrast across papers where applicable\n"
            "5. Cite papers by number (e.g., [Paper 1], [Paper 2])\n"
        )

        return {
            "status": "success",
            "message": f"Analyzing across {len(focused_papers)} papers using RAG",
            "analysis_question": analysis_question,
            "paper_count": len(focused_papers),
            "rag_papers": full_text_count,
            "abstract_only_papers": abstract_only_count,
            "depth_info": depth_warning,
            "papers_context": full_context,
            "instruction": instruction,
            "retrieval_method": "semantic_search" if full_text_count > 0 else "abstracts_only",
        }

    def _tool_generate_section_from_discussion(
        self,
        ctx: Dict[str, Any],
        section_type: str,
        target_paper_id: Optional[str] = None,
        custom_instructions: Optional[str] = None,
    ) -> Dict:
        """
        Generate a paper section based on discussion insights and focused papers.
        Can either add to an existing paper or create a standalone artifact.
        """
        channel = ctx.get("channel")
        if not channel:
            return {
                "status": "error",
                "message": "Channel context not available.",
            }

        memory = self._get_ai_memory(channel)
        focused_papers = memory.get("focused_papers", [])
        session_summary = memory.get("summary", "")
        facts = memory.get("facts", {})
        deep_search = memory.get("deep_search", {})
        cross_analysis = memory.get("cross_paper_analysis", {})

        # Build context from all available sources
        context_parts = []

        # Add focused papers context
        if focused_papers:
            context_parts.append(f"**Focused Papers ({len(focused_papers)}):**")
            for i, p in enumerate(focused_papers, 1):
                paper_info = f"- [{i}] {p.get('title', 'Untitled')} ({p.get('year', 'N/A')})"
                if p.get("key_findings"):
                    findings = p["key_findings"]
                    if isinstance(findings, list) and findings:
                        paper_info += f"\n  Key finding: {findings[0]}"
                context_parts.append(paper_info)

        # Add session context
        if session_summary:
            context_parts.append(f"\n**Discussion Summary:**\n{session_summary[:500]}")

        # Add research topic
        if facts.get("research_topic"):
            context_parts.append(f"\n**Research Topic:** {facts['research_topic']}")

        # Add decisions made
        if facts.get("decisions_made"):
            context_parts.append(f"\n**Decisions Made:**")
            for d in facts["decisions_made"][-5:]:
                context_parts.append(f"- {d}")

        # Add deep search question if available
        if deep_search.get("last_question"):
            context_parts.append(f"\n**Research Question:** {deep_search['last_question']}")

        # Add cross-analysis context
        if cross_analysis.get("last_question"):
            context_parts.append(f"\n**Cross-paper Analysis:** {cross_analysis['last_question']}")

        full_context = "\n".join(context_parts) if context_parts else "No prior context available."

        # Section-specific instructions
        section_instructions = {
            "methodology": (
                "Generate a Methodology section that:\n"
                "- Describes the research approach\n"
                "- References methods from the discussed papers\n"
                "- Uses proper academic language\n"
                "- Cites sources appropriately"
            ),
            "related_work": (
                "Generate a Related Work section that:\n"
                "- Reviews the key papers discussed\n"
                "- Groups them by theme or approach\n"
                "- Identifies gaps and opportunities\n"
                "- Uses proper citation format"
            ),
            "introduction": (
                "Generate an Introduction section that:\n"
                "- Motivates the research problem\n"
                "- Provides background context\n"
                "- States the research objectives\n"
                "- Outlines the paper structure"
            ),
            "results": (
                "Generate a Results section that:\n"
                "- Summarizes key findings from the discussion\n"
                "- Presents comparisons across papers\n"
                "- Uses clear, objective language"
            ),
            "discussion": (
                "Generate a Discussion section that:\n"
                "- Interprets the findings\n"
                "- Compares with existing literature\n"
                "- Addresses limitations\n"
                "- Suggests future directions"
            ),
            "conclusion": (
                "Generate a Conclusion section that:\n"
                "- Summarizes the main contributions\n"
                "- Restates key findings\n"
                "- Provides final thoughts"
            ),
            "abstract": (
                "Generate an Abstract that:\n"
                "- Summarizes the research in 150-250 words\n"
                "- States the problem, approach, and findings\n"
                "- Is self-contained and informative"
            ),
        }

        section_prompt = section_instructions.get(
            section_type,
            f"Generate a {section_type} section based on the discussion context."
        )

        if custom_instructions:
            section_prompt += f"\n\n**Additional Instructions:** {custom_instructions}"

        # If target paper specified, update it
        if target_paper_id:
            return {
                "status": "success",
                "message": f"Ready to generate {section_type} section for existing paper",
                "section_type": section_type,
                "target_paper_id": target_paper_id,
                "context": full_context,
                "generation_prompt": section_prompt,
                "instruction": (
                    f"Generate a {section_type.replace('_', ' ')} section in LaTeX format based on the context provided. "
                    f"Use \\section{{{section_type.replace('_', ' ').title()}}} for the heading. "
                    "Include \\cite{} commands for references. "
                    "After generating, use update_paper to add it to the target paper."
                ),
            }

        # Otherwise, return context for creating an artifact
        return {
            "status": "success",
            "message": f"Ready to generate {section_type} section",
            "section_type": section_type,
            "context": full_context,
            "generation_prompt": section_prompt,
            "focused_paper_count": len(focused_papers),
            "instruction": (
                f"Generate a {section_type.replace('_', ' ')} section in LaTeX format based on the context provided. "
                f"Use \\section{{{section_type.replace('_', ' ').title()}}} for the heading. "
                "Include \\cite{} commands for references to the focused papers. "
                "After generating the content, use create_artifact or create_paper to save it."
            ),
        }

    def _extract_actions(
        self,
        message: str,
        tool_results: List[Dict],
    ) -> List[Dict]:
        """Extract actions that should be sent to the frontend."""
        # Action types that are completed (already executed) - mark them for frontend display
        COMPLETED_ACTION_TYPES = {
            "paper_created",
            "paper_updated",
            "artifact_created",
            "search_results",  # Search already executed, results included
            "library_update",  # Library updates already applied
        }

        # Default summaries for action types
        ACTION_SUMMARIES = {
            "search_results": "View search results",
            "search_references": "Search for papers",
            "batch_search_references": "Search multiple topics",
            "paper_created": "View created paper",
            "paper_updated": "View updated paper",
            "artifact_created": "Download artifact",
            "create_task": "Create task",
            "create_paper": "Create paper",
            "edit_paper": "Apply edit",
            "library_update": "Library updated",
        }

        actions = []

        for tr in tool_results:
            result = tr.get("result", {})
            if isinstance(result, dict) and result.get("action"):
                raw_action = result["action"]
                action_type = raw_action.get("type", "")

                # Transform to frontend format: action_type instead of type
                transformed_action = {
                    "action_type": action_type,
                    "summary": raw_action.get("summary") or ACTION_SUMMARIES.get(action_type, action_type),
                    "payload": raw_action.get("payload", {}),
                }

                # Mark completed actions so frontend can display them appropriately
                if action_type in COMPLETED_ACTION_TYPES:
                    transformed_action["completed"] = True

                actions.append(transformed_action)

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

    def _refresh_focused_papers_with_library_data(
        self, focused_papers: List[Dict], project: "Project"
    ) -> List[Dict]:
        """
        Check if any focused papers have been ingested to the library since focusing.
        If so, enrich them with full-text analysis data.

        This handles the common flow:
        1. User searches papers (abstract only)
        2. User focuses on papers
        3. User asks to ingest them
        4. User asks analysis question - should now use full-text data
        """
        from app.models import Reference

        if not focused_papers or not project:
            return focused_papers

        # Get all project references for matching
        try:
            references = self.db.query(Reference).filter(
                Reference.project_id == project.id
            ).all()
        except Exception as e:
            logger.error(f"Failed to fetch references for refresh: {e}")
            return focused_papers

        if not references:
            return focused_papers

        # Build lookup maps for matching
        doi_to_ref = {}
        title_to_ref = {}
        url_to_ref = {}

        for ref in references:
            if ref.doi:
                # Normalize DOI for matching
                doi_normalized = ref.doi.lower().replace("https://doi.org/", "").strip()
                doi_to_ref[doi_normalized] = ref
            if ref.title:
                title_to_ref[ref.title.lower().strip()] = ref
            if ref.url:
                url_to_ref[ref.url] = ref

        refreshed_papers = []
        refreshed_count = 0

        for paper in focused_papers:
            # Skip if already has full text
            if paper.get("has_full_text"):
                refreshed_papers.append(paper)
                continue

            # Try to find matching reference
            matched_ref = None

            # Match by DOI first (most reliable)
            paper_doi = paper.get("doi", "")
            if paper_doi:
                doi_normalized = paper_doi.lower().replace("https://doi.org/", "").strip()
                matched_ref = doi_to_ref.get(doi_normalized)

            # Match by title if no DOI match
            if not matched_ref and paper.get("title"):
                matched_ref = title_to_ref.get(paper["title"].lower().strip())

            # Match by URL if still no match
            if not matched_ref and paper.get("url"):
                matched_ref = url_to_ref.get(paper["url"])

            # If found and has AI analysis, enrich the paper
            if matched_ref and matched_ref.ai_analysis:
                analysis = matched_ref.ai_analysis
                enriched_paper = paper.copy()
                enriched_paper["has_full_text"] = True
                enriched_paper["reference_id"] = str(matched_ref.id)
                enriched_paper["cite_key"] = matched_ref.cite_key

                # Add analysis fields
                if analysis.get("summary"):
                    enriched_paper["summary"] = analysis["summary"]
                if analysis.get("key_findings"):
                    enriched_paper["key_findings"] = analysis["key_findings"]
                if analysis.get("methodology"):
                    enriched_paper["methodology"] = analysis["methodology"]
                if analysis.get("limitations"):
                    enriched_paper["limitations"] = analysis["limitations"]
                if analysis.get("contributions"):
                    enriched_paper["contributions"] = analysis["contributions"]

                refreshed_papers.append(enriched_paper)
                refreshed_count += 1
                logger.info(f"Refreshed focused paper with full-text: {paper.get('title', 'Untitled')[:50]}")
            else:
                refreshed_papers.append(paper)

        if refreshed_count > 0:
            logger.info(f"Refreshed {refreshed_count} focused papers with library full-text data")

        return refreshed_papers

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
            # CRITICAL: Flag the JSON column as modified so SQLAlchemy detects the change
            # Without this, mutating a JSON dict in-place won't be persisted
            flag_modified(channel, "ai_memory")
            self.db.commit()
            logger.info(f"Saved AI memory for channel {channel.id} - focused_papers: {len(memory.get('focused_papers', []))}")
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

        # DEBUG: Log what's in memory
        logger.info(f"Building memory context. Memory keys: {list(memory.keys())}")
        logger.info(f"Focused papers in memory: {len(memory.get('focused_papers', []))}")

        # Tier 2: Session summary
        if memory.get("summary"):
            lines.append("## Previous Conversation Summary")
            lines.append(memory["summary"])
            lines.append("")

        # CRITICAL: Include focused papers so AI knows to use analyze_across_papers
        focused_papers = memory.get("focused_papers", [])
        if focused_papers:
            lines.append("## FOCUSED PAPERS (Use analyze_across_papers for questions about these)")
            for i, p in enumerate(focused_papers, 1):
                paper_line = f"[{i}] {p.get('title', 'Untitled')}"
                if p.get('authors'):
                    authors = p['authors']
                    if isinstance(authors, list):
                        authors = ', '.join(authors[:2]) + ('...' if len(authors) > 2 else '')
                    paper_line += f" - {authors}"
                if p.get('year'):
                    paper_line += f" ({p['year']})"
                if p.get('has_full_text'):
                    paper_line += " [Full Text]"
                else:
                    paper_line += " [Abstract Only]"
                lines.append(paper_line)
            lines.append("")
            lines.append("**IMPORTANT:** For ANY question about these papers (compare, summarize, discuss), use the analyze_across_papers tool!")
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
