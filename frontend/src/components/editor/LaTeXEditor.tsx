import React, { useEffect, useState, useRef, forwardRef, useImperativeHandle, useCallback, useMemo } from 'react'
import { useIsMobile } from '../../hooks/useMediaQuery'
import 'katex/dist/katex.min.css'
import pdfViewerHtml from '../../assets/pdf-viewer.html?raw'
import FigureUploadDialog from './FigureUploadDialog'
import CitationDialog from './CitationDialog'
import { useHistoryView } from './hooks/useHistoryView'
import { HistoryView } from './history/HistoryView'
import { useSplitPane } from './hooks/useSplitPane'
import { useRealtimeSync } from './hooks/useRealtimeSync'
import { useCodeMirrorEditor } from './hooks/useCodeMirrorEditor'
import { useLatexCompilation } from './hooks/useLatexCompilation'
import { useMultiFileManagement } from './hooks/useMultiFileManagement'
import { useLatexEventListeners } from './hooks/useLatexEventListeners'
import { useHistoryRestore } from './hooks/useHistoryRestore'
import { useLatexSnippets } from './hooks/useLatexSnippets'
import { useCitationHandlers } from './hooks/useCitationHandlers'
import { useAiTextTools } from './hooks/useAiTextTools'
import { useAuth } from '../../contexts/AuthContext'
import { API_ROOT, latexAPI } from '../../services/api'
import { EditorView } from '@codemirror/view'
import { toggleVisualModeEffect } from './extensions/latexVisualMode'
import { EditorToolbar } from './components/EditorToolbar'
import { PdfPreviewPane } from './components/PdfPreviewPane'
import { FileSelector } from './components/FileSelector'
import { FilePanel } from './components/FilePanel'
import { EditorMenuBar } from './components/EditorMenuBar'
import { EditorSideRail } from './components/EditorSideRail'
import { SymbolPalette } from './components/SymbolPalette'
import { TrackChangesPanel } from './components/TrackChangesPanel'
import { WritingAnalysisPanel, type WritingAnalysisResult } from './components/WritingAnalysisPanel'
import { useToast } from '../../hooks/useToast'
import SubmissionBuilder from './components/SubmissionBuilder'
import { useDocumentOutline } from './hooks/useDocumentOutline'
import { useSyncTeX } from './hooks/useSyncTeX'
import { useTrackChanges } from './hooks/useTrackChanges'
import { dispatchTrackedChanges, type TrackedChangeDecoration } from './extensions/trackChangesDecoration'
import { setDiagnostics } from '@codemirror/lint'
import { latexErrorsToDiagnostics } from './extensions/latexErrorMarkers'

interface LaTeXEditorProps {
  value: string
  onChange: (next: string) => void
  onSave?: (content: string, contentJson: any) => Promise<void>
  templateTitle?: string
  paperId?: string
  projectId?: string
  readOnly?: boolean
  disableSave?: boolean
  onNavigateBack?: () => void
  onOpenAiChatWithMessage?: (message: string) => void
  realtime?: {
    doc: any
    awareness?: any
    status?: 'idle' | 'connecting' | 'connected' | 'disconnected' | 'timeout'
    peers?: Array<{ id: string; name: string; email: string; color?: string }>
    version?: number
    synced?: boolean
    paperRole?: 'admin' | 'editor' | 'viewer'
  }
  collaborationStatus?: string | null
  onRenamePaper?: (newTitle: string) => Promise<void>
}

export interface LaTeXEditorHandle {
  getSelection: () => string
  replaceSelection: (text: string) => void
  setValue: (text: string) => void
  focus: () => void
}

