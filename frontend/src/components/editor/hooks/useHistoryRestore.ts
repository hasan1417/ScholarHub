import { useState, useCallback, type MutableRefObject } from 'react'
import type { EditorView } from '@codemirror/view'
import { logEvent } from '../../../utils/metrics'
import { researchPapersAPI } from '../../../services/api'

interface UseHistoryRestoreOptions {
  viewRef: MutableRefObject<EditorView | null>
  realtimeDoc: any | null
  paperId?: string
  readOnly: boolean
  disableSave: boolean
  flushBufferedChange: () => void
  onSave?: (content: string, contentJson: any) => Promise<void>
}

export function useHistoryRestore({
  viewRef, realtimeDoc, paperId, readOnly, disableSave, flushBufferedChange, onSave,
}: UseHistoryRestoreOptions) {
  const [historyPanelOpen, setHistoryPanelOpen] = useState(false)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)

  const handleRestoreFromHistory = useCallback((content: string, _snapshotId: string) => {
    if (realtimeDoc) {
      try {
        const yText = realtimeDoc.getText('main')
        // Use 'history-restore' origin so the track changes observer skips marking
        realtimeDoc.transact(() => {
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
    setHistoryPanelOpen(false)
  }, [realtimeDoc])

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

  return {
    historyPanelOpen,
    setHistoryPanelOpen,
    saveState,
    saveError,
    handleRestoreFromHistory,
    handleSave,
  }
}
