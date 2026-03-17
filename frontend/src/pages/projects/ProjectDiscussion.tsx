/**
 * Discussion AI Page
 *
 * AI-powered research assistant with multi-model support via OpenRouter.
 * Supports GPT, Claude, Gemini, DeepSeek, and more.
 */

import { useState, useEffect, useLayoutEffect, useRef, useMemo, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  MessageCircle,
  Loader2,
  AlertCircle,
  Plus,
  Sparkles,
  X,
  Bot,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Search,
  FolderOpen,
  FlaskConical,
  Puzzle,
  Hash,
  CheckCircle,
  Library,
  Menu,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useProjectContext } from './ProjectLayout'
import { useAuth } from '../../contexts/AuthContext'
import {
  projectDiscussionAPI,
  projectsAPI,
  researchPapersAPI,
  projectReferencesAPI,
  projectMeetingsAPI,
} from '../../services/api'
import {
  DiscussionMessage,
  DiscussionThread as DiscussionThreadType,
  DiscussionChannelSummary,
  DiscussionChannelResourceCreate,
  ChannelScopeConfig,
} from '../../types'
import MessageInput from '../../components/discussion/MessageInput'
import DiscussionThread from '../../components/discussion/DiscussionThread'
import DiscussionChannelSidebar from '../../components/discussion/DiscussionChannelSidebar'
import ChannelResourcePanel from '../../components/discussion/ChannelResourcePanel'
import ChannelArtifactsPanel from '../../components/discussion/ChannelArtifactsPanel'
import { DiscoveredPaper } from '../../components/discussion/DiscoveredPaperCard'
import { DiscoveryQueuePanel } from '../../components/discussion/DiscoveryQueuePanel'
import { LibraryUpdateItem } from '../../components/discussion/ReferenceSearchResults'
import { AssistantExchangeRenderer } from '../../components/discussion/AssistantExchangeRenderer'
import { getProjectUrlId } from '../../utils/urlId'
import { modelSupportsReasoning, useOpenRouterModels } from '../../components/discussion/ModelSelector'
import { useOnboarding } from '../../contexts/OnboardingContext'
import { useToast } from '../../hooks/useToast'
import ResourceScopePicker from '../../components/projects/ResourceScopePicker'
import ChannelSettingsModal from '../../components/projects/ChannelSettingsModal'
import {
  useAssistantChat,
  type AssistantExchange,
  type ConversationItem,
} from '../../hooks/useAssistantChat'
import { useDiscoveryQueue } from '../../hooks/useDiscoveryQueue'
import { useSuggestedActions } from '../../hooks/useSuggestedActions'
import { useDeepResearch } from '../../hooks/useDeepResearch'

const ASSISTANT_SCOPE_OPTIONS = [
  { id: 'transcripts', label: 'Transcripts' },
  { id: 'papers', label: 'Papers' },
  { id: 'references', label: 'References' },
]


