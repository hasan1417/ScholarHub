# Manual QA: Discussion AI Tool Functions

**Date:** 2026-02-07
**Tester:** _______________
**Project ID:** `c1234567-89ab-cdef-0123-456789abcdef`
**Channel IDs used:** _______________

## Execution Rules

1. Use prompts exactly as written (no paraphrasing).
2. Wait for the full AI response before checking.
3. Tests are grouped into flows — some tests depend on prior tests in the same flow.
4. Where a test says "same channel", reuse the channel from the previous test.
5. Where a test says "new channel", create a fresh channel.
6. Record channel IDs and any paper/reference IDs you observe.

## How to Verify

### Check exchange response (tool calls & results)
```sql
SELECT
  response->'message' as ai_message,
  response->'suggested_actions' as actions,
  jsonb_array_length(response->'suggested_actions') as action_count
FROM project_discussion_assistant_exchanges
WHERE channel_id = '<CHANNEL_ID>'
ORDER BY created_at DESC LIMIT 1;
```

### Check project references (library)
```sql
SELECT pr.id, r.title, r.authors, r.year, r.doi, r.summary,
       pr.annotations, pr.added_via_channel_id
FROM project_references pr
JOIN references r ON pr.reference_id = r.id
WHERE pr.project_id = '<PROJECT_ID>'
ORDER BY pr.created_at DESC LIMIT 10;
```

### Check research papers (user-created documents)
```sql
SELECT id, title, paper_type, format, abstract,
       length(content) as content_length,
       created_at
FROM research_papers
WHERE project_id = '<PROJECT_ID>'
ORDER BY created_at DESC LIMIT 5;
```

### Check artifacts
```sql
SELECT a.id, a.type, a.status, a.payload->>'title' as title,
       length(a.payload->>'content') as content_length,
       a.created_at
FROM ai_artifacts a
JOIN ai_artifact_channel_links acl ON acl.artifact_id = a.id
WHERE acl.channel_id = '<CHANNEL_ID>'
ORDER BY a.created_at DESC LIMIT 5;
```

### Check project info
```sql
SELECT id, title, description, keywords
FROM projects
WHERE id = '<PROJECT_ID>';
```

---

# FLOW A: Search & Discovery (Tests 13-15)

> **Setup:** New channel for each test.

---

## Test 13: `search_papers` — Basic Search

**Prompt:**
> Find papers about transformer architectures in natural language processing.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI response mentions searching | Contains "Searching" or similar | | [ ] |
| `suggested_actions` has `search_results` | `action_type = "search_results"` present | | [ ] |
| Payload contains `query` | `query` field is populated (concise, about transformers + NLP) | | [ ] |
| Payload contains `papers` array | Array with >= 1 paper objects | | [ ] |
| Each paper has: title, authors, year, source | All fields present (non-null) | | [ ] |

---

## Test 14: `discover_topics` — Broad Topic Discovery

**Prompt:**
> What are the latest trends and breakthroughs in reinforcement learning?

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI response discusses specific topics/methods | Lists concrete subtopics (not just generic text) | | [ ] |
| Response mentions specific algorithms or areas | e.g., RLHF, multi-agent RL, model-based RL, etc. | | [ ] |
| No error in response | No "I encountered an error" message | | [ ] |

**Note:** `discover_topics` returns data inline to the AI (no `suggested_actions`). Verify by checking that the AI's response contains specific, factual subtopics rather than vague generalities.

---

## Test 15: `get_related_papers` — Find Related Work

**Setup:** Same channel as Test 13 (needs search results in context).

**Prompt:**
> Find papers similar to the first paper from the search results.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI attempts to find related papers | Response mentions finding related/similar papers | | [ ] |
| Returns paper results or explains findings | Lists papers or says what it found | | [ ] |
| No "I don't have" or hallucinated IDs | Uses actual paper data from previous search | | [ ] |

---

# FLOW B: Library Management (Tests 16-21)

> **Setup:** New channel. Tests 16-21 run sequentially in the same channel.

---

## Test 16: `search_papers` + `add_to_library` — Search Then Add

**Prompt 1:**
> Search for papers about federated learning in healthcare.

*Wait for search results to appear.*

**Prompt 2:**
> Add papers 1, 2, and 3 to my library.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI confirms papers added | Response mentions papers were added to library | | [ ] |
| DB: `project_references` has new rows | >= 3 new rows with `project_id` matching and `added_via_channel_id` = this channel | | [ ] |
| DB: `references` rows created | Corresponding rows in `references` with title, authors, year | | [ ] |

