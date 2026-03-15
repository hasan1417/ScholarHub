import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import { EditorState, StateEffect, type Extension } from '@codemirror/state'
import { EditorView, keymap, drawSelection, highlightActiveLine, highlightActiveLineGutter, lineNumbers } from '@codemirror/view'
import { defaultKeymap, indentWithTab, history, historyKeymap, undo, redo, undoDepth, redoDepth } from '@codemirror/commands'
import { bracketMatching, foldGutter, foldKeymap, indentOnInput } from '@codemirror/language'
import { search, searchKeymap } from '@codemirror/search'
import { closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete'
import { lintGutter } from '@codemirror/lint'
import { latexAutocompletion, completionKeymap } from '../extensions/latexAutocomplete'
import { latexFoldService } from '../extensions/latexFoldService'
import { latexLanguageSetup, latexHighlightFixes } from '../extensions/latexLanguageSetup'
import { latexSpellcheck } from '../extensions/latexSpellcheck'
import { overleafLatexTheme } from '../codemirror/overleafTheme'
import { setRemoteSelectionsEffect, remoteSelectionsField, createRemoteDecorations } from '../extensions/remoteSelectionsField'
import { scrollOnDragSelection } from '../extensions/scrollOnDragSelection'
import { trackChangesExtension } from '../extensions/trackChangesDecoration'
import { latexVisualMode } from '../extensions/latexVisualMode'

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
  paperId?: string
  trackChangesFilter?: Extension
}

interface UseCodeMirrorEditorReturn {
  viewRef: React.MutableRefObject<EditorView | null>
  editorReady: boolean
  undoEnabled: boolean
  redoEnabled: boolean
  hasTextSelected: boolean
  boldActive: boolean
  italicActive: boolean
  handleContainerRef: (el: HTMLDivElement | null) => void
  flushBufferedChange: () => void
  latestDocRef: React.MutableRefObject<string>
  handleUndo: () => void
  handleRedo: () => void
  onSaveRef: React.MutableRefObject<(() => void) | null>
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
  paperId,
  trackChangesFilter,
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
  const syncedRef = useRef(synced)
  syncedRef.current = synced

