import { StateField, StateEffect, Extension, RangeSetBuilder } from '@codemirror/state'
import { EditorView, Decoration, DecorationSet } from '@codemirror/view'

/** A single tracked change to render as a decoration. */
export interface TrackedChangeDecoration {
  from: number
  to: number
  type: 'insert' | 'delete'
  userName: string
  userColor?: string
  timestamp: number
}

/** Effect used to push new tracked-change data into the editor state. */
export const setTrackedChanges = StateEffect.define<TrackedChangeDecoration[]>()

// ── Decoration specs ────────────────────────────────────────────────

function markForChange(change: TrackedChangeDecoration) {
  const title = `${change.userName} - ${new Date(change.timestamp).toLocaleString()}`
  if (change.type === 'insert') {
    return Decoration.mark({
      class: 'cm-track-insert',
      attributes: { title },
    })
  }
  return Decoration.mark({
    class: 'cm-track-delete',
    attributes: { title },
  })
}

// ── StateField ──────────────────────────────────────────────────────

const trackChangesField = StateField.define<DecorationSet>({
  create() {
    return Decoration.none
  },

  update(value, tr) {
    for (const effect of tr.effects) {
      if (effect.is(setTrackedChanges)) {
        return buildDecorations(effect.value, tr.state.doc.length)
      }
    }
    // Map existing decorations through document changes so positions stay valid
    if (tr.docChanged) return value.map(tr.changes)
    return value
  },

  provide: field => EditorView.decorations.from(field),
})

function buildDecorations(changes: TrackedChangeDecoration[], docLength: number): DecorationSet {
  if (!changes || changes.length === 0) return Decoration.none

  // Sort by from position (required by RangeSetBuilder)
  const sorted = [...changes].sort((a, b) => a.from - b.from || a.to - b.to)

  const builder = new RangeSetBuilder<Decoration>()
  for (const change of sorted) {
    const from = Math.max(0, Math.min(change.from, docLength))
    const to = Math.max(from, Math.min(change.to, docLength))
    if (from === to) continue
    builder.add(from, to, markForChange(change))
  }
  return builder.finish()
}

// ── Theme ───────────────────────────────────────────────────────────

const trackChangesTheme = EditorView.baseTheme({
  '.cm-track-insert': {
    backgroundColor: 'rgba(34, 197, 94, 0.2)',
  },
  '.cm-track-delete': {
    textDecoration: 'line-through',
    color: 'rgb(239, 68, 68)',
    opacity: '0.6',
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
  },
  '&dark .cm-track-insert': {
    backgroundColor: 'rgba(34, 197, 94, 0.2)',
  },
  '&dark .cm-track-delete': {
    backgroundColor: 'rgba(239, 68, 68, 0.08)',
  },
})

// Use EditorView.theme (higher specificity than baseTheme) to override
// y-codemirror.next's default of hiding collaborator name labels (opacity: 0)
const collabCursorTheme = EditorView.theme({
  '.cm-ySelectionInfo': {
    opacity: 1,
    fontSize: '10px',
    padding: '1px 4px',
    borderRadius: '3px 3px 3px 0',
    fontFamily: 'sans-serif',
  },
})

// ── Public API ───────────────────────────────────────────────────────

/** CodeMirror extension that renders tracked insertions and deletions. */
export function trackChangesExtension(): Extension {
  return [trackChangesField, trackChangesTheme, collabCursorTheme]
}

/** Dispatch a new set of tracked changes into the editor view. */
export function dispatchTrackedChanges(view: EditorView, changes: TrackedChangeDecoration[]) {
  view.dispatch({ effects: setTrackedChanges.of(changes) })
}
