# LaTeX Editor Overhaul Plan

> Audit date: 2026-02-05
> Status: Planning

---

## Table of Contents

1. [Architecture Overview (Current)](#1-architecture-overview-current)
2. [Critical Bugs](#2-critical-bugs)
3. [Architectural Problems](#3-architectural-problems)
4. [Backend Issues](#4-backend-issues)
5. [Overleaf Feature Gap](#5-overleaf-feature-gap)
6. [Target Architecture](#6-target-architecture)
7. [Execution Plan](#7-execution-plan)

---

## 1. Architecture Overview (Current)

### Component Hierarchy

```
PaperEditor (Page)
  └─> DocumentShell (Orchestrator)
       ├─> LatexAdapter (Wrapper)
       │    └─> LaTeXEditor (2,130-line God Component)
       │         ├─> CodeMirror 6 View
       │         │    ├─ StreamLanguage (stex legacy mode)
       │         │    ├─ overleafLatexTheme
       │         │    ├─ selectionLineExtension
       │         │    ├─ scrollOnDragSelection
       │         │    ├─ yCollab (if realtime enabled)
       │         │    └─ yUndoManagerKeymap (if realtime)
       │         ├─> Inline PDF compilation + iframe viewer
       │         ├─> CitationDialog
       │         ├─> FigureUploadDialog
       │         ├─> HistoryPanel
       │         └─> AI Tools Menu (inline)
       │
       ├─> useCollabProvider (Hocuspocus)
       │    └─> Y.Doc → yText = doc.getText('main')
       │
       └─> Auto-save + content persistence
```

### Files Involved

| File | Lines | Role |
|------|-------|------|
| `frontend/src/components/editor/LaTeXEditor.tsx` | 2,130 | God component — editor, toolbar, compilation, PDF, AI, dialogs |
| `frontend/src/components/editor/adapters/LatexAdapter.tsx` | 342 | Adapter wrapper — double state management |
| `frontend/src/components/editor/LatexPdfViewer.tsx` | 255 | Standalone PDF viewer — **orphaned duplicate** of inline compilation |
| `frontend/src/components/editor/codemirror/overleafTheme.ts` | 146 | CSS-variable-driven theme |
| `frontend/src/components/editor/codemirror/selectionLineExtension.ts` | 71 | Selection line decoration fix |
| `frontend/src/components/editor/latexToolbarConfig.ts` | 87 | Toolbar button config |
| `frontend/src/hooks/useCollabProvider.ts` | 184 | Hocuspocus WebSocket provider |
| `frontend/src/components/editor/DocumentShell.tsx` | ~200 | Top-level orchestrator |
| `frontend/src/assets/pdf-viewer.html` | 321 | PDF.js iframe viewer |
| `frontend/src/utils/latexDiff.ts` | 194 | Section-based diff/merge |
| `backend/app/api/v1/latex.py` | 521 | Compilation endpoints |

---

## 2. Critical Bugs

### Bug 1: Path Traversal in Artifact Serving [SECURITY]

**File:** `backend/app/api/v1/latex.py:212-218`

```python
target = paths["dir"] / filename
if not target.exists():
    raise HTTPException(status_code=404, detail="artifact not found")
return FileResponse(str(target))
```

**Problem:** `filename` comes from the URL path and is not sanitized. A request like `/latex/artifacts/hash/../../etc/passwd` could read arbitrary files.

**Fix:** Validate that `target.resolve()` is a child of `paths["dir"].resolve()`:
```python
target = (paths["dir"] / filename).resolve()
if not target.is_relative_to(paths["dir"].resolve()):
    raise HTTPException(status_code=400, detail="invalid filename")
```

---

### Bug 2: Static Property Mutation for Compile Sequencing

**File:** `LaTeXEditor.tsx:1377`

```js
const seqRef = (LaTeXEditorImpl as any)._compileSeq || ((LaTeXEditorImpl as any)._compileSeq = { current: 0 })
```

**Problem:** Attaches a mutable property to the function component itself. This is **shared across all instances**. If two editors mount, their compile sequences collide and can discard valid results.

**Fix:** Replace with a `useRef` at the component level.

---

### Bug 3: Wrong Undo in Realtime Mode

**File:** `LaTeXEditor.tsx:1240-1260`

```js
const handleUndo = useCallback(() => {
  const view = viewRef.current
  if (!view || !undoEnabled) return
  undo(view)  // <-- Always uses CodeMirror's built-in undo
  ...
}, [undoEnabled])
```

**Problem:** In realtime mode, the Yjs `UndoManager` should handle undo/redo, but `handleUndo` calls CodeMirror's `undo(view)` unconditionally. This bypasses Yjs and can cause CRDT inconsistencies.

**Fix:** Check if in realtime mode and use `yUndoManagerRef.current.undo()` / `.redo()` instead.

---

### Bug 4: Unwanted Auto-Recompilation Cascade

**File:** `LaTeXEditor.tsx:1472-1476`

```js
useEffect(() => {
  if (!readOnly) {
    void compileNow()
  }
}, [compileNow, readOnly])
```

**Problem:** `compileNow` is a `useCallback` with many dependencies (`paperId`, `readOnly`, `resolveApiUrl`, `cleanupPdf`, `flushBufferedChange`, `postPdfToIframe`). Any time these change, a new `compileNow` reference is created, re-triggering this effect. This also lists `buildApiUrl` (a stable import) in its dependency array, signaling the deps were written carelessly.

**Fix:**
- Compile only on mount and explicit user action.
- Store compile function in a ref so the effect doesn't re-fire.
- Or use a separate `compileOnMount` flag.

---

### Bug 5: Duplicate Remote Selection Parsing

**File:** `LaTeXEditor.tsx:418-458` and `LaTeXEditor.tsx:461-494`

**Problem:** Nearly identical awareness-parsing code is duplicated. The second effect (triggered by `realtime?.version`) redundantly re-parses what the first effect's event listeners already handle.

**Fix:** Extract shared logic into a single `parseAwarenessSelections()` helper. Remove the duplicate effect.

---

### Bug 6: `postMessage` with `'*'` Origin

**Files:** `LaTeXEditor.tsx:1331`, `LatexPdfViewer.tsx:35`

```js
iframe.contentWindow.postMessage({ type: 'loadFile', url, rev }, '*')
```

**Problem:** Using `'*'` as target origin is a security weakness. Any page could intercept these messages if the iframe context changes.

**Fix:** Use `window.location.origin` or the specific origin of the iframe's srcDoc.

---

### Bug 7: Aux File Read Twice

**File:** `backend/app/api/v1/latex.py:360`

```python
need_bib = aux.exists() and ("\\citation" in aux.read_text(...) or "\\bibdata" in aux.read_text(...))
```

**Problem:** Reads `main.aux` twice — once per condition in the `or`.

**Fix:** Read once, check both:
```python
aux_content = aux.read_text(errors='ignore') if aux.exists() else ''
need_bib = "\\citation" in aux_content or "\\bibdata" in aux_content
```

---

### Bug 8: BibTeX Key Collisions

**Files:** `backend/app/api/v1/latex.py:463-476`, `LaTeXEditor.tsx:299-313`

**Problem:** Both `_make_bibtex_key` (backend) and `makeBibKey` (frontend) generate keys as `author_last + year + title_prefix`. Two papers by the same author in the same year with similar titles produce identical keys, silently overwriting entries.

**Fix:** Append a disambiguator (e.g., `a`, `b`, `c`) when duplicate keys are detected, or hash a unique identifier into the key.

---

## 3. Architectural Problems

### Problem 1: God Component (2,130 lines)

`LaTeXEditor.tsx` handles everything — editor lifecycle, compilation, toolbar, AI tools, dialogs, split pane, PDF viewer, realtime sync. This makes it:
- Hard to reason about
- Hard to test
- Prone to stale closure bugs
- Full of interleaved state that causes unnecessary re-renders

**Target decomposition:**

```
LaTeXEditor.tsx (thin orchestrator, ~200 lines)
├── hooks/useCodeMirrorEditor.ts     — CM lifecycle, extensions, view creation/destroy
├── hooks/useLatexCompilation.ts     — compileNow, SSE parsing, PDF blob management, abort
├── hooks/useRealtimeSync.ts         — Yjs setup, awareness, remote selections
├── components/EditorToolbar.tsx     — formatting buttons, dropdowns, view mode toggle
├── components/AiToolsMenu.tsx       — AI action buttons, tone selector
├── components/PdfPreviewPane.tsx    — iframe, pdf-viewer.html communication
├── components/CompileStatusBar.tsx  — compile status, save status
└── (existing) CitationDialog, FigureUploadDialog, HistoryPanel
```

---

### Problem 2: Duplicate Compilation Infrastructure

Two independent, near-identical SSE compilation systems exist:
- `LaTeXEditor.tsx:1338-1442` (inline `compileNow`)
- `LatexPdfViewer.tsx:67-189` (standalone `compile`)

Both contain: SSE parsing, abort controllers, blob URL lifecycle, iframe `postMessage`.

**Fix:** Delete `LatexPdfViewer.tsx` if unused, or extract a shared `useLatexCompilation` hook used by both.

---

### Problem 3: 50+ Silent `catch {}` Blocks

Examples:
```js
try { (e.target as HTMLElement).setPointerCapture(e.pointerId) } catch {}
try { await editorRef.current?.replaceSelection?.(text) } catch {}
try { onContentChange(normalized, ...) } catch {}
try { awareness.setLocalStateField('selection', null) } catch {}
```

**Problem:** When something goes wrong, errors are silently swallowed. This is likely the primary reason the editor "feels buggy" — bugs happen but leave no trace.

**Fix:** Replace all empty `catch {}` with at minimum `catch (e) { console.warn('[context]', e) }` for non-trivial operations. Trivial ones (like `setPointerCapture`) can keep silent catches but should be explicitly commented.

---

### Problem 4: 20+ Unconditional `console.info` Calls

Debug logging like:
```js
console.info('[LaTeXEditor] yText setup effect', { ... })
console.info('[LaTeXEditor] createView called', { ... })
console.info('[LatexAdapter] Realtime doc observer update', { ... })
```

These fire in production for every user.

**Fix:** Route all through the existing `debugLog()` helper (which checks `window.__SH_DEBUG_LTX`). Remove or guard every unconditional `console.info/log`.

---

### Problem 5: Adapter Layer Adds Confusion

`LatexAdapter.tsx` wraps `LaTeXEditor.tsx` and creates a double-state problem:
- Adapter has `src` state, observes yText, manages drafts
- Editor receives `value` prop, has `latestDocRef`, manages its own sync
- In realtime mode, the value prop flows down but gets **ignored** (line 827-850)
- In local mode, changes flow: Editor → onChange → Adapter.setSrc → re-render → Editor.value → (skip if same)

**Fix:** Either:
- (a) Make LaTeXEditor fully uncontrolled in realtime mode (no value prop) and let yCollab be the sole source of truth
- (b) Merge adapter logic into the editor and eliminate the wrapper

---

### Problem 6: No Compile Debounce

Clicking "Recompile" rapidly fires multiple concurrent compilations. The abort controller prevents stale results from displaying, but still wastes backend resources.

**Fix:** Debounce the compile button (e.g., 1s cooldown after last click), or disable the button until the current compilation completes (which is partially done but the `compileNow` dependency chain can still trigger concurrent compiles).

---

## 4. Backend Issues

### Issue 1: Synchronous File I/O in Async Endpoints

**File:** `backend/app/api/v1/latex.py`

Calls like `paths["tex"].write_text(...)`, `shutil.copytree(...)`, `shutil.copy2(...)`, `Path.read_text(...)` are all **synchronous blocking calls** inside `async def` endpoints. This blocks the uvicorn event loop.

**Fix:** Wrap in `asyncio.to_thread()` or use `aiofiles`:
```python
await asyncio.to_thread(paths["tex"].write_text, effective_source, encoding="utf-8")
```

---

### Issue 2: No Cache Cleanup

`uploads/latex_cache/{hash}/` directories accumulate forever. There's no TTL, no LRU eviction, no size limit.

**Fix:** Add a periodic cleanup task (e.g., delete entries older than 7 days) or implement LRU eviction when cache size exceeds a threshold.

---

### Issue 3: Silent Exception Swallowing in Backend

Multiple bare `except Exception: pass` blocks:
```python
except Exception:
    pass  # Silently continue if style file copy fails
except Exception:
    pass  # Silently continue if figures copy fails
```

**Fix:** At minimum log warnings:
```python
except Exception as e:
    logger.warning("Failed to copy style files: %s", e)
```

---

## 5. Overleaf Feature Gap

Features Overleaf has that ScholarHub is missing, ordered by impact:

### High Impact

| Feature | Description | Effort |
|---------|-------------|--------|
| **Autocomplete** | LaTeX command/environment completion, `\cite{}` and `\ref{}` aware completions | Medium |
| **SyncTeX** | Click PDF → jump to source line. Click source → highlight in PDF. | Medium-High |
| **Inline error markers** | Show compilation errors as gutter markers on the exact line | Medium |
| **Multi-file support** | File tree, `\input{}` / `\include{}` resolution | High |

### Medium Impact

| Feature | Description | Effort |
|---------|-------------|--------|
| **Lezer LaTeX parser** | Replace legacy `stex` StreamLanguage with a proper Lezer grammar for accurate highlighting | Medium |
| **Bracket matching** | Auto-close `{}`, `[]`, `$...$`, `\begin{}...\end{}` | Low |
| **Code folding** | Fold sections, environments, comments | Low |
| **Find & replace** | Ctrl+F / Ctrl+H with regex support (CM6 has this built-in, just needs enabling) | Low |

### Nice to Have

| Feature | Description | Effort |
|---------|-------------|--------|
| **Spell check** | In-editor spell checking (skip LaTeX commands) | Medium |
| **Outline panel** | Document outline from `\section`, `\subsection` etc. | Low-Medium |
| **Incremental compilation** | Server-side persistent project for faster recompiles | High |

---

## 6. Target Architecture

### Frontend Component Tree (After Overhaul)

```
LaTeXEditor.tsx (~250 lines, thin orchestrator)
│
├── hooks/
│   ├── useCodeMirrorEditor.ts
│   │   - CM6 EditorView lifecycle (create, destroy, reconfigure)
│   │   - Extension management (language, theme, keymaps)
│   │   - Imperative handle (getSelection, replaceSelection, setValue, focus)
│   │   - Value sync (external prop ↔ editor state)
│   │
│   ├── useLatexCompilation.ts
│   │   - compileNow() with SSE streaming
│   │   - AbortController management
│   │   - PDF blob URL lifecycle (create, revoke)
│   │   - Compile status, error, logs state
│   │   - Stale result detection (sequence numbers via useRef)
│   │   - Debounced compile trigger
│   │
│   ├── useRealtimeSync.ts
│   │   - Yjs Y.Text setup from realtime.doc
│   │   - UndoManager creation
│   │   - yCollab + yUndoManagerKeymap extension building
│   │   - Awareness selection parsing → RemoteSelection[]
│   │   - Safari workarounds (content polling, view refresh)
│   │
│   └── useSplitPane.ts
│       - Split position state (persisted to localStorage)
│       - Drag handlers (mousedown, mousemove, mouseup)
│       - Overlay management during drag
│
├── components/
│   ├── EditorToolbar.tsx
│   │   - View mode toggle (Code / Split / PDF)
│   │   - Undo / Redo buttons
│   │   - Formatting dropdowns (structure, text, math, lists, refs)
│   │   - Direct formatting buttons (bold, italic, math, cite, figure, table, lists)
│   │   - References button
│   │   - Compile / Save buttons
│   │   - History button
│   │
│   ├── AiToolsMenu.tsx
│   │   - Sparkles dropdown
│   │   - Paraphrase, Summarize, Explain, Synonyms, Tone actions
│   │   - Tone sub-menu
│   │   - Loading states per action
│   │
│   ├── PdfPreviewPane.tsx
│   │   - iframe with pdf-viewer.html
│   │   - postMessage communication (loadFile, viewer-ready)
│   │   - Compile status overlay
│   │   - Compile logs panel (collapsible)
│   │
│   ├── CompileStatusBar.tsx
│   │   - Compile status text
│   │   - Save status text
│   │   - Collaboration status badge
│   │
│   └── RemoteCaretWidget.ts
│       - WidgetType subclass for remote peer carets
│       - Decoration builders (marks + widgets)
│       - Color utilities (highlightColor, computeIdealTextColor)
│
├── extensions/
│   ├── overleafTheme.ts (existing, keep)
│   ├── selectionLineExtension.ts (existing, keep)
│   ├── scrollOnDragSelection.ts (extract from LaTeXEditor.tsx)
│   └── remoteSelectionsField.ts (extract StateField + StateEffect)
│
└── (existing, keep as-is)
    ├── latexToolbarConfig.ts
    ├── CitationDialog.tsx
    ├── FigureUploadDialog.tsx
    └── HistoryPanel.tsx
```

### Adapter Simplification

Either:
- **Option A:** Merge `LatexAdapter.tsx` into `LaTeXEditor.tsx` — editor manages its own draft persistence and content sourcing
- **Option B:** Keep adapter but make it truly thin — only translates between `DocumentShell` interface and editor props, no duplicate state

### Backend Changes

```
backend/app/api/v1/latex.py
├── Add path traversal protection to artifact serving
├── Wrap sync I/O in asyncio.to_thread()
├── Read aux file once instead of twice
├── Add logger.warning() to silent except blocks
│
backend/app/services/latex_cache_cleanup.py (new)
├── Periodic task to evict old cache entries
└── Configurable TTL (default: 7 days) and max size
```

---

## 7. Execution Plan

### Phase 1: Critical Bug Fixes (do first, independent of refactor)

- [ ] **1.1** Fix path traversal in artifact serving (security)
- [ ] **1.2** Replace static `_compileSeq` with `useRef`
- [ ] **1.3** Fix undo/redo to use Yjs UndoManager in realtime mode
- [ ] **1.4** Fix auto-recompilation cascade (compile only on mount + explicit click)
- [ ] **1.5** Fix aux file double-read in backend
- [ ] **1.6** Fix `postMessage` origin from `'*'` to specific origin

### Phase 2: Extract Hooks (reduce God component)

- [ ] **2.1** Extract `useLatexCompilation` hook
  - Move `compileNow`, SSE parsing, blob lifecycle, abort management
  - Delete orphaned `LatexPdfViewer.tsx` if confirmed unused
- [ ] **2.2** Extract `useRealtimeSync` hook
  - Move Y.js setup, awareness parsing, remote selections, Safari workarounds
  - Deduplicate the two awareness parsing effects
- [ ] **2.3** Extract `useCodeMirrorEditor` hook
  - Move view creation/destruction, extension management, value sync
  - Move `handleContainerRef`, `createView`, `clearContainer`
- [ ] **2.4** Extract `useSplitPane` hook
  - Move split position state, drag handlers, overlay logic

### Phase 3: Extract Components (reduce render bloat)

- [ ] **3.1** Extract `EditorToolbar` component
  - All formatting buttons, dropdowns, view mode toggle
  - Receive formatting actions as props
- [ ] **3.2** Extract `AiToolsMenu` component
  - AI action buttons, tone menu, loading states
- [ ] **3.3** Extract `PdfPreviewPane` component
  - iframe, postMessage, compile status overlay, logs panel
- [ ] **3.4** Extract `CompileStatusBar` component
- [ ] **3.5** Extract `RemoteCaretWidget` + decoration utilities to `extensions/remoteSelectionsField.ts`
- [ ] **3.6** Extract `scrollOnDragSelection` to `extensions/scrollOnDragSelection.ts`

### Phase 4: Code Quality Sweep

- [ ] **4.1** Replace all 50+ empty `catch {}` blocks with `catch (e) { console.warn(...) }` or explicit comment
- [ ] **4.2** Move all unconditional `console.info/log` behind `debugLog()` guard
- [ ] **4.3** Remove duplicate `makeBibKey` — share one implementation (or at least keep them in sync)
- [ ] **4.4** Simplify adapter layer (Option A or B from above)

### Phase 5: Backend Hardening

- [ ] **5.1** Wrap synchronous file I/O in `asyncio.to_thread()`
- [ ] **5.2** Add cache cleanup service with configurable TTL
- [ ] **5.3** Add `logger.warning` to all silent `except Exception: pass` blocks
- [ ] **5.4** Add BibTeX key deduplication logic

### Phase 6: Feature Additions (post-refactor)

- [ ] **6.1** LaTeX autocomplete (commands, environments, `\cite{}`, `\ref{}`)
- [ ] **6.2** Enable CM6 built-in search/replace (Ctrl+F / Ctrl+H)
- [ ] **6.3** Bracket auto-closing and matching
- [ ] **6.4** Code folding for sections and environments
- [ ] **6.5** Inline compilation error markers (gutter decorations)
- [ ] **6.6** SyncTeX forward/inverse search
- [ ] **6.7** Upgrade from legacy `stex` to Lezer-based LaTeX grammar

---

## Notes

- **CodeMirror 6 was the right choice.** The issues are in the integration, not the library.
- Each phase should be a separate PR to keep reviews manageable.
- Phase 1 can be done immediately without affecting the rest of the overhaul.
- Phases 2-3 are the core refactor — they should be done together to avoid intermediate broken states.
- Phase 6 features should only be started after Phases 2-4 are complete, since the refactored architecture makes them much easier to implement.
