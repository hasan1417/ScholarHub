import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Sparkles } from 'lucide-react'
import { EditorAdapterHandle, EditorAdapterProps } from './adapters/EditorAdapter'
import BranchManager from './BranchManager'
import MergeView from './MergeView'
import VersionsModal from './VersionsModal'
import ChangesSidebar from './ChangesSidebar'
import { useAuth } from '../../contexts/AuthContext'
import { branchService } from '../../services/branchService'
import { researchPapersAPI, teamAPI } from '../../services/api'
import { fetchCollabToken } from '../../services/collabService'
import { isCollabEnabled } from '../../config/collab'
import { useCollabProvider } from '../../hooks/useCollabProvider'
import { useThemePreference } from '../../hooks/useThemePreference'
import EditorAIChatOR from './EditorAIChatOR'

type AdapterComponent = React.ForwardRefExoticComponent<EditorAdapterProps & React.RefAttributes<EditorAdapterHandle>>

interface DocumentShellProps {
  paperId: string
  projectId?: string
  paperTitle?: string
  initialContent?: string | any
  initialContentJson?: any
  Adapter: AdapterComponent
  fullBleed?: boolean
  onHostContentChange?: (html: string, json?: any) => void
  initialPaperRole?: 'admin' | 'editor' | 'viewer'
  forceReadOnly?: boolean
}

