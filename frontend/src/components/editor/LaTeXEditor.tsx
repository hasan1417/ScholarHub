import React, { useEffect, useState, useRef, forwardRef, useImperativeHandle, useCallback, useMemo } from 'react'
import 'katex/dist/katex.min.css'
import pdfViewerHtml from '../../assets/pdf-viewer.html?raw'
import FigureUploadDialog from './FigureUploadDialog'
import CitationDialog from './CitationDialog'
import HistoryPanel from './HistoryPanel'
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
import { EditorToolbar } from './components/EditorToolbar'
import { PdfPreviewPane } from './components/PdfPreviewPane'
import { OutlinePanel } from './components/OutlinePanel'
import { FileSelector } from './components/FileSelector'
import { SymbolPalette } from './components/SymbolPalette'
import { TrackChangesPanel } from './components/TrackChangesPanel'
import { useDocumentOutline } from './hooks/useDocumentOutline'
import { useSyncTeX } from './hooks/useSyncTeX'
import { useTrackChanges } from './hooks/useTrackChanges'
import { countLatexWords } from './utils/latexWordCount'
import { dispatchTrackedChanges, type TrackedChangeDecoration } from './extensions/trackChangesDecoration'
import { setDiagnostics } from '@codemirror/lint'
import { latexErrorsToDiagnostics } from './extensions/latexErrorMarkers'

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
    paperRole?: 'admin' | 'editor' | 'viewer'
  }
  collaborationStatus?: string | null
}

export interface LaTeXEditorHandle {
  getSelection: () => string
  replaceSelection: (text: string) => void
  setValue: (text: string) => void
  focus: () => void
}

