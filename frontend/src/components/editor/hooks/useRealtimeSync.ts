import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import { keymap } from '@codemirror/view'
import type { Extension } from '@codemirror/state'
import { yCollab, yUndoManagerKeymap } from 'y-codemirror.next'
import { UndoManager } from 'yjs'
import type { RemoteSelection } from '../extensions/remoteSelectionsField'

interface UseRealtimeSyncOptions {
  realtimeDoc: any | null
  awareness: any | null
  peers: Array<{ id: string; name: string; email: string; color?: string }>
  readOnly: boolean
  providerVersion?: number
  synced?: boolean
}

interface UseRealtimeSyncReturn {
  ySharedText: any | null
  yUndoManager: UndoManager | null
  yTextReady: number
  remoteSelections: RemoteSelection[]
  realtimeExtensions: Extension[]
}

export function useRealtimeSync({
  realtimeDoc,
  awareness,
  peers,
  readOnly,
  providerVersion,
}: UseRealtimeSyncOptions): UseRealtimeSyncReturn {
  const debugLog = useCallback((...args: any[]) => {
    try {
      if ((window as any).__SH_DEBUG_LTX) console.debug('[useRealtimeSync]', ...args)
    } catch {}
  }, [])

  const ySharedTextRef = useRef<any>(null)
  const yUndoManagerRef = useRef<UndoManager | null>(null)
  const ySetupRef = useRef(false)
  const yKeymapRef = useRef<Extension | null>(null)
  const [yTextReady, setYTextReady] = useState(0)
  const [remoteSelections, setRemoteSelections] = useState<RemoteSelection[]>([])

  // Yjs text setup
  useEffect(() => {
    if (!realtimeDoc) {
      ySharedTextRef.current = null
      yUndoManagerRef.current = null
      ySetupRef.current = false
      yKeymapRef.current = null
      return
    }
    const yText = realtimeDoc.getText('main')
    const needsInit = ySharedTextRef.current !== yText

    ySharedTextRef.current = yText
    if (!yUndoManagerRef.current) {
      yUndoManagerRef.current = new UndoManager(yText)
      yKeymapRef.current = keymap.of(yUndoManagerKeymap)
    }
    if (!ySetupRef.current) {
      debugLog('Yjs text attached, length=', yText.length)
      ySetupRef.current = true
    }
    if (needsInit) {
      setYTextReady(prev => prev + 1)
    }
  }, [realtimeDoc, debugLog])

  // Unified awareness effect — merges the two duplicate effects from the original
  // Depends on [awareness, peers, providerVersion] to cover both regular updates
  // and provider version changes
  useEffect(() => {
    if (!awareness) {
      setRemoteSelections([])
      return
    }
    const clientId = awareness.clientID
    const parseSelections = () => {
      try {
        const peerMap = new Map((peers || []).map(peer => [peer.id, peer]))
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
          selections.push({ id, from: sel.anchor, to: sel.head, color, name })
        })
        setRemoteSelections(selections)
      } catch (err) {
        console.warn('[useRealtimeSync] failed to parse awareness selections', err)
      }
    }
    parseSelections()
    awareness.on('update', parseSelections)
    awareness.on('change', parseSelections)
    return () => {
      awareness.off('update', parseSelections)
      awareness.off('change', parseSelections)
    }
  }, [awareness, peers, providerVersion])

  // Cleanup awareness selection on unmount
  useEffect(() => {
    if (!awareness || readOnly) return
    return () => {
      try { awareness.setLocalStateField('selection', null) } catch {}
    }
  }, [awareness, readOnly])

  // Build realtime CM extensions
  const realtimeExtensions = useMemo<Extension[]>(() => {
    if (!realtimeDoc || !ySharedTextRef.current) return []
    const yText = ySharedTextRef.current
    const ext: Extension[] = [
      yCollab(yText, awareness, {
        undoManager: yUndoManagerRef.current || undefined,
      }),
    ]
    if (yKeymapRef.current) {
      ext.push(yKeymapRef.current)
    }
    return ext
  }, [realtimeDoc, awareness, yTextReady])

  return {
    ySharedText: ySharedTextRef.current,
    yUndoManager: yUndoManagerRef.current,
    yTextReady,
    remoteSelections,
    realtimeExtensions,
  }
}
