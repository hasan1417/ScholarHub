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
import { researchPapersAPI, teamAPI, buildApiUrl, buildAuthHeaders } from '../../services/api'
import { EditProposal, parseEditProposals } from './utils/editProposals'
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
  // AI chat column width — persisted to localStorage so the user's choice
  // survives reloads. Clamped to [320, 800] so the editor+PDF always have
  // enough room to be useful.
  const AI_CHAT_WIDTH_MIN = 320
  const AI_CHAT_WIDTH_MAX = 800
  const AI_CHAT_WIDTH_DEFAULT = 400
  const [aiChatWidth, setAiChatWidth] = useState<number>(() => {
    if (typeof window === 'undefined') return AI_CHAT_WIDTH_DEFAULT
    const stored = Number(localStorage.getItem('sh:aiChatWidth'))
    if (Number.isFinite(stored) && stored >= AI_CHAT_WIDTH_MIN && stored <= AI_CHAT_WIDTH_MAX) {
      return stored
    }
    return AI_CHAT_WIDTH_DEFAULT
  })
  const [aiChatDragging, setAiChatDragging] = useState(false)

  const handleAiChatDragStart = useCallback((e: React.MouseEvent | React.PointerEvent) => {
    e.preventDefault()
    const startX = e.clientX
    const startWidth = aiChatWidth
    setAiChatDragging(true)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    const handleMove = (ev: PointerEvent) => {
      const delta = startX - ev.clientX
      const next = Math.max(
        AI_CHAT_WIDTH_MIN,
        Math.min(AI_CHAT_WIDTH_MAX, startWidth + delta),
      )
      setAiChatWidth(next)
    }
    const handleUp = () => {
      setAiChatDragging(false)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      window.removeEventListener('pointermove', handleMove)
      window.removeEventListener('pointerup', handleUp)
      window.removeEventListener('pointercancel', handleUp)
    }
    // Use pointer events so capture works over iframes too. Without this, the
    // PDF iframe swallows mousemove/mouseup as soon as the cursor enters it,
    // making the drag "stick" or reset to the original width.
    window.addEventListener('pointermove', handleMove)
    window.addEventListener('pointerup', handleUp)
    window.addEventListener('pointercancel', handleUp)
  }, [aiChatWidth])

  // Persist width on every commit (in case drag ends via keyboard or edge case)
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      localStorage.setItem('sh:aiChatWidth', String(aiChatWidth))
    } catch {}
  }, [aiChatWidth])
  const [fixLoading, setFixLoading] = useState(false)
  const [fixProposals, setFixProposals] = useState<EditProposal[]>([])
  const fixSourceSnapshotRef = useRef<string>('')
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
  const isLatex = true
  const initialLatexSource = useMemo(() => {
    return typeof initialContentJson?.latex_source === 'string' ? initialContentJson?.latex_source : ''
  }, [initialContentJson])
  const baseInitialHtml = useMemo(() => {
    return initialLatexSource || ''
  }, [initialLatexSource])
  const latestContentRef = useRef<{ html: string; json: any }>({
    html: (expectingCollab && !collabUnavailable) ? '' : baseInitialHtml,
    json: (expectingCollab && !collabUnavailable) ? undefined : initialContentJson,
  })
  const initialSignature = useMemo(() => {
    return typeof initialContentJson?.latex_source === 'string' ? initialContentJson.latex_source : baseInitialHtml
  }, [baseInitialHtml, initialContentJson])
  const persistedSignatureRef = useRef<string>((expectingCollab && !collabUnavailable) ? '' : initialSignature)
  const autosaveTimerRef = useRef<number | null>(null)
  const autosaveInFlightRef = useRef<boolean>(false)
  const autosavePendingReasonRef = useRef<string | null>(null)
  const deferredAutosaveReasonRef = useRef<string | null>(null)
  const awaitingRealtimeBootstrapRef = useRef<boolean>(false)
  const prevCollabEnabledRef = useRef<boolean>(false)

  const computeContentSignature = useCallback((html: string, json: any) => {
    const latexSrc = json?.latex_source
    return typeof latexSrc === 'string' ? latexSrc : (html || '')
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
      const payload: any = { content_json: json }
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
      paperRole,
    }
  }, [collab.awareness, collab.doc, collabEnabled, collab.status, collab.providerVersion, collabPeers, collabSynced, collabTimedOut, paperRole])

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
        const latexSource: string = data.content_json?.latex_source || ''
        if (!mounted) return

        const working = latexSource
        const realtimeActive = collabEnabled && collab.doc
        const realtimeSynced = realtimeActive && collabSynced
        const realtimeDoc = realtimeSynced && collab.doc ? collab.doc.getText('main') : null
        const hasRealtimeContent = Boolean(realtimeDoc && realtimeDoc.length > 0)
        const resolvedContent = hasRealtimeContent ? realtimeDoc!.toString() : working

        const serverJson = data.content_json || { authoring_mode: 'latex', latex_source: working }
        const latestJson = { ...(serverJson || {}), authoring_mode: 'latex', latex_source: resolvedContent }
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
            mode: 'latex',
          })
          await adapterRef.current?.setContent?.(working)
        } else {
          console.info('[DocumentShell] Skipping local content hydrate until realtime bootstrap', {
            paperId,
            mode: 'latex',
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
              mode: 'latex',
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
  // Resolve an AI edit's target location in the current document by matching
  // the anchor. Line numbers are treated as a HINT for where to start searching,
  // not as authoritative coordinates. This is the root-cause fix for line-drift
  // corruption: the anchor (a fingerprint of the starting line) is the real
  // locator — we search for it starting from the hinted line and expanding
  // outward. Returns null if no confident match is found.
  const resolveEditLocation = useCallback((
    lines: string[],
    hintStartLine: number,
    hintEndLine: number,
    anchor: string,
  ): { startIdx: number; endIdx: number } | null => {
    const totalLines = lines.length
    if (totalLines === 0) return null
    if (hintEndLine < hintStartLine) return null

    const lineSpan = hintEndLine - hintStartLine
    const normalizedAnchor = (anchor || '').trim().slice(0, 40).toLowerCase()

    // Anchor-less edits: trust line numbers exactly (legacy behavior).
    if (!normalizedAnchor) {
      if (hintStartLine < 1 || hintStartLine > totalLines) return null
      const startIdx = hintStartLine - 1
      return { startIdx, endIdx: Math.min(hintEndLine - 1, totalLines - 1) }
    }

    const matchesLine = (idx: number): boolean => {
      if (idx < 0 || idx >= totalLines) return false
      const line = (lines[idx] || '').trim().slice(0, 40).toLowerCase()
      if (!line) return false
      // Strong match: substring overlap of the first 15 chars either direction
      if (line.includes(normalizedAnchor.slice(0, 15))) return true
      if (normalizedAnchor.includes(line.slice(0, 15))) return true
      // Weaker match: 3 significant words all present (safety net for
      // whitespace/punctuation drift)
      const words = normalizedAnchor.split(/\s+/).filter(w => w.length > 2).slice(0, 3)
      if (words.length >= 2 && words.every(w => line.includes(w))) return true
      return false
    }

    // Try the hinted start first — fast path when AI line numbers are correct
    const hintIdx = hintStartLine - 1
    if (hintIdx >= 0 && hintIdx < totalLines && matchesLine(hintIdx)) {
      return { startIdx: hintIdx, endIdx: Math.min(hintIdx + lineSpan, totalLines - 1) }
    }

    // Search expanding outward from the hint (±20 lines)
    const searchRadius = 20
    for (let offset = 1; offset <= searchRadius; offset++) {
      const down = hintIdx + offset
      if (down < totalLines && matchesLine(down)) {
        return { startIdx: down, endIdx: Math.min(down + lineSpan, totalLines - 1) }
      }
      const up = hintIdx - offset
      if (up >= 0 && matchesLine(up)) {
        return { startIdx: up, endIdx: Math.min(up + lineSpan, totalLines - 1) }
      }
    }

    return null
  }, [])

  const handleApplyAiEdit = useCallback((startLine: number, endLine: number, anchor: string, replacement: string, _sourceDocument?: string, file?: string): boolean => {
    if (readOnly) return false

    // Multi-file edit: apply to a different file via Yjs
    if (file && file !== 'main.tex' && collab.doc) {
      const yText = collab.doc.getText(`file:${file}`)
      if (!yText || yText.length === 0) {
        showToast(`File ${file} not found`, 'error')
        return false
      }
      const fileContent = yText.toString()
      const lines = fileContent.split('\n')

      const loc = resolveEditLocation(lines, startLine, endLine, anchor)
      if (!loc) {
        showToast(`Edit rejected: could not locate anchor in ${file}. Please regenerate.`, 'error')
        return false
      }

      const { startIdx, endIdx } = loc
      const charStart = lines.slice(0, startIdx).reduce((sum, l) => sum + l.length + 1, 0)
      const oldText = lines.slice(startIdx, endIdx + 1).join('\n')

      collab.doc.transact(() => {
        yText.delete(charStart, oldText.length)
        yText.insert(charStart, replacement)
      })

      showToast(`Applied edit to ${file}`, 'success')
      requestAutosave('ai-edit-applied')
      return true
    }

    // Main file edit (file is undefined or 'main.tex')
    const currentContent = adapterRef.current?.getContent?.() || latestContentRef.current.html || ''
    const lines = currentContent.split('\n')

    // Resolve target location via anchor — line numbers are just a hint.
    // This is content-based addressing: we find WHERE the anchor lives in
    // the current document, not where the AI thought it was.
    const loc = resolveEditLocation(lines, startLine, endLine, anchor)
    if (!loc) {
      showToast(`Edit rejected: anchor not found near line ${startLine}. Please regenerate.`, 'error')
      return false
    }
    const { startIdx, endIdx } = loc

    // Apply the edit by replacing lines
    const before = lines.slice(0, startIdx)
    const after = lines.slice(endIdx + 1)
    const newLines = [...before, replacement, ...after]
    const newContent = newLines.join('\n')

    if (newContent === currentContent) {
      return false
    }

    // Use surgical Yjs edit when collab is active (track-changes compatible)
    if (collab.doc) {
      const mainYText = collab.doc.getText('main')
      if (mainYText && mainYText.length > 0) {
        const charStart = lines.slice(0, startIdx).reduce((sum, l) => sum + l.length + 1, 0)
        const oldText = lines.slice(startIdx, endIdx + 1).join('\n')

        collab.doc.transact(() => {
          mainYText.delete(charStart, oldText.length)
          mainYText.insert(charStart, replacement)
        })

        setLastHtml(newContent)
        const nextJson = isLatex
          ? { authoring_mode: 'latex', latex_source: newContent }
          : latestContentRef.current.json
        updateLatestContent(newContent, nextJson)
        requestAutosave('ai-edit-applied')
        return true
      }
    }

    // Fallback: non-collab mode — use adapter setContent
    adapterRef.current?.setContent?.(newContent, { overwriteRealtime: true })
    setLastHtml(newContent)
    const nextJson = isLatex
      ? { authoring_mode: 'latex', latex_source: newContent }
      : latestContentRef.current.json
    updateLatestContent(newContent, nextJson)
    requestAutosave('ai-edit-applied')
    return true
  }, [collab.doc, isLatex, readOnly, requestAutosave, showToast, updateLatestContent, resolveEditLocation])

  type BatchEdit = {
    id: string
    startLine: number
    endLine: number
    anchor: string
    proposed: string
    description?: string
    file?: string
  }

  const handleApplyAiEditsBatch = useCallback((proposals: BatchEdit[], _sourceDocument: string): string[] => {
    if (readOnly) return []

    const currentContent = adapterRef.current?.getContent?.() || latestContentRef.current.html || ''
    const lines = currentContent.split('\n')

    // Track skipped edits by reason for better user feedback
    const skipped: { id: string; reason: string; description: string }[] = []

    // Pass 1: Resolve each proposal's target via anchor matching (line numbers are hints)
    type Resolved = BatchEdit & { resolvedStartIdx: number; resolvedEndIdx: number }
    const resolved: Resolved[] = []
    for (const proposal of proposals) {
      const desc = proposal.description || `lines ${proposal.startLine}-${proposal.endLine}`
      const loc = resolveEditLocation(lines, proposal.startLine, proposal.endLine, proposal.anchor)
      if (!loc) {
        skipped.push({ id: proposal.id, reason: `anchor not found near line ${proposal.startLine}`, description: desc })
        continue
      }
      resolved.push({ ...proposal, resolvedStartIdx: loc.startIdx, resolvedEndIdx: loc.endIdx })
    }

    // Sort by resolved position DESCENDING — apply bottom-up so earlier edits
    // don't shift line numbers for later edits.
    resolved.sort((a, b) => {
      if (b.resolvedStartIdx !== a.resolvedStartIdx) return b.resolvedStartIdx - a.resolvedStartIdx
      return b.resolvedEndIdx - a.resolvedEndIdx
    })

    // Pass 2: Discard overlapping ranges using RESOLVED positions (not AI hints)
    const validProposals: Resolved[] = []
    for (const proposal of resolved) {
      const prev = validProposals[validProposals.length - 1]
      if (prev && proposal.resolvedEndIdx >= prev.resolvedStartIdx) {
        skipped.push({
          id: proposal.id,
          reason: `overlaps with another edit`,
          description: proposal.description || `lines ${proposal.startLine}-${proposal.endLine}`,
        })
        continue
      }
      validProposals.push(proposal)
    }

    if (validProposals.length === 0) {
      showToast('Could not apply edits: no proposals matched the document.', 'error')
      return []
    }

    // Pass 3: Apply all valid edits using RESOLVED positions, in reverse order
    const appliedIds: string[] = []
    for (const proposal of validProposals) {
      const { resolvedStartIdx, resolvedEndIdx } = proposal
      lines.splice(resolvedStartIdx, resolvedEndIdx - resolvedStartIdx + 1, ...proposal.proposed.split('\n'))
      appliedIds.push(proposal.id)
    }

    if (skipped.length > 0) {
      console.warn('[DocumentShell] Skipped edits:', skipped)
      // Group by reason for concise toast
      const reasons = skipped.map(s => `• "${s.description.slice(0, 50)}${s.description.length > 50 ? '…' : ''}" — ${s.reason}`).join('\n')
      showToast(`Applied ${appliedIds.length}/${proposals.length}. ${skipped.length} skipped:\n${reasons}`, 'success')
    }

    const newContent = lines.join('\n')
    if (newContent === currentContent) {
      showToast('No changes detected after applying edits.', 'error')
      return []
    }

    // Use surgical Yjs edits when collab is active (track-changes compatible)
    if (collab.doc) {
      const mainYText = collab.doc.getText('main')
      if (mainYText && mainYText.length > 0) {
        // Use RESOLVED indices (anchor-matched) instead of AI-provided line numbers.
        // validProposals are sorted descending by resolvedStartIdx, so applying in
        // order keeps char offsets valid for earlier (lower-line) edits.
        const origLines = currentContent.split('\n')
        collab.doc.transact(() => {
          for (const proposal of validProposals) {
            const { resolvedStartIdx: sIdx, resolvedEndIdx: eIdx } = proposal
            const charStart = origLines.slice(0, sIdx).reduce((sum, l) => sum + l.length + 1, 0)
            const oldText = origLines.slice(sIdx, eIdx + 1).join('\n')
            mainYText.delete(charStart, oldText.length)
            mainYText.insert(charStart, proposal.proposed)
            origLines.splice(sIdx, eIdx - sIdx + 1, ...proposal.proposed.split('\n'))
          }
        })

        setLastHtml(newContent)
        const nextJson = isLatex
          ? { authoring_mode: 'latex', latex_source: newContent }
          : latestContentRef.current.json
        updateLatestContent(newContent, nextJson)
        requestAutosave('ai-edit-applied-batch')
        return appliedIds
      }
    }

    // Fallback: non-collab mode — use adapter setContent
    adapterRef.current?.setContent?.(newContent, { overwriteRealtime: true })
    setLastHtml(newContent)
    const nextJson = isLatex
      ? { authoring_mode: 'latex', latex_source: newContent }
      : latestContentRef.current.json
    updateLatestContent(newContent, nextJson)
    requestAutosave('ai-edit-applied-batch')
    return appliedIds
  }, [collab.doc, isLatex, readOnly, requestAutosave, showToast, updateLatestContent, resolveEditLocation])

  /** Get live document text — reads from Yjs (realtime) or falls back to lastHtml/latestContentRef */
  const getLiveDocumentText = useCallback((): string => {
    // 1. Try Yjs realtime doc (most current)
    if (collab.doc) {
      try {
        const mainText = collab.doc.getText('main')
        if (mainText && mainText.length > 0) return mainText.toString()
      } catch {}
    }
    // 2. Try lastHtml state
    if (lastHtml) return lastHtml
    // 3. Try latestContentRef
    const refContent = latestContentRef.current
    if (refContent.json?.latex_source) return refContent.json.latex_source
    if (refContent.html) return refContent.html
    return ''
  }, [collab.doc, lastHtml])

  /** Get extra file contents from Yjs for multi-file AI context */
  const getDocumentFiles = useCallback((): Record<string, string> | null => {
    if (!collab.doc) return null
    const files: Record<string, string> = {}
    try {
      const types = collab.doc.share as Map<string, unknown>
      types.forEach((_value: unknown, key: string) => {
        if (key.startsWith('file:')) {
          const filename = key.slice(5)
          const yText = collab.doc!.getText(key)
          if (yText && yText.length > 0) {
            files[filename] = yText.toString()
          }
        }
      })
    } catch { /* ignore errors reading Yjs types */ }
    return Object.keys(files).length > 0 ? files : null
  }, [collab.doc])

  // --- Fix Errors with AI ---
  const handleFixErrors = useCallback(async (latexSource: string, errorLog: string) => {
    if (readOnly || fixLoading) return
    setFixLoading(true)
    setFixProposals([])
    fixSourceSnapshotRef.current = latexSource

    try {
      const res = await fetch(
        buildApiUrl('/latex/fix-errors'),
        {
          method: 'POST',
          headers: buildAuthHeaders(),
          body: JSON.stringify({
            latex_source: latexSource,
            error_log: errorLog,
            paper_id: paperId,
            project_id: projectId,
          }),
        }
      )
      if (!res.ok) {
        console.error('[DocumentShell] fix-errors failed:', res.status)
        return
      }

      const reader = res.body?.getReader()
      if (!reader) return
      const decoder = new TextDecoder()
      let buffer = ''
      let fullText = ''

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const json = line.slice(6).trim()
          if (!json || json === '[DONE]') continue
          try {
            const event = JSON.parse(json)
            if (event.type === 'token') fullText += event.content
            if (event.type === 'done') break
          } catch { /* skip malformed SSE */ }
        }
      }

      const { proposals } = parseEditProposals(fullText)
      setFixProposals(proposals)
    } catch (e) {
      console.error('[DocumentShell] fix errors failed:', e)
    } finally {
      setFixLoading(false)
    }
  }, [paperId, projectId, readOnly, fixLoading])

  const handleApplyFix = useCallback((id: string) => {
    const proposal = fixProposals.find(p => p.id === id)
    if (!proposal || proposal.status !== 'pending') return

    const success = handleApplyAiEdit(
      proposal.startLine, proposal.endLine,
      proposal.anchor, proposal.proposed,
      fixSourceSnapshotRef.current, proposal.file,
    )

    setFixProposals(prev => prev.map(p =>
      p.id === id ? { ...p, status: success ? 'approved' : 'rejected' } : p
    ))

    // Update snapshot after successful apply so subsequent edits use current state
    if (success) {
      const updated = adapterRef.current?.getContent?.() || latestContentRef.current.html || ''
      fixSourceSnapshotRef.current = updated
    }
  }, [fixProposals, handleApplyAiEdit])

  const handleRejectFix = useCallback((id: string) => {
    setFixProposals(prev => prev.map(p =>
      p.id === id ? { ...p, status: 'rejected' } : p
    ))
  }, [])

  const handleApplyAllFixes = useCallback(() => {
    const pending = fixProposals.filter(p => p.status === 'pending')
    if (pending.length === 0) return

    const appliedIds = handleApplyAiEditsBatch(
      pending.map(p => ({
        id: p.id,
        startLine: p.startLine,
        endLine: p.endLine,
        anchor: p.anchor,
        proposed: p.proposed,
      })),
      fixSourceSnapshotRef.current,
    )

    const appliedSet = new Set(appliedIds)
    setFixProposals(prev => prev.map(p => {
      if (p.status !== 'pending') return p
      return { ...p, status: appliedSet.has(p.id) ? 'approved' : 'rejected' }
    }))

    // Update snapshot
    if (appliedIds.length > 0) {
      const updated = adapterRef.current?.getContent?.() || latestContentRef.current.html || ''
      fixSourceSnapshotRef.current = updated
    }
  }, [fixProposals, handleApplyAiEditsBatch])

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
          className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 py-2.5 pl-3 pr-4 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-indigo-500/40 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 active:translate-y-0 dark:shadow-indigo-500/20 dark:hover:shadow-indigo-500/30"
          title="Open AI Assistant (⌘J)"
          aria-label="Open AI Assistant"
        >
          <Sparkles className="h-4 w-4" />
          <span>Ask AI</span>
        </button>
      )}

      <div
        ref={contentWrapRef}
        className="flex-1 min-h-0 flex flex-col p-0"
        style={fullBleed ? { } : { height: containerH }}
      >
        {/*
          Horizontal split: [Adapter (editor + PDF)] | [AI chat column].
          The AI chat is a real flex child when open — it pushes content rather
          than overlaying it, matching the Cursor / Copilot Chat pattern. On
          narrow screens (<md) it falls back to a bottom overlay so the editor
          and PDF aren't starved of width.
        */}
        <div className="relative flex-1 min-h-0 overflow-hidden flex">
          <div className="relative min-w-0 flex-1 overflow-hidden">
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
              onFixErrors={readOnly ? undefined : handleFixErrors}
              fixLoading={fixLoading}
              fixProposals={fixProposals}
              onApplyFix={handleApplyFix}
              onRejectFix={handleRejectFix}
              onApplyAllFixes={handleApplyAllFixes}
            />
          </div>
          </div>

          {/*
            Docked AI chat column — pushes the Adapter when open.
            Hidden below md (<768px); on narrow screens EditorAIChatOR falls
            back to a bottom overlay (handled inside that component).
            Width is draggable via the handle on its left edge; the resulting
            size persists across reloads.
          */}
          {!readOnly && aiChatOpen && (
            <>
              {/*
                Drag handle. Container is 8px wide for a comfortable hit
                target; the visible rule is a 2px centered strip. The flex
                wrapper makes that trivial and keeps the cursor feedback
                across the full hit area.
              */}
              <div
                role="separator"
                aria-orientation="vertical"
                aria-label="Resize AI chat panel"
                onPointerDown={handleAiChatDragStart}
                onDoubleClick={() => setAiChatWidth(AI_CHAT_WIDTH_DEFAULT)}
                title="Drag to resize · double-click to reset"
                className="group hidden shrink-0 cursor-col-resize items-center justify-center md:flex md:w-[8px]"
              >
                <div className={`h-full w-[2px] transition-colors ${aiChatDragging ? 'bg-indigo-500' : 'bg-slate-200 group-hover:bg-indigo-400 dark:bg-slate-700 dark:group-hover:bg-indigo-500'}`} />
              </div>
              <div
                className="hidden shrink-0 flex-col md:flex dark:bg-slate-900"
                style={{ width: aiChatWidth }}
              >
                <EditorAIChatOR
                  paperId={paperId}
                  projectId={projectId}
                  documentText={getLiveDocumentText()}
                  documentFiles={getDocumentFiles()}
                  open={true}
                  onOpenChange={(next) => setAiChatOpen(readOnly ? false : next)}
                  onApplyEdit={handleApplyAiEdit}
                  onApplyEditsBatch={handleApplyAiEditsBatch}
                  initialMessage={aiChatInitialMessage || undefined}
                  onInitialMessageConsumed={() => setAiChatInitialMessage(null)}
                  isOwner={isPaperOwner}
                  layout="docked"
                />
              </div>
              {/*
                During drag, a fixed full-viewport overlay intercepts pointer
                events so the PDF iframe (and any other child iframes) can't
                swallow them. pointer-events: all is implicit on a div. The
                col-resize cursor keeps the affordance obvious while dragging.
              */}
              {aiChatDragging && (
                <div
                  className="fixed inset-0 z-[100] cursor-col-resize"
                  style={{ touchAction: 'none' }}
                />
              )}
            </>
          )}
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

      {/*
        AI Chat overlay fallback — only used below md (<768px) where the
        docked column in the layout above is hidden. On desktop this second
        instance is hidden by the `md:hidden` wrapper so we don't render two
        copies of the chat.
      */}
      <div className="md:hidden">
        <EditorAIChatOR
          paperId={paperId}
          projectId={projectId}
          documentText={getLiveDocumentText()}
          documentFiles={getDocumentFiles()}
          open={!readOnly && aiChatOpen}
          onOpenChange={(next) => setAiChatOpen(readOnly ? false : next)}
          onApplyEdit={handleApplyAiEdit}
          onApplyEditsBatch={handleApplyAiEditsBatch}
          initialMessage={aiChatInitialMessage || undefined}
          onInitialMessageConsumed={() => setAiChatInitialMessage(null)}
          isOwner={isPaperOwner}
          layout="overlay"
        />
      </div>
    </div>
  )
}

export default DocumentShell
