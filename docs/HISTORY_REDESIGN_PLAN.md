# Overleaf-Style History Redesign Plan

**Created:** 2026-03-14
**Status:** Phase 1 — Not Started

## Goal

Replace the current narrow side-panel history (`HistoryPanel.tsx`) with a full-page Overleaf-style history view featuring inline document diffs, a timeline sidebar, and label management.

## Current State

- `HistoryPanel.tsx` — ~500-line overlay side panel
- Shows snapshot cards with summary diffs ("+1 added, -1 deleted")
- Backend uses `difflib.unified_diff` (only returns context hunks, not full document)
- Endpoints: `GET /snapshots`, `GET /snapshots/{id}`, `GET /snapshots/{id1}/diff/{id2}`, `POST /snapshots/{id}/restore`, `PUT /snapshots/{id}/label`

## Target (Overleaf Reference)

1. **Full-page takeover** — replaces editor entirely, "← Back to editor" button
2. **Inline diff viewer** — read-only CodeMirror showing full document with:
   - Added lines: green/teal background
   - Deleted lines: red/pink background + strikethrough
   - Inline annotations ("Added by you on [date]")
3. **Header bar** — "Viewing [date]" left, "N changes in main.tex" right
4. **Right sidebar** — version timeline with "All history" / "Labels" toggle
5. **Left file panel** — shows "main.tex" with "Edited" badge

---

## Phase 1: Backend Full-Document Diff + Data Hook

**Agents:** Backend Architect + Frontend Developer

### Scope
- New backend endpoint: `GET /papers/{id}/snapshots/{id1}/full-diff/{id2}`
  - Uses `difflib.SequenceMatcher.get_opcodes()` instead of `unified_diff`
  - Returns EVERY line tagged as `added` / `deleted` / `unchanged`
  - Response includes `stats: { added: int, deleted: int, unchanged: int }`
- New frontend hook: `useHistoryView.ts`
  - Manages: `snapshots`, `selectedSnapshotId`, `diffData`, `activeTab` ('all' | 'labels')
  - Methods: `fetchDiff(snapshotId)`, label operations
- New API client methods in `snapshotsAPI`

### Backend Detail
```python
sm = difflib.SequenceMatcher(None, old_lines, new_lines)
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == 'equal':
        for line in new_lines[j1:j2]: emit(type='unchanged', content=line)
    elif tag == 'delete':
        for line in old_lines[i1:i2]: emit(type='deleted', content=line)
    elif tag == 'insert':
        for line in new_lines[j1:j2]: emit(type='added', content=line)
    elif tag == 'replace':
        for line in old_lines[i1:i2]: emit(type='deleted', content=line)
        for line in new_lines[j1:j2]: emit(type='added', content=line)
```

### Files
- Modify: `backend/app/api/v1/snapshots.py` — add `_compute_full_diff()` + endpoint
- Modify: `frontend/src/services/api.ts` — add `getFullDiff` to `snapshotsAPI`
- Create: `frontend/src/components/editor/hooks/useHistoryView.ts`

### Manual Tests
1. `curl GET /api/v1/papers/{id}/snapshots/{older}/full-diff/{newer}` — verify ALL lines present
2. Verify `stats.added` / `stats.deleted` counts match actual diff
3. In browser console, call `snapshotsAPI.getFullDiff()` — confirm response shape

---

## Phase 2: Full-Page History Shell + Timeline Sidebar

**Agents:** UX Architect + Frontend Developer

### Scope
- New component: `HistoryView.tsx` — full-page container replacing editor
- New component: `HistoryTimeline.tsx` — right sidebar with version list
- Integration: `LaTeXEditor.tsx` conditionally renders `HistoryView` when `historyMode === true`
- "History" button toggles into history mode; "← Back to editor" exits

### Layout Structure
```
HistoryView (flex, full-height)
  ├── Header bar (h-10, border-b)
  │   ├── "← Back to editor" button (left)
  │   ├── "Viewing [date/time]" label (center)
  │   └── "N changes in main.tex" (right)
  └── Content area (flex-1, flex row)
      ├── Center pane (flex-1, placeholder: <pre> of selected snapshot text)
      └── Right sidebar (w-[260px], HistoryTimeline)
```

### HistoryTimeline Features
- Tab bar: "All history" | "Labels"
- Date-grouped snapshot list (Today, Yesterday, dates)
- Selected snapshot highlighted with accent border
- Clicking a snapshot fetches its diff

### Files
- Create: `frontend/src/components/editor/history/HistoryView.tsx`
- Create: `frontend/src/components/editor/history/HistoryTimeline.tsx`
- Modify: `frontend/src/components/editor/LaTeXEditor.tsx` — add `historyMode` state, conditional render
- Modify: `frontend/src/components/editor/hooks/useHistoryRestore.ts` — expose `historyMode` / `setHistoryMode`
- Modify: `frontend/src/components/editor/components/EditorMenuBar.tsx` — toggle `historyMode`

