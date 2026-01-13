# Discussion AI - Research Assistant Use Cases

This document defines all use cases for the Discussion AI assistant.
Each use case must pass tests before integration.

---

## 1. Discovery & Search

### 1.1 Search for References
**Intent:** User wants to find papers on a topic
**Examples:**
- "Find 5 papers about transformer architectures"
- "Search for references on population-based metaheuristics"
- "Look for recent papers on NLP in healthcare"

**Flow:** Single turn
```
User: "Find 5 papers about vision transformers"
AI: "I'll search for 5 papers about vision transformers." [+ search_references action]
→ System executes search, shows results
```

**Variations:**
- Specify count: "find 10 papers..."
- Open access only: "find free/open access papers..."
- Recent only: "find papers from 2024..."
- By author: "find papers by Hinton..."

---

### 1.2 Refine Search Results
**Intent:** User wants to filter/adjust search results
**Examples:**
- "Show me only the open access ones"
- "Find more papers like the first one"
- "Search for something more specific about attention mechanisms"

**Flow:** Follow-up to search
```
[After search results shown]
User: "Find more papers like the second one"
AI: "I'll search for papers similar to [paper title]." [+ search action]
```

---

## 2. Content Creation

### 2.1 Create Literature Review
**Intent:** User wants to create a literature review from references
**Examples:**
- "Create a literature review using these 5 papers"
- "Write a lit review about attention mechanisms"
- "Generate a review comparing these approaches"

**Flow:** Multi-turn (3 steps)
```
Turn 1 - Request:
User: "Create a literature review using the above 5 references"
AI: "I'd be happy to help! A few questions:
     1. What theme should tie these papers together?
     2. How long - brief (2 pages) or comprehensive (5+ pages)?
     3. Structure preference (thematic, chronological, methodological)?"

Turn 2 - Clarification:
User: "Algorithm design, 2 pages, thematic"
AI: "Got it - 2-page thematic review on algorithm design. Create as paper or write in chat?"

Turn 3 - Execution:
User: "chat"
AI: [Writes the full literature review]
```

**Output options:**
- Write in chat
- Create as new paper (with create_paper action)

---

### 2.2 Create Summary
**Intent:** User wants a summary of one or more papers
**Examples:**
- "Summarize this paper"
- "Give me a brief summary of these 3 papers"
- "What are the key points of the VAN paper?"

**Flow:** Single turn OR multi-turn
```
Simple (single turn):
User: "Summarize the first paper"
AI: [Writes summary directly]

Complex (multi-turn):
User: "Summarize these papers"
AI: "What should I focus on - methodology, results, or contributions?"
User: "Methodology"
AI: [Writes methodology-focused summary]
```

---

### 2.3 Create Outline
**Intent:** User wants an outline for a paper/section
**Examples:**
- "Create an outline for my introduction"
- "Draft an outline for a survey paper on transformers"
- "Help me structure my methodology section"

**Flow:** Multi-turn
```
User: "Create an outline for my literature review section"
AI: "What's the main topic and how many subsections do you want?"
User: "Vision transformers, 4 subsections"
AI: [Creates outline] "Create as paper or in chat?"
```

---

### 2.4 Write Section
**Intent:** User wants to write a specific section
**Examples:**
- "Write an introduction for my paper"
- "Draft the methodology section"
- "Write a conclusion summarizing these findings"

**Flow:** Multi-turn
```
User: "Write an introduction for my paper on ViT"
AI: "What should the introduction cover?
     1. What problem are you addressing?
     2. What's your contribution?
     3. How long should it be?"
User: "Comparing ViT variants, our contribution is a new benchmark, 1 page"
AI: [Writes introduction] "Create as paper or in chat?"
```

---

## 3. Paper Editing

### 3.1 Edit Existing Paper
**Intent:** User wants to modify their paper
**Examples:**
- "Make the introduction more concise"
- "Add a paragraph about related work"
- "Fix the grammar in the abstract"

**Flow:** Single turn with edit_paper action
```
User: "Make the introduction shorter"
AI: "I'll condense the introduction." [+ edit_paper action with original/proposed]
```

---

### 3.2 Improve Writing
**Intent:** User wants writing improvements
**Examples:**
- "Improve the flow of this paragraph"
- "Make this more academic"
- "Rewrite this to be clearer"

**Flow:** Single turn
```
User: "Make this paragraph clearer: [paste text]"
AI: [Returns improved text]
```

---

### 3.3 Add Citations
**Intent:** User wants to add references to their text
**Examples:**
- "Add citations to support this claim"
- "Which of my references supports this statement?"
- "Insert a citation for the VAN paper here"

