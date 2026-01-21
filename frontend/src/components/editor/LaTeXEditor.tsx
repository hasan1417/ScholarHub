import React, { useEffect, useRef, useState, useMemo, forwardRef, useImperativeHandle, useCallback } from 'react'
import { logEvent } from '../../utils/metrics'
import { researchPapersAPI, buildApiUrl, API_ROOT } from '../../services/api'
import { EditorState, EditorSelection, StateEffect, StateField, type Extension, type SelectionRange } from '@codemirror/state'
import { EditorView, keymap, drawSelection, highlightActiveLine, highlightActiveLineGutter, lineNumbers, Decoration, DecorationSet, WidgetType, ViewPlugin } from '@codemirror/view'
import { defaultKeymap, indentWithTab, history, historyKeymap, undo, redo, undoDepth, redoDepth } from '@codemirror/commands'
import { StreamLanguage } from '@codemirror/language'
import { stex } from '@codemirror/legacy-modes/mode/stex'
import { overleafLatexTheme } from './codemirror/overleafTheme'
import 'katex/dist/katex.min.css'
import pdfViewerHtml from '../../assets/pdf-viewer.html?raw'
import { ArrowLeft, Library, Bot, Save, Loader2, Undo2, Redo2, Sparkles, Type, FileText, Lightbulb, Book, Clock, ChevronDown, Bold, Italic, Sigma, List, ListOrdered, Image, Table, Link2 } from 'lucide-react'
import { LATEX_FORMATTING_GROUPS } from './latexToolbarConfig'
import FigureUploadDialog from './FigureUploadDialog'
import CitationDialog from './CitationDialog'
import HistoryPanel from './HistoryPanel'
import { yCollab, yUndoManagerKeymap } from 'y-codemirror.next'
import { UndoManager } from 'yjs'

type RemoteSelection = {
  id: string
  from: number
  to: number
  color: string
  name: string
}

class RemoteCaretWidget extends WidgetType {
  constructor(private readonly color: string, private readonly name: string) {
    super()
  }

  toDOM(): HTMLElement {
    const span = document.createElement('span')
    span.className = 'remote-caret'
    span.setAttribute('data-peer', this.name)
    span.style.position = 'relative'
    span.style.borderLeft = `2px solid ${this.color}`
    span.style.marginLeft = '-1px'
    span.style.pointerEvents = 'none'
    span.style.height = '100%'

    const label = document.createElement('span')
    label.textContent = this.name
    label.style.position = 'absolute'
    label.style.top = '-1.4rem'
    label.style.left = '0'
    label.style.fontSize = '10px'
    label.style.fontWeight = '600'
    label.style.padding = '1px 4px'
    label.style.borderRadius = '3px'
    label.style.background = this.color
    label.style.color = '#ffffff'
    label.style.whiteSpace = 'nowrap'
    label.style.pointerEvents = 'none'
    label.style.boxShadow = '0 1px 2px rgba(15,23,42,0.25)'
    label.style.transform = 'translateY(-2px)'

    const idealContrast = computeIdealTextColor(this.color)
    label.style.color = idealContrast

    span.appendChild(label)
    return span
  }

  ignoreEvent(): boolean {
    return true
  }
}

const setRemoteSelectionsEffect = StateEffect.define<DecorationSet>()

const remoteSelectionsField = StateField.define<DecorationSet>({
  create() {
    return Decoration.none
  },
  update(value, tr) {
    for (const effect of tr.effects) {
      if (effect.is(setRemoteSelectionsEffect)) return effect.value
    }
    if (tr.docChanged) return value.map(tr.changes)
    return value
  },
  provide: field => EditorView.decorations.from(field),
})

const highlightColor = (color: string) => {
  if (!color) return 'rgba(59, 130, 246, 0.25)'
  if (color.startsWith('#') && color.length === 7) {
    return `${color}33`
  }
  return color
}

/**
 * Extension that enables auto-scroll when dragging selection to edge of editor.
 * Scrolls the editor when mouse is near top or bottom edge during selection.
 * Uses pointer events with capture for reliable drag tracking.
 */
const scrollOnDragSelection = ViewPlugin.fromClass(class {
  private scrollInterval: number | null = null
  private lastMouseY = 0
  private edgeThreshold = 50 // pixels from edge to trigger scroll
  private scrollSpeed = 12 // pixels per frame
  private scrollContainer: HTMLElement | null = null

  constructor(private view: EditorView) {
    this.onPointerDown = this.onPointerDown.bind(this)
    this.onPointerMove = this.onPointerMove.bind(this)
    this.onPointerUp = this.onPointerUp.bind(this)

    view.dom.addEventListener('pointerdown', this.onPointerDown)
  }

  // Find the actual scrollable parent (where scrollHeight > clientHeight)
  findScrollableContainer(): HTMLElement {
    let el: HTMLElement | null = this.view.dom
    while (el) {
      if (el.scrollHeight > el.clientHeight + 10) {
        const style = window.getComputedStyle(el)
        if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
          return el
        }
      }
      el = el.parentElement
    }
    return this.view.scrollDOM
  }

  onPointerDown(e: PointerEvent) {
    if (e.button !== 0) return

    // Find scrollable container on first use (lazy init)
    if (!this.scrollContainer) {
      this.scrollContainer = this.findScrollableContainer()
    }

    try {
      (e.target as HTMLElement).setPointerCapture(e.pointerId)
    } catch {}

    document.addEventListener('pointermove', this.onPointerMove)
    document.addEventListener('pointerup', this.onPointerUp)
  }

  onPointerMove(e: PointerEvent) {
    if (e.buttons !== 1 || !this.scrollContainer) {
      this.stopScrolling()
      return
    }

    this.lastMouseY = e.clientY
    const rect = this.scrollContainer.getBoundingClientRect()
    const mouseY = e.clientY

    const nearTop = mouseY < rect.top + this.edgeThreshold
    const nearBottom = mouseY > rect.bottom - this.edgeThreshold

    if (nearTop || nearBottom) {
      if (!this.scrollInterval) {
        const container = this.scrollContainer
        this.scrollInterval = window.setInterval(() => {
          const currentRect = container.getBoundingClientRect()
          const currentY = this.lastMouseY

          if (currentY < currentRect.top + this.edgeThreshold) {
            const distance = Math.max(0, currentRect.top + this.edgeThreshold - currentY)
            const speed = Math.min(this.scrollSpeed + Math.floor(distance / 10), 30)
            container.scrollTop -= speed
          } else if (currentY > currentRect.bottom - this.edgeThreshold) {
            const distance = Math.max(0, currentY - (currentRect.bottom - this.edgeThreshold))
            const speed = Math.min(this.scrollSpeed + Math.floor(distance / 10), 30)
            container.scrollTop += speed
          } else {
            this.stopScrolling()
          }
        }, 16)
      }
    } else {
      this.stopScrolling()
    }
  }

  onPointerUp(e: PointerEvent) {
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId)
    } catch {}
    this.stopScrolling()
    document.removeEventListener('pointermove', this.onPointerMove)
    document.removeEventListener('pointerup', this.onPointerUp)
  }

  stopScrolling() {
    if (this.scrollInterval) {
      clearInterval(this.scrollInterval)
      this.scrollInterval = null
    }
  }

  destroy() {
    this.stopScrolling()
    this.view.dom.removeEventListener('pointerdown', this.onPointerDown)
    document.removeEventListener('pointermove', this.onPointerMove)
    document.removeEventListener('pointerup', this.onPointerUp)
  }
})

