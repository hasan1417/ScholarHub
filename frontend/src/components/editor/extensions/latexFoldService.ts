import { foldService } from '@codemirror/language'

/**
 * Custom fold service for LaTeX documents.
 *
 * Provides fold regions for:
 * - \begin{env} ... \end{env} blocks (nested correctly)
 * - \section, \subsection, \subsubsection, \chapter, \part
 *   (folds from the line after the heading to the line before the next
 *   heading of equal or higher rank, or end of document)
 */

// Match \begin{envName} — captures the environment name
const BEGIN_RE = /^[ \t]*\\begin\{([^}]+)\}/
// Match \end{envName}
const END_RE = /^[ \t]*\\end\{([^}]+)\}/

// Sectioning commands ordered by rank (higher index = lower rank)
const SECTION_COMMANDS = [
  '\\part',
  '\\chapter',
  '\\section',
  '\\subsection',
  '\\subsubsection',
  '\\paragraph',
  '\\subparagraph',
]

const SECTION_RE = /^[ \t]*\\(part|chapter|section|subsection|subsubsection|paragraph|subparagraph)\b/

function sectionRank(cmd: string): number {
  const idx = SECTION_COMMANDS.indexOf(`\\${cmd}`)
  return idx >= 0 ? idx : SECTION_COMMANDS.length
}

export const latexFoldService = foldService.of((state, lineStart) => {
  const line = state.doc.lineAt(lineStart)
  const text = line.text

  // --- Environment folding: \begin{env} ... \end{env} ---
  const beginMatch = BEGIN_RE.exec(text)
  if (beginMatch) {
    const envName = beginMatch[1]
    let depth = 1
    for (let i = line.number + 1; i <= state.doc.lines; i++) {
      const l = state.doc.line(i).text
      if (BEGIN_RE.exec(l)?.[1] === envName) depth++
      if (END_RE.exec(l)?.[1] === envName) {
        depth--
        if (depth === 0) {
          const endLine = state.doc.line(i)
          // Fold from end of \begin line to start of \end line
          return { from: line.to, to: endLine.from - 1 }
        }
      }
    }
    return null
  }

  // --- Section folding ---
  const sectionMatch = SECTION_RE.exec(text)
  if (sectionMatch) {
    const rank = sectionRank(sectionMatch[1])
    // Find the next section of equal or higher rank
    for (let i = line.number + 1; i <= state.doc.lines; i++) {
      const l = state.doc.line(i).text
      const nextMatch = SECTION_RE.exec(l)
      if (nextMatch && sectionRank(nextMatch[1]) <= rank) {
        const prevLine = state.doc.line(i - 1)
        if (prevLine.from > line.to) {
          return { from: line.to, to: prevLine.to }
        }
        return null
      }
    }
    // Fold to end of document
    const lastLine = state.doc.line(state.doc.lines)
    if (lastLine.from > line.to) {
      return { from: line.to, to: lastLine.to }
    }
    return null
  }

  return null
})
