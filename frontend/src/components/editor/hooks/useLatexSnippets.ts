import React, { useCallback, useMemo, type MutableRefObject } from 'react'
import { EditorSelection, type SelectionRange } from '@codemirror/state'
import type { EditorView } from '@codemirror/view'
import { LATEX_FORMATTING_GROUPS } from '../latexToolbarConfig'

interface UseLatexSnippetsOptions {
  viewRef: MutableRefObject<EditorView | null>
  readOnly: boolean
  setFigureDialogOpen: (open: boolean) => void
}

export function useLatexSnippets({ viewRef, readOnly, setFigureDialogOpen }: UseLatexSnippetsOptions) {
  const applyWrapper = useCallback((prefix: string, suffix: string, fallback = '') => {
    if (readOnly) return
    const view = viewRef.current
    if (!view) return
    const state = view.state
    const { from, to } = state.selection.main
    const selected = state.sliceDoc(from, to)
    const content = selected || fallback
    const insertText = `${prefix}${content}${suffix}`
    const anchor = from + prefix.length
    const head = anchor + content.length
    view.dispatch({
      changes: { from, to, insert: insertText },
      selection: EditorSelection.single(anchor, head),
      scrollIntoView: true,
    })
    view.focus()
  }, [readOnly])

  const insertSnippet = useCallback((snippet: string, placeholder?: string) => {
    if (readOnly) return
    const view = viewRef.current
    if (!view) return
    const state = view.state
    const { from, to } = state.selection.main
    let selection: SelectionRange | EditorSelection = EditorSelection.single(from + snippet.length, from + snippet.length)
    if (placeholder) {
      const idx = snippet.indexOf(placeholder)
      if (idx >= 0) {
        selection = EditorSelection.single(from + idx, from + idx + placeholder.length)
      }
    }
    view.dispatch({
      changes: { from, to, insert: snippet },
      selection,
      scrollIntoView: true,
    })
    view.focus()
  }, [readOnly])

  const insertAtDocumentEnd = useCallback((snippet: string, placeholder?: string) => {
    if (readOnly) return
    const view = viewRef.current
    if (!view) return
    const doc = view.state.doc
    const raw = doc.toString()
    const endDocIndex = raw.lastIndexOf('\\end{document}')

    let insertPos = doc.length
    let insertText = snippet

    if (endDocIndex !== -1) {
      insertPos = endDocIndex
      const needsNewlineBefore = insertPos > 0 && raw[insertPos - 1] !== '\n'
      insertText = `${needsNewlineBefore ? '\n' : ''}${snippet}\n`
    } else {
      const needsNewlineBefore = doc.length > 0 && doc.sliceString(Math.max(0, doc.length - 1), doc.length) !== '\n'
      insertText = `${needsNewlineBefore ? '\n' : ''}${snippet}\n`
    }

    let selection: SelectionRange | EditorSelection = EditorSelection.cursor(insertPos + insertText.length)
    if (placeholder) {
      const idx = insertText.indexOf(placeholder)
      if (idx >= 0) {
        selection = EditorSelection.single(insertPos + idx, insertPos + idx + placeholder.length)
      }
    }

    view.dispatch({
      changes: { from: insertPos, to: insertPos, insert: insertText },
      selection,
      scrollIntoView: true,
    })
    view.focus()
  }, [readOnly])

  // Individual formatting commands
  const insertHeading = useCallback((command: 'section' | 'subsection' | 'paragraph', placeholder: string) => {
    applyWrapper(`\\${command}{`, '}\n\n', placeholder)
  }, [applyWrapper])

  const insertBold = useCallback(() => applyWrapper('\\textbf{', '}', 'bold text'), [applyWrapper])
  const insertItalics = useCallback(() => applyWrapper('\\textit{', '}', 'italic text'), [applyWrapper])
  const insertSmallCaps = useCallback(() => applyWrapper('\\textsc{', '}', 'Small Caps'), [applyWrapper])
  const insertInlineCode = useCallback(() => applyWrapper('\\texttt{', '}', 'code'), [applyWrapper])
  const insertFootnote = useCallback(() => applyWrapper('\\footnote{', '}', 'Footnote text'), [applyWrapper])
  const insertInlineMath = useCallback(() => applyWrapper('$', '$', 'x^2'), [applyWrapper])
  const insertDisplayMath = useCallback(() => applyWrapper('\\[\n', '\n\\]\n\n', 'E = mc^2'), [applyWrapper])
  const insertAlignEnv = useCallback(() => insertSnippet('\\begin{align}\n  a + b &= c \\\n  d + e &= f\n\\end{align}\n\n', 'a + b &= c'), [insertSnippet])
  const insertItemize = useCallback(() => insertSnippet('\\begin{itemize}\n  \\item First item\n  \\item Second item\n\\end{itemize}\n\n', 'First item'), [insertSnippet])
  const insertEnumerate = useCallback(() => insertSnippet('\\begin{enumerate}\n  \\item First step\n  \\item Second step\n\\end{enumerate}\n\n', 'First step'), [insertSnippet])
  const insertDescription = useCallback(() => insertSnippet('\\begin{description}\n  \\item[Term] Definition text\n\\end{description}\n\n', 'Term'), [insertSnippet])
  const insertQuote = useCallback(() => insertSnippet('\\begin{quote}\nQuote text here.\n\\end{quote}\n\n', 'Quote text here.'), [insertSnippet])
  const insertFigure = useCallback(() => setFigureDialogOpen(true), [setFigureDialogOpen])
  const handleFigureInsert = useCallback((imageUrl: string, caption: string, label: string, width: string) => {
    const figureCode = `\\begin{figure}[ht]\n  \\centering\n  \\includegraphics[width=${width}\\linewidth]{${imageUrl}}\n  \\caption{${caption}}\n  \\label{${label}}\n\\end{figure}\n\n`
    insertSnippet(figureCode, caption)
  }, [insertSnippet])
  const insertTable = useCallback(() => insertSnippet('\\begin{table}[ht]\n  \\centering\n  \\begin{tabular}{lcc}\n    \\toprule\n    Column 1 & Column 2 & Column 3 \\\n    \\midrule\n    Row 1 & 0.0 & 0.0 \\\n    Row 2 & 0.0 & 0.0 \\\n    \\bottomrule\n  \\end{tabular}\n  \\caption{Caption here}\n  \\label{tab:example}\n\\end{table}\n\n', 'Caption here'), [insertSnippet])
  const insertCite = useCallback(() => {
    if (readOnly) return
    insertSnippet('\\cite{key}', 'key')
  }, [readOnly, insertSnippet])
  const handleInsertBibliographyAction = useCallback(() => {
    if (readOnly) return
    insertSnippet('\n% Bibliography\n\\bibliographystyle{plain}\n\\bibliography{main}\n', 'bibliography')
  }, [readOnly, insertSnippet])

  // Formatting action map keyed by toolbar config key
  const formattingActions = useMemo(() => ({
    section: () => insertHeading('section', 'Section Title'),
    subsection: () => insertHeading('subsection', 'Subsection Title'),
    paragraph: () => insertHeading('paragraph', 'Paragraph Title'),
    bold: insertBold,
    italic: insertItalics,
    smallcaps: insertSmallCaps,
    code: insertInlineCode,
    quote: insertQuote,
    footnote: insertFootnote,
    'math-inline': insertInlineMath,
    'math-display': insertDisplayMath,
    align: insertAlignEnv,
    itemize: insertItemize,
    enumerate: insertEnumerate,
    description: insertDescription,
    figure: insertFigure,
    table: insertTable,
    cite: insertCite,
    bibliography: handleInsertBibliographyAction,
  }), [insertHeading, insertBold, insertItalics, insertSmallCaps, insertInlineCode, insertQuote, insertFootnote, insertInlineMath, insertDisplayMath, insertAlignEnv, insertItemize, insertEnumerate, insertDescription, insertFigure, insertTable, insertCite, handleInsertBibliographyAction])

  const formattingGroups = useMemo(() => LATEX_FORMATTING_GROUPS.map(group => ({
    label: group.label,
    items: group.items.map(item => {
      const Icon = item.Icon
      return {
        key: item.key,
        label: item.label,
        title: item.title,
        icon: React.createElement(Icon, { className: 'h-3.5 w-3.5' }),
        action: formattingActions[item.key as keyof typeof formattingActions] ?? (() => {}),
      }
    }),
  })), [formattingActions])

  return {
    formattingActions,
    formattingGroups,
    insertAtDocumentEnd,
    insertSnippet,
    insertBold,
    insertItalics,
    insertInlineMath,
    insertCite,
    insertFigure,
    insertTable,
    insertItemize,
    insertEnumerate,
    handleFigureInsert,
    handleInsertBibliographyAction,
  }
}
