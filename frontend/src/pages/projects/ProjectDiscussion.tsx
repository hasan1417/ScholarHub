import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageCircle, Loader2, AlertCircle, Plus, Sparkles, X, Bot } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { formatDistanceToNow } from 'date-fns'
import { useProjectContext } from './ProjectLayout'
import { useAuth } from '../../contexts/AuthContext'
import { projectDiscussionAPI, buildApiUrl, refreshAuthToken } from '../../services/api'
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
} from '../../types'
import MessageInput from '../../components/discussion/MessageInput'
import DiscussionThread from '../../components/discussion/DiscussionThread'
import DiscussionChannelSidebar from '../../components/discussion/DiscussionChannelSidebar'
import ChannelResourcePanel from '../../components/discussion/ChannelResourcePanel'
import ChannelTaskDrawer from '../../components/discussion/ChannelTaskDrawer'

type AssistantExchange = {
  id: string
  question: string
  response: DiscussionAssistantResponse
  createdAt: Date
  completedAt?: Date
  appliedActions: string[]
  status: 'pending' | 'streaming' | 'complete'
  displayMessage: string
  author?: { id?: string; name?: { display?: string; first?: string; last?: string } | string }
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
  const queryClient = useQueryClient()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const typingTimers = useRef<Record<string, number>>({})
  const streamingFlags = useRef<Record<string, boolean>>({})
  const STORAGE_PREFIX = `assistantHistory:${project.id}`

  const buildStorageKey = useCallback(
    (channelId: string | null) => {
      if (!channelId) return null
      return `${STORAGE_PREFIX}:${channelId}`
    },
    [STORAGE_PREFIX],
  )

  const hydrateAssistantHistory = useCallback((raw: unknown): AssistantExchange[] => {
    if (!Array.isArray(raw)) return []
    return raw
      .map((item) => {
        if (!item || typeof item !== 'object') return null
        const entry = item as Partial<AssistantExchange> & {
          createdAt?: string
          completedAt?: string | null
        }
        const createdAt = entry.createdAt ? new Date(entry.createdAt) : new Date()
        const completedAt = entry.completedAt ? new Date(entry.completedAt) : undefined
        return {
          id: entry.id || createAssistantEntryId(),
          question: entry.question || '',
          response: entry.response || {
            message: '',
            citations: [],
            reasoning_used: false,
            model: '',
            usage: undefined,
            suggested_actions: [],
          },
          createdAt,
          completedAt,
          appliedActions: entry.appliedActions || [],
          status: entry.status === 'streaming' ? 'complete' : entry.status || 'complete',
          displayMessage:
            entry.displayMessage || entry.response?.message || '',
          author: entry.author,
        } satisfies AssistantExchange
      })
      .filter(Boolean) as AssistantExchange[]
  }, [])

  const [replyingTo, setReplyingTo] = useState<{ id: string; userName: string } | null>(null)
  const [editingMessage, setEditingMessage] = useState<{ id: string; content: string } | null>(null)
  const [activeChannelId, setActiveChannelId] = useState<string | null>(null)
const [isCreateChannelModalOpen, setIsCreateChannelModalOpen] = useState(false)
const [newChannelName, setNewChannelName] = useState('')
const [newChannelDescription, setNewChannelDescription] = useState('')
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
  const [openDialog, setOpenDialog] = useState<'resources' | 'tasks' | null>(null)
  const viewerDisplayName = useMemo(() => {
    if (!user) return 'You'
    const parts = [user.first_name, user.last_name].filter(Boolean).join(' ').trim()
    if (parts) return parts
    return user.email || 'You'
  }, [user?.first_name, user?.last_name, user?.email])

  const resolveAuthorLabel = useCallback(
    (author?: AssistantExchange['author']) => {
      console.log('🔍 resolveAuthorLabel called with:', JSON.stringify(author, null, 2))

      if (!author) return 'Someone'

      // If it's the current user, always use consistent name
      const sameUser = Boolean(author.id && user?.id && author.id === user.id)
      if (sameUser) {
        console.log('✅ Same user, returning:', viewerDisplayName)
        return viewerDisplayName || 'You'
      }

      // If author.name is a string, use it directly
      if (typeof author.name === 'string' && author.name.trim()) {
        console.log('✅ String name, returning:', author.name.trim())
        return author.name.trim()
      }

      // If author.name is an object, try display first, then combine first + last
      if (author.name && typeof author.name === 'object') {
        const nameObj = author.name as { display?: string; first?: string; last?: string }
        console.log('📦 Name object:', nameObj)

        if (nameObj.display?.trim()) {
          console.log('✅ Using display field:', nameObj.display.trim())
          return nameObj.display.trim()
        }

        const first = nameObj.first?.trim() || ''
        const last = nameObj.last?.trim() || ''
        const combined = [first, last].filter(Boolean).join(' ')
        console.log('✅ Combined first+last:', combined, '(first:', first, 'last:', last, ')')
        if (first || last) {
          return combined
        }
      }

      console.log('⚠️ Fallback to Someone')
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

  const channelsQuery = useQuery({
    queryKey: ['projectDiscussionChannels', project.id],
    queryFn: async () => {
      const response = await projectDiscussionAPI.listChannels(project.id)
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
  })

  const serverAssistantHistory = useMemo<AssistantExchange[]>(() => {
    if (!assistantHistoryQuery.data) return []
    return assistantHistoryQuery.data.map((item) => {
      const createdAt = item.created_at ? new Date(item.created_at) : new Date()
      const response = item.response
      const lookup = buildCitationLookup(response.citations)
      return {
        id: item.id,
        question: item.question,
        response,
        createdAt,
        completedAt: createdAt,
        appliedActions: [],
        status: 'complete',
        displayMessage: formatAssistantMessage(response.message, lookup),
        author: item.author ?? undefined,
      }
    })
  }, [assistantHistoryQuery.data])

  useEffect(() => {
    setOpenDialog(null)
  }, [activeChannelId])

  useEffect(() => {
    if (!activeChannelId) return
    setAssistantHistory((prev) => {
      const idsFromServer = new Set(serverAssistantHistory.map((entry) => entry.id))
      const unsynced = prev.filter((entry) => !idsFromServer.has(entry.id))
      const merged = [...serverAssistantHistory, ...unsynced].sort(
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

  useEffect(() => {
    setReplyingTo(null)
    setEditingMessage(null)
    setAssistantReasoning(false)
    Object.values(typingTimers.current).forEach((timerId) => window.clearTimeout(timerId))
    typingTimers.current = {}
    streamingFlags.current = {}

    if (typeof window === 'undefined') {
      setAssistantHistory([])
      return
    }

    if (!activeChannelId) {
      setAssistantHistory([])
      return
    }

    try {
      const storageKey = buildStorageKey(activeChannelId)
      const rawValue = storageKey ? window.localStorage.getItem(storageKey) : null
      if (!rawValue) {
        setAssistantHistory([])
        return
      }
      const parsed = JSON.parse(rawValue)
      setAssistantHistory(hydrateAssistantHistory(parsed))
    } catch (error) {
      console.error('Failed to load assistant history from storage', error)
      setAssistantHistory([])
    }
  }, [activeChannelId, buildStorageKey, hydrateAssistantHistory])

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

  // Fetch stats
  const { data: stats } = useQuery({
    queryKey: ['projectDiscussionStats', project.id, activeChannelId],
    queryFn: async () => {
      const response = await projectDiscussionAPI.getStats(project.id, {
        channelId: activeChannelId ?? undefined,
      })
      return response.data
    },
    enabled: Boolean(activeChannelId),
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  const handleDiscussionEvent = useCallback(
    (payload: any) => {
      if (!payload || payload.project_id !== project.id) {
        return
      }
      if (!activeChannelId || payload.channel_id !== activeChannelId) {
        return
      }

      if (payload.event === 'assistant_reply') {
        const exchange = payload.exchange
        if (!exchange) {
          return
        }
        if (exchange.author?.id && user?.id && exchange.author.id === user.id) {
          return
        }
        const exchangeId: string = exchange.id || createAssistantEntryId()
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
           question: exchange.question || '',
           response,
           createdAt,
           completedAt: createdAt,
           appliedActions: [],
           status: 'complete',
           displayMessage: formatted,
           author: exchange.author,
         }
         return [...prev, entry]
       })
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
    }: {
      name: string
      description?: string | null
    }) => {
      const payload = {
        name,
        description: description && description.trim().length > 0 ? description.trim() : undefined,
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
      payload: { name?: string; description?: string | null; is_archived?: boolean }
    }) => {
      const response = await projectDiscussionAPI.updateChannel(project.id, channelId, payload)
      return response.data
    },
    onSuccess: (channel) => {
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionChannels', project.id] })
      queryClient.invalidateQueries({ queryKey: ['projectDiscussionStats', project.id, channel.id] })
      queryClient.invalidateQueries({ queryKey: ['projectDiscussion', project.id, channel.id] })

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

  const assistantMutation = useMutation({
    mutationFn: async (variables: { id: string; question: string; reasoning: boolean; scope: string[] }) => {
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
      })

      const execute = async () =>
        fetch(url, {
          method: 'POST',
          headers,
          body,
          credentials: 'include',
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
      }
      setAssistantHistory((prev) => [...prev, placeholder])
      return { entryId }
    },
    onSuccess: (data, variables, context) => {
      const entryId = context?.entryId || createAssistantEntryId()
      const finishedAt = new Date()
      setAssistantHistory((prev) => {
      const exists = prev.some((entry) => entry.id === entryId)
      if (!exists) {
        return [
          ...prev,
          {
            id: entryId,
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
      console.error('Failed to invoke assistant:', error)
      if (context?.entryId) {
        setAssistantHistory((prev) => prev.filter((entry) => entry.id !== context.entryId))
        delete streamingFlags.current[context.entryId]
      }
      alert('Unable to reach Scholar AI right now. Please try again.')
    },
  })

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
        onSuccess: () => {
          setAssistantHistory((prev) =>
            prev.map((entry) =>
              entry.id === exchange.id
                ? { ...entry, appliedActions: [...entry.appliedActions, actionKey] }
                : entry,
            ),
          )
        },
        onError: (error) => {
          console.error('Failed to create task from assistant suggestion:', error)
          alert('Unable to create task right now. Please try again.')
        },
      })
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

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!activeChannelId) return
    const storageKey = buildStorageKey(activeChannelId)
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
  }, [assistantHistory, activeChannelId, buildStorageKey])

  const handleSendMessage = (content: string) => {
    const trimmed = content.trim()
    if (!trimmed) return

    // Slash commands trigger the assistant
    if (trimmed.startsWith('/')) {
      if (!activeChannelId) {
        alert('Select a channel before asking Scholar AI.')
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
      assistantMutation.mutate({ id: entryId, question, reasoning, scope: assistantScope })
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
    setIsCreateChannelModalOpen(true)
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
    })
  }

  const activeChannel = channels.find((channel) => channel.id === activeChannelId) ?? null
  const hasAssistantHistory = assistantHistory.length > 0

  const renderDiscussionContent = () => {
    if (isLoading || channelsQuery.isLoading) {
      return (
        <div className="flex h-full items-center justify-center">
          <div className="text-center">
            <Loader2 className="mx-auto h-8 w-8 animate-spin text-indigo-600 dark:text-indigo-300" />
            <p className="mt-2 text-sm text-gray-600 dark:text-slate-300">Loading discussion...</p>
          </div>
        </div>
      )
    }

    if (isError) {
      return (
        <div className="flex h-full items-center justify-center">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-center dark:border-red-500/40 dark:bg-red-500/10">
            <AlertCircle className="mx-auto h-8 w-8 text-red-600 dark:text-red-300" />
            <p className="mt-2 text-sm font-medium text-red-900 dark:text-red-200">Failed to load discussion</p>
            <p className="mt-1 text-xs text-red-700 dark:text-red-200/80">{(error as Error)?.message || 'Please try again later'}</p>
          </div>
        </div>
      )
    }

    const hasThreads = orderedThreads.length > 0
    if (!hasThreads && !hasAssistantHistory) {
      return (
        <div className="flex h-full items-center justify-center">
          <div className="text-center">
            <MessageCircle className="mx-auto h-12 w-12 text-gray-300 dark:text-slate-600" />
            <h3 className="mt-4 text-sm font-medium text-gray-900 dark:text-slate-100">No messages yet</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">Start the conversation by sending a message or ask Scholar AI for help.</p>
          </div>
        </div>
      )
    }

    return (
      <div className="space-y-4">
        {conversationItems.map((item) => {
          if (item.kind === 'assistant') {
            const { exchange } = item
          console.log('Rendering AI exchange:', exchange.id, 'author:', exchange.author)
          const citationLookup = buildCitationLookup(exchange.response.citations)
          const formattedMessage = formatAssistantMessage(exchange.response.message, citationLookup)
          const askedLabel = formatDistanceToNow(exchange.createdAt, { addSuffix: true })
          const answerLabel = exchange.completedAt
            ? formatDistanceToNow(exchange.completedAt, { addSuffix: true })
            : askedLabel
          const displayedMessage = exchange.displayMessage || formattedMessage
          const showTyping = !displayedMessage && exchange.status !== 'complete'
          const authorLabel = resolveAuthorLabel(exchange.author)
          console.log('authorLabel result:', authorLabel)
          const avatarText = authorLabel.trim().charAt(0).toUpperCase() || 'U'
          const promptBubbleClass = 'inline-block max-w-fit rounded-2xl bg-purple-50/70 px-4 py-2 shadow-sm ring-2 ring-purple-200 transition dark:bg-purple-500/15 dark:ring-purple-400/40 dark:shadow-purple-900/30'
          const responseBubbleClass = 'inline-block max-w-fit rounded-2xl bg-white px-4 py-2 transition dark:bg-slate-800/70 dark:ring-1 dark:ring-slate-700'
          return (
            <div key={exchange.id} className="border-b border-gray-100 pb-4 last:border-b-0 dark:border-slate-700">
              <div className="space-y-4 pt-4">
                <div className="flex items-start gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-sm font-medium text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-200">
                    {avatarText}
                  </div>
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-gray-900">{authorLabel}</span>
                      <span className="text-xs text-gray-500">{askedLabel}</span>
                      <span className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-medium text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200">
                        <Bot className="h-3 w-3" />
                        AI prompt
                      </span>
                    </div>
                    <div className={promptBubbleClass}>
                      <p className="text-sm text-gray-700">{exchange.question}</p>
                    </div>
                  </div>
                  <div className="relative flex-shrink-0 w-6"></div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-sm font-medium text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-200">
                    AI
                  </div>
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-gray-900">Scholar AI</span>
                      <span className="text-xs text-gray-500">{answerLabel}</span>
                      {exchange.response.reasoning_used && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-200">
                          <Sparkles className="h-3 w-3" />
                          Reasoning
                        </span>
                      )}
                    </div>
                    <div className={responseBubbleClass}>
                      {showTyping ? (
                        <div className="flex items-center gap-2 text-sm text-indigo-600 dark:text-indigo-300">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Scholar AI is composing…
                        </div>
                      ) : (
                        <div className="prose prose-sm max-w-none text-gray-900 prose-headings:text-gray-900 prose-p:leading-relaxed prose-li:marker:text-gray-400 dark:prose-invert">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {displayedMessage}
                          </ReactMarkdown>
                        </div>
                      )}
                    </div>
                    {!showTyping && exchange.response.citations.length > 0 && (
                      <div className="mt-2 space-y-1">
                        <p className="text-[11px] uppercase tracking-wide text-gray-400 dark:text-slate-500">Sources</p>
                        <div className="flex flex-wrap gap-2">
                          {exchange.response.citations.map((citation) => (
                            <span
                              key={`${exchange.id}-${citation.origin}-${citation.origin_id}`}
                              className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-200"
                            >
                              {citation.label}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {!showTyping && exchange.response.suggested_actions && exchange.response.suggested_actions.length > 0 && (
                      <div className="mt-2 space-y-1">
                        <p className="text-[11px] uppercase tracking-wide text-gray-400">Suggested actions</p>
                        <div className="flex flex-wrap gap-2">
                          {exchange.response.suggested_actions.map((action, idx) => {
                            const actionKey = `${exchange.id}:${idx}`
                            const applied = exchange.appliedActions.includes(actionKey)
                            return (
                              <button
                                key={actionKey}
                                type="button"
                                onClick={() => handleSuggestedAction(exchange, action, idx)}
                                disabled={applied || createTaskMutation.isPending}
                                className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium transition ${applied ? 'border-emerald-300 bg-emerald-50 text-emerald-600 dark:border-emerald-400/40 dark:bg-emerald-500/20 dark:text-emerald-200' : 'border-indigo-200 bg-white text-indigo-600 hover:bg-indigo-50 dark:border-indigo-400/40 dark:bg-slate-800/70 dark:text-indigo-200 dark:hover:bg-indigo-500/10'}`}
                              >
                                {applied ? 'Completed' : action.summary}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    )}
                    {!showTyping && (
                      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-gray-400 dark:text-slate-500">
                        {exchange.response.model && <span>Model: {exchange.response.model}</span>}
                        {exchange.response.usage && typeof exchange.response.usage['total_tokens'] === 'number' && (
                          <span>Total tokens: {exchange.response.usage['total_tokens'] as number}</span>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="relative flex-shrink-0 w-6"></div>
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

  return (
    <>
      <div className="flex h-[calc(100vh-160px)] min-h-[32rem] w-full gap-3 overflow-hidden">
        <DiscussionChannelSidebar
          channels={channels}
          activeChannelId={activeChannelId}
          onSelectChannel={setActiveChannelId}
          onCreateChannel={handleOpenCreateChannel}
          isCreating={createChannelMutation.isPending}
          onArchiveToggle={handleToggleArchive}
        />

        <div className="flex flex-1 min-h-0 min-w-0 flex-col rounded-2xl border border-gray-200 bg-white shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900/40">
          <div className="flex items-center justify-between border-b border-gray-200 p-4 dark:border-slate-700">
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <MessageCircle className="h-5 w-5 text-indigo-600 dark:text-indigo-300" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">
                  {activeChannel ? activeChannel.name : 'Project Discussion'}
                </h2>
              </div>
              {activeChannel?.description && (
                <p className="text-xs text-gray-500 dark:text-slate-400">{activeChannel.description}</p>
              )}
            </div>
            <div className="flex items-center gap-3 text-sm text-gray-600 dark:text-slate-400">
              <button
                type="button"
                onClick={() => setOpenDialog('resources')}
                className="inline-flex items-center gap-2 rounded-full border border-indigo-200 px-3 py-1.5 text-xs font-medium text-indigo-600 transition hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
                disabled={!activeChannel}
              >
                Channel resources
              </button>
              <button
                type="button"
                onClick={() => setOpenDialog('tasks')}
                className="inline-flex items-center gap-2 rounded-full border border-indigo-200 px-3 py-1.5 text-xs font-medium text-indigo-600 transition hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
                disabled={!activeChannel}
              >
                Channel tasks
              </button>
              {stats && (
                <>
                  <span>{stats.total_threads} threads</span>
                  <span>{stats.total_messages} messages</span>
                </>
              )}
              {activeChannel && activeChannel.is_archived && (
                <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-500/20 dark:text-amber-200">
                  Archived
                </span>
              )}
            </div>
          </div>

          {activeChannel ? (
            <>
              <div className="flex flex-1 min-h-0 overflow-hidden p-4">
                <div className="flex-1 min-h-0 overflow-y-auto pr-2">
                  {renderDiscussionContent()}
                </div>
              </div>

              <div className="border-t border-gray-100 bg-white px-4 py-3 text-xs text-gray-600 dark:border-slate-800 dark:bg-slate-900/40">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500">Scholar AI context</p>
                    <p className="text-xs text-gray-500 dark:text-slate-400">Pick which resources the assistant can reference.</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {ASSISTANT_SCOPE_OPTIONS.map((option) => {
                      const active = assistantScope.includes(option.id)
                      return (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => toggleAssistantScope(option.id)}
                          className={`rounded-full px-3 py-1 text-xs font-medium transition border ${
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
            <div className="flex flex-1 items-center justify-center px-6 py-10">
              <div className="max-w-md text-center">
                <MessageCircle className="mx-auto h-12 w-12 text-gray-300 dark:text-slate-600" />
                {channels.length === 0 ? (
                  <>
                    <h3 className="mt-4 text-base font-semibold text-gray-900 dark:text-slate-100">Create a channel to start the conversation</h3>
                    <p className="mt-2 text-sm text-gray-500 dark:text-slate-400">
                      Organize discussions by topic, meeting, or workstream. Once a channel is created, messages and AI tools will appear here.
                    </p>
                    <button
                      type="button"
                      onClick={handleOpenCreateChannel}
                      className="mt-4 inline-flex items-center gap-2 rounded-full border border-indigo-200 px-4 py-2 text-sm font-medium text-indigo-600 transition hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
                    >
                      <Plus className="h-4 w-4" />
                      New channel
                    </button>
                  </>
                ) : (
                  <>
                    <h3 className="mt-4 text-base font-semibold text-gray-900 dark:text-slate-100">Select a channel to view the conversation</h3>
                    <p className="mt-2 text-sm text-gray-500 dark:text-slate-400">
                      Choose a channel from the sidebar to see messages and start chatting with your team, or create a new channel to organize discussions.
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
          className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900/40 px-4 backdrop-blur-sm dark:bg-black/70"
          onClick={() => setOpenDialog(null)}
        >
          <div
            className="relative w-full max-w-3xl overflow-hidden rounded-2xl bg-white shadow-2xl transition-colors dark:bg-slate-900/90"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between border-b border-gray-200 px-5 py-4 dark:border-slate-700">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-slate-100">
                  {openDialog === 'resources' ? 'Channel resources' : 'Channel tasks'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-slate-400">
                  {openDialog === 'resources'
                    ? `Manage linked resources for ${activeChannel.name}`
                    : `Track action items for ${activeChannel.name}`}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpenDialog(null)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-700"
                aria-label="Close channel dialog"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="max-h-[70vh] overflow-y-auto px-5 py-4">
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
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-gray-900/40 backdrop-blur-sm dark:bg-black/70">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl transition-colors dark:bg-slate-900/90">
            <h3 className="text-base font-semibold text-gray-900 dark:text-slate-100">Create new channel</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">
              Organize conversations by topic, meeting, or workstream.
            </p>
            <form className="mt-4 space-y-4" onSubmit={handleCreateChannelSubmit}>
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
    </>
  )
}

export default ProjectDiscussion
