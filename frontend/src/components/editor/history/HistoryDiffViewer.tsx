import React, { useEffect, useRef } from 'react'
import { EditorState } from '@codemirror/state'
import { EditorView, lineNumbers, drawSelection } from '@codemirror/view'
import { latexLanguageSetup, latexHighlightFixes } from '../extensions/latexLanguageSetup'
import { overleafLatexTheme } from '../codemirror/overleafTheme'
import { historyDiffExtension, setDiffLines, type DiffLineInfo } from '../extensions/historyDiffDecorations'
import type { SnapshotDiffResponse } from '../../../services/api'

interface HistoryDiffViewerProps {
  diffData: SnapshotDiffResponse
}

export const HistoryDiffViewer: React.FC<HistoryDiffViewerProps> = ({ diffData }) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    // Cleanup previous view
    if (viewRef.current) {
      viewRef.current.destroy()
      viewRef.current = null
    }

    // Build merged document and diff info from diff_lines
    const mergedDoc = diffData.diff_lines.map(l => l.content).join('\n')
    const diffLineInfos: DiffLineInfo[] = diffData.diff_lines.map((l, i) => ({
      lineNumber: i + 1,
      type: l.type,
    }))

    const state = EditorState.create({
      doc: mergedDoc,
      extensions: [
        lineNumbers(),
        drawSelection(),
        EditorState.readOnly.of(true),
        EditorView.editable.of(false),
        latexLanguageSetup(),
        latexHighlightFixes(),
        overleafLatexTheme,
        ...historyDiffExtension(),
        EditorView.lineWrapping,
      ],
    })

    const view = new EditorView({
      state,
      parent: containerRef.current,
    })

    // Dispatch diff decorations
    view.dispatch({
      effects: setDiffLines.of(diffLineInfos),
    })

    viewRef.current = view

    return () => {
      view.destroy()
      viewRef.current = null
    }
  }, [diffData])

  return <div ref={containerRef} className="h-full" />
}
