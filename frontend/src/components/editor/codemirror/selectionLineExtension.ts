import { EditorView, ViewPlugin, ViewUpdate, Decoration, DecorationSet } from '@codemirror/view'
import { RangeSetBuilder } from '@codemirror/state'

/**
 * Extension that adds a line-level decoration to lines containing selection.
 * This allows us to use box-shadow to extend the selection background without
 * the triple-caret artifacts caused by per-span box-shadows.
 */

const selectionLineDeco = Decoration.line({ class: 'cm-selection-line' })

const selectionLinePlugin = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet

    constructor(view: EditorView) {
      this.decorations = this.buildDecorations(view)
    }

    update(update: ViewUpdate) {
      if (update.selectionSet || update.docChanged || update.viewportChanged) {
        this.decorations = this.buildDecorations(update.view)
      }
    }

    buildDecorations(view: EditorView): DecorationSet {
      const builder = new RangeSetBuilder<Decoration>()
      const selection = view.state.selection.main

      // Only add decorations if there's an actual selection (not just cursor)
      if (selection.empty) {
        return builder.finish()
      }

      const doc = view.state.doc
      const startLine = doc.lineAt(selection.from).number
      const endLineInfo = doc.lineAt(selection.to)

      // If selection.to is at the very start of a line, don't include that line
      // (the selection ends at the newline of the previous line, not on this line)
      let endLine = endLineInfo.number
      if (selection.to === endLineInfo.from && endLine > startLine) {
        endLine--
      }

      for (let lineNum = startLine; lineNum <= endLine; lineNum++) {
        const line = doc.line(lineNum)
        builder.add(line.from, line.from, selectionLineDeco)
      }

      return builder.finish()
    }
  },
  {
    decorations: (v) => v.decorations,
  }
)

// Theme styles for the selection line extension
const selectionLineTheme = EditorView.baseTheme({
  '.cm-selection-line': {
    // No styling needed - this class is used to detect selected lines
  },
  // When a line is both active and has selection, hide active line styling
  '.cm-selection-line.cm-activeLine': {
    backgroundColor: 'transparent',
    boxShadow: 'none',
  },
})

export const selectionLineExtension = [selectionLinePlugin, selectionLineTheme]
