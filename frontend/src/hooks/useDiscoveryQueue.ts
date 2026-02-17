import { useState, useEffect, useMemo, useCallback } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { projectDiscussionAPI, projectReferencesAPI } from '../services/api'
import { DiscoveredPaper, IngestionStatus } from '../components/discussion/DiscoveredPaperCard'
import { PaperIngestionState, IngestionStatesMap } from '../components/discussion/DiscoveryQueuePanel'

export function useDiscoveryQueue({
  projectId,
  activeChannelId,
}: {
  projectId: string
  activeChannelId: string | null
}) {
  // Reference search results state - stored per channel
  const [searchResultsByChannel, setSearchResultsByChannel] = useState<
    Record<
      string,
      {
        exchangeId: string
        papers: DiscoveredPaper[]
        query: string
        isSearching: boolean
        searchId?: string
      }
    >
  >({})

  // Ingestion state - managed here, passed to DiscoveryQueuePanel
  const [ingestionStatesByChannel, setIngestionStatesByChannel] = useState<
    Record<string, IngestionStatesMap>
  >({})
  const [ingestionUnverifiedChannels, setIngestionUnverifiedChannels] = useState<Set<string>>(new Set())

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

  // Dismissed paper IDs - persisted to localStorage
  const dismissedPapersKey = projectId ? `scholarhub_dismissed_papers_${projectId}` : null
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
        searchId?: string
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
  const dismissedNotificationsKey = projectId ? `scholarhub_dismissed_notifications_${projectId}` : null
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

  const dismissedInCurrentSearch = useMemo(() => {
    if (!activeChannelId) return 0
    const raw = discoveryQueueByChannel[activeChannelId]
    if (!raw?.papers) return 0
    return raw.papers.filter((p) => dismissedPaperIds.has(p.id)).length
  }, [activeChannelId, discoveryQueueByChannel, dismissedPaperIds])

  // Ingestion summary for notification bar
  const ingestionSummary = useMemo(() => {
    if (activeChannelId && ingestionUnverifiedChannels.has(activeChannelId)) return null

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
  }, [currentIngestionStates, activeChannelId, ingestionUnverifiedChannels])

  // Poll backend for fresh ingestion statuses
  const pendingReferenceIds = useMemo(() => {
    return Object.values(currentIngestionStates)
      .filter((s) => s.referenceId && s.status !== 'success')
      .map((s) => s.referenceId)
  }, [currentIngestionStates])

  useEffect(() => {
    if (activeChannelId && ingestionUnverifiedChannels.has(activeChannelId) && pendingReferenceIds.length === 0) {
      setIngestionUnverifiedChannels((prev) => {
        const next = new Set(prev)
        next.delete(activeChannelId)
        return next
      })
    }
  }, [activeChannelId, ingestionUnverifiedChannels, pendingReferenceIds.length])

  const ingestionPollQuery = useQuery({
    queryKey: ['ingestion-status', projectId, ...pendingReferenceIds],
    queryFn: async () => {
      const res = await projectReferencesAPI.getIngestionStatus(projectId, pendingReferenceIds)
      return res.data
    },
    enabled: pendingReferenceIds.length > 0 && !!activeChannelId && !dismissedNotificationChannels.has(activeChannelId),
    refetchInterval: 10_000,
    staleTime: 5_000,
  })

  useEffect(() => {
    const freshStatuses = ingestionPollQuery.data?.statuses
    if (!freshStatuses || !activeChannelId) return

    setIngestionStatesByChannel((prev) => {
      const channelStates = { ...(prev[activeChannelId] || {}) }
      let changed = false
      for (const [paperId, state] of Object.entries(channelStates)) {
        const freshStatus = freshStatuses[state.referenceId]
        if (freshStatus && freshStatus !== state.status) {
          channelStates[paperId] = {
            ...state,
            status: freshStatus as IngestionStatus,
            isAdding: freshStatus === 'pending',
          }
          changed = true
        }
      }
      return changed ? { ...prev, [activeChannelId]: channelStates } : prev
    })

    setIngestionUnverifiedChannels((prev) => {
      if (!prev.has(activeChannelId)) return prev
      const next = new Set(prev)
      next.delete(activeChannelId)
      return next
    })
  }, [ingestionPollQuery.data, activeChannelId])

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

  const handleDismissNotification = useCallback(() => {
    if (!activeChannelId) return
    setDismissedNotificationChannels((prev) => new Set([...prev, activeChannelId]))
  }, [activeChannelId])

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

      const response = await projectDiscussionAPI.searchReferences(projectId, query, { openAccessOnly, maxResults })
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

  return {
    referenceSearchResults,
    setReferenceSearchResults,
    searchResultsByChannel,
    discoveryQueue,
    setDiscoveryQueue,
    discoveryQueueByChannel,
    dismissedInCurrentSearch,
    ingestionSummary,
    currentIngestionStates,
    ingestionStatesByChannel,
    setIngestionStatesByChannel,
    ingestionUnverifiedChannels,
    setIngestionUnverifiedChannels,
    handleIngestionStateChange,
    handleDismissPaper,
    handleDismissNotification,
    resetDismissedPapers,
    dismissedPaperIds,
    dismissedNotificationChannels,
    setDismissedNotificationChannels,
    searchReferencesMutation,
  }
}
