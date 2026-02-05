import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { EditorAdapterHandle, EditorAdapterProps } from './EditorAdapter'
import LaTeXEditor from '../../editor/LaTeXEditor'
import { researchPapersAPI } from '../../../services/api'

type Props = EditorAdapterProps;

type EnhancedProps = Props & { branchName?: 'draft' | 'published'; };

const LatexAdapter = forwardRef(function LatexAdapter(
  props: EnhancedProps,
  ref: React.Ref<EditorAdapterHandle>
) {
  const { contentJson, onContentChange, onReady, onDirtyChange, className, paperId, projectId, paperTitle, lockedSectionKeys, branchName = 'draft', readOnly = false, onNavigateBack, onOpenReferences, onOpenAiChatWithMessage, onInsertBibliographyShortcut, realtime, collaborationStatus, theme: _theme } = props
  const dbg = (...args: any[]) => { try { if ((window as any).__SH_DEBUG_LTX) console.debug('[LatexAdapter]', ...args) } catch {} }
  const editorRef = useRef<any>(null)
  const realtimeEnabled = Boolean(realtime?.enabled)
  const realtimeActive = Boolean(realtime?.doc)
  const [src, setSrc] = useState<string>(() => {
    if (realtimeActive && realtime?.doc) {
      try {
        return realtime.doc.getText('main').toString()
      } catch {}
    }
    const fromJson = (contentJson && typeof contentJson === 'object' && (contentJson as any).latex_source) || ''
    let initial = typeof fromJson === 'string' ? fromJson : ''
    if (paperId && !realtimeEnabled) {
      try {
        const draft = localStorage.getItem(`paper:${paperId}:draft`)
        if (typeof draft === 'string' && draft.length > 0) {
          initial = draft
          try { dbg('restored draft from storage', { len: draft.length }) } catch {}
        }
      } catch {}
    }
    return initial
  })
  const dirtyTimerRef = useRef<number | null>(null)
  const [currentCommitId] = useState<string | null>(null)
  const lastCheckpointContentRef = useRef<string>(src)
  const lastCheckpointAtRef = useRef<number>(Date.now())
  const realtimeDocRef = useRef<any>(realtime?.doc || null)
  const realtimeLastSnapshotRef = useRef<string>('')

  useEffect(() => {
    if (realtimeEnabled && paperId) {
      try { localStorage.removeItem(`paper:${paperId}:draft`) } catch {}
    }
  }, [realtimeEnabled, paperId])

  useEffect(() => {
    realtimeDocRef.current = realtime?.doc || null
    if (realtime?.doc) {
      try {
        dbg('Realtime doc attached', { status: realtime?.status })
        const text = realtime.doc.getText('main')
        if (text) {
          setSrc(text.toString())
        }
      } catch {}
    }
  }, [realtime, dbg])

  useEffect(() => {
    const fromJson = (contentJson && typeof contentJson === 'object' && (contentJson as any).latex_source) || ''
    let next = typeof fromJson === 'string' ? fromJson : ''
    if (paperId && !realtimeEnabled) {
      try {
        const draft = localStorage.getItem(`paper:${paperId}:draft`)
        if (typeof draft === 'string' && draft.length > 0) {
          next = draft
          try { dbg('prop change: using stored draft', { len: draft.length }) } catch {}
        }
      } catch {}
    }
    if (typeof next === 'string' && next !== src) {
      try { dbg('prop contentJson change', { len: (next || '').length }) } catch {}
      setSrc(next)
      lastCheckpointContentRef.current = next || ''
      lastCheckpointAtRef.current = Date.now()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contentJson, paperId, realtimeEnabled])

  useEffect(() => {
    if (!realtimeActive || !realtime?.doc) return
    const yText = realtime.doc.getText('main')
    try {
      realtimeLastSnapshotRef.current = yText.toString()
    } catch {}
    const observer = () => {
      try {
        const next = yText.toString()
        if (next !== realtimeLastSnapshotRef.current) {
          try {
            console.info('[LatexAdapter] Realtime doc observer update', {
              length: next.length,
              sample: next.slice(0, 80),
            })
          } catch {}
          realtimeLastSnapshotRef.current = next
        }
        setSrc(prev => (prev === next ? prev : next))
      } catch {}
    }
    yText.observe(observer)
    return () => {
      try { yText.unobserve(observer) } catch {}
    }
  }, [realtimeActive, realtime?.doc])
  // No CRDT: no websocket, no snapshots; simple controlled editor

  // Draft content is controlled by DocumentShell; avoid fetching here to prevent races on first input.

  // Expose adapter methods
  useImperativeHandle(ref, () => ({
    getSelection: async () => {
      try { return await editorRef.current?.getSelection?.() } catch { return '' }
    },
    insertText: async (text: string) => {
      if (readOnly) return
      try { await editorRef.current?.replaceSelection?.(text) } catch {}
    },
    replaceSelection: async (text: string) => {
      if (readOnly) return
      try { await editorRef.current?.replaceSelection?.(text) } catch {}
    },
    // Get current content from the source of truth
    getContent: () => {
      if (realtimeActive && realtime?.doc) {
        try {
          return realtime.doc.getText('main').toString()
        } catch {}
      }
      return src
    },
    // For LaTeX, treat setContent as setting the LaTeX source (used for remote updates)
    setContent: async (text: string, options?: { overwriteRealtime?: boolean }) => {
      const next = typeof text === 'string' ? text : ''
      const overwriteRealtime = options?.overwriteRealtime ?? true
      try { console.debug('[LatexAdapter] setContent called:', { length: next.length, overwriteRealtime }) } catch {}

      try {
        const realtimeDoc = realtimeActive && realtime?.doc ? realtime.doc : null
        if (realtimeDoc) {
          const yText = realtimeDoc.getText('main')
          const currentRealtime = yText.toString()
          const realtimeLength = yText.length

          if (!overwriteRealtime && realtimeLength > 0) {
            dbg('setContent skipped (overwriteRealtime=false, realtime has content)', { realtimeLength })
            try {
              console.info('[LatexAdapter] setContent skipped to protect realtime doc', {
                overwriteRealtime,
                realtimeLength,
                incomingLength: next.length,
              })
            } catch {}
            setSrc(prev => (prev === currentRealtime ? prev : currentRealtime))
            lastCheckpointContentRef.current = currentRealtime
            lastCheckpointAtRef.current = Date.now()
            return
          }

          if (currentRealtime === next) {
            setSrc(prev => (prev === currentRealtime ? prev : currentRealtime))
            lastCheckpointContentRef.current = currentRealtime
            lastCheckpointAtRef.current = Date.now()
            return
          }

          try {
            console.info('[LatexAdapter] Overwriting realtime doc via setContent', {
              overwriteRealtime,
              previousLength: realtimeLength,
              incomingLength: next.length,
            })
            yText.delete(0, realtimeLength)
            if (next) {
              yText.insert(0, next)
            }
          } catch (err) {
            console.warn('[LatexAdapter] failed to overwrite realtime doc via setContent', err)
          }

          setSrc(next)
          lastCheckpointContentRef.current = next
          lastCheckpointAtRef.current = Date.now()
          return
        }

        setSrc(next)
        lastCheckpointContentRef.current = next
        lastCheckpointAtRef.current = Date.now()
        try { await editorRef.current?.setValue?.(next, { suppressChange: true }) } catch {}
      } catch (e) {
        console.warn('[LatexAdapter] setContent failed:', e)
      }
    },
    insertHTML: async (html: string) => {
      // For LaTeX, treat HTML as plain text insertion
      if (readOnly) return
      try { await editorRef.current?.replaceSelection?.(html) } catch {}
    },
    save: async () => {
      if (readOnly) return
      // Persist LaTeX draft directly on the paper (no version)
      try {
        const v = typeof src === 'string' ? src : ''
        if (!paperId) return
        await researchPapersAPI.updatePaperContent(paperId, { content_json: { authoring_mode: 'latex', latex_source: v } })
      } catch (e) { throw e }
    },
    focus: () => { try { editorRef.current?.focus?.() } catch {} }
    ,
    getCurrentCommitId: async () => {
      try { return currentCommitId } catch { return null }
    },
    scrollToLine: async (line: number) => { try { editorRef.current?.scrollToLine?.(line) } catch {} },
    replaceLines: async (fromLine: number, toLine: number, text: string) => { if (readOnly) return; try { editorRef.current?.replaceLines?.(fromLine, toLine, text) } catch {} }
  }), [currentCommitId, src, paperId, readOnly])

  // Handle content changes from LaTeX editor
  const handleChange = (next: string) => {
    if (readOnly) {
      // In realtime mode, don't update local state - Yjs manages it
      if (!realtimeActive) {
        setSrc(next)
      } else {
        dbg('onChange (realtime, skipping setSrc)', { len: next.length })
      }
      try { onContentChange(next || '', { authoring_mode: 'latex', latex_source: next || '' }) } catch {}
      return
    }
    const normalized = next || ''
    // Keep local state in sync so the controlled editor value matches realtime text.
    setSrc(normalized)
    if (realtimeActive) {
      dbg('onChange (realtime mode, setSrc for sync)', { len: normalized.length })
    } else {
      dbg('onChange (local mode)', { len: normalized.length })
    }
    // Notify host
    try { onContentChange(normalized, { authoring_mode: 'latex', latex_source: normalized }) } catch {}

    // Dirty state management (3 seconds) — only for draft
    if (branchName === 'draft' && !realtimeEnabled) {
      try { onDirtyChange?.(true) } catch {}
      if (dirtyTimerRef.current) window.clearTimeout(dirtyTimerRef.current)
      dirtyTimerRef.current = window.setTimeout(() => {
        try { onDirtyChange?.(false) } catch {}
        // Checkpointing: if >20% change from last checkpoint and > 2 mins since last checkpoint, create one
        try {
          const prev = lastCheckpointContentRef.current || ''
          const curr = next || ''
          const delta = Math.abs(curr.length - prev.length)
          const base = Math.max(prev.length, 1)
          const pct = delta / base
          const elapsedMs = Date.now() - lastCheckpointAtRef.current
          // No implicit versioning; keep draft locally only
          if (pct >= 0.2 && elapsedMs > 120000 && paperId) {
            lastCheckpointContentRef.current = curr
            lastCheckpointAtRef.current = Date.now()
            try { localStorage.removeItem(`paper:${paperId}:draft`) } catch {}
          }
        } catch {}
      }, 3000) as any
    }

    // Persist draft for recovery
    if (!realtimeEnabled) {
      try { if (paperId) { localStorage.setItem(`paper:${paperId}:draft`, next || ''); dbg('draft saved', { len: (next||'').length }) } } catch {}
    }
  }

  // Handle save from LaTeX editor - simple approach
  const handleSave = async (content: string, contentJson: any) => {
    if (readOnly) return
    if (!paperId) throw new Error('No paper ID available')

    // Save draft to paper content_json (no new version)
    // manual_save: true ensures a snapshot is always created for user-initiated saves
    await researchPapersAPI.updatePaperContent(paperId, { content_json: contentJson, manual_save: true })
    try { dbg('manual save (draft)') } catch {}

    // Update local state to match
    setSrc(content)
    lastCheckpointContentRef.current = content
    lastCheckpointAtRef.current = Date.now()
    // Clear draft on successful manual save
    if (!realtimeEnabled) {
      try { if (paperId) localStorage.removeItem(`paper:${paperId}:draft`) } catch {}
    }
  }

  // Provide a save function if host wants it
  useEffect(() => {
    onReady?.(async () => { /* no-op; host manages save */ })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    return () => {
      if (dirtyTimerRef.current) {
        window.clearTimeout(dirtyTimerRef.current)
        dirtyTimerRef.current = null
      }
    }
  }, [])

  // No special viewer-only mode; always mount editor to keep Save and PDF preview behavior consistent

  return (
    <div className={`flex flex-1 min-h-0 ${className || ''}`}>
      <LaTeXEditor
        ref={editorRef}
        value={src}
        onChange={handleChange}
        onSave={handleSave}
        templateTitle={paperTitle}
        fullHeight
        paperId={paperId}
        projectId={projectId}
        uncontrolled={false}
      lockedSectionKeys={lockedSectionKeys || []}
      branchName={branchName || 'draft'}
      readOnly={readOnly}
      disableSave={readOnly}
      allowAutoVersion={false}
      onNavigateBack={onNavigateBack}
      onOpenReferences={onOpenReferences}
      onOpenAiChatWithMessage={onOpenAiChatWithMessage}
      onInsertBibliographyShortcut={onInsertBibliographyShortcut}
      realtime={realtime}
      collaborationStatus={collaborationStatus}
    />
  </div>
)
})

export default React.memo(LatexAdapter)