// LaTeX editor with CodeMirror and live PDF preview
function LaTeXEditorImpl(
  { value, onChange, onSave, templateTitle, paperId, projectId, readOnly = false, disableSave = false, onNavigateBack, onOpenAiChatWithMessage, realtime, collaborationStatus }: LaTeXEditorProps,
  ref: React.Ref<LaTeXEditorHandle>
) {
  const [viewMode, setViewMode] = useState<'code' | 'split' | 'pdf'>('split')
  const [figureDialogOpen, setFigureDialogOpen] = useState(false)
  const [outlinePanelOpen, setOutlinePanelOpen] = useState(false)
  const [exportDocxLoading, setExportDocxLoading] = useState(false)
  const [exportSourceZipLoading, setExportSourceZipLoading] = useState(false)
  const [symbolPaletteOpen, setSymbolPaletteOpen] = useState(false)
  const tcKey = paperId ? `tc-enabled-${paperId}` : null
  const [trackChangesEnabled, setTrackChangesEnabled] = useState(() => {
    if (!tcKey) return false
    try { return localStorage.getItem(tcKey) === '1' } catch { return false }
  })
  const [trackChangesPanelOpen, setTrackChangesPanelOpen] = useState(false)
  const [wordCount, setWordCount] = useState<number | null>(null)

  // Current user identity (for track changes attribution)
  const { user: authUser } = useAuth()

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
    activeFile: 'main.tex', // updated below via multi-file hook
  })

  // Multi-file management
  const { activeFile, fileList, handleCreateFile, handleDeleteFile, handleSelectFile } = useMultiFileManagement({
    realtimeDoc: realtime?.doc || null,
    getYText,
    getFileList,
    yTextReady,
  })

  // Track changes hook (must come before useCodeMirrorEditor to provide the transaction filter)
  const trackChanges = useTrackChanges({
    yText: ySharedText,
    enabled: trackChangesEnabled,
    userId: authUser?.id || 'local',
    userName: [authUser?.first_name, authUser?.last_name].filter(Boolean).join(' ') || 'You',
    userColor: '#3B82F6',
  })
  // getTransactionFilter has [] deps (uses refs internally), so this is created once
  const trackFilterExt = useMemo(() => trackChanges.getTransactionFilter(), [trackChanges.getTransactionFilter])

  // CodeMirror editor lifecycle
  const {
    viewRef, editorReady, undoEnabled, redoEnabled, hasTextSelected,
    handleContainerRef, flushBufferedChange, latestDocRef, handleUndo, handleRedo,
  } = useCodeMirrorEditor({
    value, onChange, readOnly,
    realtimeDoc: realtime?.doc || null,
    realtimeAwareness: realtime?.awareness || null,
    realtimeExtensions, ySharedText, yUndoManager, yTextReady, remoteSelections,
    synced: realtime?.synced, paperId,
    trackChangesFilter: trackFilterExt,
  })

  // Stable accessor for latest document source
  const getLatestSource = useCallback(() => {
    try { const v = viewRef.current; if (v) return v.state.doc.toString() } catch {}
    return latestDocRef.current || ''
  }, [viewRef, latestDocRef])

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

  // Word count: debounced update from latest source
  const wordCountTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const updateWordCount = useCallback(() => {
    if (wordCountTimerRef.current) clearTimeout(wordCountTimerRef.current)
    wordCountTimerRef.current = setTimeout(() => {
      const source = getLatestSource()
      if (source.length > 10) {
        setWordCount(countLatexWords(source).words)
      }
    }, 1000)
  }, [getLatestSource])

  // Update word count after compile and on initial load
  useEffect(() => {
    updateWordCount()
  }, [compileStatus]) // eslint-disable-line react-hooks/exhaustive-deps

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

  // Wire document changes to trigger auto-compile and word count
  const triggerAutoCompileRef = useRef(triggerAutoCompile)
  triggerAutoCompileRef.current = triggerAutoCompile
  const updateWordCountRef = useRef(updateWordCount)
  updateWordCountRef.current = updateWordCount

  // Listen for doc changes via the value prop (which onChange passes up)
  const prevValueLenRef = useRef(value.length)
  useEffect(() => {
    if (value.length !== prevValueLenRef.current) {
      prevValueLenRef.current = value.length
      triggerAutoCompileRef.current()
      updateWordCountRef.current()
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

  // Document outline
  const { outline } = useDocumentOutline({ viewRef, enabled: outlinePanelOpen })

  // History restore + save
  const { historyPanelOpen, setHistoryPanelOpen, saveState, saveError, handleRestoreFromHistory, handleSave } = useHistoryRestore({
    viewRef, realtimeDoc: realtime?.doc || null, paperId, readOnly, disableSave: disableSave ?? false, flushBufferedChange, onSave,
  })

  // Snippet / formatting insertion
  const {
    formattingGroups, insertAtDocumentEnd, insertSnippet,
    insertBold, insertItalics, insertInlineMath, insertCite, insertFigure, insertTable, insertItemize, insertEnumerate,
    handleFigureInsert,
  } = useLatexSnippets({ viewRef, readOnly, setFigureDialogOpen })

  // Citation dialog
  const {
    citationDialogOpen, citationAnchor,
    handleOpenReferencesToolbar, handleCloseCitationDialog, handleInsertCitation, handleInsertBibliography,
  } = useCitationHandlers({ paperId, readOnly, insertSnippet, insertAtDocumentEnd })

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
    ? 'mt-2 flex-1 min-h-0 flex overflow-hidden'
    : 'mt-2 flex-1 min-h-0 flex flex-col'
  const editorPaneCls = splitLayout
    ? 'relative min-w-0 overflow-hidden rounded-l-md border border-slate-200 bg-white shadow-sm transition-colors dark:border-slate-800 dark:bg-slate-950/40 dark:shadow-slate-950/30'
    : 'relative flex-1 min-h-0 overflow-auto rounded-md border border-slate-200 bg-white shadow-sm transition-colors dark:border-slate-800 dark:bg-slate-950/40 dark:shadow-slate-950/30'
  const previewPaneCls = splitLayout
    ? 'min-w-0 flex flex-col overflow-hidden rounded-r-md border border-l-0 border-slate-200 bg-white shadow-sm transition-colors dark:border-slate-800 dark:bg-slate-950/40 dark:shadow-slate-950/30'
    : 'flex-1 min-h-0 flex flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm transition-colors dark:border-slate-800 dark:bg-slate-950/40 dark:shadow-slate-950/30'

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
        outlinePanelOpen={outlinePanelOpen}
        onToggleOutline={() => setOutlinePanelOpen(prev => !prev)}
        onOpenHistory={() => setHistoryPanelOpen(true)}
        aiActionLoading={aiActionLoading}
        onAiAction={handleAiAction}
        onForwardSync={handleForwardSync}
        onExportPdf={handleExportPdf}
        onExportDocx={handleExportDocx}
        onExportSourceZip={handleExportSourceZip}
        exportDocxLoading={exportDocxLoading}
        exportSourceZipLoading={exportSourceZipLoading}
        wordCount={wordCount}
        symbolPaletteOpen={symbolPaletteOpen}
        onToggleSymbolPalette={() => setSymbolPaletteOpen(prev => !prev)}
        autoCompileEnabled={autoCompileEnabled}
        onToggleAutoCompile={toggleAutoCompile}
        trackChangesEnabled={trackChangesEnabled}
        onToggleTrackChanges={ySharedText ? () => setTrackChangesEnabled(prev => {
          const next = !prev
          if (tcKey) try { localStorage.setItem(tcKey, next ? '1' : '0') } catch {}
          return next
        }) : undefined}
        trackChangesPanelOpen={trackChangesPanelOpen}
        onToggleTrackChangesPanel={realtime?.paperRole === 'admin' ? () => setTrackChangesPanelOpen(prev => !prev) : undefined}
        hasTrackedChanges={trackChanges.trackedChanges.length > 0}
      />
      <div ref={splitContainerRef} className={contentLayoutCls}>
        {showEditor && (
          <div className={editorPaneCls} style={splitLayout ? { width: `${splitPosition}%` } : undefined}>
            {realtime?.doc && (
              <FileSelector
                files={fileList}
                activeFile={activeFile}
                onSelectFile={handleSelectFile}
                onCreateFile={handleCreateFile}
                onDeleteFile={handleDeleteFile}
                readOnly={readOnly}
              />
            )}
            <div ref={handleContainerRef} className={realtime?.doc ? 'absolute inset-0 top-auto bottom-0' : 'absolute inset-0'} style={realtime?.doc && fileList.length > 0 ? { top: fileList.length > 1 ? '33px' : '29px' } : undefined} />
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
          <div className={previewPaneCls} style={splitLayout ? { width: `${100 - splitPosition}%` } : undefined}>
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
          onClose={handleCloseCitationDialog}
          paperId={paperId}
          projectId={projectId}
          onInsertCitation={handleInsertCitation}
          onInsertBibliography={handleInsertBibliography}
          anchorElement={citationAnchor}
        />
      )}

      {outlinePanelOpen && (
        <OutlinePanel
          outline={outline}
          viewRef={viewRef}
          onClose={() => setOutlinePanelOpen(false)}
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
    </div>
  )
}

const ForwardedLaTeXEditor = forwardRef(LaTeXEditorImpl) as React.ForwardRefExoticComponent<LaTeXEditorProps & React.RefAttributes<LaTeXEditorHandle>>
const LaTeXEditor = React.memo(ForwardedLaTeXEditor)

export default LaTeXEditor