const ProjectDiscussion = () => {
  const { toast } = useToast()
  const { project } = useProjectContext()
  const { user, subscription: subState } = useAuth()
  const userTier = subState.subscription?.tier_id ?? 'free'
  const canUseDeepResearch = userTier === 'pro' || userTier === 'byok'
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { models: openrouterModels, warning: openrouterWarning } = useOpenRouterModels(project.id)
  const { state: onboardingState, markScholarAISeen } = useOnboarding()
  const [showWelcome, setShowWelcome] = useState(!onboardingState.hasSeenScholarAI)
  // Discussion settings
  const discussionSettingsQuery = useQuery({
    queryKey: ['project-discussion-settings', project.id],
    queryFn: async () => {
      const response = await projectsAPI.getDiscussionSettings(project.id)
      return response.data
    },
    staleTime: 30000,
  })

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
  const [assistantScope, setAssistantScope] = useState<string[]>(['transcripts', 'papers', 'references'])

  const [openDialog, setOpenDialog] = useState<'resources' | 'artifacts' | 'discoveries' | null>(null)
  const [closedInlineResults, setClosedInlineResults] = useState<Set<string>>(new Set())
  const [aiContextExpanded, setAiContextExpanded] = useState(false)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const [showArchivedChannels, setShowArchivedChannels] = useState(false)

  // Deep research modal state
  const [isDeepResearchModalOpen, setIsDeepResearchModalOpen] = useState(false)
  const [deepResearchQuestion, setDeepResearchQuestion] = useState('')
  const [deepResearchSelectedRefs, setDeepResearchSelectedRefs] = useState<Set<string>>(new Set())
  const [deepResearchModel, setDeepResearchModel] = useState('openai/o4-mini-deep-research')
  const [deepResearchLibraryOpen, setDeepResearchLibraryOpen] = useState(false)
  const [deepResearchRefSearch, setDeepResearchRefSearch] = useState('')

  // Turn off reasoning when model doesn't support it
  useEffect(() => {
    if (!modelSupportsReasoning(selectedModel, openrouterModels)) {
      setAssistantReasoning(false)
    }
  }, [selectedModel, openrouterModels])

  const toggleAssistantScope = useCallback((value: string) => {
    setAssistantScope((prev) => {
      if (prev.includes(value)) {
        if (prev.length === 1) return prev
        return prev.filter((item) => item !== value)
      }
      return [...prev, value]
    })
  }, [])

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

  // Viewer display name
  const viewerDisplayName = useMemo(() => {
    if (!user) return 'You'
    const parts = [user.first_name, user.last_name].filter(Boolean).join(' ').trim()
    if (parts) return parts
    return user.email || 'You'
  }, [user?.first_name, user?.last_name, user?.email])

  // Get current model info
  const currentModelInfo = useMemo(
    () => openrouterModels.find((m) => m.id === selectedModel) || openrouterModels[0],
    [selectedModel, openrouterModels]
  )

  // ========== EXTRACTED HOOKS ==========

  const {
    assistantHistory,
    setAssistantHistory,
    assistantMutation,
    sendAssistantMessage,
    cancelAssistantRequest,
    markActionApplied,
  } = useAssistantChat({
    projectId: project.id,
    activeChannelId,
    selectedModel,
    userId: user?.id,
    viewerDisplayName,
  })

  const {
    referenceSearchResults,
    setReferenceSearchResults,
    discoveryQueue,
    setDiscoveryQueue,
    discoveryQueueByChannel,
    dismissedInCurrentSearch,
    ingestionSummary,
    currentIngestionStates,
    setIngestionStatesByChannel,
    ingestionUnverifiedChannels,
    setIngestionUnverifiedChannels,
    handleIngestionStateChange,
    handleDismissPaper,
    handleDismissNotification,
    resetDismissedPapers,
    dismissedNotificationChannels,
    setDismissedNotificationChannels,
    searchReferencesMutation,
  } = useDiscoveryQueue({
    projectId: project.id,
    activeChannelId,
  })

  const {
    startDeepResearch,
  } = useDeepResearch({
    projectId: project.id,
    activeChannelId,
    setAssistantHistory,
  })

  const {
    paperCreationDialog,
    setPaperCreationDialog,
    paperFormData,
    setPaperFormData,
    keywordInput,
    setKeywordInput,
    paperActionMutation,
    handleAddKeyword,
    handleRemoveKeyword,
    handleToggleObjective,
    handlePaperCreationSubmit,
    handleSuggestedAction,
    navigateToPaper,
  } = useSuggestedActions({
    projectId: project.id,
    project,
    activeChannelId,
    markActionApplied,
  })

  // ========== DEEP RESEARCH ==========

  const handleOpenDeepResearch = useCallback(() => {
    setDeepResearchQuestion('')
    setDeepResearchSelectedRefs(new Set())
    setDeepResearchLibraryOpen(false)
    setIsDeepResearchModalOpen(true)
  }, [])

  const handleStartDeepResearch = useCallback(() => {
    if (!deepResearchQuestion.trim()) return
    const id = crypto.randomUUID()
    startDeepResearch(
      deepResearchQuestion.trim(),
      '',
      Array.from(deepResearchSelectedRefs),
      id,
      deepResearchModel,
    )
    setIsDeepResearchModalOpen(false)
    setDeepResearchQuestion('')
    setDeepResearchSelectedRefs(new Set())
    setDeepResearchRefSearch('')
  }, [deepResearchQuestion, deepResearchSelectedRefs, deepResearchModel, startDeepResearch])

  // ========== AUTO SCROLL ==========

  const scrollToBottom = useCallback(() => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTo({
        top: messagesContainerRef.current.scrollHeight,
        behavior: 'smooth'
      })
    }
  }, [])

  useEffect(() => {
    const timer = setTimeout(scrollToBottom, 100)
    return () => clearTimeout(timer)
  }, [assistantHistory.length, activeChannelId, scrollToBottom])

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

  // Project objectives for paper creation
  const projectObjectives = useMemo(() => {
    return (project as { objectives?: string[] }).objectives ?? []
  }, [project])

  // ========== QUERIES ==========

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

  useEffect(() => {
    if (!activeChannelId && channels.length > 0) {
      const defaultChannel = channels.find((c) => c.is_default)
      setActiveChannelId(defaultChannel?.id ?? channels[0].id)
    }
  }, [channels, activeChannelId])

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

  const resourcesQuery = useQuery({
    queryKey: ['channel-resources', project.id, activeChannelId],
    queryFn: async () => {
      if (!activeChannelId) return []
      const response = await projectDiscussionAPI.listChannelResources(project.id, activeChannelId)
      return response.data
    },
    enabled: Boolean(activeChannelId),
  })

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
    enabled: isCreateChannelModalOpen || isChannelSettingsOpen || isDeepResearchModalOpen,
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

  // ========== MUTATIONS ==========

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
      toast.error(message)
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
      toast.error(message)
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
      toast.error('Failed to delete channel. Please try again.')
    },
  })

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
      toast.error('Failed to send message. Please try again.')
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
      toast.error('Failed to update message. Please try again.')
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
      toast.error('Failed to delete message. Please try again.')
    },
  })

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
      toast.error('Failed to add resource. Please try again.')
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
      toast.error('Failed to remove resource. Please try again.')
    },
  })

  // ========== ACTION PROCESSING ==========

  useEffect(() => {
    const latestSearchIdByChannel: Record<string, string> = {}

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

    for (const exchange of assistantHistory) {
      if (exchange.status !== 'complete') continue
      if (!exchange.response?.suggested_actions) continue

      for (let i = 0; i < exchange.response.suggested_actions.length; i++) {
        const action = exchange.response.suggested_actions[i]
        const actionKey = `${exchange.id}:${i}`
        if (exchange.appliedActions.includes(actionKey)) continue

        if (action.action_type === 'search_results') {
          const payload = action.payload as { query?: string; papers?: DiscoveredPaper[]; total_found?: number; search_id?: string } | undefined
          const papers = payload?.papers || []
          const query = payload?.query || ''
          const searchId = payload?.search_id

          if (!activeChannelId) continue
          if (exchange.channelId && exchange.channelId !== activeChannelId) continue

          markActionApplied(exchange.id, actionKey)

          if (papers.length > 0) {
            if (!exchange.fromHistory) {
              setDismissedNotificationChannels((prev) => {
                const next = new Set(prev)
                next.delete(activeChannelId)
                return next
              })
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

        if (action.action_type === 'library_update') {
          const payload = action.payload as { search_id?: string; updates?: { index: number; reference_id: string; ingestion_status: string }[] } | undefined
          const updates = payload?.updates || []
          const searchId = payload?.search_id

          if (!activeChannelId) continue
          if (exchange.channelId && exchange.channelId !== activeChannelId) continue

          const latestSearchId = latestSearchIdByChannel[activeChannelId]
          if (searchId && latestSearchId && searchId !== latestSearchId) {
            markActionApplied(exchange.id, actionKey)
            continue
          }

          if (exchange.fromHistory && dismissedNotificationChannels.has(activeChannelId)) continue

          if (!exchange.fromHistory && dismissedNotificationChannels.has(activeChannelId)) {
            setDismissedNotificationChannels((prev) => {
              const next = new Set(prev)
              next.delete(activeChannelId)
              return next
            })
          }

          markActionApplied(exchange.id, actionKey)

          if (updates.length > 0) {
            let queuePapers: DiscoveredPaper[] = []

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
                    status: u.ingestion_status as any,
                    isAdding: u.ingestion_status === 'pending',
                  }
                }
              }
              return { ...prev, [activeChannelId]: channelStates }
            })

            if (exchange.fromHistory) {
              setIngestionUnverifiedChannels((prev) => {
                if (prev.has(activeChannelId)) return prev
                const next = new Set(prev)
                next.add(activeChannelId)
                return next
              })
            } else {
              setIngestionUnverifiedChannels((prev) => {
                if (!prev.has(activeChannelId)) return prev
                const next = new Set(prev)
                next.delete(activeChannelId)
                return next
              })
            }
          }
          continue
        }
      }
    }
  }, [assistantHistory, markActionApplied, activeChannelId, setReferenceSearchResults, setDiscoveryQueue, dismissedNotificationChannels])


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

  // Build a lookup: searchId -> LibraryUpdateItem[] from all exchanges
  const libraryUpdatesBySearchId = useMemo(() => {
    const lookup: Record<string, LibraryUpdateItem[]> = {}
    for (const exchange of assistantHistory) {
      if (exchange.status !== 'complete' || !exchange.response?.suggested_actions) continue
      for (const action of exchange.response.suggested_actions) {
        if (action.action_type === 'library_update') {
          const payload = action.payload as { search_id?: string; updates?: { index: number; reference_id: string; ingestion_status: string }[] } | undefined
          const searchId = payload?.search_id
          const updates = payload?.updates
          if (searchId && updates?.length) {
            if (!lookup[searchId]) lookup[searchId] = []
            for (const u of updates) {
              lookup[searchId].push({
                index: u.index,
                reference_id: u.reference_id,
                ingestion_status: u.ingestion_status as LibraryUpdateItem['ingestion_status'],
              })
            }
          }
        }
      }
    }
    return lookup
  }, [assistantHistory])

  // True when any exchange has inline search results visible (not closed by user)
  const hasVisibleInlineResults = useMemo(() => {
    return assistantHistory.some(exchange => {
      if (closedInlineResults.has(exchange.id)) return false
      return exchange.response?.suggested_actions?.some(
        a => a.action_type === 'search_results' &&
          (a.payload as { papers?: unknown[] } | undefined)?.papers?.length
      )
    })
  }, [assistantHistory, closedInlineResults])

  // ========== EVENT HANDLERS ==========

  const handleSendMessage = (content: string) => {
    const trimmed = content.trim()
    if (!trimmed) return

    if (trimmed.startsWith('/')) {
      if (!activeChannelId) {
        toast.warning('Select a channel before asking Scholar AI.')
        return
      }
      if (assistantMutation.isPending) return

      const commandBody = trimmed.slice(1).trim()
      if (!commandBody) {
        toast.warning('Add a command after the slash (e.g., /reason What should we do next?).')
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
        toast.warning('Add a question after the slash (e.g., /reason What is next?) to ask Scholar AI.')
        return
      }

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

      sendAssistantMessage({
        question,
        reasoning,
        scope: assistantScope,
        recentSearchResults,
        recentSearchId: referenceSearchResults?.searchId,
      })
      return
    }

    if (!activeChannelId && !editingMessage) {
      toast.warning('Select a channel before sending messages.')
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
      toast.warning('Channel name is required.')
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
            return (
              <AssistantExchangeRenderer
                key={exchange.id}
                exchange={exchange}
                openrouterModels={openrouterModels}
                currentModelInfo={currentModelInfo}
                authorLabel={resolveAuthorLabel(exchange.author)}
                onCancelRequest={cancelAssistantRequest}
                onSuggestedAction={handleSuggestedAction}
                onNavigateToPaper={navigateToPaper}
                paperActionPending={paperActionMutation.isPending}
                searchReferencesPending={searchReferencesMutation.isPending}
                projectId={project.id}
                closedInlineResults={closedInlineResults}
                onCloseInlineResult={(id) => setClosedInlineResults(prev => new Set([...prev, id]))}
                libraryUpdatesBySearchId={libraryUpdatesBySearchId}
                onDismissPaper={handleDismissPaper}
              />
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
              <div
                className="hidden sm:flex items-center gap-1.5 rounded-lg border border-gray-200 bg-gray-50 px-2 py-1.5 text-xs text-gray-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300"
                title="AI model - configure in Project Settings"
              >
                <Bot className="h-3.5 w-3.5" />
                <span className="max-w-[100px] truncate">{currentModelInfo.name}</span>
              </div>

              {activeChannel && (
                <div className="flex items-center gap-1">
                  {activeChannel.scope && (
                    <button
                      type="button"
                      onClick={() => setOpenDialog('resources')}
                      className="inline-flex items-center gap-1 rounded-lg border border-gray-200 p-1.5 sm:px-2.5 sm:py-1.5 text-gray-600 transition hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                      title="Channel resources"
                    >
                      <FolderOpen className="h-3.5 w-3.5 text-indigo-500" />
                      <span className="hidden sm:inline text-xs">Resources</span>
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setOpenDialog('artifacts')}
                    className="inline-flex items-center gap-1 rounded-lg border border-gray-200 p-1.5 sm:px-2.5 sm:py-1.5 text-gray-600 transition hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                    title="Artifacts"
                  >
                    <Puzzle className="h-3.5 w-3.5 text-emerald-500" />
                    <span className="hidden sm:inline text-xs">Artifacts</span>
                    {artifactsCount > 0 && (
                      <span className="inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-emerald-500 px-1 text-[10px] font-semibold text-white">
                        {artifactsCount}
                      </span>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => setOpenDialog('discoveries')}
                    className="inline-flex items-center gap-1 rounded-lg border border-gray-200 p-1.5 sm:px-2.5 sm:py-1.5 text-gray-600 transition hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                    title="Discoveries"
                  >
                    <Search className="h-3.5 w-3.5 text-amber-500" />
                    <span className="hidden sm:inline text-xs">Discoveries</span>
                    {!isChannelSwitching && discoveryQueue.papers.length > 0 && (
                      <span className="inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-semibold text-white">
                        {discoveryQueue.papers.length}
                      </span>
                    )}
                  </button>
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
              {!isChannelSwitching && !(activeChannelId && ingestionUnverifiedChannels.has(activeChannelId)) && (discoveryQueue.papers.length > 0 || ingestionSummary) && (
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
                          onClick={() => navigate(`/projects/${getProjectUrlId(project)}/library/references`)}
                          className="rounded-lg border border-emerald-300 px-2.5 py-1 sm:px-3 sm:py-1.5 text-[10px] sm:text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 dark:border-emerald-500/40 dark:text-emerald-300 dark:hover:bg-emerald-500/20"
                        >
                          View in Library
                        </button>
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
                  ) : discoveryQueue.papers.length > 0 && activeChannelId && !dismissedNotificationChannels.has(activeChannelId) && !hasVisibleInlineResults ? (
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
                onDeepResearch={discussionEnabled && hasAnyApiKey && canUseDeepResearch && activeChannelId ? handleOpenDeepResearch : undefined}
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

      {/* Dialogs - portaled to body so backdrop-filter covers the entire viewport */}
      {openDialog && activeChannel && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-gray-900/50 sm:px-4 backdrop-blur-md dark:bg-black/70"
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
        </div>,
        document.body
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

      {/* Deep Research Modal */}
      {isDeepResearchModalOpen && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setIsDeepResearchModalOpen(false)}>
          <div
            className="w-full sm:max-w-[560px] rounded-t-2xl sm:rounded-2xl bg-slate-900 shadow-2xl shadow-black/40 border border-slate-800/80 overflow-visible"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header — minimal, just close button */}
            <div className="flex items-center justify-between px-6 pt-5 pb-0">
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/15">
                  <FlaskConical className="h-4 w-4 text-indigo-400" />
                </div>
                <span className="text-sm font-medium text-slate-400">Deep Research</span>
              </div>
              <button
                type="button"
                onClick={() => setIsDeepResearchModalOpen(false)}
                className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-300"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Hero — research question front and center */}
            <div className="px-6 pt-5 pb-2">
              <h2 className="text-xl font-semibold text-slate-100 leading-tight">
                What do you want to research?
              </h2>
              <p className="mt-1.5 text-sm text-slate-500">
                AI will search the web comprehensively and synthesize a cited report.
              </p>

              <textarea
                value={deepResearchQuestion}
                onChange={(e) => setDeepResearchQuestion(e.target.value)}
                rows={4}
                maxLength={5000}
                className="mt-4 w-full resize-none rounded-xl border border-slate-700/80 bg-slate-800/60 px-4 py-3 text-[15px] leading-relaxed text-slate-100 placeholder-slate-500 transition-colors focus:border-indigo-500/60 focus:bg-slate-800 focus:outline-none focus:ring-1 focus:ring-indigo-500/40"
                placeholder="e.g. What are the latest approaches to transformer-based protein folding and how do they compare to AlphaFold3?"
                autoFocus
              />

              <div className="mt-1.5 flex items-center justify-between">
                <span className="text-xs text-slate-600">
                  {deepResearchQuestion.length > 0 && `${deepResearchQuestion.length.toLocaleString()} / 5,000`}
                </span>
                <span className="text-xs text-slate-600">Typically 2-15 min</span>
              </div>
            </div>

            {/* Compact model selector — horizontal pills */}
            <div className="px-6 pt-3 pb-1">
              <div className="flex items-center gap-2 mb-2.5">
                <span className="text-xs font-medium text-slate-400">Model</span>
              </div>
              <div className="relative flex flex-wrap gap-1.5 overflow-visible">
                {[
                  {
                    id: 'openai/o4-mini-deep-research',
                    label: 'o4-mini',
                    badge: 'Recommended',
                    badgeColor: 'bg-emerald-500/20 text-emerald-400',
                    tooltip: 'Fast & affordable. Web search + synthesis. Best for most research queries.',
                  },
                  {
                    id: 'openai/o3-deep-research',
                    label: 'o3',
                    badge: 'Premium',
                    badgeColor: 'bg-amber-500/20 text-amber-400',
                    tooltip: 'Premium reasoning with 100K output. For complex multi-step analysis requiring deeper synthesis.',
                  },
                  {
                    id: 'perplexity/sonar-deep-research',
                    label: 'Sonar',
                    badge: null,
                    badgeColor: '',
                    tooltip: 'Iterative source evaluation by Perplexity. Best for current events & multi-domain topics.',
                  },
                ].map((model) => {
                  const isActive = deepResearchModel === model.id
                  return (
                    <div key={model.id} className="group relative">
                      <button
                        type="button"
                        onClick={() => setDeepResearchModel(model.id)}
                        className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                          isActive
                            ? 'bg-indigo-500/15 text-indigo-300 ring-1 ring-indigo-500/40'
                            : 'bg-slate-800/80 text-slate-400 ring-1 ring-slate-700/60 hover:bg-slate-800 hover:text-slate-300 hover:ring-slate-600'
                        }`}
                      >
                        {model.label}
                        {model.badge && (
                          <span className={`rounded px-1 py-0.5 text-[10px] leading-none font-medium ${model.badgeColor}`}>
                            {model.badge}
                          </span>
                        )}
                      </button>
                      <div className="pointer-events-none absolute left-0 bottom-full z-50 mb-2 w-56 rounded-lg bg-slate-950 px-3 py-2 text-[11px] leading-relaxed text-slate-300 opacity-0 shadow-xl ring-1 ring-slate-700 transition-opacity group-hover:opacity-100">
                        {model.tooltip}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Collapsible library context */}
            <div className="px-6 pt-4 pb-2">
              <button
                type="button"
                onClick={() => setDeepResearchLibraryOpen(!deepResearchLibraryOpen)}
                className="flex w-full items-center justify-between rounded-lg bg-slate-800/50 px-3 py-2.5 transition-colors hover:bg-slate-800/80"
              >
                <div className="flex items-center gap-2">
                  <Library className="h-3.5 w-3.5 text-slate-500" />
                  <span className="text-xs font-medium text-slate-400">
                    Library context
                    {deepResearchSelectedRefs.size > 0 && (
                      <span className="ml-1.5 inline-flex items-center justify-center rounded-full bg-indigo-500/20 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-indigo-400">
                        {deepResearchSelectedRefs.size}
                      </span>
                    )}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-slate-600">Optional</span>
                  {deepResearchLibraryOpen ? (
                    <ChevronUp className="h-3.5 w-3.5 text-slate-500" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5 text-slate-500" />
                  )}
                </div>
              </button>

              {deepResearchLibraryOpen && (
                <div className="mt-2 rounded-lg border border-slate-700/60 bg-slate-800/30">
                  {(availableReferencesQuery.data || []).length > 0 && (
                    <div className="border-b border-slate-700/40">
                      <div className="flex items-center gap-2 px-3 py-1.5">
                        <Search className="h-3 w-3 text-slate-500" />
                        <input
                          type="text"
                          placeholder="Search references..."
                          value={deepResearchRefSearch}
                          onChange={(e) => setDeepResearchRefSearch(e.target.value)}
                          className="flex-1 bg-transparent text-xs text-slate-300 placeholder-slate-600 outline-none"
                        />
                        <button
                          type="button"
                          onClick={() => {
                            const allIds = (availableReferencesQuery.data || [])
                              .filter(r => r.reference_id)
                              .map(r => r.reference_id)
                            setDeepResearchSelectedRefs(new Set(allIds))
                          }}
                          className="text-[11px] text-indigo-400 hover:text-indigo-300 transition-colors"
                        >
                          All
                        </button>
                        <span className="text-slate-700">|</span>
                        <button
                          type="button"
                          onClick={() => setDeepResearchSelectedRefs(new Set())}
                          className="text-[11px] text-indigo-400 hover:text-indigo-300 transition-colors"
                        >
                          Clear
                        </button>
                      </div>
                    </div>
                  )}

                  {availableReferencesQuery.isLoading ? (
                    <div className="flex items-center gap-2 px-3 py-4 text-sm text-slate-500">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Loading references...
                    </div>
                  ) : (availableReferencesQuery.data || []).length === 0 ? (
                    <p className="px-3 py-4 text-xs text-slate-500">No approved references in this project yet.</p>
                  ) : (
                    <div className="max-h-44 overflow-y-auto">
                      <div className="divide-y divide-slate-700/30">
                        {(availableReferencesQuery.data || []).filter((ref) => {
                          if (!deepResearchRefSearch.trim()) return true
                          const q = deepResearchRefSearch.toLowerCase()
                          return (
                            ref.reference?.title?.toLowerCase().includes(q) ||
                            ref.reference?.authors?.some((a: string) => a.toLowerCase().includes(q)) ||
                            ref.reference?.journal?.toLowerCase().includes(q)
                          )
                        }).map((ref) => {
                          const isSelected = deepResearchSelectedRefs.has(ref.reference_id)
                          return (
                            <label
                              key={ref.reference_id}
                              className="flex cursor-pointer items-start gap-2.5 px-3 py-2 transition-colors hover:bg-slate-700/20"
                            >
                              <div className={`mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border transition-colors ${
                                isSelected
                                  ? 'border-indigo-500 bg-indigo-500'
                                  : 'border-slate-600 hover:border-slate-500'
                              }`}>
                                {isSelected && <Check className="h-3 w-3 text-white" />}
                              </div>
                              <input
                                type="checkbox"
                                className="sr-only"
                                checked={isSelected}
                                onChange={() =>
                                  setDeepResearchSelectedRefs(prev => {
                                    const next = new Set(prev)
                                    next.has(ref.reference_id) ? next.delete(ref.reference_id) : next.add(ref.reference_id)
                                    return next
                                  })
                                }
                              />
                              <div className="min-w-0">
                                <p className="truncate text-sm text-slate-300">
                                  {ref.reference?.title || 'Untitled Reference'}
                                </p>
                                {(ref.reference?.authors?.length ?? 0) > 0 && (
                                  <p className="truncate text-xs text-slate-500">
                                    {ref.reference!.authors!.slice(0, 2).join(', ')}
                                    {ref.reference!.authors!.length > 2 ? ' et al.' : ''}
                                    {ref.reference?.year ? ` \u00b7 ${ref.reference.year}` : ''}
                                  </p>
                                )}
                              </div>
                            </label>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Action bar — sticky bottom with visual separation */}
            <div className="sticky bottom-0 flex items-center justify-between border-t border-slate-800 bg-slate-900/95 px-6 py-4 backdrop-blur-sm">
              <button
                type="button"
                onClick={() => setIsDeepResearchModalOpen(false)}
                className="rounded-lg px-4 py-2 text-sm font-medium text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-300"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleStartDeepResearch}
                disabled={!deepResearchQuestion.trim()}
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition-all hover:bg-indigo-500 hover:shadow-indigo-500/30 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-500 disabled:shadow-none"
              >
                <FlaskConical className="h-4 w-4" />
                Start research
              </button>
            </div>
          </div>
        </div>
      )}

      {showWelcome && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-gray-900/50 backdrop-blur-sm dark:bg-black/70" aria-hidden="true" onClick={() => { markScholarAISeen(); setShowWelcome(false) }} />
          <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-xl dark:bg-slate-900">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-500/20">
                <Sparkles className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
              </div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">Welcome to Scholar AI</h2>
            </div>
            <ul className="mt-5 space-y-3 text-sm text-gray-600 dark:text-slate-300">
              <li className="flex items-start gap-2.5">
                <Bot className="mt-0.5 h-4 w-4 flex-shrink-0 text-indigo-500" />
                <span><strong>Multi-model AI</strong> — GPT, Claude, Gemini, DeepSeek — pick the best model for your task</span>
              </li>
              <li className="flex items-start gap-2.5">
                <Search className="mt-0.5 h-4 w-4 flex-shrink-0 text-indigo-500" />
                <span><strong>Research tools</strong> — search papers, manage references, analyze your library</span>
              </li>
              <li className="flex items-start gap-2.5">
                <Hash className="mt-0.5 h-4 w-4 flex-shrink-0 text-indigo-500" />
                <span><strong>Channels</strong> — organize conversations by topic like methodology or literature review</span>
              </li>
              <li className="flex items-start gap-2.5">
                <BookOpen className="mt-0.5 h-4 w-4 flex-shrink-0 text-indigo-500" />
                <span><strong>Context-aware</strong> — Scholar AI knows your project's papers, references, and objectives</span>
              </li>
            </ul>
            <button
              type="button"
              onClick={() => { markScholarAISeen(); setShowWelcome(false) }}
              className="mt-6 w-full rounded-full bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 dark:focus:ring-offset-slate-900"
            >
              Get Started
            </button>
          </div>
        </div>,
        document.body
      )}
    </>
  )
}

export default ProjectDiscussion
