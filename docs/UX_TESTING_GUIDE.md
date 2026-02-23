# ScholarHub - Comprehensive UX Testing Guide

**Date:** 2026-02-23
**Purpose:** Manual testing of all features to ensure complete coverage before demo/submission.

> **How to use:** Go through each section sequentially. Check off items as you test them. Note any bugs or issues in the "Notes" column.

---

## Prerequisites

- [ ] Docker services running (`docker compose up -d`)
- [ ] Frontend accessible at `http://localhost:3000`
- [ ] Backend accessible at `http://localhost:8000`
- [ ] At least one user account created
- [ ] At least one project with papers, references, and discussion channels

---

## 1. PUBLIC PAGES (No Auth Required)

### 1.1 Landing Page (`/`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open `/` in browser | Landing page loads with hero section | | |
| 2 | Check hero title and subtitle | "Write and publish research papers, together" visible | | |
| 3 | Click "Start for free" button | Navigates to `/register` | | |
| 4 | Click "See what's inside" button | Scrolls to features section | | |
| 5 | Click each showcase tab (LaTeX Editor, AI Assistant, Reference Library, Project Dashboard) | Screenshot changes for each tab | | |
| 6 | Verify only active tab image loads eagerly | Check Network tab — inactive tab images should lazy-load | | |
| 7 | Scroll down to Platform Highlights section | Feature pills animate in on scroll | | |
| 8 | Scroll to Features section | 6 feature cards visible with icons | | |
| 9 | Verify LaTeX feature mentions Tectonic engine | Check collaboration card text mentions "Tectonic engine, full package support, and live PDF preview" | | |
| 10 | Scroll to "How it Works" section | 4 workflow steps visible | | |
| 11 | Scroll to final CTA section | "Ready to transform your research workflow?" visible | | |
| 12 | Check final CTA button on mobile viewport | No janky scale effect on hover (no `scale-105` on full-width) | | |
| 13 | Scroll to About section | "Built by researchers, for researchers" with specific story text | | |
| 14 | Check About section uses em dashes | Proper `—` characters, not `--` | | |
| 15 | Check footer links (Features, How it works, Pricing, Contact, Privacy, Terms) | All links navigate correctly | | |
| 16 | Test dark mode (if toggle available) | All sections render properly in dark mode | | |
| 17 | Test responsive (resize to mobile width ~375px) | Layout adapts, no horizontal overflow | | |
| 18 | Click nav "Features" link | Scrolls to features section smoothly | | |
| 19 | Click nav "How it Works" link | Scrolls to how-it-works section | | |
| 20 | Click nav "Sign in" | Navigates to `/login` | | |

### 1.2 Pricing Page (`/pricing`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open `/pricing` | Pricing page loads with 3 tier cards | | |
| 2 | Verify Free tier card | Shows $0/month, features list, "Get Started Free" button | | |
| 3 | Verify Pro tier card | Shows "Coming Soon" badge (NOT "Most Popular") | | |
| 4 | Click Pro "Coming Soon - Notify Me" button | Opens informational modal (NOT mailto link) | | |
| 5 | In Pro modal, click "Try BYOK Instead" | Navigates to `/profile` | | |
| 6 | Verify BYOK tier card | Shows "$0 + your API costs", explains bring-your-own-key | | |
| 7 | Verify CTA section text | Says "Start using ScholarHub..." (NOT "Join thousands of researchers") | | |
| 8 | Expand FAQ questions | Each FAQ expands/collapses | | |
| 9 | Verify FAQ has "When will Pro be available?" | Honest answer about being in development | | |
| 10 | Verify FAQ has "Is the free plan really free?" | Honest answer about free tier + BYOK | | |
| 11 | Check feature comparison table | All 3 tiers compared correctly | | |
| 12 | Test responsive layout | Cards stack on mobile | | |

### 1.3 Privacy Policy (`/privacy`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open `/privacy` | Privacy policy page renders | | |
| 2 | Content is readable and complete | No placeholder text | | |

