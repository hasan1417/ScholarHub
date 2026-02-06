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
  activeFile?: string // Multi-file: which file is active (default 'main.tex')
}

interface UseRealtimeSyncReturn {
  ySharedText: any | null
  yUndoManager: UndoManager | null
  yTextReady: number
  remoteSelections: RemoteSelection[]
  realtimeExtensions: Extension[]
  getYText: (filename: string) => any | null
  getFileList: () => string[]
}

// Map filename to Yjs shared name
function yTextKey(filename: string): string {
  return filename === 'main.tex' ? 'main' : `file:${filename}`
}

export function useRealtimeSync({
  realtimeDoc,
  awareness,
  peers,
  readOnly,
  providerVersion,
  activeFile = 'main.tex',
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
  // Track per-file UndoManagers so undo in one file doesn't affect others
  const undoManagersRef = useRef<Map<string, UndoManager>>(new Map())
  const [yTextReady, setYTextReady] = useState(0)
  const [remoteSelections, setRemoteSelections] = useState<RemoteSelection[]>([])

  // Yjs text setup — re-runs when activeFile changes
  useEffect(() => {
    if (!realtimeDoc) {
      ySharedTextRef.current = null
      yUndoManagerRef.current = null
      ySetupRef.current = false
      yKeymapRef.current = null
      return
    }
    const key = yTextKey(activeFile)
    const yText = realtimeDoc.getText(key)
    const needsInit = ySharedTextRef.current !== yText

    ySharedTextRef.current = yText

    // Get or create UndoManager for this file
    let um = undoManagersRef.current.get(activeFile)
    if (!um) {
      um = new UndoManager(yText)
      undoManagersRef.current.set(activeFile, um)
    }
    yUndoManagerRef.current = um

    if (!yKeymapRef.current) {
      yKeymapRef.current = keymap.of(yUndoManagerKeymap)
    }

    if (!ySetupRef.current) {
      debugLog('Yjs text attached, length=', yText.length, 'file=', activeFile)
      ySetupRef.current = true
    }
    if (needsInit) {
      setYTextReady(prev => prev + 1)
    }
  }, [realtimeDoc, debugLog, activeFile])

  // Get Y.Text for a given file (for reading all files during compilation)
  const getYText = useCallback((filename: string) => {
    if (!realtimeDoc) return null
    const key = yTextKey(filename)
    return realtimeDoc.getText(key)
  }, [realtimeDoc])

  // Get list of known files from the Yjs doc
  const getFileList = useCallback((): string[] => {
    if (!realtimeDoc) return ['main.tex']
    const files: string[] = ['main.tex']
    try {
      // Check the Yjs doc's shared types for file: prefixed texts
      const types = realtimeDoc.share as Map<string, any>
      if (types && typeof types.forEach === 'function') {
        types.forEach((_value: any, key: string) => {
          if (key.startsWith('file:')) {
            files.push(key.slice(5))
          }
        })
      }
    } catch {}
    return files
  }, [realtimeDoc])

  // Unified awareness effect
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
    getYText,
    getFileList,
  }
}