**SQL check:**
```sql
SELECT COUNT(*) FROM project_references
WHERE project_id = '<PROJECT_ID>'
AND added_via_channel_id = '<CHANNEL_ID>';
```

---

## Test 17: `get_project_references` — List Library

**Prompt (same channel):**
> What papers are in my library?

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI lists papers with titles | Shows titles of papers added in Test 16 | | [ ] |
| Includes author and year info | At least some papers show authors/year | | [ ] |
| Mentions total count | Says something like "3 papers" or lists them | | [ ] |

---

## Test 18: `get_reference_details` — Paper Details

**Prompt (same channel):**
> Tell me more about the first paper in my library. What are its key findings?

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI provides detailed info about a specific paper | Shows title, abstract, or analysis details | | [ ] |
| If PDF was ingested: shows summary/findings | `summary` or `key_findings` from reference | | [ ] |
| If no PDF: explains limited info available | Mentions only abstract is available | | [ ] |

---

## Test 19: `annotate_reference` — Add Notes & Tags

**Prompt (same channel):**
> Tag the first paper in my library as "key-paper" and "methodology" and add a note: "This is the foundational paper for our federated learning approach."

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI confirms annotation added | Response mentions note/tags were added | | [ ] |
| DB: `annotations` field updated | `annotations` jsonb contains tags and note | | [ ] |

**SQL check:**
```sql
SELECT pr.id, pr.annotations
FROM project_references pr
JOIN references r ON pr.reference_id = r.id
WHERE pr.project_id = '<PROJECT_ID>'
AND pr.annotations != '{}'::jsonb
ORDER BY pr.updated_at DESC LIMIT 1;
```

---

## Test 20: `export_citations` — BibTeX Export

**Prompt (same channel):**
> Export all my library papers in BibTeX format.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI returns BibTeX-formatted citations | Contains `@article{` or `@inproceedings{` entries | | [ ] |
| Each entry has author, title, year | Standard BibTeX fields present | | [ ] |
| Covers all library papers | Number of entries matches library count | | [ ] |

---

## Test 21: `semantic_search_library` — Semantic Search in Library

**Prompt (same channel):**
> Search my library for papers about privacy-preserving machine learning.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI returns results from library (not web search) | Mentions "in your library" or "from your collection" | | [ ] |
| Results are semantically relevant | Papers returned relate to privacy/ML (not random) | | [ ] |
| If no match: says so clearly | "No papers in your library match" (not an error) | | [ ] |

---

# FLOW C: Analysis & Comparison (Tests 22-26)

> **Setup:** Continue from Flow B channel (needs library papers). Or new channel — search and add 3+ papers first.

---

## Test 22: `focus_on_papers` — Load Papers for Analysis

**Prompt:**
> Let's focus on the first 3 papers from our library for detailed analysis.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI confirms papers loaded into focus | "I've focused on" or "loaded" 3 papers | | [ ] |
| Response summarizes which papers are focused | Lists titles or brief descriptions | | [ ] |

---

## Test 23: `analyze_across_papers` — Cross-Paper Analysis

**Prompt (same channel):**
> What common themes and methodologies appear across these focused papers?

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI provides cross-paper analysis | Discusses patterns, common themes | | [ ] |
| Mentions specific papers by name | References individual paper findings | | [ ] |
| Identifies agreements/disagreements | Notes where papers align or differ | | [ ] |

---

## Test 24: `compare_papers` — Structured Comparison

**Prompt (same channel):**
> Compare these papers in terms of methodology and results.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI provides structured comparison | Organized by dimensions (methodology, results) | | [ ] |
| Covers multiple papers | Doesn't just describe one paper | | [ ] |
| Uses Markdown formatting | Headers, bold, or lists for structure | | [ ] |

---

## Test 25: `suggest_research_gaps` — Gap Identification

**Prompt (same channel):**
> What research gaps do you see in these papers? What future work could be done?

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI identifies specific gaps | Lists concrete research opportunities | | [ ] |
| Gaps relate to the papers' topics | Not generic/random suggestions | | [ ] |
| Suggests future directions | Actionable research ideas | | [ ] |

---

## Test 26: `trigger_search_ui` — Frontend Search Trigger

**Prompt (new channel):**
> I want to explore papers about quantum computing applications in drug discovery. Can you set up a search for me?

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| `suggested_actions` contains `trigger_search` type | Action sent to frontend | | [ ] |
| Payload has `research_question` field | Contains the search topic | | [ ] |
| AI message acknowledges the search setup | Not a direct search — sets up UI | | [ ] |

**Note:** This test may vary — the AI might call `search_papers` directly instead of `trigger_search_ui`. Both are valid tool choices. If AI searches directly, mark as PASS if results are relevant.

