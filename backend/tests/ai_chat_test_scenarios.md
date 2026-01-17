# AI Chat Assistant Test Scenarios

This document contains test prompts to evaluate the Discussion AI assistant across various complexity levels and use cases.

---

## Category 1: Simple Tasks (Single Tool Call)

### Test 1.1: Get Project Info
**Prompt:** "What is this project about?"

**Expected Behavior:**
- AI calls `get_project_info` tool
- Returns project title, idea, scope, keywords
- Does NOT search for papers or call other tools

---

### Test 1.2: List Project Papers
**Prompt:** "Show me the papers in this project"

**Expected Behavior:**
- AI calls `get_project_papers` tool
- Lists papers with titles, types, and status
- Does NOT attempt to create or modify anything

---

### Test 1.3: List Project References
**Prompt:** "What references do we have in the library?"

**Expected Behavior:**
- AI calls `get_project_references` tool
- Returns list of references with titles, authors, years
- Does NOT trigger a search

---

### Test 1.4: Simple Paper Search
**Prompt:** "Search for papers about transformer architecture"

**Expected Behavior:**
- AI calls `search_papers` tool with query like "transformer architecture"
- Returns action for frontend to execute search
- AI says it's searching and tells user to wait for results
- Does NOT call `get_recent_search_results` in same turn (it would be empty)

---

### Test 1.5: Get Channel Resources
**Prompt:** "What resources are attached to this channel?"

**Expected Behavior:**
- AI calls `get_channel_resources` tool
- Returns list of attached resources
- Single tool call, immediate response

---

## Category 2: Medium Tasks (2 Tool Calls or Reasoning Required)

### Test 2.1: Search with Specific Year
**Prompt:** "Find papers about diffusion models published in 2024"

**Expected Behavior:**
- AI calls `search_papers` with query including "2024" or year filter
- Uses proper academic terms, not just user's literal words
- Single search, waits for results

---

### Test 2.2: Search with Multiple Keywords
**Prompt:** "I need papers about federated learning for healthcare applications"

**Expected Behavior:**
- AI calls `search_papers` with combined query like "federated learning healthcare medical"
- Proper query construction, not separate searches
- Clear message about what's being searched

---

### Test 2.3: Get Paper Content
**Prompt:** "Show me the content of the literature review paper"

**Expected Behavior:**
- AI calls `get_project_papers` with `include_content=True`
- Identifies the correct paper by title/type
- Displays content in readable format (LaTeX converted to markdown for chat)

---

### Test 2.4: Check Search Results Exist
**Prompt:** "Do we have any search results from earlier?"

**Expected Behavior:**
- AI calls `get_recent_search_results` tool
- Reports count and lists papers if available
- Does NOT trigger a new search

---

### Test 2.5: Ambiguous Request - Needs Clarification
**Prompt:** "Write something for me"

**Expected Behavior:**
- AI asks ONE clarifying question: "What would you like me to write? A paper, summary, or something else?"
- Does NOT attempt to create anything without knowing what
- Does NOT ask multiple follow-up questions

---

## Category 3: Complex Tasks (Multi-Phase Workflows)

### Test 3.1: Two-Phase: Search Then Use Results
**Phase 1 Prompt:** "Search for papers about mixture of experts"
**Phase 2 Prompt:** "Use these papers to create a literature review"

**Expected Behavior Phase 1:**
- AI calls `search_papers`
- Tells user to wait for results
- STOPS (does not create paper yet)

**Expected Behavior Phase 2:**
- AI calls `get_recent_search_results` to get the papers
- AI calls `create_paper` with proper LaTeX content
- Includes `\cite{}` commands for references
- References are automatically linked to project library
- Paper is created in LaTeX mode

---

### Test 3.2: Three-Phase: Search, Create, Then Extend
**Phase 1:** "Find papers about BERT and attention mechanisms"
**Phase 2:** "Create a paper summarizing these findings"
**Phase 3:** "Extend the conclusion section with future research directions"

**Expected Behavior Phase 1:**
- Search triggered, results appear

**Expected Behavior Phase 2:**
- Paper created with sections (Introduction, Methods, Results, Conclusion)
- References properly cited

**Expected Behavior Phase 3:**
- AI calls `update_paper` with `section_name="Conclusion"`
- Existing conclusion is REPLACED (not duplicated)
- Bibliography section preserved
- Paper content updated, frontend refreshes

---

### Test 3.3: Batch Search Multiple Topics
**Prompt:** "I need papers on three topics: transformer efficiency, model compression, and knowledge distillation"

**Expected Behavior:**
- AI calls `batch_search_papers` with 3 queries
- Results grouped by topic when displayed
- Does NOT make 3 separate `search_papers` calls

---

### Test 3.4: Discovery Flow for Vague Request
**Prompt:** "Find me the latest AI algorithms from 2025"

