import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { pdfjs, Document, Page } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
import {
  FileText,
  Highlighter,
  MessageSquare,
  Minus,
  Palette,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  StickyNote,
  Trash2,
  X,
} from 'lucide-react'
import { annotationsAPI } from '../../services/api'
import { useToast } from '../../hooks/useToast'
import type { PdfAnnotation, PdfAnnotationCreate } from '../../types'

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

interface PdfAnnotationViewerProps {
  documentId: string
  downloadUrl: string
  onClose?: () => void
}

const HIGHLIGHT_COLORS = [
  { label: 'Yellow', value: '#FFEB3B' },
  { label: 'Green', value: '#81C784' },
  { label: 'Blue', value: '#64B5F6' },
  { label: 'Pink', value: '#F48FB1' },
  { label: 'Purple', value: '#CE93D8' },
]

// --- Sub-components ---

interface AnnotationOverlayProps {
  annotations: PdfAnnotation[]
  onNoteClick: (ann: PdfAnnotation) => void
}

const AnnotationOverlay: React.FC<AnnotationOverlayProps> = ({ annotations, onNoteClick }) => (
  <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 3 }}>
    {annotations.map((ann) => {
      if (ann.type === 'note' && ann.position_data?.rects?.[0]) {
        const r = ann.position_data.rects[0]
        return (
          <div
            key={ann.id}
            className="absolute pointer-events-auto cursor-pointer group"
            style={{ left: `${r.x}%`, top: `${r.y}%` }}
            onClick={(e) => { e.stopPropagation(); onNoteClick(ann) }}
            title={ann.content || 'Note'}
          >
            <div
              className="flex h-6 w-6 items-center justify-center rounded-full shadow-md border border-white/50 transition-transform group-hover:scale-110"
              style={{ backgroundColor: ann.color }}
            >
              <StickyNote className="h-3.5 w-3.5 text-white" />
            </div>
          </div>
        )
      }
      // Highlight / underline rects
      return (ann.position_data?.rects ?? []).map((r, i) => (
        <div
          key={`${ann.id}-${i}`}
          className="absolute rounded-sm pointer-events-auto"
          style={{
            left: `${r.x}%`,
            top: `${r.y}%`,
            width: `${r.width}%`,
            height: `${r.height}%`,
            backgroundColor: ann.type === 'underline' ? 'transparent' : `${ann.color}40`,
            borderBottom: ann.type === 'underline' ? `2px solid ${ann.color}` : undefined,
            mixBlendMode: 'multiply',
          }}
          title={ann.selected_text || ''}
        />
      ))
    })}
  </div>
)

interface SelectionToolbarProps {
  position: { x: number; y: number }
  color: string
  onHighlight: () => void
  onHighlightWithNote: () => void
}

const SelectionToolbar: React.FC<SelectionToolbarProps> = ({
  position,
  color,
  onHighlight,
  onHighlightWithNote,
}) => (
  <div
    className="absolute z-20 flex items-center gap-1 rounded-lg border border-gray-200 bg-white p-1 shadow-lg dark:border-slate-600 dark:bg-slate-800"
    style={{ left: position.x, top: position.y }}
    onMouseDown={(e) => e.preventDefault()}
  >
    <button
      className="rounded p-1.5 transition-colors hover:bg-gray-100 dark:hover:bg-slate-700"
      title="Highlight"
      onMouseDown={(e) => { e.preventDefault(); onHighlight() }}
    >
      <Highlighter className="h-4 w-4" style={{ color }} />
    </button>
    <button
      className="rounded p-1.5 transition-colors hover:bg-gray-100 dark:hover:bg-slate-700"
      title="Highlight & Add Note"
      onMouseDown={(e) => { e.preventDefault(); onHighlightWithNote() }}
    >
      <MessageSquare className="h-4 w-4 text-gray-600 dark:text-slate-300" />
    </button>
  </div>
)

// --- Main Component ---