### 1.4 Terms of Service (`/terms`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open `/terms` | Terms page renders | | |
| 2 | Content is readable and complete | No placeholder text | | |

---

## 2. AUTHENTICATION

### 2.1 Registration (`/register`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open `/register` | Registration form loads | | |
| 2 | Submit empty form | Validation errors shown | | |
| 3 | Enter invalid email | Email validation error | | |
| 4 | Enter mismatched passwords | Password mismatch error | | |
| 5 | Enter weak password | Password strength indicator shows weak | | |
| 6 | Register with valid data | Success, verification pending screen shown | | |
| 7 | Try registering with same email | "Email already registered" error | | |
| 8 | Click Google Sign-In button | Google OAuth flow initiates | | |

### 2.2 Login (`/login`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open `/login` | Login form loads | | |
| 2 | Submit empty form | Validation errors | | |
| 3 | Enter wrong credentials | "Incorrect email or password" error | | |
| 4 | Enter correct credentials | Login successful, redirected to `/projects` | | |
| 5 | Click "Forgot password?" | Navigates to `/forgot-password` | | |
| 6 | Click Google Sign-In | Google OAuth flow | | |
| 7 | After login, refresh page | Session persists (token in localStorage) | | |

### 2.3 Forgot Password (`/forgot-password`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Enter registered email | Success message: "Check your email" | | |
| 2 | Enter unregistered email | Appropriate error or generic success (security) | | |
| 3 | Click back button | Returns to login | | |

### 2.4 Email Verification (`/verify-email`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open with valid token in URL | Auto-verifies and shows success | | |
| 2 | Open without token | Shows manual email entry form | | |
| 3 | Click "Resend verification" | Sends new verification email | | |

### 2.5 Logout
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Click settings/user icon | Settings modal appears | | |
| 2 | Click Logout | Session cleared, redirected to `/login` | | |
| 3 | Try accessing `/projects` after logout | Redirected to `/login` | | |

---

## 3. USER PROFILE (`/profile`)

| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open `/profile` | Profile page loads with user info | | |
| 2 | Edit first name and last name | Changes save successfully | | |
| 3 | Upload avatar image | Avatar updates, visible in nav | | |
| 4 | Delete avatar | Avatar removed, default shown | | |
| 5 | Check email verification status | Badge shows verified/unverified | | |
| 6 | Click "Resend verification" (if unverified) | Verification email sent | | |
| 7 | Change password (enter current + new) | Password updated successfully | | |
| 8 | Enter wrong current password | Error shown | | |
| 9 | Check subscription section | Current tier displayed (Free) | | |
| 10 | Enter OpenRouter API key | Key saved, masked display shown | | |
| 11 | Delete OpenRouter API key | Key removed | | |
| 12 | Enter Zotero API key + User ID | Integration configured | | |
| 13 | Delete Zotero integration | Integration removed | | |

---

## 4. PROJECTS

### 4.1 Projects Home (`/projects`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open `/projects` | Project list loads | | |
| 2 | Toggle between Grid and Table view | Layout changes correctly | | |
| 3 | Filter by "All" / "My" / "Shared" tabs | Projects filter correctly | | |
| 4 | Type in search bar | Projects filter by name | | |
| 5 | Sort by "Updated" / "Created" / "Title" | Sort order changes | | |
| 6 | Click pin icon on a project | Project moves to pinned section | | |
| 7 | Click Refresh button | Projects reload from server | | |

### 4.2 Create Project
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Click "Create Project" button | Project form modal opens | | |
| 2 | Submit with empty title | Validation error | | |
| 3 | Fill title, description, keywords, objectives | Project creates successfully | | |
| 4 | Verify project appears in list | New project visible | | |

### 4.3 Edit Project
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Click edit button on project card | Edit modal opens with pre-filled data | | |
| 2 | Change title and description | Changes saved | | |
| 3 | Add/remove keywords | Keywords updated | | |
| 4 | Add/remove objectives | Objectives updated | | |

