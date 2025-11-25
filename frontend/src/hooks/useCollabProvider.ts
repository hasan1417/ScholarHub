import { useEffect, useMemo, useState } from 'react'
import { HocuspocusProvider } from '@hocuspocus/provider'
import * as Y from 'yjs'
import { collabConfig, isCollabEnabled } from '../config/collab'

interface UseCollabProviderArgs {
  paperId?: string
  enabled?: boolean
  token?: string | null
  wsUrl?: string | null
}

export function useCollabProvider({ paperId, enabled, token, wsUrl }: UseCollabProviderArgs) {
  const featureEnabled = isCollabEnabled()
  const shouldEnable = featureEnabled && enabled && Boolean(paperId) && Boolean(token)
  const [status, setStatus] = useState<'idle' | 'connecting' | 'connected' | 'disconnected'>('idle')
  const [state, setState] = useState<{ instance: HocuspocusProvider; doc: Y.Doc } | null>(null)
  const [providerVersion, setProviderVersion] = useState(0)
  const [synced, setSynced] = useState(false)

  useEffect(() => {
    if (!shouldEnable || !paperId || !token) {
      setStatus('idle')
      setSynced(false)
      setState(prev => {
        prev?.instance?.destroy()
        return null
      })
      return
    }

    setStatus('connecting')
    setSynced(false)
    const doc = new Y.Doc()
    const instance = new HocuspocusProvider({
      url: wsUrl || collabConfig.wsUrl || 'ws://localhost:3001',
      name: paperId,
      token,
      document: doc,
    })

    const handleStatus = (event: { status: string }) => {
      if (event.status === 'connected') {
        setStatus('connected')
        // Increment version to force re-render of dependent components
        setProviderVersion(v => v + 1)
        return
      }
      if (event.status === 'disconnected') {
        setStatus('disconnected')
        setSynced(false)
      }
    }

    const handleSynced = () => {
      setStatus('connected')
      setSynced(true)
      // Increment version when synced to ensure components update
      setProviderVersion(v => v + 1)
    }

    instance.on('status', handleStatus)
    instance.on('synced', handleSynced)

    setState({ instance, doc })

    return () => {
      setSynced(false)
      instance.off('status', handleStatus)
      instance.off('synced', handleSynced)
      instance.destroy()
    }
  }, [shouldEnable, paperId, token, wsUrl])

  const awareness = useMemo(() => state?.instance?.awareness ?? null, [state])

  return {
    provider: state?.instance ?? null,
    doc: state?.doc ?? null,
    awareness,
    status,
    enabled: shouldEnable,
    synced,
    providerVersion, // Add version to help force updates
  }
}
