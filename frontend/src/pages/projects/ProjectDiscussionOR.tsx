/**
 * OpenRouter Discussion Page (Feature-Complete)
 *
 * This page mirrors ProjectDiscussion.tsx but uses OpenRouter API for multi-model support.
 * Key differences from the original:
 * - Uses /discussion-or/ endpoints for AI calls
 * - Adds model selector to switch between GPT, Claude, Gemini, etc.
 * - Saves model preference per project to localStorage
 */

import { useState, useEffect, useLayoutEffect, useRef, useMemo, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  MessageCircle,
  Loader2,
  AlertCircle,
  Plus,
  Sparkles,
  X,
  Bot,
  FileText,
  BookOpen,
  Calendar,
  Check,
  ChevronDown,
  ChevronRight,
  FilePlus,
  Pencil,
  Search,
  Download,
  MoreHorizontal,
  FolderOpen,
  Puzzle,
  Hash,
  CheckCircle,
  Library,
  Menu,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { formatDistanceToNow } from 'date-fns'
import { useProjectContext } from './ProjectLayout'
import { useAuth } from '../../contexts/AuthContext'
import {
  projectDiscussionAPI,
  projectsAPI,
  buildApiUrl,
  refreshAuthToken,
  researchPapersAPI,
  projectReferencesAPI,
  projectMeetingsAPI,
} from '../../services/api'
import discussionWebsocket from '../../services/discussionWebsocket'
import {
  DiscussionMessage,
  DiscussionThread as DiscussionThreadType,
  DiscussionChannelSummary,
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
import ChannelArtifactsPanel from '../../components/discussion/ChannelArtifactsPanel'
import { DiscoveredPaper, IngestionStatus } from '../../components/discussion/DiscoveredPaperCard'
import { DiscoveryQueuePanel, PaperIngestionState, IngestionStatesMap } from '../../components/discussion/DiscoveryQueuePanel'
import { getProjectUrlId } from '../../utils/urlId'
import { modelSupportsReasoning, useOpenRouterModels } from '../../components/discussion/ModelSelector'

// Types
type AssistantExchange = {
  id: string
  channelId: string
  question: string
  response: DiscussionAssistantResponse
  createdAt: Date
  completedAt?: Date
  appliedActions: string[]
  status: 'pending' | 'streaming' | 'complete'
  displayMessage: string
  statusMessage?: string
  isWaitingForTools?: boolean // True when tokens paused but result not yet received
  author?: { id?: string; name?: { display?: string; first?: string; last?: string } | string }
  fromHistory?: boolean
  model?: string
}

type ConversationItem =
  | { kind: 'thread'; timestamp: number; thread: DiscussionThreadType }
  | { kind: 'assistant'; timestamp: number; exchange: AssistantExchange }

// Utility functions
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

const formatAssistantMessage = (message: string, lookup: Map<string, string>): string => {
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


const ProjectDiscussionOR = () => {
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
  const { models: openrouterModels, warning: openrouterWarning } = useOpenRouterModels(project.id)

  const buildStorageKey = useCallback(
    (channelId: string | null) => {
      if (!channelId) return null
      return `${STORAGE_PREFIX}:${channelId}`
    },
    [STORAGE_PREFIX]
  )

  // Fetch project discussion settings (model is now a project-level setting)
  const discussionSettingsQuery = useQuery({
    queryKey: ['project-discussion-settings', project.id],
    queryFn: async () => {
      const response = await projectsAPI.getDiscussionSettings(project.id)
      return response.data
    },
    staleTime: 30000,
  })

  // Get model from project settings (read-only for non-owners)
  const selectedModel =
    openrouterModels.find((model) => model.id === discussionSettingsQuery.data?.model)?.id ||
    openrouterModels[0]?.id
  const discussionEnabled = discussionSettingsQuery.data?.enabled ?? true
  const ownerHasApiKey = discussionSettingsQuery.data?.owner_has_api_key ?? false
  const viewerHasApiKey = discussionSettingsQuery.data?.viewer_has_api_key ?? false
  const serverKeyAvailable = discussionSettingsQuery.data?.server_key_available ?? false
  const useOwnerKeyForTeam = discussionSettingsQuery.data?.use_owner_key_for_team ?? false
  const isOwner = user?.id === project.created_by
  const isViewer = project.current_user_role === 'viewer'
  const ownerKeyAvailableForViewer = isOwner ? ownerHasApiKey : ownerHasApiKey && useOwnerKeyForTeam
  const hasAnyApiKey = viewerHasApiKey || serverKeyAvailable || ownerKeyAvailableForViewer
  const noKeyMessage = isOwner
    ? 'AI commands require an API key. Add your OpenRouter key in Settings.'
    : ownerHasApiKey && !ownerKeyAvailableForViewer
      ? 'AI commands require an API key. The project owner has a key but has not enabled sharing. Add your own key or ask them to enable sharing.'
      : 'AI commands require an API key. Add your OpenRouter key or ask the project owner to enable key sharing.'

  // Turn off reasoning when model doesn't support it
  useEffect(() => {
    if (!modelSupportsReasoning(selectedModel, openrouterModels)) {
      setAssistantReasoning(false)
    }
  }, [selectedModel, openrouterModels])

  // Core state
  const [replyingTo, setReplyingTo] = useState<{ id: string; userName: string } | null>(null)
  const [editingMessage, setEditingMessage] = useState<{ id: string; content: string } | null>(null)
  const [activeChannelId, setActiveChannelId] = useState<string | null>(null)
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false)
  const [isCreateChannelModalOpen, setIsCreateChannelModalOpen] = useState(false)
  const [newChannelName, setNewChannelName] = useState('')
  const [newChannelDescription, setNewChannelDescription] = useState('')
  const [newChannelScope, setNewChannelScope] = useState<ChannelScopeConfig | null>(null)
  const [isChannelSettingsOpen, setIsChannelSettingsOpen] = useState(false)
  const [settingsChannel, setSettingsChannel] = useState<DiscussionChannelSummary | null>(null)
  const [assistantReasoning, setAssistantReasoning] = useState(false)
  const [assistantHistory, setAssistantHistory] = useState<AssistantExchange[]>([])
  const [assistantScope, setAssistantScope] = useState<string[]>(['transcripts', 'papers', 'references'])

  const toggleAssistantScope = useCallback((value: string) => {
    setAssistantScope((prev) => {
      if (prev.includes(value)) {
        if (prev.length === 1) return prev
        return prev.filter((item) => item !== value)
      }
      return [...prev, value]
    })
  }, [])

  // Toggle resource in newChannelScope for create channel modal
  const toggleNewChannelScopeResource = useCallback((type: 'paper' | 'reference' | 'meeting', id: string) => {
    setNewChannelScope((prev) => {
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
  }, [])

  const [openDialog, setOpenDialog] = useState<'resources' | 'artifacts' | 'discoveries' | null>(null)
  const [channelMenuOpen, setChannelMenuOpen] = useState(false)
  const [aiContextExpanded, setAiContextExpanded] = useState(false)
  const channelMenuRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new messages arrive
  const scrollToBottom = useCallback(() => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTo({
        top: messagesContainerRef.current.scrollHeight,
        behavior: 'smooth'
      })
    }
  }, [])

  // Scroll to bottom when assistant history changes or channel switches
  useEffect(() => {
    // Small delay to ensure content is rendered
    const timer = setTimeout(scrollToBottom, 100)
    return () => clearTimeout(timer)
  }, [assistantHistory.length, activeChannelId, scrollToBottom])

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

  // Reference search results state - stored per channel
  const [searchResultsByChannel, setSearchResultsByChannel] = useState<
    Record<
      string,
      {
        exchangeId: string
        papers: DiscoveredPaper[]
        query: string
        isSearching: boolean
        searchId?: string  // Track search_id for correlation with library_update
      }
    >
  >({})

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

  // Track channel switch to prevent notification flash
  const [isChannelSwitching, setIsChannelSwitching] = useState(false)
  const prevChannelRef = useRef<string | null>(null)

  useLayoutEffect(() => {
    if (prevChannelRef.current !== null && prevChannelRef.current !== activeChannelId) {
      setIsChannelSwitching(true)
    }
    prevChannelRef.current = activeChannelId
  }, [activeChannelId])

  useEffect(() => {
    if (isChannelSwitching) {
      const timer = setTimeout(() => setIsChannelSwitching(false), 50)
      return () => clearTimeout(timer)
    }
  }, [isChannelSwitching])

  // Dismissed paper IDs - persisted to localStorage
  const dismissedPapersKey = project?.id ? `scholarhub_dismissed_papers_${project.id}` : null
  const [dismissedPaperIds, setDismissedPaperIds] = useState<Set<string>>(() => {
    if (!dismissedPapersKey) return new Set()
    try {
      const stored = localStorage.getItem(dismissedPapersKey)
      if (stored) return new Set(JSON.parse(stored))
    } catch {
      // Ignore
    }
    return new Set()
  })

  useEffect(() => {
    if (!dismissedPapersKey) return
    try {
      localStorage.setItem(dismissedPapersKey, JSON.stringify([...dismissedPaperIds]))
    } catch {
      // Ignore
    }
  }, [dismissedPaperIds, dismissedPapersKey])

  const resetDismissedPapers = useCallback(() => {
    setDismissedPaperIds(new Set())
    if (dismissedPapersKey) {
      localStorage.removeItem(dismissedPapersKey)
    }
  }, [dismissedPapersKey])

  // Get current channel's search results (filtering out dismissed)
  const referenceSearchResults = useMemo(() => {
    if (!activeChannelId) return null
    const raw = searchResultsByChannel[activeChannelId]
    if (!raw) return null
    return {
      ...raw,
      papers: raw.papers.filter((p) => !dismissedPaperIds.has(p.id)),
    }
  }, [activeChannelId, searchResultsByChannel, dismissedPaperIds])

  const setReferenceSearchResults = useCallback(
    (
      value: {
        exchangeId: string
        channelId: string
        papers: DiscoveredPaper[]
        query: string
        isSearching: boolean
        searchId?: string  // Track search_id for correlation with library_update
      } | null
    ) => {
      if (!value) {
        if (activeChannelId) {
          setSearchResultsByChannel((prev) => {
            const next = { ...prev }
            delete next[activeChannelId]
            return next
          })
        }
        return
      }
      setSearchResultsByChannel((prev) => ({
        ...prev,
        [value.channelId]: {
          exchangeId: value.exchangeId,
          papers: value.papers,
          query: value.query,
          isSearching: value.isSearching,
          searchId: value.searchId,
        },
      }))
    },
    [activeChannelId]
  )

  // Discovery queue - stored per channel
  const [discoveryQueueByChannel, setDiscoveryQueueByChannel] = useState<
    Record<
      string,
      {
        papers: DiscoveredPaper[]
        query: string
        isSearching: boolean
        notification: string | null
      }
    >
  >({})

  // Track dismissed notification channels
  const dismissedNotificationsKey = project?.id ? `scholarhub_dismissed_notifications_${project.id}` : null
  const [dismissedNotificationChannels, setDismissedNotificationChannels] = useState<Set<string>>(() => {
    if (!dismissedNotificationsKey) return new Set()
    try {
      const stored = localStorage.getItem(dismissedNotificationsKey)
      if (stored) return new Set(JSON.parse(stored))
    } catch {
      // Ignore
    }
    return new Set()
  })

  useEffect(() => {
    if (!dismissedNotificationsKey) return
    try {
      localStorage.setItem(dismissedNotificationsKey, JSON.stringify([...dismissedNotificationChannels]))
    } catch {
      // Ignore
    }
  }, [dismissedNotificationChannels, dismissedNotificationsKey])

  // Get current channel's discovery queue
  const discoveryQueue = useMemo(() => {
    if (!activeChannelId) {
      return { papers: [], query: '', isSearching: false, notification: null }
    }
    const raw = discoveryQueueByChannel[activeChannelId] || {
      papers: [],
      query: '',
      isSearching: false,
      notification: null,
    }
    return {
      ...raw,
      papers: raw.papers.filter((p) => !dismissedPaperIds.has(p.id)),
    }
  }, [activeChannelId, discoveryQueueByChannel, dismissedPaperIds])

  // Count dismissed papers only for the current search (not all dismissed papers ever)
  const dismissedInCurrentSearch = useMemo(() => {
    if (!activeChannelId) return 0
    const raw = discoveryQueueByChannel[activeChannelId]
    if (!raw?.papers) return 0
    return raw.papers.filter((p) => dismissedPaperIds.has(p.id)).length
  }, [activeChannelId, discoveryQueueByChannel, dismissedPaperIds])

  // Ingestion summary for notification bar - derived from unified ingestion state
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

  const setDiscoveryQueue = useCallback(
    (
      value: React.SetStateAction<{
        papers: DiscoveredPaper[]
        query: string
        isSearching: boolean
        notification: string | null
      }>
    ) => {
      if (!activeChannelId) return
      setDiscoveryQueueByChannel((prev) => {
        const currentQueue = prev[activeChannelId] || {
          papers: [],
          query: '',
          isSearching: false,
          notification: null,
        }
        const newQueue = typeof value === 'function' ? value(currentQueue) : value
        return { ...prev, [activeChannelId]: newQueue }
      })
    },
    [activeChannelId]
  )

  const handleDismissPaper = useCallback(
    (paperId: string) => {
      if (!activeChannelId) return
      setDismissedPaperIds((prev) => new Set([...prev, paperId]))
      setSearchResultsByChannel((prev) => {
        const current = prev[activeChannelId]
        if (!current) return prev
        return {
          ...prev,
          [activeChannelId]: {
            ...current,
            papers: current.papers.filter((p) => p.id !== paperId),
          },
        }
      })
      setDiscoveryQueueByChannel((prev) => {
        const current = prev[activeChannelId]
        if (!current) return prev
        return {
          ...prev,
          [activeChannelId]: {
            ...current,
            papers: current.papers.filter((p) => p.id !== paperId),
          },
        }
      })
    },
    [activeChannelId]
  )

  // Paper form state
  const [paperFormData, setPaperFormData] = useState({
    title: '',
    paperType: 'research',
    authoringMode: 'latex',
    abstract: '',
    keywords: [] as string[],
    objectives: [] as string[],
  })
  const [keywordInput, setKeywordInput] = useState('')

  // Viewer display name
  const viewerDisplayName = useMemo(() => {
    if (!user) return 'You'
    const parts = [user.first_name, user.last_name].filter(Boolean).join(' ').trim()
    if (parts) return parts
    return user.email || 'You'
  }, [user?.first_name, user?.last_name, user?.email])

  const resolveAuthorLabel = useCallback(
    (author?: AssistantExchange['author']) => {
      if (!author) return 'Someone'
      const sameUser = Boolean(author.id && user?.id && author.id === user.id)
      if (sameUser) return viewerDisplayName || 'You'
      if (typeof author.name === 'string' && author.name.trim()) return author.name.trim()
      if (author.name && typeof author.name === 'object') {
        const nameObj = author.name as { display?: string; first?: string; last?: string }
        if (nameObj.display?.trim()) return nameObj.display.trim()
        const first = nameObj.first?.trim() || ''
        const last = nameObj.last?.trim() || ''
        const combined = [first, last].filter(Boolean).join(' ')
        if (first || last) return combined
      }
      return 'Someone'
    },
    [user?.id, viewerDisplayName]
  )

  // Get current model info
  const currentModelInfo = useMemo(
    () => openrouterModels.find((m) => m.id === selectedModel) || openrouterModels[0],
    [selectedModel, openrouterModels]
  )

  const [showArchivedChannels, setShowArchivedChannels] = useState(false)

  // ========== QUERIES ==========

  // Channels query
  const channelsQuery = useQuery({
    queryKey: ['projectDiscussionChannels', project.id],
    queryFn: async () => {
      const response = await projectDiscussionAPI.listChannels(project.id)
      return response.data
    },
    staleTime: 30000,
  })

  const channels = useMemo(() => {
    const all = channelsQuery.data ?? []
    return showArchivedChannels ? all : all.filter((c) => !c.is_archived)
  }, [channelsQuery.data, showArchivedChannels])

  // Auto-select first channel or default
  useEffect(() => {
    if (!activeChannelId && channels.length > 0) {
      const defaultChannel = channels.find((c) => c.is_default)
      setActiveChannelId(defaultChannel?.id ?? channels[0].id)
    }
  }, [channels, activeChannelId])

  // Messages query
  const {
    data: threadsData,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['projectDiscussion', project.id, activeChannelId],
    queryFn: async () => {
      if (!activeChannelId) return []
      const response = await projectDiscussionAPI.listThreads(project.id, { channelId: activeChannelId })
      return response.data
    },
    enabled: Boolean(activeChannelId),
    staleTime: 10000,
  })

  const orderedThreads = useMemo(() => {
    if (!threadsData) return []
    return [...threadsData].sort(
      (a, b) => new Date(a.message.created_at).getTime() - new Date(b.message.created_at).getTime()
    )
  }, [threadsData])

  // Artifacts query
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

  // Assistant history query (fetch from server to restore processing state)
  const assistantHistoryQuery = useQuery({
    queryKey: ['assistant-history-or', project.id, activeChannelId],
    queryFn: async () => {
      if (!activeChannelId) return []
      const response = await projectDiscussionAPI.listAssistantHistory(project.id, activeChannelId)
      return response.data
    },
    enabled: Boolean(activeChannelId),
    placeholderData: [], // Return empty immediately when channel changes
    staleTime: 0, // Always consider data stale
    refetchOnMount: 'always', // Always refetch when component mounts or channel changes
  })

  // Transform server history to AssistantExchange format, handling processing status
  const serverAssistantHistory = useMemo<AssistantExchange[]>(() => {
    if (!assistantHistoryQuery.data || !activeChannelId) return []

    return assistantHistoryQuery.data.map((item) => {
      const createdAt = item.created_at ? new Date(item.created_at) : new Date()
      const response = item.response
      const lookup = buildCitationLookup(response.citations)

      // Handle processing status from server - this restores loading state after refresh/channel switch
      const isProcessing = item.status === 'processing'
      const isFailed = item.status === 'failed'

      return {
        id: item.id,
        channelId: activeChannelId,
        question: item.question,
        response,
        createdAt,
        completedAt: isProcessing ? undefined : createdAt,
        appliedActions: [],
        status: isProcessing ? 'streaming' : 'complete',
        statusMessage: isProcessing ? (item.status_message || 'Thinking') : (isFailed ? (item.status_message || 'Processing failed') : undefined),
        displayMessage: isProcessing ? '' : formatAssistantMessage(response.message, lookup),
        author: item.author ?? undefined,
        fromHistory: true,
        isWaitingForTools: isProcessing, // Show loading indicator for processing exchanges
      }
    })
  }, [assistantHistoryQuery.data, activeChannelId])

  // Resources query (for channel scope)
  const resourcesQuery = useQuery({
    queryKey: ['channel-resources', project.id, activeChannelId],
    queryFn: async () => {
      if (!activeChannelId) return []
      const response = await projectDiscussionAPI.listChannelResources(project.id, activeChannelId)
      return response.data
    },
    enabled: Boolean(activeChannelId),
  })

  // Available resources for scope picker
  const availablePapersQuery = useQuery({
    queryKey: ['papers', project.id],
    queryFn: async () => {
      const response = await researchPapersAPI.getPapers({ projectId: project.id })
      return response.data.papers
    },
    staleTime: 60000,
    enabled: isCreateChannelModalOpen || isChannelSettingsOpen,
  })

  const availableReferencesQuery = useQuery({
    queryKey: ['projectReferences', project.id],
    queryFn: async () => {
      const response = await projectReferencesAPI.list(project.id)
      return response.data.references
    },
    staleTime: 60000,
    enabled: isCreateChannelModalOpen || isChannelSettingsOpen,
  })

  const availableMeetingsQuery = useQuery({
    queryKey: ['meetings', project.id],
    queryFn: async () => {
      const response = await projectMeetingsAPI.listMeetings(project.id)
      return response.data.meetings
    },
    staleTime: 60000,
    enabled: isCreateChannelModalOpen || isChannelSettingsOpen,
  })

  // Project objectives for paper creation
  const projectObjectives = useMemo(() => {
    return (project as { objectives?: string[] }).objectives ?? []
  }, [project])

  // ========== MUTATIONS ==========

  // Channel mutations
  const createChannelMutation = useMutation({
    mutationFn: async (data: { name: string; description?: string; scope?: ChannelScopeConfig | null }) => {
      const response = await projectDiscussionAPI.createChannel(project.id, data)
      return response.data
    },
    onSuccess: (newChannel) => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionChannels', project.id] })
      setActiveChannelId(newChannel.id)
      setIsCreateChannelModalOpen(false)
      setNewChannelName('')
      setNewChannelDescription('')
      setNewChannelScope(null)
    },
    onError: (error: any) => {
      console.error('Failed to create channel:', error)
      const message = error?.response?.data?.detail || 'Failed to create channel. Please try again.'
      alert(message)
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionChannels', project.id] })
      setIsChannelSettingsOpen(false)
      setSettingsChannel(null)
    },
    onError: (error: any) => {
      console.error('Failed to update channel:', error)
      const message = error?.response?.data?.detail || 'Failed to update channel. Please try again.'
      alert(message)
    },
  })

  const deleteChannelMutation = useMutation({
    mutationFn: async (channelId: string) => {
      await projectDiscussionAPI.deleteChannel(project.id, channelId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionChannels', project.id] })
      setIsChannelSettingsOpen(false)
      setSettingsChannel(null)
      if (channels.length > 1) {
        const remaining = channels.filter((c) => c.id !== activeChannelId)
        setActiveChannelId(remaining[0]?.id ?? null)
      } else {
        setActiveChannelId(null)
      }
    },
    onError: (error) => {
      console.error('Failed to delete channel:', error)
      alert('Failed to delete channel. Please try again.')
    },
  })

  // Message mutations
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
              if (alreadyExists) return threads
              const newThread: DiscussionThreadType = { message: createdMessage, replies: [] }
              return [newThread, ...threads]
            }
            let updated = false
            const nextThreads = threads.map((thread) => {
              if (thread.message.id !== createdMessage.parent_id) return thread
              const replies = thread.replies ?? []
              if (replies.some((reply) => reply.id === createdMessage.id)) return thread
              updated = true
              const sortedReplies = [...replies, createdMessage].sort(
                (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
              )
              return {
                ...thread,
                message: { ...thread.message, reply_count: thread.message.reply_count + 1 },
                replies: sortedReplies,
              }
            })
            return updated ? nextThreads : threads
          }
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

  // Resource mutations
  const createResourceMutation = useMutation({
    mutationFn: async (payload: DiscussionChannelResourceCreate) => {
      if (!activeChannelId) throw new Error('No channel selected')
      const response = await projectDiscussionAPI.createChannelResource(project.id, activeChannelId, payload)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channel-resources', project.id, activeChannelId] })
    },
    onError: (error) => {
      console.error('Failed to create resource:', error)
      alert('Failed to add resource. Please try again.')
    },
  })

  const deleteResourceMutation = useMutation({
    mutationFn: async (resourceId: string) => {
      if (!activeChannelId) throw new Error('No channel selected')
      await projectDiscussionAPI.deleteChannelResource(project.id, activeChannelId, resourceId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channel-resources', project.id, activeChannelId] })
    },
    onError: (error) => {
      console.error('Failed to delete resource:', error)
      alert('Failed to remove resource. Please try again.')
    },
  })

  // Paper action mutation
  const paperActionMutation = useMutation({
    mutationFn: async ({
      actionType,
      payload,
    }: {
      actionType: string
      payload: Record<string, unknown>
    }) => {
      const response = await projectDiscussionAPI.executePaperAction(project.id, actionType, payload)
      return response.data
    },
    onSuccess: (data) => {
      if (data.paper_id) {
        queryClient.invalidateQueries({ queryKey: ['papers', project.id] })
        queryClient.invalidateQueries({ queryKey: ['paper', data.paper_id] })
      }
    },
    onError: (error) => {
      console.error('Paper action failed:', error)
      alert('Failed to perform paper action. Please try again.')
    },
  })

  // Search references mutation
  const searchReferencesMutation = useMutation({
    mutationFn: async ({
      query,
      exchangeId,
      openAccessOnly,
      maxResults,
    }: {
      query: string
      exchangeId: string
      openAccessOnly: boolean
      maxResults: number
    }) => {
      setReferenceSearchResults({
        exchangeId,
        channelId: activeChannelId || '',
        papers: [],
        query,
        isSearching: true,
      })
      // Clear dismissed state for fresh search
      if (activeChannelId) {
        setDismissedNotificationChannels((prev) => {
          const next = new Set(prev)
          next.delete(activeChannelId)
          return next
        })
      }
      setDiscoveryQueue({
        papers: [],
        query,
        isSearching: true,
        notification: `Searching for "${query}"...`,
      })

      const response = await projectDiscussionAPI.searchReferences(project.id, query, { openAccessOnly, maxResults })
      return { papers: response.data.papers, exchangeId, query }
    },
    onSuccess: ({ papers, exchangeId, query }) => {
      setReferenceSearchResults({
        exchangeId,
        channelId: activeChannelId || '',
        papers,
        query,
        isSearching: false,
      })
      setDiscoveryQueue({
        papers,
        query,
        isSearching: false,
        notification: `Found ${papers.length} paper${papers.length !== 1 ? 's' : ''}`,
      })
    },
    onError: (error) => {
      console.error('Reference search failed:', error)
      setDiscoveryQueue((prev) => ({
        papers: prev?.papers ?? [],
        query: prev?.query ?? '',
        isSearching: false,
        notification: 'Search failed. Please try again.',
      }))
    },
  })

  // ========== HELPER FUNCTIONS ==========

  const markActionApplied = useCallback((exchangeId: string, actionKey: string) => {
    setAssistantHistory((prev) =>
      prev.map((entry) => {
        if (entry.id !== exchangeId) return entry
        if (entry.appliedActions.includes(actionKey)) return entry
        return { ...entry, appliedActions: [...entry.appliedActions, actionKey] }
      })
    )
  }, [])

  // Handle dismiss notification bar only (keeps papers in queue)
  const handleDismissNotification = useCallback(() => {
    if (!activeChannelId) return
    // Only mark channel notification as dismissed, don't remove papers from queue
    setDismissedNotificationChannels((prev) => new Set([...prev, activeChannelId]))
  }, [activeChannelId])

  const cancelAssistantRequest = useCallback(() => {
    if (assistantAbortController.current) {
      assistantAbortController.current.abort()
      assistantAbortController.current = null
    }
    // Mark any pending entries as complete with error
    setAssistantHistory((prev) =>
      prev.map((entry) => {
        if (entry.status !== 'complete') {
          return {
            ...entry,
            status: 'complete' as const,
            displayMessage: entry.displayMessage || '(Request cancelled)',
            completedAt: new Date(),
          }
        }
        return entry
      })
    )
  }, [])

  // ========== OPENROUTER ASSISTANT MUTATION ==========

  const assistantMutation = useMutation({
    mutationFn: async ({
      id,
      question,
      reasoning,
      scope,
      recentSearchResults,
      recentSearchId,
      conversationHistory,
    }: {
      id: string
      question: string
      reasoning: boolean
      scope: string[]
      recentSearchResults?: Array<{
        title: string
        authors?: string
        year?: number
        source?: string
        abstract?: string
        doi?: string
        url?: string
        pdf_url?: string
        is_open_access?: boolean
      }>
      recentSearchId?: string  // Track search_id for library_update correlation
      conversationHistory?: Array<{ role: string; content: string }>
    }) => {
      if (!activeChannelId) throw new Error('No channel selected')

      // Create placeholder entry
      const entry: AssistantExchange = {
        id,
        channelId: activeChannelId,
        question,
        response: {
          message: '',
          citations: [],
          reasoning_used: reasoning,
          model: selectedModel,
          usage: undefined,
          suggested_actions: [],
        },
        createdAt: new Date(),
        appliedActions: [],
        status: 'pending',
        displayMessage: '',
        model: selectedModel,
        author: { id: user?.id, name: { display: viewerDisplayName } },
      }

      setAssistantHistory((prev) => [...prev, entry])

      // Build request body
      const body = JSON.stringify({
        question,
        reasoning,
        scope,
        conversation_history: conversationHistory,
        recent_search_results: recentSearchResults?.map((paper) => ({
          title: paper.title,
          authors: paper.authors || '',
          year: paper.year,
          source: paper.source,
          abstract: paper.abstract,
          doi: paper.doi,
          url: paper.url,
          pdf_url: paper.pdf_url,
          is_open_access: paper.is_open_access,
        })),
        recent_search_id: recentSearchId,  // For library_update correlation
      })

      // OpenRouter endpoint with streaming (model is determined by project settings)
      const url = buildApiUrl(
        `/projects/${project.id}/discussion-or/channels/${activeChannelId}/assistant?stream=true`
      )

      const controller = new AbortController()
      assistantAbortController.current = controller

      // Get fresh token
      let token = localStorage.getItem('access_token')
      if (!token) {
        const refreshed = await refreshAuthToken()
        token = refreshed || localStorage.getItem('access_token')
      }

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body,
        signal: controller.signal,
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Request failed: ${response.status} ${errorText}`)
      }

      if (!response.body) {
        throw new Error('No response body')
      }

      // Stream processing
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulatedContent = ''
      let finalResult: DiscussionAssistantResponse | null = null

      streamingFlags.current[id] = true
      setAssistantHistory((prev) =>
        prev.map((e) => (e.id === id ? { ...e, status: 'streaming' } : e))
      )

      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const jsonStr = line.slice(6).trim()
            if (!jsonStr || jsonStr === '[DONE]') continue

            try {
              const event = JSON.parse(jsonStr)

              if (event.type === 'token') {
                accumulatedContent += event.content || ''
                // Throttle UI updates
                if (typingTimers.current[id]) {
                  clearTimeout(typingTimers.current[id])
                }
                typingTimers.current[id] = window.setTimeout(() => {
                  setAssistantHistory((prev) =>
                    prev.map((e) =>
                      e.id === id
                        ? { ...e, displayMessage: stripActionsBlock(accumulatedContent) }
                        : e
                    )
                  )
                }, 30)
              } else if (event.type === 'status') {
                // Tool is being executed - set status message and flag
                setAssistantHistory((prev) =>
                  prev.map((e) =>
                    e.id === id ? { ...e, statusMessage: event.message, isWaitingForTools: true } : e
                  )
                )
              } else if (event.type === 'result') {
                finalResult = event.payload
              } else if (event.type === 'error') {
                throw new Error(event.message || 'Stream error')
              }
            } catch (parseError) {
              console.warn('Failed to parse SSE event:', parseError)
            }
          }
        }
      } finally {
        streamingFlags.current[id] = false
        if (typingTimers.current[id]) {
          clearTimeout(typingTimers.current[id])
          delete typingTimers.current[id]
        }
      }

      if (!finalResult) {
        finalResult = {
          message: accumulatedContent,
          citations: [],
          reasoning_used: reasoning,
          model: selectedModel,
          usage: undefined,
          suggested_actions: [],
        }
      }

      return { id, result: finalResult }
    },
    onSuccess: ({ id, result }) => {
      if (!result) return
      setAssistantHistory((prev) =>
        prev.map((entry) => {
          if (entry.id !== id) return entry
          const citationLookup = buildCitationLookup(result.citations ?? [])
          const formattedMessage = formatAssistantMessage(result.message ?? '', citationLookup)
          return {
            ...entry,
            response: result,
            status: 'complete' as const,
            completedAt: new Date(),
            displayMessage: formattedMessage,
            isWaitingForTools: false,
            statusMessage: undefined,
          }
        })
      )
      assistantAbortController.current = null
    },
    onError: (error, variables) => {
      // Check if this was a user-initiated cancel (AbortError)
      const isAbort = error.name === 'AbortError' || error.message?.includes('abort')
      if (isAbort) {
        // User cancelled - cancelAssistantRequest already handled the state update
        console.log('Request cancelled by user')
        assistantAbortController.current = null
        return
      }

      console.error('OpenRouter assistant error:', error)
      setAssistantHistory((prev) =>
        prev.map((entry) => {
          if (entry.id !== variables.id) return entry
          return {
            ...entry,
            status: 'complete' as const,
            completedAt: new Date(),
            displayMessage: `Error: ${error.message || 'Request failed'}`,
            response: {
              ...entry.response,
              message: `Error: ${error.message || 'Request failed'}`,
            },
          }
        })
      )
      assistantAbortController.current = null
    },
  })

  // ========== LOAD ASSISTANT HISTORY ==========

  // Clear history when channel changes
  useEffect(() => {
    setAssistantHistory([])
    historyChannelRef.current = activeChannelId
  }, [activeChannelId])

  // Merge server history with local unsynced entries
  useEffect(() => {
    if (!activeChannelId) return

    // Merge server data with local unsynced entries (entries created during streaming)
    setAssistantHistory((prev) => {
      const idsFromServer = new Set(serverAssistantHistory.map((entry) => entry.id))

      // Keep local entries that don't exist on server yet (currently streaming)
      // but filter out any that have been completed on server
      const localOnlyEntries = prev.filter((entry) => {
        // If this entry exists on server, use server version instead
        if (idsFromServer.has(entry.id)) return false
        // Keep local streaming/pending entries
        if (entry.status === 'streaming' || entry.status === 'pending') return true
        return false
      })

      // Combine server history with local-only entries
      const merged = [...serverAssistantHistory, ...localOnlyEntries]

      // Sort by creation time
      return merged.sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime())
    })
  }, [serverAssistantHistory, activeChannelId])

  // Save assistant history to localStorage
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

  // ========== WEBSOCKET SETUP ==========

  // Connect to WebSocket for real-time updates
  useEffect(() => {
    if (!project.id || !activeChannelId) return

    const token = localStorage.getItem('access_token') || ''
    discussionWebsocket.connect(project.id, activeChannelId, token)
  }, [project.id, activeChannelId])

  // Handle discussion events from WebSocket (messages + assistant events)
  const handleDiscussionEvent = useCallback(
    (payload: any) => {
      if (!payload || payload.project_id !== project.id) return
      if (!activeChannelId || payload.channel_id !== activeChannelId) return

      // Handle real-time message events (new messages from other users)
      if (payload.event === 'message_created' || payload.event === 'message_updated') {
        queryClient.invalidateQueries({ queryKey: ['projectDiscussion', project.id, activeChannelId] })
        return
      }

      if (payload.event === 'message_deleted') {
        const messageId = payload.message_id
        if (messageId) {
          queryClient.setQueryData<DiscussionThreadType[] | undefined>(
            ['projectDiscussion', project.id, activeChannelId],
            (threads) => {
              if (!threads) return threads
              return threads.filter((t) => t.message.id !== messageId)
            }
          )
        }
        return
      }

      // Handle assistant processing started (restores state after channel switch/refresh)
      if (payload.event === 'assistant_processing') {
        const exchange = payload.exchange
        if (!exchange) return

        // Skip if from same user who already has local streaming entry
        if (exchange.author?.id && user?.id && exchange.author.id === user.id) {
          setAssistantHistory((prev) => {
            if (prev.some((entry) => entry.status === 'streaming' || entry.status === 'pending')) return prev
            if (prev.some((entry) => entry.id === exchange.id)) return prev
            const entry: AssistantExchange = {
              id: exchange.id,
              channelId: activeChannelId,
              question: exchange.question || '',
              response: { message: '', citations: [], reasoning_used: false, model: '', usage: undefined, suggested_actions: [] },
              createdAt: exchange.created_at ? new Date(exchange.created_at) : new Date(),
              appliedActions: [],
              status: 'streaming',
              statusMessage: exchange.status_message || 'Processing...',
              displayMessage: '',
              author: exchange.author,
              fromHistory: true,
              isWaitingForTools: true,
            }
            return [...prev, entry]
          })
        }
        return
      }

      // Handle assistant status updates (live progress)
      if (payload.event === 'assistant_status') {
        const exchangeId = payload.exchange_id
        const statusMessage = payload.status_message
        if (!exchangeId || !statusMessage) return

        // Update local state immediately
        setAssistantHistory((prev) =>
          prev.map((entry) =>
            entry.id === exchangeId && entry.status === 'streaming'
              ? { ...entry, statusMessage, isWaitingForTools: true }
              : entry
          )
        )

        // Also update the query cache so server data stays in sync
        queryClient.setQueryData<typeof assistantHistoryQuery.data>(
          ['assistant-history-or', project.id, activeChannelId],
          (old) => {
            if (!old) return old
            return old.map((item) =>
              item.id === exchangeId
                ? { ...item, status_message: statusMessage }
                : item
            )
          }
        )
        return
      }

      // Handle assistant reply completed
      if (payload.event === 'assistant_reply') {
        const exchange = payload.exchange
        if (!exchange) return
        const exchangeId: string = exchange.id

        // Update existing processing entry
        setAssistantHistory((prev) => {
          const existingIndex = prev.findIndex((entry) => entry.id === exchangeId)
          if (existingIndex >= 0) {
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
              isWaitingForTools: false,
            }
            return updated
          }
          return prev
        })
        // Refresh the query to get latest data
        queryClient.invalidateQueries({ queryKey: ['assistant-history-or', project.id, activeChannelId] })
      }
    },
    [project.id, activeChannelId, user?.id, queryClient]
  )

  // Subscribe to WebSocket discussion events
  useEffect(() => {
    discussionWebsocket.on('discussion_event', handleDiscussionEvent)
    return () => {
      discussionWebsocket.off('discussion_event', handleDiscussionEvent)
    }
  }, [handleDiscussionEvent])

  // Close channel menu on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (channelMenuRef.current && !channelMenuRef.current.contains(event.target as Node)) {
        setChannelMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [assistantHistory, orderedThreads])

  // ========== CONVERSATION ITEMS ==========

  const conversationItems = useMemo<ConversationItem[]>(() => {
    const items: ConversationItem[] = []

    for (const thread of orderedThreads) {
      items.push({
        kind: 'thread',
        timestamp: new Date(thread.message.created_at).getTime(),
        thread,
      })
    }

    for (const exchange of assistantHistory) {
      items.push({
        kind: 'assistant',
        timestamp: exchange.createdAt.getTime(),
        exchange,
      })
    }

    return items.sort((a, b) => a.timestamp - b.timestamp)
  }, [orderedThreads, assistantHistory])

  // ========== ACTION PROCESSING ==========

  // Process search_results and library_update actions
  useEffect(() => {
    // Track latest search_id per channel within this loop
    // This ensures we only show ingestion states for the LATEST search
    const latestSearchIdByChannel: Record<string, string> = {}

    // First pass: Find the latest search_id for each channel
    for (const exchange of assistantHistory) {
      if (exchange.status !== 'complete') continue
      if (!exchange.response?.suggested_actions) continue
      const channelId = exchange.channelId || activeChannelId
      if (!channelId) continue

      for (const action of exchange.response.suggested_actions) {
        if (action.action_type === 'search_results') {
          const payload = action.payload as { search_id?: string } | undefined
          if (payload?.search_id) {
            latestSearchIdByChannel[channelId] = payload.search_id
          }
        }
      }
    }

    // Second pass: Process actions
    for (const exchange of assistantHistory) {
      if (exchange.status !== 'complete') continue
      if (!exchange.response?.suggested_actions) continue

      for (let i = 0; i < exchange.response.suggested_actions.length; i++) {
        const action = exchange.response.suggested_actions[i]
        const actionKey = `${exchange.id}:${i}`
        if (exchange.appliedActions.includes(actionKey)) continue

        // Handle search_results action
        if (action.action_type === 'search_results') {
          const payload = action.payload as { query?: string; papers?: DiscoveredPaper[]; total_found?: number; search_id?: string } | undefined
          const papers = payload?.papers || []
          const query = payload?.query || ''
          const searchId = payload?.search_id

          if (!activeChannelId) continue
          if (exchange.channelId && exchange.channelId !== activeChannelId) continue

          markActionApplied(exchange.id, actionKey)

          if (papers.length > 0) {
            // Clear dismissed state for this channel - new search should show results
            if (!exchange.fromHistory) {
              setDismissedNotificationChannels((prev) => {
                const next = new Set(prev)
                next.delete(activeChannelId)
                return next
              })
              // Clear previous ingestion states so new search notification takes priority
              setIngestionStatesByChannel((prev) => {
                const next = { ...prev }
                delete next[activeChannelId]
                return next
              })
            }

            setReferenceSearchResults({
              exchangeId: exchange.id,
              channelId: activeChannelId,
              papers: papers,
              query: query,
              isSearching: false,
              searchId: searchId,
            })
            setDiscoveryQueue({
              papers: papers,
              query: query,
              isSearching: false,
              notification: `Found ${papers.length} papers`,
            })
          }
          continue
        }

        // Handle library_update action
        if (action.action_type === 'library_update') {
          const payload = action.payload as { search_id?: string; updates?: { index: number; reference_id: string; ingestion_status: string }[] } | undefined
          const updates = payload?.updates || []
          const searchId = payload?.search_id

          if (!activeChannelId) continue
          if (exchange.channelId && exchange.channelId !== activeChannelId) continue

          // SKIP if this library_update is for an OLD search (not the latest)
          // This prevents stale ingestion notifications from previous searches
          const latestSearchId = latestSearchIdByChannel[activeChannelId]
          if (searchId && latestSearchId && searchId !== latestSearchId) {
            markActionApplied(exchange.id, actionKey)
            continue  // Skip this library_update - it's from an old search
          }

          // For history entries, skip if user dismissed notifications
          if (exchange.fromHistory && dismissedNotificationChannels.has(activeChannelId)) continue

          // Fresh library_update - clear dismissed state
          if (!exchange.fromHistory && dismissedNotificationChannels.has(activeChannelId)) {
            setDismissedNotificationChannels((prev) => {
              const next = new Set(prev)
              next.delete(activeChannelId)
              return next
            })
          }

          markActionApplied(exchange.id, actionKey)

          // Convert AI updates to ingestion state keyed by paper ID
          // Find papers from matching search_results action (using search_id), not from React state
          // This ensures it works on page refresh when state hasn't been updated yet
          if (updates.length > 0) {
            let queuePapers: DiscoveredPaper[] = []

            // First try to find papers from history using search_id
            if (searchId) {
              for (const hist of assistantHistory) {
                if (hist.status !== 'complete' || !hist.response?.suggested_actions) continue
                for (const act of hist.response.suggested_actions) {
                  if (act.action_type === 'search_results') {
                    const srPayload = act.payload as { search_id?: string; papers?: DiscoveredPaper[] } | undefined
                    if (srPayload?.search_id === searchId && srPayload?.papers) {
                      queuePapers = srPayload.papers
                      break
                    }
                  }
                }
                if (queuePapers.length > 0) break
              }
            }

            // Fallback to React state if history lookup failed
            if (queuePapers.length === 0) {
              queuePapers = discoveryQueueByChannel[activeChannelId]?.papers || []
            }

            setIngestionStatesByChannel((prev) => {
              const channelStates = { ...(prev[activeChannelId] || {}) }
              for (const u of updates) {
                const paper = queuePapers[u.index]
                if (paper) {
                  channelStates[paper.id] = {
                    referenceId: u.reference_id,
                    status: u.ingestion_status as IngestionStatus,
                    isAdding: u.ingestion_status === 'pending',
                  }
                }
              }
              return { ...prev, [activeChannelId]: channelStates }
            })
          }
          continue
        }
      }
    }
  }, [assistantHistory, markActionApplied, activeChannelId, setReferenceSearchResults, setDiscoveryQueue, dismissedNotificationChannels])

  // ========== EVENT HANDLERS ==========

  const handleSendMessage = (content: string) => {
    const trimmed = content.trim()
    if (!trimmed) return

    // Slash commands trigger the assistant
    if (trimmed.startsWith('/')) {
      if (!activeChannelId) {
        alert('Select a channel before asking Scholar AI.')
        return
      }
      if (assistantMutation.isPending) return

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

      // Build search results context
      const papersToSend =
        (referenceSearchResults?.papers?.length ?? 0) > 0
          ? referenceSearchResults?.papers ?? []
          : discoveryQueue.papers

      const recentSearchResults = papersToSend.map((p) => ({
        title: p.title,
        authors: Array.isArray(p.authors) ? p.authors.slice(0, 3).join(', ') : p.authors,
        year: p.year,
        source: p.source,
        abstract: p.abstract,
        doi: p.doi,
        url: p.url,
        pdf_url: p.pdf_url,
        is_open_access: p.is_open_access,
      }))

      // Build conversation history
      const conversationHistory: Array<{ role: string; content: string }> = []
      for (const exchange of assistantHistory) {
        if (exchange.question) {
          conversationHistory.push({ role: 'user', content: exchange.question })
        }
        if (exchange.response?.message) {
          conversationHistory.push({ role: 'assistant', content: exchange.response.message })
        }
      }

      assistantMutation.mutate({
        id: entryId,
        question,
        reasoning,
        scope: assistantScope,
        recentSearchResults,
        recentSearchId: referenceSearchResults?.searchId,  // For library_update correlation
        conversationHistory,
      })
      return
    }

    // Regular message
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

  const handleCancelReply = () => setReplyingTo(null)
  const handleCancelEdit = () => setEditingMessage(null)

  const handleOpenCreateChannel = () => {
    setNewChannelName('')
    setNewChannelDescription('')
    setNewChannelScope(null)
    setIsCreateChannelModalOpen(true)
  }

  const handleCloseCreateChannel = () => {
    setIsCreateChannelModalOpen(false)
    setNewChannelName('')
    setNewChannelDescription('')
    setNewChannelScope(null)
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

  const handleToggleArchive = (channel: DiscussionChannelSummary) => {
    if (channel.is_default) return
    const action = channel.is_archived ? 'unarchive' : 'archive'
    if (!window.confirm(`Are you sure you want to ${action} "${channel.name}"?`)) return

    updateChannelMutation.mutate({
      channelId: channel.id,
      payload: { is_archived: !channel.is_archived },
    })
  }

  const handleMobileChannelSelect = (channelId: string) => {
    setActiveChannelId(channelId)
    setIsMobileSidebarOpen(false)
  }

  // Paper form handlers
  const handleAddKeyword = () => {
    const kw = keywordInput.trim()
    if (kw && !paperFormData.keywords.includes(kw)) {
      setPaperFormData((prev) => ({ ...prev, keywords: [...prev.keywords, kw] }))
    }
    setKeywordInput('')
  }

  const handleRemoveKeyword = (keyword: string) => {
    setPaperFormData((prev) => ({
      ...prev,
      keywords: prev.keywords.filter((k) => k !== keyword),
    }))
  }

  const handleToggleObjective = (objective: string) => {
    setPaperFormData((prev) => {
      if (prev.objectives.includes(objective)) {
        return { ...prev, objectives: prev.objectives.filter((o) => o !== objective) }
      }
      return { ...prev, objectives: [...prev.objectives, objective] }
    })
  }

  const handlePaperCreationSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!paperFormData.title.trim()) {
      alert('Paper title is required.')
      return
    }
    if (!paperCreationDialog) return

    paperActionMutation.mutate(
      {
        actionType: 'create_paper',
        payload: {
          title: paperFormData.title.trim(),
          paper_type: paperFormData.paperType,
          authoring_mode: paperFormData.authoringMode,
          abstract: paperFormData.abstract.trim() || undefined,
          keywords: paperFormData.keywords.length > 0 ? paperFormData.keywords : undefined,
          objectives: paperFormData.objectives.length > 0 ? paperFormData.objectives : undefined,
        },
      },
      {
        onSuccess: (data) => {
          if (data.paper_id && paperCreationDialog) {
            markActionApplied(paperCreationDialog.exchangeId, `${paperCreationDialog.exchangeId}:${paperCreationDialog.actionIndex}`)
          }
          setPaperCreationDialog(null)
          setPaperFormData({
            title: '',
            paperType: 'research',
            authoringMode: 'latex',
            abstract: '',
            keywords: [],
            objectives: [],
          })
        },
      }
    )
  }

  const handleSuggestedAction = (
    exchange: AssistantExchange,
    action: DiscussionAssistantSuggestedAction,
    index: number
  ) => {
    if (!activeChannelId) {
      alert('Select a channel before accepting assistant suggestions.')
      return
    }

    const actionKey = `${exchange.id}:${index}`
    if (exchange.appliedActions.includes(actionKey)) return

    if (action.action_type === 'create_paper') {
      const title = String(action.payload?.title || '').trim()
      const paperType = String(action.payload?.paper_type || 'research').trim()
      const authoringMode = String(action.payload?.authoring_mode || 'latex').trim()
      const abstract = String(action.payload?.abstract || '').trim()
      const suggestedKeywords = Array.isArray(action.payload?.keywords) ? action.payload.keywords : []

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

    if (action.action_type === 'artifact_created') {
      const title = String(action.payload?.title || 'download').trim()
      const filename = String(action.payload?.filename || `${title}.md`).trim()
      const contentBase64 = String(action.payload?.content_base64 || '')
      const mimeType = String(action.payload?.mime_type || 'text/plain')

      if (!contentBase64) {
        alert('The artifact is missing content.')
        return
      }

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
        queryClient.invalidateQueries({ queryKey: ['channel-artifacts', project.id, activeChannelId] })
      } catch (e) {
        console.error('Failed to decode artifact:', e)
        alert('Failed to download artifact.')
      }
      return
    }

    alert('This assistant suggestion type is not yet supported.')
  }

  // ========== DERIVED STATE ==========

  const activeChannel = channels.find((channel) => channel.id === activeChannelId) ?? null
  const hasAssistantHistory = assistantHistory.length > 0

  // ========== RENDER HELPERS ==========

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
            <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-slate-400">
              Start the conversation by sending a message or ask Scholar AI for help using /{currentModelInfo.name}.
            </p>
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
            // Show tool execution indicator when we have content but tools are being executed
            const isExecutingTools = displayedMessage && exchange.isWaitingForTools && exchange.status !== 'complete'
            const authorLabel = resolveAuthorLabel(exchange.author)
            const avatarText = authorLabel.trim().charAt(0).toUpperCase() || 'U'
            const modelName = exchange.model
              ? openrouterModels.find((m) => m.id === exchange.model)?.name || exchange.model
              : currentModelInfo.name

            const promptBubbleClass = 'inline-block max-w-full sm:max-w-fit rounded-xl sm:rounded-2xl bg-purple-50/70 px-3 py-1.5 sm:px-4 sm:py-2 shadow-sm ring-2 ring-purple-200 transition dark:bg-purple-500/15 dark:ring-purple-400/40 dark:shadow-purple-900/30'
            const responseBubbleClass = 'inline-block max-w-full sm:max-w-fit rounded-xl sm:rounded-2xl bg-white px-3 py-1.5 sm:px-4 sm:py-2 transition dark:bg-slate-800/70 dark:ring-1 dark:ring-slate-700'

            return (
              <div key={exchange.id} className="border-b border-gray-100 pb-3 sm:pb-4 last:border-b-0 dark:border-slate-700">
                <div className="space-y-3 sm:space-y-4 pt-3 sm:pt-4">
                  {/* User question */}
                  <div className="flex items-start gap-2 sm:gap-3">
                    <div className="flex h-6 w-6 sm:h-8 sm:w-8 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs sm:text-sm font-medium text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-200">
                      {avatarText}
                    </div>
                    <div className="flex min-w-0 flex-1 flex-col">
                      <div className="mb-1 flex flex-wrap items-center gap-1.5 sm:gap-2">
                        <span className="text-xs sm:text-sm font-medium text-gray-900 dark:text-slate-100">{authorLabel}</span>
                        <span className="text-[10px] sm:text-xs text-gray-500">{askedLabel}</span>
                        <span className="inline-flex items-center gap-0.5 sm:gap-1 rounded-full bg-indigo-100 px-1.5 py-0.5 text-[9px] sm:text-[10px] font-medium text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200">
                          <Bot className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                          {modelName}
                        </span>
                      </div>
                      <div className={promptBubbleClass}>
                        <p className="text-xs sm:text-sm text-gray-700 dark:text-slate-200 break-words">{exchange.question}</p>
                      </div>
                    </div>
                  </div>
                  {/* AI response */}
                  <div className="flex items-start gap-2 sm:gap-3">
                    <div className="flex h-6 w-6 sm:h-8 sm:w-8 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs sm:text-sm font-medium text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-200">
                      AI
                    </div>
                    <div className="flex min-w-0 flex-1 flex-col">
                      <div className="mb-1 flex flex-wrap items-center gap-1.5 sm:gap-2">
                        <span className="text-xs sm:text-sm font-medium text-gray-900 dark:text-slate-100">Scholar AI</span>
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
                        {/* Tool execution indicator - shown when processing tools after initial message */}
                        {isExecutingTools && (
                          <div className="mt-3 flex items-center gap-2 text-sm text-indigo-600 dark:text-indigo-400">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span>{exchange.statusMessage}...</span>
                          </div>
                        )}
                      </div>
                      {/* Citations */}
                      {!showTyping && exchange.response.citations.length > 0 && (
                        <div className="mt-2 sm:mt-3 space-y-1 sm:space-y-1.5">
                          <p className="text-[10px] sm:text-xs font-medium text-slate-500 dark:text-slate-400">Sources Used:</p>
                          <div className="flex flex-wrap gap-1.5 sm:gap-2">
                            {exchange.response.citations.map((citation) => {
                              const getResourceIcon = (resourceType?: string) => {
                                switch (resourceType) {
                                  case 'paper': return <FileText className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-blue-500" />
                                  case 'reference': return <BookOpen className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-emerald-500" />
                                  case 'meeting': return <Calendar className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-purple-500" />
                                  default: return <FileText className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-slate-400" />
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
                      {/* Paper created/updated actions */}
                      {!showTyping && exchange.response.suggested_actions?.some(a => a.action_type === 'paper_created' || a.action_type === 'paper_updated') && (
                        <div className="mt-2 sm:mt-3 flex flex-wrap gap-1.5 sm:gap-2">
                          {exchange.response.suggested_actions
                            .filter(a => a.action_type === 'paper_created' || a.action_type === 'paper_updated')
                            .map((action, idx) => {
                              const urlId = action.payload?.url_id || action.payload?.paper_id
                              return (
                                <button
                                  key={idx}
                                  onClick={() => navigate(`/projects/${getProjectUrlId(project)}/papers/${urlId}`)}
                                  className="inline-flex items-center gap-1.5 sm:gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 sm:px-3 sm:py-2 text-xs sm:text-sm font-medium text-emerald-700 hover:bg-emerald-100 dark:border-emerald-400/30 dark:bg-emerald-500/10 dark:text-emerald-300 dark:hover:bg-emerald-500/20 transition-colors"
                                >
                                  <FileText className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-emerald-600 dark:text-emerald-400" />
                                  View Paper
                                </button>
                              )
                            })}
                        </div>
                      )}
                      {/* Suggested actions */}
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
                              a.action_type !== 'paper_created' &&
                              a.action_type !== 'paper_updated' &&
                              a.action_type !== 'library_update' &&
                              a.action_type !== 'search_results'
                            ).map((action, idx) => {
                              const actionKey = `${exchange.id}:${idx}`
                              const applied = exchange.appliedActions.includes(actionKey)
                              const isPending = paperActionMutation.isPending || searchReferencesMutation.isPending
                              const getActionIcon = () => {
                                if (applied) return <Check className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                                switch (action.action_type) {
                                  case 'create_paper': return <FilePlus className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                                  case 'edit_paper': return <Pencil className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
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
                      {/* Model info */}
                      {!showTyping && (
                        <div className="mt-1.5 sm:mt-2 flex flex-wrap items-center gap-2 sm:gap-3 text-[9px] sm:text-[11px] text-gray-400 dark:text-slate-500">
                          <span>Model: {modelName}</span>
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

  // ========== MAIN RENDER ==========

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
              onCreateChannel={isViewer ? undefined : handleOpenCreateChannel}
              isCreating={createChannelMutation.isPending}
              onArchiveToggle={isViewer ? undefined : handleToggleArchive}
              onOpenSettings={isViewer ? undefined : (channel) => {
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

      <div className="flex h-[calc(100vh-80px)] sm:h-[calc(100vh-90px)] md:h-[calc(100vh-100px)] min-h-[24rem] sm:min-h-[28rem] md:min-h-[36rem] w-full gap-2 md:gap-3 overflow-hidden">
        {/* Desktop sidebar */}
        <div className="hidden md:block flex-shrink-0">
          <DiscussionChannelSidebar
            channels={channels}
            activeChannelId={activeChannelId}
            onSelectChannel={setActiveChannelId}
            onCreateChannel={isViewer ? undefined : handleOpenCreateChannel}
            isCreating={createChannelMutation.isPending}
            onArchiveToggle={isViewer ? undefined : handleToggleArchive}
            onOpenSettings={isViewer ? undefined : (channel) => {
              setSettingsChannel(channel)
              setIsChannelSettingsOpen(true)
            }}
            showArchived={showArchivedChannels}
            onToggleShowArchived={() => setShowArchivedChannels((prev) => !prev)}
          />
        </div>

        {/* Main content */}
        <div className="flex flex-1 min-h-0 min-w-0 flex-col rounded-xl md:rounded-2xl border border-gray-200 bg-white shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900/40">
          {/* Header */}
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
                    {activeChannel ? activeChannel.name : 'OpenRouter Discussion'}
                  </h2>
                  {activeChannel?.is_default && (
                    <span className="hidden sm:inline flex-shrink-0 rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
                      Default
                    </span>
                  )}
                </div>
                {activeChannel?.description && (
                  <p className="hidden md:block text-xs text-gray-500 dark:text-slate-400 truncate">{activeChannel.description}</p>
                )}
              </div>
            </div>
            {/* Model badge and channel menu */}
            <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
              {/* Model badge - configured in Project Settings */}
              <div
                className="hidden sm:flex items-center gap-1.5 rounded-lg border border-gray-200 bg-gray-50 px-2 py-1.5 text-xs text-gray-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300"
                title="AI model - configure in Project Settings"
              >
                <Bot className="h-3.5 w-3.5" />
                <span className="max-w-[100px] truncate">{currentModelInfo.name}</span>
              </div>

              {activeChannel && (
                <div className="relative" ref={channelMenuRef}>
                  <button
                    type="button"
                    onClick={() => setChannelMenuOpen(!channelMenuOpen)}
                    className="inline-flex items-center gap-1 rounded-lg border border-gray-200 p-1.5 sm:p-2 text-gray-600 transition hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                  >
                    <MoreHorizontal className="h-4 w-4" />
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
                          onClick={() => { setOpenDialog('resources'); setChannelMenuOpen(false) }}
                          className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 transition hover:bg-gray-50 dark:text-slate-200 dark:hover:bg-slate-700"
                        >
                          <FolderOpen className="h-4 w-4 text-indigo-500" />
                          Channel resources
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => { setOpenDialog('artifacts'); setChannelMenuOpen(false) }}
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
                        onClick={() => { setOpenDialog('discoveries'); setChannelMenuOpen(false) }}
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
              )}
            </div>
          </div>

          {activeChannel ? (
            <>
              {/* Messages area */}
              <div className="flex flex-1 min-h-0 overflow-hidden p-2 sm:p-3 md:p-4">
                <div
                  ref={messagesContainerRef}
                  className="flex-1 min-h-0 overflow-y-auto scroll-smooth pr-1 sm:pr-2"
                  style={{
                    scrollbarWidth: 'thin',
                    scrollbarColor: 'rgb(203 213 225) transparent',
                  }}
                >
                  {renderDiscussionContent()}
                </div>
              </div>

              {/* Floating notification bar */}
              {!isChannelSwitching && (discoveryQueue.papers.length > 0 || ingestionSummary) && (
                <>
                  {ingestionSummary?.isProcessing ? (
                    <div className="mx-2 sm:mx-4 mb-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 sm:gap-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 sm:px-4 sm:py-2.5 shadow-sm dark:border-blue-500/30 dark:bg-blue-900/20">
                      <div className="flex items-center gap-2 sm:gap-3">
                        <div className="flex h-7 w-7 sm:h-8 sm:w-8 flex-shrink-0 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-500/20">
                          <Loader2 className="h-3.5 w-3.5 sm:h-4 sm:w-4 animate-spin text-blue-600 dark:text-blue-400" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs sm:text-sm font-medium text-blue-800 dark:text-blue-200">Adding papers to library...</p>
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
                    <div className="mx-2 sm:mx-4 mb-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 sm:gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 sm:px-4 sm:py-2.5 shadow-sm dark:border-emerald-500/30 dark:bg-emerald-900/20">
                      <div className="flex items-center gap-2 sm:gap-3">
                        <div className="flex h-7 w-7 sm:h-8 sm:w-8 flex-shrink-0 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-500/20">
                          <CheckCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-emerald-600 dark:text-emerald-400" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs sm:text-sm font-medium text-emerald-800 dark:text-emerald-200">
                            {ingestionSummary.totalAdded} paper{ingestionSummary.totalAdded !== 1 ? 's' : ''} added to library
                          </p>
                          <p className="text-[10px] sm:text-xs text-emerald-600 dark:text-emerald-400">All with full text available</p>
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
                              setIngestionStatesByChannel((prev) => {
                                const next = { ...prev }
                                delete next[activeChannelId]
                                return next
                              })
                              handleDismissNotification()
                            }
                          }}
                          className="rounded-lg px-2 py-1 sm:px-2 sm:py-1.5 text-[10px] sm:text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 dark:text-emerald-300 dark:hover:bg-emerald-500/20"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  ) : ingestionSummary && ingestionSummary.needsAttention > 0 ? (
                    <div className="mx-2 sm:mx-4 mb-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 sm:gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 sm:px-4 sm:py-2.5 shadow-sm dark:border-amber-500/30 dark:bg-amber-900/20">
                      <div className="flex items-center gap-2 sm:gap-3">
                        <div className="flex h-7 w-7 sm:h-8 sm:w-8 flex-shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-500/20">
                          <Library className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-amber-600 dark:text-amber-400" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs sm:text-sm font-medium text-amber-800 dark:text-amber-200">
                            {ingestionSummary.totalAdded} added • {ingestionSummary.needsAttention} need PDF
                          </p>
                          <p className="text-[10px] sm:text-xs text-amber-600 dark:text-amber-400">Some papers need manual PDF upload</p>
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
                              setIngestionStatesByChannel((prev) => {
                                const next = { ...prev }
                                delete next[activeChannelId]
                                return next
                              })
                              handleDismissNotification()
                            }
                          }}
                          className="rounded-lg px-2 py-1 text-[10px] sm:text-xs font-medium text-amber-700 transition hover:bg-amber-100 dark:text-amber-300 dark:hover:bg-amber-500/20"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  ) : discoveryQueue.papers.length > 0 && activeChannelId && !dismissedNotificationChannels.has(activeChannelId) ? (
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
                          onClick={handleDismissNotification}
                          className="rounded-lg px-2 py-1 text-[10px] sm:text-xs font-medium text-amber-700 transition hover:bg-amber-100 dark:text-amber-300 dark:hover:bg-amber-500/20"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  ) : null}
                </>
              )}

              {/* AI Context toggle */}
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

              {/* AI availability warning */}
              {!discussionEnabled && (
                <div className="mx-3 mb-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                  <AlertCircle className="mr-1.5 inline-block h-3.5 w-3.5" />
                  Discussion AI is disabled for this project. Contact the project owner to enable it.
                </div>
              )}
              {discussionEnabled && !hasAnyApiKey && (
                <div className="mx-3 mb-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                  <AlertCircle className="mr-1.5 inline-block h-3.5 w-3.5" />
                  {noKeyMessage}
                </div>
              )}
              {discussionEnabled && hasAnyApiKey && openrouterWarning && (
                <div className="mx-3 mb-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                  <AlertCircle className="mr-1.5 inline-block h-3.5 w-3.5" />
                  {openrouterWarning}
                </div>
              )}

              {/* Message input */}
              <MessageInput
                onSend={handleSendMessage}
                placeholder={discussionEnabled && hasAnyApiKey
                  ? `Type a message… use / to ask ${currentModelInfo.name} for help`
                  : 'Type a message…'
                }
                replyingTo={replyingTo}
                onCancelReply={handleCancelReply}
                editingMessage={editingMessage}
                onCancelEdit={handleCancelEdit}
                isSubmitting={createMessageMutation.isPending || updateMessageMutation.isPending}
                reasoningEnabled={assistantReasoning}
                onToggleReasoning={discussionEnabled && hasAnyApiKey ? () => setAssistantReasoning((prev) => !prev) : undefined}
                reasoningPending={assistantMutation.isPending}
                reasoningSupported={discussionEnabled && hasAnyApiKey && modelSupportsReasoning(selectedModel, openrouterModels)}
                aiGenerating={assistantMutation.isPending}
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
                      Organize discussions by topic, meeting, or workstream.
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
                      <span className="hidden sm:inline">Choose a channel from the sidebar to see messages.</span>
                      <span className="sm:hidden">Tap the menu icon to choose a channel.</span>
                    </p>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Dialogs */}
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
                  {openDialog === 'resources' ? 'Channel resources' : openDialog === 'artifacts' ? 'Channel artifacts' : 'Paper Discoveries'}
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
              ) : (
                <DiscoveryQueuePanel
                  papers={discoveryQueue.papers}
                  query={discoveryQueue.query}
                  projectId={project.id}
                  isSearching={discoveryQueue.isSearching}
                  notification={discoveryQueue.notification}
                  onDismiss={handleDismissPaper}
                  onDismissAll={handleDismissNotification}
                  onClearNotification={() => setDiscoveryQueue((prev) => ({ ...prev, notification: null }))}
                  ingestionStates={currentIngestionStates}
                  onIngestionStateChange={handleIngestionStateChange}
                />
              )}
            </div>
          </div>
        </div>
      )}

      {/* Create Channel Modal */}
      {isCreateChannelModalOpen && (
        <div className="fixed inset-0 z-40 flex items-end sm:items-center justify-center bg-gray-900/40 backdrop-blur-sm dark:bg-black/70">
          <div className="w-full sm:max-w-md max-h-[90vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl bg-white p-4 sm:p-6 shadow-xl transition-colors dark:bg-slate-900/90">
            <h3 className="text-base font-semibold text-gray-900 dark:text-slate-100">Create new channel</h3>
            <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-slate-400">
              Organize conversations by topic, meeting, or workstream.
            </p>
            <form className="mt-3 sm:mt-4 space-y-3 sm:space-y-4" onSubmit={handleCreateChannelSubmit}>
              <div>
                <label htmlFor="channel-name" className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300">
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
                <label htmlFor="channel-description" className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300">
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
              {/* AI Context Scope */}
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
                    <div className="mt-3 max-h-48 overflow-y-auto rounded-lg border border-gray-200 dark:border-slate-700">
                      <ResourceScopePicker
                        scope={newChannelScope}
                        papers={availablePapersQuery.data || []}
                        references={availableReferencesQuery.data || []}
                        meetings={availableMeetingsQuery.data || []}
                        onToggle={toggleNewChannelScopeResource}
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
                  {createChannelMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  Create channel
                </button>
              </div>
            </form>
          </div>
        </div>
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

      {/* Channel Settings Modal */}
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
    </>
  )
}

// Resource scope picker for channel settings
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

// Channel settings modal component
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
                This will permanently delete the channel and all its messages and artifacts.
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

export default ProjectDiscussionOR