const DocumentShell: React.FC<DocumentShellProps> = ({ paperId, projectId, paperTitle, initialContent = '', initialContentJson, Adapter, fullBleed = false, onHostContentChange, initialPaperRole, forceReadOnly = false }) => {
  const navigate = useNavigate()
  const { user } = useAuth()
  const adapterRef = useRef<EditorAdapterHandle>(null)
  const { theme } = useThemePreference()
  const [branchOpen, setBranchOpen] = useState(false)
  const [mergeOpen, setMergeOpen] = useState(false)
  const [currentBranchId, setCurrentBranchId] = useState<string | undefined>(undefined)
  // One-mode workflow
  const [baselinePublished, setBaselinePublished] = useState<string>('')
  const [commitOpen, setCommitOpen] = useState(false)
  const [commitMessage, setCommitMessage] = useState('')
  const [outlineOpen, setOutlineOpen] = useState(false)
  const [sectionLocks, setSectionLocks] = useState<Record<string, { userName: string; expiresAt: string }>>({})
  const [lastHtml, setLastHtml] = useState('')
  const [toast, setToast] = useState<{ visible: boolean; text: string; type?: 'success' | 'error' }>({ visible: false, text: '' })
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [pendingVersion, setPendingVersion] = useState<string | null>(null)
  const [currentVersion, setCurrentVersion] = useState<string | null>(null)
  const fallbackRole: 'admin' | 'editor' | 'viewer' = forceReadOnly ? 'viewer' : (initialPaperRole ?? 'viewer')
  const [paperRole, setPaperRole] = useState<'admin' | 'editor' | 'viewer'>(fallbackRole)
  const [isPaperOwner, setIsPaperOwner] = useState(false)
  const [aiChatOpen, setAiChatOpen] = useState(false)
  const [aiChatInitialMessage, setAiChatInitialMessage] = useState<string | null>(null)
  const readOnly = forceReadOnly || paperRole === 'viewer'
  const collabFeatureEnabled = useMemo(() => isCollabEnabled(), [])
  const [collabToken, setCollabToken] = useState<{ token: string; ws_url?: string } | null>(null)
  const [collabPeers, setCollabPeers] = useState<Array<{ id: string; name: string; email: string; color?: string }>>([])
  const [collabStatusMessage, setCollabStatusMessage] = useState<string | null>(null)
  const [collabTokenVersion, setCollabTokenVersion] = useState(0)
  const [collabTimedOut, setCollabTimedOut] = useState(false) // Permanent flag for this paper load
  const collab = useCollabProvider({
    paperId,
    // Keep provider enabled even after timeout - let it try connecting in background
    // This keeps the Yjs doc alive so editor doesn't reinitialize and lose content
    enabled: !readOnly && Boolean(collabToken?.token),
    token: collabToken?.token ?? null,
    wsUrl: collabToken?.ws_url ?? null,
  })
  // collabEnabled determines if we're actively using collab for editing
  // When timed out, we stop blocking the UI but keep the doc for content preservation
  const collabEnabled = !!(collab.enabled && !readOnly && !collabTimedOut)
  const collabSynced = !!collab.synced
  const expectingCollab = collabFeatureEnabled && !readOnly
  const collabReady = collabEnabled && collabSynced
  const collabUnavailable = collabTimedOut || collabStatusMessage === 'Collaboration unavailable'
  const showToast = (text: string, type: 'success' | 'error' = 'success') => {
    setToast({ visible: true, text, type })
    setTimeout(() => setToast({ visible: false, text: '' }), type === 'error' ? 5000 : 3000)
  }
  const contentWrapRef = useRef<HTMLDivElement>(null)
  const [containerH, setContainerH] = useState<number>(600)
  const isLatex = Boolean(initialContentJson && typeof initialContentJson === 'object' && (initialContentJson as any).authoring_mode === 'latex')
  const initialLatexSource = useMemo(() => {
    if (!isLatex) return ''
    return typeof initialContentJson?.latex_source === 'string' ? initialContentJson?.latex_source : ''
  }, [initialContentJson, isLatex])
  const baseInitialHtml = useMemo(() => {
    if (isLatex) return initialLatexSource || ''
    return typeof initialContent === 'string' ? initialContent : ''
  }, [initialContent, initialLatexSource, isLatex])
  const latestContentRef = useRef<{ html: string; json: any }>({
    html: (expectingCollab && !collabUnavailable) ? '' : baseInitialHtml,
    json: (expectingCollab && !collabUnavailable) ? undefined : initialContentJson,
  })
  const initialSignature = useMemo(() => {
    if (initialContentJson && typeof initialContentJson === 'object' && initialContentJson.authoring_mode === 'latex') {
      return typeof initialContentJson.latex_source === 'string' ? initialContentJson.latex_source : baseInitialHtml
    }
    return baseInitialHtml
  }, [baseInitialHtml, initialContentJson])
  const persistedSignatureRef = useRef<string>((expectingCollab && !collabUnavailable) ? '' : initialSignature)
  const autosaveTimerRef = useRef<number | null>(null)
  const autosaveInFlightRef = useRef<boolean>(false)
  const autosavePendingReasonRef = useRef<string | null>(null)
  const deferredAutosaveReasonRef = useRef<string | null>(null)
  const awaitingRealtimeBootstrapRef = useRef<boolean>(false)
  const prevCollabEnabledRef = useRef<boolean>(false)

  const computeContentSignature = useCallback((html: string, json: any) => {
    if (json && typeof json === 'object' && json.authoring_mode === 'latex') {
      const latexSrc = json.latex_source
      return typeof latexSrc === 'string' ? latexSrc : (html || '')
    }
    return html || ''
  }, [])

  const updateLatestContent = useCallback((html: string, json?: any) => {
    latestContentRef.current = { html: html || '', json }
  }, [])

  const persistLatestContent = useCallback(async (reason: string) => {
    if (readOnly || !paperId) return
    const { html, json } = latestContentRef.current
    const signature = computeContentSignature(html, json)
    if (signature === persistedSignatureRef.current) {
      try { console.info('[DocumentShell] autosave skipped (no content change)', { paperId, reason }) } catch {}
      return
    }
    // Prevent concurrent saves
    if (autosaveInFlightRef.current) {
      autosavePendingReasonRef.current = reason
      try { console.info('[DocumentShell] autosave already in flight, queuing reason', { paperId, reason }) } catch {}
      return
    }

    autosaveInFlightRef.current = true
    try {
      try {
        console.info('[DocumentShell] autosave started', {
          paperId,
          reason,
          htmlLength: html?.length ?? 0,
          hasJson: Boolean(json),
        })
      } catch {}
      const payload: any = {}
      if (json && typeof json === 'object' && json.authoring_mode === 'latex') {
        payload.content_json = json
      } else {
        payload.content = html || ''
        if (json) payload.content_json = json
      }
      await researchPapersAPI.updatePaperContent(paperId, payload)
      persistedSignatureRef.current = signature
      autosavePendingReasonRef.current = null
      console.info('[DocumentShell] Autosaved paper content', { paperId, reason, length: signature?.length ?? 0 })
    } catch (error) {
      console.warn('[DocumentShell] Autosave failed', { paperId, reason, error })
      // If save fails, allow retry on next change
    } finally {
      autosaveInFlightRef.current = false
      if (autosavePendingReasonRef.current) {
        const pendingReason = autosavePendingReasonRef.current
        autosavePendingReasonRef.current = null
        // schedule immediate retry
        window.setTimeout(() => {
          try { console.info('[DocumentShell] retrying queued autosave', { paperId, reason: pendingReason }) } catch {}
          persistLatestContent(pendingReason)
        }, 300)
      }
    }
  }, [computeContentSignature, paperId, readOnly])

  const scheduleAutosave = useCallback((reason: string) => {
    if (readOnly || !paperId) return
    if (autosaveTimerRef.current) {
      try { console.info('[DocumentShell] autosave timer cleared', { paperId, previousReason: reason }) } catch {}
      window.clearTimeout(autosaveTimerRef.current)
      autosaveTimerRef.current = null
    }
    autosaveTimerRef.current = window.setTimeout(() => {
      autosaveTimerRef.current = null
      try { console.info('[DocumentShell] autosave timer fired', { paperId, reason }) } catch {}
      void persistLatestContent(reason)
    }, collabEnabled ? 1200 : 800)
    try { console.info('[DocumentShell] autosave scheduled', { paperId, reason, delayMs: collabEnabled ? 1200 : 800 }) } catch {}
  }, [paperId, readOnly, persistLatestContent, collabEnabled])
  const requestAutosave = useCallback((reason: string) => {
    if (readOnly || !paperId) return
    if (!expectingCollab || collabReady || collabUnavailable) {
      try {
        console.info('[DocumentShell] autosave requested immediately', {
          paperId,
          reason,
          collabEnabled,
          collabSynced,
          collabUnavailable,
          expectingCollab,
        })
      } catch {}
      scheduleAutosave(reason)
    } else {
      deferredAutosaveReasonRef.current = reason
      try { console.info('[DocumentShell] autosave deferred until sync', { paperId, reason }) } catch {}
    }
  }, [collabEnabled, collabSynced, collabUnavailable, collabReady, expectingCollab, paperId, readOnly, scheduleAutosave])
  useEffect(() => {
    return () => {
      if (autosaveTimerRef.current) {
        window.clearTimeout(autosaveTimerRef.current)
        autosaveTimerRef.current = null
      }
      if (!readOnly && paperId) {
        void persistLatestContent('unmount')
      }
    }
  }, [paperId, persistLatestContent, readOnly])
  useEffect(() => {
    const wasEnabled = prevCollabEnabledRef.current
    if (wasEnabled && !collabEnabled && !readOnly) {
      void persistLatestContent('collab-disabled')
    }
    prevCollabEnabledRef.current = collabEnabled
  }, [collabEnabled, persistLatestContent, readOnly])
  useEffect(() => {
    if ((collabReady || collabUnavailable || !expectingCollab) && deferredAutosaveReasonRef.current && !readOnly) {
      const reason = deferredAutosaveReasonRef.current
      deferredAutosaveReasonRef.current = null
      try { console.info('[DocumentShell] flushing deferred autosave', { paperId, reason }) } catch {}
      scheduleAutosave(reason)
    }
  }, [collabReady, collabUnavailable, expectingCollab, readOnly, scheduleAutosave, paperId])
  // No global paper id; pass through props

  useEffect(() => {
    if (typeof window !== 'undefined') {
      console.info('[DocumentShell] collab state', {
        collabFeatureEnabled,
        readOnly,
        paperId,
        hasToken: Boolean(collabToken?.token),
      })
    }
  }, [collabFeatureEnabled, readOnly, paperId, collabToken?.token])

  useEffect(() => {
    const calc = () => {
      try {
        const top = contentWrapRef.current?.getBoundingClientRect().top || 0
        const vh = window.innerHeight || 800
        const h = Math.max(360, vh - top - 12)
        setContainerH(h)
      } catch {}
    }
    calc()
    window.addEventListener('resize', calc)
    return () => window.removeEventListener('resize', calc)
  }, [])

  // Branchless workflow: no-op placeholder to keep state consistent
  useEffect(() => {
    setCurrentBranchId(undefined)
  }, [paperId])

  const collabBootstrappedRef = useRef(false)

  // Reset timeout flag when paper changes
  useEffect(() => {
    setCollabTimedOut(false)
  }, [paperId])

  // Master timeout: if collaboration doesn't become ready within 4 seconds, give up permanently
  // Keep short to avoid flickering - users shouldn't wait long when server is down
  useEffect(() => {
    // Don't set timeout if we've already timed out or collab is ready
    if (collabTimedOut || collabReady || !expectingCollab) {
      return
    }

    const timeout = setTimeout(() => {
      console.warn('[DocumentShell] Master collab timeout - giving up on collaboration')
      setCollabTimedOut(true)
    }, 4000)

    return () => clearTimeout(timeout)
  }, [expectingCollab, collabReady, collabTimedOut])

  useEffect(() => {
    collabBootstrappedRef.current = false
    awaitingRealtimeBootstrapRef.current = expectingCollab && !collabUnavailable
  }, [paperId, collab.doc, expectingCollab, collabUnavailable])

  useEffect(() => {
    if (!collabFeatureEnabled || readOnly || !paperId) {
      setCollabToken(null)
      setCollabStatusMessage(null)
      return
    }

    const controller = new AbortController()
    let isMounted = true

    const loadToken = async () => {
      try {
        const data = await fetchCollabToken(paperId, controller.signal)
        if (!isMounted) return
        setCollabToken({ token: data.token, ws_url: data.ws_url })
        // Don't clear unavailable status if master timeout already fired
        setCollabStatusMessage(prev => prev === 'Collaboration unavailable' ? prev : null)
      } catch (error: any) {
        if (controller.signal.aborted || !isMounted) return
        console.warn('[DocumentShell] failed to fetch collab token', error)
        setCollabToken(null)
        setCollabStatusMessage('Collaboration unavailable')
      }
    }

    loadToken()

    return () => {
      isMounted = false
      controller.abort()
    }
  }, [collabFeatureEnabled, paperId, readOnly, collabTokenVersion])

  useEffect(() => {
    let cancelled = false

    const loadRole = async () => {
      if (forceReadOnly) {
        setPaperRole('viewer')
        return
      }
      if (!paperId) {
        setPaperRole(fallbackRole)
        return
      }
      try {
        const response = await teamAPI.getTeamMembers(paperId)
        const members = Array.isArray(response.data) ? response.data : []
        const match = members.find((member: any) => member.user_id === user?.id)
        if (!match) {
          if (!cancelled) {
            setPaperRole(fallbackRole)
          }
          return
        }
        const rawRole = (match?.role || 'viewer').toLowerCase()
        const normalized = rawRole === 'reviewer'
          ? 'viewer'
          : rawRole === 'owner'
            ? 'admin'
            : (rawRole as 'admin' | 'editor' | 'viewer')
        if (!cancelled) {
          setPaperRole(normalized || fallbackRole)
          setIsPaperOwner(rawRole === 'owner' || rawRole === 'admin')
        }
      } catch (err) {
        if (!cancelled) {
          setPaperRole(prev => prev || fallbackRole)
        }
      }
    }

    loadRole()

    return () => {
      cancelled = true
    }
  }, [paperId, user?.id, fallbackRole, forceReadOnly])

  useEffect(() => {
    setPaperRole(forceReadOnly ? 'viewer' : fallbackRole)
  }, [fallbackRole, forceReadOnly, paperId])

  useEffect(() => {
    const awareness = collab.awareness
    if (!awareness || !collabEnabled) {
      setCollabPeers([])
      return
    }

    const updatePeers = () => {
      const next: Array<{ id: string; name: string; email: string; color?: string }> = []
      awareness.getStates().forEach((state: any, clientId: number) => {
        if (clientId === awareness.clientID) return
        const userState = state?.user || {}
        next.push({
          id: userState.id ?? String(clientId),
          name: userState.name ?? userState.email ?? 'Collaborator',
          email: userState.email ?? userState.name ?? 'collaborator@local',
          color: userState.color ?? '#3B82F6',
        })
      })
      setCollabPeers(next)
    }

    updatePeers()
    awareness.on('update', updatePeers)

    return () => {
      awareness.off('update', updatePeers)
    }
  }, [collab.awareness, collabEnabled])

  useEffect(() => {
    if (!collab.awareness || !collabEnabled) return

    const displayName = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email || 'You'

    try {
      collab.awareness.setLocalStateField('user', {
        id: user?.id ?? 'current-user',
        name: displayName,
        email: user?.email || 'you@local',
        color: '#3B82F6',
      })
    } catch (error) {
      console.warn('[DocumentShell] failed to set local collaboration state', error)
    }

    return () => {
      try {
        collab.awareness?.setLocalStateField('user', null)
      } catch {}
    }
  }, [collab.awareness, collabEnabled, user?.email, user?.first_name, user?.last_name, user?.id])

  // Handle persistent disconnections with a debounce to avoid reconnection loops
  const disconnectTimerRef = useRef<number | null>(null)
  useEffect(() => {
    if (!collabFeatureEnabled || readOnly) return

    // Clear any pending disconnect timer when status changes
    if (disconnectTimerRef.current) {
      window.clearTimeout(disconnectTimerRef.current)
      disconnectTimerRef.current = null
    }

    if (collab.status === 'disconnected' && collabToken) {
      // Wait 3 seconds before treating as a persistent disconnection
      // This prevents reconnection loops from brief WebSocket hiccups
      disconnectTimerRef.current = window.setTimeout(() => {
        console.info('[DocumentShell] Persistent disconnection detected, refreshing token')
        setCollabToken(null)
        setCollabTokenVersion(v => v + 1)
      }, 3000)
    }

    return () => {
      if (disconnectTimerRef.current) {
        window.clearTimeout(disconnectTimerRef.current)
        disconnectTimerRef.current = null
      }
    }
  }, [collab.status, collabFeatureEnabled, readOnly, collabToken])

  useEffect(() => {
    if (!collabEnabled || !collab.doc || !collabSynced) return
    if (collabBootstrappedRef.current) return

    // Mark as bootstrapped immediately to prevent re-entry
    collabBootstrappedRef.current = true

    // NOTE: Document seeding is handled by the Hocuspocus server in onLoadDocument.
    // The client should NOT seed - just wait for the server to provide content.
    const yText = collab.doc.getText('main')
    console.info('[DocumentShell] Collab synced, content from server:', {
      paperId,
      realtimeLength: yText.length,
    })
  }, [collabEnabled, collab.doc, collabSynced, paperId])

  useEffect(() => {
    if (!collabFeatureEnabled || readOnly) return
    if (collab.status === 'connected') {
      setCollabStatusMessage(prev => (prev === 'Collaboration unavailable' ? prev : null))
    } else if (collab.status === 'disconnected') {
      // Don't overwrite 'unavailable' with 'offline'
      setCollabStatusMessage(prev => (prev === 'Collaboration unavailable' ? prev : 'Collaboration offline'))
    } else if (collab.status === 'timeout') {
      setCollabStatusMessage('Collaboration unavailable')
    } else if (collab.status === 'connecting') {
      setCollabStatusMessage(prev => (prev === 'Collaboration unavailable' ? prev : null))
    }
  }, [collab.status, collabFeatureEnabled, readOnly])

  // Removed mode-based content injection in one-mode workflow

  const realtimeContext = useMemo(() => {
    // Keep passing realtime context even when timed out, as long as doc exists
    // This prevents editor from reinitializing and losing content
    if (!collab.doc) return undefined
    // If not enabled (including timeout), don't pass realtime - let editor use its own content
    if (!collabEnabled && !collabTimedOut) return undefined
    return {
      doc: collab.doc,
      awareness: collabTimedOut ? null : (collab.awareness ?? null),
      provider: collabTimedOut ? null : (collab.provider ?? null),
      status: collabTimedOut ? 'timeout' : collab.status,
      peers: collabTimedOut ? [] : collabPeers,
      version: collab.providerVersion ?? 0,
      synced: collabTimedOut ? true : collabSynced, // Mark as synced when timed out so editor proceeds
      enabled: !collabTimedOut,
    }
  }, [collab.awareness, collab.doc, collabEnabled, collab.status, collab.providerVersion, collabPeers, collabSynced, collabTimedOut])

  const handleContentChange = (html: string, json?: any) => {
    if (expectingCollab && !collabUnavailable && !collabReady) {
      console.info('[DocumentShell] Ignoring content change before collab sync', {
        paperId,
        htmlLength: html?.length || 0,
      })
      return
    }
    if (expectingCollab && !collabUnavailable && awaitingRealtimeBootstrapRef.current) {
      awaitingRealtimeBootstrapRef.current = false
      const signature = computeContentSignature(html || '', json)
      persistedSignatureRef.current = signature
      updateLatestContent(html || '', json)
      setLastHtml(html || '')
      console.info('[DocumentShell] Captured realtime bootstrap content', {
        paperId,
        length: signature.length,
      })
      return
    }
    console.log('[DocumentShell] 🔄 handleContentChange called:', {
      htmlLength: html?.length || 0,
      hasJson: Boolean(json),
      isLatex,
      latexSourceLength: json?.latex_source?.length || 0,
      paperId,
      timestamp: new Date().toISOString()
    })
    
    // Hook for autosave or collaboration in later milestones
    ;(window as any).__SH_LAST_HTML = html
    ;(window as any).__SH_LAST_JSON = json
    updateLatestContent(html || '', json)
    requestAutosave('content-change')
    try { setLastHtml(html || '') } catch {}
    // Compute hasChanges vs baseline
    try { onHostContentChange?.(html, json) } catch {}
  }

  const refreshVersions = useCallback(async () => {
    try {
      const pv = await researchPapersAPI.getPaperVersions(paperId)
      const pvData = pv?.data as { versions?: any[]; current_version?: string | null } | undefined
      const list = (pvData?.versions || []) as Array<Record<string, any>>
      const current = pvData?.current_version || (list[0]?.version_number ?? null)
      setCurrentVersion(current || null)
      const currentEntry = current ? list.find((v: any) => v.version_number === current) : null
      const baselineSource = currentEntry
        ? ((currentEntry.content_json && currentEntry.content_json.latex_source)
            ? currentEntry.content_json.latex_source
            : (currentEntry.content || ''))
        : ''
      setBaselinePublished(baselineSource || '')
      const latest = list[0]
      if (latest && latest.version_number && latest.version_number !== current) {
        setPendingVersion(latest.version_number)
      } else {
        setPendingVersion(null)
      }
    } catch (e) {
      console.warn('Failed to refresh versions', e)
    }
  }, [paperId])

  // Load initial content once from the server (fallback for non-realtime or pre-CRDT bootstrap)
  useEffect(() => {
    if (!paperId) return

    let mounted = true
    const hydrateFromServer = async () => {
      try {
        const resp = await researchPapersAPI.getPaper(paperId)
        const data: any = resp.data || {}
        const isLatexMode = Boolean(
          data?.content_json &&
          typeof data.content_json === 'object' &&
          data.content_json.authoring_mode === 'latex'
        )
        const latexSource: string = isLatexMode ? (data.content_json?.latex_source || '') : ''
        const richHtml: string = !isLatexMode ? (data.content || '') : ''
        if (!mounted) return

        const working = isLatexMode ? (latexSource || '') : (richHtml || '')
        const realtimeActive = collabEnabled && collab.doc
        const realtimeSynced = realtimeActive && collabSynced
        const realtimeDoc = realtimeSynced && collab.doc ? collab.doc.getText('main') : null
        const hasRealtimeContent = Boolean(realtimeDoc && realtimeDoc.length > 0)
        const resolvedContent = hasRealtimeContent ? realtimeDoc!.toString() : working

        const serverJson = isLatexMode ? (data.content_json || { authoring_mode: 'latex', latex_source: working }) : data.content_json
        const latestJson = isLatexMode
          ? { ...(serverJson || {}), authoring_mode: 'latex', latex_source: resolvedContent }
          : serverJson
        const serverSignature = computeContentSignature(working, serverJson)
        const resolvedSignature = computeContentSignature(resolvedContent, latestJson)

        if (!expectingCollab || collabUnavailable) {
          setLastHtml(resolvedContent)
          updateLatestContent(resolvedContent, latestJson)
          persistedSignatureRef.current = serverSignature
          if (!readOnly && resolvedSignature !== serverSignature) {
            requestAutosave('post-sync-reconcile')
          }
          console.info('[DocumentShell] Hydrating adapter content (realtime disabled for this session)', {
            paperId,
            mode: isLatex ? 'latex' : 'rich',
          })
          await adapterRef.current?.setContent?.(working)
        } else {
          console.info('[DocumentShell] Skipping local content hydrate until realtime bootstrap', {
            paperId,
            mode: isLatex ? 'latex' : 'rich',
            serverLength: working.length,
          })
          updateLatestContent('', null)
          setLastHtml('')
          persistedSignatureRef.current = serverSignature
        }

        if (expectingCollab && !collabUnavailable) {
          if (!realtimeSynced) {
            console.info('[DocumentShell] Waiting for realtime sync before hydrating adapter', {
              paperId,
              mode: isLatex ? 'latex' : 'rich',
            })
          } else if (!hasRealtimeContent) {
            console.info('[DocumentShell] Realtime synced but doc empty; deferring to realtime bootstrap', {
              paperId,
            })
          } else {
            console.info('[DocumentShell] Using realtime doc content post-sync; no adapter hydrate needed', {
              paperId,
              realtimeLength: realtimeDoc?.length ?? 0,
            })
          }
        }

        await refreshVersions()
      } catch (e) {
        console.warn('Failed to load paper content for shell', e)
      }
    }

    hydrateFromServer()

    return () => {
      mounted = false
    }
  }, [paperId, collabEnabled, collab.doc, collabSynced, refreshVersions, isLatex, computeContentSignature, updateLatestContent, readOnly, expectingCollab, collabUnavailable, requestAutosave])

  const handleNavigateBack = useCallback(() => {
    navigate(projectId ? `/projects/${projectId}/papers/${paperId}` : '/projects')
  }, [navigate, projectId, paperId])

  const handleOpenReferences = useCallback(() => {
    /* references sidebar disabled */
  }, [])

  const handleInsertBibliographyShortcut = useCallback(() => {
    if (readOnly) return
    const snippet = '\n\\bibliographystyle{plain}\n\\bibliography{references}\n'
    adapterRef.current?.insertText(snippet)
  }, [readOnly])

  // Open AI chat with a pre-filled message (from Sparkles explain/summarize)
  const handleOpenAiChatWithMessage = useCallback((message: string) => {
    setAiChatInitialMessage(message)
    setAiChatOpen(true)
  }, [])

  /** Handle AI edit approval - replace lines by line numbers (root cause fix) */
  const handleApplyAiEdit = useCallback((startLine: number, endLine: number, anchor: string, replacement: string, sourceDocument?: string): boolean => {
    if (readOnly) return false

    // Get current content from the adapter directly for most accurate state
    const currentContent = adapterRef.current?.getContent?.() || latestContentRef.current.html || ''

    // Staleness check: reject if document changed since the AI generated this edit
    if (sourceDocument) {
      const normalize = (s: string) => s.replace(/\s+$/, '')
      if (normalize(currentContent) !== normalize(sourceDocument)) {
        showToast('Edits are stale: document changed. Please regenerate.', 'error')
        return false
      }
    }

    console.log('[DocumentShell] Applying AI edit (line-based):', {
      startLine,
      endLine,
      anchor: anchor.slice(0, 50),
      replacementLen: replacement.length,
      contentLen: currentContent.length,
    })

    // Split content into lines (1-indexed in UI, 0-indexed in array)
    const lines = currentContent.split('\n')
    const totalLines = lines.length

    // Validate line numbers
    if (startLine < 1 || endLine < startLine || startLine > totalLines) {
      console.warn('[DocumentShell] Invalid line range:', {
        startLine,
        endLine,
        totalLines,
      })
      return false
    }

    // Convert to 0-indexed
    const startIdx = startLine - 1
    const endIdx = Math.min(endLine - 1, totalLines - 1)

    // Verify anchor matches (required safety check - prevents corrupting wrong lines)
    if (anchor && anchor.trim()) {
      const actualLineStart = lines[startIdx] || ''
      const normalizedAnchor = anchor.trim().slice(0, 40).toLowerCase()
      const normalizedActual = actualLineStart.trim().slice(0, 40).toLowerCase()

      // Log for debugging
      console.log('[DocumentShell] Anchor verification:', {
        line: startLine,
        expectedAnchor: normalizedAnchor,
        actualContent: normalizedActual,
        actualLineRaw: actualLineStart.slice(0, 60),
      })

      // Check if anchor matches - require significant overlap
      const substringMatch =
        normalizedActual.includes(normalizedAnchor.slice(0, 15)) ||
        normalizedAnchor.includes(normalizedActual.slice(0, 15))

      const wordMatch = normalizedAnchor.split(/\s+/).filter(w => w.length > 2).slice(0, 3)
        .every((word) => normalizedActual.includes(word))

      const anchorMatches = substringMatch || wordMatch

      console.log('[DocumentShell] Anchor match result:', {
        substringMatch,
        wordMatch,
        anchorMatches,
      })

      if (!anchorMatches) {
        console.error('[DocumentShell] Anchor mismatch - edit REJECTED to prevent document corruption:', {
          line: startLine,
          expectedAnchor: normalizedAnchor,
          actualContent: normalizedActual,
        })
        showToast(`Edit rejected: document changed at line ${startLine}. Please regenerate.`, 'error')
        return false
      }
    } else {
      console.warn('[DocumentShell] No anchor provided - skipping verification')
    }

    // Apply the edit by replacing lines
    const before = lines.slice(0, startIdx)
    const after = lines.slice(endIdx + 1)
    const newLines = [...before, replacement, ...after]
    const newContent = newLines.join('\n')

    // Check if content actually changed
    if (newContent === currentContent) {
      console.warn('[DocumentShell] No change after line replacement')
      return false
    }

    console.log('[DocumentShell] Line edit applied:', {
      removedLines: endIdx - startIdx + 1,
      beforeLen: currentContent.length,
      afterLen: newContent.length,
      diff: newContent.length - currentContent.length,
    })

    // Apply to editor
    adapterRef.current?.setContent?.(newContent, { overwriteRealtime: true })
    setLastHtml(newContent)
    const nextJson = isLatex
      ? { authoring_mode: 'latex', latex_source: newContent }
      : latestContentRef.current.json
    updateLatestContent(newContent, nextJson)
    requestAutosave('ai-edit-applied')
    return true
  }, [isLatex, readOnly, requestAutosave, showToast, updateLatestContent])

  type BatchEdit = {
    startLine: number
    endLine: number
    anchor: string
    proposed: string
  }

  const handleApplyAiEditsBatch = useCallback((proposals: BatchEdit[], sourceDocument: string): boolean => {
    if (readOnly) return false
    if (!sourceDocument) return false

    const currentContent = adapterRef.current?.getContent?.() || latestContentRef.current.html || ''
    // Normalize trailing whitespace before comparison — editor/collab can add/remove trailing newlines
    const normalize = (s: string) => s.replace(/\s+$/, '')
    if (normalize(currentContent) !== normalize(sourceDocument)) {
      showToast('Edits are stale: document changed. Please regenerate.', 'error')
      return false
    }

    // Apply edits against the sourceDocument snapshot (the version the AI saw)
    const lines = sourceDocument.split('\n')
    const totalLines = lines.length

    const sorted = [...proposals].sort((a, b) => {
      if (b.startLine !== a.startLine) return b.startLine - a.startLine
      return b.endLine - a.endLine
    })

    for (const proposal of sorted) {
      const { startLine, endLine, anchor, proposed } = proposal
      if (startLine < 1 || endLine < startLine || startLine > totalLines) {
        showToast(`Invalid edit range at line ${startLine}. Please regenerate.`, 'error')
        return false
      }

      const startIdx = startLine - 1
      const endIdx = Math.min(endLine - 1, totalLines - 1)

      if (anchor && anchor.trim()) {
        const actualLineStart = lines[startIdx] || ''
        const normalizedAnchor = anchor.trim().slice(0, 40).toLowerCase()
        const normalizedActual = actualLineStart.trim().slice(0, 40).toLowerCase()
        const substringMatch =
          normalizedActual.includes(normalizedAnchor.slice(0, 15)) ||
          normalizedAnchor.includes(normalizedActual.slice(0, 15))
        const wordMatch = normalizedAnchor.split(/\s+/).filter(w => w.length > 2).slice(0, 3)
          .every((word) => normalizedActual.includes(word))
        const anchorMatches = substringMatch || wordMatch

        if (!anchorMatches) {
          showToast(`Edit rejected: document changed at line ${startLine}. Please regenerate.`, 'error')
          return false
        }
      }

      const replacementLines = proposed.split('\n')
      lines.splice(startIdx, endIdx - startIdx + 1, ...replacementLines)
    }

    const newContent = lines.join('\n')
    if (newContent === currentContent) {
      showToast('No changes detected after applying edits.', 'error')
      return false
    }

    adapterRef.current?.setContent?.(newContent, { overwriteRealtime: true })
    setLastHtml(newContent)
    const nextJson = isLatex
      ? { authoring_mode: 'latex', latex_source: newContent }
      : latestContentRef.current.json
    updateLatestContent(newContent, nextJson)
    requestAutosave('ai-edit-applied-batch')
    return true
  }, [isLatex, readOnly, requestAutosave, showToast, updateLatestContent])

  const rootCls = fullBleed
    ? 'fixed inset-0 flex flex-col overflow-auto bg-slate-100 transition-colors duration-200 dark:bg-slate-900'
    : 'min-h-screen flex flex-col overflow-auto bg-slate-100 transition-colors duration-200 dark:bg-slate-900'

  const collaborationStatus = useMemo(() => {
    if (!collabFeatureEnabled || readOnly) return null
    if (collabStatusMessage) return collabStatusMessage
    switch (collab.status) {
      case 'connected':
        return 'Collaboration active'
      case 'connecting':
        return 'Connecting collaborators…'
      case 'disconnected':
        return 'Collaboration offline'
      case 'timeout':
        return 'Collaboration unavailable'
      case 'idle':
      default:
        return 'Collaboration idle'
    }
  }, [collab.status, collabStatusMessage, collabFeatureEnabled, readOnly])
  const showSyncOverlay = expectingCollab && !collabUnavailable && (!collabEnabled || !collabSynced)

  return (
    <div className={rootCls}>
      <div className="pointer-events-none absolute top-20 right-4 z-30 flex flex-col items-end gap-2">
        {toast?.visible && (
          <div className={`pointer-events-auto rounded-md border px-3 py-1 text-[11px] font-medium shadow ${
            toast.type === 'error'
              ? 'border-red-300 bg-red-100 text-red-800 dark:border-red-500/50 dark:bg-red-500/10 dark:text-red-200'
              : 'border-green-300 bg-green-100 text-green-800 dark:border-green-500/50 dark:bg-green-500/10 dark:text-green-200'
          }`}>
            {toast.text}
          </div>
        )}
        {pendingVersion && (
          <div className="pointer-events-auto flex items-center gap-3 rounded-md bg-white/80 px-2.5 py-1.5 shadow backdrop-blur dark:bg-slate-800/80 dark:text-slate-100">
            <button
              className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-700 hover:bg-amber-100"
              onClick={() => setVersionsOpen(true)}
            >
              Version {pendingVersion} ready — review versions
            </button>
          </div>
        )}
      </div>

      {!readOnly && !aiChatOpen && (
        <button
          onClick={() => setAiChatOpen(true)}
          className="fixed bottom-6 left-1/2 z-40 flex h-14 w-14 -translate-x-1/2 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-lg shadow-indigo-500/30 transition-all duration-300 hover:scale-110 hover:shadow-xl hover:shadow-indigo-500/40 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 active:scale-95 dark:shadow-indigo-500/20 dark:hover:shadow-indigo-500/30"
          title="AI Assistant"
        >
          <Sparkles className="h-6 w-6 animate-pulse" />
        </button>
      )}

      <div
        ref={contentWrapRef}
        className="flex-1 min-h-0 flex flex-col p-0"
        style={fullBleed ? { } : { height: containerH }}
      >
        <div className="relative flex-1">
          {showSyncOverlay && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-slate-100/95 text-slate-600 dark:bg-slate-900/95 dark:text-slate-300">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span className="text-xs font-medium uppercase tracking-wide">Syncing latest draft…</span>
            </div>
          )}
          <div className="h-full">
            <Adapter
              ref={adapterRef}
              content={initialContent || ''}
              contentJson={initialContentJson}
              paperId={paperId}
              projectId={projectId}
              paperTitle={paperTitle}
              onContentChange={handleContentChange}
              onSelectionChange={() => {}}
              className="h-full"
              lockedSectionKeys={Object.keys(sectionLocks)}
              readOnly={readOnly}
              onNavigateBack={handleNavigateBack}
              onOpenReferences={handleOpenReferences}
              onOpenAiChatWithMessage={handleOpenAiChatWithMessage}
              onInsertBibliographyShortcut={handleInsertBibliographyShortcut}
              realtime={realtimeContext}
              collaborationStatus={collaborationStatus}
              theme={theme}
            />
          </div>
        </div>
      </div>

      {branchOpen && (
        <div className="fixed inset-0 z-50 bg-black bg-opacity-30 flex items-center justify-center" onClick={() => setBranchOpen(false)}>
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-[800px] p-4" onClick={(e)=>e.stopPropagation()}>
            <BranchManager
              paperId={paperId}
              currentBranchId={currentBranchId}
              onBranchSwitch={async (_branchId) => { /* adapter will reload via onContentUpdate */ }}
              onContentUpdate={async (html) => {
                await adapterRef.current?.setContent?.(html, { overwriteRealtime: true })
                setLastHtml(html || '')
                const nextJson = isLatex ? { authoring_mode: 'latex', latex_source: html || '' } : null
                updateLatestContent(html || '', nextJson)
                requestAutosave('branch-update')
              }}
            />
          </div>
        </div>
      )}

      {outlineOpen && (
        <ChangesSidebar
          paperId={paperId}
          content={lastHtml}
          baseline={baselinePublished}
          onRevertAll={async () => {
            try {
              await adapterRef.current?.setContent?.(baselinePublished || '', { overwriteRealtime: true })
              setLastHtml(baselinePublished || '')
              const nextJson = isLatex ? { authoring_mode: 'latex', latex_source: baselinePublished || '' } : null
              updateLatestContent(baselinePublished || '', nextJson)
              requestAutosave('outline-revert')
            } catch {}
          }}
          lockedKeys={sectionLocks}
          onClose={()=> setOutlineOpen(false)}
          onJumpToLine={(line)=> adapterRef.current?.scrollToLine?.(line)}
          onReplaceLines={(from,to,text)=> adapterRef.current?.replaceLines?.(from,to,text)}
          onLockToggle={(key, lock)=> {
            setSectionLocks(prev => {
              const next = { ...prev }
              if (lock) {
                next[key] = { userName: user?.email || 'You', expiresAt: '' }
              } else {
                delete next[key]
              }
              return next
            })
          }}
        />
      )}

      {mergeOpen && (
        <div className="fixed inset-0 z-50 bg-black bg-opacity-30 flex items-center justify-center" onClick={() => setMergeOpen(false)}>
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-[900px] p-4" onClick={(e)=>e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <div className="text-base font-semibold">Merge</div>
              <button className="text-sm px-2 py-1 border rounded" onClick={() => setMergeOpen(false)}>Close</button>
            </div>
            <MergeView
              paperId={paperId}
              onMerged={async (merged) => {
                await adapterRef.current?.setContent?.(merged, { overwriteRealtime: true })
                setMergeOpen(false)
                const nextJson = isLatex ? { authoring_mode: 'latex', latex_source: merged || '' } : null
                updateLatestContent(merged || '', nextJson)
                requestAutosave('merge-accepted')
              }}
            />
          </div>
        </div>
      )}

      {commitOpen && (
        <div className="fixed inset-0 z-50 bg-black bg-opacity-30 flex items-center justify-center" onClick={() => setCommitOpen(false)}>
          <div className="bg-white rounded-lg shadow-xl w-[560px] p-5" onClick={(e)=>e.stopPropagation()}>
            <div className="text-lg font-semibold mb-2">Commit Changes</div>
            <div className="text-sm text-gray-600 mb-3">Current branch: <span className="font-mono">{currentBranchId || 'unknown'}</span></div>
            <textarea
              className="w-full border border-gray-300 rounded-md p-2 text-sm mb-3"
              rows={3}
              placeholder="Commit message"
              value={commitMessage}
              onChange={e => setCommitMessage(e.target.value)}
            />
            <div className="flex justify-end gap-2">
              <button className="px-3 py-1.5 border rounded-md" onClick={() => setCommitOpen(false)}>Cancel</button>
              <button
                className="px-3 py-1.5 rounded-md bg-blue-600 text-white"
                onClick={async () => {
                    try {
                    if (!currentBranchId) throw new Error('No branch selected')
                    let commitContent = lastHtml || ''
                    let commitContentJson: any = undefined
                    if (isLatex) {
                      commitContentJson = {
                        authoring_mode: 'latex',
                        latex_source: commitContent,
                      }
                    }
                    await branchService.commitChanges(currentBranchId, commitMessage || 'Update', commitContent, commitContentJson)
                    try {
                      await refreshVersions()
                    } catch (err) {
                      console.warn('[DocumentShell] failed to refresh versions after commit', err)
                    }
                    setCommitOpen(false)
                    setCommitMessage('')
                  } catch (e) { console.error('Commit failed', e) }
                }}
              >Commit</button>
            </div>
          </div>
        </div>
      )}

      <VersionsModal
        paperId={paperId}
        open={versionsOpen}
        currentVersion={currentVersion || undefined}
        pendingVersion={pendingVersion || undefined}
        onClose={() => setVersionsOpen(false)}
        onLoadVersion={async (content) => {
          try {
            await adapterRef.current?.setContent?.(content, { overwriteRealtime: true })
            setLastHtml(content || '')
            const nextJson = isLatex ? { authoring_mode: 'latex', latex_source: content || '' } : null
            updateLatestContent(content || '', nextJson)
            requestAutosave('load-version')
          } catch {}
        }}
        onPromote={async () => {
          await refreshVersions()
          showToast('Default version updated')
        }}
      />

      {/* AI Chat with multi-model support via OpenRouter */}
      <EditorAIChatOR
        paperId={paperId}
        projectId={projectId}
        documentText={lastHtml}
        open={!readOnly && aiChatOpen}
        onOpenChange={(next) => setAiChatOpen(readOnly ? false : next)}
        onApplyEdit={handleApplyAiEdit}
        onApplyEditsBatch={handleApplyAiEditsBatch}
        initialMessage={aiChatInitialMessage || undefined}
        onInitialMessageConsumed={() => setAiChatInitialMessage(null)}
        isOwner={isPaperOwner}
      />
    </div>
  )
}

export default DocumentShell
