import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { Check, Loader2, Sparkles, X } from 'lucide-react'
import type { EditProposal } from '../utils/editProposals'

/* ─── Log entry types ───────────────────────────────────────────── */

interface ParsedLogEntry {
  type: 'error' | 'warning' | 'info'
  message: string
  file?: string
  line?: number
  fullContext: string
}

type LogFilter = 'all' | 'error' | 'warning' | 'info'

/* ─── Log parser ────────────────────────────────────────────────── */

function parseCompileLogs(rawLines: string[]): ParsedLogEntry[] {
  const entries: ParsedLogEntry[] = []
  const contextRadius = 2 // lines before/after to include as context

  for (let i = 0; i < rawLines.length; i++) {
    const line = rawLines[i]

    let type: 'error' | 'warning' | 'info' | null = null

    if (/^!\s/.test(line) || /Error:/i.test(line) || /Fatal error/i.test(line)) {
      type = 'error'
    } else if (/Warning:/i.test(line) || /LaTeX Warning/i.test(line) || /Package\s+\S+\s+Warning/i.test(line)) {
      type = 'warning'
    } else if (/Overfull/i.test(line) || /Underfull/i.test(line)) {
      type = 'info'
    }

    if (!type) continue

    // Extract file:line from patterns like "./main.tex:42:" or "l.42"
    let file: string | undefined
    let lineNum: number | undefined

    const fileLineMatch = line.match(/\.\/([^:]+):(\d+):/)
    if (fileLineMatch) {
      file = fileLineMatch[1]
      lineNum = parseInt(fileLineMatch[2], 10)
    } else {
      const lMatch = line.match(/\bl\.(\d+)\b/)
      if (lMatch) lineNum = parseInt(lMatch[1], 10)
    }

    // Build context from surrounding lines
    const start = Math.max(0, i - contextRadius)
    const end = Math.min(rawLines.length - 1, i + contextRadius)
    const fullContext = rawLines.slice(start, end + 1).join('\n')

    // Clean up message: trim "! " prefix, collapse whitespace
    let message = line.replace(/^!\s*/, '').trim()
    if (message.length > 200) message = message.slice(0, 200) + '...'

    entries.push({ type, message, file, line: lineNum, fullContext })
  }

  return entries
}

/* ─── Zoom presets ──────────────────────────────────────────────── */

const ZOOM_PRESETS = [50, 75, 100, 125, 150] as const
const ZOOM_MIN = 25
const ZOOM_MAX = 300
const ZOOM_STEP = 25

/* ─── Props ─────────────────────────────────────────────────────── */

interface PdfPreviewPaneProps {
  iframeRef: React.Ref<HTMLIFrameElement>
  pdfViewerHtml: string
  compileStatus: 'idle' | 'compiling' | 'success' | 'error'
  compileError: string | null
  compileLogs: string[]
  lastCompileAt: number | null
  // Optional compile controls (for compile dropdown)
  onCompile?: () => void
  autoCompileEnabled?: boolean
  onToggleAutoCompile?: () => void
  // Export controls
  onExportPdf?: () => void
  onExportDocx?: () => void
  onExportSourceZip?: () => void
  exportDocxLoading?: boolean
  exportSourceZipLoading?: boolean
  // Fix errors with AI
  onFixErrors?: () => void
  fixLoading?: boolean
  fixProposals?: EditProposal[]
  onApplyFix?: (id: string) => void
  onRejectFix?: (id: string) => void
  onApplyAllFixes?: () => void
}

/* ─── Component ─────────────────────────────────────────────────── */

