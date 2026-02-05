import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import { EditorState, StateEffect, type Extension } from '@codemirror/state'
import { EditorView, keymap, drawSelection, highlightActiveLine, highlightActiveLineGutter, lineNumbers } from '@codemirror/view'
import { defaultKeymap, indentWithTab, history, historyKeymap, undo, redo, undoDepth, redoDepth } from '@codemirror/commands'
import { StreamLanguage, bracketMatching, foldGutter, foldKeymap } from '@codemirror/language'
import { stex } from '@codemirror/legacy-modes/mode/stex'
import { search, searchKeymap } from '@codemirror/search'
import { closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete'
import { latexFoldService } from '../extensions/latexFoldService'
import { overleafLatexTheme } from '../codemirror/overleafTheme'
import { setRemoteSelectionsEffect, remoteSelectionsField, createRemoteDecorations } from '../extensions/remoteSelectionsField'
import { scrollOnDragSelection } from '../extensions/scrollOnDragSelection'
import type { RemoteSelection } from '../extensions/remoteSelectionsField'
import type { UndoManager } from 'yjs'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UseCodeMirrorEditorOptions {
  value: string
  onChange: (next: string) => void
  readOnly: boolean
  realtimeDoc: any | null
  realtimeAwareness: any | null
  realtimeExtensions: Extension[]
  ySharedText: any | null
  yUndoManager: UndoManager | null
  yTextReady: number
  remoteSelections: RemoteSelection[]
  synced?: boolean
}

interface UseCodeMirrorEditorReturn {
  viewRef: React.MutableRefObject<EditorView | null>
  editorReady: boolean
  undoEnabled: boolean
  redoEnabled: boolean
  hasTextSelected: boolean
  handleContainerRef: (el: HTMLDivElement | null) => void
  flushBufferedChange: () => void
  latestDocRef: React.MutableRefObject<string>
  handleUndo: () => void
  handleRedo: () => void
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useCodeMirrorEditor({
  value,
  onChange,
  readOnly,
  realtimeDoc,
  realtimeAwareness,
  realtimeExtensions,
  ySharedText,
  yUndoManager,
  yTextReady,
  remoteSelections,
  synced,
}: UseCodeMirrorEditorOptions): UseCodeMirrorEditorReturn {
  // Debug helper -- enable with `window.__SH_DEBUG_LTX = true` in DevTools
  const debugLog = useCallback((...args: any[]) => {
    try {
      if ((window as any).__SH_DEBUG_LTX) console.debug('[useCodeMirrorEditor]', ...args)
    } catch {}
  }, [])

  // -----------------------------------------------------------------------
  // Refs & change buffering
  // -----------------------------------------------------------------------
  const containerRef = useRef<HTMLDivElement | null>(null)
  const viewRef = useRef<EditorView | null>(null)
  const [editorReady, setEditorReady] = useState(false)
  const applyingFromEditorRef = useRef(false)
  const latestDocRef = useRef<string>(value || '')
  const pendingChangeTimerRef = useRef<number | null>(null)

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

  // Flush on unmount
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

  // -----------------------------------------------------------------------
  // Remote selections dispatch
  // -----------------------------------------------------------------------
  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    const decorations = createRemoteDecorations(view.state, remoteSelections)
    view.dispatch({ effects: setRemoteSelectionsEffect.of(decorations) })
  }, [remoteSelections])

  // -----------------------------------------------------------------------
  // Undo / redo state
  // -----------------------------------------------------------------------
  const [undoEnabled, setUndoEnabled] = useState(false)
  const [redoEnabled, setRedoEnabled] = useState(false)
  const [hasTextSelected, setHasTextSelected] = useState(false)

  useEffect(() => {
    if (readOnly) {
      setUndoEnabled(false)
      setRedoEnabled(false)
    } else if (realtimeDoc && yUndoManager) {
      setUndoEnabled((yUndoManager.undoStack || []).length > 0)
      setRedoEnabled((yUndoManager.redoStack || []).length > 0)
    } else {
      const view = viewRef.current
      if (view) {
        try {
          setUndoEnabled(undoDepth(view.state) > 0)
          setRedoEnabled(redoDepth(view.state) > 0)
        } catch {}
      }
    }
  }, [readOnly, realtimeDoc, yUndoManager])

  // -----------------------------------------------------------------------
  // CM extensions memo
  // -----------------------------------------------------------------------
  const cmExtensions = useMemo<Extension[]>(() => {
    const baseKeymap = [
      ...(realtimeDoc ? [] : historyKeymap),
      ...searchKeymap,
      ...closeBracketsKeymap,
      ...foldKeymap,
      indentWithTab,
      ...defaultKeymap,
    ]
    return [
      remoteSelectionsField,
      lineNumbers(),
      drawSelection(),
      highlightActiveLine(),
      highlightActiveLineGutter(),
      ...(realtimeDoc ? [] : [history()]),
      StreamLanguage.define(stex),
      keymap.of(baseKeymap),
      EditorView.lineWrapping,
      scrollOnDragSelection,
      overleafLatexTheme,
      // Search & replace (Ctrl+F / Ctrl+H)
      search({ top: true }),
      // Bracket matching & auto-closing
      bracketMatching(),
      closeBrackets(),
      // Code folding for LaTeX environments and sections
      foldGutter(),
      latexFoldService,
      ...realtimeExtensions,
      EditorView.updateListener.of((update) => {
        if (update.selectionSet || update.docChanged) {
          const hasSelection = update.state.selection.ranges.some(range => !range.empty)
          const dom = update.view.dom
          if (hasSelection) dom.classList.add('cm-has-selection')
          else dom.classList.remove('cm-has-selection')
          setHasTextSelected(hasSelection)
          if (!readOnly && realtimeAwareness) {
            try {
              const main = update.state.selection.main
              realtimeAwareness.setLocalStateField('selection', { anchor: main.from, head: main.to })
            } catch {}
          }
          try {
            if (realtimeDoc && yUndoManager) {
              setUndoEnabled((yUndoManager.undoStack || []).length > 0)
              setRedoEnabled((yUndoManager.redoStack || []).length > 0)
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
  }, [realtimeDoc, realtimeAwareness, readOnly, realtimeExtensions, scheduleBufferedChange, debugLog, yUndoManager])

  // -----------------------------------------------------------------------
  // View lifecycle helpers
  // -----------------------------------------------------------------------
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
    const isSafari = typeof navigator !== 'undefined' && /^((?!chrome|android).)*safari/i.test(navigator.userAgent)
    const yTextContent = ySharedText ? ySharedText.toString() : ''

    // In realtime mode:
    // - Safari: use yText content directly (bypasses yCollab sync timing issues)
    // - Other browsers: start empty, let yCollab sync from Yjs
    const initialDoc = realtimeDoc
      ? (isSafari && yTextContent ? yTextContent : '')
      : (latestDocRef.current || '')

    const hasYCollab = realtimeExtensions.length > 0
    debugLog('createView called', {
      isSafari,
      hasRealtimeDoc: !!realtimeDoc,
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

    debugLog('View created', {
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
    if (!readOnly && realtimeAwareness) {
      try {
        const main = view.state.selection.main
        realtimeAwareness.setLocalStateField('selection', { anchor: main.from, head: main.to })
      } catch {}
    }
  }, [cmExtensions, realtimeDoc, realtimeAwareness, readOnly, clearContainer, realtimeExtensions.length, ySharedText])

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
    if (realtimeDoc && !ySharedText) {
      debugLog('Deferring view creation until yText is ready')
      return
    }
    requestAnimationFrame(() => {
      if (!containerRef.current) return
      try { createView(containerRef.current) } catch {}
    })
  }, [createView, clearContainer, realtimeDoc, debugLog, ySharedText])

  // -----------------------------------------------------------------------
  // yText-ready effect: create view once yText is available in realtime mode
  // -----------------------------------------------------------------------
  useEffect(() => {
    debugLog('yText ready effect check', {
      hasRealtimeDoc: !!realtimeDoc,
      hasYSharedText: !!ySharedText,
      hasView: !!viewRef.current,
      hasContainer: !!containerRef.current,
      yTextReady,
      yTextLength: ySharedText?.length ?? 'N/A',
    })

    if (!realtimeDoc) return
    if (!ySharedText) return
    if (viewRef.current) return // View already exists
    if (!containerRef.current) return

    const yTextContent = ySharedText.toString()
    debugLog('yText ready, creating view now', {
      yTextLength: yTextContent.length,
      yTextContent: yTextContent.slice(0, 50),
    })
    requestAnimationFrame(() => {
      if (!containerRef.current || viewRef.current) return
      try { createView(containerRef.current) } catch {}
    })
  }, [realtimeDoc, yTextReady, createView, debugLog, ySharedText])

  // -----------------------------------------------------------------------
  // Reconfigure effect
  // -----------------------------------------------------------------------
  useEffect(() => {
    const view = viewRef.current
    if (!view) return
    view.dispatch({ effects: StateEffect.reconfigure.of(cmExtensions) })
  }, [cmExtensions])

  // -----------------------------------------------------------------------
  // Safari workaround: Force refresh when synced becomes true
  // -----------------------------------------------------------------------
  useEffect(() => {
    const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent)
    if (!isSafari) return
    if (!realtimeDoc) return

    debugLog('Safari effect triggered:', {
      synced,
      hasView: !!viewRef.current,
      hasYSharedText: !!ySharedText,
      hasContainer: !!containerRef.current,
    })

    if (!synced) return

    // Check periodically for content mismatch (Safari timing issues)
    const checkAndFix = () => {
      const yText = realtimeDoc?.getText('main')
      if (!yText) {
        debugLog('Safari: no yText available')
        return
      }

      const yContent = yText.toString()
      const viewContent = viewRef.current?.state?.doc?.toString() || ''

      debugLog('Safari sync check:', {
        yTextLength: yContent.length,
        viewLength: viewContent.length,
        mismatch: yContent.length !== viewContent.length,
      })

      // If CodeMirror view is empty but Yjs has content, force refresh
      if (viewContent.length === 0 && yContent.length > 0) {
        debugLog('Safari: view empty but Yjs has content, forcing refresh')

        if (containerRef.current) {
          // Destroy and recreate the view
          if (viewRef.current) {
            viewRef.current.destroy()
            viewRef.current = null
          }
          setTimeout(() => {
            if (containerRef.current && !viewRef.current) {
              try { createView(containerRef.current) } catch (e) {
                console.error('[useCodeMirrorEditor] Safari: failed to recreate view', e)
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
  }, [synced, realtimeDoc, createView, ySharedText])

  // -----------------------------------------------------------------------
  // Value sync (non-realtime mode only)
  // -----------------------------------------------------------------------
  useEffect(() => {
    // CRITICAL: Skip external value sync when in realtime mode
    // In realtime mode, Yjs is the single source of truth
    if (realtimeDoc) {
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
  }, [value, debugLog, realtimeDoc])

  // -----------------------------------------------------------------------
  // Undo / redo handlers (Bug fix #3: use yUndoManager in realtime mode)
  // -----------------------------------------------------------------------
  const handleUndo = useCallback(() => {
    if (yUndoManager) {
      try { yUndoManager.undo() } catch {}
      try { viewRef.current?.focus() } catch {}
      try {
        setUndoEnabled((yUndoManager.undoStack || []).length > 0)
        setRedoEnabled((yUndoManager.redoStack || []).length > 0)
      } catch {}
      return
    }
    const view = viewRef.current
    if (!view || !undoEnabled) return
    undo(view)
    try { view.focus() } catch {}
    try {
      setUndoEnabled(undoDepth(view.state) > 0)
      setRedoEnabled(redoDepth(view.state) > 0)
    } catch {}
  }, [undoEnabled, yUndoManager])

  const handleRedo = useCallback(() => {
    if (yUndoManager) {
      try { yUndoManager.redo() } catch {}
      try { viewRef.current?.focus() } catch {}
      try {
        setUndoEnabled((yUndoManager.undoStack || []).length > 0)
        setRedoEnabled((yUndoManager.redoStack || []).length > 0)
      } catch {}
      return
    }
    const view = viewRef.current
    if (!view || !redoEnabled) return
    redo(view)
    try { view.focus() } catch {}
    try {
      setUndoEnabled(undoDepth(view.state) > 0)
      setRedoEnabled(redoDepth(view.state) > 0)
    } catch {}
  }, [redoEnabled, yUndoManager])

  // -----------------------------------------------------------------------
  // Return
  // -----------------------------------------------------------------------
  return {
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
  }
}