// LaTeX editor with CodeMirror and live PDF preview
function LaTeXEditorImpl(
  { value, onChange, onSave, templateTitle, paperId, projectId, readOnly = false, disableSave = false, onOpenAiChatWithMessage, realtime, onRenamePaper }: LaTeXEditorProps,
  ref: React.Ref<LaTeXEditorHandle>
) {
  const isMobile = useIsMobile()
  const [viewMode, setViewMode] = useState<'code' | 'split' | 'pdf'>(() =>
    window.innerWidth < 640 ? 'pdf' : 'split'
  )
  const [figureDialogOpen, setFigureDialogOpen] = useState(false)
  const [sideRailPanel, setSideRailPanel] = useState<'files' | 'search' | null>(null)
  const [showBreadcrumbs, setShowBreadcrumbs] = useState(true)
  const [exportDocxLoading, setExportDocxLoading] = useState(false)
  const [exportSourceZipLoading, setExportSourceZipLoading] = useState(false)
  const [symbolPaletteOpen, setSymbolPaletteOpen] = useState(false)
  const tcKey = paperId ? `tc-enabled-${paperId}` : null
  const [trackChangesEnabled, setTrackChangesEnabled] = useState(() => {
    if (!tcKey) return false
    try { return localStorage.getItem(tcKey) === '1' } catch { return false }
  })
  // Re-read localStorage when paperId becomes available (may be undefined on first render)
  useEffect(() => {
    if (!tcKey) return
    try {
      const stored = localStorage.getItem(tcKey) === '1'
      setTrackChangesEnabled(stored)
    } catch {}
  }, [tcKey])
  const [trackChangesPanelOpen, setTrackChangesPanelOpen] = useState(false)
  const [writingAnalysisPanelOpen, setWritingAnalysisPanelOpen] = useState(false)
  const [writingAnalysisResult, setWritingAnalysisResult] = useState<WritingAnalysisResult | null>(null)
  const [writingAnalysisLoading, setWritingAnalysisLoading] = useState(false)
  const [submissionBuilderOpen, setSubmissionBuilderOpen] = useState(false)
  const [visualMode, setVisualMode] = useState(false)
  const [activeFile, setActiveFile] = useState('main.tex')

  // Current user identity (for track changes attribution)
  const { user: authUser } = useAuth()
  const { toast } = useToast()

  // Resizable split view
  const { splitPosition, splitContainerRef, handleSplitDragStart } = useSplitPane()

  // Realtime sync (Yjs)
  const { ySharedText, yUndoManager, yTextReady, remoteSelections, realtimeExtensions, getYText, getFileList } = useRealtimeSync({
    realtimeDoc: realtime?.doc || null,
    awareness: realtime?.awareness || null,
    peers: realtime?.peers || [],
    readOnly,
    providerVersion: realtime?.version,
    synced: realtime?.synced,
    activeFile,
  })

  // Multi-file management
  const { fileList, handleCreateFile, handleDeleteFile, handleSelectFile } = useMultiFileManagement({
    realtimeDoc: realtime?.doc || null,
    getYText,
    getFileList,
    yTextReady,
    activeFile,
    onActiveFileChange: setActiveFile,
  })

  // Track changes hook (must come AFTER useMultiFileManagement for fileList,
  // and BEFORE useCodeMirrorEditor to provide the transaction filter)
  const trackChanges = useTrackChanges({
    yText: ySharedText,
    realtimeDoc: realtime?.doc || null,
    fileList,
    enabled: trackChangesEnabled,
    userId: authUser?.id || 'local',
    userName: [authUser?.first_name, authUser?.last_name].filter(Boolean).join(' ') || 'You',
    userColor: '#3B82F6',
  })
  // getTransactionFilter has [] deps (uses refs internally), so this is created once
  const trackFilterExt = useMemo(() => trackChanges.getTransactionFilter(), [trackChanges.getTransactionFilter])

  // CodeMirror editor lifecycle
  const {
    viewRef, editorReady, undoEnabled, redoEnabled, hasTextSelected, boldActive, italicActive,
    handleContainerRef, flushBufferedChange, latestDocRef, handleUndo, handleRedo, onSaveRef,
  } = useCodeMirrorEditor({
    value, onChange, readOnly,
    realtimeDoc: realtime?.doc || null,
    realtimeAwareness: realtime?.awareness || null,
    realtimeExtensions, ySharedText, yUndoManager, yTextReady, remoteSelections,
    synced: realtime?.synced, paperId,
    trackChangesFilter: trackFilterExt,
  })

  // Dispatch visual mode toggle via CM6 effect (avoids extension reconfigure)
  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    view.dispatch({ effects: toggleVisualModeEffect.of(visualMode) })
  }, [visualMode, editorReady])

  // Stable accessor for latest MAIN document source (always main.tex, not the active file)
  const getLatestSource = useCallback(() => {
    // In realtime mode, ALWAYS read from Y.Text('main') — never the editor view
    if (realtime?.doc) {
      return realtime.doc.getText('main').toString()
    }
    // Non-realtime: editor always shows main.tex (no multi-file)
    try { const v = viewRef.current; if (v) return v.state.doc.toString() } catch {}
    return latestDocRef.current || ''
  }, [viewRef, latestDocRef, realtime?.doc])

  // Multi-file: get contents of all extra files for compilation
  const getExtraFiles = useCallback((): Record<string, string> | null => {
    if (fileList.length <= 1) return null
    const files: Record<string, string> = {}
    for (const f of fileList) {
      if (f === 'main.tex') continue
      if (realtime?.doc) {
        const yText = getYText(f)
        if (yText) files[f] = yText.toString()
      }
    }
    return Object.keys(files).length > 0 ? files : null
  }, [fileList, realtime?.doc, getYText])

  // LaTeX compilation
  const {
    iframeRef, compileStatus, compileError, compileLogs, compileErrors, lastCompileAt, compileNow, contentHash,
    autoCompileEnabled, toggleAutoCompile, triggerAutoCompile,
  } = useLatexCompilation({ paperId, readOnly, getLatestSource, flushBufferedChange, getExtraFiles })

  // SyncTeX: bidirectional PDF <-> source sync
  const { forwardSync, backwardSync } = useSyncTeX({ contentHash, enabled: compileStatus === 'success' })

  // Forward sync: source line → PDF position
  const handleForwardSync = useCallback(() => {
    const view = viewRef.current
    if (!view) return
    const line = view.state.doc.lineAt(view.state.selection.main.head).number
    const result = forwardSync(line)
    if (!result) return
    const iframe = iframeRef.current
    if (!iframe?.contentWindow) return
    iframe.contentWindow.postMessage(
      { type: 'syncToPosition', page: result.page, x: result.x, y: result.y },
      window.location.origin
    )
  }, [forwardSync, iframeRef])

  // Backward sync: PDF click → source line
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const data = event.data
      if (!data || data.type !== 'syncToSource') return
      const iframe = iframeRef.current
      if (iframe && event.source !== iframe.contentWindow) return
      const page = Number(data.page)
      const x = Number(data.x)
      const y = Number(data.y)
      if (!Number.isFinite(page) || !Number.isFinite(x) || !Number.isFinite(y)) return
      const result = backwardSync(page, x, y)
      if (!result) return
      const view = viewRef.current
      if (!view) return
      try {
        const lineInfo = view.state.doc.line(Math.min(result.line, view.state.doc.lines))
        view.dispatch({ selection: { anchor: lineInfo.from }, scrollIntoView: true })
        view.focus()
      } catch {}
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [backwardSync, iframeRef])

  // Keep a ref to contentHash for use in async export handlers
  const contentHashRef = useRef(contentHash)
  useEffect(() => { contentHashRef.current = contentHash }, [contentHash])

  // Export: Download PDF
  const handleExportPdf = useCallback(async () => {
    let hash = contentHashRef.current
    if (!hash) {
      // No compile yet — trigger one and wait for it
      await compileNow()
      // After compile, contentHash state updates asynchronously;
      // give it a tick to propagate
      await new Promise(r => setTimeout(r, 300))
      hash = contentHashRef.current
    }
    if (!hash) return
    try {
      const resp = await fetch(`${API_ROOT}/api/v1/latex/artifacts/${hash}/main.pdf`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
      })
      if (!resp.ok) return
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'paper.pdf'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('PDF download failed', e)
    }
  }, [compileNow])

  // Export: Download Word (DOCX)
  const handleExportDocx = useCallback(async () => {
    setExportDocxLoading(true)
    try {
      flushBufferedChange()
      const source = getLatestSource()
      const extraFiles = getExtraFiles()
      const resp = await latexAPI.exportDocx({
        latex_source: source,
        paper_id: paperId,
        latex_files: extraFiles ?? undefined,
        include_bibtex: true,
      })
      const blob = new Blob([resp.data as BlobPart], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'paper.docx'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('DOCX export failed', e)
    } finally {
      setExportDocxLoading(false)
    }
  }, [flushBufferedChange, getLatestSource, getExtraFiles, paperId])

  // Export: Download Source ZIP
  const handleExportSourceZip = useCallback(async () => {
    setExportSourceZipLoading(true)
    try {
      flushBufferedChange()
      const source = getLatestSource()
      const extraFiles = getExtraFiles()
      const resp = await latexAPI.exportSourceZip({
        latex_source: source,
        paper_id: paperId,
        latex_files: extraFiles ?? undefined,
        include_bibtex: true,
      })
      const blob = new Blob([resp.data as BlobPart], { type: 'application/zip' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'source.zip'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('Source ZIP export failed', e)
    } finally {
      setExportSourceZipLoading(false)
    }
  }, [flushBufferedChange, getLatestSource, getExtraFiles, paperId])

  // Writing analysis handler
  const handleAnalyzeWriting = useCallback(async (venue?: string) => {
    setWritingAnalysisLoading(true)
    try {
      flushBufferedChange()
      const source = getLatestSource()
      const extraFiles = getExtraFiles()
      const resp = await latexAPI.analyzeWriting({
        latex_source: source,
        paper_id: paperId,
        venue,
        latex_files: extraFiles ?? undefined,
      })
      setWritingAnalysisResult(resp.data)
    } catch (e) {
      console.error('Writing analysis failed', e)
      toast.error('Writing analysis failed')
    } finally {
      setWritingAnalysisLoading(false)
    }
  }, [flushBufferedChange, getLatestSource, getExtraFiles, paperId, toast])


  // Symbol palette: insert symbol at cursor
  const handleInsertSymbol = useCallback((latex: string) => {
    const view = viewRef.current
    if (!view) return
    const sel = view.state.selection.main
    view.dispatch({ changes: { from: sel.from, to: sel.to, insert: latex } })
    view.focus()
  }, [viewRef])

  // Sync tracked changes decorations to CodeMirror
  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    const decos: TrackedChangeDecoration[] = trackChanges.trackedChanges.map(c => ({
      from: c.position,
      to: c.position + c.length,
      type: c.type,
      userName: c.userName,
      userColor: c.userColor,
      timestamp: c.timestamp,
    }))
    dispatchTrackedChanges(view, decos)
  }, [trackChanges.trackedChanges, viewRef])

  // Wire document changes to trigger auto-compile
  const triggerAutoCompileRef = useRef(triggerAutoCompile)
  triggerAutoCompileRef.current = triggerAutoCompile

  // Listen for doc changes via the value prop (which onChange passes up)
  const prevValueLenRef = useRef(value.length)
  useEffect(() => {
    if (value.length !== prevValueLenRef.current) {
      prevValueLenRef.current = value.length
      triggerAutoCompileRef.current()
    }
  }, [value])

  // Dispatch compile error diagnostics to CodeMirror lint layer
  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    const diagnostics = compileErrors.length > 0
      ? latexErrorsToDiagnostics(compileErrors, view)
      : []
    view.dispatch(setDiagnostics(view.state, diagnostics))
  }, [compileErrors])

  // Window event listeners for sidebar bibliography/cite insertion
  useLatexEventListeners(viewRef)

  // Document outline (enabled when file panel or breadcrumbs visible)
  const outlineEnabled = sideRailPanel === 'files' || showBreadcrumbs
  const { outline } = useDocumentOutline({ viewRef, enabled: outlineEnabled })

  // Scroll editor to a section position
  const handleScrollToSection = useCallback((from: number) => {
    const view = viewRef.current
    if (!view) return
    view.dispatch({
      selection: { anchor: from },
      effects: EditorView.scrollIntoView(from, { y: 'start' }),
    })
    view.focus()
  }, [viewRef])

  // History restore + save
  // handleRestoreFromHistory will be wired to HistoryView's restore button in Phase 3
  const { handleRestoreFromHistory: _handleRestoreFromHistory, handleSave, saveState } = useHistoryRestore({
    viewRef, realtimeDoc: realtime?.doc || null, paperId, readOnly, disableSave: disableSave ?? false, flushBufferedChange, onSave,
  })

  // History view (full-page mode)
  const historyView = useHistoryView({
    paperId,
    currentContent: viewRef.current?.state?.doc?.toString() || '',
  })

  // History restore handler
  const [historyRestoring, setHistoryRestoring] = useState(false)

  const handleHistoryRestore = useCallback(async (snapshotId: string) => {
    setHistoryRestoring(true)
    const content = await historyView.restoreSnapshot(snapshotId)
    if (content !== null) {
      if (realtime?.doc) {
        try {
          const yText = realtime.doc.getText('main')
          realtime.doc.transact(() => {
            yText.delete(0, yText.length)
            yText.insert(0, content)
          }, 'history-restore')
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
      historyView.exitHistoryMode()
    }
    setHistoryRestoring(false)
  }, [historyView, realtime?.doc, viewRef])

  // Wire Cmd/Ctrl+S to handleSave via the CodeMirror keybinding
  onSaveRef.current = readOnly || disableSave ? null : handleSave

  // Also catch Cmd/Ctrl+S at window level (for when editor doesn't have focus)
  useEffect(() => {
    if (readOnly || disableSave) return
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        handleSave()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [readOnly, disableSave, handleSave])


  // Snippet / formatting insertion
  const {
    formattingActions, formattingGroups, insertAtDocumentEnd, insertSnippet,
    insertBold, insertItalics, insertInlineMath, insertDisplayMath, insertCite, insertRef, insertLink,
    insertFigure, insertTable, insertTableWithSize, insertItemize, insertEnumerate,
    handleFigureInsert,
  } = useLatexSnippets({ viewRef, readOnly, setFigureDialogOpen })

  // Citation dialog
  const {
    citationDialogOpen, citationAnchor,
    handleOpenReferencesToolbar, handleCloseCitationDialog, handleInsertCitation, handleInsertBibliography,
  } = useCitationHandlers({ paperId, readOnly, insertSnippet, insertAtDocumentEnd })

  // Auto-insert citation from URL query param (from "Cite in Paper" flow)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const citeKey = params.get('insertCite')
    if (!citeKey || readOnly) return
    const timer = setTimeout(() => {
      insertSnippet(`\\cite{${citeKey}}`, citeKey)
      const url = new URL(window.location.href)
      url.searchParams.delete('insertCite')
      window.history.replaceState({}, '', url.toString())
    }, 500)
    return () => clearTimeout(timer)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // AI text tools
  const { aiActionLoading, handleAiAction } = useAiTextTools({ viewRef, readOnly, projectId, onOpenAiChatWithMessage })

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

  // Layout classes
  const containerCls = 'flex flex-1 min-h-0 flex-col bg-white text-slate-900 transition-colors dark:bg-slate-900 dark:text-slate-100'
  const showEditor = viewMode === 'code' || viewMode === 'split'
  const showPreview = viewMode === 'pdf' || viewMode === 'split'
  const splitLayout = viewMode === 'split'
  const contentLayoutCls = splitLayout
    ? 'flex-1 min-h-0 flex overflow-hidden'
    : 'flex-1 min-h-0 flex flex-col'
  const editorPaneCls = splitLayout
    ? 'min-w-0 overflow-hidden rounded-l-md border border-slate-200 bg-white shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900 dark:shadow-slate-950/30'
    : 'flex-1 min-h-0 overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900 dark:shadow-slate-950/30'
  const previewPaneCls = splitLayout
    ? 'min-w-0 flex flex-col overflow-hidden rounded-r-md border border-l-0 border-slate-200 bg-white shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900 dark:shadow-slate-950/30'
    : 'flex-1 min-h-0 flex flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900 dark:shadow-slate-950/30'

  // Map viewMode to EditorMenuBar's expected format
  const handleToggleView = useCallback((mode: 'split' | 'editor' | 'pdf') => {
    setViewMode(mode === 'editor' ? 'code' : mode)
  }, [])

  return (
    <div className={containerCls}>
      {historyView.historyMode ? (
        <HistoryView
          paperId={paperId!}
          snapshots={historyView.snapshots}
          snapshotsLoading={historyView.snapshotsLoading}
          selectedSnapshotId={historyView.selectedSnapshotId}
          onSelectSnapshot={historyView.selectSnapshot}
          diffData={historyView.diffData}
          diffLoading={historyView.diffLoading}
          activeTab={historyView.activeTab}
          onSetActiveTab={historyView.setActiveTab}
          onBack={historyView.exitHistoryMode}
          onRestore={handleHistoryRestore}
          restoring={historyRestoring}
          onUpdateLabel={historyView.updateLabel}
          selectedRange={historyView.selectedRange}
          currentStateId={historyView.CURRENT_STATE_ID}
          activeHistoryFile={historyView.activeHistoryFile}
          onFileSelect={historyView.setActiveHistoryFile}
          snapshotFiles={historyView.snapshotFiles}
        />
      ) : (
        <>
          {/* Row 1: Menu Bar */}
          <EditorMenuBar
            editorViewRef={viewRef}
            onCompile={compileNow}
            onToggleView={handleToggleView}
            viewMode={viewMode}
            paperId={paperId}
            activeFile={activeFile}
            paperTitle={templateTitle}
            showBreadcrumbs={showBreadcrumbs}
            onToggleBreadcrumbs={() => setShowBreadcrumbs(prev => !prev)}
            onDownloadPdf={handleExportPdf}
            onSave={readOnly || disableSave ? undefined : handleSave}
            onInsertSnippet={insertSnippet}
            onInsertBold={insertBold}
            onInsertItalics={insertItalics}
            onInsertInlineMath={insertInlineMath}
            onInsertCite={insertCite}
            onInsertFigure={insertFigure}
            onInsertTable={insertTable}
            onInsertItemize={insertItemize}
            onInsertEnumerate={insertEnumerate}
            formattingActions={formattingActions}
            symbolPaletteOpen={symbolPaletteOpen}
            onToggleSymbolPalette={() => setSymbolPaletteOpen(prev => !prev)}
            onForwardSync={handleForwardSync}
            onOpenSubmissionBuilder={() => setSubmissionBuilderOpen(true)}
            onOpenHistory={paperId ? historyView.enterHistoryMode : undefined}
            saveState={saveState}
            onRenamePaper={onRenamePaper}
            canRename={!readOnly && (realtime?.paperRole === 'admin' || !realtime?.paperRole)}
            onExportSourceZip={handleExportSourceZip}
          />

          {/* Row 2: Main content area */}
          <div className="flex flex-1 min-h-0 overflow-hidden">
            {/* Col 1: Side Rail (always visible) */}
            <EditorSideRail
              activePanel={sideRailPanel}
              onTogglePanel={(panel) => setSideRailPanel(prev => prev === panel ? null : panel)}
              trackChangesEnabled={trackChangesEnabled}
              onToggleTrackChanges={ySharedText ? () => setTrackChangesEnabled(prev => {
                const next = !prev
                if (tcKey) try { localStorage.setItem(tcKey, next ? '1' : '0') } catch {}
                return next
              }) : undefined}
              trackChangesPanelOpen={trackChangesPanelOpen}
              onToggleTrackChangesPanel={realtime?.paperRole === 'admin' ? () => setTrackChangesPanelOpen(prev => !prev) : undefined}
              hasTrackedChanges={trackChanges.trackedChanges.length > 0}
              writingAnalysisPanelOpen={writingAnalysisPanelOpen}
              onToggleWritingAnalysis={() => setWritingAnalysisPanelOpen(prev => !prev)}
              writingAnalysisLoading={writingAnalysisLoading}
            />

            {/* Col 2: File Panel (always mounted when paperId exists, hidden when not active) */}
            {paperId && (
              <div className={sideRailPanel === 'files' ? '' : 'hidden'}>
                <FilePanel
                  paperId={paperId}
                  fileList={fileList}
                  activeFile={activeFile}
                  onSelectFile={handleSelectFile}
                  onCreateFile={handleCreateFile}
                  onDeleteFile={handleDeleteFile}
                  readOnly={readOnly}
                  editorViewRef={viewRef}
                  canCreateFiles={!!realtime?.doc}
                  yText={ySharedText}
                  outlineItems={outline}
                  onScrollToSection={handleScrollToSection}
                />
              </div>
            )}

            {/* Col 3: Editor + PDF area */}
            <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
              {/* Split pane: Editor | PDF */}
              <div ref={splitContainerRef} className={contentLayoutCls}>
                {showEditor && (
                  <div className={editorPaneCls + ' flex flex-col'} style={splitLayout ? { width: `${splitPosition}%` } : undefined}>
                    {/* Editor Toolbar — scoped to editor pane only */}
                    <EditorToolbar
                      viewMode={viewMode}
                      isMobile={isMobile}
                      readOnly={readOnly}
                      undoEnabled={undoEnabled}
                      redoEnabled={redoEnabled}
                      onUndo={handleUndo}
                      onRedo={handleRedo}
                      hasTextSelected={hasTextSelected}
                      boldActive={boldActive}
                      italicActive={italicActive}
                      formattingGroups={formattingGroups}
                      onInsertBold={insertBold}
                      onInsertItalics={insertItalics}
                      onInsertInlineMath={insertInlineMath}
                      onInsertDisplayMath={insertDisplayMath}
                      onInsertCite={insertCite}
                      onInsertRef={insertRef}
                      onInsertLink={insertLink}
                      onInsertFigure={insertFigure}
                      onInsertTable={insertTable}
                      onInsertTableWithSize={insertTableWithSize}
                      onInsertItemize={insertItemize}
                      onInsertEnumerate={insertEnumerate}
                      onOpenReferences={handleOpenReferencesToolbar}
                      editorViewRef={viewRef}
                      aiActionLoading={aiActionLoading}
                      onAiAction={handleAiAction}
                      symbolPaletteOpen={symbolPaletteOpen}
                      onToggleSymbolPalette={() => setSymbolPaletteOpen(prev => !prev)}
                      onForwardSync={handleForwardSync}
                      visualMode={visualMode}
                      onToggleVisualMode={() => setVisualMode(prev => !prev)}
                    />
                    {/* Code editor area */}
                    <div className="relative flex-1 min-h-0">
                      {realtime?.doc && sideRailPanel !== 'files' && (
                        <FileSelector
                          files={fileList}
                          activeFile={activeFile}
                          onSelectFile={handleSelectFile}
                          onCreateFile={handleCreateFile}
                          onDeleteFile={handleDeleteFile}
                          readOnly={readOnly}
                        />
                      )}
                      <div ref={handleContainerRef} className={realtime?.doc && sideRailPanel !== 'files' ? 'absolute inset-0 top-auto bottom-0' : 'absolute inset-0'} style={realtime?.doc && fileList.length > 0 && sideRailPanel !== 'files' ? { top: fileList.length > 1 ? '33px' : '29px' } : undefined} />
                      {!editorReady && (
                        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-white/80 text-xs text-slate-500 dark:bg-slate-950/70 dark:text-slate-300">
                          Initializing editor…
                        </div>
                      )}
                    </div>
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
                  <div className={previewPaneCls} style={splitLayout ? { width: `${100 - splitPosition}%` } : undefined}>
                    <PdfPreviewPane
                      iframeRef={iframeRef}
                      pdfViewerHtml={pdfViewerHtml}
                      compileStatus={compileStatus}
                      compileError={compileError}
                      compileLogs={compileLogs}
                      lastCompileAt={lastCompileAt}
                      onCompile={compileNow}
                      autoCompileEnabled={autoCompileEnabled}
                      onToggleAutoCompile={toggleAutoCompile}
                      onExportPdf={handleExportPdf}
                      onExportDocx={handleExportDocx}
                      onExportSourceZip={handleExportSourceZip}
                      exportDocxLoading={exportDocxLoading}
                      exportSourceZipLoading={exportSourceZipLoading}
                    />
                  </div>
                )}
              </div>
            </div>
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
              onClose={handleCloseCitationDialog}
              paperId={paperId}
              projectId={projectId}
              onInsertCitation={handleInsertCitation}
              onInsertBibliography={handleInsertBibliography}
              anchorElement={citationAnchor}
            />
          )}

          {symbolPaletteOpen && (
            <SymbolPalette
              onInsertSymbol={handleInsertSymbol}
              onClose={() => setSymbolPaletteOpen(false)}
            />
          )}

          {trackChangesPanelOpen && trackChanges.trackedChanges.length > 0 && (
            <TrackChangesPanel
              changes={trackChanges.trackedChanges}
              onAcceptChange={trackChanges.acceptChange}
              onRejectChange={trackChanges.rejectChange}
              onAcceptAll={trackChanges.acceptAllChanges}
              onRejectAll={trackChanges.rejectAllChanges}
              onClose={() => setTrackChangesPanelOpen(false)}
            />
          )}

          {writingAnalysisPanelOpen && (
            <WritingAnalysisPanel
              result={writingAnalysisResult}
              loading={writingAnalysisLoading}
              onAnalyze={handleAnalyzeWriting}
              onClose={() => setWritingAnalysisPanelOpen(false)}
            />
          )}

          <SubmissionBuilder
            isOpen={submissionBuilderOpen}
            onClose={() => setSubmissionBuilderOpen(false)}
            getLatexSource={() => { flushBufferedChange(); return getLatestSource() }}
            paperId={paperId}
            getExtraFiles={getExtraFiles}
          />
        </>
      )}
    </div>
  )
}

const ForwardedLaTeXEditor = forwardRef(LaTeXEditorImpl) as React.ForwardRefExoticComponent<LaTeXEditorProps & React.RefAttributes<LaTeXEditorHandle>>
const LaTeXEditor = React.memo(ForwardedLaTeXEditor)

export default LaTeXEditor