  const onChangeRef = useRef(onChange)
  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  // Save callback ref — set by the parent after useHistoryRestore provides handleSave
  const onSaveRef = useRef<(() => void) | null>(null)


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
  const [boldActive, setBoldActive] = useState(false)
  const [italicActive, setItalicActive] = useState(false)

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
      { key: 'Mod-s', run: () => { onSaveRef.current?.(); return true } },
      ...(realtimeDoc ? [] : historyKeymap),
      ...searchKeymap,
      ...closeBracketsKeymap,
      ...completionKeymap,
      ...foldKeymap,
      indentWithTab,
      ...defaultKeymap,
    ]
    return [
      remoteSelectionsField,
      lineNumbers(),
      drawSelection(),
      highlightActiveLine(), highlightActiveLineGutter(),
      ...(realtimeDoc ? [] : [history()]),
      latexLanguageSetup(),
      latexHighlightFixes(),
      keymap.of(baseKeymap),
      EditorView.lineWrapping,
      scrollOnDragSelection,
      overleafLatexTheme,
      // Search & replace (Ctrl+F / Ctrl+H)
      search({ top: false }),
      // Bracket matching, auto-closing & auto-indentation
      bracketMatching(),
      closeBrackets(),
      indentOnInput(),
      // LaTeX-aware autocompletion (commands, environments, citations, refs)
      latexAutocompletion(paperId),
      // Code folding for LaTeX environments and sections
      foldGutter(), latexFoldService,
      lintGutter(),
      latexSpellcheck(),
      trackChangesExtension(),
      latexVisualMode(),
      ...(trackChangesFilter ? [trackChangesFilter] : []),

      ...realtimeExtensions,
      EditorView.updateListener.of((update) => {
        if (update.selectionSet || update.docChanged) {
          const hasSelection = update.state.selection.ranges.some(range => !range.empty)
          const dom = update.view.dom
          if (hasSelection) dom.classList.add('cm-has-selection')
          else dom.classList.remove('cm-has-selection')
          setHasTextSelected(hasSelection)
          // Detect if cursor is inside \textbf{} or \textit{}
          const pos = update.state.selection.main.head
          const doc = update.state.doc.toString()
          const lineStart = doc.lastIndexOf('\n', pos - 1) + 1
          const before = doc.slice(lineStart, pos)
          setBoldActive(/\\textbf\{(?:[^}]*)$/.test(before))
          setItalicActive(/\\textit\{(?:[^}]*)$/.test(before))
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
  }, [realtimeDoc, realtimeAwareness, readOnly, realtimeExtensions, scheduleBufferedChange, debugLog, yUndoManager, paperId, trackChangesFilter])

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
    // In realtime mode:
    //  - If provider has NOT synced yet (synced=false): use '' as initialDoc.
    //    yCollab's Y.Text observer will push content when the provider syncs.
    //  - If provider HAS synced (synced=true, e.g. HMR re-mount): use Y.Text
    //    content as initialDoc, since no new sync event will fire the observer.
    let initialDoc: string
    if (realtimeDoc) {
      // When provider has NOT synced yet (synced=false): use '' — yCollab
      // will push Y.Text content when the provider syncs.
      // When provider HAS synced (synced=true, e.g. file switch): use
      // Y.Text content directly, since yCollab won't fire a new sync.
      if (syncedRef.current) {
        const yText = ySharedText || realtimeDoc.getText('main')
        initialDoc = yText?.toString() || ''
      } else {
        initialDoc = ''
      }
    } else {
      initialDoc = latestDocRef.current || ''
    }

    const hasYCollab = realtimeExtensions.length > 0
    debugLog('createView called', {
      hasRealtimeDoc: !!realtimeDoc,
      hasYCollab,
      initialDocLength: initialDoc.length,
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
  // yText-ready effect: create or RECREATE view when yText changes
  // (e.g. initial load or multi-file switching)
  // -----------------------------------------------------------------------
  const prevYTextRef = useRef<any>(null)
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
    if (!containerRef.current) return

    const isFileSwitch = viewRef.current && prevYTextRef.current && prevYTextRef.current !== ySharedText
    prevYTextRef.current = ySharedText

    if (viewRef.current && !isFileSwitch) return // View already exists, same file

    // Destroy old view on file switch — yCollab can't be swapped via reconfigure
    if (isFileSwitch && viewRef.current) {
      debugLog('File switch detected, recreating view')
      try { viewRef.current.destroy() } catch {}
      viewRef.current = null
      // Create immediately — container is already in DOM (no rAF gap)
      if (containerRef.current) {
        try { createView(containerRef.current) } catch {}
      }
      return
    }

    // Initial mount — use rAF to ensure container is in the DOM
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
  // Post-sync integrity check: detect doubled content in Y.Text
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!realtimeDoc) return
    if (!synced) return

    const checkAndFix = () => {
      const yText = realtimeDoc?.getText('main')
      if (!yText) return

      const yContent = yText.toString()

      // Safety net: detect doubled content in Y.Text.
      // If the content is exactly the same text repeated twice, fix it.
      if (yContent.length > 100 && yContent.length % 2 === 0) {
        const half = yContent.length / 2
        const firstHalf = yContent.slice(0, half)
        const secondHalf = yContent.slice(half)
        if (firstHalf === secondHalf) {
          console.warn('[useCodeMirrorEditor] Detected doubled content in Y.Text, deduplicating', {
            totalLength: yContent.length,
            halfLength: half,
          })
          realtimeDoc.transact(() => {
            yText.delete(half, half)
          })
          return // yCollab will sync the corrected content to the view
        }
      }
    }

    // Run check after a delay to catch bootstrap-related doubling
    const timeout = setTimeout(checkAndFix, 1500)

    return () => clearTimeout(timeout)
  }, [synced, realtimeDoc, debugLog])

  // -----------------------------------------------------------------------
  // Value sync (non-realtime mode only)
  // -----------------------------------------------------------------------
  useEffect(() => {
    // CRITICAL: Skip external value sync when in realtime mode.
    // In realtime mode, Yjs is the single source of truth — never push
    // prop values into the editor (which would also flow into Y.Text via
    // yCollab and risk content doubling during bootstrap).
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
    boldActive,
    italicActive,
    handleContainerRef,
    flushBufferedChange,
    latestDocRef,
    handleUndo,
    handleRedo,
    onSaveRef,
  }
}
