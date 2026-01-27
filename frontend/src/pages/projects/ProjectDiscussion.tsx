import { useState, useEffect, useLayoutEffect, useRef, useMemo, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageCircle, Loader2, AlertCircle, Plus, Sparkles, X, Bot, FileText, BookOpen, Calendar, Check, ChevronDown, ChevronRight, FilePlus, Pencil, CheckSquare, Search, Download, MoreHorizontal, FolderOpen, ListTodo, Puzzle, Hash, CheckCircle, Library, Menu } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { formatDistanceToNow } from 'date-fns'
import { useProjectContext } from './ProjectLayout'
import { useAuth } from '../../contexts/AuthContext'
import { projectDiscussionAPI, buildApiUrl, refreshAuthToken, researchPapersAPI, projectReferencesAPI, projectMeetingsAPI } from '../../services/api'
import discussionWebsocket from '../../services/discussionWebsocket'
import {
  DiscussionMessage,
  DiscussionThread as DiscussionThreadType,
  DiscussionChannelSummary,
  DiscussionChannelResource,
  DiscussionTask,
  DiscussionTaskCreate,
  DiscussionTaskUpdate,
  DiscussionChannelResourceCreate,
  DiscussionAssistantResponse,
  DiscussionAssistantSuggestedAction,
  ChannelScopeConfig,
  ResearchPaper,
  ProjectReferenceSuggestion,
  MeetingSummary,
} from '../../types'
import MessageInput from '../../components/discussion/MessageInput'
import DiscussionThread from '../../components/discussion/DiscussionThread'
import DiscussionChannelSidebar from '../../components/discussion/DiscussionChannelSidebar'
import ChannelResourcePanel from '../../components/discussion/ChannelResourcePanel'
import ChannelTaskDrawer from '../../components/discussion/ChannelTaskDrawer'
import ChannelArtifactsPanel from '../../components/discussion/ChannelArtifactsPanel'
import { DiscoveredPaper, IngestionStatus } from '../../components/discussion/DiscoveredPaperCard'
import { DiscoveryQueuePanel, PaperIngestionState, IngestionStatesMap } from '../../components/discussion/DiscoveryQueuePanel'
import { getProjectUrlId } from '../../utils/urlId'

type AssistantExchange = {
  id: string
  channelId: string // Channel this exchange belongs to
  question: string
  response: DiscussionAssistantResponse
  createdAt: Date
  completedAt?: Date
  appliedActions: string[]
  status: 'pending' | 'streaming' | 'complete'
  displayMessage: string
  statusMessage?: string // Dynamic status message showing what the AI is doing
  author?: { id?: string; name?: { display?: string; first?: string; last?: string } | string }
  fromHistory?: boolean // true if loaded from history, false if created in current session
}

type ConversationItem =
  | { kind: 'thread'; timestamp: number; thread: DiscussionThreadType }
  | { kind: 'assistant'; timestamp: number; exchange: AssistantExchange }

const stripActionsBlock = (value: string): string =>
  value
    .replace(/<actions>[\s\S]*?<\/actions>/gi, '')
    .replace(/<actions>[\s\S]*$/gi, '')
    .trimEnd()

const buildCitationLookup = (citations: DiscussionAssistantResponse['citations']) => {
  const lookup = new Map<string, string>()
  citations.forEach((citation) => {
    if (!citation) return
    const key = `${citation.origin}:${citation.origin_id}`.toLowerCase()
    const label = typeof citation.label === 'string' ? citation.label.trim() : ''
    if (label) {
      lookup.set(key, label)
    }
  })
  return lookup
}

const formatAssistantMessage = (
  message: string,
  lookup: Map<string, string>,
): string => {
  if (!message) return ''

  const replaced = message.replace(/\[(resource|message):([^\]]+)\]/gi, (_, origin, identifier) => {
    const key = `${origin}:${identifier}`.toLowerCase()
    const label = lookup.get(key)
    return label ? `**${label}**` : ''
  })

  return stripActionsBlock(replaced).replace(/[ \t]+$/gm, '').replace(/\n{3,}/g, '\n\n').trim()
}

const createAssistantEntryId = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

const ASSISTANT_SCOPE_OPTIONS = [
  { id: 'transcripts', label: 'Transcripts' },
  { id: 'papers', label: 'Papers' },
  { id: 'references', label: 'References' },
]