### Manual Tests
1. Click History icon → editor disappears, full-page history view appears
2. Click "← Back to editor" → editor returns, no content loss
3. Click snapshots in timeline → center pane updates (raw text for now)
4. Toggle "All history" / "Labels" tabs — labels tab shows only labeled snapshots
5. Verify responsive behavior (sidebar doesn't collapse awkwardly)

---

## Phase 3: Inline Diff CodeMirror Viewer

**Agents:** Frontend Developer

### Scope
- New CM6 extension: `historyDiffDecorations.ts`
  - `StateField` with `Decoration.line()` for backgrounds + `Decoration.mark()` for strikethrough
  - Follows same pattern as `trackChangesDecoration.ts`
- New component: `HistoryDiffViewer.tsx` — read-only CM6 with:
  - Overleaf theme + LaTeX syntax highlighting
  - Diff decoration extension
  - Line numbers
- Merged document: newer snapshot text with deleted lines inserted at original positions

### CSS Classes
- `.cm-history-added` — `background: rgba(34, 197, 94, 0.15)` (green)
- `.cm-history-deleted` — `background: rgba(239, 68, 68, 0.1)` (red) + `text-decoration: line-through` + `opacity: 0.7`
- Dark mode variants via `&dark` in `EditorView.baseTheme`

### Files
- Create: `frontend/src/components/editor/history/HistoryDiffViewer.tsx`
- Create: `frontend/src/components/editor/extensions/historyDiffDecorations.ts`
- Modify: `frontend/src/components/editor/history/HistoryView.tsx` — replace placeholder with `HistoryDiffViewer`

### Manual Tests
1. Select a snapshot → full document with green added / red strikethrough deleted lines
2. Verify editor is read-only (cannot type)
3. Verify LaTeX syntax highlighting works in diff view
4. Scroll through long document — decorations consistent
5. Switch between snapshots — diff updates correctly
6. Test in dark mode — colors are appropriate
7. Verify line numbers visible

---

## Phase 4: Restore, Labels, and Polish

**Agents:** Frontend Developer + Code Reviewer (pr-review-toolkit)

### Scope
- "Restore this version" button in history view header
- Inline label editing in timeline (click to add/edit, Enter to save)
- Change count display in header ("N changes in main.tex")
- Left file panel showing "main.tex" with "Edited" badge
- Escape key exits history mode
- Delete old `HistoryPanel.tsx`

### Files
- Modify: `frontend/src/components/editor/history/HistoryView.tsx` — restore button, header info, file panel
- Modify: `frontend/src/components/editor/history/HistoryTimeline.tsx` — inline label editing
- Modify: `frontend/src/components/editor/hooks/useHistoryView.ts` — `restoreSnapshot()` + exit history mode
- Delete: `frontend/src/components/editor/HistoryPanel.tsx`
- Modify: `frontend/src/components/editor/LaTeXEditor.tsx` — remove old HistoryPanel import/render

### Manual Tests
1. Click "Restore this version" → confirm dialog → editor returns with restored content
2. New "restore" snapshot appears in timeline
3. Click snapshot label area → inline editor → type + Enter → saves
4. Header shows "N changes in main.tex" for selected diff
5. Press Escape → exits history view
6. Verify old side panel no longer appears anywhere
7. Code review: no regressions in editor functionality

---

## Phase 5: Compare Any Two Versions + Edge Cases

**Agents:** Frontend Developer + Backend Architect

### Scope
- Compare mode: shift-click two snapshots to diff arbitrary versions (not just adjacent)
- "Current state" virtual entry at top of timeline (diffs live editor content vs any snapshot)
- Navigation: up/down arrows in header to jump between change regions
- Empty state: paper with 0 snapshots shows helpful message
- Single snapshot: shows full document as "all added"

### Files
- Modify: `frontend/src/components/editor/history/HistoryTimeline.tsx` — range selection UI, "Current state" entry
- Modify: `frontend/src/components/editor/history/HistoryView.tsx` — navigation arrows in header
- Modify: `frontend/src/components/editor/history/HistoryDiffViewer.tsx` — expose change positions, scroll-to-change
- Modify: `frontend/src/components/editor/hooks/useHistoryView.ts` — arbitrary pair comparison, virtual current snapshot

### Manual Tests
1. Shift-click two non-adjacent snapshots → diff shows changes between them
2. "Current state" at top → diffs against live editor content
3. Navigation arrows jump between change regions in the diff viewer
4. Paper with 0 snapshots → helpful empty state message
5. Paper with 1 snapshot → shows full document as "all added"

---

## Dependency Graph

```
Phase 1 (Backend + Hook)
    │
    ▼
Phase 2 (Layout Shell + Timeline)
    │
    ▼
Phase 3 (Inline Diff Viewer)
    │
    ▼
Phase 4 (Restore + Labels + Polish)
    │
    ▼
Phase 5 (Compare + Edge Cases)
```

Phases 1 & 2 can potentially be parallelized (different agents, different files) as long as the hook interface is defined first.

## Key Architecture Decisions

1. **Full-page takeover** (not overlay) — matches Overleaf, gives enough space for inline diffs
2. **SequenceMatcher over unified_diff** — returns all lines tagged, not just context hunks
3. **Merged document for CM6** — newer text with deleted lines inserted at original positions
4. **StateField pattern** (not ViewPlugin) — required for decorations spanning line breaks
5. **Keep existing snapshot API** — new endpoint alongside, not replacing
6. **Single-file first** — multi-file snapshot support deferred (TODO in useHistoryRestore)