### 4.4 Delete Project
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Click delete button on project | Confirmation dialog appears | | |
| 2 | Confirm deletion | Project removed from list | | |
| 3 | Cancel deletion | Project remains | | |

---

## 5. PROJECT OVERVIEW (`/projects/:id/overview/dashboard`)

### 5.1 Dashboard Tab
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Navigate to project overview | Dashboard tab loads with project info | | |
| 2 | Verify project title and description | Correct data displayed | | |
| 3 | Check Project Stats (Papers, References, Members counts) | Numbers are accurate | | |
| 4 | View Objectives section | Objectives listed with progress percentage | | |
| 5 | Click objective checkbox to mark complete | Status updates, progress bar changes | | |
| 6 | View Team section | Team members listed with roles | | |
| 7 | Click "Invite member" | Invite modal opens | | |
| 8 | Invite by email with role selection | Invitation sent | | |
| 9 | Click "Manage" in Team section | Member management options visible | | |
| 10 | Change member role (Admin/Editor/Viewer) | Role updates | | |
| 11 | Remove a member | Member removed with confirmation | | |
| 12 | Click "Edit project" button | Edit modal opens | | |
| 13 | Click "Settings" button | Project settings modal opens | | |
| 14 | Click "Delete" button | Delete confirmation appears | | |

### 5.2 Project Settings Modal
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open project settings | Settings modal loads | | |
| 2 | Change AI model selection | Model updates | | |
| 3 | Toggle "use owner key for team" | Setting saved | | |

### 5.3 Meetings Tab
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Switch to Meetings tab | Meetings interface loads | | |
| 2 | Create a new meeting/sync session | Video room created | | |
| 3 | Join meeting | Jitsi/Daily video UI loads | | |
| 4 | Test mute/camera/screen share controls | Controls work | | |
| 5 | End meeting | Session ends, recording available (if enabled) | | |

---

## 6. PROJECT DISCUSSION (`/projects/:id/discussion`)

### 6.1 Channel Management
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open Discussion page | Channel sidebar loads with channels | | |
| 2 | Click "+" to create new channel | Channel creation form appears | | |
| 3 | Enter channel name and create | New channel appears in sidebar | | |
| 4 | Click on a channel | Channel messages load in main area | | |
| 5 | Right-click/context menu on channel | Options: settings, archive, delete | | |
| 6 | Open channel settings | Settings modal with name, description, scope | | |
| 7 | Archive a channel | Channel moves to archived section | | |
| 8 | Toggle archived channels view | Archived channels visible | | |
| 9 | Delete a channel | Channel removed (with confirmation) | | |

### 6.2 Messaging
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Type message in input field | Text appears, auto-resize works | | |
| 2 | Press Enter to send | Message sent and appears in chat | | |
| 3 | Press Shift+Enter | New line in message (not send) | | |
| 4 | Send empty message | Nothing happens (prevented) | | |
| 5 | Hover over sent message | Action buttons appear (edit, delete) | | |
| 6 | Edit a message | Edit mode activates, save changes | | |
| 7 | Delete a message | Message removed (with confirmation) | | |
| 8 | Send a long message | Message wraps properly | | |

### 6.3 AI Assistant
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | First visit shows welcome modal | AI assistant introduction modal appears | | |
| 2 | Send a message to AI (e.g., "hello") | AI responds in chat | | |
| 3 | Click model selector dropdown | Available models listed (GPT, Claude, Gemini, etc.) | | |
| 4 | Switch AI model | Model changes, next response uses new model | | |
| 5 | Toggle reasoning mode | Reasoning indicator shown | | |
| 6 | Ask AI to search for papers (e.g., "find papers about transformer architectures") | AI performs search, shows results with citations | | |
| 7 | Ask AI to add a paper to library | Paper added to project library | | |
| 8 | Ask AI to compare two papers | AI provides structured comparison | | |
| 9 | Ask AI to generate an abstract | AI generates abstract based on paper content | | |
| 10 | Ask AI to suggest research gaps | AI analyzes and suggests gaps | | |
| 11 | Ask AI about project references | AI accesses library and responds with context | | |
| 12 | Ask AI to update project objectives | Objectives updated through AI | | |
| 13 | Verify AI citations link to actual papers | Clicking citations opens paper details | | |
| 14 | Test AI memory (reference earlier conversation) | AI remembers context from earlier in conversation | | |