---

# FLOW D: Paper Creation & Writing (Tests 27-31)

> **Setup:** New channel. Search and add 2+ papers to library first (repeat Test 16 flow), then proceed.

---

## Test 27: `create_paper` — Create a Literature Review

**Prompt:**
> Create a literature review paper titled "Federated Learning in Healthcare: A Survey" based on the papers in my library.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI confirms paper created | Response mentions paper was created | | [ ] |
| DB: `research_papers` row created | New row with matching title | | [ ] |
| Content is in LaTeX format | Contains `\section{}`, `\cite{}`, etc. | | [ ] |
| Includes citations (`\cite{}`) | At least 1 `\cite{}` command present | | [ ] |
| `paper_type` is set | `literature_review` or `research` | | [ ] |

**SQL check:**
```sql
-- NOTE: Paper content is stored in content_json (JSONB), not content (legacy text).
SELECT id, title, paper_type,
       content_json->>'authoring_mode' as mode,
       length(content_json->>'latex_source') as latex_length,
       substring(content_json->>'latex_source', 1, 500) as content_preview,
       (content_json->>'latex_source' LIKE '%\cite{%') as has_citations,
       (content_json->>'latex_source' LIKE '%\section{%') as has_sections
FROM research_papers
WHERE project_id = '<PROJECT_ID>'
ORDER BY created_at DESC LIMIT 1;
```

---

## Test 28: `get_project_papers` — List My Papers

**Prompt (same channel):**
> Show me my papers in this project.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI lists the paper created in Test 27 | Shows title "Federated Learning in Healthcare..." | | [ ] |
| Includes paper type and status info | Mentions it's a literature review | | [ ] |

---

## Test 29: `update_paper` — Add a Section

**Prompt (same channel):**
> Add a conclusion section to my literature review paper.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI confirms section added | Response mentions conclusion was added | | [ ] |
| DB: content now contains conclusion | `\section{Conclusion}` present in content | | [ ] |
| Content is LaTeX (not Markdown) | No `##` or `**bold**` — uses `\section{}`, `\textbf{}` | | [ ] |

**SQL check:**
```sql
SELECT id, (content LIKE '%\section{Conclusion}%') as has_conclusion,
       length(content) as content_length
FROM research_papers
WHERE project_id = '<PROJECT_ID>'
ORDER BY updated_at DESC LIMIT 1;
```

---

## Test 30: `generate_section_from_discussion` — Generate Related Work

**Prompt (same channel):**
> Generate a related work section based on our discussion.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI generates a related work section | Response contains or creates a section | | [ ] |
| Content references papers from discussion | Mentions papers by name or topic | | [ ] |
| Output is in LaTeX format | Uses `\section{}`, `\cite{}` | | [ ] |

---

## Test 31: `generate_abstract` — Generate Abstract

**Prompt (same channel):**
> Generate an abstract for my literature review paper.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI generates an abstract | Response contains a structured abstract | | [ ] |
| Abstract summarizes the paper content | References topics from the paper | | [ ] |
| Reasonable length (150-300 words) | Not too short or excessively long | | [ ] |

---

# FLOW E: Artifacts (Tests 32-33)

> **Setup:** New channel.

---

## Test 32: `create_artifact` — Create Downloadable Document

**Prompt:**
> Create a summary document of the key differences between BERT and GPT architectures. Make it downloadable.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI confirms artifact created | Response mentions document/artifact was created | | [ ] |
| `suggested_actions` has artifact action | Contains download link or artifact reference | | [ ] |
| DB: `discussion_artifacts` row created | New row linked to this channel | | [ ] |
| Artifact has title and content | Non-empty `content_base64` | | [ ] |

**SQL check:**
```sql
-- NOTE: Artifacts are stored in discussion_artifacts (not ai_artifacts).
SELECT id, title, filename, format, artifact_type,
       length(content_base64) as content_length,
       mime_type, file_size
FROM discussion_artifacts
WHERE channel_id = '<CHANNEL_ID>'
ORDER BY created_at DESC LIMIT 1;
```

---

## Test 33: `get_created_artifacts` — List Channel Artifacts

**Prompt (same channel):**
> Show me the documents I created in this discussion.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI lists the artifact from Test 32 | Shows title of the BERT vs GPT summary | | [ ] |
| Includes artifact type/format info | Mentions it's a summary or document | | [ ] |

---

# FLOW F: Project Management (Tests 34-35)

> **Setup:** New channel.

---

## Test 34: `get_project_info` — Get Project Details

