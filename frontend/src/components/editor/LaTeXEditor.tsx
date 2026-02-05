import React, { useEffect, useState, useMemo, forwardRef, useImperativeHandle, useCallback } from 'react'
import { logEvent } from '../../utils/metrics'
import { researchPapersAPI, buildApiUrl } from '../../services/api'
import { EditorSelection, type SelectionRange } from '@codemirror/state'
import 'katex/dist/katex.min.css'
import pdfViewerHtml from '../../assets/pdf-viewer.html?raw'
import { LATEX_FORMATTING_GROUPS } from './latexToolbarConfig'
import FigureUploadDialog from './FigureUploadDialog'
import CitationDialog from './CitationDialog'
import HistoryPanel from './HistoryPanel'
import { useSplitPane } from './hooks/useSplitPane'
import { useRealtimeSync } from './hooks/useRealtimeSync'
import { useCodeMirrorEditor } from './hooks/useCodeMirrorEditor'
import { useLatexCompilation } from './hooks/useLatexCompilation'
import { EditorToolbar } from './components/EditorToolbar'
import { PdfPreviewPane } from './components/PdfPreviewPane'

interface LaTeXEditorProps {
  value: string
  onChange: (next: string) => void
  onSave?: (content: string, contentJson: any) => Promise<void>
  templateTitle?: string
  fullHeight?: boolean
  paperId?: string
  projectId?: string
  readOnly?: boolean
  disableSave?: boolean
  branchName?: 'draft' | 'published'
  lockedSectionKeys?: string[]
  allowAutoVersion?: boolean
  uncontrolled?: boolean
  onNavigateBack?: () => void
  onOpenReferences?: () => void
  onInsertBibliographyShortcut?: () => void
  onOpenAiChatWithMessage?: (message: string) => void
  realtime?: {
    doc: any
    awareness?: any
    status?: 'idle' | 'connecting' | 'connected' | 'disconnected' | 'timeout'
    peers?: Array<{ id: string; name: string; email: string; color?: string }>
    version?: number
    synced?: boolean
  }
  collaborationStatus?: string | null
}

export interface LaTeXEditorHandle {
  getSelection: () => string
  replaceSelection: (text: string) => void
  setValue: (text: string) => void
  focus: () => void
}

// Generate BibTeX key from reference (same as in CitationDialog)
function makeBibKey(ref: any): string {
  try {
    const first = (Array.isArray(ref.authors) && ref.authors.length > 0) ? String(ref.authors[0]) : ''
    const lastToken = first.split(/\s+/).filter(Boolean).slice(-1)[0] || ''
    const last = lastToken.toLowerCase()
    const yr = ref.year ? String(ref.year) : ''
    const base = (ref.title || '').toLowerCase().replace(/[^a-z0-9\s]/g, ' ')
    const parts = base.split(/\s+/).filter(Boolean)
    const short = (parts.slice(0, 3).join('')).slice(0, 12)
    const key = (last + yr + short) || ('ref' + yr)
    return key
  } catch {
    return 'ref'
  }
}

