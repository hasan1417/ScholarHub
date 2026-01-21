import { useEffect, useMemo, useState, useRef } from 'react'
import { HocuspocusProvider } from '@hocuspocus/provider'
import * as Y from 'yjs'
import { collabConfig, isCollabEnabled } from '../config/collab'

// Safari detection - Safari has WebSocket reconnection timing issues
const isSafari = typeof navigator !== 'undefined' &&
  /^((?!chrome|android).)*safari/i.test(navigator.userAgent)

// Log browser detection on load
if (typeof navigator !== 'undefined') {
  console.info('[useCollabProvider] Browser detection:', {
    isSafari,
    userAgent: navigator.userAgent,
  })
}

interface UseCollabProviderArgs {
  paperId?: string
  enabled?: boolean
  token?: string | null
  wsUrl?: string | null
}

// Connection timeout in ms - if collab doesn't connect within this time, fall back to offline mode
// Keep this short to avoid long waits when server is down
const CONNECTION_TIMEOUT_MS = 3000

export function useCollabProvider({ paperId, enabled, token, wsUrl }: UseCollabProviderArgs) {
  const featureEnabled = isCollabEnabled()
  const shouldEnable = featureEnabled && enabled && Boolean(paperId) && Boolean(token)
  const [status, setStatus] = useState<'idle' | 'connecting' | 'connected' | 'disconnected' | 'timeout'>('idle')
  const [state, setState] = useState<{ instance: HocuspocusProvider; doc: Y.Doc } | null>(null)
  const [providerVersion, setProviderVersion] = useState(0)
  const [synced, setSynced] = useState(false)
  const safariSyncCheckRef = useRef<NodeJS.Timeout | null>(null)
  const connectionTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    if (!shouldEnable || !paperId || !token) {
      setStatus('idle')
      setSynced(false)
      if (safariSyncCheckRef.current) {
        clearTimeout(safariSyncCheckRef.current)
        safariSyncCheckRef.current = null
      }
      if (connectionTimeoutRef.current) {
        clearTimeout(connectionTimeoutRef.current)
        connectionTimeoutRef.current = null
      }
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

    // Set connection timeout - if we don't sync within this time, allow offline editing
    connectionTimeoutRef.current = setTimeout(() => {
      console.warn('[useCollabProvider] Connection timeout - collaboration server may be unavailable')
      setStatus('timeout')
      setSynced(true) // Allow editing without collab
      setProviderVersion(v => v + 1)
    }, CONNECTION_TIMEOUT_MS)

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
      // Clear connection timeout - we successfully synced
      if (connectionTimeoutRef.current) {
        clearTimeout(connectionTimeoutRef.current)
        connectionTimeoutRef.current = null
      }

      const yText = doc.getText('main')
      const textLength = yText.length

      console.info('[useCollabProvider] handleSynced called:', {
        isSafari,
        textLength,
        willPoll: isSafari && textLength === 0,
      })

      // Safari-specific: Sometimes synced fires before content is actually received
      // Check if we have content, if not wait a bit and check again
      if (isSafari && textLength === 0) {
        console.info('[useCollabProvider] Safari: synced but empty, waiting for content...')

        // Clear any existing check
        if (safariSyncCheckRef.current) {
          clearTimeout(safariSyncCheckRef.current)
        }

        // Poll for content arrival (Safari timing issue workaround)
        let attempts = 0
        const maxAttempts = 10
        const checkContent = () => {
          attempts++
          const currentLength = doc.getText('main').length
          console.info(`[useCollabProvider] Safari content check #${attempts}: length=${currentLength}`)

          if (currentLength > 0) {
            console.info('[useCollabProvider] Safari: content received, marking synced')
            setStatus('connected')
            setSynced(true)
            setProviderVersion(v => v + 1)
          } else if (attempts < maxAttempts) {
            // Check again in 200ms
            safariSyncCheckRef.current = setTimeout(checkContent, 200)
          } else {
            // Give up and mark synced anyway (might be genuinely empty doc)
            console.info('[useCollabProvider] Safari: max attempts reached, marking synced')
            setStatus('connected')
            setSynced(true)
            setProviderVersion(v => v + 1)
          }
        }

        // Start checking after a short delay
        safariSyncCheckRef.current = setTimeout(checkContent, 100)
        return
      }

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
      if (safariSyncCheckRef.current) {
        clearTimeout(safariSyncCheckRef.current)
        safariSyncCheckRef.current = null
      }
      if (connectionTimeoutRef.current) {
        clearTimeout(connectionTimeoutRef.current)
        connectionTimeoutRef.current = null
      }
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