**Flow:** Single turn
```
User: "Add a citation for the attention mechanism claim"
AI: "Based on your references, [Paper X] supports this. [+ edit suggestion]"
```

---

## 4. Analysis & Explanation

### 4.1 Explain Paper/Concept
**Intent:** User wants to understand something
**Examples:**
- "Explain how self-attention works"
- "What is the main contribution of the VAN paper?"
- "How does this paper's method differ from standard CNNs?"
- "What are our project objectives?"
- "Summarize what my paper says about methodology"

**Flow:** Single turn

**Sources (in priority order):**
1. **Discovered references** - Papers from recent search results
2. **Project references** - Papers saved in project library
3. **Project papers** - Papers being written by the user
4. **Project info** - Project objectives, description, scope

```
User: "Explain the main contribution of the first paper"
AI: [Uses discovered references if available, else project refs]

User: "What does my paper say about attention?"
AI: [Uses project papers - the user's own writing]

User: "What are our project goals?"
AI: [Uses project info - objectives/scope]
```

**Context Selection Logic:**
```
IF question mentions "discovered/found/above papers" → use recent_search_results
ELIF question mentions "my paper/our paper" → use project_papers
ELIF question mentions "project/objectives/goals" → use project_info
ELIF question mentions specific paper title → find in all sources
ELSE → use all available context
```

---

### 4.2 Compare Papers
**Intent:** User wants to compare multiple papers
**Examples:**
- "Compare the first and third papers"
- "What are the differences between these approaches?"
- "Which paper has better results?"

**Flow:** Single turn or multi-turn
```
User: "Compare the methodologies of papers 1 and 3"
AI: [Provides comparison table/analysis]
```

---

### 4.3 Identify Gaps
**Intent:** User wants to find research gaps
**Examples:**
- "What gaps exist in this research area?"
- "What's missing from these papers?"
- "What could be future work based on these?"

**Flow:** Single turn
```
User: "What research gaps do you see in these papers?"
AI: [Analyzes and identifies gaps]
```

---

## 5. Task Management

### 5.1 Create Task
**Intent:** User wants to create a task/todo
**Examples:**
- "Create a task to review the VAN paper"
- "Add a todo: read methodology section of paper 2"
- "Remind me to add more citations"

**Flow:** Single turn with create_task action
```
User: "Create a task to review the methodology of paper 1"
AI: "I'll create that task." [+ create_task action]
```

---

### 5.2 Suggest Tasks
**Intent:** User wants task suggestions
**Examples:**
- "What should I work on next?"
- "Suggest tasks based on my paper progress"
- "What's missing from my paper?"

**Flow:** Single turn
```
User: "What should I work on next for my paper?"
AI: "Based on your paper, I suggest:
     1. Add more references to section 2
     2. Expand the methodology
     3. Write the conclusion"
```

---

## 6. Conversation & Help

### 6.1 General Chat
**Intent:** Greetings, thanks, general questions
**Examples:**
- "Hi"
- "Thanks!"
- "What can you help me with?"

**Flow:** Single turn
```
User: "Hello"
AI: "Hello! I can help you search for papers, create literature reviews,
     summarize research, and more. What would you like to do?"
```

---

### 6.2 Clarification
**Intent:** User needs clarification on AI's response
**Examples:**
- "What do you mean?"
- "Can you explain that more?"
- "I don't understand"

**Flow:** Single turn
```
User: "What do you mean by thematic structure?"
AI: "Thematic structure organizes the review by topics/themes rather than
     chronologically or by methodology..."
```

---

## 7. Context-Aware Features

### 7.1 Use Project References
**Intent:** User wants to use papers from their library
**Examples:**
- "Use my project references to write about attention"
- "What do my saved papers say about this?"
- "Cite from my library"

**Flow:** Requires project_references context
```
User: "What do my references say about transformers?"
AI: [Searches project library, synthesizes answer]
```

---

### 7.2 Reference Meeting Transcripts
**Intent:** User wants to use meeting notes
**Examples:**
- "What did we discuss about the methodology?"
- "Summarize our last meeting"
- "What action items came from the meeting?"

**Flow:** Requires meeting_transcripts context
```
User: "What did we decide about the experiment design?"
AI: [References transcript] "In your meeting on [date], you discussed..."
```

---

## Multi-Turn Strategy

**Principle:** Smart multi-turn - only ask for missing information.

### Required Parameters by Use Case

| Use Case | Required Params | If Missing → Ask |
|----------|-----------------|------------------|
| Search | query, count | Only query (count defaults to 5) |
| Lit Review | theme, length, structure, output | Ask missing ones |
| Summary | target (which paper), focus | Ask if ambiguous |
| Write Section | section_type, scope, length | Ask missing ones |
| Edit Paper | paper_id, change description | Usually provided |
| Explain | topic/paper | Usually provided |
| Compare | paper_ids (which to compare) | Ask if not clear |