### 6.4 Channel Resources Panel
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open resource panel | Panel slides open | | |
| 2 | Add a paper as resource | Paper attached to channel | | |
| 3 | Add a reference as resource | Reference attached | | |
| 4 | Remove a resource | Resource detached | | |
| 5 | Toggle resource scope (Papers, References, Transcripts) | Scope filter works | | |

### 6.5 Channel Artifacts
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | After AI generates content, check artifacts panel | Generated artifacts listed | | |
| 2 | Click on an artifact | Artifact detail view opens | | |
| 3 | Delete an artifact | Artifact removed | | |

### 6.6 Tasks
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open task drawer | Task panel slides open | | |
| 2 | Click "Create task" | Task creation form appears | | |
| 3 | Create a task with title | Task added to list | | |
| 4 | Toggle task status (Open → In Progress → Completed) | Status updates with icon | | |
| 5 | Delete a task | Task removed | | |

### 6.7 Discovery Queue
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Check discovery queue panel | Shows pending discovery results | | |
| 2 | Promote a discovered paper | Paper moves to project library | | |
| 3 | Dismiss a discovered paper | Paper removed from queue | | |

---

## 7. PROJECT LIBRARY (`/projects/:id/library`)

### 7.1 Discover Tab (`/library/discover`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open Discover tab | Discovery UI loads | | |
| 2 | Enter search query (e.g., "deep learning medical imaging") | Results load from academic databases | | |
| 3 | Toggle between Query Mode and Paper Mode | Search mode switches | | |
| 4 | Select/deselect sources (Semantic Scholar, OpenAlex, arXiv, etc.) | Source toggles work | | |
| 5 | Adjust max results slider | Slider moves, value updates | | |
| 6 | Change sort order (Relevance, Year, Citations) | Results reorder | | |
| 7 | Adjust relevance threshold filter | Lower-relevance results hidden/shown | | |
| 8 | Toggle "PDF only" filter | Only papers with PDFs shown | | |
| 9 | Toggle "Deep rescoring" | Rescoring indicator appears | | |
| 10 | Set year filter | Papers outside range hidden | | |
| 11 | View result card details (title, authors, abstract, year, citations) | All metadata displayed correctly | | |
| 12 | Check relevance score badge | Score percentage visible | | |
| 13 | Check open access badge | OA badge shown for open access papers | | |
| 14 | Click "Add to project" on a result | Paper added to project library | | |
| 15 | Click "View PDF" on a result | PDF opens in new tab (if available) | | |

### 7.2 References Tab (`/library/references`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open References tab | Reference list loads | | |
| 2 | Verify reference count badge | Count matches actual references | | |
| 3 | View reference details (title, authors, DOI, journal, year) | All metadata shown | | |
| 4 | Add a new reference manually | Reference form opens and saves | | |
| 5 | Delete a reference | Reference removed with confirmation | | |
| 6 | Import BibTeX file | References imported from .bib file | | |
| 7 | Export BibTeX | BibTeX file downloads | | |

---

## 8. PAPERS

### 8.1 Papers List (`/projects/:id/papers`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open Papers page | Paper list loads | | |
| 2 | Search by title | Papers filter correctly | | |
| 3 | Filter by category (Literature Review, Research, etc.) | Filter works | | |
| 4 | Filter by editor type (LaTeX, Rich) | Filter works | | |
| 5 | Sort (Newest, Oldest, Title A-Z, Z-A) | Sort order changes | | |
| 6 | Click "Create New Paper" | Navigates to paper creation wizard | | |
| 7 | Click on a paper card | Opens paper detail | | |

