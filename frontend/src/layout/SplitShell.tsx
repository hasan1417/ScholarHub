import React, { useEffect, useState } from 'react'
import { Play, FileCode2, Columns, FileText, ArrowLeft } from 'lucide-react'
import { uiStore, ViewMode } from '../state/uiStore'
import { logEvent } from '../utils/metrics'

const SPLIT_RATIO = 0.5

interface SplitShellProps {
  left: React.ReactNode
  right: React.ReactNode
  logPane?: React.ReactNode
  onCompile: () => void
  saveControl?: React.ReactNode
  interactControl?: React.ReactNode
  statusControl?: React.ReactNode
  onNavigateBack?: () => void
}

const SplitShell: React.FC<SplitShellProps> = ({ left, right, logPane, onCompile, saveControl, interactControl, statusControl, onNavigateBack }) => {
  const [mode, setMode] = useState<ViewMode>(uiStore.getViewMode())
  const [w, setW] = useState<number>(typeof window !== 'undefined' ? window.innerWidth : 1200)
  const isNarrow = w < 900

  useEffect(() => {
    const unsubscribe = uiStore.subscribe(() => {
      setMode(uiStore.getViewMode())
    })
    return () => { unsubscribe() }
  }, [])

  useEffect(() => {
    const onResize = () => setW(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const changeMode = (next: ViewMode) => {
    if (mode === next) return
    try { logEvent('ViewModeChanged', { from: mode, to: next }) } catch {}
    uiStore.setViewMode(next)
  }

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey
      if (!mod) return
      if (e.key === 'Enter') { e.preventDefault(); onCompile(); return }
      if (e.key === '1') { e.preventDefault(); changeMode('editor'); return }
      if (e.key === '2') { e.preventDefault(); changeMode('split'); return }
      if (e.key === '3') { e.preventDefault(); changeMode('preview'); return }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCompile, mode])

  // Compute pane styles so both panes can stay mounted without layout jumps
  const leftStyle: React.CSSProperties = (() => {
    if (isNarrow) return { width: '100%' }
    if (mode === 'editor') return { width: '100%' }
    if (mode === 'preview') return { width: 0, display: 'none' }
    return { width: `${SPLIT_RATIO * 100}%` }
  })()
  const rightStyle: React.CSSProperties = (() => {
    if (isNarrow) return { width: '100%' }
    if (mode === 'preview') return { width: '100%' }
    if (mode === 'editor') return { width: 0, display: 'none' }
    return { width: `${(1 - SPLIT_RATIO) * 100}%` }
  })()

  const renderViewModeButton = (target: ViewMode, label: string, Icon: React.ComponentType<{ className?: string }>) => (
    <button
      key={target}
      aria-selected={mode === target}
      role="tab"
      onClick={() => changeMode(target)}
      className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
        mode === target
          ? 'bg-slate-100 text-slate-900 shadow-sm'
          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/80'
      }`}
      aria-label={label}
    >
      <Icon className="h-3.5 w-3.5" />
      <span className="hidden sm:inline">{label}</span>
    </button>
  )

  return (
    <div className="h-full flex flex-col">
      {/* Sticky toolbar */}
      <div className="sticky top-0 z-20 bg-slate-900 text-slate-100 border-b border-slate-800 shadow">
        <div className="flex items-center justify-between px-3 sm:px-4 py-2" role="toolbar" aria-label="Document controls">
          <div className="flex items-center gap-3">
            {onNavigateBack && (
              <button
                aria-label="Back to paper details"
                onMouseDown={(e) => {
                  if (e.button === 0) e.preventDefault()
                }}
                onClick={onNavigateBack}
                className="inline-flex items-center justify-center rounded-md border border-slate-700/50 bg-slate-800/70 p-2 text-slate-300 hover:text-white hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-300"
              >
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              </button>
            )}
            <button
              aria-label="Compile (Ctrl/Cmd+Enter)"
              onMouseDown={(e) => {
                if (e.button === 0) e.preventDefault()
              }}
              onClick={onCompile}
              className="inline-flex items-center gap-2 rounded-md bg-indigo-500 px-3 py-1.5 text-sm font-semibold text-white shadow hover:bg-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-300"
            >
              <Play className="h-4 w-4" />
              Compile
            </button>
            {statusControl ? (
              <div className="hidden sm:flex items-center gap-2 text-xs text-slate-300">
                {statusControl}
              </div>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            {interactControl}
            {saveControl}
            <div className="flex items-center gap-1 rounded-md bg-slate-800/80 px-1.5 py-1" role="tablist" aria-label="View modes">
              {renderViewModeButton('editor', 'Code', FileCode2)}
              {renderViewModeButton('split', 'Split', Columns)}
              {renderViewModeButton('preview', 'PDF', FileText)}
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      {!isNarrow ? (
        <div id="split-shell-container" className="flex-1 min-h-0 h-full flex items-stretch">
          <div className="flex h-full min-h-0" style={leftStyle}>
            <div className="flex-1 min-h-0 overflow-auto">{left}</div>
          </div>
          <div id="pdf-preview-pane" className="flex h-full min-h-0" style={{ ...rightStyle, position: 'relative', zIndex: 0 }}>
            <div className="flex-1 min-h-0 overflow-auto">{right}</div>
          </div>
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col">
          <div className="flex items-center gap-2 px-3 py-2 border-b">
            <button className={`px-2 py-1.5 rounded ${mode==='editor'?'bg-gray-200':'hover:bg-gray-100'}`} onClick={()=>changeMode('editor')}>Editor</button>
            <button className={`px-2 py-1.5 rounded ${mode==='preview'?'bg-gray-200':'hover:bg-gray-100'}`} onClick={()=>changeMode('preview')}>Preview</button>
            {logPane && (
              <button className={`px-2 py-1.5 rounded ${mode==='split'?'bg-gray-200':'hover:bg-gray-100'}`} onClick={()=>changeMode('split')}>Log</button>
            )}
          </div>
          <div className="flex-1 min-h-0 overflow-auto">
            {mode==='editor' && left}
            {mode==='preview' && right}
            {mode==='split' && logPane}
          </div>
        </div>
      )}
    </div>
  )
}

export default React.memo(SplitShell)

// Observe right pane width to auto-fit pdf scale; keeps scale consistent when resizing
const initPreviewAutoFit = () => {
  const container = document.querySelector('#pdf-preview-pane') as HTMLElement | null
  if (!container) return
  let debounce: number | null = null
  const ro = new ResizeObserver((entries) => {
    for (const entry of entries) {
      const w = entry.contentRect.width
      if (debounce) cancelAnimationFrame(debounce)
      debounce = requestAnimationFrame(() => {
        const scale = 'page-width'
        try { const app: any = (window as any).PDFViewerApplication; if (app && app.pdfViewer) app.pdfViewer.currentScaleValue = scale } catch {}
        // If using a custom PDF viewer, send a message to adjust scale here.
        try { logEvent('PreviewAutoFit', { width: Math.round(w), scale }) } catch {}
      })
    }
  })
  try { ro.observe(container) } catch {}
}

if (typeof window !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initPreviewAutoFit)
  else initPreviewAutoFit()
}