### Smart Multi-Turn Flow

```
1. Parse user message for parameters
2. Check what's missing
3. IF nothing missing → execute immediately
   ELSE → ask ONLY for missing params (not full questionnaire)
4. On user response → merge with existing params → execute
```

**Example - Full Info Provided:**
```
User: "Create a 2-page thematic literature review about attention, in chat"
AI: [Executes immediately - all params present]
```

**Example - Partial Info:**
```
User: "Create a literature review about attention"
AI: "How long (2 pages brief, or 5+ comprehensive)? And create as paper or write in chat?"
[Only asks missing: length + output format. Theme already known.]
```

---

## Integration Matrix

| Use Case | ScholarHub Integration | Data Needed |
|----------|----------------------|-------------|
| **Search** | PaperDiscoveryService | None (external search) |
| **Lit Review** | - | recent_search_results |
| **Summary** | Reference model | reference.abstract, reference.content |
| **Edit Paper** | ResearchPaper model | paper.content, paper.id |
| **Add Citations** | ProjectReference model | project references list |
| **Explain** | Reference model | reference.abstract |
| **Create Task** | ProjectDiscussionTask model | Creates new task |
| **Project Refs** | ProjectReference model | All project references |
| **Meetings** | Meeting model | meeting.transcript, meeting.summary |

### Integration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DiscussionOrchestrator                    │
└─────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  ContextManager │  │  ActionExecutor │  │   StateManager  │
│                 │  │                 │  │                 │
│ Loads from DB:  │  │ Executes:       │  │ Tracks:         │
│ - References    │  │ - search_refs   │  │ - Current skill │
│ - Papers        │  │ - create_paper  │  │ - Skill state   │
│ - Meetings      │  │ - edit_paper    │  │ - Params so far │
│ - Search results│  │ - create_task   │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    Existing Models/Services                  │
│  Reference | ResearchPaper | Meeting | Task | Discovery     │
└─────────────────────────────────────────────────────────────┘
```

---

## Test Matrix

| Use Case | Intent | Multi-turn | Needs Search Results | Needs Papers | Needs Refs |
|----------|--------|------------|---------------------|--------------|------------|
| 1.1 Search | SEARCH | No | No | No | No |
| 1.2 Refine Search | SEARCH | Yes | Yes | No | No |
| 2.1 Lit Review | CREATE_CONTENT | Smart | Yes | No | No |
| 2.2 Summary | CREATE_CONTENT | Smart | Yes | No | No |
| 2.3 Outline | CREATE_CONTENT | Smart | Maybe | Yes | No |
| 2.4 Write Section | CREATE_CONTENT | Smart | Maybe | Yes | No |
| 3.1 Edit Paper | EDIT_PAPER | No | No | Yes | No |
| 3.2 Improve Writing | EDIT_PAPER | No | No | No | No |
| 3.3 Add Citations | EDIT_PAPER | No | No | Yes | Yes |
| 4.1 Explain | EXPLAIN | No | Yes | No | Yes |
| 4.2 Compare | EXPLAIN | Smart | Yes | No | No |
| 4.3 Identify Gaps | EXPLAIN | No | Yes | No | No |
| 5.1 Create Task | TASK | No | No | No | No |
| 5.2 Suggest Tasks | TASK | No | No | Yes | No |
| 6.1 Chat | CHAT | No | No | No | No |
| 6.2 Clarification | CONTINUATION | No | Inherit | Inherit | Inherit |
| 7.1 Use Project Refs | EXPLAIN | No | No | No | Yes |
| 7.2 Meeting Transcripts | EXPLAIN | No | No | No | No |

---

## Priority for MVP

### P0 - Must Have (Core Flow)
- [ ] 1.1 Search for References
- [ ] 2.1 Create Literature Review
- [ ] 4.1 Explain Paper/Concept
- [ ] 6.1 General Chat

### P1 - Should Have
- [ ] 2.2 Create Summary
- [ ] 3.1 Edit Existing Paper
- [ ] 4.2 Compare Papers
- [ ] 5.1 Create Task

### P2 - Nice to Have
- [ ] 1.2 Refine Search Results
- [ ] 2.3 Create Outline
- [ ] 2.4 Write Section
- [ ] 3.2 Improve Writing
- [ ] 3.3 Add Citations
- [ ] 4.3 Identify Gaps
- [ ] 5.2 Suggest Tasks
- [ ] 7.1 Use Project References
- [ ] 7.2 Reference Meeting Transcripts
