import type { EditorView } from '@codemirror/view'
import type { Diagnostic } from '@codemirror/lint'

export interface LatexError {
  line: number
  message: string
  context?: string
}

/**
 * Convert backend LaTeX errors into CodeMirror 6 Diagnostic objects.
 * If `context` is available, highlights the matching substring on that line;
 * otherwise highlights the full line.
 */
export function latexErrorsToDiagnostics(
  errors: LatexError[],
  view: EditorView,
): Diagnostic[] {
  const doc = view.state.doc
  const diagnostics: Diagnostic[] = []

  for (const err of errors) {
    if (!err.line || err.line < 1 || err.line > doc.lines) continue

    const docLine = doc.line(err.line)
    let from = docLine.from
    let to = docLine.to

    // Narrow to context substring if available
    if (err.context) {
      const idx = docLine.text.indexOf(err.context)
      if (idx >= 0) {
        from = docLine.from + idx
        to = from + err.context.length
      }
    }

    // Skip empty ranges (collapsed lines)
    if (from === to) {
      to = Math.min(from + 1, doc.length)
    }

    diagnostics.push({
      from,
      to,
      severity: 'error',
      message: err.message,
    })
  }

  return diagnostics
}
