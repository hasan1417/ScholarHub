import { StateField, StateEffect, Extension, RangeSetBuilder } from '@codemirror/state'
import type { EditorState } from '@codemirror/state'
import { EditorView, Decoration, DecorationSet } from '@codemirror/view'

export interface DiffLineInfo {
  lineNumber: number // 1-based line number in the merged document
  type: 'added' | 'deleted' | 'unchanged'
}

export const setDiffLines = StateEffect.define<DiffLineInfo[]>()

const diffField = StateField.define<DecorationSet>({
  create() {
    return Decoration.none
  },
  update(value, tr) {
    for (const effect of tr.effects) {
      if (effect.is(setDiffLines)) {
        return buildDiffDecorations(effect.value, tr.state)
      }
    }
    return value
  },
  provide: field => EditorView.decorations.from(field),
})

function buildDiffDecorations(lines: DiffLineInfo[], state: EditorState): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>()

  for (const info of lines) {
    if (info.type === 'unchanged') continue
    if (info.lineNumber < 1 || info.lineNumber > state.doc.lines) continue

    const line = state.doc.line(info.lineNumber)

    if (info.type === 'added') {
      builder.add(line.from, line.from, Decoration.line({ class: 'cm-diff-added' }))
    } else if (info.type === 'deleted') {
      builder.add(line.from, line.from, Decoration.line({ class: 'cm-diff-deleted' }))
      // Mark decoration for strikethrough on the text content
      if (line.length > 0) {
        builder.add(line.from, line.to, Decoration.mark({ class: 'cm-diff-deleted-text' }))
      }
    }
  }

  return builder.finish()
}

const diffTheme = EditorView.baseTheme({
  '.cm-diff-added': {
    backgroundColor: 'rgba(34, 197, 94, 0.15)',
  },
  '.cm-diff-deleted': {
    backgroundColor: 'rgba(239, 68, 68, 0.10)',
  },
  '.cm-diff-deleted-text': {
    textDecoration: 'line-through',
    opacity: '0.6',
  },
  '&dark .cm-diff-added': {
    backgroundColor: 'rgba(34, 197, 94, 0.12)',
  },
  '&dark .cm-diff-deleted': {
    backgroundColor: 'rgba(239, 68, 68, 0.12)',
  },
  '&dark .cm-diff-deleted-text': {
    opacity: '0.5',
  },
})

export function historyDiffExtension(): Extension[] {
  return [diffField, diffTheme]
}