const PdfAnnotationViewer: React.FC<PdfAnnotationViewerProps> = ({
  documentId,
  downloadUrl,
  onClose,
}) => {
  const { toast } = useToast()

  // PDF state
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null)
  const [isLoadingPdf, setIsLoadingPdf] = useState(true)
  const [pdfError, setPdfError] = useState<string | null>(null)
  const [numPages, setNumPages] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)

  // Annotations state
  const [annotations, setAnnotations] = useState<PdfAnnotation[]>([])
  const [isLoadingAnnotations, setIsLoadingAnnotations] = useState(true)
  const [selectedAnnotation, setSelectedAnnotation] = useState<PdfAnnotation | null>(null)
  const [pulsingAnnotationId, setPulsingAnnotationId] = useState<string | null>(null)

  // UI state
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [activeColor, setActiveColor] = useState('#FFEB3B')
  const [showColorPicker, setShowColorPicker] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [isCreatingNote, setIsCreatingNote] = useState(false)

  // Selection state
  const [selectionToolbar, setSelectionToolbar] = useState<{
    position: { x: number; y: number }
    pageNumber: number
    text: string
    rects: Array<{ x: number; y: number; width: number; height: number }>
  } | null>(null)

  // Note creation inline
  const [notePrompt, setNotePrompt] = useState<{
    pageNumber: number
    position: { x: number; y: number }
    highlightAnnotationId?: string // if adding note to existing highlight
  } | null>(null)
  const [noteText, setNoteText] = useState('')

  // Editing
  const [editingAnnotationId, setEditingAnnotationId] = useState<string | null>(null)
  const [editContent, setEditContent] = useState('')

  // Refs
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const pageRefsMap = useRef<Map<number, HTMLDivElement>>(new Map())

  // --- Data fetching ---

  useEffect(() => {
    let cancelled = false
    const fetchPdf = async () => {
      setIsLoadingPdf(true)
      setPdfError(null)
      try {
        const token = localStorage.getItem('access_token')
        if (!token) { setPdfError('Authentication required'); return }
        const url = downloadUrl.startsWith('http')
          ? downloadUrl
          : `${window.location.origin}${downloadUrl.startsWith('/') ? downloadUrl : '/' + downloadUrl}`
        const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
        if (!resp.ok) throw new Error(`Download failed (${resp.status})`)
        const blob = await resp.blob()
        if (cancelled) return
        setPdfBlobUrl(URL.createObjectURL(blob))
      } catch (err) {
        if (!cancelled) { console.error('Failed to fetch PDF', err); setPdfError('Failed to load PDF') }
      } finally {
        if (!cancelled) setIsLoadingPdf(false)
      }
    }
    fetchPdf()
    return () => { cancelled = true }
  }, [downloadUrl])

  useEffect(() => {
    return () => { if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl) }
  }, [pdfBlobUrl])

  const loadAnnotations = useCallback(async () => {
    setIsLoadingAnnotations(true)
    try {
      const resp = await annotationsAPI.list(documentId)
      setAnnotations(resp.data.annotations)
    } catch (err) {
      console.error('Failed to load annotations', err)
    } finally {
      setIsLoadingAnnotations(false)
    }
  }, [documentId])

  useEffect(() => { loadAnnotations() }, [loadAnnotations])

  // --- Scroll-based page tracking ---

  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container) return
    const scrollMid = container.scrollTop + container.clientHeight / 3
    let closest = 1
    let closestDist = Infinity
    pageRefsMap.current.forEach((el, pageNum) => {
      const dist = Math.abs(el.offsetTop - scrollMid)
      if (dist < closestDist) { closestDist = dist; closest = pageNum }
    })
    setCurrentPage(closest)
  }, [])

  // --- Text selection handling ---

  const handleTextSelection = useCallback(() => {
    const sel = document.getSelection()
    if (!sel || sel.isCollapsed || !sel.rangeCount) {
      setSelectionToolbar(null)
      return
    }
    const text = sel.toString().trim()
    if (!text) { setSelectionToolbar(null); return }

    const range = sel.getRangeAt(0)
    // Find which page wrapper contains this selection
    let node: Node | null = range.startContainer
    let pageWrapper: HTMLElement | null = null
    while (node) {
      if (node instanceof HTMLElement && node.dataset.pageNumber) {
        pageWrapper = node
        break
      }
      node = node.parentNode
    }
    if (!pageWrapper) { setSelectionToolbar(null); return }

    const pageNumber = parseInt(pageWrapper.dataset.pageNumber!, 10)
    const pageRect = pageWrapper.getBoundingClientRect()
    const pageW = pageRect.width
    const pageH = pageRect.height

    // Compute rects as percentages
    const clientRects = range.getClientRects()
    const rects: Array<{ x: number; y: number; width: number; height: number }> = []
    for (let i = 0; i < clientRects.length; i++) {
      const cr = clientRects[i]
      rects.push({
        x: ((cr.left - pageRect.left) / pageW) * 100,
        y: ((cr.top - pageRect.top) / pageH) * 100,
        width: (cr.width / pageW) * 100,
        height: (cr.height / pageH) * 100,
      })
    }

    // Position toolbar near the end of the selection
    const lastRect = clientRects[clientRects.length - 1]
    const scrollContainer = scrollContainerRef.current
    const containerRect = scrollContainer?.getBoundingClientRect()
    if (!containerRect) return

    setSelectionToolbar({
      position: {
        x: lastRect.right - containerRect.left + (scrollContainer?.scrollLeft ?? 0),
        y: lastRect.bottom - containerRect.top + (scrollContainer?.scrollTop ?? 0) + 4,
      },
      pageNumber,
      text,
      rects,
    })
  }, [])

  useEffect(() => {
    document.addEventListener('mouseup', handleTextSelection)
    return () => document.removeEventListener('mouseup', handleTextSelection)
  }, [handleTextSelection])

  // --- Annotation CRUD ---

  const createHighlight = useCallback(async (withNote: boolean) => {
    if (!selectionToolbar) return
    const { pageNumber, text, rects } = selectionToolbar
    try {
      const data: PdfAnnotationCreate = {
        page_number: pageNumber - 1, // 0-indexed for backend
        type: 'highlight',
        color: activeColor,
        selected_text: text,
        position_data: { rects },
      }
      const resp = await annotationsAPI.create(documentId, data)
      setAnnotations((prev) => [...prev, resp.data])
      toast.success('Highlight created')
      document.getSelection()?.removeAllRanges()
      setSelectionToolbar(null)

      if (withNote) {
        const pageEl = pageRefsMap.current.get(pageNumber)
        if (pageEl) {
          const r = rects[0]
          setNotePrompt({
            pageNumber,
            position: { x: r.x, y: r.y + r.height },
            highlightAnnotationId: resp.data.id,
          })
          setNoteText('')
        }
      }
    } catch (err) {
      console.error('Failed to create highlight', err)
      toast.error('Failed to create highlight')
    }
  }, [selectionToolbar, activeColor, documentId, toast])

  const handlePageClickForNote = useCallback((e: React.MouseEvent, pageNumber: number) => {
    if (!isCreatingNote) return
    const pageEl = pageRefsMap.current.get(pageNumber)
    if (!pageEl) return
    const rect = pageEl.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * 100
    const y = ((e.clientY - rect.top) / rect.height) * 100
    setNotePrompt({ pageNumber, position: { x, y } })
    setNoteText('')
  }, [isCreatingNote])

  const handleSaveNote = useCallback(async () => {
    if (!notePrompt || !noteText.trim()) return
    try {
      if (notePrompt.highlightAnnotationId) {
        // Add note content to existing highlight
        const resp = await annotationsAPI.update(notePrompt.highlightAnnotationId, {
          content: noteText.trim(),
        })
        setAnnotations((prev) => prev.map((a) => a.id === notePrompt.highlightAnnotationId ? resp.data : a))
        toast.success('Note added to highlight')
      } else {
        // Create standalone note
        const data: PdfAnnotationCreate = {
          page_number: notePrompt.pageNumber - 1,
          type: 'note',
          color: activeColor,
          content: noteText.trim(),
          position_data: { rects: [{ x: notePrompt.position.x, y: notePrompt.position.y, width: 0, height: 0 }] },
        }
        const resp = await annotationsAPI.create(documentId, data)
        setAnnotations((prev) => [...prev, resp.data])
        toast.success('Note created')
      }
    } catch (err) {
      console.error('Failed to save note', err)
      toast.error('Failed to save note')
    } finally {
      setNotePrompt(null)
      setNoteText('')
      setIsCreatingNote(false)
    }
  }, [notePrompt, noteText, activeColor, documentId, toast])

  const handleUpdateAnnotation = useCallback(async (annotationId: string) => {
    try {
      const resp = await annotationsAPI.update(annotationId, { content: editContent })
      setAnnotations((prev) => prev.map((a) => (a.id === annotationId ? resp.data : a)))
      setEditingAnnotationId(null)
      setEditContent('')
      toast.success('Annotation updated')
    } catch (err) {
      console.error('Failed to update annotation', err)
      toast.error('Failed to update annotation')
    }
  }, [editContent, toast])

  const handleDeleteAnnotation = useCallback(async (annotationId: string) => {
    if (!window.confirm('Delete this annotation?')) return
    try {
      await annotationsAPI.delete(annotationId)
      setAnnotations((prev) => prev.filter((a) => a.id !== annotationId))
      if (selectedAnnotation?.id === annotationId) setSelectedAnnotation(null)
      toast.success('Annotation deleted')
    } catch (err) {
      console.error('Failed to delete annotation', err)
      toast.error('Failed to delete annotation')
    }
  }, [selectedAnnotation, toast])

  // --- Sidebar scrolling to annotation ---

  const scrollToAnnotation = useCallback((ann: PdfAnnotation) => {
    const pageNum = ann.page_number + 1 // convert 0-indexed to 1-indexed
    const pageEl = pageRefsMap.current.get(pageNum)
    if (pageEl && scrollContainerRef.current) {
      pageEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    setSelectedAnnotation(ann)
    setPulsingAnnotationId(ann.id)
    setTimeout(() => setPulsingAnnotationId(null), 1500)
  }, [])

  // --- Grouping annotations ---

  const groupedByPage = useMemo(() => {
    const groups: Record<number, PdfAnnotation[]> = {}
    for (const ann of annotations) {
      const page = ann.page_number
      if (!groups[page]) groups[page] = []
      groups[page].push(ann)
    }
    return groups
  }, [annotations])

  const sortedPages = useMemo(
    () => Object.keys(groupedByPage).map(Number).sort((a, b) => a - b),
    [groupedByPage],
  )

  // Annotations indexed by 1-based page number for overlays
  const annotationsByPage = useMemo(() => {
    const m: Record<number, PdfAnnotation[]> = {}
    for (const ann of annotations) {
      const p = ann.page_number + 1 // convert to 1-indexed for rendering
      if (!m[p]) m[p] = []
      m[p].push(ann)
    }
    return m
  }, [annotations])

  // --- Zoom ---

  const zoomIn = () => setZoom((z) => Math.min(z + 0.25, 3))
  const zoomOut = () => setZoom((z) => Math.max(z - 0.25, 0.25))
  const zoomReset = () => setZoom(1)

  // --- Page ref registration ---

  const setPageRef = useCallback((pageNum: number, el: HTMLDivElement | null) => {
    if (el) pageRefsMap.current.set(pageNum, el)
    else pageRefsMap.current.delete(pageNum)
  }, [])

  return (
    <div className="fixed inset-0 z-50 flex bg-black/60 backdrop-blur-sm">
      {/* Main viewer area */}
      <div className="flex flex-1 flex-col">
        {/* Toolbar */}
        <div className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-2 dark:border-slate-700 dark:bg-slate-900">
          <div className="flex items-center gap-3">
            <button onClick={onClose} className="rounded-lg p-2 text-gray-500 transition-colors hover:bg-gray-100 dark:text-slate-400 dark:hover:bg-slate-800" title="Close">
              <X className="h-5 w-5" />
            </button>
            <div className="h-5 w-px bg-gray-200 dark:bg-slate-700" />
            <FileText className="h-5 w-5 text-gray-400 dark:text-slate-500" />
            <span className="text-sm font-medium text-gray-700 dark:text-slate-300">
              PDF Annotations
            </span>
            {numPages > 0 && (
              <span className="text-xs text-gray-400 dark:text-slate-500">
                Page {currentPage} / {numPages}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Zoom controls */}
            <div className="flex items-center gap-1 rounded-lg border border-gray-200 dark:border-slate-600">
              <button onClick={zoomOut} className="p-1.5 text-gray-500 hover:bg-gray-50 dark:text-slate-400 dark:hover:bg-slate-800" title="Zoom out">
                <Minus className="h-3.5 w-3.5" />
              </button>
              <button onClick={zoomReset} className="px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:text-slate-300 dark:hover:bg-slate-800" title="Reset zoom">
                {Math.round(zoom * 100)}%
              </button>
              <button onClick={zoomIn} className="p-1.5 text-gray-500 hover:bg-gray-50 dark:text-slate-400 dark:hover:bg-slate-800" title="Zoom in">
                <Plus className="h-3.5 w-3.5" />
              </button>
            </div>

            <div className="h-5 w-px bg-gray-200 dark:bg-slate-700" />

            {/* Color picker */}
            <div className="relative">
              <button
                onClick={() => setShowColorPicker(!showColorPicker)}
                className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-2.5 py-1.5 text-sm transition-colors hover:bg-gray-50 dark:border-slate-600 dark:hover:bg-slate-800"
                title="Highlight color"
              >
                <div className="h-4 w-4 rounded-full border border-gray-300 dark:border-slate-500" style={{ backgroundColor: activeColor }} />
                <Palette className="h-3.5 w-3.5 text-gray-500 dark:text-slate-400" />
              </button>
              {showColorPicker && (
                <div className="absolute right-0 top-full z-10 mt-1 rounded-lg border border-gray-200 bg-white p-2 shadow-lg dark:border-slate-700 dark:bg-slate-800">
                  <div className="flex gap-1.5">
                    {HIGHLIGHT_COLORS.map((c) => (
                      <button
                        key={c.value}
                        onClick={() => { setActiveColor(c.value); setShowColorPicker(false) }}
                        className={`h-7 w-7 rounded-full border-2 transition-transform hover:scale-110 ${activeColor === c.value ? 'border-gray-800 dark:border-white' : 'border-transparent'}`}
                        style={{ backgroundColor: c.value }}
                        title={c.label}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Add note mode toggle */}
            <button
              onClick={() => { setIsCreatingNote(!isCreatingNote); if (isCreatingNote) setNotePrompt(null) }}
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm transition-colors ${
                isCreatingNote
                  ? 'border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-500 dark:bg-indigo-500/10 dark:text-indigo-300'
                  : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
              title="Add note by clicking on PDF"
            >
              <StickyNote className="h-3.5 w-3.5" />
              Add Note
            </button>

            <div className="h-5 w-px bg-gray-200 dark:bg-slate-700" />

            {/* Toggle sidebar */}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="rounded-lg p-2 text-gray-500 transition-colors hover:bg-gray-100 dark:text-slate-400 dark:hover:bg-slate-800"
              title={sidebarOpen ? 'Hide annotations panel' : 'Show annotations panel'}
            >
              {sidebarOpen ? <PanelRightClose className="h-5 w-5" /> : <PanelRightOpen className="h-5 w-5" />}
            </button>
          </div>
        </div>

        {/* PDF Content */}
        <div className="relative flex-1 overflow-hidden bg-gray-100 dark:bg-slate-950">
          {isLoadingPdf && (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <div className="mx-auto h-10 w-10 animate-spin rounded-full border-b-2 border-indigo-600 dark:border-indigo-400" />
                <p className="mt-3 text-sm text-gray-500 dark:text-slate-400">Loading PDF...</p>
              </div>
            </div>
          )}
          {pdfError && (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <FileText className="mx-auto h-12 w-12 text-gray-300 dark:text-slate-600" />
                <p className="mt-3 text-sm text-red-600 dark:text-red-400">{pdfError}</p>
              </div>
            </div>
          )}
          {pdfBlobUrl && !isLoadingPdf && (
            <div
              ref={scrollContainerRef}
              className="h-full w-full overflow-auto"
              onScroll={handleScroll}
              style={{ cursor: isCreatingNote ? 'crosshair' : undefined }}
            >
              <Document
                file={pdfBlobUrl}
                onLoadSuccess={(pdf) => setNumPages(pdf.numPages)}
                onLoadError={(err) => { console.error('PDF load error', err); setPdfError('Failed to render PDF') }}
                loading={
                  <div className="flex h-64 items-center justify-center">
                    <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-indigo-600" />
                  </div>
                }
                className="flex flex-col items-center gap-4 py-4"
              >
                {Array.from({ length: numPages }, (_, i) => i + 1).map((pageNum) => (
                  <div
                    key={pageNum}
                    ref={(el) => setPageRef(pageNum, el)}
                    data-page-number={pageNum}
                    className="relative shadow-lg"
                    onClick={(e) => handlePageClickForNote(e, pageNum)}
                  >
                    <Page
                      pageNumber={pageNum}
                      scale={zoom}
                      renderTextLayer={true}
                      renderAnnotationLayer={true}
                    />
                    {/* Annotation overlay */}
                    <AnnotationOverlay
                      annotations={annotationsByPage[pageNum] ?? []}
                      onNoteClick={(ann) => {
                        setSelectedAnnotation(ann)
                        setSidebarOpen(true)
                      }}
                    />
                    {/* Pulsing effect for scrolled-to annotation */}
                    {pulsingAnnotationId && annotationsByPage[pageNum]?.some((a) => a.id === pulsingAnnotationId) && (
                      <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 4 }}>
                        {annotationsByPage[pageNum]
                          .filter((a) => a.id === pulsingAnnotationId)
                          .flatMap((a) =>
                            (a.position_data?.rects ?? []).map((r, i) => (
                              <div
                                key={i}
                                className="absolute animate-pulse rounded"
                                style={{
                                  left: `${r.x}%`,
                                  top: `${r.y}%`,
                                  width: `${r.width || 3}%`,
                                  height: `${r.height || 3}%`,
                                  border: `2px solid ${a.color}`,
                                  boxShadow: `0 0 8px ${a.color}`,
                                }}
                              />
                            )),
                          )}
                      </div>
                    )}
                    {/* Inline note input */}
                    {notePrompt && notePrompt.pageNumber === pageNum && (
                      <div
                        className="absolute z-20"
                        style={{ left: `${notePrompt.position.x}%`, top: `${notePrompt.position.y}%` }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="flex flex-col gap-1 rounded-lg border border-gray-200 bg-white p-2 shadow-lg dark:border-slate-600 dark:bg-slate-800" style={{ width: 220 }}>
                          <textarea
                            value={noteText}
                            onChange={(e) => setNoteText(e.target.value)}
                            placeholder="Add a note..."
                            className="w-full rounded border border-gray-300 bg-white px-2 py-1.5 text-xs focus:border-indigo-500 focus:outline-none dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100"
                            rows={3}
                            autoFocus
                          />
                          <div className="flex gap-1 justify-end">
                            <button
                              onClick={() => { setNotePrompt(null); setNoteText('') }}
                              className="rounded px-2 py-1 text-[10px] text-gray-500 hover:bg-gray-100 dark:text-slate-400 dark:hover:bg-slate-700"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={handleSaveNote}
                              disabled={!noteText.trim()}
                              className="rounded bg-indigo-600 px-2 py-1 text-[10px] font-medium text-white hover:bg-indigo-700 disabled:opacity-50 dark:bg-indigo-500"
                            >
                              Save
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </Document>

              {/* Selection floating toolbar */}
              {selectionToolbar && (
                <SelectionToolbar
                  position={selectionToolbar.position}
                  color={activeColor}
                  onHighlight={() => createHighlight(false)}
                  onHighlightWithNote={() => createHighlight(true)}
                />
              )}
            </div>
          )}
        </div>
      </div>

      {/* Annotation sidebar */}
      {sidebarOpen && (
        <div className="flex w-80 flex-col border-l border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-900">
          <div className="border-b border-gray-200 px-4 py-3 dark:border-slate-700">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-slate-100">Annotations</h3>
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-slate-700 dark:text-slate-300">
                {annotations.length}
              </span>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {isLoadingAnnotations ? (
              <div className="flex items-center justify-center py-12">
                <div className="h-6 w-6 animate-spin rounded-full border-b-2 border-indigo-600 dark:border-indigo-400" />
              </div>
            ) : annotations.length === 0 ? (
              <div className="px-4 py-12 text-center">
                <StickyNote className="mx-auto h-8 w-8 text-gray-300 dark:text-slate-600" />
                <p className="mt-2 text-sm text-gray-500 dark:text-slate-400">No annotations yet</p>
                <p className="mt-1 text-xs text-gray-400 dark:text-slate-500">
                  Select text on the PDF to highlight, or use &quot;Add Note&quot; mode
                </p>
              </div>
            ) : (
              <div className="divide-y divide-gray-100 dark:divide-slate-800">
                {sortedPages.map((page) => (
                  <div key={page}>
                    <div className="bg-gray-50 px-4 py-1.5 dark:bg-slate-800/50">
                      <span className="text-xs font-medium text-gray-500 dark:text-slate-400">
                        Page {page + 1}
                      </span>
                    </div>
                    {groupedByPage[page].map((ann) => (
                      <div
                        key={ann.id}
                        className={`group cursor-pointer px-4 py-3 transition-colors hover:bg-gray-50 dark:hover:bg-slate-800/50 ${
                          selectedAnnotation?.id === ann.id ? 'bg-indigo-50/50 dark:bg-indigo-500/5' : ''
                        }`}
                        onClick={() => scrollToAnnotation(ann)}
                      >
                        <div className="flex items-start gap-2.5">
                          <div className="mt-1 h-3 w-3 flex-shrink-0 rounded-full" style={{ backgroundColor: ann.color }} />
                          <div className="min-w-0 flex-1">
                            <div className="mb-1 flex items-center gap-2">
                              <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-gray-600 dark:bg-slate-700 dark:text-slate-300">
                                {ann.type}
                              </span>
                              <span className="text-[10px] text-gray-400 dark:text-slate-500">
                                p.{ann.page_number + 1}
                              </span>
                            </div>

                            {ann.selected_text && (
                              <p
                                className="mb-1 rounded px-2 py-1 text-xs leading-relaxed"
                                style={{
                                  backgroundColor: ann.color + '30',
                                  borderLeft: `3px solid ${ann.color}`,
                                }}
                              >
                                &ldquo;{ann.selected_text.length > 120 ? ann.selected_text.slice(0, 120) + '...' : ann.selected_text}&rdquo;
                              </p>
                            )}

                            {editingAnnotationId === ann.id ? (
                              <div className="mt-1">
                                <textarea
                                  value={editContent}
                                  onChange={(e) => setEditContent(e.target.value)}
                                  className="w-full rounded border border-gray-300 bg-white px-2 py-1.5 text-xs focus:border-indigo-500 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                                  rows={3}
                                  autoFocus
                                  onClick={(e) => e.stopPropagation()}
                                />
                                <div className="mt-1.5 flex gap-1">
                                  <button
                                    onClick={(e) => { e.stopPropagation(); handleUpdateAnnotation(ann.id) }}
                                    className="rounded bg-indigo-600 px-2 py-1 text-[10px] font-medium text-white hover:bg-indigo-700 dark:bg-indigo-500"
                                  >
                                    Save
                                  </button>
                                  <button
                                    onClick={(e) => { e.stopPropagation(); setEditingAnnotationId(null) }}
                                    className="rounded px-2 py-1 text-[10px] text-gray-500 hover:bg-gray-100 dark:text-slate-400 dark:hover:bg-slate-700"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            ) : ann.content ? (
                              <p className="mt-0.5 text-xs leading-relaxed text-gray-600 dark:text-slate-400">
                                {ann.content}
                              </p>
                            ) : null}

                            <p className="mt-1 text-[10px] text-gray-400 dark:text-slate-500">
                              {new Date(ann.created_at).toLocaleDateString(undefined, {
                                month: 'short',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </p>
                          </div>

                          <div className="flex flex-shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                            <button
                              onClick={(e) => { e.stopPropagation(); setEditingAnnotationId(ann.id); setEditContent(ann.content || '') }}
                              className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:text-slate-500 dark:hover:bg-slate-700 dark:hover:text-slate-300"
                              title="Edit note"
                            >
                              <MessageSquare className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); handleDeleteAnnotation(ann.id) }}
                              className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:text-slate-500 dark:hover:bg-red-500/10 dark:hover:text-red-400"
                              title="Delete"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default PdfAnnotationViewer
