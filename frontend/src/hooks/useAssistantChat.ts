import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  DiscussionAssistantResponse,
  DiscussionThread as DiscussionThreadType,
} from '../types'
import {
  projectDiscussionAPI,
  buildApiUrl,
  refreshAuthToken,
} from '../services/api'
import discussionWebsocket from '../services/discussionWebsocket'

export type AssistantExchange = {
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
  isWaitingForTools?: boolean
  author?: { id?: string; name?: { display?: string; first?: string; last?: string } | string }
  fromHistory?: boolean
  model?: string
}

export type ConversationItem =
  | { kind: 'thread'; timestamp: number; thread: DiscussionThreadType }
  | { kind: 'assistant'; timestamp: number; exchange: AssistantExchange }

export const stripActionsBlock = (value: string): string =>
  value
    .replace(/<actions>[\s\S]*?<\/actions>/gi, '')
    .replace(/<actions>[\s\S]*$/gi, '')
    .trimEnd()

export const buildCitationLookup = (citations: DiscussionAssistantResponse['citations']) => {
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

export const formatAssistantMessage = (message: string, lookup: Map<string, string>): string => {
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

export function useAssistantChat({
  projectId,
  activeChannelId,
  selectedModel,
  userId,
  viewerDisplayName,
}: {
  projectId: string
  activeChannelId: string | null
  selectedModel: string
  userId?: string
  viewerDisplayName: string
}) {
  const queryClient = useQueryClient()
  const typingTimers = useRef<Record<string, number>>({})
  const streamingFlags = useRef<Record<string, boolean>>({})
  const historyChannelRef = useRef<string | null>(null)
  const assistantAbortController = useRef<AbortController | null>(null)
  const STORAGE_PREFIX = `assistantHistory:${projectId}`

  const [assistantHistory, setAssistantHistory] = useState<AssistantExchange[]>([])

  const buildStorageKey = useCallback(
    (channelId: string | null) => {
      if (!channelId) return null
      return `${STORAGE_PREFIX}:${channelId}`
    },
    [STORAGE_PREFIX]
  )

  const markActionApplied = useCallback((exchangeId: string, actionKey: string) => {
    setAssistantHistory((prev) =>
      prev.map((entry) => {
        if (entry.id !== exchangeId) return entry
        if (entry.appliedActions.includes(actionKey)) return entry
        return { ...entry, appliedActions: [...entry.appliedActions, actionKey] }
      })
    )
  }, [])

  const cancelAssistantRequest = useCallback(() => {
    if (assistantAbortController.current) {
      assistantAbortController.current.abort()
      assistantAbortController.current = null
    }
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

  // Assistant history query (fetch from server)
  const assistantHistoryQuery = useQuery({
    queryKey: ['assistant-history', projectId, activeChannelId],
    queryFn: async () => {
      if (!activeChannelId) return []
      const response = await projectDiscussionAPI.listAssistantHistory(projectId, activeChannelId)
      return response.data
    },
    enabled: Boolean(activeChannelId),
    placeholderData: [],
    staleTime: 0,
    refetchOnMount: 'always',
  })

  // Transform server history to AssistantExchange format
  const serverAssistantHistory = useMemo<AssistantExchange[]>(() => {
    if (!assistantHistoryQuery.data || !activeChannelId) return []

    return assistantHistoryQuery.data.map((item) => {
      const createdAt = item.created_at ? new Date(item.created_at) : new Date()
      const response = item.response
      const lookup = buildCitationLookup(response.citations)

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
        isWaitingForTools: isProcessing,
      }
    })
  }, [assistantHistoryQuery.data, activeChannelId])

  // SSE streaming mutation
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
      recentSearchId?: string
      conversationHistory?: Array<{ role: string; content: string }>
    }) => {
      if (!activeChannelId) throw new Error('No channel selected')

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
        author: { id: userId, name: { display: viewerDisplayName } },
      }

      setAssistantHistory((prev) => [...prev, entry])

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
        recent_search_id: recentSearchId,
      })

      const url = buildApiUrl(
        `/projects/${projectId}/discussion/channels/${activeChannelId}/assistant?stream=true`
      )

      const controller = new AbortController()
      assistantAbortController.current = controller

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
                const isFirstToken = accumulatedContent === ''
                accumulatedContent += event.content || ''

                if (isFirstToken) {
                  setAssistantHistory((prev) =>
                    prev.map((e) =>
                      e.id === id
                        ? { ...e, displayMessage: stripActionsBlock(accumulatedContent), isWaitingForTools: false }
                        : e
                    )
                  )
                } else {
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
                }
              } else if (event.type === 'content_reset') {
                if (typingTimers.current[id]) {
                  clearTimeout(typingTimers.current[id])
                  delete typingTimers.current[id]
                }
                accumulatedContent = ''
                setAssistantHistory((prev) =>
                  prev.map((e) =>
                    e.id === id ? { ...e, displayMessage: '' } : e
                  )
                )
              } else if (event.type === 'status') {
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
      const isAbort = error.name === 'AbortError' || error.message?.includes('abort')
      if (isAbort) {
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

  // Clear history when channel changes
  useEffect(() => {
    setAssistantHistory([])
    historyChannelRef.current = activeChannelId
  }, [activeChannelId])

  // Merge server history with local unsynced entries
  useEffect(() => {
    if (!activeChannelId) return

    setAssistantHistory((prev) => {
      const idsFromServer = new Set(serverAssistantHistory.map((entry) => entry.id))

      const localOnlyEntries = prev.filter((entry) => {
        if (idsFromServer.has(entry.id)) return false
        if (entry.status === 'streaming' || entry.status === 'pending') return true
        return false
      })

      const merged = [...serverAssistantHistory, ...localOnlyEntries]
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

  // WebSocket setup
  useEffect(() => {
    if (!projectId || !activeChannelId) return

    const token = localStorage.getItem('access_token') || ''
    discussionWebsocket.connect(projectId, activeChannelId, token)
  }, [projectId, activeChannelId])

  // Handle discussion events from WebSocket
  const handleDiscussionEvent = useCallback(
    (payload: any) => {
      if (!payload || payload.project_id !== projectId) return
      if (!activeChannelId || payload.channel_id !== activeChannelId) return

      if (payload.event === 'message_created' || payload.event === 'message_updated') {
        queryClient.invalidateQueries({ queryKey: ['projectDiscussion', projectId, activeChannelId] })
        return
      }

      if (payload.event === 'message_deleted') {
        const messageId = payload.message_id
        if (messageId) {
          queryClient.setQueryData<DiscussionThreadType[] | undefined>(
            ['projectDiscussion', projectId, activeChannelId],
            (threads) => {
              if (!threads) return threads
              return threads.filter((t) => t.message.id !== messageId)
            }
          )
        }
        return
      }

      if (payload.event === 'assistant_processing') {
        const exchange = payload.exchange
        if (!exchange) return

        if (exchange.author?.id && userId && exchange.author.id === userId) {
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
              statusMessage: exchange.status_message || 'Thinking',
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

      if (payload.event === 'assistant_status') {
        const exchangeId = payload.exchange_id
        const statusMessage = payload.status_message
        if (!exchangeId || !statusMessage) return

        setAssistantHistory((prev) =>
          prev.map((entry) =>
            entry.id === exchangeId && entry.status === 'streaming'
              ? { ...entry, statusMessage, isWaitingForTools: true }
              : entry
          )
        )

        queryClient.setQueryData<typeof assistantHistoryQuery.data>(
          ['assistant-history', projectId, activeChannelId],
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

      if (payload.event === 'assistant_reply') {
        const exchange = payload.exchange
        if (!exchange) return
        const exchangeId: string = exchange.id

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
        queryClient.invalidateQueries({ queryKey: ['assistant-history', projectId, activeChannelId] })
      }
    },
    [projectId, activeChannelId, userId, queryClient]
  )

  // Subscribe to WebSocket discussion events
  useEffect(() => {
    discussionWebsocket.on('discussion_event', handleDiscussionEvent)
    return () => {
      discussionWebsocket.off('discussion_event', handleDiscussionEvent)
    }
  }, [handleDiscussionEvent])

  const sendAssistantMessage = useCallback(
    ({
      question,
      reasoning,
      scope,
      recentSearchResults,
      recentSearchId,
    }: {
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
      recentSearchId?: string
    }) => {
      const entryId = createAssistantEntryId()

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
        scope,
        recentSearchResults,
        recentSearchId,
        conversationHistory,
      })
    },
    [assistantHistory, assistantMutation]
  )

  return {
    assistantHistory,
    setAssistantHistory,
    assistantMutation,
    sendAssistantMessage,
    cancelAssistantRequest,
    markActionApplied,
  }
}