export const PdfPreviewPane: React.FC<PdfPreviewPaneProps> = ({
  iframeRef,
  pdfViewerHtml,
  compileStatus,
  compileError,
  compileLogs,
  lastCompileAt,
  onCompile,
  autoCompileEnabled,
  onToggleAutoCompile,
  onExportPdf,
  onExportDocx,
  onExportSourceZip,
  exportDocxLoading,
  exportSourceZipLoading,
  onFixErrors,
  fixLoading,
  fixProposals,
  onApplyFix,
  onRejectFix,
  onApplyAllFixes,
}) => {
  // --- State ---
  const [logFilter, setLogFilter] = useState<LogFilter>('all')
  const [expandedEntries, setExpandedEntries] = useState<Set<number>>(new Set())
  const [rawLogsExpanded, setRawLogsExpanded] = useState(false)
  const [logsVisible, setLogsVisible] = useState(false)
  const [invertColors, setInvertColors] = useState(false)
  const [compileDropdownOpen, setCompileDropdownOpen] = useState(false)
  const [exportDropdownOpen, setExportDropdownOpen] = useState(false)
  const [zoomLevel, setZoomLevel] = useState(100)
  const [zoomDropdownOpen, setZoomDropdownOpen] = useState(false)

  // --- Responsive toolbar width tracking ---
  const toolbarRef = useRef<HTMLDivElement>(null)
  const [toolbarWidth, setToolbarWidth] = useState(999)
  useEffect(() => {
    const el = toolbarRef.current
    if (!el) return
    const ro = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect.width ?? 999
      setToolbarWidth(w)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const compact = toolbarWidth < 380

  // --- Parsed logs ---
  const parsedLogs = useMemo(() => parseCompileLogs(compileLogs), [compileLogs])

  const errorCount = useMemo(() => parsedLogs.filter(e => e.type === 'error').length, [parsedLogs])
  const warningCount = useMemo(() => parsedLogs.filter(e => e.type === 'warning').length, [parsedLogs])
  const infoCount = useMemo(() => parsedLogs.filter(e => e.type === 'info').length, [parsedLogs])

  const filteredLogs = useMemo(() => {
    if (logFilter === 'all') return parsedLogs
    return parsedLogs.filter(e => e.type === logFilter)
  }, [parsedLogs, logFilter])

  // --- Handlers ---
  const toggleEntry = useCallback((index: number) => {
    setExpandedEntries(prev => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }, [])

  const handleZoomIn = useCallback(() => setZoomLevel(z => Math.min(ZOOM_MAX, z + ZOOM_STEP)), [])
  const handleZoomOut = useCallback(() => setZoomLevel(z => Math.max(ZOOM_MIN, z - ZOOM_STEP)), [])
  const handleZoomPreset = useCallback((preset: number) => {
    setZoomLevel(preset)
    setZoomDropdownOpen(false)
  }, [])

  // Send zoom level to PDF viewer iframe via postMessage
  useEffect(() => {
    const iframe = typeof iframeRef === 'object' && iframeRef ? (iframeRef as React.RefObject<HTMLIFrameElement>).current : null
    if (!iframe?.contentWindow) return
    iframe.contentWindow.postMessage({ type: 'setZoom', zoom: zoomLevel / 100 }, window.location.origin)
  }, [zoomLevel, iframeRef])

  // --- Page navigation ---
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(0)
  const [pageInputValue, setPageInputValue] = useState('')

  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.data?.type === 'pageInfo') {
        setCurrentPage(e.data.currentPage ?? 1)
        setTotalPages(e.data.totalPages ?? 0)
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [])

  const goToPage = useCallback((page: number) => {
    const iframe = typeof iframeRef === 'object' && iframeRef ? (iframeRef as React.RefObject<HTMLIFrameElement>).current : null
    if (!iframe?.contentWindow) return
    iframe.contentWindow.postMessage({ type: 'goToPage', page }, window.location.origin)
  }, [iframeRef])

  // Re-render every 5s to keep "Updated Xs ago" fresh
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!lastCompileAt || compileStatus !== 'success') return
    const timer = setInterval(() => setTick(t => t + 1), 5000)
    return () => clearInterval(timer)
  }, [lastCompileAt, compileStatus])

  const isMac = typeof navigator !== 'undefined' && /Mac/i.test(navigator.userAgent)
  const compileShortcut = isMac ? '\u2318\u21A9' : 'Ctrl+Enter'

  const totalLogCount = parsedLogs.length

  return (
    <>
      {/* ─── PDF Toolbar (Overleaf-style) ────────────────── */}
      {/* Left: [Recompile v] [⬇]  ···spacer···  Right: [timestamp] [◐] [≡] | [−] [+] [100%▼] */}
      <div
        ref={toolbarRef}
        className="flex items-center gap-1 border-b border-slate-200 bg-slate-50 px-1.5 py-1 text-xs dark:border-slate-800 dark:bg-slate-900/60"
      >
        {/* ── Left group ── */}

        {/* Recompile split-button */}
        {onCompile && (
          <div className="relative flex items-center shrink-0">
            <button
              onClick={onCompile}
              disabled={compileStatus === 'compiling'}
              className="flex items-center gap-1 rounded-l px-1.5 py-0.5 text-[11px] font-medium bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title={`Recompile (${compileShortcut})`}
            >
              {compileStatus === 'compiling' ? (
                <svg className="h-2.5 w-2.5 animate-spin shrink-0" viewBox="0 0 16 16" fill="none">
                  <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" opacity="0.3" />
                  <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              ) : (
                <svg className="h-2.5 w-2.5 shrink-0" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M4 2l10 6-10 6V2z" />
                </svg>
              )}
              {!compact && 'Recompile'}
            </button>
            <button
              onClick={() => setCompileDropdownOpen(o => !o)}
              className="flex items-center self-stretch rounded-r border-l border-emerald-700 bg-emerald-600 px-0.5 text-white hover:bg-emerald-700 transition-colors"
            >
              <svg className="h-2.5 w-2.5" viewBox="0 0 16 16" fill="currentColor">
                <path d="M4 6l4 4 4-4H4z" />
              </svg>
            </button>
            {compileDropdownOpen && (
              <>
                <div className="fixed inset-0 z-30" onClick={() => setCompileDropdownOpen(false)} />
                <div className="absolute left-0 top-full z-40 mt-1 w-48 rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800">
                  <button
                    onClick={() => { onToggleAutoCompile?.(); setCompileDropdownOpen(false) }}
                    className="flex w-full items-center justify-between px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                  >
                    Auto Compile
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${autoCompileEnabled ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' : 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400'}`}>
                      {autoCompileEnabled ? 'ON' : 'OFF'}
                    </span>
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {/* Download */}
        {(onExportPdf || onExportDocx || onExportSourceZip) && (
          <div className="relative shrink-0">
            <button
              onClick={() => setExportDropdownOpen(o => !o)}
              className={`rounded p-1 transition-colors ${exportDropdownOpen ? 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200' : 'text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300'}`}
              title="Download"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
            </button>
            {exportDropdownOpen && (
              <>
                <div className="fixed inset-0 z-30" onClick={() => setExportDropdownOpen(false)} />
                <div className="absolute left-0 top-full z-40 mt-1 w-48 rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800">
                  {onExportPdf && (
                    <button
                      onClick={() => { onExportPdf(); setExportDropdownOpen(false) }}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                    >
                      Download PDF
                    </button>
                  )}
                  {onExportDocx && (
                    <button
                      onClick={() => { onExportDocx(); setExportDropdownOpen(false) }}
                      disabled={exportDocxLoading}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-700"
                    >
                      {exportDocxLoading && (
                        <svg className="h-3 w-3 animate-spin shrink-0" viewBox="0 0 16 16" fill="none">
                          <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" opacity="0.3" />
                          <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                        </svg>
                      )}
                      Download Word
                    </button>
                  )}
                  {onExportSourceZip && (
                    <>
                      <div className="my-1 border-t border-slate-200 dark:border-slate-700" />
                      <button
                        onClick={() => { onExportSourceZip(); setExportDropdownOpen(false) }}
                        disabled={exportSourceZipLoading}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        {exportSourceZipLoading && (
                          <svg className="h-3 w-3 animate-spin shrink-0" viewBox="0 0 16 16" fill="none">
                            <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" opacity="0.3" />
                            <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                          </svg>
                        )}
                        Download Source (.zip)
                      </button>
                    </>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {/* ── Spacer ── */}
        <div className="flex-1" />

        {/* ── Right group ── */}

        {/* Status text */}
        {compileStatus === 'compiling' && (
          <svg className="h-3 w-3 animate-spin text-indigo-400 shrink-0" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" opacity="0.3" />
            <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        )}
        {compileStatus === 'success' && lastCompileAt && !compact && (
          <span className="text-[10px] text-slate-400 dark:text-slate-500 whitespace-nowrap tabular-nums shrink-0">
            {(() => {
              const secs = Math.max(1, Math.round((Date.now() - lastCompileAt) / 1000))
              if (secs < 60) return `${secs}s ago`
              const mins = Math.floor(secs / 60)
              if (mins < 60) return `${mins}m ago`
              return `${Math.floor(mins / 60)}h ago`
            })()}
          </span>
        )}
        {compileStatus === 'error' && compileError && (
          <span className="text-[10px] text-rose-500 dark:text-rose-400 shrink-0" title={compileError}>
            Failed
          </span>
        )}

        {/* Invert colors */}
        <button
          onClick={() => setInvertColors(i => !i)}
          className={`rounded p-1 transition-colors shrink-0 ${invertColors ? 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-400' : 'text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300'}`}
          title="Invert colors (dark reading mode)"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zM2 8a6 6 0 0 1 6-6v12a6 6 0 0 1-6-6z" />
          </svg>
        </button>

        {/* Logs toggle */}
        <button
          onClick={() => setLogsVisible(v => !v)}
          className={`relative rounded p-1 transition-colors shrink-0 ${logsVisible ? 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200' : 'text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300'}`}
          title="Toggle compile logs"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
            <path d="M2 3h12v1H2V3zm0 3h12v1H2V6zm0 3h10v1H2V9zm0 3h8v1H2v-1z" />
          </svg>
          {errorCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex h-3 w-3 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white">
              {errorCount > 9 ? '9+' : errorCount}
            </span>
          )}
        </button>

        {/* Page navigation */}
        {totalPages > 0 && !compact && (
          <div className="flex items-center gap-0.5 shrink-0">
            {/* Page up */}
            <button
              onClick={() => goToPage(currentPage - 1)}
              disabled={currentPage <= 1}
              className="rounded p-0.5 text-slate-400 hover:text-slate-600 disabled:opacity-30 dark:text-slate-500 dark:hover:text-slate-300"
              title="Previous page"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
                <path d="M4 10l4-4 4 4H4z" />
              </svg>
            </button>
            {/* Page down */}
            <button
              onClick={() => goToPage(currentPage + 1)}
              disabled={currentPage >= totalPages}
              className="rounded p-0.5 text-slate-400 hover:text-slate-600 disabled:opacity-30 dark:text-slate-500 dark:hover:text-slate-300"
              title="Next page"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
                <path d="M4 6l4 4 4-4H4z" />
              </svg>
            </button>
            {/* Page input */}
            <input
              type="text"
              inputMode="numeric"
              className="w-7 rounded border border-slate-300 bg-white px-1 py-0.5 text-center text-[11px] tabular-nums text-slate-700 outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/30 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              value={pageInputValue || String(currentPage)}
              onFocus={() => setPageInputValue(String(currentPage))}
              onChange={(e) => setPageInputValue(e.target.value.replace(/\D/g, ''))}
              onBlur={() => {
                const p = parseInt(pageInputValue, 10)
                if (p >= 1 && p <= totalPages) goToPage(p)
                setPageInputValue('')
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  const p = parseInt(pageInputValue, 10)
                  if (p >= 1 && p <= totalPages) goToPage(p)
                  setPageInputValue('')
                  ;(e.target as HTMLInputElement).blur()
                }
              }}
            />
            <span className="text-[11px] text-slate-400 dark:text-slate-500 tabular-nums">/ {totalPages}</span>
          </div>
        )}

        {/* Divider */}
        <div className="mx-0.5 h-4 w-px bg-slate-300 dark:bg-slate-700 shrink-0" />

        {/* Zoom out */}
        <button
          onClick={handleZoomOut}
          disabled={zoomLevel <= ZOOM_MIN}
          className="rounded p-0.5 text-slate-400 hover:text-slate-600 disabled:opacity-30 dark:text-slate-500 dark:hover:text-slate-300 shrink-0"
          title="Zoom out"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="8" x2="13" y2="8" />
          </svg>
        </button>

        {/* Zoom in */}
        <button
          onClick={handleZoomIn}
          disabled={zoomLevel >= ZOOM_MAX}
          className="rounded p-0.5 text-slate-400 hover:text-slate-600 disabled:opacity-30 dark:text-slate-500 dark:hover:text-slate-300 shrink-0"
          title="Zoom in"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="8" x2="13" y2="8" />
            <line x1="8" y1="3" x2="8" y2="13" />
          </svg>
        </button>

        {/* Zoom percentage dropdown */}
        <div className="relative shrink-0">
          <button
            onClick={() => setZoomDropdownOpen(z => !z)}
            className="flex items-center gap-0.5 rounded px-1 py-0.5 text-[11px] font-medium text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 tabular-nums"
          >
            {zoomLevel}%
            <svg className="h-2.5 w-2.5" viewBox="0 0 16 16" fill="currentColor">
              <path d="M4 6l4 4 4-4H4z" />
            </svg>
          </button>
          {zoomDropdownOpen && (
            <>
              <div className="fixed inset-0 z-30" onClick={() => setZoomDropdownOpen(false)} />
              <div className="absolute right-0 top-full z-40 mt-1 w-28 rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800">
                {ZOOM_PRESETS.map(p => (
                  <button
                    key={p}
                    onClick={() => handleZoomPreset(p)}
                    className={`block w-full px-3 py-1 text-left text-xs hover:bg-slate-100 dark:hover:bg-slate-700 ${zoomLevel === p ? 'font-medium text-indigo-600 dark:text-indigo-400' : 'text-slate-700 dark:text-slate-200'}`}
                  >
                    {p}%
                  </button>
                ))}
                <div className="my-1 border-t border-slate-200 dark:border-slate-700" />
                <button
                  onClick={() => handleZoomPreset(100)}
                  className="block w-full px-3 py-1 text-left text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                >
                  Fit width
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* ─── PDF Viewer ───────────────────────────────────── */}
      <div className="overflow-hidden flex-1 relative">
        <iframe
          ref={iframeRef}
          id="latex-preview-frame"
          title="Compiled PDF"
          srcDoc={pdfViewerHtml}
          data-loaded="false"
          className="h-full w-full"
          style={invertColors ? { filter: 'invert(1) hue-rotate(180deg)' } : undefined}
        />
      </div>

      {/* ─── Compile Logs Panel ───────────────────────────── */}
      {logsVisible && (
        <div className="flex flex-col border-t border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900/80" style={{ maxHeight: '40%', minHeight: '120px' }}>
          {/* Status + summary bar */}
          <div className="flex items-center gap-2 border-b border-slate-200 px-3 py-1.5 dark:border-slate-800">
            {/* Compilation status indicator */}
            {compileStatus === 'success' || (compileStatus !== 'error' && compileStatus !== 'compiling' && errorCount === 0) ? (
              <span className="flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M8 1a7 7 0 1 1 0 14A7 7 0 0 1 8 1zm3.3 4.3L7 9.6 4.7 7.3l-.7.7L7 11l5-5-.7-.7z" />
                </svg>
                {compileStatus === 'idle' ? 'Ready' : 'Compilation successful'}
              </span>
            ) : compileStatus === 'error' || errorCount > 0 ? (
              <span className="flex items-center gap-1 text-xs font-medium text-red-500 dark:text-red-400">
                <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M8 1a7 7 0 1 1 0 14A7 7 0 0 1 8 1zM5.3 5.3l-.7.7L7.3 8l-2.7 2L5.3 10.7 8 8.7l2 2.6.7-.7L8.7 8l2.6-2-.7-.7L8 7.3 5.3 5.3z" />
                </svg>
                Compilation failed
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 16 16" fill="none">
                  <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" opacity="0.3" />
                  <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
                Compiling...
              </span>
            )}

            <div className="mx-2 h-4 w-px bg-slate-300 dark:bg-slate-700" />

            {/* Filter tabs */}
            <div className="flex items-center gap-0.5 text-[11px]">
              <FilterTab
                label="All logs"
                count={totalLogCount}
                active={logFilter === 'all'}
                onClick={() => setLogFilter('all')}
                color="text-slate-600 dark:text-slate-300"
              />
              <FilterTab
                label="Errors"
                count={errorCount}
                active={logFilter === 'error'}
                onClick={() => setLogFilter('error')}
                color="text-red-400"
              />
              <FilterTab
                label="Warnings"
                count={warningCount}
                active={logFilter === 'warning'}
                onClick={() => setLogFilter('warning')}
                color="text-amber-400"
              />
              <FilterTab
                label="Info"
                count={infoCount}
                active={logFilter === 'info'}
                onClick={() => setLogFilter('info')}
                color="text-blue-400"
              />
            </div>

            {/* Fix with AI button */}
            {onFixErrors && errorCount > 0 && (
              <>
                <div className="mx-1 h-4 w-px bg-slate-300 dark:bg-slate-700" />
                <button
                  onClick={onFixErrors}
                  disabled={fixLoading}
                  className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
                  title="Ask AI to fix compilation errors"
                >
                  {fixLoading ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Sparkles className="h-3 w-3" />
                  )}
                  {fixLoading ? 'Fixing...' : 'Fix with AI'}
                </button>
              </>
            )}
          </div>

          {/* AI Fix proposals — hide when compiling or after successful recompile */}
          {fixProposals && fixProposals.length > 0 && compileStatus !== 'compiling' && errorCount > 0 && (
            <FixProposalsPanel
              proposals={fixProposals}
              onApply={onApplyFix}
              onReject={onRejectFix}
              onApplyAll={onApplyAllFixes}
            />
          )}

          {/* Log entries */}
          <div className="flex-1 overflow-auto px-2 py-1.5 text-xs">
            {filteredLogs.length === 0 && (
              <div className="py-4 text-center text-xs text-slate-400 dark:text-slate-500">
                {compileLogs.length === 0 ? 'No compile output yet' : 'No entries matching this filter'}
              </div>
            )}

            {filteredLogs.map((entry, i) => {
              const isExpanded = expandedEntries.has(i)
              return (
                <LogEntryCard
                  key={`${logFilter}-${i}`}
                  entry={entry}
                  expanded={isExpanded}
                  onToggle={() => toggleEntry(i)}
                />
              )
            })}

            {/* Raw logs (collapsible) */}
            {compileLogs.length > 0 && (
              <div className="mt-2 border-t border-slate-200 pt-2 dark:border-slate-800">
                <button
                  onClick={() => setRawLogsExpanded(r => !r)}
                  className="flex items-center gap-1 text-[11px] font-medium text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
                >
                  <svg
                    className={`h-3 w-3 transition-transform ${rawLogsExpanded ? 'rotate-90' : ''}`}
                    viewBox="0 0 16 16"
                    fill="currentColor"
                  >
                    <path d="M6 3l5 5-5 5V3z" />
                  </svg>
                  Raw logs ({compileLogs.length} lines)
                </button>
                {rawLogsExpanded && (
                  <pre className="mt-1 max-h-48 overflow-auto rounded bg-slate-900 p-2 text-[10px] leading-relaxed text-slate-300 font-mono dark:bg-slate-950">
                    {compileLogs.join('\n')}
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── Compact log indicator when logs panel is hidden ─── */}
      {!logsVisible && compileLogs.length > 0 && (errorCount > 0 || warningCount > 0) && (
        <button
          onClick={() => setLogsVisible(true)}
          className="flex items-center gap-2 border-t border-slate-200 bg-slate-50 px-3 py-1 text-[11px] dark:border-slate-700 dark:bg-slate-900/70 hover:bg-slate-100 dark:hover:bg-slate-800/70 transition-colors"
        >
          {errorCount > 0 && (
            <span className="flex items-center gap-0.5 text-red-500 dark:text-red-400">
              <span>&#10060;</span> {errorCount} error{errorCount !== 1 ? 's' : ''}
            </span>
          )}
          {warningCount > 0 && (
            <span className="flex items-center gap-0.5 text-amber-500 dark:text-amber-400">
              <span>&#9888;&#65039;</span> {warningCount} warning{warningCount !== 1 ? 's' : ''}
            </span>
          )}
          <span className="ml-auto text-slate-400">Click to view logs</span>
        </button>
      )}
    </>
  )
}

/* ─── Sub-components ────────────────────────────────────────────── */

interface FilterTabProps {
  label: string
  count: number
  active: boolean
  onClick: () => void
  color: string
}

const FilterTab: React.FC<FilterTabProps> = ({ label, count, active, onClick, color }) => (
  <button
    onClick={onClick}
    className={`flex items-center gap-1 rounded px-1.5 py-0.5 transition-colors ${
      active
        ? 'bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-100 font-medium'
        : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
    }`}
  >
    {label}
    <span className={`rounded px-1 py-px text-[10px] font-medium tabular-nums ${active ? color : 'text-slate-400 dark:text-slate-500'}`}>
      {count}
    </span>
  </button>
)

interface LogEntryCardProps {
  entry: ParsedLogEntry
  expanded: boolean
  onToggle: () => void
}

const LogEntryCard: React.FC<LogEntryCardProps> = ({ entry, expanded, onToggle }) => {
  const icon = entry.type === 'error' ? '\u274C' : entry.type === 'warning' ? '\u26A0\uFE0F' : '\u2139\uFE0F'
  const borderColor =
    entry.type === 'error'
      ? 'border-red-500/30 dark:border-red-500/20'
      : entry.type === 'warning'
        ? 'border-amber-500/30 dark:border-amber-500/20'
        : 'border-blue-500/30 dark:border-blue-500/20'
  const bgColor =
    entry.type === 'error'
      ? 'bg-red-50/50 dark:bg-red-950/20'
      : entry.type === 'warning'
        ? 'bg-amber-50/50 dark:bg-amber-950/20'
        : 'bg-blue-50/50 dark:bg-blue-950/20'

  return (
    <div className={`mb-1 rounded border ${borderColor} ${bgColor} overflow-hidden`}>
      <button
        onClick={onToggle}
        className="flex w-full items-start gap-1.5 px-2 py-1.5 text-left text-xs text-slate-700 hover:bg-white/50 dark:text-slate-200 dark:hover:bg-white/5"
      >
        <span className="shrink-0 text-[11px] leading-4">{icon}</span>
        <span className="flex-1 min-w-0 break-words leading-4">{entry.message}</span>
        {(entry.file || entry.line != null) && (
          <span className="shrink-0 text-[10px] text-slate-400 dark:text-slate-500 tabular-nums">
            {entry.file && entry.file}{entry.file && entry.line != null && ':'}{entry.line != null && `l.${entry.line}`}
          </span>
        )}
        <svg
          className={`h-3 w-3 shrink-0 text-slate-400 transition-transform ${expanded ? 'rotate-90' : ''}`}
          viewBox="0 0 16 16"
          fill="currentColor"
        >
          <path d="M6 3l5 5-5 5V3z" />
        </svg>
      </button>
      {expanded && (
        <pre className="border-t border-slate-200 bg-slate-900/80 px-2 py-1.5 text-[10px] leading-relaxed text-slate-300 font-mono dark:border-slate-800 overflow-x-auto">
          {entry.fullContext}
        </pre>
      )}
    </div>
  )
}

/* ─── Fix Proposals Panel ──────────────────────────────────────── */

interface FixProposalsPanelProps {
  proposals: EditProposal[]
  onApply?: (id: string) => void
  onReject?: (id: string) => void
  onApplyAll?: () => void
}

const FixProposalsPanel: React.FC<FixProposalsPanelProps> = ({ proposals, onApply, onReject, onApplyAll }) => {
  const pendingCount = proposals.filter(p => p.status === 'pending').length

  return (
    <div className="border-b border-slate-200 bg-indigo-50/50 px-2 py-1.5 dark:border-slate-700 dark:bg-indigo-950/20">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[11px] font-medium text-indigo-700 dark:text-indigo-300">
          AI Fixes ({proposals.length})
        </span>
        {pendingCount > 1 && onApplyAll && (
          <button
            onClick={onApplyAll}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
          >
            <Check className="h-2.5 w-2.5" />
            Apply All ({pendingCount})
          </button>
        )}
      </div>
      <div className="flex flex-col gap-1">
        {proposals.map(p => (
          <FixProposalCard key={p.id} proposal={p} onApply={onApply} onReject={onReject} />
        ))}
      </div>
    </div>
  )
}

interface FixProposalCardProps {
  proposal: EditProposal
  onApply?: (id: string) => void
  onReject?: (id: string) => void
}

const FixProposalCard: React.FC<FixProposalCardProps> = ({ proposal, onApply, onReject }) => {
  const isPending = proposal.status === 'pending'
  const isApproved = proposal.status === 'approved'
  const isRejected = proposal.status === 'rejected'

  return (
    <div className={`flex items-start gap-1.5 rounded border px-2 py-1 text-[11px] ${
      isApproved
        ? 'border-emerald-300/50 bg-emerald-50/50 dark:border-emerald-700/30 dark:bg-emerald-950/20'
        : isRejected
          ? 'border-slate-200/50 bg-slate-50/50 opacity-50 dark:border-slate-700/30 dark:bg-slate-900/20'
          : 'border-indigo-200/50 bg-white/60 dark:border-indigo-800/30 dark:bg-slate-800/40'
    }`}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          {isApproved && <Check className="h-3 w-3 text-emerald-600 dark:text-emerald-400 shrink-0" />}
          {isRejected && <X className="h-3 w-3 text-slate-400 shrink-0" />}
          <span className={`leading-4 ${isRejected ? 'line-through text-slate-400' : 'text-slate-700 dark:text-slate-200'}`}>
            {proposal.description}
          </span>
        </div>
        <span className="text-[10px] text-slate-400 dark:text-slate-500 tabular-nums">
          Lines {proposal.startLine}-{proposal.endLine}
        </span>
      </div>
      {isPending && (
        <div className="flex items-center gap-0.5 shrink-0">
          <button
            onClick={() => onApply?.(proposal.id)}
            className="rounded p-0.5 text-emerald-600 hover:bg-emerald-100 dark:text-emerald-400 dark:hover:bg-emerald-900/30 transition-colors"
            title="Apply fix"
          >
            <Check className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => onReject?.(proposal.id)}
            className="rounded p-0.5 text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
            title="Reject fix"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  )
}
