# Multi-File Stability Redesign Plan

**Created:** 2026-03-14
**Status:** Not Started
**Priority:** CRITICAL — recurring "Emergency stop" compilation failures

## Problem

Multi-file LaTeX editing was bolted onto a single-file architecture. Five distinct bugs stem from having no single source of truth:

1. `getLatestSource()` returns whatever file is in the editor, not main.tex
2. `handleSave` reads from the editor view, not Y.Text('main')
3. `onStoreDocument` only persists main.tex, ignores extra files
4. File list detection relies on timing (retry timers)
5. File switch has a `requestAnimationFrame` gap causing inconsistency

## Root Cause

The system reads document content from `viewRef.current.state.doc` (the CodeMirror editor view), which shows **whatever file is currently active**. When the user switches to `introduction.tex` and triggers a compile or save, the system sends introduction.tex content as main.tex.

## Architecture Decision

**Keep the destroy/recreate approach for file switching.** After analyzing y-codemirror.next source, `StateEffect.reconfigure` can swap yCollab plugins, but it does NOT replace document content. A simultaneous content replacement + reconfigure would corrupt the new Y.Text. The destroy/recreate approach is fundamentally correct — the bugs are in what happens AROUND the switch, not the switch itself.

---

## Phase 1: Fix Data Reads (CRITICAL — Frontend Only)

### File: `frontend/src/components/editor/LaTeXEditor.tsx`

**Change `getLatestSource`** to ONLY read from Y.Text, never the editor view:

```typescript
const getLatestSource = useCallback(() => {
  if (realtime?.doc) {
    return realtime.doc.getText('main').toString()
  }
  // Non-realtime: editor always shows main.tex
  return viewRef.current?.state.doc.toString() || latestDocRef.current || ''
}, [viewRef, latestDocRef, realtime?.doc])
```

Remove `activeFile` dependency. Remove try/catch. Y.Text is always available once doc exists.

### File: `frontend/src/components/editor/hooks/useHistoryRestore.ts`

**Change `handleSave`** to read main.tex from Y.Text:

```typescript
let v: string
if (realtimeDoc) {
  v = realtimeDoc.getText('main').toString()
} else {
  v = viewRef.current?.state.doc.toString() || ''
}
```

### Manual Test
1. Open multi-file paper
2. Switch to introduction.tex
3. Press Cmd+S → should save main.tex content, not introduction.tex
4. Click Recompile while viewing introduction.tex → should compile correctly

---

## Phase 2: Fix Collab Persist (CRITICAL — Backend + Collab Server)

### File: `collab-server/index.mjs`

**Change `onStoreDocument`** to persist ALL files:

```javascript
async onStoreDocument({ documentName, document }) {
  const yText = document.getText('main')
  const materializedText = yText.toString()

  // Collect extra files
  const latexFiles = {}
  document.share.forEach((value, key) => {
    if (key.startsWith('file:')) {
      const filename = key.slice(5)
      const fileText = document.getText(key)
      if (fileText.length > 0) {
        latexFiles[filename] = fileText.toString()
      }
    }
  })

  const body = { latex_source: materializedText }
  if (Object.keys(latexFiles).length > 0) {
    body.latex_files = latexFiles
  }

  // Persist to backend
  await fetch(`${backendBaseUrl}/api/v1/collab/persist/${documentName}`, {
    method: 'POST',
    headers: { 'X-Collab-Secret': bootstrapSecret, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
```

### File: `backend/app/schemas/collab.py`

Add `latex_files` to `CollabPersistRequest`:

```python
class CollabPersistRequest(BaseModel):
    latex_source: str
    latex_files: Optional[Dict[str, str]] = None
```

### File: `backend/app/api/v1/collab_bootstrap.py`

In `persist_collab_document_state`, persist `data.latex_files`:

```python
if data.latex_files:
    paper.latex_files = data.latex_files
```

### Manual Test
1. Open multi-file paper, edit introduction.tex
2. Wait 2s (onStoreDocument debounce)
3. Check DB: `SELECT latex_files->>'introduction.tex' FROM research_papers WHERE id = '...'`
4. Verify it has the updated content

---

## Phase 3: Fix File List Detection (Frontend Only)

### File: `frontend/src/components/editor/hooks/useMultiFileManagement.ts`

Replace retry timer with `afterTransaction` listener:

```typescript
useEffect(() => {
  if (!realtimeDoc) return
  const refreshFiles = () => {
    const files = getFileList()
    setFileList(prev => {
      if (JSON.stringify(prev) === JSON.stringify(files)) return prev
      return files
    })
  }
  refreshFiles()
  realtimeDoc.on('afterTransaction', refreshFiles)
  return () => {
    realtimeDoc.off('afterTransaction', refreshFiles)
  }
}, [realtimeDoc, getFileList])
```

Remove `yTextReady` dependency, `update` listener, and retry timer.

### Manual Test
1. Refresh the page
2. File tabs should appear immediately (no 1.5s delay)
3. All 4 files should show consistently on every refresh

---

## Phase 4: Improve File Switch UX (Frontend Only)

### File: `frontend/src/components/editor/hooks/useCodeMirrorEditor.ts`

1. Remove `requestAnimationFrame` for file switches (keep for initial mount):

```typescript
if (isFileSwitch && viewRef.current) {
  viewRef.current.destroy()
  viewRef.current = null
  // Create immediately — container is already in DOM
  try { createView(containerRef.current) } catch {}
  return
}
// Initial mount — use rAF
requestAnimationFrame(() => {
  if (!containerRef.current || viewRef.current) return
  try { createView(containerRef.current) } catch {}
})
```

2. Save/restore cursor position per file (optional improvement)

### Manual Test
1. Switch between files rapidly
2. No flicker or empty states
3. Cursor returns to previous position when switching back

---

## Phase 5: Cleanup

### File: `collab-server/index.mjs`

Remove the `\documentclass` guard (lines 272-275). After Phase 1, Y.Text('main') will never contain sub-file content, so this guard is unnecessary.

### Manual Test
1. Switch files, wait for onStoreDocument
2. Check DB: main.tex content should always start with `\documentclass`
3. No "Skipping persist" warnings in collab logs

---

## Dependency Order

```
Phase 1 (fix reads) ──── no dependencies, highest impact
    │
Phase 2 (fix persist) ── depends on Phase 1 for safety
    │
Phase 3 (fix file list) ── independent, can parallel with Phase 2
    │
Phase 4 (fix switch UX) ── independent
    │
Phase 5 (cleanup) ──── depends on Phase 1 being verified
```

## Agent Assignments

- **Phase 1**: Frontend Developer agent
- **Phase 2**: Codex (backend) + Frontend Developer (collab server)
- **Phase 3**: Frontend Developer agent
- **Phase 4**: Frontend Developer agent
- **Phase 5**: Manual cleanup (small change)

## Risks

1. **Breaking non-realtime mode** — all changes must preserve the `if (realtimeDoc)` guard pattern
2. **`afterTransaction` fires too often** — debounce with 100ms if perf issue
3. **Removing rAF causes DOM issues** — only remove for file switches, keep for initial mount
4. **`CollabPersistRequest` schema change** — `latex_files` is Optional, backward compatible