### 8.2 Create Paper with Template (`/projects/:id/papers/new`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Step 1: Enter paper title | Title input works | | |
| 2 | Select template type (Research, Lit Review, Thesis, etc.) | Template selected | | |
| 3 | Add keywords | Keywords tag input works | | |
| 4 | Select objectives from project | Checkboxes work | | |
| 5 | Step 2: Select venue format (IEEE, ACM, NeurIPS, etc.) | Template updates | | |
| 6 | Enable/disable sections | Section toggles work | | |
| 7 | Toggle raw LaTeX editor | Raw LaTeX visible and editable | | |
| 8 | Step 3: Review summary | All selections shown correctly | | |
| 9 | Click "Create" | Paper created, navigated to editor | | |

### 8.3 Paper Detail (`/projects/:id/papers/:paperId`)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | View paper title and metadata | Title, status, type displayed | | |
| 2 | Edit paper title (if admin/editor) | Title updates | | |
| 3 | Change paper status (Draft/In Progress/Completed/Published) | Status badge updates | | |
| 4 | View attached references | References listed | | |
| 5 | Click "Add reference" | Reference picker modal opens | | |
| 6 | Attach a reference to paper | Reference appears in list | | |
| 7 | Remove a reference | Reference detached | | |
| 8 | Upload PDF for a reference | PDF uploaded and linked | | |
| 9 | View paper stats (word count, dates) | Stats displayed | | |
| 10 | Click "Edit" button | Opens editor | | |
| 11 | Click "View" button | Opens read-only view | | |
| 12 | Invite team member to paper | Team invite modal opens | | |
| 13 | Delete paper | Confirmation dialog, paper deleted | | |

---

## 9. LATEX EDITOR (`/projects/:id/papers/:paperId/editor`)

### 9.1 Editor Basics
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open LaTeX paper in editor | CodeMirror editor loads with LaTeX content | | |
| 2 | Type LaTeX code | Code appears with syntax highlighting | | |
| 3 | Verify auto-save indicator | "Saving..." and "Saved" status shown | | |
| 4 | Check PDF preview pane | PDF renders on right side | | |
| 5 | Click "Recompile" button | LaTeX recompiles, PDF updates | | |
| 6 | Introduce a LaTeX error (e.g., unclosed brace) | Error markers appear, error list shows | | |
| 7 | Fix the error | Error markers clear | | |
| 8 | Check word count | Word count updates as you type | | |

### 9.2 Editor Panels & Tools
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open Outline panel | Document structure tree visible | | |
| 2 | Click on outline section | Editor scrolls to that section | | |
| 3 | Open Symbol palette | LaTeX symbols displayed | | |
| 4 | Click a symbol | Symbol inserted at cursor | | |
| 5 | Type `\cite{` | Citation suggestions appear | | |
| 6 | Select a citation suggestion | Citation key inserted | | |
| 7 | Open toolbar | Formatting buttons visible | | |
| 8 | Use toolbar buttons (bold, italic, section, etc.) | LaTeX commands inserted | | |

### 9.3 PDF Preview
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | PDF renders after compilation | Full document PDF visible | | |
| 2 | Zoom controls work | PDF zooms in/out | | |
| 3 | Page navigation works | Can navigate between pages | | |
| 4 | Click in PDF to jump to source (SyncTeX) | Editor scrolls to matching source line | | |
| 5 | Click in editor to jump to PDF (forward search) | PDF scrolls to matching position | | |

### 9.4 Figure & Citation Dialogs
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open figure upload dialog | File picker appears | | |
| 2 | Upload an image | Image uploaded, LaTeX figure code inserted | | |
| 3 | Open citation dialog | Reference search appears | | |
| 4 | Search and select reference | Citation inserted in LaTeX | | |

### 9.5 Version History
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open versions modal | Version history listed | | |
| 2 | View a previous version | Version content shown | | |
| 3 | Restore a previous version | Paper content reverts | | |
| 4 | Create manual snapshot | New version saved | | |