// LaTeX editor with CodeMirror and live PDF preview
function LaTeXEditorImpl(
  { value, onChange, onSave, templateTitle, fullHeight = false, paperId, projectId, readOnly = false, disableSave = false, onNavigateBack, onOpenAiChatWithMessage, realtime, collaborationStatus }: LaTeXEditorProps,
  ref: React.Ref<LaTeXEditorHandle>
) {
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'code' | 'split' | 'pdf'>('split')
  const [figureDialogOpen, setFigureDialogOpen] = useState(false)
  const [citationDialogOpen, setCitationDialogOpen] = useState(false)
  const [historyPanelOpen, setHistoryPanelOpen] = useState(false)
  const [citationAnchor, setCitationAnchor] = useState<HTMLElement | null>(null)
  const [aiActionLoading, setAiActionLoading] = useState<string | null>(null)
  // Resizable split view
  const { splitPosition, splitContainerRef, handleSplitDragStart } = useSplitPane()
  const { ySharedText, yUndoManager, yTextReady, remoteSelections, realtimeExtensions } = useRealtimeSync({
    realtimeDoc: realtime?.doc || null,
    awareness: realtime?.awareness || null,
    peers: realtime?.peers || [],
    readOnly,
    providerVersion: realtime?.version,
    synced: realtime?.synced,
  })

  // CodeMirror editor lifecycle hook
  const {
    viewRef,
    editorReady,
    undoEnabled,
    redoEnabled,
    hasTextSelected,
    handleContainerRef,
    flushBufferedChange,
    latestDocRef,
    handleUndo,
    handleRedo,
  } = useCodeMirrorEditor({
    value,
    onChange,
    readOnly,
    realtimeDoc: realtime?.doc || null,
    realtimeAwareness: realtime?.awareness || null,
    realtimeExtensions,
    ySharedText,
    yUndoManager,
    yTextReady,
    remoteSelections,
    synced: realtime?.synced,
  })

  // Stable accessor for latest document source
  const getLatestSource = useCallback(() => {
    try { const v = viewRef.current; if (v) return v.state.doc.toString() } catch {}
    return latestDocRef.current || ''
  }, [viewRef, latestDocRef])

  // LaTeX compilation hook
  const {
    iframeRef,
    compileStatus,
    compileError,
    compileLogs,
    lastCompileAt,
    compileNow,
  } = useLatexCompilation({
    paperId,
    readOnly,
    getLatestSource,
    flushBufferedChange,
  })

  // Expose imperative handle
  useImperativeHandle(ref, () => ({
    getSelection: () => {
      try { const v = viewRef.current; if (!v) return ''; const sel = v.state.selection.main; return v.state.doc.sliceString(sel.from, sel.to) } catch { return '' }
    },
    replaceSelection: (text: string) => {
      try { const v = viewRef.current; if (!v) return; const sel = v.state.selection.main; v.dispatch({ changes: { from: sel.from, to: sel.to, insert: text || '' } }); v.focus() } catch {}
    },
    setValue: (text: string) => {
      const next = text || ''
      if (realtime?.doc) {
        try {
          const yText = realtime.doc.getText('main')
          yText.delete(0, yText.length)
          yText.insert(0, next)
        } catch (err) {
          console.warn('[LaTeXEditor] realtime setValue failed', err)
        }
        return
      }
      try { const v = viewRef.current; if (!v) return; const cur = v.state.doc.toString(); v.dispatch({ changes: { from: 0, to: cur.length, insert: next } }) } catch {}
    },
    focus: () => { try { viewRef.current?.focus() } catch {} }
  }), [realtime])

  // Listen for LaTeX insertion events from sidebar (bibliography, cite)
  useEffect(() => {
    const onInsertBib = () => {
      try {
        const v = viewRef.current
        if (!v) return
        const doc = v.state.doc.toString()
        if (/\\bibliography\{/.test(doc)) return
        const insert = ['','% Bibliography','\\bibliographystyle{plain}','\\bibliography{main}',''].join('\n')
        const endIdx = doc.lastIndexOf('\\end{document}')
        const pos = endIdx >= 0 ? endIdx : v.state.doc.length
        v.dispatch({ changes: { from: pos, to: pos, insert } })
        v.focus()
      } catch {}
    }
    const onInsertNoCite = (e: Event) => {
      try {
        const v = viewRef.current
        if (!v) return
        const ev = e as CustomEvent
        const keys: string[] = Array.isArray(ev.detail?.keys) ? ev.detail.keys : []
        if (!keys.length) return
        const doc = v.state.doc.toString()
        const line = `\\nocite{${Array.from(new Set(keys)).join(',')}}\n`
        const endIdx = doc.lastIndexOf('\\end{document}')
        const pos = endIdx >= 0 ? endIdx : v.state.doc.length
        v.dispatch({ changes: { from: pos, to: pos, insert: '\n' + line } })
        v.focus()
      } catch {}
    }
    const onInsertCite = (e: Event) => {
      try {
        const v = viewRef.current
        if (!v) return
        const ev = e as CustomEvent
        const key = ev.detail?.key
        if (!key) return
        const sel = v.state.selection.main
        const insert = `\\cite{${key}}`
        v.dispatch({ changes: { from: sel.from, to: sel.to, insert } })
        v.focus()
      } catch {}
    }
    window.addEventListener('SH_LATEX_INSERT_BIB', onInsertBib)
    window.addEventListener('SH_LATEX_INSERT_NOCITE', onInsertNoCite as any)
    window.addEventListener('SH_LATEX_INSERT_CITE', onInsertCite as any)
    return () => {
      window.removeEventListener('SH_LATEX_INSERT_BIB', onInsertBib)
      window.removeEventListener('SH_LATEX_INSERT_NOCITE', onInsertNoCite as any)
      window.removeEventListener('SH_LATEX_INSERT_CITE', onInsertCite as any)
    }
  }, [])

  const containerCls = fullHeight
    ? 'flex flex-1 min-h-0 flex-col bg-white text-slate-900 transition-colors dark:bg-slate-900 dark:text-slate-100'
    : 'flex flex-1 min-h-0 flex-col bg-white text-slate-900 transition-colors dark:bg-slate-900 dark:text-slate-100'
  const showEditor = viewMode === 'code' || viewMode === 'split'
  const showPreview = viewMode === 'pdf' || viewMode === 'split'
  const splitLayout = viewMode === 'split'
  const contentLayoutCls = splitLayout
    ? 'mt-2 flex-1 min-h-0 flex overflow-hidden'
    : 'mt-2 flex-1 min-h-0 flex flex-col'
  // In split mode, use dynamic widths based on splitPosition
  const editorPaneCls = splitLayout
    ? 'relative min-w-0 overflow-hidden rounded-l-md border border-slate-200 bg-white shadow-sm transition-colors dark:border-slate-800 dark:bg-slate-950/40 dark:shadow-slate-950/30'
    : 'relative flex-1 min-h-0 overflow-auto rounded-md border border-slate-200 bg-white shadow-sm transition-colors dark:border-slate-800 dark:bg-slate-950/40 dark:shadow-slate-950/30'
  const previewPaneCls = splitLayout
    ? 'min-w-0 flex flex-col overflow-hidden rounded-r-md border border-l-0 border-slate-200 bg-white shadow-sm transition-colors dark:border-slate-800 dark:bg-slate-950/40 dark:shadow-slate-950/30'
    : 'flex-1 min-h-0 flex flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm transition-colors dark:border-slate-800 dark:bg-slate-950/40 dark:shadow-slate-950/30'

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

  const insertHeading = useCallback((command: 'section' | 'subsection' | 'paragraph', placeholder: string) => {
    const prefix = `\\${command}{`
    const suffix = `}\n\n`
    applyWrapper(prefix, suffix, placeholder)
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
  const insertFigure = useCallback(() => {
    setFigureDialogOpen(true)
  }, [])

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
    // Simple direct insertion - user can manually edit the style
    insertSnippet('\n% Bibliography\n\\bibliographystyle{plain}\n\\bibliography{main}\n', 'bibliography')
  }, [readOnly, insertSnippet])

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
        icon: <Icon className="h-3.5 w-3.5" />,
        action: formattingActions[item.key as keyof typeof formattingActions] ?? (() => {}),
      }
    }),
  })), [formattingActions])

  const handleOpenReferencesToolbar = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    if (readOnly) return
    // Store button element for positioning
    const button = event.currentTarget
    setCitationAnchor(button)
    setCitationDialogOpen(true)
  }, [readOnly])

  const handleInsertCitation = useCallback((citationKey: string, _references?: any[]) => {
    const cite = `\\cite{${citationKey}}`
    insertSnippet(cite, citationKey)
  }, [insertSnippet])

  const getSelectedText = useCallback(() => {
    try {
      const view = viewRef.current
      if (!view) return ''
      const sel = view.state.selection.main
      return view.state.doc.sliceString(sel.from, sel.to)
    } catch {
      return ''
    }
  }, [])

  const replaceSelectedText = useCallback((text: string) => {
    try {
      const view = viewRef.current
      if (!view) return
      const sel = view.state.selection.main
      view.dispatch({
        changes: { from: sel.from, to: sel.to, insert: text || '' }
      })
      view.focus()
    } catch {}
  }, [])

  const handleAiAction = useCallback(async (action: string, tone?: string) => {
    if (readOnly || aiActionLoading) return

    const selectedText = getSelectedText()
    if (!selectedText.trim()) {
      alert('Please select some text first')
      return
    }

    // For explain/summarize/synonyms: redirect to AI chat panel (non-destructive)
    const chatActions = ['explain', 'summarize', 'synonyms']
    if (chatActions.includes(action) && onOpenAiChatWithMessage) {
      const actionLabels: Record<string, string> = {
        explain: 'Explain this text',
        summarize: 'Summarize this text',
        synonyms: 'Suggest synonyms for key terms in this text',
      }
      const prompt = `${actionLabels[action]}:\n\n"${selectedText}"`
      onOpenAiChatWithMessage(prompt)
      return
    }

    // For paraphrase/tone: in-place replacement via API
    const loadingKey = action === 'tone' && tone ? `tone_${tone}` : action
    setAiActionLoading(loadingKey)

    try {
      const payload: any = {
        text: selectedText,
        action: action,
        project_id: projectId,
      }

      if (tone) {
        payload.tone = tone
      }

      const token = localStorage.getItem('access_token')
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      }
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const response = await fetch(buildApiUrl('/ai/text-tools'), {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`)
      }

      const data = await response.json()
      if (data.result) {
        replaceSelectedText(data.result)
      }
    } catch (error) {
      console.error('AI action failed:', error)
      alert('Failed to process text. Please try again.')
    } finally {
      setAiActionLoading(null)
    }
  }, [readOnly, getSelectedText, replaceSelectedText, projectId, aiActionLoading, onOpenAiChatWithMessage])

  const handleRestoreFromHistory = useCallback((content: string, _snapshotId: string) => {
    if (realtime?.doc) {
      try {
        const yText = realtime.doc.getText('main')
        yText.delete(0, yText.length)
        yText.insert(0, content)
      } catch (err) {
        console.warn('[LaTeXEditor] realtime restore failed', err)
      }
    } else {
      try {
        const v = viewRef.current
        if (v) {
          const cur = v.state.doc.toString()
          v.dispatch({ changes: { from: 0, to: cur.length, insert: content } })
        }
      } catch {}
    }
    setHistoryPanelOpen(false)
  }, [realtime])

  const handleSave = useCallback(async () => {
    if (disableSave || readOnly || saveState === 'saving') return
    flushBufferedChange()
    setSaveState('saving')
    setSaveError(null)
    try {
      const v = viewRef.current?.state.doc.toString() || ''
      const contentJson = { authoring_mode: 'latex', latex_source: v }
      const activePaperId = paperId ?? (window as any).__SH_ACTIVE_PAPER_ID

      if (onSave) {
        await onSave(v, contentJson)
      } else {
        if (!activePaperId) throw new Error('Missing paper id')
        await researchPapersAPI.updatePaperContent(activePaperId, { content_json: contentJson, manual_save: true })
      }

      try { logEvent('LatexSaveClicked', { len: v.length }) } catch {}
      setSaveState('success')
      setTimeout(() => setSaveState('idle'), 2000)
    } catch (e: any) {
      console.warn('Save failed', e)
      setSaveState('error')
      setSaveError(e?.message || 'Save failed')
    }
  }, [disableSave, readOnly, saveState, flushBufferedChange, paperId, onSave])

  return (
    <div className={containerCls}>
      <EditorToolbar
        viewMode={viewMode}
        onSetViewMode={setViewMode}
        onNavigateBack={onNavigateBack}
        templateTitle={templateTitle}
        collaborationStatus={collaborationStatus}
        compileStatus={compileStatus}
        compileError={compileError}
        lastCompileAt={lastCompileAt}
        onCompile={compileNow}
        readOnly={readOnly}
        disableSave={disableSave}
        saveState={saveState}
        saveError={saveError}
        onSave={handleSave}
        undoEnabled={undoEnabled}
        redoEnabled={redoEnabled}
        onUndo={handleUndo}
        onRedo={handleRedo}
        hasTextSelected={hasTextSelected}
        formattingGroups={formattingGroups}
        onInsertBold={insertBold}
        onInsertItalics={insertItalics}
        onInsertInlineMath={insertInlineMath}
        onInsertCite={insertCite}
        onInsertFigure={insertFigure}
        onInsertTable={insertTable}
        onInsertItemize={insertItemize}
        onInsertEnumerate={insertEnumerate}
        paperId={paperId}
        onOpenReferences={handleOpenReferencesToolbar}
        onOpenHistory={() => setHistoryPanelOpen(true)}
        aiActionLoading={aiActionLoading}
        onAiAction={handleAiAction}
      />
      <div ref={splitContainerRef} className={contentLayoutCls}>
        {showEditor && (
          <div
            className={editorPaneCls}
            style={splitLayout ? { width: `${splitPosition}%` } : undefined}
          >
            <div ref={handleContainerRef} className="absolute inset-0" />
            {!editorReady && (
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-white/80 text-xs text-slate-500 dark:bg-slate-950/70 dark:text-slate-300">
                Initializing editor…
              </div>
            )}
          </div>
        )}

        {/* Resizable Divider */}
        {splitLayout && showEditor && showPreview && (
          <div
            className="group relative z-10 flex w-1 cursor-col-resize items-center justify-center bg-slate-200 transition-colors hover:bg-indigo-400 dark:bg-slate-700 dark:hover:bg-indigo-500"
            onMouseDown={handleSplitDragStart}
          >
            <div className="absolute flex h-8 w-4 items-center justify-center rounded bg-slate-300 opacity-0 transition-opacity group-hover:opacity-100 dark:bg-slate-600">
              <div className="flex flex-col gap-0.5">
                <div className="h-0.5 w-1 rounded-full bg-slate-500 dark:bg-slate-400" />
                <div className="h-0.5 w-1 rounded-full bg-slate-500 dark:bg-slate-400" />
                <div className="h-0.5 w-1 rounded-full bg-slate-500 dark:bg-slate-400" />
              </div>
            </div>
          </div>
        )}

        {showPreview && (
          <div
            className={previewPaneCls}
            style={splitLayout ? { width: `${100 - splitPosition}%` } : undefined}
          >
            <PdfPreviewPane
              iframeRef={iframeRef}
              pdfViewerHtml={pdfViewerHtml}
              compileStatus={compileStatus}
              compileError={compileError}
              compileLogs={compileLogs}
              lastCompileAt={lastCompileAt}
            />
          </div>
        )}
      </div>

      {paperId && (
        <FigureUploadDialog
          isOpen={figureDialogOpen}
          onClose={() => setFigureDialogOpen(false)}
          onInsert={handleFigureInsert}
          paperId={paperId}
        />
      )}

      {paperId && (
        <CitationDialog
          isOpen={citationDialogOpen}
          onClose={() => setCitationDialogOpen(false)}
          paperId={paperId}
          projectId={projectId}
          onInsertCitation={handleInsertCitation}
          onInsertBibliography={async (style, bibFile, references) => {
            const bibContent = references.map(ref => {
              const key = makeBibKey(ref)
              const authors = ref.authors?.join(' and ') || ''
              const title = ref.title || ''
              const year = ref.year || ''
              const journal = ref.journal || ''
              const doi = ref.doi || ''

              return `@article{${key},
  author = {${authors}},
  title = {${title}},
  year = {${year}},
  journal = {${journal}},
  doi = {${doi}}
}`
            }).join('\n\n')

            try {
              const formData = new FormData()
              const bibFile_obj = new File([bibContent], `${bibFile}.bib`, {
                type: 'application/x-bibtex'
              })
              formData.append('file', bibFile_obj)
              await researchPapersAPI.uploadBib(paperId, formData)
              const snippet = `\\clearpage\n% Bibliography\n\\bibliographystyle{${style}}\n\\bibliography{${bibFile}}\n`
              insertAtDocumentEnd(snippet, bibFile)
            } catch (error: any) {
              console.error('Failed to upload .bib file:', error)
              const detail = error.response?.data?.detail
              const message = Array.isArray(detail)
                ? detail.map((d: any) => `${d.loc?.join('.') || 'unknown'}: ${d.msg}`).join(', ')
                : (detail || error.message || 'Upload failed')
              alert(`Failed to upload bibliography file. ${message}`)
            }
          }}
          anchorElement={citationAnchor}
        />
      )}

      {paperId && historyPanelOpen && (
        <HistoryPanel
          paperId={paperId}
          isOpen={historyPanelOpen}
          onClose={() => setHistoryPanelOpen(false)}
          onRestore={handleRestoreFromHistory}
          currentContent={viewRef.current?.state?.doc?.toString() || ''}
        />
      )}
    </div>
  )
}

const ForwardedLaTeXEditor = forwardRef(LaTeXEditorImpl) as React.ForwardRefExoticComponent<LaTeXEditorProps & React.RefAttributes<LaTeXEditorHandle>>
const LaTeXEditor = React.memo(ForwardedLaTeXEditor)

export default LaTeXEditor