const computeIdealTextColor = (bg: string): string => {
  if (!bg || typeof bg !== 'string') return '#ffffff'
  let hex = bg.replace('#', '')
  if (hex.length === 3) {
    hex = hex.split('').map(ch => ch + ch).join('')
  }
  if (hex.length !== 6) return '#ffffff'
  const r = parseInt(hex.slice(0, 2), 16)
  const g = parseInt(hex.slice(2, 4), 16)
  const b = parseInt(hex.slice(4, 6), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.6 ? '#111827' : '#ffffff'
}

const createRemoteDecorations = (state: EditorState, selections: RemoteSelection[]): DecorationSet => {
  if (!selections || selections.length === 0) return Decoration.none
  const ranges: any[] = []
  const docLength = state.doc.length

  for (const sel of selections) {
    let from = Math.max(0, Math.min(sel.from, docLength))
    let to = Math.max(0, Math.min(sel.to, docLength))
    if (from > to) {
      const tmp = from
      from = to
      to = tmp
    }

    const color = sel.color || '#3B82F6'
    if (from === to) {
      const caret = Decoration.widget({
        widget: new RemoteCaretWidget(color, sel.name),
        side: 1,
      }).range(from)
      ranges.push(caret)
    } else {
      const mark = Decoration.mark({
        attributes: {
          style: `background-color: ${highlightColor(color)}; border-left: 2px solid ${color}; border-right: 2px solid ${color}; border-radius: 2px;`
        }
      }).range(from, to)
      ranges.push(mark)
      const caret = Decoration.widget({
        widget: new RemoteCaretWidget(color, sel.name),
        side: sel.to >= sel.from ? 1 : -1,
      }).range(sel.to)
      ranges.push(caret)
    }
  }

  return Decoration.set(ranges, true)
}

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
  onOpenAiAssistant?: (anchor: HTMLElement | null) => void
  onInsertBibliographyShortcut?: () => void
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
  { value, onChange, onSave, templateTitle, fullHeight = false, paperId, projectId, readOnly = false, disableSave = false, onNavigateBack, onOpenAiAssistant, realtime, collaborationStatus }: LaTeXEditorProps,
  ref: React.Ref<LaTeXEditorHandle>
) {
  // Optional debug helper: in DevTools run `window.__SH_DEBUG_LTX = true`
  const debugLog = useCallback((...args: any[]) => {
    try {
      if ((window as any).__SH_DEBUG_LTX) console.debug('[LaTeXEditor]', ...args)
    } catch {}
  }, [])
  const containerRef = useRef<HTMLDivElement | null>(null)
  const viewRef = useRef<EditorView | null>(null)
  const [editorReady, setEditorReady] = useState(false)
  const applyingFromEditorRef = useRef(false)
  const latestDocRef = useRef<string>(value || '')
  const pendingChangeTimerRef = useRef<number | null>(null)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [compileStatus, setCompileStatus] = useState<'idle' | 'compiling' | 'success' | 'error'>('idle')
  const [compileError, setCompileError] = useState<string | null>(null)
  const [compileLogs, setCompileLogs] = useState<string[]>([])
  const [lastCompileAt, setLastCompileAt] = useState<number | null>(null)
  const [viewMode, setViewMode] = useState<'code' | 'split' | 'pdf'>('split')
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const pdfBlobRef = useRef<string | null>(null)
  const lastPostedRevRef = useRef<number>(0)
  const compileAbortRef = useRef<AbortController | null>(null)
  const [undoEnabled, setUndoEnabled] = useState(false)
  const [redoEnabled, setRedoEnabled] = useState(false)
  const [figureDialogOpen, setFigureDialogOpen] = useState(false)
  const [citationDialogOpen, setCitationDialogOpen] = useState(false)
  const [historyPanelOpen, setHistoryPanelOpen] = useState(false)
  const [citationAnchor, setCitationAnchor] = useState<HTMLElement | null>(null)
  const [hasTextSelected, setHasTextSelected] = useState(false)
  const [toneMenuOpen, setToneMenuOpen] = useState(false)
  const [toneMenuAnchor, setToneMenuAnchor] = useState<HTMLElement | null>(null)
  const [openDropdown, setOpenDropdown] = useState<string | null>(null)
  const [aiToolsMenuOpen, setAiToolsMenuOpen] = useState(false)
  // Resizable split view
  const [splitPosition, setSplitPosition] = useState(() => {
    // Load from localStorage or default to 50%
    const saved = localStorage.getItem('latex-editor-split-position')
    return saved ? parseFloat(saved) : 50
  })
  const splitContainerRef = useRef<HTMLDivElement | null>(null)
  const isDraggingRef = useRef(false)
  const ySharedTextRef = useRef<any>(null)
  const yUndoManagerRef = useRef<UndoManager | null>(null)
  const ySetupRef = useRef(false)
  const yKeymapRef = useRef<Extension | null>(null)
  const [yTextReady, setYTextReady] = useState(0)
  const [remoteSelections, setRemoteSelections] = useState<RemoteSelection[]>([])

  useEffect(() => {
    if (realtime?.doc) {
      debugLog('Realtime session status', realtime?.status)
    }
  }, [realtime, debugLog])

  useEffect(() => {
    console.info('[LaTeXEditor] yText setup effect', {
      hasRealtimeDoc: !!realtime?.doc,
      currentYSharedText: !!ySharedTextRef.current,
    })

    if (!realtime?.doc) {
      ySharedTextRef.current = null
      yUndoManagerRef.current = null
      ySetupRef.current = false
      yKeymapRef.current = null
      return
    }
    const yDoc = realtime.doc
    const yText = yDoc.getText('main')
    const yTextContent = yText.toString()
    const needsInit = ySharedTextRef.current !== yText

    console.info('[LaTeXEditor] yText from doc', {
      yTextLength: yTextContent.length,
      yTextContent: yTextContent.slice(0, 50),
      needsInit,
    })

    ySharedTextRef.current = yText
    if (!yUndoManagerRef.current) {
      yUndoManagerRef.current = new UndoManager(yText)
      yKeymapRef.current = keymap.of(yUndoManagerKeymap)
    }
    if (!ySetupRef.current) {
      // Server-side seeding handles initial content
      // No need to seed from client - this prevents race conditions
      debugLog('Yjs text attached, length=', yText.length)
      ySetupRef.current = true
    }
    if (needsInit) {
      console.info('[LaTeXEditor] Incrementing yTextReady')
      setYTextReady(prev => prev + 1)
    }
    // No manual observer needed - yCollab extension handles all Yjs ↔ CodeMirror sync automatically
  }, [realtime?.doc, debugLog])

  useEffect(() => {
    const awareness = realtime?.awareness
    if (!awareness) {
      setRemoteSelections([])
      return
    }
    const clientId = awareness.clientID
    const updateSelections = () => {
      try {
        const peerMap = new Map((realtime?.peers || []).map(peer => [peer.id, peer]))
        const selections: RemoteSelection[] = []
        awareness.getStates().forEach((state: any, key: number) => {
          if (key === clientId) return
          const sel = state?.selection
          if (!sel || typeof sel.anchor !== 'number' || typeof sel.head !== 'number') return
          const user = state?.user || peerMap.get(state?.user?.id || '')
          const id: string = user?.id || state?.user?.id || String(key)
          if (!id) return
          const color = user?.color || state?.user?.color || '#3B82F6'
          const name = user?.name || state?.user?.name || user?.email || state?.user?.email || 'Collaborator'
          selections.push({
            id,
            from: sel.anchor,
            to: sel.head,
            color,
            name,
          })
        })
        setRemoteSelections(selections)
      } catch (err) {
        console.warn('[LaTeXEditor] failed to parse awareness selections', err)
      }
    }
    updateSelections()
    awareness.on('update', updateSelections)
    awareness.on('change', updateSelections)
    return () => {
      awareness.off('update', updateSelections)
      awareness.off('change', updateSelections)
    }
  }, [realtime?.awareness, realtime?.peers])

  // Force update when provider version changes (e.g., when new peers join)
  useEffect(() => {
    if (!realtime?.awareness || !realtime?.version) return
    debugLog('Provider version changed, refreshing awareness', { version: realtime.version })
    // Trigger a manual awareness update to pick up new peer states
    const awareness = realtime.awareness
    if (awareness) {
      try {
        // Force awareness state to be re-read
        const clientId = awareness.clientID
        const peerMap = new Map((realtime?.peers || []).map(peer => [peer.id, peer]))
        const selections: RemoteSelection[] = []
        awareness.getStates().forEach((state: any, key: number) => {
          if (key === clientId) return
          const sel = state?.selection
          if (!sel || typeof sel.anchor !== 'number' || typeof sel.head !== 'number') return
          const user = state?.user || peerMap.get(state?.user?.id || '')
          const id: string = user?.id || state?.user?.id || String(key)
          if (!id) return
          const color = user?.color || state?.user?.color || '#3B82F6'
          const name = user?.name || state?.user?.name || user?.email || state?.user?.email || 'Collaborator'
          selections.push({
            id,
            from: sel.anchor,
            to: sel.head,
            color,
            name,
          })
        })
        setRemoteSelections(selections)
      } catch (err) {
        console.warn('[LaTeXEditor] Failed to update selections on version change', err)
      }
    }
  }, [realtime?.version, realtime?.awareness, realtime?.peers, debugLog])

  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    const decorations = createRemoteDecorations(view.state, remoteSelections)
    view.dispatch({ effects: setRemoteSelectionsEffect.of(decorations) })
  }, [remoteSelections])

  useEffect(() => {
    const awareness = realtime?.awareness
    if (!awareness || readOnly) return
    return () => {
      try { awareness.setLocalStateField('selection', null) } catch {}
    }
  }, [realtime?.awareness, readOnly])

  const onChangeRef = useRef(onChange)
  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  const flushBufferedChange = useCallback(() => {
    if (pendingChangeTimerRef.current !== null) {
      window.clearTimeout(pendingChangeTimerRef.current)
      pendingChangeTimerRef.current = null
    }
    const handler = onChangeRef.current
    if (handler) handler(latestDocRef.current)
  }, [])

  const scheduleBufferedChange = useCallback(() => {
    if (pendingChangeTimerRef.current !== null) {
      window.clearTimeout(pendingChangeTimerRef.current)
    }
    pendingChangeTimerRef.current = window.setTimeout(() => {
      pendingChangeTimerRef.current = null
      const handler = onChangeRef.current
      if (handler) handler(latestDocRef.current)
    }, 220)
  }, [])

  useEffect(() => {
    return () => {
      if (pendingChangeTimerRef.current !== null) {
        window.clearTimeout(pendingChangeTimerRef.current)
        pendingChangeTimerRef.current = null
        const handler = onChangeRef.current
        if (handler) handler(latestDocRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (readOnly) {
      setUndoEnabled(false)
      setRedoEnabled(false)
    } else if (realtime?.doc && yUndoManagerRef.current) {
      setUndoEnabled((yUndoManagerRef.current.undoStack || []).length > 0)
      setRedoEnabled((yUndoManagerRef.current.redoStack || []).length > 0)
    } else {
      const view = viewRef.current
      if (view) {
        try {
          setUndoEnabled(undoDepth(view.state) > 0)
          setRedoEnabled(redoDepth(view.state) > 0)
        } catch {}
      }
    }
  }, [readOnly, realtime?.doc])

  const realtimeExtensions = useMemo<Extension[]>(() => {
    if (!realtime?.doc || !ySharedTextRef.current) return []
    const yText = ySharedTextRef.current
    const awareness = realtime?.awareness || null
    const extensions: Extension[] = [
      yCollab(yText, awareness, {
        undoManager: yUndoManagerRef.current || undefined,
      }),
    ]
    if (yKeymapRef.current) {
      extensions.push(yKeymapRef.current)
    }
    return extensions
  }, [realtime?.doc, realtime?.awareness, yTextReady])

  const cmExtensions = useMemo<Extension[]>(() => {
    const baseKeymap = [...(realtime?.doc ? [] : historyKeymap), indentWithTab, ...defaultKeymap]
    return [
      remoteSelectionsField,
      lineNumbers(),
      drawSelection(),
      highlightActiveLine(),
      highlightActiveLineGutter(),
      ...(realtime?.doc ? [] : [history()]),
      StreamLanguage.define(stex),
      keymap.of(baseKeymap),
      EditorView.lineWrapping,
      scrollOnDragSelection,
      overleafLatexTheme,
      ...realtimeExtensions,
      EditorView.updateListener.of((update) => {
        if (update.selectionSet || update.docChanged) {
          const hasSelection = update.state.selection.ranges.some(range => !range.empty)
          const dom = update.view.dom
          if (hasSelection) dom.classList.add('cm-has-selection')
          else dom.classList.remove('cm-has-selection')
          setHasTextSelected(hasSelection)
          if (!readOnly && realtime?.awareness) {
            try {
              const main = update.state.selection.main
              realtime.awareness.setLocalStateField('selection', { anchor: main.from, head: main.to })
            } catch {}
          }
          try {
            if (realtime?.doc && yUndoManagerRef.current) {
              setUndoEnabled((yUndoManagerRef.current.undoStack || []).length > 0)
              setRedoEnabled((yUndoManagerRef.current.redoStack || []).length > 0)
            } else {
              setUndoEnabled(undoDepth(update.state) > 0)
              setRedoEnabled(redoDepth(update.state) > 0)
            }
          } catch {}
        }
        if (!update.docChanged) return
        try {
          (update as any).transactions?.forEach((tr: any) => { if (tr.scrollIntoView) tr.scrollIntoView = false })
        } catch {}
        applyingFromEditorRef.current = true
        const doc = update.state.doc.toString()
        latestDocRef.current = doc
        debugLog('docChanged len=', doc.length)
        scheduleBufferedChange()
        Promise.resolve().then(() => { applyingFromEditorRef.current = false })
      }),
    ]
  }, [realtime?.doc, realtime?.awareness, readOnly, realtimeExtensions, scheduleBufferedChange, debugLog])

  // Create/destroy CodeMirror view based on container mount/unmount
  const clearContainer = useCallback((node: HTMLElement | null) => {
    if (!node) return
    try {
      node.replaceChildren()
    } catch {
      node.textContent = ''
    }
  }, [])

  const createView = useCallback((parent: HTMLElement) => {
    clearContainer(parent)
    // Safari workaround: use yText content directly instead of relying on yCollab sync
    // Safari has timing issues where yCollab doesn't properly sync content to CodeMirror
    const isSafari = typeof navigator !== 'undefined' && /^((?!chrome|android).)*safari/i.test(navigator.userAgent)
    const yTextContent = ySharedTextRef.current ? ySharedTextRef.current.toString() : ''

    // In realtime mode:
    // - Safari: use yText content directly (bypasses yCollab sync timing issues)
    // - Other browsers: start empty, let yCollab sync from Yjs
    const initialDoc = realtime?.doc
      ? (isSafari && yTextContent ? yTextContent : '')
      : (latestDocRef.current || '')

    // Debug: Check yText content before creating view
    const hasYCollab = realtimeExtensions.length > 0
    console.info('[LaTeXEditor] createView called', {
      isSafari,
      hasRealtimeDoc: !!realtime?.doc,
      yTextLength: yTextContent?.length ?? 'N/A',
      yTextSample: yTextContent?.slice(0, 50) ?? 'N/A',
      hasYCollab,
      initialDocLength: initialDoc.length,
      realtimeExtensionsCount: realtimeExtensions.length,
    })

    const state = EditorState.create({
      doc: initialDoc,
      extensions: cmExtensions,
    })

    const view = new EditorView({ state, parent })

    // Debug: Check what the view has after creation
    console.info('[LaTeXEditor] View created', {
      viewDocLength: view.state.doc.length,
      viewDocContent: view.state.doc.toString().slice(0, 50),
    })

    const hasSelection = state.selection.ranges.some(range => !range.empty)
    if (hasSelection) view.dom.classList.add('cm-has-selection')
    else view.dom.classList.remove('cm-has-selection')
    try {
      setUndoEnabled(undoDepth(state) > 0)
      setRedoEnabled(redoDepth(state) > 0)
    } catch {}
    viewRef.current = view
    setEditorReady(true)
    if (!readOnly && realtime?.awareness) {
      try {
        const main = view.state.selection.main
        realtime.awareness.setLocalStateField('selection', { anchor: main.from, head: main.to })
      } catch {}
    }
  }, [cmExtensions, realtime?.doc, realtime?.awareness, readOnly, clearContainer, realtimeExtensions.length])

  const handleContainerRef = useCallback((el: HTMLDivElement | null) => {
    if (el === containerRef.current) return
    if (el === null) {
      const prevContainer = containerRef.current
      try { viewRef.current?.destroy() } catch {}
      viewRef.current = null
      containerRef.current = null
      clearContainer(prevContainer || null)
      setEditorReady(false)
      setUndoEnabled(false)
      setRedoEnabled(false)
      return
    }
    containerRef.current = el
    try { viewRef.current?.destroy() } catch {}
    clearContainer(containerRef.current)
    viewRef.current = null
    setEditorReady(false)
    // In realtime mode, wait for yText to be ready before creating the view
    // This ensures yCollab is included in extensions from the start
    if (realtime?.doc && !ySharedTextRef.current) {
      debugLog('Deferring view creation until yText is ready')
      return
    }
    requestAnimationFrame(() => {
      if (!containerRef.current) return
      try { createView(containerRef.current) } catch {}
    })
  }, [createView, clearContainer, realtime?.doc, debugLog])

  // Create the view once yText becomes ready in realtime mode
  useEffect(() => {
    console.info('[LaTeXEditor] yText ready effect check', {
      hasRealtimeDoc: !!realtime?.doc,
      hasYSharedText: !!ySharedTextRef.current,
      hasView: !!viewRef.current,
      hasContainer: !!containerRef.current,
      yTextReady,
      yTextLength: ySharedTextRef.current?.length ?? 'N/A',
    })

    if (!realtime?.doc) return
    if (!ySharedTextRef.current) return
    if (viewRef.current) return // View already exists
    if (!containerRef.current) return

    const yTextContent = ySharedTextRef.current.toString()
    console.info('[LaTeXEditor] yText ready, creating view now', {
      yTextLength: yTextContent.length,
      yTextContent: yTextContent.slice(0, 50),
    })
    requestAnimationFrame(() => {
      if (!containerRef.current || viewRef.current) return
      try { createView(containerRef.current) } catch {}
    })
  }, [realtime?.doc, yTextReady, createView, debugLog])

  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    view.dispatch({ effects: StateEffect.reconfigure.of(cmExtensions) })
  }, [cmExtensions])

  // Safari fix: Force CodeMirror to refresh when synced becomes true
  // Safari sometimes doesn't render the content even though yCollab has it
  useEffect(() => {
    const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent)
    if (!isSafari) return
    if (!realtime?.doc) return

    // Log state for debugging
    console.info('[LaTeXEditor] Safari effect triggered:', {
      synced: realtime?.synced,
      hasView: !!viewRef.current,
      hasYSharedText: !!ySharedTextRef.current,
      hasContainer: !!containerRef.current,
    })

    if (!realtime?.synced) return

    // Check periodically for content mismatch (Safari timing issues)
    const checkAndFix = () => {
      const yText = realtime.doc?.getText('main')
      if (!yText) {
        console.info('[LaTeXEditor] Safari: no yText available')
        return
      }

      const yContent = yText.toString()
      const viewContent = viewRef.current?.state?.doc?.toString() || ''

      console.info('[LaTeXEditor] Safari sync check:', {
        yTextLength: yContent.length,
        viewLength: viewContent.length,
        mismatch: yContent.length !== viewContent.length,
      })

      // If CodeMirror view is empty but Yjs has content, force refresh
      if (viewContent.length === 0 && yContent.length > 0) {
        console.info('[LaTeXEditor] Safari: view empty but Yjs has content, forcing refresh')

        if (containerRef.current) {
          // Destroy and recreate the view
          if (viewRef.current) {
            viewRef.current.destroy()
            viewRef.current = null
          }
          // Update ySharedTextRef before creating view
          ySharedTextRef.current = yText
          setTimeout(() => {
            if (containerRef.current && !viewRef.current) {
              try { createView(containerRef.current) } catch (e) {
                console.error('[LaTeXEditor] Safari: failed to recreate view', e)
              }
            }
          }, 50)
        }
      }
    }

    // Run check immediately and after a delay (Safari timing workaround)
    checkAndFix()
    const timeout = setTimeout(checkAndFix, 500)

    return () => clearTimeout(timeout)
  }, [realtime?.synced, realtime?.doc, createView])

  // Keep external value in sync (only in non-realtime mode)
  useEffect(() => {
    // CRITICAL: Skip external value sync when in realtime mode
    // In realtime mode, Yjs is the single source of truth
    if (realtime?.doc) {
      debugLog('skipping external value sync (realtime mode)')
      return
    }

    const view = viewRef.current
    const normalized = value || ''
    if (!view) {
      latestDocRef.current = normalized
      return
    }
    if (applyingFromEditorRef.current) return
    const current = view.state.doc.toString()
    if (current === normalized) {
      latestDocRef.current = normalized
      return
    }
    debugLog('prop sync to editor, len=', normalized.length)
    latestDocRef.current = normalized
    view.dispatch({ changes: { from: 0, to: current.length, insert: normalized } })
  }, [value, debugLog, realtime?.doc])

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
  const formattingDisabled = readOnly
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

  const handleOpenAiToolbar = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    if (readOnly) return
    // Capture button rect immediately before it might unmount
    const button = event.currentTarget
    const rect = button.getBoundingClientRect()
    // Store rect in a way that survives re-renders
    const stableButton = button.cloneNode(true) as HTMLElement
    stableButton.style.position = 'fixed'
    stableButton.style.top = `${rect.top}px`
    stableButton.style.left = `${rect.left}px`
    stableButton.style.width = `${rect.width}px`
    stableButton.style.height = `${rect.height}px`
    stableButton.style.visibility = 'hidden'
    stableButton.style.pointerEvents = 'none'
    document.body.appendChild(stableButton)

    onOpenAiAssistant?.(stableButton)

    // Clean up after popover closes
    setTimeout(() => {
      if (document.body.contains(stableButton)) {
        document.body.removeChild(stableButton)
      }
    }, 5000)
  }, [readOnly, onOpenAiAssistant])

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
    if (readOnly) return

    const selectedText = getSelectedText()
    if (!selectedText.trim()) {
      alert('Please select some text first')
      return
    }

    try {
      const payload: any = {
        text: selectedText,
        action: action,
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
    }
  }, [readOnly, getSelectedText, replaceSelectedText])

  const handleToneButtonClick = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    if (readOnly || !hasTextSelected) return
    setToneMenuAnchor(event.currentTarget)
    setToneMenuOpen(true)
  }, [readOnly, hasTextSelected])

  const handleToneSelect = useCallback(async (tone: string) => {
    setToneMenuOpen(false)
    setToneMenuAnchor(null)
    await handleAiAction('tone', tone)
  }, [handleAiAction])

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

  const handleUndo = useCallback(() => {
    const view = viewRef.current
    if (!view || !undoEnabled) return
    undo(view)
    try { view.focus() } catch {}
    try {
      setUndoEnabled(undoDepth(view.state) > 0)
      setRedoEnabled(redoDepth(view.state) > 0)
    } catch {}
  }, [undoEnabled])

  const handleRedo = useCallback(() => {
    const view = viewRef.current
    if (!view || !redoEnabled) return
    redo(view)
    try { view.focus() } catch {}
    try {
      setUndoEnabled(undoDepth(view.state) > 0)
      setRedoEnabled(redoDepth(view.state) > 0)
    } catch {}
  }, [redoEnabled])

  // Resizable split handlers - use refs to avoid stale closures
  const splitPositionRef = useRef(splitPosition)
  useEffect(() => {
    splitPositionRef.current = splitPosition
  }, [splitPosition])

  const handleSplitDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    isDraggingRef.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    // Add overlay to prevent iframe from capturing mouse events
    const overlay = document.createElement('div')
    overlay.id = 'split-drag-overlay'
    overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;cursor:col-resize;'
    document.body.appendChild(overlay)

    const handleMouseMove = (moveEvent: MouseEvent) => {
      // Check if mouse button is still pressed
      if (moveEvent.buttons === 0) {
        handleMouseUp()
        return
      }
      if (!splitContainerRef.current) return
      const rect = splitContainerRef.current.getBoundingClientRect()
      const newPosition = ((moveEvent.clientX - rect.left) / rect.width) * 100
      // Clamp between 20% and 80%
      const clamped = Math.min(80, Math.max(20, newPosition))
      setSplitPosition(clamped)
    }

    const handleMouseUp = () => {
      isDraggingRef.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      // Remove overlay
      const existingOverlay = document.getElementById('split-drag-overlay')
      if (existingOverlay) existingOverlay.remove()
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      // Save current position from ref
      localStorage.setItem('latex-editor-split-position', String(splitPositionRef.current))
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [])

  const resolveApiUrl = useCallback((url: string | null | undefined) => {
    if (!url) return url || ''
    if (/^https?:/i.test(url)) return url
    const sanitized = url.startsWith('/') ? url : `/${url}`
    return `${API_ROOT}${sanitized}`
  }, [])

  const cleanupPdf = useCallback(() => {
    const current = pdfBlobRef.current
    if (current && current.startsWith('blob:')) {
      try { URL.revokeObjectURL(current) } catch {}
    }
    pdfBlobRef.current = null
  }, [])

  const postPdfToIframe = useCallback((blobUrl: string, rev: number) => {
    const iframe = iframeRef.current
    if (!iframe || !iframe.contentWindow) return
    try {
      iframe.contentWindow.postMessage({ type: 'loadFile', url: blobUrl, rev }, '*')
      console.log('[LaTeX] Posted PDF to iframe:', { rev, url: blobUrl.substring(0, 50) })
    } catch (e) {
      console.error('[LaTeX] Failed to post PDF to iframe:', e)
    }
  }, [])

  const compileNow = useCallback(async () => {
    if (readOnly) {
      setCompileError('Compile disabled in read-only mode')
      setCompileStatus('error')
      return
    }
    const projectId = paperId ?? (window as any).__SH_ACTIVE_PAPER_ID ?? null
    setCompileLogs([])
    setCompileError(null)
    setCompileStatus('compiling')
    if (compileAbortRef.current) {
      try { compileAbortRef.current.abort() } catch {}
    }
    flushBufferedChange()
    const controller = new AbortController()
    compileAbortRef.current = controller
    const buildId = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`
    try { await logEvent('CompileClicked', { srcLen: latestDocRef.current.length, projectId, buildId }) } catch {}
    const t0 = performance.now()
    let firstError: string | null = null
    let producedPdf = false
    try {
      let src = latestDocRef.current || ''
      try { const v = viewRef.current; if (v) src = v.state.doc.toString() } catch {}
      latestDocRef.current = src
      try { await logEvent('CompileStart', { approxLen: src.length, buildId, projectId }) } catch {}
      const resp = await fetch(buildApiUrl('/latex/compile/stream'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`
        },
        body: JSON.stringify({ latex_source: src, paper_id: projectId, include_bibtex: true, job_label: buildId }),
        signal: controller.signal
      })
      if (!resp.ok || !resp.body) throw new Error(`Compile failed: ${resp.status} ${resp.statusText}`)
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const seqRef = (LaTeXEditorImpl as any)._compileSeq || ((LaTeXEditorImpl as any)._compileSeq = { current: 0 })
      seqRef.current += 1
      const mySeq = seqRef.current
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''
        for (const chunk of parts) {
          const trimmed = chunk.trim()
          if (!trimmed.startsWith('data:')) continue
          try {
            const payload = JSON.parse(trimmed.replace(/^data:\s*/, ''))
            if (payload.type === 'log') {
              const line = typeof payload.line === 'string' ? payload.line : ''
              if (line) {
                setCompileLogs(prev => prev.length > 200 ? [...prev.slice(-199), line] : [...prev, line])
                if (!firstError && /error:/i.test(line)) firstError = line
              }
            } else if (payload.type === 'error') {
              const msg = payload.message || 'Compilation error'
              firstError = firstError || msg
            } else if (payload.type === 'final' && payload.pdf_url) {
              console.log('[LaTeX] Received final event with PDF URL:', payload.pdf_url)
              const pdfUrl = resolveApiUrl(payload.pdf_url)
              console.log('[LaTeX] Resolved PDF URL:', pdfUrl)
              const token = localStorage.getItem('access_token') || ''
              const pdfResp = await fetch(pdfUrl, { headers: token ? { 'Authorization': `Bearer ${token}` } : undefined })
              console.log('[LaTeX] PDF fetch response:', pdfResp.status, pdfResp.ok)
              if (!pdfResp.ok) throw new Error(`Failed to fetch PDF (${pdfResp.status})`)
              const blob = await pdfResp.blob()
              console.log('[LaTeX] PDF blob size:', blob.size, 'mySeq:', mySeq, 'currentSeq:', (LaTeXEditorImpl as any)._compileSeq.current)
              if (mySeq !== (LaTeXEditorImpl as any)._compileSeq.current) {
                console.log('[LaTeX] Skipping stale compile result')
                continue
              }
              const objectUrl = URL.createObjectURL(blob)
              console.log('[LaTeX] Created blob URL:', objectUrl)
              cleanupPdf()
              pdfBlobRef.current = objectUrl
              postPdfToIframe(objectUrl, mySeq)
              lastPostedRevRef.current = mySeq
              producedPdf = true
            }
          } catch {}
        }
      }
      const duration = Math.round(performance.now() - t0)
      try { await logEvent('CompileEnd', { buildId, durationMs: duration, projectId, success: producedPdf }) } catch {}
      if (producedPdf) {
        setCompileStatus('success')
        setCompileError(null)
        setLastCompileAt(Date.now())
      } else {
        setCompileStatus('error')
        setCompileError(firstError || 'Compilation failed')
      }
    } catch (err: any) {
      if (controller.signal.aborted) return
      const message = err?.message || 'Compilation failed'
      setCompileStatus('error')
      setCompileError(message)
    } finally {
      if (compileAbortRef.current === controller) compileAbortRef.current = null
    }
  }, [buildApiUrl, cleanupPdf, flushBufferedChange, paperId, postPdfToIframe, readOnly, resolveApiUrl])

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const data = event.data
      if (!data || typeof data !== 'object') return
      if (data.type !== 'viewer-ready') return
      const iframe = iframeRef.current
      if (iframe && event.source !== iframe.contentWindow) return
      const url = pdfBlobRef.current
      const rev = lastPostedRevRef.current
      if (!url || !rev) return
      postPdfToIframe(url, rev)
    }
    window.addEventListener('message', onMessage)
    return () => {
      window.removeEventListener('message', onMessage)
    }
  }, [postPdfToIframe])

  useEffect(() => {
    return () => {
      if (compileAbortRef.current) {
        try { compileAbortRef.current.abort() } catch {}
      }
      cleanupPdf()
    }
  }, [cleanupPdf])

  useEffect(() => {
    if (!readOnly) {
      void compileNow()
    }
  }, [compileNow, readOnly])

  return (
    <div className={containerCls}>
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3 py-2 text-slate-700 transition-colors dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-200">
        <div className="flex items-center gap-3">
          {onNavigateBack && (
            <button
              aria-label="Back to paper details"
              onClick={onNavigateBack}
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-600 transition-colors hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
          )}
          <span className="text-sm font-semibold">{templateTitle || 'LaTeX Source'}</span>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500 dark:text-slate-300">
          {collaborationStatus && (
            <span className="inline-flex items-center gap-1 rounded border border-indigo-200 bg-indigo-50 px-2 py-1 font-medium text-indigo-600 dark:border-indigo-300/40 dark:bg-indigo-400/20 dark:text-indigo-100">
              {collaborationStatus}
            </span>
          )}
          {compileStatus === 'error' && compileError && (
            <span className="max-w-xs truncate text-rose-600 dark:text-rose-200" title={compileError}>{compileError}</span>
          )}
          {compileStatus === 'success' && lastCompileAt && (
            <span className="text-emerald-600 dark:text-emerald-200">Compiled {Math.max(1, Math.round((Date.now() - lastCompileAt) / 1000))}s ago</span>
          )}
          {saveState === 'saving' && <span className="text-indigo-500 dark:text-indigo-200">Saving…</span>}
          {saveState === 'success' && <span className="text-emerald-600 dark:text-emerald-200">Draft saved</span>}
          {saveState === 'error' && saveError && <span className="max-w-xs truncate text-rose-600 dark:text-rose-200" title={saveError}>{saveError}</span>}
        </div>
      </div>
      {/* Overleaf-style Toolbar */}
      <div className="border-b border-slate-200 bg-slate-50 px-2 py-1.5 transition-colors dark:border-slate-700 dark:bg-slate-800/90">
        <div className="flex items-center gap-1">
          {/* View Mode Toggle - Overleaf style */}
          <div className="inline-flex items-center rounded-md bg-slate-200/80 p-0.5 dark:bg-slate-700">
            {(['code', 'split', 'pdf'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                className={`rounded px-3 py-1 text-xs font-medium transition-all ${
                  viewMode === mode
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white'
                }`}
              >
                {mode === 'code' ? 'Code' : mode === 'split' ? 'Split' : 'PDF'}
              </button>
            ))}
          </div>

          <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

          {viewMode !== 'pdf' && !readOnly && (
            <>
              {/* Undo/Redo */}
              <button
                type="button"
                onClick={handleUndo}
                disabled={!undoEnabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 disabled:hover:bg-transparent dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Undo"
              >
                <Undo2 className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={handleRedo}
                disabled={!redoEnabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 disabled:hover:bg-transparent dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Redo"
              >
                <Redo2 className="h-4 w-4" />
              </button>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              {/* Structure Dropdown */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setOpenDropdown(openDropdown === 'structure' ? null : 'structure')}
                  disabled={formattingDisabled}
                  className={`inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition-colors ${
                    formattingDisabled
                      ? 'cursor-not-allowed text-slate-400'
                      : openDropdown === 'structure'
                      ? 'bg-slate-200 text-slate-900 dark:bg-slate-600 dark:text-white'
                      : 'text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700'
                  }`}
                >
                  <span>Normal text</span>
                  <ChevronDown className="h-3 w-3" />
                </button>
                {openDropdown === 'structure' && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setOpenDropdown(null)} />
                    <div className="absolute left-0 top-full z-50 mt-1 min-w-[160px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-600 dark:bg-slate-800">
                      <button
                        onClick={() => { setOpenDropdown(null) }}
                        className="flex w-full items-center px-3 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        Normal text
                      </button>
                      {formattingGroups.find(g => g.label === 'Structure')?.items.map(item => (
                        <button
                          key={item.key}
                          onClick={() => { item.action(); setOpenDropdown(null) }}
                          className={`flex w-full items-center px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-700 ${
                            item.key === 'section' ? 'text-lg font-bold text-slate-800 dark:text-slate-100' :
                            item.key === 'subsection' ? 'text-base font-semibold text-slate-700 dark:text-slate-200' :
                            'text-sm font-medium text-slate-600 dark:text-slate-300'
                          }`}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              {/* Text Formatting Icons */}
              <button
                type="button"
                onClick={insertBold}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Bold (\\textbf)"
              >
                <Bold className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={insertItalics}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Italic (\\textit)"
              >
                <Italic className="h-4 w-4" />
              </button>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              {/* Math */}
              <button
                type="button"
                onClick={insertInlineMath}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Inline math ($...$)"
              >
                <Sigma className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={insertCite}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Citation (\\cite)"
              >
                <Link2 className="h-4 w-4" />
              </button>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              {/* Insert Elements */}
              <button
                type="button"
                onClick={insertFigure}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Insert figure"
              >
                <Image className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={insertTable}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Insert table"
              >
                <Table className="h-4 w-4" />
              </button>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              {/* Lists */}
              <button
                type="button"
                onClick={insertItemize}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Bullet list"
              >
                <List className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={insertEnumerate}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Numbered list"
              >
                <ListOrdered className="h-4 w-4" />
              </button>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              {/* More formatting dropdown */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setOpenDropdown(openDropdown === 'more' ? null : 'more')}
                  disabled={formattingDisabled}
                  className={`rounded p-1.5 transition-colors ${
                    formattingDisabled
                      ? 'cursor-not-allowed text-slate-400'
                      : openDropdown === 'more'
                      ? 'bg-slate-200 text-slate-900 dark:bg-slate-600 dark:text-white'
                      : 'text-slate-500 hover:bg-slate-200 dark:text-slate-400 dark:hover:bg-slate-700'
                  }`}
                  title="More formatting"
                >
                  <ChevronDown className="h-4 w-4" />
                </button>
                {openDropdown === 'more' && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setOpenDropdown(null)} />
                    <div className="absolute left-0 top-full z-50 mt-1 min-w-[180px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-600 dark:bg-slate-800">
                      <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Text</div>
                      {formattingGroups.find(g => g.label === 'Text')?.items.filter(i => !['bold', 'italic'].includes(i.key)).map(item => (
                        <button
                          key={item.key}
                          onClick={() => { item.action(); setOpenDropdown(null) }}
                          className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                        >
                          {item.icon}
                          <span>{item.label}</span>
                        </button>
                      ))}
                      <div className="my-1 border-t border-slate-200 dark:border-slate-600" />
                      <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Math</div>
                      {formattingGroups.find(g => g.label === 'Math')?.items.filter(i => i.key !== 'math-inline').map(item => (
                        <button
                          key={item.key}
                          onClick={() => { item.action(); setOpenDropdown(null) }}
                          className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                        >
                          {item.icon}
                          <span>{item.label}</span>
                        </button>
                      ))}
                      <div className="my-1 border-t border-slate-200 dark:border-slate-600" />
                      <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">References</div>
                      {formattingGroups.find(g => g.label === 'References')?.items.map(item => (
                        <button
                          key={item.key}
                          onClick={() => { item.action(); setOpenDropdown(null) }}
                          className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                        >
                          {item.icon}
                          <span>{item.label}</span>
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              {/* AI Tools */}
              <button
                type="button"
                onClick={handleOpenAiToolbar}
                disabled={readOnly || !onOpenAiAssistant}
                className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-emerald-700 transition-colors hover:bg-emerald-100 disabled:opacity-40 dark:text-emerald-400 dark:hover:bg-emerald-500/20"
                title="AI Assistant"
              >
                <Bot className="h-4 w-4" />
                <span>AI</span>
              </button>

              <button
                type="button"
                onClick={handleOpenReferencesToolbar}
                disabled={readOnly || !paperId}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="References & Citations"
              >
                <Library className="h-4 w-4" />
              </button>

              {/* AI Text Tools Dropdown */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setAiToolsMenuOpen(!aiToolsMenuOpen)}
                  disabled={readOnly || !hasTextSelected}
                  className={`rounded p-1.5 transition-colors disabled:opacity-30 ${
                    aiToolsMenuOpen
                      ? 'bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-300'
                      : 'text-slate-500 hover:bg-slate-200 dark:text-slate-400 dark:hover:bg-slate-700'
                  }`}
                  title={hasTextSelected ? 'AI text tools' : 'Select text first'}
                >
                  <Sparkles className="h-4 w-4" />
                </button>
                {aiToolsMenuOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setAiToolsMenuOpen(false)} />
                    <div className="absolute right-0 top-full z-50 mt-1 min-w-[150px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-600 dark:bg-slate-800">
                      <button
                        onClick={() => { handleAiAction('paraphrase'); setAiToolsMenuOpen(false) }}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        <Sparkles className="h-3.5 w-3.5 text-violet-500" />
                        Paraphrase
                      </button>
                      <button
                        onClick={() => { handleAiAction('summarize'); setAiToolsMenuOpen(false) }}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        <FileText className="h-3.5 w-3.5 text-emerald-500" />
                        Summarize
                      </button>
                      <button
                        onClick={() => { handleAiAction('explain'); setAiToolsMenuOpen(false) }}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        <Lightbulb className="h-3.5 w-3.5 text-amber-500" />
                        Explain
                      </button>
                      <button
                        onClick={() => { handleAiAction('synonyms'); setAiToolsMenuOpen(false) }}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        <Book className="h-3.5 w-3.5 text-blue-500" />
                        Synonyms
                      </button>
                      <div className="my-1 border-t border-slate-200 dark:border-slate-600" />
                      <button
                        onClick={handleToneButtonClick}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        <Type className="h-3.5 w-3.5 text-rose-500" />
                        Change Tone...
                      </button>
                    </div>
                  </>
                )}
              </div>
            </>
          )}

          {/* Spacer */}
          <div className="flex-1" />

          {/* Right side: History, Compile, Save */}
          <div className="flex items-center gap-1">
            {paperId && (
              <button
                type="button"
                onClick={() => setHistoryPanelOpen(true)}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="History"
              >
                <Clock className="h-4 w-4" />
              </button>
            )}

            {!(disableSave || readOnly) && (
              <button
                type="button"
                className={`rounded p-1.5 transition-colors ${
                  saveState === 'saving'
                    ? 'text-indigo-500'
                    : saveState === 'success'
                    ? 'text-emerald-500'
                    : saveState === 'error'
                    ? 'text-rose-500'
                    : 'text-slate-500 hover:bg-slate-200 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-700'
                }`}
                onClick={async () => {
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
                }}
                disabled={disableSave || readOnly}
                title={saveState === 'saving' ? 'Saving...' : saveState === 'success' ? 'Saved' : 'Save'}
              >
                {saveState === 'saving' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
              </button>
            )}

            <button
              type="button"
              className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-semibold transition-colors ${
                compileStatus === 'compiling'
                  ? 'cursor-wait bg-slate-400 text-white'
                  : compileStatus === 'success'
                  ? 'bg-emerald-600 text-white hover:bg-emerald-700'
                  : compileStatus === 'error'
                  ? 'bg-rose-600 text-white hover:bg-rose-700'
                  : 'bg-emerald-600 text-white hover:bg-emerald-700'
              }`}
              onClick={() => compileNow()}
              disabled={compileStatus === 'compiling'}
              title="Recompile"
            >
              {compileStatus === 'compiling' ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Compiling</span>
                </>
              ) : (
                <span>Recompile</span>
              )}
            </button>
          </div>
        </div>
      </div>
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
            {/* Drag handle indicator */}
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
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-300">
              <span className="font-medium text-slate-600 dark:text-slate-200">PDF Preview</span>
              {compileStatus === 'compiling' && <span className="text-indigo-500 dark:text-indigo-300">Updating…</span>}
              {compileStatus === 'success' && lastCompileAt && <span className="text-slate-500 dark:text-slate-300">Updated {Math.max(1, Math.round((Date.now() - lastCompileAt) / 1000))}s ago</span>}
              {compileStatus === 'error' && compileError && <span className="text-rose-500 dark:text-rose-300" title={compileError}>Compile failed</span>}
            </div>
            <div className="overflow-hidden flex-1">
              <iframe
                ref={iframeRef}
                id="latex-preview-frame"
                title="Compiled PDF"
                srcDoc={pdfViewerHtml}
                data-loaded="false"
                className="h-full w-full"
              />
            </div>
            {compileLogs.length > 0 && (
              <div className="max-h-40 overflow-auto border-t border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-600 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300">
                {compileLogs.slice(-60).map((line, idx) => (
                  <div key={idx} className="whitespace-pre-wrap">{line}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Figure Upload Dialog */}
      {paperId && (
        <FigureUploadDialog
          isOpen={figureDialogOpen}
          onClose={() => setFigureDialogOpen(false)}
          onInsert={handleFigureInsert}
          paperId={paperId}
        />
      )}

      {/* Citation Dialog */}
      {paperId && (
        <CitationDialog
          isOpen={citationDialogOpen}
          onClose={() => setCitationDialogOpen(false)}
          paperId={paperId}
          projectId={projectId}
          onInsertCitation={handleInsertCitation}
          onInsertBibliography={async (style, bibFile, references) => {
            // Generate BibTeX content from references
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

            console.log('Generated BibTeX content:', bibContent)

            // Upload .bib file to backend
            try {
              const formData = new FormData()
              // Create a File object instead of Blob for better compatibility
              const bibFile_obj = new File([bibContent], `${bibFile}.bib`, {
                type: 'application/x-bibtex'
              })
              formData.append('file', bibFile_obj)

              console.log('Uploading .bib file for paper:', paperId)
              console.log('File size:', bibContent.length, 'bytes')
              console.log('FormData entries:', Array.from(formData.entries()).map(([k, v]) => [k, v instanceof File ? `File: ${v.name} (${v.size} bytes)` : v]))

              const response = await researchPapersAPI.uploadBib(paperId, formData)
              console.log('Upload successful:', response.data)

              // Insert bibliography commands
              const snippet = `\\clearpage\n% Bibliography\n\\bibliographystyle{${style}}\n\\bibliography{${bibFile}}\n`
              insertAtDocumentEnd(snippet, bibFile)
            } catch (error: any) {
              console.error('Failed to upload .bib file:', error)
              console.error('Error response:', error.response?.data)
              console.error('Detail:', JSON.stringify(error.response?.data?.detail, null, 2))
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

      {/* Tone Selector Menu */}
      {toneMenuOpen && toneMenuAnchor && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => {
              setToneMenuOpen(false)
              setToneMenuAnchor(null)
            }}
          />

          {/* Menu */}
          <div
            className="fixed z-50 min-w-[160px] rounded-lg border border-slate-200 bg-white shadow-xl dark:border-slate-600 dark:bg-slate-800"
            style={{
              top: `${toneMenuAnchor.getBoundingClientRect().bottom + 8}px`,
              left: `${toneMenuAnchor.getBoundingClientRect().left}px`,
            }}
          >
            <div className="p-2">
              <div className="mb-2 px-2 text-xs font-semibold text-slate-600 dark:text-slate-400">Select Tone</div>
              {['formal', 'casual', 'academic', 'friendly', 'professional'].map((tone) => (
                <button
                  key={tone}
                  onClick={() => handleToneSelect(tone)}
                  className="w-full rounded px-3 py-2 text-left text-sm text-slate-600 transition-colors hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                >
                  {tone.charAt(0).toUpperCase() + tone.slice(1)}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      {/* History Panel - only mount when open to avoid unnecessary API calls */}
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