### 9.6 Branching (Git-like)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open branch manager | Current branch shown | | |
| 2 | Create a new branch | Branch created from current state | | |
| 3 | Switch between branches | Editor content changes to branch content | | |
| 4 | Make edits on branch | Changes saved to branch only | | |
| 5 | Create merge request | MR created for review | | |
| 6 | View merge diff | Changes highlighted | | |
| 7 | Merge branch | Content merged to target branch | | |
| 8 | Delete branch | Branch removed | | |

### 9.7 AI Chat in Editor
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Toggle AI Chat sidebar | Chat panel opens/closes | | |
| 2 | Send a message to editor AI | AI responds with context about paper | | |
| 3 | Ask AI to improve a section | AI suggests edits | | |
| 4 | Accept an AI edit proposal | Edit applied to document | | |
| 5 | Reject an AI edit proposal | Edit discarded | | |
| 6 | Ask AI to explain selected text | AI provides explanation | | |
| 7 | Switch AI model in editor | Model changes | | |

### 9.8 Collaboration (Multi-user)
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open same paper in two browsers (different users) | Both editors load | | |
| 2 | Type in one editor | Changes appear in other editor in real-time | | |
| 3 | Check collaborative cursors | Other user's cursor visible with label | | |
| 4 | Check section locking | Editing locked section shows indicator | | |

### 9.9 Export Options
| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Export as PDF | PDF downloads | | |
| 2 | Export as DOCX | DOCX file downloads | | |
| 3 | Export LaTeX source as ZIP | ZIP with .tex and assets downloads | | |
| 4 | Open submission builder | Venue selection and export options shown | | |
| 5 | Validate for submission venue | Validation report generated | | |

---

## 10. RICH TEXT EDITOR (OnlyOffice)

| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Create a Rich Text paper and open in editor | OnlyOffice editor loads | | |
| 2 | Type text with formatting (bold, italic, lists) | Formatting works | | |
| 3 | Track changes toggle | Track changes mode activates | | |
| 4 | Add inline comments | Comment appears in margin | | |
| 5 | Multi-user editing | Real-time sync between users | | |
| 6 | Export as PDF | PDF downloads | | |

---

## 11. VIEW PAPER (Read-Only) (`/projects/:id/papers/:paperId/view`)

| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open paper in view mode | PDF viewer loads (LaTeX) or read-only OnlyOffice (Rich Text) | | |
| 2 | Navigate PDF pages | Page navigation works | | |
| 3 | Zoom controls | Zoom works | | |
| 4 | Back button | Returns to paper detail | | |

---

## 12. REFERENCES LIBRARY (`/my-references`)

| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open My References | Reference list loads | | |
| 2 | Search references by title | Filter works | | |
| 3 | Click "Add Reference" | Manual entry form appears | | |
| 4 | Fill title, authors, year, DOI, journal | Reference saves | | |
| 5 | Upload PDF for reference | PDF attached | | |
| 6 | Click "Zotero Import" | Zotero import modal opens | | |
| 7 | Select Zotero collection | Items from collection listed | | |
| 8 | Import selected items | References added to library | | |
| 9 | Delete a reference | Reference removed | | |
| 10 | Check PDF ingestion status banner | Shows pending PDFs being processed | | |

---

## 13. NOTIFICATIONS

| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Check notification icon in nav | Notification count badge visible (if any) | | |
| 2 | Click notifications | Notification dropdown/panel opens | | |
| 3 | Trigger a notification (e.g., receive invitation) | Notification appears | | |
| 4 | Mark notification as read | Unread indicator clears | | |

---

## 14. PROJECT INVITATIONS

| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Invite user to project by email | Invitation sent | | |
| 2 | Check pending invitations list | Invitation shown as pending | | |
| 3 | Cancel a pending invitation | Invitation removed | | |
| 4 | As invited user, view pending invitations | Invitation visible | | |
| 5 | Accept invitation | User added to project | | |
| 6 | Decline invitation | Invitation dismissed | | |

---

## 15. COMMAND PALETTE

| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Press Cmd+K (or Ctrl+K) | Command palette opens | | |
| 2 | Type project name | Fuzzy search shows matching projects | | |
| 3 | Type paper name | Matching papers shown | | |
| 4 | Select result | Navigates to selected item | | |
| 5 | Press Escape | Palette closes | | |

---

## 16. SUBSCRIPTION & LIMITS

| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Check current tier on profile | Tier shown (Free/Pro/BYOK) | | |
| 2 | View usage stats | Current usage vs limits displayed | | |
| 3 | Trigger a limit (e.g., create projects up to limit) | Upgrade modal appears | | |
| 4 | Switch to BYOK tier | Tier changes, AI calls unlimited with own key | | |

---

## 17. DARK MODE & ACCESSIBILITY

| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Toggle dark mode | All pages switch to dark theme | | |
| 2 | Check text contrast in dark mode | Text readable against dark backgrounds | | |
| 3 | Check buttons/inputs in dark mode | All interactive elements visible | | |
| 4 | Test keyboard navigation | Tab through all interactive elements | | |
| 5 | Test on mobile viewport (375px) | All pages responsive, no overflow | | |
| 6 | Test on tablet viewport (768px) | Layout adapts correctly | | |

---

## 18. EDGE CASES & ERROR HANDLING

| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Access non-existent project URL | "Project unavailable" error page | | |
| 2 | Access project you don't have permission to | Access denied message | | |
| 3 | Session expiry (wait for token to expire) | Auto-refresh or redirect to login | | |
| 4 | Network offline — try sending message | Graceful error, no crash | | |
| 5 | Upload oversized file (>10MB) | File size error shown | | |
| 6 | Upload wrong file type | File type error shown | | |
| 7 | Very long project/paper title | Text truncated properly, no layout break | | |
| 8 | Empty project (no papers, no references) | Empty state messages shown | | |
| 9 | Rate limit on login (10+ attempts/minute) | Rate limit error shown | | |

---

## 19. ANNOTATIONS (PDF)

| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open a reference PDF with annotation viewer | PDF loads with annotation tools | | |
| 2 | Create a highlight annotation | Text highlighted | | |
| 3 | Add a note annotation | Note pin appears | | |
| 4 | Edit an annotation | Annotation updated | | |
| 5 | Delete an annotation | Annotation removed | | |

---

## 20. WRITING ANALYSIS

| # | Test | Expected Result | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Open writing analysis panel in editor | Panel loads | | |
| 2 | Run grammar check | Grammar issues highlighted | | |
| 3 | View readability metrics | Metrics displayed | | |
| 4 | Apply AI suggestion | Text updated | | |

---

## Bug Tracking

| # | Page/Feature | Bug Description | Severity (Critical/High/Medium/Low) | Screenshot |
|---|-------------|----------------|--------------------------------------|------------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| 7 | | | | |
| 8 | | | | |
| 9 | | | | |
| 10 | | | | |

---

## Summary Checklist

| Area | Total Tests | Passed | Failed | Skipped |
|------|-------------|--------|--------|---------|
| Public Pages | 32 | | | |
| Authentication | 20 | | | |
| User Profile | 13 | | | |
| Projects CRUD | 14 | | | |
| Project Overview | 18 | | | |
| Discussion | 30 | | | |
| Library/Discovery | 22 | | | |
| Papers CRUD | 20 | | | |
| LaTeX Editor | 36 | | | |
| Rich Text Editor | 6 | | | |
| View Paper | 4 | | | |
| References Library | 10 | | | |
| Notifications | 4 | | | |
| Invitations | 6 | | | |
| Command Palette | 5 | | | |
| Subscription | 4 | | | |
| Dark Mode & A11y | 6 | | | |
| Edge Cases | 9 | | | |
| Annotations | 5 | | | |
| Writing Analysis | 4 | | | |
| **TOTAL** | **~268** | | | |

---

*Generated from codebase analysis on 2026-02-23. Covers 262+ API endpoints, 32 database models, 28+ AI tools, and all frontend components.*