**Expected Behavior:**
- AI recognizes this is vague (doesn't know WHICH algorithms)
- Calls `discover_topics` tool to find what's trending
- Shows discovered topics to user
- Asks user to confirm which topics to search
- THEN does batch search for selected topics

---

### Test 3.5: Create Paper with Specific References
**Prompt:** "Create a paper about panoptic segmentation using the 5 papers we just found"

**Expected Behavior:**
- AI calls `get_recent_search_results` first
- Creates paper with proper LaTeX structure
- Includes bibliography with the 5 papers
- All 5 papers linked to paper AND project library
- Response mentions "Linked 5 references to paper and project library"

---

## Category 4: Section Editing Tasks

### Test 4.1: Extend Existing Section
**Prompt:** "Make the introduction longer with more background"

**Expected Behavior:**
- AI calls `get_project_papers` with `include_content=True` to read current content
- AI calls `update_paper` with `section_name="Introduction"`
- Content includes FULL expanded introduction (not just additions)
- Introduction replaced, other sections preserved
- Bibliography preserved

---

### Test 4.2: Add New Section
**Prompt:** "Add a Related Work section to the paper"

**Expected Behavior:**
- AI calls `update_paper` with `append=True` (no section_name)
- New section added before `\end{document}`
- Existing sections untouched

---

### Test 4.3: Rewrite Section Completely
**Prompt:** "Rewrite the methodology section to focus on experimental setup"

**Expected Behavior:**
- AI reads paper first
- Calls `update_paper` with `section_name="Methodology"` or `section_name="Methods"`
- Completely new content for that section
- Other sections preserved

---

### Test 4.4: Section Not Found - Graceful Handling
**Prompt:** "Update the 'Experiments' section"

**Expected Behavior (if section doesn't exist):**
- AI attempts `update_paper` with `section_name="Experiments"`
- Section not found → content appended instead
- AI informs user: "Section 'Experiments' not found, added as new section"

---

## Category 5: Error Handling & Edge Cases

### Test 5.1: No Papers in Project
**Prompt:** "Show me the conclusion of our paper"

**Expected Behavior (if no papers exist):**
- AI calls `get_project_papers`
- Returns "No papers found in this project"
- Does NOT attempt to read non-existent content

---

### Test 5.2: No Search Results Available
**Prompt:** "Use the papers from the search to write a summary"

**Expected Behavior (if no recent search):**
- AI calls `get_recent_search_results`
- Gets empty results
- Responds: "No recent search results available. Would you like me to search for papers first?"
- Does NOT hallucinate papers

---

### Test 5.3: Invalid Paper ID
**Prompt:** "Update paper abc123 with new content"

**Expected Behavior:**
- AI attempts to use the ID
- Returns error: "Invalid paper ID format" or "Paper not found"
- Does NOT crash or hang

---

### Test 5.4: User Says "Yes" Without Context
**Prompt:** "Yes"

**Expected Behavior:**
- AI checks conversation context
- If previous AI message asked a question → respond to that
- If no context → ask "What would you like me to help you with?"
- Does NOT trigger a search (frontend should block this)

---

### Test 5.5: Conflicting Instructions
**Prompt:** "Search for papers but don't search for papers"

**Expected Behavior:**
- AI asks for clarification
- Does NOT execute contradictory commands
- Single clarifying question

---

## Category 6: Reference & Citation Handling

### Test 6.1: Proper Citation Format
**Prompt:** "Create a paper about attention mechanisms using the search results"

**Expected Behavior:**
- Paper uses `\cite{authorYearKeyword}` format
- Bibliography uses `\begin{thebibliography}` or similar
- Citation keys match between text and bibliography
- All cited papers added to project library

---

### Test 6.2: Citation Key Matching
**Prompt:** (After search returns paper by "Vaswani et al., 2017, Attention Is All You Need")
"Include this in the references"

**Expected Behavior:**
- Creates citation key like `vaswani2017attention`
- Key is findable in search results
- Reference properly linked

---

### Test 6.3: Don't Duplicate References
**Prompt:** (Run twice) "Add the search results as references to the paper"

**Expected Behavior:**
- First time: References added to paper and project library
- Second time: "References already linked" or similar (no duplicates)
- Check by DOI and title to prevent duplicates

---

## Category 7: Content Quality Tests

### Test 7.1: LaTeX Format Only
**Prompt:** "Create a paper about neural networks"

**Expected Behavior:**
- Paper uses `\section{}`, `\subsection{}`, NOT `#`, `##`
- Uses `\textbf{}`, `\textit{}`, NOT `**bold**`, `*italic*`
- Uses `\begin{itemize}`, NOT `- bullet`
- Proper LaTeX document structure

---

### Test 7.2: No Markdown in LaTeX Paper
**Prompt:** "Add a summary section with bullet points"

**Expected Behavior:**
- Uses `\begin{itemize}` and `\item`
- Does NOT use markdown syntax
- Properly formatted LaTeX

---

### Test 7.3: Don't Include \end{document} in Updates
**Prompt:** "Add a new section about future work"

**Expected Behavior:**
- New content does NOT include `\end{document}`
- Document structure preserved
- No duplicate `\end{document}` tags

---

## Category 8: Conversation Flow Tests

### Test 8.1: Remember Context Across Messages
**Prompt 1:** "Search for papers about GPT-4"
**Prompt 2:** "How many did you find?"

**Expected Behavior:**
- AI remembers the search was done
- Calls `get_recent_search_results` to count
- Does NOT search again

---

### Test 8.2: Don't Search Again After Search Done
**Prompt 1:** "Find papers about RLHF"
**Prompt 2:** "Now create a literature review about RLHF"

**Expected Behavior Prompt 2:**
- AI uses existing search results
- Does NOT trigger new search
- Calls `get_recent_search_results` then `create_paper`

---

### Test 8.3: Handle "Use These" Command
**Prompt:** (After search results appear) "Use these"

**Expected Behavior:**
- AI understands "these" refers to search results
- Asks what to do with them OR proceeds with most logical action
- Does NOT search again

---

### Test 8.4: Stop After Search (Async Behavior)
**Prompt:** "Search for papers and then create a summary"

**Expected Behavior:**
- AI calls `search_papers` and STOPS
- Does NOT immediately call `create_paper` (results not available yet)
- Says "Searching... Once results appear, I'll help you create the summary"
- User must send another message after results appear

---

## Category 9: Performance & Stress Tests

### Test 9.1: Long Paper Content
**Prompt:** "Create a comprehensive 10-section paper about machine learning"

**Expected Behavior:**
- Paper created successfully (not truncated)
- All 10 sections present
- Proper structure maintained

---

### Test 9.2: Many References
**Prompt:** (After batch search returns 30 papers) "Create a paper citing all of these"

**Expected Behavior:**
- All 30 citations included
- Bibliography complete
- All 30 references linked to project library
- No timeout or failure

---

### Test 9.3: Rapid Sequential Requests
**Prompt 1:** "Search for transformers"
**Prompt 2:** (immediately) "Search for CNNs"
**Prompt 3:** (immediately) "Search for RNNs"

**Expected Behavior:**
- Handles concurrent requests gracefully
- No race conditions
- Each search completes properly

---

## Test Execution Checklist

| Test ID | Category | Status | Notes |
|---------|----------|--------|-------|
| 1.1 | Simple | [ ] | |
| 1.2 | Simple | [ ] | |
| 1.3 | Simple | [ ] | |
| 1.4 | Simple | [ ] | |
| 1.5 | Simple | [ ] | |
| 2.1 | Medium | [ ] | |
| 2.2 | Medium | [ ] | |
| 2.3 | Medium | [ ] | |
| 2.4 | Medium | [ ] | |
| 2.5 | Medium | [ ] | |
| 3.1 | Complex | [ ] | |
| 3.2 | Complex | [ ] | |
| 3.3 | Complex | [ ] | |
| 3.4 | Complex | [ ] | |
| 3.5 | Complex | [ ] | |
| 4.1 | Editing | [ ] | |
| 4.2 | Editing | [ ] | |
| 4.3 | Editing | [ ] | |
| 4.4 | Editing | [ ] | |
| 5.1 | Errors | [ ] | |
| 5.2 | Errors | [ ] | |
| 5.3 | Errors | [ ] | |
| 5.4 | Errors | [ ] | |
| 5.5 | Errors | [ ] | |
| 6.1 | References | [ ] | |
| 6.2 | References | [ ] | |
| 6.3 | References | [ ] | |
| 7.1 | Quality | [ ] | |
| 7.2 | Quality | [ ] | |
| 7.3 | Quality | [ ] | |
| 8.1 | Flow | [ ] | |
| 8.2 | Flow | [ ] | |
| 8.3 | Flow | [ ] | |
| 8.4 | Flow | [ ] | |
| 9.1 | Stress | [ ] | |
| 9.2 | Stress | [ ] | |
| 9.3 | Stress | [ ] | |

---

## Known Issues to Watch For

1. **AI searches again when asked to create** - Should use existing results
2. **AI calls get_recent_search_results immediately after search_papers** - Results will be empty
3. **AI uses markdown in LaTeX papers** - Should use LaTeX syntax only
4. **AI includes \end{document} in section updates** - Should be stripped
5. **AI duplicates sections instead of replacing** - Should use section_name parameter
6. **AI loses bibliography when updating sections** - Regex should preserve it
7. **References not linked to project library** - Should auto-link cited papers
8. **AI asks too many clarifying questions** - Should ask at most ONE
9. **Frontend doesn't refresh after paper_updated** - Query invalidation needed