const ProjectDiscussion = () => {
  const { project } = useProjectContext()
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const typingTimers = useRef<Record<string, number>>({})
  const streamingFlags = useRef<Record<string, boolean>>({})
  const historyChannelRef = useRef<string | null>(null)
  const assistantAbortController = useRef<AbortController | null>(null)
  const STORAGE_PREFIX = `assistantHistory:${project.id}`

  const buildStorageKey = useCallback(
    (channelId: string | null) => {
      if (!channelId) return null
      return `${STORAGE_PREFIX}:${channelId}`
    },
    [STORAGE_PREFIX],
  )

  const [replyingTo, setReplyingTo] = useState<{ id: string; userName: string } | null>(null)
  const [editingMessage, setEditingMessage] = useState<{ id: string; content: string } | null>(null)
  const [activeChannelId, setActiveChannelId] = useState<string | null>(null)
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false)
const [isCreateChannelModalOpen, setIsCreateChannelModalOpen] = useState(false)
const [newChannelName, setNewChannelName] = useState('')
const [newChannelDescription, setNewChannelDescription] = useState('')
const [newChannelScope, setNewChannelScope] = useState<ChannelScopeConfig | null>(null) // null = project-wide
const [isChannelSettingsOpen, setIsChannelSettingsOpen] = useState(false)
const [settingsChannel, setSettingsChannel] = useState<DiscussionChannelSummary | null>(null)
  const [assistantReasoning, setAssistantReasoning] = useState(false)
  const [assistantHistory, setAssistantHistory] = useState<AssistantExchange[]>([])
  const [assistantScope, setAssistantScope] = useState<string[]>(['transcripts', 'papers', 'references'])

  const toggleAssistantScope = useCallback((value: string) => {
    setAssistantScope((prev) => {
      if (prev.includes(value)) {
        if (prev.length === 1) {
          return prev
        }
        return prev.filter((item) => item !== value)
      }
      return [...prev, value]
    })
  }, [])
  const [openDialog, setOpenDialog] = useState<'resources' | 'tasks' | 'artifacts' | 'discoveries' | null>(null)
  const [channelMenuOpen, setChannelMenuOpen] = useState(false)
  const [aiContextExpanded, setAiContextExpanded] = useState(false)
  const channelMenuRef = useRef<HTMLDivElement>(null)

  // Paper creation dialog state
  const [paperCreationDialog, setPaperCreationDialog] = useState<{
    open: boolean
    exchangeId: string
    actionIndex: number
    suggestedTitle: string
    suggestedType: string
    suggestedMode: string
    suggestedAbstract: string
    suggestedKeywords: string[]
  } | null>(null)

  // Reference search results state - stored per channel to preserve when switching
  const [searchResultsByChannel, setSearchResultsByChannel] = useState<Record<string, {
    exchangeId: string
    papers: DiscoveredPaper[]
    query: string
    isSearching: boolean
  }>>({})

  // Ingestion state - managed here, passed to DiscoveryQueuePanel
  const [ingestionStatesByChannel, setIngestionStatesByChannel] = useState<
    Record<string, IngestionStatesMap>
  >({})

  // Get current channel's ingestion states
  const currentIngestionStates = useMemo(() => {
    if (!activeChannelId) return {}
    return ingestionStatesByChannel[activeChannelId] || {}
  }, [activeChannelId, ingestionStatesByChannel])

  // Callback for DiscoveryQueuePanel to update ingestion state
  const handleIngestionStateChange = useCallback((paperId: string, state: Partial<PaperIngestionState>) => {
    if (!activeChannelId) return
    setIngestionStatesByChannel((prev) => {
      const channelStates = prev[activeChannelId] || {}
      const existingState = channelStates[paperId] || { referenceId: '', status: 'pending' as IngestionStatus, isAdding: false }
      return {
        ...prev,
        [activeChannelId]: {
          ...channelStates,
          [paperId]: { ...existingState, ...state },
        },
      }
    })
  }, [activeChannelId])

  // Track channel switch to prevent brief notification flash during transitions
  // With the batched state updates fix, this is mainly a safety net
  const [isChannelSwitching, setIsChannelSwitching] = useState(false)
  const prevChannelRef = useRef<string | null>(null)

  // Use useLayoutEffect to synchronously hide notification before paint
  useLayoutEffect(() => {
    if (prevChannelRef.current !== null && prevChannelRef.current !== activeChannelId) {
      setIsChannelSwitching(true)
    }
    prevChannelRef.current = activeChannelId
  }, [activeChannelId])

  // Re-enable after state updates are batched (very brief delay)
  useEffect(() => {
    if (isChannelSwitching) {
      const timer = setTimeout(() => setIsChannelSwitching(false), 50)
      return () => clearTimeout(timer)
    }
  }, [isChannelSwitching])

  // Dismissed paper IDs - persisted to localStorage per project
  const dismissedPapersKey = project?.id ? `scholarhub_dismissed_papers_${project.id}` : null
  const [dismissedPaperIds, setDismissedPaperIds] = useState<Set<string>>(() => {
    if (!dismissedPapersKey) return new Set()
    try {
      const stored = localStorage.getItem(dismissedPapersKey)
      if (stored) {
        return new Set(JSON.parse(stored))
      }
    } catch {
      // Ignore localStorage errors
    }
    return new Set()
  })

  // Persist dismissed papers to localStorage when they change
  useEffect(() => {
    if (!dismissedPapersKey) return
    try {
      localStorage.setItem(dismissedPapersKey, JSON.stringify([...dismissedPaperIds]))
    } catch {
      // Ignore localStorage errors
    }
  }, [dismissedPaperIds, dismissedPapersKey])

  // Reset all dismissed papers
  const resetDismissedPapers = useCallback(() => {
    setDismissedPaperIds(new Set())
    if (dismissedPapersKey) {
      localStorage.removeItem(dismissedPapersKey)
    }
  }, [dismissedPapersKey])

  // Get current channel's search results (filtering out dismissed papers)
  const referenceSearchResults = useMemo(() => {
    if (!activeChannelId) return null
    const raw = searchResultsByChannel[activeChannelId]
    if (!raw) return null
    return {
      ...raw,
      papers: raw.papers.filter(p => !dismissedPaperIds.has(p.id))
    }
  }, [activeChannelId, searchResultsByChannel, dismissedPaperIds])

  // Helper to set search results for a specific channel
  const setReferenceSearchResults = useCallback((
    value: { exchangeId: string; channelId: string; papers: DiscoveredPaper[]; query: string; isSearching: boolean } | null
  ) => {
    if (!value) {
      // Clear results for current channel
      if (activeChannelId) {
        setSearchResultsByChannel(prev => {
          const next = { ...prev }
          delete next[activeChannelId]
          return next
        })
      }
      return
    }
    // Set results for the specified channel
    setSearchResultsByChannel(prev => ({
      ...prev,
      [value.channelId]: {
        exchangeId: value.exchangeId,
        papers: value.papers,
        query: value.query,
        isSearching: value.isSearching,
      }
    }))
  }, [activeChannelId])

  // Discovery queue - stored per channel to preserve when switching
  const [discoveryQueueByChannel, setDiscoveryQueueByChannel] = useState<Record<string, {
    papers: DiscoveredPaper[]
    query: string
    isSearching: boolean
    notification: string | null
  }>>({})

  // Track channels where user has dismissed the notification (prevents re-showing from history)
  // Persisted to localStorage per project
  const dismissedNotificationsKey = project?.id ? `scholarhub_dismissed_notifications_${project.id}` : null
  const [dismissedNotificationChannels, setDismissedNotificationChannels] = useState<Set<string>>(() => {
    if (!dismissedNotificationsKey) return new Set()
    try {
      const stored = localStorage.getItem(dismissedNotificationsKey)
      if (stored) {
        return new Set(JSON.parse(stored))
      }
    } catch {
      // Ignore localStorage errors
    }
    return new Set()
  })

  // Persist dismissed notifications to localStorage when they change
  useEffect(() => {
    if (!dismissedNotificationsKey) return
    try {
      localStorage.setItem(dismissedNotificationsKey, JSON.stringify([...dismissedNotificationChannels]))
    } catch {
      // Ignore localStorage errors
    }
  }, [dismissedNotificationChannels, dismissedNotificationsKey])

  // Get current channel's discovery queue (filtering out dismissed papers)
  const discoveryQueue = useMemo(() => {
    if (!activeChannelId) {
      return { papers: [], query: '', isSearching: false, notification: null }
    }
    const raw = discoveryQueueByChannel[activeChannelId] || { papers: [], query: '', isSearching: false, notification: null }
    return {
      ...raw,
      papers: raw.papers.filter(p => !dismissedPaperIds.has(p.id))
    }
  }, [activeChannelId, discoveryQueueByChannel, dismissedPaperIds])

  // Count dismissed papers only for the current search (not all dismissed papers ever)
  const dismissedInCurrentSearch = useMemo(() => {
    if (!activeChannelId) return 0
    const raw = discoveryQueueByChannel[activeChannelId]
    if (!raw?.papers) return 0
    return raw.papers.filter(p => dismissedPaperIds.has(p.id)).length
  }, [activeChannelId, discoveryQueueByChannel, dismissedPaperIds])

  // Compute ingestion summary for notification bar - derived from unified ingestion state
  const ingestionSummary = useMemo(() => {
    const states = Object.values(currentIngestionStates)
    if (states.length === 0) return null

    const totalAdded = states.filter((s) => s.referenceId || s.isAdding).length
    if (totalAdded === 0) return null

    const successCount = states.filter((s) => s.status === 'success').length
    const failedCount = states.filter((s) => s.status === 'failed').length
    const noPdfCount = states.filter((s) => s.status === 'no_pdf').length
    const pendingCount = states.filter(
      (s) => s.status === 'pending' || s.status === 'uploading' || s.isAdding
    ).length
    const needsAttention = failedCount + noPdfCount

    return {
      totalAdded,
      successCount,
      failedCount,
      noPdfCount,
      pendingCount,
      needsAttention,
      isAllSuccess: successCount === totalAdded && totalAdded > 0,
      isProcessing: pendingCount > 0,
    }
  }, [currentIngestionStates])

  // Helper to set discovery queue for current channel
  const setDiscoveryQueue = useCallback((
    value: React.SetStateAction<{
      papers: DiscoveredPaper[]
      query: string
      isSearching: boolean
      notification: string | null
    }>
  ) => {
    if (!activeChannelId) return
    setDiscoveryQueueByChannel(prev => {
      const currentQueue = prev[activeChannelId] || { papers: [], query: '', isSearching: false, notification: null }
      const newQueue = typeof value === 'function' ? value(currentQueue) : value
      return {
        ...prev,
        [activeChannelId]: newQueue
      }
    })
  }, [activeChannelId])

  // Handler to dismiss a paper from search results and discovery queue
  const handleDismissPaper = useCallback((paperId: string) => {
    if (!activeChannelId) return

    // Persist dismissed paper ID to localStorage
    setDismissedPaperIds(prev => new Set([...prev, paperId]))

    // Remove from search results
    setSearchResultsByChannel(prev => {
      const current = prev[activeChannelId]
      if (!current) return prev
      return {
        ...prev,
        [activeChannelId]: {
          ...current,
          papers: current.papers.filter(p => p.id !== paperId)
        }
      }
    })

    // Remove from discovery queue
    setDiscoveryQueueByChannel(prev => {
      const current = prev[activeChannelId]
      if (!current) return prev
      return {
        ...prev,
        [activeChannelId]: {
          ...current,
          papers: current.papers.filter(p => p.id !== paperId)
        }
      }
    })
  }, [activeChannelId])

  const [paperFormData, setPaperFormData] = useState({
    title: '',
    paperType: 'research',
    authoringMode: 'latex',
    abstract: '',
    keywords: [] as string[],
    objectives: [] as string[],
  })
  const [keywordInput, setKeywordInput] = useState('')

  const viewerDisplayName = useMemo(() => {
    if (!user) return 'You'
    const parts = [user.first_name, user.last_name].filter(Boolean).join(' ').trim()
    if (parts) return parts
    return user.email || 'You'
  }, [user?.first_name, user?.last_name, user?.email])

  const resolveAuthorLabel = useCallback(
    (author?: AssistantExchange['author']) => {
      if (!author) return 'Someone'

      // If it's the current user, always use consistent name
      const sameUser = Boolean(author.id && user?.id && author.id === user.id)
      if (sameUser) {
        return viewerDisplayName || 'You'
      }

      // If author.name is a string, use it directly
      if (typeof author.name === 'string' && author.name.trim()) {
        return author.name.trim()
      }

      // If author.name is an object, try display first, then combine first + last
      if (author.name && typeof author.name === 'object') {
        const nameObj = author.name as { display?: string; first?: string; last?: string }

        if (nameObj.display?.trim()) {
          return nameObj.display.trim()
        }

        const first = nameObj.first?.trim() || ''
        const last = nameObj.last?.trim() || ''
        const combined = [first, last].filter(Boolean).join(' ')
        if (first || last) {
          return combined
        }
      }

      return 'Someone'
    },
    [user?.id, viewerDisplayName],
  )

  const startTypewriter = useCallback(
    (entryId: string, fullText: string) => {
      if (typingTimers.current[entryId]) {
        window.clearTimeout(typingTimers.current[entryId])
        delete typingTimers.current[entryId]
      }

      const text = fullText || ''
      if (!text) {
        setAssistantHistory((prev) =>
          prev.map((entry) =>
            entry.id === entryId
              ? {
                  ...entry,
                  displayMessage: '',
                  status: 'complete',
                  completedAt: entry.completedAt ?? new Date(),
                }
              : entry,
          ),
        )
        return
      }

      let index = 0

      const step = () => {
        index += 1
        const slice = text.slice(0, index)
        setAssistantHistory((prev) =>
          prev.map((entry) =>
            entry.id === entryId
              ? {
                  ...entry,
                  displayMessage: slice,
                  status: index >= text.length ? 'complete' : 'streaming',
                  completedAt:
                    index >= text.length ? entry.completedAt ?? new Date() : entry.completedAt,
                }
              : entry,
          ),
        )

        if (index < text.length) {
          const cadence = Math.max(15, Math.min(60, Math.floor(1000 / text.length)))
          typingTimers.current[entryId] = window.setTimeout(step, cadence)
        } else {
          delete typingTimers.current[entryId]
        }
      }

      setAssistantHistory((prev) =>
        prev.map((entry) =>
          entry.id === entryId
            ? {
                ...entry,
                displayMessage: '',
                status: 'streaming',
                completedAt: entry.completedAt,
              }
            : entry,
        ),
      )

      typingTimers.current[entryId] = window.setTimeout(step, 40)
    },
    [setAssistantHistory],
  )

  useEffect(() => {
    return () => {
      Object.values(typingTimers.current).forEach((timerId) => window.clearTimeout(timerId))
      typingTimers.current = {}
      streamingFlags.current = {}
    }
  }, [])

  // Close channel menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (channelMenuRef.current && !channelMenuRef.current.contains(event.target as Node)) {
        setChannelMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const [showArchivedChannels, setShowArchivedChannels] = useState(false)

  const channelsQuery = useQuery({
    queryKey: ['projectDiscussionChannels', project.id],
    queryFn: async () => {
      // Always fetch all channels including archived - filtering happens in sidebar
      const response = await projectDiscussionAPI.listChannels(project.id, { includeArchived: true })
      return response.data
    },
  })

  const assistantHistoryQuery = useQuery({
    queryKey: ['projectDiscussionAssistantHistory', project.id, activeChannelId],
    queryFn: async () => {
      if (!activeChannelId) return []
      const response = await projectDiscussionAPI.listAssistantHistory(project.id, activeChannelId)
      return response.data
    },
    enabled: Boolean(activeChannelId),
    placeholderData: [], // Return empty immediately when channel changes to prevent stale data
  })

  // Query for artifacts count (for badge display)
  const artifactsQuery = useQuery({
    queryKey: ['channel-artifacts', project.id, activeChannelId],
    queryFn: async () => {
      if (!activeChannelId) return []
      const response = await projectDiscussionAPI.listArtifacts(project.id, activeChannelId)
      return response.data
    },
    enabled: Boolean(activeChannelId),
  })
  const artifactsCount = artifactsQuery.data?.length ?? 0

  const serverAssistantHistory = useMemo<AssistantExchange[]>(() => {
    if (!assistantHistoryQuery.data || !activeChannelId) return []

    return assistantHistoryQuery.data.map((item) => {
      const createdAt = item.created_at ? new Date(item.created_at) : new Date()
      const response = item.response
      const lookup = buildCitationLookup(response.citations)

      // Handle processing status from server
      const isProcessing = item.status === 'processing'
      const isFailed = item.status === 'failed'

      return {
        id: item.id,
        channelId: activeChannelId, // Server history is filtered by channel
        question: item.question,
        response,
        createdAt,
        completedAt: isProcessing ? undefined : createdAt,
        appliedActions: [],
        status: isProcessing ? 'streaming' : 'complete',
        statusMessage: isProcessing ? (item.status_message || 'Processing...') : (isFailed ? (item.status_message || 'Processing failed') : undefined),
        displayMessage: isProcessing ? '' : formatAssistantMessage(response.message, lookup),
        author: item.author ?? undefined,
        fromHistory: true, // Loaded from server, don't auto-trigger actions
      }
    })
  }, [assistantHistoryQuery.data, activeChannelId])

  // Clear history when channel changes - search results and discovery queue are preserved per channel
  useEffect(() => {
    setAssistantHistory([])
    // Don't clear referenceSearchResults or discoveryQueue - they're stored per channel now
    historyChannelRef.current = activeChannelId
  }, [activeChannelId])

  useEffect(() => {
    setOpenDialog(null)
  }, [activeChannelId])

  // Merge server history with local unsynced entries
  useEffect(() => {
    if (!activeChannelId) return

    // Merge server data with local unsynced entries (entries created during streaming)
    setAssistantHistory((prev) => {
      const idsFromServer = new Set(serverAssistantHistory.map((entry) => entry.id))
      // Map questions from server to their IDs (for replacing local entry IDs)
      const questionToServerIdMap = new Map<string, string>()
      serverAssistantHistory.forEach((entry) => {
        questionToServerIdMap.set(entry.question.toLowerCase().trim(), entry.id)
      })

      // Find local entries that have duplicates in server (same question, different ID)
      // We need to update referenceSearchResults if its exchangeId matches a removed local entry
      const localIdsToServerIds = new Map<string, string>()
      prev.forEach((entry) => {
        if (!idsFromServer.has(entry.id)) {
          const serverId = questionToServerIdMap.get(entry.question.toLowerCase().trim())
          if (serverId) {
            localIdsToServerIds.set(entry.id, serverId)
          }
        }
      })

      // Filter local entries: keep only if not in server by ID AND not duplicate by question
      const unsynced = prev.filter((entry) => {
        // Already in server by ID - skip
        if (idsFromServer.has(entry.id)) return false
        // Same question exists in server - this is a duplicate with different ID
        if (questionToServerIdMap.has(entry.question.toLowerCase().trim())) return false
        return true
      })

      // Update referenceSearchResults if its exchangeId was a local ID that's now replaced
      if (localIdsToServerIds.size > 0 && activeChannelId) {
        setSearchResultsByChannel(prevByChannel => {
          const currentResults = prevByChannel[activeChannelId]
          if (!currentResults) return prevByChannel
          const newServerId = localIdsToServerIds.get(currentResults.exchangeId)
          if (newServerId) {
            return {
              ...prevByChannel,
              [activeChannelId]: { ...currentResults, exchangeId: newServerId }
            }
          }
          return prevByChannel
        })
      }

      // Build map of existing appliedActions to preserve them during merge
      const existingAppliedActions = new Map<string, string[]>()
      prev.forEach((entry) => {
        if (entry.appliedActions.length > 0) {
          existingAppliedActions.set(entry.id, entry.appliedActions)
        }
      })

      // Merge server entries (preserving appliedActions from local state) with unsynced local entries
      const mergedServerEntries = serverAssistantHistory.map((entry) => {
        const existingActions = existingAppliedActions.get(entry.id)
        if (existingActions && existingActions.length > 0) {
          return { ...entry, appliedActions: existingActions }
        }
        return entry
      })

      const merged = [...mergedServerEntries, ...unsynced].sort(
        (a, b) => a.createdAt.getTime() - b.createdAt.getTime(),
      )
      return merged
    })
  }, [serverAssistantHistory, activeChannelId])

  useEffect(() => {
    if (!openDialog) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpenDialog(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [openDialog])

  const allChannels = (channelsQuery.data as DiscussionChannelSummary[] | undefined) ?? []
  const channels = useMemo(
    () => allChannels.filter((channel) => !channel.is_default),
    [allChannels],
  )

  // Removed automatic channel selection - users should explicitly select a channel
  // Previously auto-selected first channel which caused poor UX (auto-scrolling to bottom of long chats)
  useEffect(() => {
    // Only clear activeChannelId if the selected channel no longer exists
    if (activeChannelId && !channels.some((channel) => channel.id === activeChannelId)) {
      setActiveChannelId(null)
    }
  }, [channels, activeChannelId])

  // Clear UI state when channel changes
  useEffect(() => {
    setReplyingTo(null)
    setEditingMessage(null)
    setAssistantReasoning(false)
    Object.values(typingTimers.current).forEach((timerId) => window.clearTimeout(timerId))
    typingTimers.current = {}
    streamingFlags.current = {}
  }, [activeChannelId])

  // Fetch discussion threads
  const {
    data: threads,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['projectDiscussion', project.id, activeChannelId],
    queryFn: async () => {
      const response = await projectDiscussionAPI.listThreads(project.id, {
        channelId: activeChannelId ?? undefined,
      })
      return response.data
    },
    enabled: Boolean(activeChannelId),
    refetchInterval: 10000, // Refresh every 10 seconds for near-real-time updates
  })

  const orderedThreads = useMemo(() => {
    if (!threads) return []
    return [...threads].reverse()
  }, [threads])

  const conversationItems = useMemo<ConversationItem[]>(() => {
    const items: ConversationItem[] = orderedThreads.map((thread) => ({
      kind: 'thread',
      timestamp: new Date(thread.message.created_at).getTime(),
      thread,
    }))
    assistantHistory.forEach((exchange) => {
      items.push({
        kind: 'assistant',
        timestamp: exchange.createdAt.getTime(),
        exchange,
      })
    })
    return items.sort((a, b) => a.timestamp - b.timestamp)
  }, [orderedThreads, assistantHistory])

  const handleDiscussionEvent = useCallback(
    (payload: any) => {
      if (!payload || payload.project_id !== project.id) {
        return
      }
      if (!activeChannelId || payload.channel_id !== activeChannelId) {
        return
      }

      // Handle assistant processing started (background mode)
      if (payload.event === 'assistant_processing') {
        const exchange = payload.exchange
        if (!exchange) return
        // Skip if this is from the current user - they already have a local streaming entry
        // The WebSocket broadcast is mainly for other users or when returning to the page
        if (exchange.author?.id && user?.id && exchange.author.id === user.id) {
          // Check if there's already ANY streaming/pending entry (local ID won't match server ID)
          setAssistantHistory((prev) => {
            // If any entry is currently streaming or pending, skip adding duplicate
            // (local entries start as 'pending' before tokens arrive, then become 'streaming')
            if (prev.some((entry) => entry.status === 'streaming' || entry.status === 'pending')) return prev
            // Also skip if this exact server ID already exists
            if (prev.some((entry) => entry.id === exchange.id)) return prev
            const entry: AssistantExchange = {
              id: exchange.id,
              channelId: activeChannelId, // Track which channel this belongs to
              question: exchange.question || '',
              response: { message: '', citations: [], reasoning_used: false, model: '', usage: undefined, suggested_actions: [] },
              createdAt: exchange.created_at ? new Date(exchange.created_at) : new Date(),
              appliedActions: [],
              status: 'streaming',
              statusMessage: exchange.status_message || 'Processing...',
              displayMessage: '',
              author: exchange.author,
              fromHistory: true,
            }
            return [...prev, entry]
          })
        }
        return
      }

      // Handle assistant status updates (live progress updates)
      if (payload.event === 'assistant_status') {
        const exchangeId = payload.exchange_id
        const statusMessage = payload.status_message
        if (!exchangeId || !statusMessage) return
        setAssistantHistory((prev) =>
          prev.map((entry) =>
            entry.id === exchangeId && entry.status === 'streaming'
              ? { ...entry, statusMessage }
              : entry
          )
        )
        return
      }

      if (payload.event === 'assistant_reply') {
        const exchange = payload.exchange
        if (!exchange) {
          return
        }
        const exchangeId: string = exchange.id || createAssistantEntryId()

        // Skip if from same user - they already have the response via SSE stream
        // Only process replies from other users or when user returned to page mid-processing
        if (exchange.author?.id && user?.id && exchange.author.id === user.id) {
          // Check if we have a processing entry that needs to be updated
          setAssistantHistory((prev) => {
            const existingIndex = prev.findIndex((entry) => entry.id === exchangeId)
            if (existingIndex >= 0 && prev[existingIndex].statusMessage) {
              // Update processing entry with completed response
              const response: DiscussionAssistantResponse = exchange.response || {
                message: '',
                citations: [],
                reasoning_used: false,
                model: '',
                usage: undefined,
                suggested_actions: [],
              }
              const lookup = buildCitationLookup(response.citations || [])
              const formatted = formatAssistantMessage(response.message || '', lookup)
              const updated = [...prev]
              updated[existingIndex] = {
                ...updated[existingIndex],
                response,
                status: 'complete',
                statusMessage: undefined,
                displayMessage: formatted,
                completedAt: new Date(),
              }
              return updated
            }
            // Same user, not processing - skip (they already have it via SSE)
            return prev
          })
          return
        }

        // New exchange from another user
        setAssistantHistory((prev) => {
          if (prev.some((entry) => entry.id === exchangeId)) {
            return prev
          }
          const response: DiscussionAssistantResponse = exchange.response || {
            message: '',
            citations: [],
            reasoning_used: false,
            model: '',
            usage: undefined,
            suggested_actions: [],
          }
          const createdAt = exchange.created_at ? new Date(exchange.created_at) : new Date()
          const lookup = buildCitationLookup(response.citations || [])
          const formatted = formatAssistantMessage(response.message || '', lookup)
          const entry: AssistantExchange = {
            id: exchangeId,
            channelId: activeChannelId, // Track which channel this belongs to
            question: exchange.question || '',
            response,
            createdAt,
            completedAt: createdAt,
            appliedActions: [],
            status: 'complete',
            displayMessage: formatted,
            author: exchange.author,
            fromHistory: true,
          }
          return [...prev, entry]
        })

        // Only invalidate history for other users' replies
        queryClient.invalidateQueries({
          queryKey: ['projectDiscussionAssistantHistory', project.id, activeChannelId],
          exact: false,
        })
        return
      }

      if (
        payload.event === 'message_created' ||
        payload.event === 'message_updated' ||
        payload.event === 'message_deleted'
      ) {
        queryClient.invalidateQueries({ queryKey: ['projectDiscussion', project.id, activeChannelId] })
        queryClient.invalidateQueries({ queryKey: ['projectDiscussionStats', project.id, activeChannelId] })
      }
    },
    [project.id, activeChannelId, queryClient, user?.id],
  )

  useEffect(() => {
    discussionWebsocket.on('discussion_event', handleDiscussionEvent)
    return () => {
      discussionWebsocket.off('discussion_event', handleDiscussionEvent)
    }
  }, [handleDiscussionEvent])

  useEffect(() => {
    let cancelled = false
    if (!activeChannelId) {
      discussionWebsocket.disconnect()
      return
    }

    const connect = async () => {
      try {
        const token = await refreshAuthToken()
        if (cancelled) return
        await discussionWebsocket.connect(project.id, activeChannelId, token)
      } catch (error) {
        console.error('Failed to connect to discussion websocket', error)
      }
    }

    connect()

    return () => {
      cancelled = true
      discussionWebsocket.disconnect()
    }
  }, [project.id, activeChannelId])

  const createChannelMutation = useMutation({
    mutationFn: async ({
      name,
      description,
      scope,
    }: {
      name: string
      description?: string | null
      scope?: ChannelScopeConfig | null
    }) => {
      const payload: { name: string; description?: string; scope?: ChannelScopeConfig } = {
        name,
        description: description && description.trim().length > 0 ? description.trim() : undefined,
      }
      if (scope) {
        payload.scope = scope
      }
      const response = await projectDiscussionAPI.createChannel(project.id, payload)
      return response.data
    },
    onSuccess: (channel) => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionChannels', project.id] })
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionStats', project.id, channel.id] })
      queryClient.invalidateQueries({ queryKey: ['projectDiscussion', project.id, channel.id] })
      setActiveChannelId(channel.id)
      setIsCreateChannelModalOpen(false)
      setNewChannelName('')
      setNewChannelDescription('')
      setNewChannelScope(null)
    },
    onError: (error) => {
      console.error('Failed to create channel:', error)
      alert('Failed to create channel. Please try again.')
    },
  })

  const updateChannelMutation = useMutation({
    mutationFn: async ({
      channelId,
      payload,
    }: {
      channelId: string
      payload: { name?: string; description?: string | null; is_archived?: boolean; scope?: ChannelScopeConfig | null }
    }) => {
      const response = await projectDiscussionAPI.updateChannel(project.id, channelId, payload)
      return response.data
    },
    onSuccess: (channel) => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionChannels', project.id] })
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionStats', project.id, channel.id] })
      queryClient.invalidateQueries({ queryKey: ['projectDiscussion', project.id, channel.id] })
      setIsChannelSettingsOpen(false)
      setSettingsChannel(null)

      if (channel.is_archived && activeChannelId === channel.id) {
        const otherChannels = channels.filter((c) => c.id !== channel.id && !c.is_archived)
        const fallback = otherChannels[0] ?? null
        setActiveChannelId(fallback ? fallback.id : null)
      }
    },
    onError: (error) => {
      console.error('Failed to update channel:', error)
      alert('Unable to update channel right now. Please try again.')
    },
  })

  const deleteChannelMutation = useMutation({
    mutationFn: async (channelId: string) => {
      await projectDiscussionAPI.deleteChannel(project.id, channelId)
    },
    onSuccess: (_, deletedChannelId) => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionChannels', project.id] })
      setIsChannelSettingsOpen(false)
      setSettingsChannel(null)

      // Switch to another channel if the deleted one was active
      if (activeChannelId === deletedChannelId) {
        const otherChannels = channels.filter((c) => c.id !== deletedChannelId)
        const fallback = otherChannels.find((c) => c.is_default) ?? otherChannels[0] ?? null
        setActiveChannelId(fallback ? fallback.id : null)
      }
    },
    onError: (error) => {
      console.error('Failed to delete channel:', error)
      alert('Unable to delete channel. Please try again.')
    },
  })

  const resourcesQuery = useQuery<DiscussionChannelResource[]>({
    queryKey: ['projectDiscussionChannelResources', project.id, activeChannelId],
    queryFn: async () => {
      if (!activeChannelId) return []
      const response = await projectDiscussionAPI.listChannelResources(project.id, activeChannelId)
      return response.data
    },
    enabled: Boolean(activeChannelId),
    staleTime: 30_000,
  })

  const tasksQuery = useQuery<DiscussionTask[]>({
    queryKey: ['projectDiscussionTasks', project.id, activeChannelId],
    queryFn: async () => {
      if (!activeChannelId) return []
      const response = await projectDiscussionAPI.listTasks(project.id, {
        channelId: activeChannelId,
      })
      return response.data
    },
    enabled: Boolean(activeChannelId),
    staleTime: 15_000,
  })

  // Count pending tasks (open + in_progress) for badge display
  const pendingTasksCount = useMemo(() => {
    if (!tasksQuery.data) return 0
    return tasksQuery.data.filter(t => t.status === 'open' || t.status === 'in_progress').length
  }, [tasksQuery.data])

  // Fetch available resources for scope picker
  const availablePapersQuery = useQuery<ResearchPaper[]>({
    queryKey: ['scopePapers', project.id],
    queryFn: async () => {
      const response = await researchPapersAPI.getPapers({ projectId: project.id, limit: 200 })
      return response.data.papers as ResearchPaper[]
    },
    enabled: isCreateChannelModalOpen || isChannelSettingsOpen,
    staleTime: 60_000,
  })

  const availableReferencesQuery = useQuery<ProjectReferenceSuggestion[]>({
    queryKey: ['scopeReferences', project.id],
    queryFn: async () => {
      const response = await projectReferencesAPI.list(project.id, { status: 'approved' })
      return response.data.references as ProjectReferenceSuggestion[]
    },
    enabled: isCreateChannelModalOpen || isChannelSettingsOpen,
    staleTime: 60_000,
  })

  const availableMeetingsQuery = useQuery<MeetingSummary[]>({
    queryKey: ['scopeMeetings', project.id],
    queryFn: async () => {
      const response = await projectMeetingsAPI.listMeetings(project.id)
      return response.data.meetings as MeetingSummary[]
    },
    enabled: isCreateChannelModalOpen || isChannelSettingsOpen,
    staleTime: 60_000,
  })

  const createTaskMutation = useMutation({
    mutationFn: async (payload: DiscussionTaskCreate) => {
      if (!activeChannelId) throw new Error('Channel not selected')
      const response = await projectDiscussionAPI.createTask(project.id, activeChannelId, payload)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionTasks', project.id, activeChannelId] })
    },
    onError: (error) => {
      console.error('Failed to create task:', error)
      alert('Unable to create task right now. Please try again.')
    },
  })

  const paperActionMutation = useMutation({
    mutationFn: async (params: { actionType: string; payload: Record<string, unknown> }) => {
      const response = await projectDiscussionAPI.executePaperAction(
        project.id,
        params.actionType,
        params.payload
      )
      return response.data
    },
    onSuccess: (data, variables) => {
      if (data.success) {
        // Navigate to paper if created
        if (variables.actionType === 'create_paper' && (data.url_id || data.paper_id)) {
          navigate(`/projects/${getProjectUrlId(project)}/papers/${data.url_id || data.paper_id}`)
        }
        // Invalidate paper queries if edited
        if (variables.actionType === 'edit_paper') {
          queryClient.invalidateQueries({ queryKey: ['papers', project.id] })
          queryClient.invalidateQueries({ queryKey: ['paper'] })
        }
      }
    },
    onError: (error) => {
      console.error('Paper action failed:', error)
      alert('Failed to execute paper action. Please try again.')
    },
  })

  // Search references mutation
  const searchReferencesMutation = useMutation({
    mutationFn: async (params: { query: string; exchangeId: string; openAccessOnly?: boolean; maxResults?: number }) => {
      const response = await projectDiscussionAPI.searchReferences(
        project.id,
        params.query,
        { maxResults: params.maxResults || 10, openAccessOnly: params.openAccessOnly }
      )
      return { ...response.data, exchangeId: params.exchangeId }
    },
    onMutate: (params) => {
      // Capture the channel ID at mutation start - use this in onSuccess/onError
      const originalChannelId = activeChannelId || ''
      // Clear dismissed state for this channel - new search should show results
      if (originalChannelId) {
        setDismissedNotificationChannels(prev => {
          const next = new Set(prev)
          next.delete(originalChannelId)
          return next
        })
      }
      // Set searching state
      const currentResults = originalChannelId ? searchResultsByChannel[originalChannelId] : null
      setReferenceSearchResults({
        exchangeId: params.exchangeId,
        channelId: originalChannelId,
        papers: currentResults?.exchangeId === params.exchangeId ? currentResults.papers : [],
        query: params.query,
        isSearching: true,
      })
      // Also update discovery queue - auto-clear with notification
      setDiscoveryQueue((prev) => {
        const previousCount = prev.papers.length
        return {
          papers: [],
          query: params.query,
          isSearching: true,
          notification: previousCount > 0
            ? `Cleared ${previousCount} previous ${previousCount === 1 ? 'discovery' : 'discoveries'}. Searching...`
            : null,
        }
      })
      // Return context with original channel ID
      return { originalChannelId }
    },
    onSuccess: (data, _params, context) => {
      // Use the original channel ID from when the mutation started
      const channelId = context?.originalChannelId || activeChannelId || ''
      // Replace papers (not accumulate) - new search replaces old results
      const papers = data.papers || []
      setReferenceSearchResults({
        exchangeId: data.exchangeId,
        channelId: channelId,
        papers: papers,
        query: data.query,
        isSearching: false,
      })
      // Also replace discovery queue for the original channel
      // Clear old ingestion status when new search results arrive
      setIngestionStatesByChannel(prev => {
        const next = { ...prev }
        delete next[channelId]
        return next
      })
      // Only update discovery queue if still in the same channel
      if (channelId === activeChannelId) {
        setDiscoveryQueue({
          papers: papers,
          query: data.query,
          isSearching: false,
          notification: `Found ${papers.length} paper${papers.length !== 1 ? 's' : ''} for "${data.query}"`,
        })
      } else {
        // Store in the original channel's discovery queue
        setDiscoveryQueueByChannel(prev => ({
          ...prev,
          [channelId]: {
            papers: papers,
            query: data.query,
            isSearching: false,
            notification: `Found ${papers.length} paper${papers.length !== 1 ? 's' : ''} for "${data.query}"`,
          }
        }))
      }
    },
    onError: (error, params, context) => {
      console.error('Reference search failed:', error)
      const channelId = context?.originalChannelId || activeChannelId || ''
      const currentResults = channelId ? searchResultsByChannel[channelId] : null
      setReferenceSearchResults({
        exchangeId: params.exchangeId,
        channelId: channelId,
        papers: currentResults?.exchangeId === params.exchangeId ? (currentResults.papers || []) : [],
        query: params.query,
        isSearching: false,
      })
      // Also update discovery queue on error
      setDiscoveryQueue((prev) => ({
        ...prev,
        isSearching: false,
        notification: 'Search failed. Please try again.',
      }))
    },
  })

  // Parse project objectives from scope string
  const projectObjectives = useMemo(() => {
    if (!project.scope) return []
    const entries = project.scope.split(/\r?\n|•/)
    const parsed: string[] = []
    for (const entry of entries) {
      const cleaned = entry.replace(/^\s*\d+[\).\-\s]*/, '').trim()
      if (cleaned) {
        parsed.push(cleaned)
      }
    }
    return parsed
  }, [project.scope])

  // Handle paper creation dialog submission
  const handlePaperCreationSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!paperCreationDialog) return

    const { title, paperType, authoringMode, abstract, keywords, objectives } = paperFormData
    if (!title.trim()) {
      alert('Please enter a paper title.')
      return
    }

    const payload = {
      title: title.trim(),
      paper_type: paperType,
      authoring_mode: authoringMode,
      abstract: abstract.trim() || undefined,
      keywords: keywords.length > 0 ? keywords : undefined,
      objectives: objectives.length > 0 ? objectives : undefined,
    }

    paperActionMutation.mutate(
      { actionType: 'create_paper', payload },
      {
        onSuccess: (data) => {
          if (data.success) {
            markActionApplied(paperCreationDialog.exchangeId, `${paperCreationDialog.exchangeId}:${paperCreationDialog.actionIndex}`)
            setPaperCreationDialog(null)
            setPaperFormData({
              title: '',
              paperType: 'research',
              authoringMode: 'latex',
              abstract: '',
              keywords: [],
              objectives: [],
            })
          } else {
            alert(data.message || 'Failed to create paper')
          }
        },
      }
    )
  }

  // Add keyword handler
  const handleAddKeyword = () => {
    const keyword = keywordInput.trim()
    if (keyword && !paperFormData.keywords.includes(keyword)) {
      setPaperFormData((prev) => ({
        ...prev,
        keywords: [...prev.keywords, keyword],
      }))
      setKeywordInput('')
    }
  }

  // Remove keyword handler
  const handleRemoveKeyword = (keyword: string) => {
    setPaperFormData((prev) => ({
      ...prev,
      keywords: prev.keywords.filter((k) => k !== keyword),
    }))
  }

  // Toggle objective handler
  const handleToggleObjective = (objective: string) => {
    setPaperFormData((prev) => ({
      ...prev,
      objectives: prev.objectives.includes(objective)
        ? prev.objectives.filter((o) => o !== objective)
        : [...prev.objectives, objective],
    }))
  }

  const updateTaskMutation = useMutation({
    mutationFn: async ({ taskId, payload }: { taskId: string; payload: DiscussionTaskUpdate }) => {
      const response = await projectDiscussionAPI.updateTask(project.id, taskId, payload)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionTasks', project.id, activeChannelId] })
    },
    onError: (error) => {
      console.error('Failed to update task:', error)
      alert('Unable to update task right now.')
    },
  })

  const deleteTaskMutation = useMutation({
    mutationFn: async (taskId: string) => {
      await projectDiscussionAPI.deleteTask(project.id, taskId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionTasks', project.id, activeChannelId] })
    },
    onError: (error) => {
      console.error('Failed to delete task:', error)
      alert('Unable to delete task right now.')
    },
  })

  const createResourceMutation = useMutation({
    mutationFn: async (payload: DiscussionChannelResourceCreate) => {
      if (!activeChannelId) throw new Error('Channel not selected')
      const response = await projectDiscussionAPI.createChannelResource(project.id, activeChannelId, payload)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionChannelResources', project.id, activeChannelId] })
    },
    onError: (error) => {
      console.error('Failed to link resource:', error)
      alert('Unable to link this resource right now.')
    },
  })

  const deleteResourceMutation = useMutation({
    mutationFn: async (resourceId: string) => {
      if (!activeChannelId) throw new Error('Channel not selected')
      await projectDiscussionAPI.deleteChannelResource(project.id, activeChannelId, resourceId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionChannelResources', project.id, activeChannelId] })
    },
    onError: (error) => {
      console.error('Failed to unlink resource:', error)
      alert('Unable to unlink this resource right now.')
    },
  })

  const handleDismissAllPapers = () => {
    // Only clear the notification text, keep papers for the discovery panel
    setDiscoveryQueue((prev) => ({
      ...prev,
      notification: null,
    }))
    // Mark this channel as having dismissed notification bar (prevents re-showing)
    // Papers remain accessible via the Discoveries menu
    if (activeChannelId) {
      setDismissedNotificationChannels(prev => new Set([...prev, activeChannelId]))
    }
  }

  const assistantMutation = useMutation({
    mutationFn: async (variables: {
      id: string
      question: string
      reasoning: boolean
      scope: string[]
      recentSearchResults?: Array<{ title: string; authors?: string; year?: number; source?: string }>
      conversationHistory?: Array<{ role: string; content: string }>
    }) => {
      if (!activeChannelId) throw new Error('Channel not selected')

      const url = buildApiUrl(
        `/projects/${project.id}/discussion/channels/${activeChannelId}/assistant?stream=true`,
      )
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      }

      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
      if (token) {
        headers.Authorization = `Bearer ${token}`
      }

      const body = JSON.stringify({
        question: variables.question,
        reasoning: variables.reasoning,
        scope: variables.scope,
        recent_search_results: variables.recentSearchResults,
        conversation_history: variables.conversationHistory,
      })

      // Create abort controller for this request
      assistantAbortController.current = new AbortController()
      const signal = assistantAbortController.current.signal

      const execute = async () =>
        fetch(url, {
          method: 'POST',
          headers,
          body,
          credentials: 'include',
          signal,
        })

      let response = await execute()

      if (response.status === 401 || response.status === 403) {
        try {
          const refreshed = await refreshAuthToken()
          headers.Authorization = `Bearer ${refreshed}`
          response = await execute()
        } catch (refreshError) {
          console.error('Assistant auth refresh failed', refreshError)
          throw new Error('Assistant authentication failed; please sign in again.')
        }
      }

      if (!response.ok) {
        throw new Error(`Assistant request failed with status ${response.status}`)
      }

      const contentType = response.headers.get('content-type') || ''
      if (!response.body || !contentType.includes('text/event-stream')) {
        const json = (await response.json()) as DiscussionAssistantResponse
        return json
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      let rawText = ''
      let finalPayload: DiscussionAssistantResponse | null = null

      const buildFallback = (message?: string): DiscussionAssistantResponse => {
        const partial = stripActionsBlock(rawText)
        const fallbackMessage = message
          ? partial
            ? `${partial}\n\n_${message}_`
            : message
          : partial
        return {
          message: fallbackMessage || 'Scholar AI did not return a response.',
          citations: [],
          reasoning_used: variables.reasoning,
          model: '',
          usage: undefined,
          suggested_actions: [],
        }
      }

      outer: while (true) {
        const { value, done } = await reader.read()
        if (done) {
          break
        }
        buffer += decoder.decode(value, { stream: true })

        while (true) {
          const separatorIndex = buffer.indexOf('\n\n')
          if (separatorIndex === -1) {
            break
          }

          const rawEvent = buffer.slice(0, separatorIndex)
          buffer = buffer.slice(separatorIndex + 2)

          const dataLine = rawEvent.split('\n').find((line) => line.startsWith('data:'))
          if (!dataLine) {
            continue
          }

          const payloadText = dataLine.replace(/^data:\s*/, '').trim()
          if (!payloadText) {
            continue
          }

          try {
            const event = JSON.parse(payloadText) as {
              type: string
              content?: string
              payload?: DiscussionAssistantResponse
              message?: string
              tool?: string
            }

            if (event.type === 'token' && typeof event.content === 'string') {
              streamingFlags.current[variables.id] = true
              rawText += event.content
              const partial = stripActionsBlock(rawText)
              setAssistantHistory((prev) =>
                prev.map((entry) =>
                  entry.id === variables.id
                    ? {
                        ...entry,
                        displayMessage: partial,
                        status: 'streaming',
                        statusMessage: undefined, // Clear status when tokens start streaming
                      }
                    : entry,
                ),
              )
            } else if (event.type === 'status' && event.message) {
              // Update status message to show what the AI is doing
              setAssistantHistory((prev) =>
                prev.map((entry) =>
                  entry.id === variables.id
                    ? {
                        ...entry,
                        statusMessage: event.message,
                      }
                    : entry,
                ),
              )
            } else if (event.type === 'result' && event.payload) {
              finalPayload = event.payload
            } else if (event.type === 'error') {
              const errMessage = event.message?.trim() || 'Scholar AI encountered an issue while replying.'
              finalPayload = buildFallback(errMessage)
              break outer
            }
          } catch (parseError) {
            console.error('Failed to parse assistant stream event', parseError)
          }
        }
      }

      if (buffer.trim()) {
        try {
          const residual = buffer.trim()
          if (residual.startsWith('data:')) {
            const payloadText = residual.replace(/^data:\s*/, '').trim()
            if (payloadText) {
              const event = JSON.parse(payloadText)
              if (event?.type === 'result' && event.payload) {
                finalPayload = event.payload as DiscussionAssistantResponse
              }
            }
          }
        } catch (parseError) {
          console.error('Failed to parse trailing assistant stream event', parseError)
        }
      }

      try {
        await reader.cancel()
      } catch (cancelError) {
        console.debug('Assistant stream reader cancel failed (safe to ignore)', cancelError)
      }

      if (!finalPayload) {
        finalPayload = buildFallback()
      }

      return finalPayload
    },
    onMutate: async (variables) => {
      if (!activeChannelId) {
        throw new Error('Channel not selected')
      }
      const entryId = variables.id || createAssistantEntryId()
      const placeholder: AssistantExchange = {
        id: entryId,
        channelId: activeChannelId, // Track which channel this exchange belongs to
        question: variables.question,
        response: {
          message: '',
          citations: [],
          reasoning_used: variables.reasoning,
          model: '',
          usage: undefined,
          suggested_actions: [],
        },
        createdAt: new Date(),
        appliedActions: [],
        status: 'pending',
        displayMessage: '',
        author: {
          id: user?.id,
          name: {
            display: viewerDisplayName,
            first: user?.first_name,
            last: user?.last_name,
          },
        },
        fromHistory: false, // Created in current session, can auto-trigger
      }
      setAssistantHistory((prev) => [...prev, placeholder])
      return { entryId, channelId: activeChannelId }
    },
    onSuccess: (data, variables, context) => {
      const entryId = context?.entryId || createAssistantEntryId()
      const originalChannelId = context?.channelId
      const finishedAt = new Date()

      // CRITICAL: If user switched channels while request was processing, don't add to wrong channel
      // BUT we still need to store search results for the original channel
      if (originalChannelId && originalChannelId !== activeChannelId) {
        // Store any search_results in the original channel before returning
        const searchResultsAction = data.suggested_actions?.find(
          (action: DiscussionAssistantSuggestedAction) => action.action_type === 'search_results'
        )
        if (searchResultsAction) {
          const payload = searchResultsAction.payload as { query?: string; papers?: DiscoveredPaper[] } | undefined
          const papers = payload?.papers || []
          const query = payload?.query || ''
          if (papers.length > 0) {
            // Clear old ingestion status when new search results arrive
            setIngestionStatesByChannel(prev => {
              const next = { ...prev }
              delete next[originalChannelId]
              return next
            })
            // Clear dismissed notification state for this channel (new search = show new results)
            setDismissedNotificationChannels(prev => {
              const next = new Set(prev)
              next.delete(originalChannelId)
              return next
            })
            // Clear dismissed paper IDs - new search results shouldn't be affected by old dismissals
            setDismissedPaperIds(new Set())
            // Store results for the ORIGINAL channel
            setSearchResultsByChannel(prev => ({
              ...prev,
              [originalChannelId]: {
                exchangeId: entryId,
                papers: papers,
                query: query,
                isSearching: false,
              }
            }))
            // Also store in discovery queue for original channel
            setDiscoveryQueueByChannel(prev => ({
              ...prev,
              [originalChannelId]: {
                papers: papers,
                query: query,
                isSearching: false,
                notification: `Found ${papers.length} paper${papers.length !== 1 ? 's' : ''} for "${query}"`,
              }
            }))
          }
        }
        return
      }

      // First update the exchange in history so it has the response with suggested_actions
      setAssistantHistory((prev) => {
      const exists = prev.some((entry) => entry.id === entryId)
      if (!exists) {
        return [
          ...prev,
          {
            id: entryId,
            channelId: originalChannelId || activeChannelId || '', // Track which channel this exchange belongs to
            question: variables.question,
            response: data,
            createdAt: finishedAt,
            completedAt: finishedAt,
            appliedActions: [],
            status: 'streaming',
            displayMessage: '',
            author: {
              id: user?.id,
              name: {
                display: viewerDisplayName,
                first: user?.first_name,
                last: user?.last_name,
              },
            },
            fromHistory: false, // Created in current session, can auto-trigger
          },
        ]
      }

        return prev.map((entry) =>
          entry.id === entryId
            ? {
                ...entry,
                response: data,
                completedAt: finishedAt,
                status: 'streaming',
                displayMessage: streamingFlags.current[entryId] ? entry.displayMessage : '',
                author:
                  entry.author || {
                    id: user?.id,
                    name: {
                      display: viewerDisplayName,
                      first: user?.first_name,
                      last: user?.last_name,
                    },
                  },
              }
            : entry,
        )
      })

      // Process search_results AFTER history update so exchange has suggested_actions when rendering
      const searchResultsAction = data.suggested_actions?.find(
        (action: DiscussionAssistantSuggestedAction) => action.action_type === 'search_results'
      )
      if (searchResultsAction && originalChannelId) {
        const payload = searchResultsAction.payload as { query?: string; papers?: DiscoveredPaper[] } | undefined
        const papers = payload?.papers || []
        const query = payload?.query || ''
        if (papers.length > 0) {
          // Clear old ingestion status when new search results arrive
          setIngestionStatesByChannel(prev => {
            const next = { ...prev }
            delete next[originalChannelId]
            return next
          })
          // Clear dismissed paper IDs - new search results shouldn't be affected by old dismissals
          setDismissedPaperIds(new Set())
          setSearchResultsByChannel(prev => ({
            ...prev,
            [originalChannelId]: {
              exchangeId: entryId,
              papers: papers,
              query: query,
              isSearching: false,
            }
          }))
          setDiscoveryQueueByChannel(prev => ({
            ...prev,
            [originalChannelId]: {
              papers: papers,
              query: query,
              isSearching: false,
              notification: `Found ${papers.length} paper${papers.length !== 1 ? 's' : ''} for "${query}"`,
            }
          }))
        }
      }

      // Process library_update immediately so ingestion status shows without delay
      const libraryUpdateAction = data.suggested_actions?.find(
        (action: DiscussionAssistantSuggestedAction) => action.action_type === 'library_update'
      )
      if (libraryUpdateAction && originalChannelId) {
        const payload = libraryUpdateAction.payload as { updates?: { index: number; reference_id: string; ingestion_status: string }[] } | undefined
        const updates = payload?.updates || []
        if (updates.length > 0) {
          // Clear dismissed state so notification shows
          setDismissedNotificationChannels(prev => {
            const next = new Set(prev)
            next.delete(originalChannelId)
            return next
          })
          // Convert index-based updates to paper ID-based ingestion states
          // Get papers from discoveryQueueByChannel or searchResultsByChannel
          const channelPapers = discoveryQueueByChannel[originalChannelId]?.papers ||
            searchResultsByChannel[originalChannelId]?.papers || []
          setIngestionStatesByChannel(prev => {
            const channelStates = prev[originalChannelId] || {}
            const newStates = { ...channelStates }
            for (const u of updates) {
              const paper = channelPapers[u.index]
              if (paper) {
                newStates[paper.id] = {
                  referenceId: u.reference_id,
                  status: u.ingestion_status as IngestionStatus,
                  isAdding: false,
                }
              }
            }
            return { ...prev, [originalChannelId]: newStates }
          })
        }
      }

      const lookup = buildCitationLookup(data.citations)
      const formatted = formatAssistantMessage(data.message, lookup)
      const wasStreamed = streamingFlags.current[entryId]
      if (wasStreamed) {
        setAssistantHistory((prev) =>
          prev.map((entry) =>
            entry.id === entryId
              ? {
                  ...entry,
                  displayMessage: formatted,
                  status: 'complete',
                  completedAt: entry.completedAt ?? finishedAt,
                  author:
                    entry.author || {
                      id: user?.id,
                      name: {
                        display: viewerDisplayName,
                        first: user?.first_name,
                        last: user?.last_name,
                      },
                    },
                }
              : entry,
          ),
        )
        delete streamingFlags.current[entryId]
        return
      }

      startTypewriter(entryId, formatted)
    },
    onError: (error, _variables, context) => {
      // Don't show error for cancelled requests
      if (error instanceof Error && error.name === 'AbortError') {
        console.log('Assistant request was cancelled')
        if (context?.entryId) {
          setAssistantHistory((prev) => prev.filter((entry) => entry.id !== context.entryId))
          delete streamingFlags.current[context.entryId]
        }
        return
      }
      console.error('Failed to invoke assistant:', error)
      if (context?.entryId) {
        setAssistantHistory((prev) => prev.filter((entry) => entry.id !== context.entryId))
        delete streamingFlags.current[context.entryId]
      }
      alert('Unable to reach Scholar AI right now. Please try again.')
    },
  })

  // Cancel the current assistant request
  const cancelAssistantRequest = useCallback(() => {
    if (assistantAbortController.current) {
      assistantAbortController.current.abort()
      assistantAbortController.current = null
    }
  }, [])

  const markActionApplied = useCallback((exchangeId: string, actionKey: string) => {
    setAssistantHistory((prev) =>
      prev.map((entry) =>
        entry.id === exchangeId
          ? { ...entry, appliedActions: [...entry.appliedActions, actionKey] }
          : entry,
      ),
    )
  }, [])

  // Check if user's message is actually a search request (not just a conversational response)
  const isSearchRequest = (userQuestion: string): boolean => {
    const q = userQuestion.toLowerCase().trim()
    // Must contain search-related keywords to be considered a search request
    const searchKeywords = [
      'search', 'find', 'look for', 'looking for', 'papers', 'references',
      'articles', 'literature', 'publications', 'research on', 'about'
    ]
    // Research question patterns that trigger deep search
    const researchQuestionKeywords = [
      'what are the', 'what is the', 'how do', 'how does', 'how are',
      'main approaches', 'approaches to', 'methods for', 'techniques for',
      'state of the art', 'state-of-the-art', 'overview', 'comprehensive',
      'survey', 'review of', 'summary of', 'explain', 'describe'
    ]
    // Short messages or confirmations are NOT search requests
    if (q.length < 10) return false
    // Skip pure conversational responses (but NOT "please search...", "please find..." which are valid)
    if (/^(yes|no|ok|okay|sure|thanks|thank you|i want|i need|option|a|b|c|\d+)(\s|$)/i.test(q)) return false
    // Must have at least one search keyword OR be a research question
    return searchKeywords.some(kw => q.includes(kw)) || researchQuestionKeywords.some(kw => q.includes(kw))
  }

  // Extract search topic from user's original question ONLY if it's clearly a search request
  // Returns empty string if not a search request, so AI's query from action payload is used instead
  const extractSearchTopic = (userQuestion: string): string => {
    // Only extract topic if user explicitly asked for a search
    const patterns = [
      /(?:search|find|look)\s+(?:for\s+)?(?:\d+\s+)?(?:papers?|references?|articles?)?\s*(?:about|on|regarding|related to)\s+(.+)/i,
      /(?:papers?|references?|articles?)\s+(?:about|on|regarding)\s+(.+)/i,
      /(?:search|find|look)\s+(?:for\s+)?(?:\d+\s+)?(?:papers?|references?|articles?)\s+(?:on|about)\s+(.+)/i,
    ]
    for (const pattern of patterns) {
      const match = userQuestion.match(pattern)
      if (match && match[1]) {
        return match[1].trim()
      }
    }
    // If user didn't explicitly ask for a search, return empty so AI's query is used
    return ''
  }

  // Auto-trigger search_references and batch_search_references actions when AI suggests them
  // search_results actions are processed even for history entries (papers already in payload)
  useEffect(() => {
    // Find exchanges with search actions that haven't been applied yet
    for (const exchange of assistantHistory) {
      if (exchange.status !== 'complete') continue

      const actions = exchange.response?.suggested_actions || []
      for (let idx = 0; idx < actions.length; idx++) {
        const action = actions[idx]
        const actionKey = `${exchange.id}:${idx}`
        if (exchange.appliedActions.includes(actionKey)) continue

        // Handle search_results - papers already fetched by backend, just display them
        if (action.action_type === 'search_results') {
          const payload = action.payload as { query?: string; papers?: DiscoveredPaper[]; total_found?: number } | undefined
          const papers = payload?.papers || []
          const query = payload?.query || ''
          if (papers.length === 0) continue

          // Only process if exchange belongs to current channel
          if (!activeChannelId) continue
          if (exchange.channelId && exchange.channelId !== activeChannelId) continue

          // Check if user has dismissed notifications for this channel
          const isChannelDismissed = dismissedNotificationChannels.has(activeChannelId)

          // For history entries + dismissed channel, skip restoring discoveryQueue
          // For fresh responses, clear dismissed state so notification shows
          if (isChannelDismissed) {
            if (exchange.fromHistory) {
              // History entry - keep notification hidden, but still populate discoveryQueue
              // so papers are accessible in the Discovery drawer
              // Always mark action as applied to prevent re-processing
              markActionApplied(exchange.id, actionKey)
              // Always use current action's papers (newer exchanges overwrite older ones)
              setReferenceSearchResults({
                exchangeId: exchange.id,
                channelId: activeChannelId,
                papers: papers,
                query: query,
                isSearching: false,
              })
              // Populate discoveryQueue so papers show in drawer (notification bar stays hidden)
              setDiscoveryQueue({
                papers: papers,
                query: query,
                isSearching: false,
                notification: null, // No notification since channel is dismissed
              })
              continue
            } else {
              // Fresh response - clear dismissed state so notification shows
              setDismissedNotificationChannels(prev => {
                const next = new Set(prev)
                next.delete(activeChannelId)
                return next
              })
              // Clear dismissed paper IDs - new search results shouldn't be affected by old dismissals
              setDismissedPaperIds(new Set())
            }
          }

          // Always mark action as applied to prevent re-processing on next render
          markActionApplied(exchange.id, actionKey)

          // Clear old ingestion status so search results notification shows
          setIngestionStatesByChannel(prev => {
            const next = { ...prev }
            delete next[activeChannelId]
            return next
          })

          // Always use current action's papers (newer exchanges overwrite older ones)
          setReferenceSearchResults({
            exchangeId: exchange.id,
            channelId: activeChannelId,
            papers: papers,
            query: query,
            isSearching: false,
          })

          // Restore discoveryQueue.papers so notification bar shows them
          setDiscoveryQueue({
            papers: papers,
            query: query,
            isSearching: false,
            notification: `Found ${papers.length} papers`,
          })
          // Continue to process all actions - React batches state updates
          continue
        }

        // Handle library_update - auto-apply ingestion status from AI's add_to_library
        if (action.action_type === 'library_update') {
          console.log('[ProjectDiscussion] Found library_update action:', action)
          const payload = action.payload as { updates?: { index: number; reference_id: string; ingestion_status: string }[] } | undefined
          const updates = payload?.updates || []

          // Only process if exchange belongs to current channel
          if (!activeChannelId) {
            console.log('[ProjectDiscussion] Skipping - no activeChannelId')
            continue
          }
          if (exchange.channelId && exchange.channelId !== activeChannelId) {
            console.log('[ProjectDiscussion] Skipping - channel mismatch:', exchange.channelId, 'vs', activeChannelId)
            continue
          }

          // Check if there's a NEWER exchange with search_results - if so, skip this old library_update
          // This prevents old ingestion notifications from overwriting new search results
          const exchangeIndex = assistantHistory.findIndex(e => e.id === exchange.id)
          const hasNewerSearchResults = assistantHistory.slice(exchangeIndex + 1).some(laterExchange => {
            if (laterExchange.status !== 'complete') return false
            const laterActions = laterExchange.response?.suggested_actions || []
            return laterActions.some(a => a.action_type === 'search_results')
          })
          if (hasNewerSearchResults) {
            console.log('[ProjectDiscussion] Skipping old library_update - newer search_results exists')
            markActionApplied(exchange.id, actionKey)
            continue
          }

          // For history entries, skip if user dismissed notifications for this channel
          // For fresh responses, always show and clear dismissed state
          if (exchange.fromHistory && dismissedNotificationChannels.has(activeChannelId)) {
            console.log('[ProjectDiscussion] Skipping history library_update - channel dismissed:', activeChannelId)
            continue
          }

          // Fresh library_update - clear dismissed state so notification shows
          if (!exchange.fromHistory && dismissedNotificationChannels.has(activeChannelId)) {
            setDismissedNotificationChannels(prev => {
              const next = new Set(prev)
              next.delete(activeChannelId)
              return next
            })
          }

          markActionApplied(exchange.id, actionKey)
          console.log('[ProjectDiscussion] Processing', updates.length, 'library updates for channel', activeChannelId)

          if (updates.length > 0) {
            // Convert index-based updates to paper ID-based ingestion states
            const channelPapers = discoveryQueue.papers.length > 0
              ? discoveryQueue.papers
              : (discoveryQueueByChannel[activeChannelId]?.papers || searchResultsByChannel[activeChannelId]?.papers || [])
            setIngestionStatesByChannel(prev => {
              const channelStates = prev[activeChannelId] || {}
              const newStates = { ...channelStates }
              for (const u of updates) {
                const paper = channelPapers[u.index]
                if (paper) {
                  newStates[paper.id] = {
                    referenceId: u.reference_id,
                    status: u.ingestion_status as IngestionStatus,
                    isAdding: false,
                  }
                }
              }
              return { ...prev, [activeChannelId]: newStates }
            })
          }
          // Continue to process all actions - React batches state updates
          continue
        }

        // Handle single search_references (legacy - triggers frontend search)
        // ONLY auto-trigger if user's message looks like a search request
        // This prevents triggering on conversational responses like "yes", "i want", "one page"
        // Skip for history entries - don't re-trigger API calls when returning to page
        if (action.action_type === 'search_references') {
          if (exchange.fromHistory) continue  // Don't re-trigger for history
          // Skip if user's message wasn't a search request
          if (!isSearchRequest(exchange.question)) continue
          // Extract topic from user's original question (AI tends to over-expand)
          const userTopic = extractSearchTopic(exchange.question)
          const query = userTopic || String(action.payload?.query || '').trim()
          if (!query) continue
          const openAccessOnly = Boolean(action.payload?.open_access_only)
          const maxResults = Number(action.payload?.max_results) || 10
          markActionApplied(exchange.id, actionKey)
          searchReferencesMutation.mutate({
            query,
            exchangeId: exchange.id,
            openAccessOnly,
            maxResults,
          })
          return // Only trigger one at a time
        }

        // Handle batch_search_references (multi-topic search)
        // Skip for history entries - don't re-trigger API calls when returning to page
        if (action.action_type === 'batch_search_references') {
          if (exchange.fromHistory) continue  // Don't re-trigger for history
          const queries = action.payload?.queries as Array<{ topic: string; query: string; max_results?: number }> | undefined
          if (!queries || queries.length === 0) continue
          const openAccessOnly = Boolean(action.payload?.open_access_only)
          markActionApplied(exchange.id, actionKey)

          // Set searching state
          const batchQuery = queries.map(q => q.topic).join(', ')
          if (!activeChannelId) continue
          // Clear dismissed state for this channel - new search should show results
          setDismissedNotificationChannels(prev => {
            const next = new Set(prev)
            next.delete(activeChannelId)
            return next
          })
          setReferenceSearchResults({
            exchangeId: exchange.id,
            channelId: activeChannelId,
            papers: [],
            query: batchQuery,
            isSearching: true,
          })
          setDiscoveryQueue(() => ({
            papers: [],
            query: batchQuery,
            isSearching: true,
            notification: `Searching ${queries.length} topics...`,
          }))

          // Execute batch search
          projectDiscussionAPI.batchSearchReferences(project.id, queries, { openAccessOnly })
            .then((response) => {
              // Flatten all papers from all topics
              const allPapers = response.data.results.flatMap(result =>
                result.papers.map(paper => ({
                  ...paper,
                  _topic: result.topic, // Tag with topic for display
                }))
              )
              // Update reference search results - replace, not accumulate
              setReferenceSearchResults({
                exchangeId: exchange.id,
                channelId: activeChannelId || '',
                papers: allPapers,
                query: batchQuery,
                isSearching: false,
              })
              // Update discovery queue - replace, not accumulate
              setDiscoveryQueue({
                papers: allPapers,
                query: batchQuery,
                isSearching: false,
                notification: `Found ${allPapers.length} paper${allPapers.length !== 1 ? 's' : ''} across ${queries.length} topics`,
              })
            })
            .catch((error) => {
              console.error('Auto batch search failed:', error)
              const currentResults = activeChannelId ? searchResultsByChannel[activeChannelId] : null
              if (currentResults) {
                setReferenceSearchResults({
                  exchangeId: exchange.id,
                  channelId: activeChannelId || '',
                  papers: currentResults.papers,
                  query: currentResults.query,
                  isSearching: false,
                })
              }
              setDiscoveryQueue(prev => ({
                papers: prev?.papers ?? [],
                query: prev?.query ?? '',
                isSearching: false,
                notification: 'Batch search failed. Please try again.',
              }))
            })
          return // Only trigger one at a time
        }

        // Handle paper_updated - refresh paper view when AI updates a paper
        if (action.action_type === 'paper_updated') {
          markActionApplied(exchange.id, actionKey)
          // Invalidate paper queries to refresh the view
          queryClient.invalidateQueries({ queryKey: ['papers', project.id] })
          queryClient.invalidateQueries({ queryKey: ['paper'] })
          // Continue processing other actions (don't return)
        }
      }
    }
  }, [assistantHistory, markActionApplied, searchReferencesMutation, project.id, queryClient, activeChannelId, searchResultsByChannel, setReferenceSearchResults])

  const handleSuggestedAction = (
    exchange: AssistantExchange,
    action: DiscussionAssistantSuggestedAction,
    index: number,
  ) => {
    if (!activeChannelId) {
      alert('Select a channel before accepting assistant suggestions.')
      return
    }

    const actionKey = `${exchange.id}:${index}`
    if (exchange.appliedActions.includes(actionKey)) {
      return
    }

    if (action.action_type === 'create_task') {
      const title = String(action.payload?.title || '').trim()
      if (!title) {
        alert('The assistant suggestion is missing a task title. Please create the task manually.')
        return
      }
      const description = action.payload?.description ? String(action.payload.description) : undefined
      const messageId = action.payload?.message_id ? String(action.payload.message_id) : undefined
      if (!window.confirm(`Create task "${title}"?`)) {
        return
      }
      const taskPayload: DiscussionTaskCreate = {
        title,
        description: description || undefined,
        message_id: messageId || undefined,
      }
      createTaskMutation.mutate(taskPayload, {
        onSuccess: () => markActionApplied(exchange.id, actionKey),
        onError: (error) => {
          console.error('Failed to create task from assistant suggestion:', error)
          alert('Unable to create task right now. Please try again.')
        },
      })
      return
    }

    if (action.action_type === 'create_paper') {
      const title = String(action.payload?.title || '').trim()
      const paperType = String(action.payload?.paper_type || 'research').trim()
      const authoringMode = String(action.payload?.authoring_mode || 'latex').trim()
      const abstract = String(action.payload?.abstract || '').trim()
      const suggestedKeywords = Array.isArray(action.payload?.keywords) ? action.payload.keywords : []

      // Open the paper creation dialog instead of directly creating
      setPaperCreationDialog({
        open: true,
        exchangeId: exchange.id,
        actionIndex: index,
        suggestedTitle: title,
        suggestedType: paperType,
        suggestedMode: authoringMode,
        suggestedAbstract: abstract,
        suggestedKeywords: suggestedKeywords,
      })
      // Initialize form with suggested values
      setPaperFormData({
        title: title,
        paperType: paperType,
        authoringMode: authoringMode,
        abstract: abstract,
        keywords: suggestedKeywords,
        objectives: [],
      })
      return
    }

    if (action.action_type === 'edit_paper') {
      const paperId = action.payload?.paper_id
      const original = String(action.payload?.original || '').trim()
      const proposed = String(action.payload?.proposed || '').trim()
      const description = String(action.payload?.description || 'Apply suggested edit')
      if (!paperId || !original || !proposed) {
        alert('The assistant suggestion is missing required edit information.')
        return
      }
      if (!window.confirm(`Apply edit: ${description}?`)) {
        return
      }
      paperActionMutation.mutate(
        { actionType: 'edit_paper', payload: action.payload as Record<string, unknown> },
        {
          onSuccess: (data) => {
            if (data.success) {
              markActionApplied(exchange.id, actionKey)
              alert('Edit applied successfully!')
            } else {
              alert(data.message || 'Failed to apply edit')
            }
          },
        }
      )
      return
    }

    if (action.action_type === 'search_references') {
      // Extract topic from user's original question (AI tends to over-expand)
      const userTopic = extractSearchTopic(exchange.question)
      const query = userTopic || String(action.payload?.query || '').trim()
      if (!query) {
        alert('The assistant suggestion is missing a search query.')
        return
      }
      const openAccessOnly = Boolean(action.payload?.open_access_only)
      const maxResults = Number(action.payload?.max_results) || 10
      // Mark action as applied immediately (search is being triggered)
      markActionApplied(exchange.id, actionKey)
      // Trigger the search
      searchReferencesMutation.mutate({
        query,
        exchangeId: exchange.id,
        openAccessOnly,
        maxResults,
      })
      return
    }

    // Handle batch search across multiple topics
    if (action.action_type === 'batch_search_references') {
      const queries = action.payload?.queries as Array<{ topic: string; query: string; max_results?: number }> | undefined
      if (!queries || queries.length === 0) {
        alert('The batch search is missing queries.')
        return
      }
      const openAccessOnly = Boolean(action.payload?.open_access_only)
      markActionApplied(exchange.id, actionKey)

      // Clear dismissed state for this channel - new search should show results
      if (activeChannelId) {
        setDismissedNotificationChannels(prev => {
          const next = new Set(prev)
          next.delete(activeChannelId)
          return next
        })
      }

      // Set searching state
      const batchQuery = queries.map(q => q.topic).join(', ')
      setReferenceSearchResults({
        exchangeId: exchange.id,
        channelId: activeChannelId || '',
        papers: [],
        query: batchQuery,
        isSearching: true,
      })
      setDiscoveryQueue(() => ({
        papers: [],
        query: batchQuery,
        isSearching: true,
        notification: `Searching ${queries.length} topics...`,
      }))

      // Execute batch search
      projectDiscussionAPI.batchSearchReferences(project.id, queries, { openAccessOnly })
        .then((response) => {
          // Flatten all papers from all topics
          const allPapers = response.data.results.flatMap(result =>
            result.papers.map(paper => ({
              ...paper,
              _topic: result.topic, // Tag with topic for display
            }))
          )
          // Update reference search results - replace, not accumulate
          setReferenceSearchResults({
            exchangeId: exchange.id,
            channelId: activeChannelId || '',
            papers: allPapers,
            query: batchQuery,
            isSearching: false,
          })
          // Update discovery queue - replace, not accumulate
          setDiscoveryQueue({
            papers: allPapers,
            query: batchQuery,
            isSearching: false,
            notification: `Found ${allPapers.length} paper${allPapers.length !== 1 ? 's' : ''} across ${queries.length} topics`,
          })
        })
        .catch((error) => {
          console.error('Batch search failed:', error)
          const currentResults = activeChannelId ? searchResultsByChannel[activeChannelId] : null
          if (currentResults) {
            setReferenceSearchResults({
              exchangeId: exchange.id,
              channelId: activeChannelId || '',
              papers: currentResults.papers,
              query: currentResults.query,
              isSearching: false,
            })
          }
          setDiscoveryQueue(prev => ({
            papers: prev?.papers ?? [],
            query: prev?.query ?? '',
            isSearching: false,
            notification: 'Batch search failed. Please try again.',
          }))
          alert('Batch search failed. Please try again.')
        })
      return
    }

    // Handle paper_updated - paper was already updated, just refresh view
    if (action.action_type === 'paper_updated') {
      markActionApplied(exchange.id, actionKey)
      queryClient.invalidateQueries({ queryKey: ['papers', project.id] })
      queryClient.invalidateQueries({ queryKey: ['paper'] })
      return
    }

    // Handle search_results - papers already fetched, just display them
    if (action.action_type === 'search_results') {
      const payload = action.payload as { query?: string; papers?: DiscoveredPaper[]; total_found?: number } | undefined
      const papers = payload?.papers || []
      const query = payload?.query || ''
      markActionApplied(exchange.id, actionKey)

      // Display results in Discovery Queue panel - replace, not accumulate
      // Only show if exchange belongs to current channel
      if (papers.length > 0 && (!exchange.channelId || exchange.channelId === activeChannelId)) {
        setReferenceSearchResults({
          exchangeId: exchange.id,
          channelId: activeChannelId || '',
          papers: papers,  // Replace with new papers
          query: query,
          isSearching: false,
        })
        // Also replace discoveryQueue (not accumulate)
        setDiscoveryQueue({
          papers: papers,
          query: query,
          isSearching: false,
          notification: `Found ${papers.length} papers`,
        })
      }
      return
    }

    // Handle library_update - ingestion status updates from AI's add_to_library tool
    if (action.action_type === 'library_update') {
      const payload = action.payload as { updates?: { index: number; reference_id: string; ingestion_status: string }[] } | undefined
      const updates = payload?.updates || []
      markActionApplied(exchange.id, actionKey)

      if (updates.length > 0 && activeChannelId) {
        // Convert index-based updates to paper ID-based ingestion states
        const channelPapers = discoveryQueue.papers.length > 0
          ? discoveryQueue.papers
          : (discoveryQueueByChannel[activeChannelId]?.papers || searchResultsByChannel[activeChannelId]?.papers || [])
        setIngestionStatesByChannel(prev => {
          const channelStates = prev[activeChannelId] || {}
          const newStates = { ...channelStates }
          for (const u of updates) {
            const paper = channelPapers[u.index]
            if (paper) {
              newStates[paper.id] = {
                referenceId: u.reference_id,
                status: u.ingestion_status as IngestionStatus,
                isAdding: false,
              }
            }
          }
          return { ...prev, [activeChannelId]: newStates }
        })
      }
      return
    }

    if (action.action_type === 'artifact_created') {
      const title = String(action.payload?.title || 'download').trim()
      const filename = String(action.payload?.filename || `${title}.md`).trim()
      const contentBase64 = String(action.payload?.content_base64 || '')
      const mimeType = String(action.payload?.mime_type || 'text/plain')

      if (!contentBase64) {
        alert('The artifact is missing content.')
        return
      }

      // Properly decode base64 to binary and trigger download
      try {
        const binaryString = atob(contentBase64)
        const bytes = new Uint8Array(binaryString.length)
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i)
        }
        const blob = new Blob([bytes], { type: mimeType })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        markActionApplied(exchange.id, actionKey)
        // Refresh artifacts panel to show the new artifact
        queryClient.invalidateQueries({ queryKey: ['channel-artifacts', project.id, activeChannelId] })
      } catch (e) {
        console.error('Failed to decode artifact:', e)
        alert('Failed to download artifact.')
      }
      return
    }

    alert('This assistant suggestion type is not yet supported.')
  }

  // Create message mutation
  const createMessageMutation = useMutation({
    mutationFn: async (content: string) => {
      const response = await projectDiscussionAPI.createMessage(project.id, {
        content,
        channel_id: activeChannelId ?? undefined,
        parent_id: replyingTo?.id || null,
      })
      return response.data
    },
    onSuccess: (createdMessage) => {
      if (activeChannelId) {
        queryClient.setQueryData<DiscussionThreadType[] | undefined>(
          ['projectDiscussion', project.id, activeChannelId],
          (existingThreads) => {
            const threads = existingThreads ?? []

            if (!createdMessage.parent_id) {
              const alreadyExists = threads.some((thread) => thread.message.id === createdMessage.id)
              if (alreadyExists) {
                return threads
              }

              const newThread: DiscussionThreadType = {
                message: createdMessage,
                replies: [],
              }
              return [newThread, ...threads]
            }

            let updated = false
            const nextThreads = threads.map((thread) => {
              if (thread.message.id !== createdMessage.parent_id) {
                return thread
              }

              const replies = thread.replies ?? []
              if (replies.some((reply) => reply.id === createdMessage.id)) {
                return thread
              }

              updated = true
              const sortedReplies = [...replies, createdMessage].sort(
                (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
              )

              return {
                ...thread,
                message: {
                  ...thread.message,
                  reply_count: thread.message.reply_count + 1,
                },
                replies: sortedReplies,
              }
            })

            return updated ? nextThreads : threads
          },
        )
      }

      queryClient.invalidateQueries({ queryKey: ['projectDiscussion', project.id, activeChannelId] })
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionStats', project.id, activeChannelId] })
      setReplyingTo(null)
    },
    onError: (error) => {
      console.error('Failed to send message:', error)
      alert('Failed to send message. Please try again.')
    },
  })

  // Update message mutation
  const updateMessageMutation = useMutation({
    mutationFn: async ({ messageId, content }: { messageId: string; content: string }) => {
      const response = await projectDiscussionAPI.updateMessage(project.id, messageId, { content })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussion', project.id, activeChannelId] })
      setEditingMessage(null)
    },
    onError: (error) => {
      console.error('Failed to update message:', error)
      alert('Failed to update message. Please try again.')
    },
  })

  // Delete message mutation
  const deleteMessageMutation = useMutation({
    mutationFn: async (messageId: string) => {
      await projectDiscussionAPI.deleteMessage(project.id, messageId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussion', project.id, activeChannelId] })
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionStats', project.id, activeChannelId] })
    },
    onError: (error) => {
      console.error('Failed to delete message:', error)
      alert('Failed to delete message. Please try again.')
    },
  })

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversationItems])

  // Save assistant history to localStorage - only trigger on assistantHistory changes
  // Use ref to track which channel the history belongs to, not activeChannelId dependency
  useEffect(() => {
    if (typeof window === 'undefined') return
    const channelId = historyChannelRef.current
    if (!channelId) return

    const storageKey = buildStorageKey(channelId)
    if (!storageKey) return

    const payload = assistantHistory.map((entry) => ({
      ...entry,
      createdAt: entry.createdAt.toISOString(),
      completedAt: entry.completedAt ? entry.completedAt.toISOString() : null,
    }))

    try {
      window.localStorage.setItem(storageKey, JSON.stringify(payload))
    } catch (error) {
      console.error('Failed to persist assistant history', error)
    }
  }, [assistantHistory, buildStorageKey])

  const handleSendMessage = (content: string) => {
    const trimmed = content.trim()
    if (!trimmed) return

    // Slash commands trigger the assistant
    if (trimmed.startsWith('/')) {
      if (!activeChannelId) {
        alert('Select a channel before asking Scholar AI.')
        return
      }
      // Prevent double-submit while AI is processing
      if (assistantMutation.isPending) {
        return
      }
      const commandBody = trimmed.slice(1).trim()
      if (!commandBody) {
        alert('Add a command after the slash (e.g., /reason What should we do next?).')
        return
      }

      const firstSpace = commandBody.indexOf(' ')
      const keyword = (firstSpace === -1 ? commandBody : commandBody.slice(0, firstSpace)).toLowerCase()
      const remainder = firstSpace === -1 ? '' : commandBody.slice(firstSpace + 1).trim()

      let question = commandBody
      let reasoning = assistantReasoning
      if (keyword === 'reason' || keyword === 'reasoning' || keyword === 'r') {
        reasoning = true
        question = remainder
      } else {
        const lowered = commandBody.toLowerCase()
        if (lowered.startsWith('reason ')) {
          reasoning = true
          question = commandBody.slice(7).trim()
        } else if (lowered.startsWith('reasoning ')) {
          reasoning = true
          question = commandBody.slice(10).trim()
        }
      }

      if (!question) {
        alert('Add a question after the slash (e.g., /reason What is next?) to ask Scholar AI.')
        return
      }
      const entryId = createAssistantEntryId()
      // Pass recent search results for conversational context
      // Prefer reference search results first, fall back to discovery queue
      const papersToSend = (referenceSearchResults?.papers?.length ?? 0) > 0
        ? referenceSearchResults?.papers ?? []
        : discoveryQueue.papers
      const recentSearchResults = papersToSend.map((p) => ({
        title: p.title,
        authors: p.authors?.slice(0, 3).join(', '),
        year: p.year,
        source: p.source,
        abstract: p.abstract,
        doi: p.doi,
        url: p.url,
        pdf_url: p.pdf_url,
        is_open_access: p.is_open_access,
      }))
      // Build conversation history from previous exchanges
      const conversationHistory: Array<{ role: string; content: string }> = []
      for (const exchange of assistantHistory) {
        if (exchange.question) {
          conversationHistory.push({ role: 'user', content: exchange.question })
        }
        if (exchange.response?.message) {
          conversationHistory.push({ role: 'assistant', content: exchange.response.message })
        }
      }
      assistantMutation.mutate({ id: entryId, question, reasoning, scope: assistantScope, recentSearchResults, conversationHistory })
      // Don't clear search results here - they will be replaced when new search results arrive
      // This keeps previous search results visible until a new paper search completes
      return
    }

    if (!activeChannelId && !editingMessage) {
      alert('Select a channel before sending messages.')
      return
    }

    if (editingMessage) {
      updateMessageMutation.mutate({ messageId: editingMessage.id, content: trimmed })
    } else {
      createMessageMutation.mutate(trimmed)
    }
  }

  const handleReply = (message: DiscussionMessage) => {
    setReplyingTo({ id: message.id, userName: message.user.name || message.user.email })
    setEditingMessage(null)
  }

  const handleEdit = (message: DiscussionMessage) => {
    setEditingMessage({ id: message.id, content: message.content })
    setReplyingTo(null)
  }

  const handleDelete = (messageId: string) => {
    if (window.confirm('Are you sure you want to delete this message?')) {
      deleteMessageMutation.mutate(messageId)
    }
  }

  const handleCancelReply = () => {
    setReplyingTo(null)
  }

  const handleCancelEdit = () => {
    setEditingMessage(null)
  }

  const handleOpenCreateChannel = () => {
    setNewChannelName('')
    setNewChannelDescription('')
    setNewChannelScope(null)
    setIsCreateChannelModalOpen(true)
  }

  const toggleScopeResource = (
    type: 'paper' | 'reference' | 'meeting',
    id: string,
    setScope: React.Dispatch<React.SetStateAction<ChannelScopeConfig | null>>
  ) => {
    setScope((prev) => {
      const keyMap = { paper: 'paper_ids', reference: 'reference_ids', meeting: 'meeting_ids' } as const
      const key = keyMap[type]

      if (prev === null) {
        // Switching from project-wide to specific scope
        return { [key]: [id] } as ChannelScopeConfig
      }

      const currentIds = prev[key] || []
      if (currentIds.includes(id)) {
        const filtered = currentIds.filter((existingId) => existingId !== id)
        const newScope = { ...prev, [key]: filtered.length > 0 ? filtered : null }
        // If all scope arrays are empty/null, return null (project-wide)
        const hasAny = newScope.paper_ids?.length || newScope.reference_ids?.length || newScope.meeting_ids?.length
        return hasAny ? newScope : null
      }

      return { ...prev, [key]: [...currentIds, id] }
    })
  }

  const handleCloseCreateChannel = () => {
    setIsCreateChannelModalOpen(false)
  }

  const handleCreateChannelSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!newChannelName.trim()) {
      alert('Channel name is required.')
      return
    }

    createChannelMutation.mutate({
      name: newChannelName.trim(),
      description: newChannelDescription.trim() || undefined,
      scope: newChannelScope,
    })
  }

  const activeChannel = channels.find((channel) => channel.id === activeChannelId) ?? null
  const hasAssistantHistory = assistantHistory.length > 0

  const renderDiscussionContent = () => {
    if (isLoading || channelsQuery.isLoading) {
      return (
        <div className="flex h-full items-center justify-center px-4">
          <div className="text-center">
            <Loader2 className="mx-auto h-6 w-6 sm:h-8 sm:w-8 animate-spin text-indigo-600 dark:text-indigo-300" />
            <p className="mt-2 text-xs sm:text-sm text-gray-600 dark:text-slate-300">Loading discussion...</p>
          </div>
        </div>
      )
    }

    if (isError) {
      return (
        <div className="flex h-full items-center justify-center px-4">
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 sm:p-4 text-center dark:border-red-500/40 dark:bg-red-500/10">
            <AlertCircle className="mx-auto h-6 w-6 sm:h-8 sm:w-8 text-red-600 dark:text-red-300" />
            <p className="mt-2 text-xs sm:text-sm font-medium text-red-900 dark:text-red-200">Failed to load discussion</p>
            <p className="mt-1 text-[10px] sm:text-xs text-red-700 dark:text-red-200/80">{(error as Error)?.message || 'Please try again later'}</p>
          </div>
        </div>
      )
    }

    const hasThreads = orderedThreads.length > 0
    if (!hasThreads && !hasAssistantHistory) {
      return (
        <div className="flex h-full items-center justify-center px-4">
          <div className="text-center">
            <MessageCircle className="mx-auto h-10 w-10 sm:h-12 sm:w-12 text-gray-300 dark:text-slate-600" />
            <h3 className="mt-3 sm:mt-4 text-xs sm:text-sm font-medium text-gray-900 dark:text-slate-100">No messages yet</h3>
            <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-slate-400">Start the conversation by sending a message or ask Scholar AI for help.</p>
          </div>
        </div>
      )
    }

    return (
      <div className="space-y-4">
        {conversationItems.map((item) => {
          if (item.kind === 'assistant') {
            const { exchange } = item
          const citationLookup = buildCitationLookup(exchange.response.citations)
          const formattedMessage = formatAssistantMessage(exchange.response.message, citationLookup)
          const askedLabel = formatDistanceToNow(exchange.createdAt, { addSuffix: true })
          const answerLabel = exchange.completedAt
            ? formatDistanceToNow(exchange.completedAt, { addSuffix: true })
            : askedLabel
          const displayedMessage = exchange.displayMessage || formattedMessage
          const showTyping = !displayedMessage && exchange.status !== 'complete'
          const authorLabel = resolveAuthorLabel(exchange.author)
          const avatarText = authorLabel.trim().charAt(0).toUpperCase() || 'U'
          const promptBubbleClass = 'inline-block max-w-full sm:max-w-fit rounded-xl sm:rounded-2xl bg-purple-50/70 px-3 py-1.5 sm:px-4 sm:py-2 shadow-sm ring-2 ring-purple-200 transition dark:bg-purple-500/15 dark:ring-purple-400/40 dark:shadow-purple-900/30'
          const responseBubbleClass = 'inline-block max-w-full sm:max-w-fit rounded-xl sm:rounded-2xl bg-white px-3 py-1.5 sm:px-4 sm:py-2 transition dark:bg-slate-800/70 dark:ring-1 dark:ring-slate-700'
          return (
            <div key={exchange.id} className="border-b border-gray-100 pb-3 sm:pb-4 last:border-b-0 dark:border-slate-700">
              <div className="space-y-3 sm:space-y-4 pt-3 sm:pt-4">
                <div className="flex items-start gap-2 sm:gap-3">
                  <div className="flex h-6 w-6 sm:h-8 sm:w-8 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs sm:text-sm font-medium text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-200">
                    {avatarText}
                  </div>
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="mb-1 flex flex-wrap items-center gap-1.5 sm:gap-2">
                      <span className="text-xs sm:text-sm font-medium text-gray-900">{authorLabel}</span>
                      <span className="text-[10px] sm:text-xs text-gray-500">{askedLabel}</span>
                      <span className="inline-flex items-center gap-0.5 sm:gap-1 rounded-full bg-indigo-100 px-1.5 py-0.5 text-[9px] sm:text-[10px] font-medium text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200">
                        <Bot className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                        AI prompt
                      </span>
                    </div>
                    <div className={promptBubbleClass}>
                      <p className="text-xs sm:text-sm text-gray-700 break-words">{exchange.question}</p>
                    </div>
                  </div>
                </div>
                <div className="flex items-start gap-2 sm:gap-3">
                  <div className="flex h-6 w-6 sm:h-8 sm:w-8 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs sm:text-sm font-medium text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-200">
                    AI
                  </div>
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="mb-1 flex flex-wrap items-center gap-1.5 sm:gap-2">
                      <span className="text-xs sm:text-sm font-medium text-gray-900">Scholar AI</span>
                      <span className="text-[10px] sm:text-xs text-gray-500">{answerLabel}</span>
                      {exchange.response.reasoning_used && (
                        <span className="inline-flex items-center gap-0.5 sm:gap-1 rounded-full bg-emerald-50 px-1.5 py-0.5 text-[9px] sm:text-[10px] font-medium text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-200">
                          <Sparkles className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                          Reasoning
                        </span>
                      )}
                    </div>
                    <div className={responseBubbleClass}>
                      {showTyping ? (
                        <div className="space-y-3">
                          <div className="flex items-center gap-3">
                            <div className="flex items-center gap-2.5 text-sm font-medium text-indigo-600 dark:text-indigo-300">
                              <div className="relative">
                                <Loader2 className="h-4 w-4 animate-spin" />
                              </div>
                              <span>{exchange.statusMessage || 'Thinking'}...</span>
                            </div>
                            <button
                              onClick={cancelAssistantRequest}
                              className="ml-auto flex h-6 w-6 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
                              title="Cancel"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <div className="h-1 w-1 animate-pulse rounded-full bg-indigo-400 dark:bg-indigo-500" style={{ animationDelay: '0ms' }} />
                            <div className="h-1 w-1 animate-pulse rounded-full bg-indigo-400 dark:bg-indigo-500" style={{ animationDelay: '150ms' }} />
                            <div className="h-1 w-1 animate-pulse rounded-full bg-indigo-400 dark:bg-indigo-500" style={{ animationDelay: '300ms' }} />
                          </div>
                        </div>
                      ) : (
                        <div className="prose prose-sm max-w-none text-gray-900 prose-headings:text-gray-900 prose-p:leading-relaxed prose-li:marker:text-gray-400 dark:prose-invert prose-p:text-xs sm:prose-p:text-sm prose-headings:text-sm sm:prose-headings:text-base prose-li:text-xs sm:prose-li:text-sm">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {displayedMessage}
                          </ReactMarkdown>
                        </div>
                      )}
                    </div>
                    {!showTyping && exchange.response.citations.length > 0 && (
                      <div className="mt-2 sm:mt-3 space-y-1 sm:space-y-1.5">
                        <p className="text-[10px] sm:text-xs font-medium text-slate-500 dark:text-slate-400">Sources Used:</p>
                        <div className="flex flex-wrap gap-1.5 sm:gap-2">
                          {exchange.response.citations.map((citation) => {
                            const getResourceIcon = (resourceType?: string) => {
                              switch (resourceType) {
                                case 'paper':
                                  return <FileText className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-blue-500" />
                                case 'reference':
                                  return <BookOpen className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-emerald-500" />
                                case 'meeting':
                                  return <Calendar className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-purple-500" />
                                default:
                                  return <FileText className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-slate-400" />
                              }
                            }
                            return (
                              <div
                                key={`${exchange.id}-${citation.origin}-${citation.origin_id}`}
                                className="inline-flex items-center gap-1 sm:gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-1.5 py-1 sm:px-2.5 sm:py-1.5 text-[10px] sm:text-xs dark:border-slate-700 dark:bg-slate-800"
                              >
                                {getResourceIcon(citation.resource_type ?? undefined)}
                                <span className="font-medium text-slate-700 dark:text-slate-200 truncate max-w-[100px] sm:max-w-none">
                                  {citation.label}
                                </span>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )}
                    {/* Paper created/updated actions - show View/Write buttons */}
                    {!showTyping && exchange.response.suggested_actions?.some(a => a.action_type === 'paper_created' || a.action_type === 'paper_updated') && (
                      <div className="mt-2 sm:mt-3 flex flex-wrap gap-1.5 sm:gap-2">
                        {exchange.response.suggested_actions
                          .filter(a => a.action_type === 'paper_created' || a.action_type === 'paper_updated')
                          .map((action, idx) => {
                            const urlId = action.payload?.url_id || action.payload?.paper_id
                            const title = action.payload?.title || 'Paper'
                            return (
                              <div key={idx} className="inline-flex items-center gap-1.5 sm:gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1.5 sm:px-3 sm:py-2 dark:border-emerald-400/30 dark:bg-emerald-500/10">
                                <FileText className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
                                <span className="text-xs sm:text-sm font-medium text-emerald-700 dark:text-emerald-300 truncate max-w-[100px] sm:max-w-[200px]">{title}</span>
                                <div className="ml-1 sm:ml-2 flex gap-0.5 sm:gap-1 flex-shrink-0">
                                  <button
                                    onClick={() => navigate(`/projects/${getProjectUrlId(project)}/papers/${urlId}`)}
                                    className="rounded px-1.5 py-0.5 text-[10px] sm:text-xs font-medium text-emerald-600 hover:bg-emerald-100 dark:text-emerald-400 dark:hover:bg-emerald-500/20"
                                  >
                                    View
                                  </button>
                                  <button
                                    onClick={() => navigate(`/projects/${getProjectUrlId(project)}/papers/${urlId}/editor`)}
                                    className="rounded px-1.5 py-0.5 text-[10px] sm:text-xs font-medium text-emerald-600 hover:bg-emerald-100 dark:text-emerald-400 dark:hover:bg-emerald-500/20"
                                  >
                                    Write
                                  </button>
                                </div>
                              </div>
                            )
                          })}
                      </div>
                    )}
                    {!showTyping && exchange.response.suggested_actions && exchange.response.suggested_actions.filter(a =>
                      a.action_type !== 'paper_created' &&
                      a.action_type !== 'paper_updated' &&
                      a.action_type !== 'library_update' &&
                      a.action_type !== 'search_results'
                    ).length > 0 && (
                      <div className="mt-2 space-y-1">
                        <p className="text-[10px] sm:text-[11px] uppercase tracking-wide text-gray-400">Suggested actions</p>
                        <div className="flex flex-wrap gap-1.5 sm:gap-2">
                          {exchange.response.suggested_actions.filter(a =>
                            // Filter out internal actions that update UI but shouldn't show as suggested actions
                            a.action_type !== 'paper_created' &&
                            a.action_type !== 'paper_updated' &&
                            a.action_type !== 'library_update' &&
                            a.action_type !== 'search_results'
                          ).map((action, idx) => {
                            const actionKey = `${exchange.id}:${idx}`
                            const applied = exchange.appliedActions.includes(actionKey)
                            const isPending = createTaskMutation.isPending || paperActionMutation.isPending || searchReferencesMutation.isPending
                            const getActionIcon = () => {
                              if (applied) return <Check className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                              switch (action.action_type) {
                                case 'create_paper': return <FilePlus className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                                case 'edit_paper': return <Pencil className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                                case 'paper_updated': return <FileText className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                                case 'create_task': return <CheckSquare className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                                case 'search_references': return <Search className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                                case 'artifact_created': return <Download className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                                default: return <Sparkles className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                              }
                            }
                            return (
                              <button
                                key={actionKey}
                                type="button"
                                onClick={() => handleSuggestedAction(exchange, action, idx)}
                                disabled={applied || isPending}
                                className={`inline-flex items-center gap-1 sm:gap-1.5 rounded-full border px-2 py-0.5 sm:px-3 sm:py-1 text-[10px] sm:text-xs font-medium transition ${applied ? 'border-emerald-300 bg-emerald-50 text-emerald-600 dark:border-emerald-400/40 dark:bg-emerald-500/20 dark:text-emerald-200' : 'border-indigo-200 bg-white text-indigo-600 hover:bg-indigo-50 dark:border-indigo-400/40 dark:bg-slate-800/70 dark:text-indigo-200 dark:hover:bg-indigo-500/10'}`}
                              >
                                {getActionIcon()}
                                <span className="truncate max-w-[80px] sm:max-w-none">{applied ? 'Applied' : action.summary}</span>
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    )}
                    {!showTyping && (
                      <div className="mt-1.5 sm:mt-2 flex flex-wrap items-center gap-2 sm:gap-3 text-[9px] sm:text-[11px] text-gray-400 dark:text-slate-500">
                        {exchange.response.model && <span className="hidden sm:inline">Model: {exchange.response.model}</span>}
                        {exchange.response.usage && typeof exchange.response.usage['total_tokens'] === 'number' && (
                          <span className="hidden sm:inline">Total tokens: {exchange.response.usage['total_tokens'] as number}</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )
          }

          const { thread } = item
          return (
            <DiscussionThread
              key={thread.message.id}
              thread={thread}
              currentUserId={user?.id || ''}
              onReply={handleReply}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          )
        })}
        <div ref={messagesEndRef} />
      </div>
    )
  }

  const handleToggleArchive = (channel: DiscussionChannelSummary) => {
    if (channel.is_default) return
    const action = channel.is_archived ? 'unarchive' : 'archive'
    if (!window.confirm(`Are you sure you want to ${action} “${channel.name}”?`)) {
      return
    }

    updateChannelMutation.mutate({
      channelId: channel.id,
      payload: { is_archived: !channel.is_archived },
    })
  }

  // Close mobile sidebar when a channel is selected
  const handleMobileChannelSelect = (channelId: string) => {
    setActiveChannelId(channelId)
    setIsMobileSidebarOpen(false)
  }

  return (
    <>
      {/* Mobile sidebar overlay */}
      {isMobileSidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden touch-manipulation"
          onClick={() => setIsMobileSidebarOpen(false)}
        />
      )}

      {/* Mobile sidebar drawer */}
      <div
        className={`fixed inset-y-0 left-0 z-50 w-72 transform transition-transform duration-300 ease-in-out md:hidden ${
          isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex h-full flex-col bg-white dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-slate-700">
            <span className="text-sm font-semibold text-gray-800 dark:text-slate-100">Channels</span>
            <button
              type="button"
              onClick={() => setIsMobileSidebarOpen(false)}
              className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:text-slate-400 dark:hover:bg-slate-800 touch-manipulation"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto overscroll-contain">
            <DiscussionChannelSidebar
              channels={channels}
              activeChannelId={activeChannelId}
              onSelectChannel={handleMobileChannelSelect}
              onCreateChannel={handleOpenCreateChannel}
              isCreating={createChannelMutation.isPending}
              onArchiveToggle={handleToggleArchive}
              onOpenSettings={(channel) => {
                setSettingsChannel(channel)
                setIsChannelSettingsOpen(true)
                setIsMobileSidebarOpen(false)
              }}
              showArchived={showArchivedChannels}
              onToggleShowArchived={() => setShowArchivedChannels((prev) => !prev)}
            />
          </div>
        </div>
      </div>

      <div className="flex h-[calc(100vh-120px)] sm:h-[calc(100vh-140px)] md:h-[calc(100vh-160px)] min-h-[20rem] sm:min-h-[24rem] md:min-h-[32rem] w-full gap-2 md:gap-3 overflow-hidden">
        {/* Desktop sidebar - hidden on mobile */}
        <div className="hidden md:block flex-shrink-0">
          <DiscussionChannelSidebar
            channels={channels}
            activeChannelId={activeChannelId}
            onSelectChannel={setActiveChannelId}
            onCreateChannel={handleOpenCreateChannel}
            isCreating={createChannelMutation.isPending}
            onArchiveToggle={handleToggleArchive}
            onOpenSettings={(channel) => {
              setSettingsChannel(channel)
              setIsChannelSettingsOpen(true)
            }}
            showArchived={showArchivedChannels}
            onToggleShowArchived={() => setShowArchivedChannels((prev) => !prev)}
          />
        </div>

        <div className="flex flex-1 min-h-0 min-w-0 flex-col rounded-xl md:rounded-2xl border border-gray-200 bg-white shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900/40">
          <div className="flex items-center justify-between border-b border-gray-200 px-2 py-2 sm:px-3 sm:py-3 md:p-4 dark:border-slate-700">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              {/* Mobile menu button */}
              <button
                type="button"
                onClick={() => setIsMobileSidebarOpen(true)}
                className="flex-shrink-0 rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 md:hidden dark:text-slate-400 dark:hover:bg-slate-800 touch-manipulation"
              >
                <Menu className="h-5 w-5" />
              </button>
              <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                <div className="flex items-center gap-1.5 sm:gap-2">
                  {activeChannel && (
                    <Hash className="h-4 w-4 flex-shrink-0 text-indigo-500 dark:text-indigo-400" />
                  )}
                  <h2 className="text-sm sm:text-base md:text-lg font-semibold text-gray-900 dark:text-slate-100 truncate">
                    {activeChannel ? activeChannel.name : 'Project Discussion'}
                  </h2>
                  {activeChannel?.is_default && (
                    <span className="hidden sm:inline flex-shrink-0 rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
                      Default
                    </span>
                  )}
                  {activeChannel?.is_archived && (
                    <span className="hidden sm:inline flex-shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-700 dark:bg-amber-500/20 dark:text-amber-300">
                      Archived
                    </span>
                  )}
                </div>
                {activeChannel?.description && (
                  <p className="hidden md:block text-xs text-gray-500 dark:text-slate-400 truncate">{activeChannel.description}</p>
                )}
              </div>
            </div>
            {activeChannel && (
              <div className="flex items-center gap-1.5 sm:gap-2 text-sm text-gray-600 dark:text-slate-400 flex-shrink-0">
                {/* Channel actions dropdown menu */}
                <div className="relative" ref={channelMenuRef}>
                  <button
                    type="button"
                    onClick={() => setChannelMenuOpen(!channelMenuOpen)}
                    className="inline-flex items-center gap-1 rounded-lg border border-gray-200 p-1.5 sm:p-2 text-gray-600 transition hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                    {pendingTasksCount > 0 && (
                      <span className="ml-0.5 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-indigo-500 px-1 text-[10px] font-semibold text-white">
                        {pendingTasksCount}
                      </span>
                    )}
                    {artifactsCount > 0 && (
                      <span className="ml-0.5 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-emerald-500 px-1 text-[10px] font-semibold text-white">
                        {artifactsCount}
                      </span>
                    )}
                    {!isChannelSwitching && discoveryQueue.papers.length > 0 && (
                      <span className="ml-0.5 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-semibold text-white">
                        {discoveryQueue.papers.length}
                      </span>
                    )}
                  </button>

                  {channelMenuOpen && (
                    <div className="absolute right-0 top-full z-50 mt-1 w-44 sm:w-48 rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800">
                      {activeChannel.scope && (
                        <button
                          type="button"
                          onClick={() => {
                            setOpenDialog('resources')
                            setChannelMenuOpen(false)
                          }}
                          className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 transition hover:bg-gray-50 dark:text-slate-200 dark:hover:bg-slate-700"
                        >
                          <FolderOpen className="h-4 w-4 text-indigo-500" />
                          Channel resources
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => {
                          setOpenDialog('tasks')
                          setChannelMenuOpen(false)
                        }}
                        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-sm text-gray-700 transition hover:bg-gray-50 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        <div className="flex items-center gap-2">
                          <ListTodo className="h-4 w-4 text-indigo-500" />
                          Channel tasks
                        </div>
                        {pendingTasksCount > 0 && (
                          <span className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-indigo-500 px-1.5 text-[10px] font-semibold text-white">
                            {pendingTasksCount}
                          </span>
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setOpenDialog('artifacts')
                          setChannelMenuOpen(false)
                        }}
                        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-sm text-gray-700 transition hover:bg-gray-50 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        <div className="flex items-center gap-2">
                          <Puzzle className="h-4 w-4 text-emerald-500" />
                          Artifacts
                        </div>
                        {artifactsCount > 0 && (
                          <span className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-emerald-500 px-1.5 text-[10px] font-semibold text-white">
                            {artifactsCount}
                          </span>
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setOpenDialog('discoveries')
                          setChannelMenuOpen(false)
                        }}
                        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-sm text-gray-700 transition hover:bg-gray-50 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        <div className="flex items-center gap-2">
                          <Search className="h-4 w-4 text-amber-500" />
                          Discoveries
                        </div>
                        {!isChannelSwitching && discoveryQueue.papers.length > 0 && (
                          <span className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-amber-500 px-1.5 text-[10px] font-semibold text-white">
                            {discoveryQueue.papers.length}
                          </span>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {activeChannel ? (
            <>
              <div className="flex flex-1 min-h-0 overflow-hidden p-2 sm:p-3 md:p-4">
                <div className="flex-1 min-h-0 overflow-y-auto pr-1 sm:pr-2">
                  {renderDiscussionContent()}
                </div>
              </div>

              {/* Floating discovery notification bar - evolves based on state */}
              {!isChannelSwitching && (discoveryQueue.papers.length > 0 || ingestionSummary) && (
                <>
                  {/* State 1: Processing papers - blue progress bar (highest priority) */}
                  {ingestionSummary?.isProcessing ? (
                    <div className="mx-2 sm:mx-4 mb-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 sm:gap-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 sm:px-4 sm:py-2.5 shadow-sm dark:border-blue-500/30 dark:bg-blue-900/20">
                      <div className="flex items-center gap-2 sm:gap-3">
                        <div className="flex h-7 w-7 sm:h-8 sm:w-8 flex-shrink-0 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-500/20">
                          <Loader2 className="h-3.5 w-3.5 sm:h-4 sm:w-4 animate-spin text-blue-600 dark:text-blue-400" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs sm:text-sm font-medium text-blue-800 dark:text-blue-200">
                            Adding papers to library...
                          </p>
                          <p className="text-[10px] sm:text-xs text-blue-600 dark:text-blue-400">
                            {ingestionSummary.successCount} of {ingestionSummary.totalAdded} processed
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => setOpenDialog('discoveries')}
                        className="ml-auto rounded-lg border border-blue-300 px-2.5 py-1 sm:px-3 sm:py-1.5 text-[10px] sm:text-xs font-medium text-blue-700 transition hover:bg-blue-100 dark:border-blue-500/40 dark:text-blue-300 dark:hover:bg-blue-500/20"
                      >
                        View Progress
                      </button>
                    </div>
                  ) : ingestionSummary?.isAllSuccess ? (
                    /* State 2: All papers successfully added - green success bar */
                    <div className="mx-2 sm:mx-4 mb-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 sm:gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 sm:px-4 sm:py-2.5 shadow-sm dark:border-emerald-500/30 dark:bg-emerald-900/20">
                      <div className="flex items-center gap-2 sm:gap-3">
                        <div className="flex h-7 w-7 sm:h-8 sm:w-8 flex-shrink-0 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-500/20">
                          <CheckCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-emerald-600 dark:text-emerald-400" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs sm:text-sm font-medium text-emerald-800 dark:text-emerald-200">
                            {ingestionSummary.totalAdded} paper{ingestionSummary.totalAdded !== 1 ? 's' : ''} added to library
                          </p>
                          <p className="text-[10px] sm:text-xs text-emerald-600 dark:text-emerald-400">
                            All with full text available
                          </p>
                        </div>
                      </div>
                      <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
                        <button
                          type="button"
                          onClick={() => setOpenDialog('discoveries')}
                          className="rounded-lg border border-emerald-300 px-2.5 py-1 sm:px-3 sm:py-1.5 text-[10px] sm:text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 dark:border-emerald-500/40 dark:text-emerald-300 dark:hover:bg-emerald-500/20"
                        >
                          View Details
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (activeChannelId) {
                              setIngestionStatesByChannel(prev => {
                                const next = { ...prev }
                                delete next[activeChannelId]
                                return next
                              })
                              handleDismissAllPapers()
                            }
                          }}
                          className="rounded-lg px-2 py-1 sm:px-2 sm:py-1.5 text-[10px] sm:text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 dark:text-emerald-300 dark:hover:bg-emerald-500/20"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  ) : ingestionSummary && ingestionSummary.needsAttention > 0 ? (
                    /* State 3: Papers added but some need attention - amber warning bar */
                    <div className="mx-2 sm:mx-4 mb-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 sm:gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 sm:px-4 sm:py-2.5 shadow-sm dark:border-amber-500/30 dark:bg-amber-900/20">
                      <div className="flex items-center gap-2 sm:gap-3">
                        <div className="flex h-7 w-7 sm:h-8 sm:w-8 flex-shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-500/20">
                          <Library className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-amber-600 dark:text-amber-400" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs sm:text-sm font-medium text-amber-800 dark:text-amber-200">
                            <span className="hidden sm:inline">{ingestionSummary.totalAdded} added</span>
                            <span className="sm:hidden">{ingestionSummary.totalAdded} added</span>
                            {ingestionSummary.successCount > 0 && (
                              <span className="hidden sm:inline mx-1.5 text-emerald-600 dark:text-emerald-400">
                                • {ingestionSummary.successCount} full text
                              </span>
                            )}
                            {ingestionSummary.needsAttention > 0 && (
                              <span className="hidden sm:inline mx-1.5 text-amber-600 dark:text-amber-400">
                                • {ingestionSummary.needsAttention} need PDF
                              </span>
                            )}
                          </p>
                          <p className="text-[10px] sm:text-xs text-amber-600 dark:text-amber-400">
                            <span className="hidden sm:inline">Some papers need manual PDF upload</span>
                            <span className="sm:hidden">{ingestionSummary.needsAttention} need PDF upload</span>
                          </p>
                        </div>
                      </div>
                      <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
                        <button
                          type="button"
                          onClick={() => setOpenDialog('discoveries')}
                          className="rounded-lg bg-amber-600 px-2.5 py-1 sm:px-3 sm:py-1.5 text-[10px] sm:text-xs font-medium text-white transition hover:bg-amber-700 dark:bg-amber-500 dark:hover:bg-amber-600"
                        >
                          Review
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (activeChannelId) {
                              setIngestionStatesByChannel(prev => {
                                const next = { ...prev }
                                delete next[activeChannelId]
                                return next
                              })
                              handleDismissAllPapers()
                            }
                          }}
                          className="rounded-lg px-2 py-1 sm:px-2 sm:py-1.5 text-[10px] sm:text-xs font-medium text-amber-700 transition hover:bg-amber-100 dark:text-amber-300 dark:hover:bg-amber-500/20"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  ) : discoveryQueue.papers.length > 0 && activeChannelId && !dismissedNotificationChannels.has(activeChannelId) ? (
                    /* State 4: Papers found but not yet added - amber discovery bar (hidden if dismissed) */
                    <div className="mx-2 sm:mx-4 mb-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 sm:gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 sm:px-4 sm:py-2.5 shadow-sm dark:border-amber-500/30 dark:bg-amber-900/20">
                      <div className="flex items-center gap-2 sm:gap-3">
                        <div className="flex h-7 w-7 sm:h-8 sm:w-8 flex-shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-500/20">
                          <Search className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-amber-600 dark:text-amber-400" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs sm:text-sm font-medium text-amber-800 dark:text-amber-200">
                            {discoveryQueue.papers.length} paper{discoveryQueue.papers.length !== 1 ? 's' : ''} found
                          </p>
                          {discoveryQueue.query && (
                            <p className="text-[10px] sm:text-xs text-amber-600 dark:text-amber-400 truncate max-w-[150px] sm:max-w-none">
                              for "{discoveryQueue.query}"
                            </p>
                          )}
                          {dismissedInCurrentSearch > 0 && (
                            <button
                              type="button"
                              onClick={resetDismissedPapers}
                              className="text-[10px] sm:text-xs text-amber-500 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-300 underline"
                            >
                              Show {dismissedInCurrentSearch} dismissed
                            </button>
                          )}
                        </div>
                      </div>
                      <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
                        <button
                          type="button"
                          onClick={() => setOpenDialog('discoveries')}
                          className="rounded-lg bg-amber-600 px-2.5 py-1 sm:px-3 sm:py-1.5 text-[10px] sm:text-xs font-medium text-white transition hover:bg-amber-700 dark:bg-amber-500 dark:hover:bg-amber-600"
                        >
                          Review
                        </button>
                        <button
                          type="button"
                          onClick={handleDismissAllPapers}
                          className="rounded-lg px-2 py-1 sm:px-2 sm:py-1.5 text-[10px] sm:text-xs font-medium text-amber-700 transition hover:bg-amber-100 dark:text-amber-300 dark:hover:bg-amber-500/20"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  ) : null}
                </>
              )}

              <div className="border-t border-gray-100 bg-white px-2 py-1.5 sm:px-4 sm:py-2 text-xs text-gray-600 dark:border-slate-800 dark:bg-slate-900/40">
                <button
                  type="button"
                  onClick={() => setAiContextExpanded(!aiContextExpanded)}
                  className="flex w-full items-center gap-1.5 sm:gap-2 text-left"
                >
                  {aiContextExpanded ? (
                    <ChevronDown className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-gray-400 dark:text-slate-500" />
                  ) : (
                    <ChevronRight className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-gray-400 dark:text-slate-500" />
                  )}
                  <span className="text-[10px] sm:text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500">
                    AI Context
                  </span>
                  {!aiContextExpanded && (
                    <span className="text-[9px] sm:text-[10px] text-gray-400 dark:text-slate-500">
                      ({assistantScope.length} selected)
                    </span>
                  )}
                </button>
                {aiContextExpanded && (
                  <div className="mt-1.5 sm:mt-2 flex flex-col sm:flex-row sm:flex-wrap items-start sm:items-center justify-between gap-2 sm:gap-3">
                    <p className="text-[10px] sm:text-xs text-gray-500 dark:text-slate-400">Pick which resources the assistant can reference.</p>
                    <div className="flex flex-wrap gap-1.5 sm:gap-2">
                      {ASSISTANT_SCOPE_OPTIONS.map((option) => {
                        const active = assistantScope.includes(option.id)
                        return (
                          <button
                            key={option.id}
                            type="button"
                            onClick={() => toggleAssistantScope(option.id)}
                            className={`rounded-full px-2 py-0.5 sm:px-3 sm:py-1 text-[10px] sm:text-xs font-medium transition border ${
                              active
                                ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-500/20 dark:text-indigo-100'
                                : 'border-gray-200 text-gray-600 hover:border-indigo-200 hover:text-indigo-600 dark:border-slate-700 dark:text-slate-300 dark:hover:border-indigo-400/60'
                            }`}
                        >
                          {option.label}
                        </button>
                      )
                    })}
                    </div>
                  </div>
                )}
              </div>

              <MessageInput
                onSend={handleSendMessage}
                placeholder="Type a message… use / to ask Scholar AI for help"
                replyingTo={replyingTo}
                onCancelReply={handleCancelReply}
                editingMessage={editingMessage}
                onCancelEdit={handleCancelEdit}
                isSubmitting={createMessageMutation.isPending || updateMessageMutation.isPending}
                reasoningEnabled={assistantReasoning}
                onToggleReasoning={() => setAssistantReasoning((prev) => !prev)}
                reasoningPending={assistantMutation.isPending}
              />
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center px-4 sm:px-6 py-6 sm:py-10">
              <div className="max-w-md text-center">
                <MessageCircle className="mx-auto h-10 w-10 sm:h-12 sm:w-12 text-gray-300 dark:text-slate-600" />
                {channels.length === 0 ? (
                  <>
                    <h3 className="mt-3 sm:mt-4 text-sm sm:text-base font-semibold text-gray-900 dark:text-slate-100">Create a channel to start the conversation</h3>
                    <p className="mt-1.5 sm:mt-2 text-xs sm:text-sm text-gray-500 dark:text-slate-400">
                      Organize discussions by topic, meeting, or workstream. Once a channel is created, messages and AI tools will appear here.
                    </p>
                    <button
                      type="button"
                      onClick={handleOpenCreateChannel}
                      className="mt-3 sm:mt-4 inline-flex items-center gap-1.5 sm:gap-2 rounded-full border border-indigo-200 px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-indigo-600 transition hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
                    >
                      <Plus className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                      New channel
                    </button>
                  </>
                ) : (
                  <>
                    <h3 className="mt-3 sm:mt-4 text-sm sm:text-base font-semibold text-gray-900 dark:text-slate-100">Select a channel to view the conversation</h3>
                    <p className="mt-1.5 sm:mt-2 text-xs sm:text-sm text-gray-500 dark:text-slate-400">
                      <span className="hidden sm:inline">Choose a channel from the sidebar to see messages and start chatting with your team, or create a new channel to organize discussions.</span>
                      <span className="sm:hidden">Tap the menu icon to choose a channel and start chatting.</span>
                    </p>
                  </>
                )}
              </div>
            </div>
          )}
    </div>
  </div>

      {openDialog && activeChannel && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-gray-900/40 sm:px-4 backdrop-blur-sm dark:bg-black/70"
          onClick={() => setOpenDialog(null)}
        >
          <div
            className="relative w-full sm:max-w-3xl h-[85vh] sm:h-auto sm:max-h-[85vh] overflow-hidden rounded-t-2xl sm:rounded-2xl bg-white shadow-2xl transition-colors dark:bg-slate-900/90"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between border-b border-gray-200 px-4 py-3 sm:px-5 sm:py-4 dark:border-slate-700">
              <div className="min-w-0 flex-1 pr-2">
                <h3 className="text-base sm:text-lg font-semibold text-gray-900 dark:text-slate-100 truncate">
                  {openDialog === 'resources' ? 'Channel resources' : openDialog === 'artifacts' ? 'Channel artifacts' : openDialog === 'discoveries' ? 'Paper Discoveries' : 'Channel tasks'}
                </h3>
                <p className="text-[10px] sm:text-xs text-gray-500 dark:text-slate-400 truncate">
                  {openDialog === 'resources'
                    ? `Manage linked resources for ${activeChannel.name}`
                    : openDialog === 'artifacts'
                    ? `Generated files for ${activeChannel.name}`
                    : openDialog === 'discoveries'
                    ? `Papers found via AI search - add to your library`
                    : `Track action items for ${activeChannel.name}`}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpenDialog(null)}
                className="flex-shrink-0 inline-flex h-8 w-8 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-700"
                aria-label="Close channel dialog"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-3 sm:px-5 sm:py-4" style={{ maxHeight: 'calc(85vh - 70px)' }}>
              {openDialog === 'resources' ? (
                <ChannelResourcePanel
                  projectId={project.id}
                  loading={resourcesQuery.isLoading}
                  error={resourcesQuery.isError ? (resourcesQuery.error as Error) : null}
                  resources={resourcesQuery.data ?? []}
                  onCreateResource={(payload) => createResourceMutation.mutate(payload)}
                  onRemoveResource={(resourceId) => deleteResourceMutation.mutate(resourceId)}
                  isSubmitting={createResourceMutation.isPending || deleteResourceMutation.isPending}
                />
              ) : openDialog === 'artifacts' ? (
                <ChannelArtifactsPanel
                  projectId={project.id}
                  channelId={activeChannel.id}
                />
              ) : openDialog === 'discoveries' ? (
                <DiscoveryQueuePanel
                  papers={discoveryQueue.papers}
                  query={discoveryQueue.query}
                  projectId={project.id}
                  isSearching={discoveryQueue.isSearching}
                  notification={discoveryQueue.notification}
                  onDismiss={handleDismissPaper}
                  onDismissAll={handleDismissAllPapers}
                  onClearNotification={() => setDiscoveryQueue((prev) => ({ ...prev, notification: null }))}
                  ingestionStates={currentIngestionStates}
                  onIngestionStateChange={handleIngestionStateChange}
                />
              ) : (
                <ChannelTaskDrawer
                  tasks={tasksQuery.data ?? []}
                  loading={tasksQuery.isLoading || createTaskMutation.isPending}
                  error={tasksQuery.isError ? (tasksQuery.error as Error) : null}
                  onCreateTask={(payload) => createTaskMutation.mutate(payload)}
                  onUpdateTask={(taskId, payload) => updateTaskMutation.mutate({ taskId, payload })}
                  onDeleteTask={(taskId) => deleteTaskMutation.mutate(taskId)}
                  allowCreate={Boolean(activeChannelId)}
                  defaultMessageId={replyingTo?.id ?? editingMessage?.id ?? null}
                />
              )}
            </div>
          </div>
        </div>
      )}

      {isCreateChannelModalOpen && (
        <div className="fixed inset-0 z-40 flex items-end sm:items-center justify-center bg-gray-900/40 backdrop-blur-sm dark:bg-black/70">
          <div className="w-full sm:max-w-md max-h-[90vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl bg-white p-4 sm:p-6 shadow-xl transition-colors dark:bg-slate-900/90">
            <h3 className="text-base font-semibold text-gray-900 dark:text-slate-100">Create new channel</h3>
            <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-slate-400">
              Organize conversations by topic, meeting, or workstream.
            </p>
            <form className="mt-3 sm:mt-4 space-y-3 sm:space-y-4" onSubmit={handleCreateChannelSubmit}>
              <div>
                <label
                  htmlFor="channel-name"
                  className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300"
                >
                  Channel name
                </label>
                <input
                  id="channel-name"
                  type="text"
                  value={newChannelName}
                  onChange={(event) => setNewChannelName(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
                  placeholder="e.g. Brainstorming"
                  maxLength={255}
                  required
                />
              </div>

              <div>
                <label
                  htmlFor="channel-description"
                  className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300"
                >
                  Description <span className="text-gray-400 dark:text-slate-500">(optional)</span>
                </label>
                <textarea
                  id="channel-description"
                  value={newChannelDescription}
                  onChange={(event) => setNewChannelDescription(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
                  rows={3}
                  maxLength={2000}
                  placeholder="Describe the focus of this channel"
                />
              </div>

              <div>
                <label className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300">
                  AI Context Scope
                </label>
                <p className="mt-0.5 text-xs text-gray-500 dark:text-slate-400">
                  Choose which resources the AI can access in this channel
                </p>
                <div className="mt-2 space-y-2">
                  <button
                    type="button"
                    onClick={() => setNewChannelScope(null)}
                    className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition ${
                      newChannelScope === null
                        ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-500/20 dark:text-indigo-100'
                        : 'border-gray-200 text-gray-600 hover:border-gray-300 dark:border-slate-600 dark:text-slate-300 dark:hover:border-slate-500'
                    }`}
                  >
                    <span className="font-medium">Project-wide</span>
                    <span className="ml-1 text-xs opacity-70">(all papers, references, transcripts)</span>
                  </button>

                  {newChannelScope !== null && (
                    <div className="mt-3 max-h-64 overflow-y-auto rounded-lg border border-gray-200 dark:border-slate-700">
                      <ResourceScopePicker
                        scope={newChannelScope}
                        papers={availablePapersQuery.data || []}
                        references={availableReferencesQuery.data || []}
                        meetings={availableMeetingsQuery.data || []}
                        onToggle={(type, id) => toggleScopeResource(type, id, setNewChannelScope)}
                        isLoading={availablePapersQuery.isLoading || availableReferencesQuery.isLoading || availableMeetingsQuery.isLoading}
                      />
                    </div>
                  )}

                  {newChannelScope === null && (
                    <button
                      type="button"
                      onClick={() => setNewChannelScope({})}
                      className="text-xs text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
                    >
                      Or select specific resources...
                    </button>
                  )}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={handleCloseCreateChannel}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                  disabled={createChannelMutation.isPending}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createChannelMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300 dark:disabled:bg-indigo-500/40"
                >
                  {createChannelMutation.isPending && (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  )}
                  Create channel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {isChannelSettingsOpen && settingsChannel && (
        <ChannelSettingsModal
          channel={settingsChannel}
          onClose={() => {
            setIsChannelSettingsOpen(false)
            setSettingsChannel(null)
          }}
          onSave={(payload) => {
            updateChannelMutation.mutate({
              channelId: settingsChannel.id,
              payload,
            })
          }}
          onDelete={() => {
            deleteChannelMutation.mutate(settingsChannel.id)
          }}
          isSaving={updateChannelMutation.isPending}
          isDeleting={deleteChannelMutation.isPending}
          papers={availablePapersQuery.data || []}
          references={availableReferencesQuery.data || []}
          meetings={availableMeetingsQuery.data || []}
          isLoadingResources={availablePapersQuery.isLoading || availableReferencesQuery.isLoading || availableMeetingsQuery.isLoading}
        />
      )}

      {/* Paper Creation Dialog */}
      {paperCreationDialog?.open && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-gray-900/40 backdrop-blur-sm dark:bg-black/70">
          <div className="w-full sm:max-w-lg max-h-[90vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl bg-white p-4 sm:p-6 shadow-xl transition-colors dark:bg-slate-900/90">
            <div className="flex items-center justify-between mb-3 sm:mb-4">
              <h3 className="text-base sm:text-lg font-semibold text-gray-900 dark:text-slate-100">Create New Paper</h3>
              <button
                type="button"
                onClick={() => setPaperCreationDialog(null)}
                className="rounded-full p-1 hover:bg-gray-100 dark:hover:bg-slate-800"
              >
                <X className="h-5 w-5 text-gray-500" />
              </button>
            </div>

            <form onSubmit={handlePaperCreationSubmit} className="space-y-3 sm:space-y-4">
              {/* Title */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">
                  Paper Title <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={paperFormData.title}
                  onChange={(e) => setPaperFormData((prev) => ({ ...prev, title: e.target.value }))}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
                  placeholder="Enter paper title"
                  required
                />
              </div>

              {/* Paper Type & Authoring Mode */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Paper Type</label>
                  <select
                    value={paperFormData.paperType}
                    onChange={(e) => setPaperFormData((prev) => ({ ...prev, paperType: e.target.value }))}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
                  >
                    <option value="research">Research Paper</option>
                    <option value="review">Literature Review</option>
                    <option value="case_study">Case Study</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Authoring Mode</label>
                  <select
                    value={paperFormData.authoringMode}
                    onChange={(e) => setPaperFormData((prev) => ({ ...prev, authoringMode: e.target.value }))}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
                  >
                    <option value="latex">LaTeX</option>
                    <option value="rich">Rich Text</option>
                  </select>
                </div>
              </div>

              {/* Abstract */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Abstract (optional)</label>
                <textarea
                  value={paperFormData.abstract}
                  onChange={(e) => setPaperFormData((prev) => ({ ...prev, abstract: e.target.value }))}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
                  rows={2}
                  placeholder="Brief abstract or description"
                />
              </div>

              {/* Keywords */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Keywords</label>
                <div className="flex gap-2 mb-2">
                  <input
                    type="text"
                    value={keywordInput}
                    onChange={(e) => setKeywordInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        handleAddKeyword()
                      }
                    }}
                    className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
                    placeholder="Type keyword and press Enter"
                  />
                  <button
                    type="button"
                    onClick={handleAddKeyword}
                    className="rounded-lg border border-indigo-300 px-3 py-2 text-sm text-indigo-600 hover:bg-indigo-50 dark:border-indigo-500/40 dark:text-indigo-300 dark:hover:bg-indigo-500/10"
                  >
                    Add
                  </button>
                </div>
                {paperFormData.keywords.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {paperFormData.keywords.map((keyword) => (
                      <span
                        key={keyword}
                        className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200"
                      >
                        {keyword}
                        <button
                          type="button"
                          onClick={() => handleRemoveKeyword(keyword)}
                          className="ml-0.5 hover:text-indigo-900 dark:hover:text-indigo-100"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Objectives */}
              {projectObjectives.length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">
                    Paper Objectives (select from project)
                  </label>
                  <div className="max-h-32 overflow-y-auto rounded-lg border border-gray-200 dark:border-slate-700">
                    {projectObjectives.map((objective, idx) => {
                      const isSelected = paperFormData.objectives.includes(objective)
                      return (
                        <label
                          key={idx}
                          className="flex cursor-pointer items-center gap-2 px-3 py-2 hover:bg-gray-50 dark:hover:bg-slate-800"
                        >
                          <div
                            className={`flex h-4 w-4 items-center justify-center rounded border ${
                              isSelected
                                ? 'border-indigo-500 bg-indigo-500'
                                : 'border-gray-300 dark:border-slate-600'
                            }`}
                          >
                            {isSelected && <Check className="h-3 w-3 text-white" />}
                          </div>
                          <input
                            type="checkbox"
                            className="sr-only"
                            checked={isSelected}
                            onChange={() => handleToggleObjective(objective)}
                          />
                          <span className="text-sm text-gray-700 dark:text-slate-300">{objective}</span>
                        </label>
                      )
                    })}
                  </div>
                  <p className="mt-1 text-xs text-gray-500 dark:text-slate-400">
                    Selected: {paperFormData.objectives.length} objective{paperFormData.objectives.length !== 1 ? 's' : ''}
                  </p>
                </div>
              )}

              {/* Actions */}
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setPaperCreationDialog(null)}
                  className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={paperActionMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:bg-indigo-300 dark:disabled:bg-indigo-500/40"
                >
                  {paperActionMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Create Paper
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}

// Resource Scope Picker Component
const ResourceScopePicker = ({
  scope,
  papers,
  references,
  meetings,
  onToggle,
  isLoading,
}: {
  scope: ChannelScopeConfig
  papers: ResearchPaper[]
  references: ProjectReferenceSuggestion[]
  meetings: MeetingSummary[]
  onToggle: (type: 'paper' | 'reference' | 'meeting', id: string) => void
  isLoading: boolean
}) => {
  const [expandedSections, setExpandedSections] = useState<string[]>(['papers', 'references', 'meetings'])

  const toggleSection = (section: string) => {
    setExpandedSections((prev) =>
      prev.includes(section) ? prev.filter((s) => s !== section) : [...prev, section]
    )
  }

  const selectedPaperIds = new Set(scope.paper_ids || [])
  const selectedReferenceIds = new Set(scope.reference_ids || [])
  const selectedMeetingIds = new Set(scope.meeting_ids || [])

  const totalSelected = selectedPaperIds.size + selectedReferenceIds.size + selectedMeetingIds.size

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-4">
        <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        <span className="ml-2 text-sm text-gray-500">Loading resources...</span>
      </div>
    )
  }

  return (
    <div className="divide-y divide-gray-100 dark:divide-slate-700">
      {totalSelected > 0 && (
        <div className="bg-indigo-50 px-3 py-2 text-xs text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300">
          {totalSelected} resource{totalSelected !== 1 ? 's' : ''} selected
        </div>
      )}

      {/* Papers Section */}
      {papers.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => toggleSection('papers')}
            className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-slate-800"
          >
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-blue-500" />
              <span className="text-sm font-medium text-gray-700 dark:text-slate-200">Papers</span>
              {selectedPaperIds.size > 0 && (
                <span className="rounded-full bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700 dark:bg-blue-500/20 dark:text-blue-300">
                  {selectedPaperIds.size}
                </span>
              )}
            </div>
            <ChevronDown className={`h-4 w-4 text-gray-400 transition ${expandedSections.includes('papers') ? 'rotate-180' : ''}`} />
          </button>
          {expandedSections.includes('papers') && (
            <div className="space-y-1 px-3 pb-2">
              {papers.map((paper) => (
                <label
                  key={paper.id}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-slate-800"
                >
                  <div className={`flex h-4 w-4 items-center justify-center rounded border ${
                    selectedPaperIds.has(paper.id)
                      ? 'border-indigo-500 bg-indigo-500'
                      : 'border-gray-300 dark:border-slate-600'
                  }`}>
                    {selectedPaperIds.has(paper.id) && <Check className="h-3 w-3 text-white" />}
                  </div>
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={selectedPaperIds.has(paper.id)}
                    onChange={() => onToggle('paper', paper.id)}
                  />
                  <span className="text-sm text-gray-700 dark:text-slate-300 truncate">{paper.title || 'Untitled Paper'}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {/* References Section */}
      {references.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => toggleSection('references')}
            className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-slate-800"
          >
            <div className="flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-emerald-500" />
              <span className="text-sm font-medium text-gray-700 dark:text-slate-200">References</span>
              {selectedReferenceIds.size > 0 && (
                <span className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300">
                  {selectedReferenceIds.size}
                </span>
              )}
            </div>
            <ChevronDown className={`h-4 w-4 text-gray-400 transition ${expandedSections.includes('references') ? 'rotate-180' : ''}`} />
          </button>
          {expandedSections.includes('references') && (
            <div className="space-y-1 px-3 pb-2">
              {references.map((ref) => (
                <label
                  key={ref.reference_id}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-slate-800"
                >
                  <div className={`flex h-4 w-4 items-center justify-center rounded border ${
                    selectedReferenceIds.has(ref.reference_id)
                      ? 'border-indigo-500 bg-indigo-500'
                      : 'border-gray-300 dark:border-slate-600'
                  }`}>
                    {selectedReferenceIds.has(ref.reference_id) && <Check className="h-3 w-3 text-white" />}
                  </div>
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={selectedReferenceIds.has(ref.reference_id)}
                    onChange={() => onToggle('reference', ref.reference_id)}
                  />
                  <span className="text-sm text-gray-700 dark:text-slate-300 truncate">{ref.reference?.title || 'Untitled Reference'}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Meetings Section */}
      {meetings.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => toggleSection('meetings')}
            className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-slate-800"
          >
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-purple-500" />
              <span className="text-sm font-medium text-gray-700 dark:text-slate-200">Meetings</span>
              {selectedMeetingIds.size > 0 && (
                <span className="rounded-full bg-purple-100 px-1.5 py-0.5 text-xs text-purple-700 dark:bg-purple-500/20 dark:text-purple-300">
                  {selectedMeetingIds.size}
                </span>
              )}
            </div>
            <ChevronDown className={`h-4 w-4 text-gray-400 transition ${expandedSections.includes('meetings') ? 'rotate-180' : ''}`} />
          </button>
          {expandedSections.includes('meetings') && (
            <div className="space-y-1 px-3 pb-2">
              {meetings.map((meeting) => (
                <label
                  key={meeting.id}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-slate-800"
                >
                  <div className={`flex h-4 w-4 items-center justify-center rounded border ${
                    selectedMeetingIds.has(meeting.id)
                      ? 'border-indigo-500 bg-indigo-500'
                      : 'border-gray-300 dark:border-slate-600'
                  }`}>
                    {selectedMeetingIds.has(meeting.id) && <Check className="h-3 w-3 text-white" />}
                  </div>
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={selectedMeetingIds.has(meeting.id)}
                    onChange={() => onToggle('meeting', meeting.id)}
                  />
                  <span className="text-sm text-gray-700 dark:text-slate-300 truncate">{meeting.summary || `Meeting ${meeting.id.slice(0, 8)}`}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {papers.length === 0 && references.length === 0 && meetings.length === 0 && (
        <div className="px-3 py-4 text-center text-sm text-gray-500 dark:text-slate-400">
          No resources available in this project yet.
        </div>
      )}
    </div>
  )
}

const ChannelSettingsModal = ({
  channel,
  onClose,
  onSave,
  onDelete,
  isSaving,
  isDeleting,
  papers,
  references,
  meetings,
  isLoadingResources,
}: {
  channel: DiscussionChannelSummary
  onClose: () => void
  onSave: (payload: { name?: string; description?: string | null; scope?: ChannelScopeConfig | null }) => void
  onDelete: () => void
  isSaving: boolean
  isDeleting: boolean
  papers: ResearchPaper[]
  references: ProjectReferenceSuggestion[]
  meetings: MeetingSummary[]
  isLoadingResources: boolean
}) => {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [name, setName] = useState(channel.name)
  const [description, setDescription] = useState(channel.description || '')
  const [scope, setScope] = useState<ChannelScopeConfig | null>(channel.scope ?? null)

  const toggleScopeResource = (type: 'paper' | 'reference' | 'meeting', id: string) => {
    setScope((prev) => {
      const keyMap = { paper: 'paper_ids', reference: 'reference_ids', meeting: 'meeting_ids' } as const
      const key = keyMap[type]

      if (prev === null) {
        return { [key]: [id] } as ChannelScopeConfig
      }

      const currentIds = prev[key] || []
      if (currentIds.includes(id)) {
        const filtered = currentIds.filter((existingId) => existingId !== id)
        const newScope = { ...prev, [key]: filtered.length > 0 ? filtered : null }
        const hasAny = newScope.paper_ids?.length || newScope.reference_ids?.length || newScope.meeting_ids?.length
        return hasAny ? newScope : null
      }

      return { ...prev, [key]: [...currentIds, id] }
    })
  }

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!name.trim()) {
      alert('Channel name is required.')
      return
    }

    const payload: { name?: string; description?: string | null; scope?: ChannelScopeConfig | null } = {}
    if (name.trim() !== channel.name) {
      payload.name = name.trim()
    }
    if (description.trim() !== (channel.description || '')) {
      payload.description = description.trim() || null
    }
    const currentScope = channel.scope ?? null
    const newScope = scope
    if (JSON.stringify(currentScope) !== JSON.stringify(newScope)) {
      // Send empty object {} for project-wide (backend will convert to null)
      payload.scope = newScope === null ? { paper_ids: null, reference_ids: null, meeting_ids: null } : newScope
    }

    if (Object.keys(payload).length === 0) {
      onClose()
      return
    }

    onSave(payload)
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end sm:items-center justify-center bg-gray-900/40 backdrop-blur-sm dark:bg-black/70">
      <div className="w-full sm:max-w-md max-h-[90vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl bg-white p-4 sm:p-6 shadow-xl transition-colors dark:bg-slate-900/90">
        <h3 className="text-base font-semibold text-gray-900 dark:text-slate-100">Channel Settings</h3>
        <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-slate-400">
          Update channel configuration and AI scope
        </p>
        <form className="mt-3 sm:mt-4 space-y-3 sm:space-y-4" onSubmit={handleSubmit}>
          <div>
            <label
              htmlFor="settings-channel-name"
              className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300"
            >
              Channel name
            </label>
            <input
              id="settings-channel-name"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
              placeholder="e.g. Brainstorming"
              maxLength={255}
              required
            />
          </div>

          <div>
            <label
              htmlFor="settings-channel-description"
              className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300"
            >
              Description <span className="text-gray-400 dark:text-slate-500">(optional)</span>
            </label>
            <textarea
              id="settings-channel-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
              rows={3}
              maxLength={2000}
              placeholder="Describe the focus of this channel"
            />
          </div>

          <div>
            <label className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300">
              AI Context Scope
            </label>
            <p className="mt-0.5 text-xs text-gray-500 dark:text-slate-400">
              Choose which resources the AI can access in this channel
            </p>
            <div className="mt-2 space-y-2">
              <button
                type="button"
                onClick={() => setScope(null)}
                className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition ${
                  scope === null
                    ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-500/20 dark:text-indigo-100'
                    : 'border-gray-200 text-gray-600 hover:border-gray-300 dark:border-slate-600 dark:text-slate-300 dark:hover:border-slate-500'
                }`}
              >
                <span className="font-medium">Project-wide</span>
                <span className="ml-1 text-xs opacity-70">(all papers, references, transcripts)</span>
              </button>

              {scope !== null && (
                <div className="mt-3 max-h-64 overflow-y-auto rounded-lg border border-gray-200 dark:border-slate-700">
                  <ResourceScopePicker
                    scope={scope}
                    papers={papers}
                    references={references}
                    meetings={meetings}
                    onToggle={toggleScopeResource}
                    isLoading={isLoadingResources}
                  />
                </div>
              )}

              {scope === null && (
                <button
                  type="button"
                  onClick={() => setScope({})}
                  className="text-xs text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
                >
                  Or select specific resources...
                </button>
              )}
            </div>
          </div>

          {/* Delete confirmation */}
          {confirmDelete && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 dark:border-red-500/30 dark:bg-red-500/10">
              <p className="text-sm text-red-700 dark:text-red-300">
                This will permanently delete the channel and all its messages, tasks, and artifacts.
              </p>
              <p className="mt-2 text-xs text-red-600 dark:text-red-400">
                Type <strong>{channel.name}</strong> to confirm:
              </p>
              <input
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                className="mt-2 w-full rounded-md border border-red-300 px-2 py-1.5 text-sm focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500 dark:border-red-500/50 dark:bg-slate-900/60 dark:text-slate-100"
                placeholder={channel.name}
              />
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setConfirmDelete(false)
                    setDeleteConfirmText('')
                  }}
                  className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={onDelete}
                  disabled={deleteConfirmText !== channel.name || isDeleting}
                  className="flex-1 inline-flex items-center justify-center gap-1 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-300 dark:disabled:bg-red-500/40"
                >
                  {isDeleting && <Loader2 className="h-3 w-3 animate-spin" />}
                  Delete channel
                </button>
              </div>
            </div>
          )}

          <div className="flex justify-between gap-2 pt-2">
            {!channel.is_default && !confirmDelete && (
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                className="rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:border-red-500/40 dark:text-red-400 dark:hover:bg-red-500/10"
                disabled={isSaving || isDeleting}
              >
                Delete
              </button>
            )}
            {(channel.is_default || confirmDelete) && <div />}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                disabled={isSaving || isDeleting}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSaving || isDeleting || confirmDelete}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300 dark:disabled:bg-indigo-500/40"
              >
                {isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
                Save changes
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}

export default ProjectDiscussion