**Prompt:**
> What is this project about? What are its goals and keywords?

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI returns project title | Shows the project's actual title | | [ ] |
| Shows description (if set) | Displays project description | | [ ] |
| Shows keywords (if set) | Lists project keywords | | [ ] |
| No error | Doesn't say "I couldn't find project info" | | [ ] |

---

## Test 35: `update_project_info` — Update Project Description

**Prompt:**
> Update the project description to: "This project explores the application of federated learning techniques in healthcare settings, with a focus on privacy-preserving patient data analysis." Also add keywords: federated learning, healthcare AI, privacy.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI confirms project updated | Response mentions description/keywords updated | | [ ] |
| DB: description updated | `idea` field matches new text | | [ ] |
| DB: keywords updated | `keywords` array contains the 3 new keywords | | [ ] |

**SQL check:**
```sql
-- NOTE: Project "description" is stored in the `idea` column (not `description`).
SELECT title, idea, keywords
FROM projects
WHERE id = '<PROJECT_ID>';
```

---

# FLOW G: Edge Cases & Multi-Tool Chains (Tests 36-38)

> Tests that require the AI to chain multiple tools together.

---

## Test 36: Search → Add → Focus → Compare (Full Pipeline)

**Setup:** New channel.

**Prompt 1:**
> Search for papers about attention mechanisms in computer vision.

*Wait for results.*

**Prompt 2:**
> Add the first 3 papers to my library and then compare them in terms of methodology and results.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| Papers added to library | `project_references` rows created | | [ ] |
| Comparison provided | AI compares the 3 papers across dimensions | | [ ] |
| Uses actual paper content | References specific titles/findings | | [ ] |

---

## Test 37: `get_channel_papers` — Channel-Specific Papers

**Prompt (same channel as Test 36):**
> What papers did we add in this discussion?

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI lists papers added in this channel | Shows the 3 papers from Test 36 | | [ ] |
| Only shows channel-specific papers | Doesn't list papers from other channels | | [ ] |

---

## Test 38: `batch_search_papers` — Multi-Topic Search

**Setup:** New channel.

**Prompt:**
> Search for papers on these two topics: (1) graph neural networks for molecular property prediction, and (2) self-supervised learning for protein structure.

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| AI searches both topics | Response covers both research areas | | [ ] |
| Results grouped by topic | Separate sections or clear grouping | | [ ] |
| `suggested_actions` has search results | Papers returned for both topics | | [ ] |

---

# Summary Scorecard

| # | Test | Tool(s) | Result |
|---|---|---|---|
| **Search & Discovery** | | | |
| 13 | Basic search | `search_papers` | [ ] |
| 14 | Topic discovery | `discover_topics` | [ ] |
| 15 | Related papers | `get_related_papers` | [ ] |
| **Library Management** | | | |
| 16 | Search + add to library | `search_papers` + `add_to_library` | [ ] |
| 17 | List library | `get_project_references` | [ ] |
| 18 | Paper details | `get_reference_details` | [ ] |
| 19 | Annotate reference | `annotate_reference` | [ ] |
| 20 | Export citations | `export_citations` | [ ] |
| 21 | Semantic search library | `semantic_search_library` | [ ] |
| **Analysis & Comparison** | | | |
| 22 | Focus on papers | `focus_on_papers` | [ ] |
| 23 | Cross-paper analysis | `analyze_across_papers` | [ ] |
| 24 | Structured comparison | `compare_papers` | [ ] |
| 25 | Research gaps | `suggest_research_gaps` | [ ] |
| 26 | Trigger search UI | `trigger_search_ui` | [ ] |
| **Paper Creation** | | | |
| 27 | Create paper | `create_paper` | [ ] |
| 28 | List my papers | `get_project_papers` | [ ] |
| 29 | Update paper | `update_paper` | [ ] |
| 30 | Generate section | `generate_section_from_discussion` | [ ] |
| 31 | Generate abstract | `generate_abstract` | [ ] |
| **Artifacts** | | | |
| 32 | Create artifact | `create_artifact` | [ ] |
| 33 | List artifacts | `get_created_artifacts` | [ ] |
| **Project Management** | | | |
| 34 | Get project info | `get_project_info` | [ ] |
| 35 | Update project info | `update_project_info` | [ ] |
| **Multi-Tool Chains** | | | |
| 36 | Full pipeline | `search` → `add` → `focus` → `compare` | [ ] |
| 37 | Channel papers | `get_channel_papers` | [ ] |
| 38 | Batch search | `batch_search_papers` | [ ] |

**Overall: ___ / 26 passed**

---

## Notes / Issues Found

```
(Write any issues, unexpected behavior, or observations here)
```
