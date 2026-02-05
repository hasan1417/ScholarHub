import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  FileText,
  Filter,
  Loader2,
  MinusCircle,
  RefreshCw,
  RotateCcw,
  Settings2,
  Sparkles,
  Trash2,
  X,
  XCircle,
  Zap,
} from 'lucide-react'
import { projectDiscoveryAPI, projectReferencesAPI } from '../../services/api'
import { Navigate } from 'react-router-dom'
import {
  ProjectDiscoveryPreferences,
  ProjectDiscoverySettingsPayload,
  ProjectDiscoveryResultItem,
  ProjectDiscoveryResultStatus,
  SourceStatsItem,
} from '../../types'
import { useProjectContext } from './ProjectLayout'
import { DiscoveryResultCard } from '../../components/discovery/DiscoveryResultCard'

const AVAILABLE_SOURCES: Array<{ label: string; value: string }> = [
  { label: 'Semantic Scholar', value: 'semantic_scholar' },
  { label: 'arXiv', value: 'arxiv' },
  { label: 'Crossref', value: 'crossref' },
  { label: 'OpenAlex', value: 'openalex' },
  { label: 'PubMed', value: 'pubmed' },
  { label: 'ScienceDirect', value: 'sciencedirect' },
  { label: 'CORE', value: 'core' },
  { label: 'Europe PMC', value: 'europe_pmc' },
]

const DEFAULT_SOURCES = AVAILABLE_SOURCES.map((source) => source.value)
const MIN_REFRESH_INTERVAL_MINUTES = 5
const DEFAULT_REFRESH_INTERVAL_MINUTES = 24 * 60

const toRefreshIntervalHours = (value: string): number | null => {
  if (!value) return null
  const minutes = Number(value)
  if (!Number.isFinite(minutes)) return null
  const normalizedMinutes = Math.max(MIN_REFRESH_INTERVAL_MINUTES, minutes)
  return normalizedMinutes / 60
}

const formatRefreshIntervalSummary = (minutesValue: string): string => {
  const minutes = minutesValue === ''
    ? DEFAULT_REFRESH_INTERVAL_MINUTES
    : Number(minutesValue)
  if (!Number.isFinite(minutes) || minutes <= 0) return 'Auto-refresh off'
  if (minutes < 60) {
    return `Auto-refresh every ${Math.round(minutes)} min`
  }
  const hours = minutes / 60
  if (hours < 24) {
    const roundedHours = Number.isInteger(hours) ? hours : Number(hours.toFixed(1))
    return `Auto-refresh every ${roundedHours} h`
  }
  const days = hours / 24
  const roundedDays = Number.isInteger(days) ? days : Number(days.toFixed(1))
  return `Auto-refresh every ${roundedDays} day${roundedDays === 1 ? '' : 's'}`
}

const STATUS_FILTERS: Array<{ value: ProjectDiscoveryResultStatus | 'all'; label: string }> = [
  { value: 'pending', label: 'Pending' },
  { value: 'promoted', label: 'Promoted' },
  { value: 'dismissed', label: 'Dismissed' },
  { value: 'all', label: 'All' },
]

type SortOption = 'relevance' | 'year_desc' | 'year_asc' | 'has_pdf'

const SORT_OPTIONS: Array<{ value: SortOption; label: string }> = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'year_desc', label: 'Newest' },
  { value: 'year_asc', label: 'Oldest' },
  { value: 'has_pdf', label: 'Has PDF' },
]

// Source presets for quick selection
const SOURCE_PRESETS = {
  fast: {
    label: 'Fast',
    description: 'Quick results from reliable sources',
    sources: ['semantic_scholar', 'arxiv', 'openalex'],
  },
  comprehensive: {
    label: 'All Sources',
    description: 'Search all available databases',
    sources: AVAILABLE_SOURCES.map((s) => s.value),
  },
  biomedical: {
    label: 'Biomedical',
    description: 'PubMed, Europe PMC, and general',
    sources: ['pubmed', 'europe_pmc', 'semantic_scholar', 'crossref'],
  },
} as const

const sanitizeKeywords = (value: string) => {
  const trimmed = value.trim()
  if (!trimmed) return ''
  if (trimmed.toLowerCase() === 'ai') return ''
  return trimmed
}

const getSourceLabel = (source: string): string => {
  const match = AVAILABLE_SOURCES.find((s) => s.value === source)
  return match?.label ?? source
}

type ManualFormState = {
  query: string
  sources: string[]
  maxResults: string
  relevanceThreshold: string
}

type ActiveFormState = {
  query: string
  sources: string[]
  autoRefresh: boolean
  refreshIntervalMinutes: string
  maxResults: string
  relevanceThreshold: string
}

const defaultManualFormState: ManualFormState = {
  query: '',
  sources: DEFAULT_SOURCES,
  maxResults: '',
  relevanceThreshold: '',
}

const defaultActiveFormState: ActiveFormState = {
  query: '',
  sources: DEFAULT_SOURCES,
  autoRefresh: false,
  refreshIntervalMinutes: String(DEFAULT_REFRESH_INTERVAL_MINUTES),
  maxResults: '20',
  relevanceThreshold: '',
}

const formatDateTime = (value?: string | null) => {
  if (!value) return '—'
  const date = new Date(value)
  return date.toLocaleString()
}

const parseList = (value: string) =>
  value
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)

const ProjectDiscovery = () => {
  const { project, currentRole } = useProjectContext()
  const queryClient = useQueryClient()
  const isViewer = currentRole === 'viewer'

  const projectIdea = useMemo(() => project?.idea?.trim() ?? '', [project])
  const projectKeywordPreset = useMemo(() => {
    if (!project?.keywords) return ''
    if (Array.isArray(project.keywords)) {
      return project.keywords.filter(Boolean).join(', ')
    }
    return project.keywords
  }, [project])

  const [manualFormState, setManualFormState] = useState<ManualFormState>(defaultManualFormState)
  const [activeFormState, setActiveFormState] = useState<ActiveFormState>(defaultActiveFormState)
  const [statusFilter, setStatusFilter] = useState<ProjectDiscoveryResultStatus | 'all'>('pending')
  const [sortBy, setSortBy] = useState<SortOption>('relevance')
  const [showPdfOnly, setShowPdfOnly] = useState(false)
  const [activeStatusMessage, setActiveStatusMessage] = useState<string | null>(null)
  const [activeErrorMessage, setActiveErrorMessage] = useState<string | null>(null)
  const [manualStatusMessage, setManualStatusMessage] = useState<string | null>(null)
  const [manualErrorMessage, setManualErrorMessage] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'manual' | 'active'>('manual')
  const [isDeleteMode, setIsDeleteMode] = useState(false)
  const [selectedResults, setSelectedResults] = useState<string[]>([])
  const [promotingIds, setPromotingIds] = useState<Set<string>>(new Set())
  const [dismissingIds, setDismissingIds] = useState<Set<string>>(new Set())
  const [isClearingResults, setIsClearingResults] = useState(false)
  const [resultsLimit, setResultsLimit] = useState(20)
  const [discoveryCooldown, setDiscoveryCooldown] = useState(0) // Seconds remaining
  const [lastSourceStats, setLastSourceStats] = useState<SourceStatsItem[] | null>(null)
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false)
  const [lastRunAtOverride, setLastRunAtOverride] = useState<string | null>(null)
  const hasHydratedActiveForm = useRef(false)
  const activeFormDirtyRef = useRef(false)

  // Cooldown timer effect
  useEffect(() => {
    if (discoveryCooldown <= 0) return
    const timer = setInterval(() => {
      setDiscoveryCooldown((prev) => Math.max(0, prev - 1))
    }, 1000)
    return () => clearInterval(timer)
  }, [discoveryCooldown])

  const manualSessionStart = useMemo(() => {
    if (typeof window === 'undefined') return 0
    const globalAny = window as typeof window & { __shDiscoverySessionStart?: Record<string, number> }
    if (!globalAny.__shDiscoverySessionStart) {
      globalAny.__shDiscoverySessionStart = {}
    }
    if (!globalAny.__shDiscoverySessionStart[project.id]) {
      globalAny.__shDiscoverySessionStart[project.id] = Date.now()
    }
    return globalAny.__shDiscoverySessionStart[project.id]
  }, [project.id])

  const updateManualForm = (updater: (prev: ManualFormState) => ManualFormState) => {
    setManualFormState((prev) => updater(prev))
  }

  const handleStatusFilterChange = (value: ProjectDiscoveryResultStatus | 'all') => {
    setStatusFilter(value)
    setResultsLimit(20) // Reset pagination when filter changes
  }

  const updateActiveForm = (updater: (prev: ActiveFormState) => ActiveFormState) => {
    activeFormDirtyRef.current = true
    setActiveFormState((prev) => updater(prev))
  }

  const settingsQuery = useQuery<ProjectDiscoveryPreferences | null>({
    queryKey: ['project', project.id, 'discoverySettings'],
    queryFn: async () => {
      const response = await projectDiscoveryAPI.getSettings(project.id)
      return response.data
    },
    enabled: !isViewer,
  })

  const resultsQuery = useQuery({
    queryKey: ['project', project.id, 'discoveryResults', statusFilter, resultsLimit],
    queryFn: async () => {
      const response = await projectDiscoveryAPI.listResults(project.id, {
        status: statusFilter === 'all' ? undefined : statusFilter,
        limit: resultsLimit,
      })
      return response.data
    },
    enabled: !isViewer,
  })

  const suggestionsQuery = useQuery({
    queryKey: ['project', project.id, 'referenceSuggestionsForDiscovery'],
    queryFn: async () => {
      try {
        const response = await projectReferencesAPI.listSuggestions(project.id)
        return response.data.suggestions ?? []
      } catch (error) {
        const axiosError = error as { response?: { status?: number; data?: { detail?: unknown } } }
        if (axiosError.response?.status === 404) {
          return []
        }
        throw error
      }
    },
    staleTime: 60_000,
    enabled: !isViewer,
  })

  const allResults = useMemo(() => resultsQuery.data?.results ?? [], [resultsQuery.data])
  const totalResults = resultsQuery.data?.total ?? 0
  const hasMoreResults = allResults.length < totalResults

  // Sort function for results
  const sortResults = (items: ProjectDiscoveryResultItem[]) => {
    const sorted = [...items]
    switch (sortBy) {
      case 'relevance':
        sorted.sort((a, b) => (b.relevance_score ?? 0) - (a.relevance_score ?? 0))
        break
      case 'year_desc':
        sorted.sort((a, b) => (b.published_year ?? 0) - (a.published_year ?? 0))
        break
      case 'year_asc':
        sorted.sort((a, b) => (a.published_year ?? 0) - (b.published_year ?? 0))
        break
      case 'has_pdf':
        sorted.sort((a, b) => {
          const aHasPdf = a.has_pdf || Boolean(a.pdf_url) ? 1 : 0
          const bHasPdf = b.has_pdf || Boolean(b.pdf_url) ? 1 : 0
          return bHasPdf - aHasPdf
        })
        break
    }
    return sorted
  }

  // Filter function for results
  const filterResults = (items: ProjectDiscoveryResultItem[]) => {
    if (!showPdfOnly) return items
    return items.filter((item) => item.has_pdf || Boolean(item.pdf_url))
  }

  const manualResults = useMemo(() => {
    const filtered = allResults.filter((item) => item.run_type === 'manual')
      .filter((item) => {
        if (!manualSessionStart) return true
        const startedAt = new Date(item.run_started_at).getTime()
        return Number.isFinite(startedAt) ? startedAt >= manualSessionStart : true
      })
    return sortResults(filterResults(filtered))
  }, [allResults, sortBy, showPdfOnly, manualSessionStart])

  const deletableManualResults = useMemo(
    () => manualResults.filter((item) => item.status !== 'promoted'),
    [manualResults]
  )

  const autoResultsRaw = useMemo(
    () => allResults.filter((item) => item.run_type === 'auto'),
    [allResults]
  )

  const storedPreferences = useMemo(() => {
    return settingsQuery.data ?? project?.discovery_preferences ?? null
  }, [project?.discovery_preferences, settingsQuery.data])

  const autoRefreshProfile = useMemo(() => {
    if (!storedPreferences) {
      return {
        enabled: false,
        intervalMinutes: DEFAULT_REFRESH_INTERVAL_MINUTES,
        lastRunAt: null as string | null,
      }
    }
    const intervalMinutes = storedPreferences.refresh_interval_hours != null
      ? Math.max(
          MIN_REFRESH_INTERVAL_MINUTES,
          Math.round(Number(storedPreferences.refresh_interval_hours) * 60),
        )
      : DEFAULT_REFRESH_INTERVAL_MINUTES
    return {
      enabled: Boolean(storedPreferences.auto_refresh_enabled),
      intervalMinutes,
      lastRunAt: storedPreferences.last_run_at ?? null,
    }
  }, [storedPreferences])

  const suggestionKeys = useMemo(() => {
    const items = suggestionsQuery.data ?? []
    const keys = new Set<string>()
    items.forEach((suggestion) => {
      const doi = suggestion.reference?.doi?.toLowerCase()
      if (doi) keys.add(`doi:${doi}`)
      const title = suggestion.reference?.title?.toLowerCase()
      if (title) keys.add(`title:${title}`)
    })
    return keys
  }, [suggestionsQuery.data])

  const autoResults = useMemo(
    () => {
      const deduplicated = autoResultsRaw.filter((item) => {
        const doiKey = item.doi ? `doi:${item.doi.toLowerCase()}` : null
        if (doiKey && suggestionKeys.has(doiKey)) return false
        const titleKey = item.title ? `title:${item.title.toLowerCase()}` : null
        if (titleKey && suggestionKeys.has(titleKey)) return false
        return true
      })
      return sortResults(filterResults(deduplicated))
    },
    [autoResultsRaw, suggestionKeys, sortBy, showPdfOnly]
  )

  const hiddenAutoCount = Math.max(0, autoResultsRaw.length - autoResults.length)

  useEffect(() => {
    if (!project?.id || isViewer) return
    if (!autoRefreshProfile.enabled) return

    const intervalMinutes = Math.max(
      MIN_REFRESH_INTERVAL_MINUTES,
      autoRefreshProfile.intervalMinutes,
    )
    const intervalMs = intervalMinutes * 60_000
    const lastRunAt = autoRefreshProfile.lastRunAt
      ? new Date(autoRefreshProfile.lastRunAt).getTime()
      : 0

    let timer: ReturnType<typeof setInterval> | undefined
    let running = false

    const runRefresh = async (reason: 'interval' | 'initial') => {
      if (running) return
      running = true
      try {
        await projectReferencesAPI.refreshSuggestions(project.id)
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryResults'] }),
          queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryPendingCount'] }),
          queryClient.invalidateQueries({ queryKey: ['project', project.id, 'referenceSuggestionsForDiscovery'] }),
          queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoverySettings'] }),
        ])
      } catch (error) {
        console.warn('Auto discovery refresh failed', { reason, error })
      } finally {
        running = false
      }
    }

    const now = Date.now()
    if (!lastRunAt || now - lastRunAt >= intervalMs) {
      void runRefresh('initial')
    }

    timer = setInterval(() => {
      void runRefresh('interval')
    }, intervalMs)

    return () => {
      if (timer) {
        clearInterval(timer)
      }
    }
  }, [autoRefreshProfile, isViewer, project?.id, queryClient])

  const extractErrorMessage = (detail: unknown): string => {
    if (!detail) return 'Unable to save preferences right now.'
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object') {
            const locValue = (item as { loc?: unknown }).loc
            const loc = Array.isArray(locValue) ? locValue.join('.') : locValue
            const msg = (item as { msg?: unknown }).msg
            if (typeof msg === 'string') {
              return loc ? `${loc}: ${msg}` : msg
            }
          }
          return null
        })
        .filter(Boolean) as string[]
      if (messages.length) {
        return messages.join('\n')
      }
    }
    if (typeof detail === 'object') {
      try {
        return JSON.stringify(detail)
      } catch (error) {
        console.warn('Failed to serialize error detail', error)
      }
    }
    return 'Unable to save preferences right now.'
  }

  useEffect(() => {
    if (!project) return
    const rawPrefs: ProjectDiscoveryPreferences | undefined = storedPreferences ?? undefined

    setActiveFormState((prev) => {
      if (activeFormDirtyRef.current && hasHydratedActiveForm.current) {
        return prev
      }

      const queryProvided = rawPrefs?.query !== undefined
      const sourcesProvided = rawPrefs?.sources !== undefined
      const autoRefreshProvided = rawPrefs?.auto_refresh_enabled !== undefined
      const refreshProvided = rawPrefs?.refresh_interval_hours !== undefined
      const maxResultsProvided = rawPrefs?.max_results !== undefined
      const relevanceProvided = rawPrefs?.relevance_threshold !== undefined

      const nextQuery = queryProvided ? rawPrefs?.query ?? '' : prev.query || projectIdea

      const sourceCandidate = sourcesProvided ? rawPrefs?.sources ?? [] : prev.sources
      const nextSources =
        sourceCandidate && sourceCandidate.length ? sourceCandidate : DEFAULT_SOURCES

      const parsedRefreshHours =
        rawPrefs?.refresh_interval_hours != null
          ? Number(rawPrefs.refresh_interval_hours)
          : null

      const nextRefreshMinutes = refreshProvided
        ? parsedRefreshHours != null && Number.isFinite(parsedRefreshHours)
          ? String(Math.max(MIN_REFRESH_INTERVAL_MINUTES, Math.round(parsedRefreshHours * 60)))
          : ''
        : prev.refreshIntervalMinutes || String(DEFAULT_REFRESH_INTERVAL_MINUTES)

      const nextAutoRefresh = autoRefreshProvided
        ? Boolean(rawPrefs?.auto_refresh_enabled)
        : prev.autoRefresh

      const nextMaxResults = maxResultsProvided
        ? rawPrefs?.max_results != null
          ? String(rawPrefs.max_results)
          : ''
        : prev.maxResults || defaultActiveFormState.maxResults

      const nextRelevance = relevanceProvided
        ? rawPrefs?.relevance_threshold != null
          ? String(rawPrefs.relevance_threshold)
          : ''
        : prev.relevanceThreshold

      hasHydratedActiveForm.current = true
      activeFormDirtyRef.current = false

      return {
        query: nextQuery,
        sources: nextSources,
        autoRefresh: nextAutoRefresh,
        refreshIntervalMinutes: nextRefreshMinutes,
        maxResults: nextMaxResults,
        relevanceThreshold: nextRelevance,
      }
    })
  }, [project, projectIdea, projectKeywordPreset, storedPreferences])

  useEffect(() => {
    if (!isDeleteMode) {
      setSelectedResults([])
      return
    }
    setSelectedResults((prev) => prev.filter((id) => deletableManualResults.some((item) => item.id === id)))
  }, [isDeleteMode, deletableManualResults])

  const saveSettings = useMutation({
    onMutate: () => {
      setActiveStatusMessage(null)
      setActiveErrorMessage(null)
    },
    mutationFn: async () => {
      const effectiveKeywords = sanitizeKeywords(projectKeywordPreset || '')
      const keywordsList = effectiveKeywords ? parseList(effectiveKeywords) : []
      const refreshHours = toRefreshIntervalHours(activeFormState.refreshIntervalMinutes)
      const payload: ProjectDiscoverySettingsPayload = {
        query: activeFormState.query.trim() || null,
        keywords: keywordsList.length ? keywordsList : null,
        sources: activeFormState.sources.length ? activeFormState.sources : null,
        auto_refresh_enabled: activeFormState.autoRefresh,
        refresh_interval_hours: activeFormState.autoRefresh ? refreshHours : null,
        max_results: activeFormState.maxResults ? Number(activeFormState.maxResults) : null,
        relevance_threshold: activeFormState.relevanceThreshold
          ? Number(activeFormState.relevanceThreshold)
          : null,
      }
      const response = await projectDiscoveryAPI.updateSettings(project.id, payload)
      return response.data
    },
    onSuccess: () => {
      activeFormDirtyRef.current = false
      setActiveStatusMessage('Discovery preferences saved.')
      setActiveErrorMessage(null)
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoverySettings'] })
    },
    onError: (error: unknown) => {
      setActiveStatusMessage(null)
        const axiosError = error as { response?: { status?: number; data?: { detail?: unknown } } }
      const message = extractErrorMessage(axiosError?.response?.data?.detail)
      setActiveErrorMessage(message)
    },
  })

  const promoteResult = useMutation({
    mutationFn: async (resultId: string) => {
      // Block promotion while results are being cleared (prevents race condition)
      if (isClearingResults) {
        throw new Error('Please wait for page to finish loading')
      }
      setPromotingIds((prev) => new Set(prev).add(resultId))
      const response = await projectDiscoveryAPI.promoteResult(project.id, resultId)
      return { data: response.data, resultId }
    },
    onSuccess: (_data, resultId) => {
      setPromotingIds((prev) => {
        const next = new Set(prev)
        next.delete(resultId)
        return next
      })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryResults'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryPendingCount'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'referenceSuggestions'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoverySettings'] })
    },
    onError: (error, resultId) => {
      setPromotingIds((prev) => {
        const next = new Set(prev)
        next.delete(resultId)
        return next
      })
      // Show error to user
      const axiosError = error as { response?: { status?: number; data?: { detail?: string } } }
      const status = axiosError?.response?.status
      if (status === 404) {
        setActiveErrorMessage('Paper no longer available. Please refresh and try again.')
      } else {
        const message = axiosError?.response?.data?.detail || 'Failed to add paper to library'
        setActiveErrorMessage(message)
      }
    },
    retry: false, // Don't retry on error - avoids hammering server
  })

  const dismissResult = useMutation({
    mutationFn: async (resultId: string) => {
      setDismissingIds((prev) => new Set(prev).add(resultId))
      const response = await projectDiscoveryAPI.dismissResult(project.id, resultId)
      return { data: response.data, resultId }
    },
    onSuccess: (_data, resultId) => {
      setDismissingIds((prev) => {
        const next = new Set(prev)
        next.delete(resultId)
        return next
      })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryResults'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryPendingCount'] })
    },
    onError: (_error, resultId) => {
      setDismissingIds((prev) => {
        const next = new Set(prev)
        next.delete(resultId)
        return next
      })
    },
  })

  const bulkDeleteResults = useMutation({
    mutationFn: async (resultIds: string[]) => {
      await Promise.all(resultIds.map((id) => projectDiscoveryAPI.deleteResult(project.id, id)))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryResults'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryPendingCount'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'referenceSuggestions'] })
      setSelectedResults([])
      setIsDeleteMode(false)
    },
  })

  const bulkPromoteResults = useMutation({
    mutationFn: async (resultIds: string[]) => {
      // Process sequentially to avoid race conditions
      for (const id of resultIds) {
        await projectDiscoveryAPI.promoteResult(project.id, id)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryResults'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryPendingCount'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'referenceSuggestions'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoverySettings'] })
    },
  })

  const bulkDismissResults = useMutation({
    mutationFn: async (resultIds: string[]) => {
      // Process sequentially to avoid race conditions
      for (const id of resultIds) {
        await projectDiscoveryAPI.dismissResult(project.id, id)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryResults'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryPendingCount'] })
    },
  })

  const isDeleting = bulkDeleteResults.isPending
  const isBulkPromoting = bulkPromoteResults.isPending
  const isBulkDismissing = bulkDismissResults.isPending

  // Pending items for batch actions
  const pendingManualResults = useMemo(
    () => manualResults.filter((item) => item.status === 'pending'),
    [manualResults]
  )

  const pendingAutoResults = useMemo(
    () => autoResults.filter((item) => item.status === 'pending'),
    [autoResults]
  )

  const runDiscovery = useMutation({
    onMutate: () => {
      setManualStatusMessage(null)
      setManualErrorMessage(null)
      setLastSourceStats(null)
    },
    mutationFn: async () => {
      const effectiveKeywords = sanitizeKeywords(projectKeywordPreset || '')
      const keywordsList = effectiveKeywords ? parseList(effectiveKeywords) : []
      const payload: ProjectDiscoverySettingsPayload = {
        query: manualFormState.query.trim() || null,
        keywords: keywordsList.length ? keywordsList : null,
        sources: manualFormState.sources.length ? manualFormState.sources : null,
        max_results: manualFormState.maxResults ? Number(manualFormState.maxResults) : null,
        relevance_threshold: manualFormState.relevanceThreshold
          ? Number(manualFormState.relevanceThreshold)
          : null,
      }

      const response = await projectDiscoveryAPI.runDiscovery(project.id, payload)
      return response.data
    },
    onSuccess: (data) => {
      setManualErrorMessage(null)
      setDiscoveryCooldown(30) // 30 second cooldown after discovery

      // Update last run timestamp immediately from response
      if (data?.last_run_at) {
        setLastRunAtOverride(data.last_run_at)
      }

      // Capture source stats from response
      if (data?.source_stats) {
        setLastSourceStats(data.source_stats)
      }

      const totalFound = data?.total_found ?? 0
      const resultsCreated = data?.results_created ?? 0

      // Build status message based on source stats
      const sourceStats = data?.source_stats
      const failedSources = sourceStats?.filter((s) => s.status === 'error' || s.status === 'timeout' || s.status === 'rate_limited') ?? []
      const successfulSources = sourceStats?.filter((s) => s.status === 'success') ?? []

      if (failedSources.length > 0 && successfulSources.length === 0) {
        // All sources failed
        const failedNames = failedSources.map((s) => getSourceLabel(s.source)).join(', ')
        setManualStatusMessage(`All sources failed: ${failedNames}. Please try again.`)
      } else if (failedSources.length > 0) {
        // Some sources failed
        const failedDetails = failedSources.map((s) => {
          const label = getSourceLabel(s.source)
          if (s.status === 'timeout') return `${label} (timed out)`
          if (s.status === 'rate_limited') return `${label} (rate limited)`
          return `${label} (${s.error || 'error'})`
        }).join(', ')
        if (totalFound === 0) {
          setManualStatusMessage(`Some sources failed: ${failedDetails}. No results from remaining sources.`)
        } else if (resultsCreated === 0) {
          setManualStatusMessage(`Some sources failed: ${failedDetails}. All found results already match your project.`)
        } else {
          setManualStatusMessage(`Note: ${failedDetails}. Found ${resultsCreated} new result${resultsCreated === 1 ? '' : 's'} from other sources.`)
        }
      } else if (totalFound === 0) {
        setManualStatusMessage('No results found from the selected sources. Try different keywords or sources.')
      } else if (resultsCreated === 0) {
        setManualStatusMessage('No new discovery results — everything found already matches your project references.')
      } else {
        setManualStatusMessage(null)
      }
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryResults'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryPendingCount'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'referenceSuggestions'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoverySettings'] })
    },
    onError: (error: unknown) => {
      setLastSourceStats(null)
      const axiosError = error as { response?: { status?: number; data?: { detail?: unknown } } }
      const message = extractErrorMessage(axiosError?.response?.data?.detail)
      setManualErrorMessage(message)
    },
  })

  const clearDismissedResults = useMutation({
    mutationFn: async () => {
      const response = await projectDiscoveryAPI.clearDismissedResults(project.id)
      return response.data
    },
    onSuccess: () => {
      setManualStatusMessage('Dismissed discovery results cleared.')
      setManualErrorMessage(null)
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryResults'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryPendingCount'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'referenceSuggestions'] })
    },
    onError: () => {
      setManualStatusMessage(null)
      setManualErrorMessage('Unable to clear dismissed results right now.')
    },
  })

  const toggleDeleteMode = () => {
    setIsDeleteMode((prev) => {
      if (prev) {
        setSelectedResults([])
      }
      return !prev
    })
  }

  const toggleResultSelection = (resultId: string) => {
    setSelectedResults((prev) =>
      prev.includes(resultId)
        ? prev.filter((id) => id !== resultId)
        : [...prev, resultId]
    )
  }

  const handleSelectAll = () => {
    if (!deletableManualResults.length) {
      setSelectedResults([])
      return
    }
    if (selectedResults.length === deletableManualResults.length) {
      setSelectedResults([])
    } else {
      setSelectedResults(deletableManualResults.map((item) => item.id))
    }
  }

  const handleBulkDelete = () => {
    if (!selectedResults.length || isDeleting) return
    bulkDeleteResults.mutate(selectedResults)
  }

  const fallbackPrefs = project.discovery_preferences
  const pendingCount = settingsQuery.data?.last_result_count ?? fallbackPrefs?.last_result_count ?? 0
  const lastRunAt = lastRunAtOverride ?? settingsQuery.data?.last_run_at ?? fallbackPrefs?.last_run_at

  const toggleSourceValue = (current: string[], value: string) => {
    if (current.includes(value)) {
      const remaining = current.filter((item) => item !== value)
      return remaining.length ? remaining : current
    }
    return [...current, value]
  }

  const handleManualSourceToggle = (value: string) => {
    updateManualForm((prev) => ({
      ...prev,
      sources: toggleSourceValue(prev.sources, value),
    }))
  }

  const handleActiveSourceToggle = (value: string) => {
    updateActiveForm((prev) => ({
      ...prev,
      sources: toggleSourceValue(prev.sources, value),
    }))
  }

  const resetActiveForm = () => {
    activeFormDirtyRef.current = false
    hasHydratedActiveForm.current = false
    setActiveFormState(defaultActiveFormState)
    setActiveStatusMessage(null)
    setActiveErrorMessage(null)
  }

  const renderManualContent = () => (
    <div className="space-y-6">
      <section className="rounded-2xl border border-indigo-100 bg-white shadow-sm transition-colors dark:border-indigo-500/30 dark:bg-slate-900/40">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-indigo-50 px-5 py-4 dark:border-indigo-500/20">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-100 dark:bg-indigo-500/20">
            <Sparkles className="h-4.5 w-4.5 text-indigo-600 dark:text-indigo-300" />
          </div>
          <div className="flex-1">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-slate-100">Discover Papers</h2>
            <p className="text-xs text-gray-500 dark:text-slate-400">
              Find relevant papers from academic databases
            </p>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-gray-400 dark:text-slate-500">
            <Clock className="h-3.5 w-3.5" />
            <span>{lastRunAt ? formatDateTime(lastRunAt) : 'Never run'}</span>
          </div>
        </div>

        {/* Main content */}
        <div className="space-y-4 p-5">
          {manualErrorMessage && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-400/40 dark:bg-rose-500/10 dark:text-rose-200">
              {manualErrorMessage}
            </div>
          )}
          {manualStatusMessage && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:border-emerald-400/40 dark:bg-emerald-500/15 dark:text-emerald-200">
              {manualStatusMessage}
            </div>
          )}

          {/* Search query - full width, prominent */}
          <div>
            <label className="text-xs font-medium text-gray-700 dark:text-slate-300">
              Search query
            </label>
            <div className="relative mt-1.5">
              <input
                type="text"
                value={manualFormState.query}
                onChange={(event) =>
                  updateManualForm((prev) => ({ ...prev, query: event.target.value }))
                }
                placeholder="e.g. transformer architectures for NLP, diffusion models..."
                className="w-full rounded-lg border border-gray-200 bg-gray-50/50 px-4 py-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-800/50 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:bg-slate-800"
              />
            </div>
            {projectKeywordPreset && (
              <p className="mt-1.5 text-xs text-gray-500 dark:text-slate-400">
                Project keywords: <span className="text-indigo-600 dark:text-indigo-400">{projectKeywordPreset}</span>
              </p>
            )}
          </div>

          {/* Source presets */}
          <div>
            <label className="text-xs font-medium text-gray-700 dark:text-slate-300">Quick presets</label>
            <div className="mt-2 flex flex-wrap gap-2">
              {Object.entries(SOURCE_PRESETS).map(([key, preset]) => {
                const isActive = preset.sources.length === manualFormState.sources.length &&
                  preset.sources.every((s) => manualFormState.sources.includes(s))
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => updateManualForm((prev) => ({ ...prev, sources: [...preset.sources] }))}
                    className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-all ${
                      isActive
                        ? 'bg-indigo-600 text-white shadow-sm'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                    }`}
                    title={preset.description}
                  >
                    {key === 'fast' && <Zap className="h-3 w-3" />}
                    {preset.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Compact source chips */}
          <div>
            <label className="text-xs font-medium text-gray-700 dark:text-slate-300">
              Sources ({manualFormState.sources.length} selected)
            </label>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {AVAILABLE_SOURCES.map((source) => {
                const checked = manualFormState.sources.includes(source.value)
                return (
                  <button
                    key={source.value}
                    type="button"
                    onClick={() => handleManualSourceToggle(source.value)}
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs transition-all ${
                      checked
                        ? 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-200 dark:bg-indigo-500/20 dark:text-indigo-200 dark:ring-indigo-500/40'
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
                    }`}
                  >
                    {checked && <Check className="h-3 w-3" />}
                    {source.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Collapsible advanced options */}
          <div className="rounded-lg border border-gray-100 dark:border-slate-700/50">
            <button
              type="button"
              onClick={() => setShowAdvancedOptions(!showAdvancedOptions)}
              className="flex w-full items-center justify-between px-3 py-2.5 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:text-slate-400 dark:hover:bg-slate-800/50"
            >
              <span className="flex items-center gap-2">
                <Settings2 className="h-3.5 w-3.5" />
                Advanced options
              </span>
              {showAdvancedOptions ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </button>
            {showAdvancedOptions && (
              <div className="grid gap-4 border-t border-gray-100 px-3 py-3 dark:border-slate-700/50 sm:grid-cols-2">
                <label className="text-xs font-medium text-gray-600 dark:text-slate-400">
                  Max results
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={manualFormState.maxResults}
                    onChange={(event) =>
                      updateManualForm((prev) => ({ ...prev, maxResults: event.target.value }))
                    }
                    placeholder="20"
                    className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                  />
                </label>
                <label className="text-xs font-medium text-gray-600 dark:text-slate-400">
                  Relevance threshold (0-1)
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={manualFormState.relevanceThreshold}
                    onChange={(event) =>
                      updateManualForm((prev) => ({
                        ...prev,
                        relevanceThreshold: event.target.value,
                      }))
                    }
                    placeholder="0.5"
                    className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                  />
                </label>
              </div>
            )}
          </div>
        </div>

        {/* Footer with action button */}
        <div className="flex items-center justify-between border-t border-indigo-50 bg-gray-50/50 px-5 py-3 dark:border-indigo-500/20 dark:bg-slate-900/50">
          <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-slate-400">
            <span>{pendingCount} pending results</span>
          </div>
          <button
            type="button"
            onClick={() => runDiscovery.mutate()}
            disabled={runDiscovery.isPending || discoveryCooldown > 0 || !manualFormState.query.trim()}
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {runDiscovery.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            {runDiscovery.isPending
              ? 'Searching...'
              : discoveryCooldown > 0
                ? `Wait ${discoveryCooldown}s`
                : 'Run Discovery'}
          </button>
        </div>
      </section>

      {/* Progress indicator during discovery */}
      {runDiscovery.isPending && (
        <div className="rounded-2xl border border-indigo-200 bg-indigo-50 p-4 dark:border-indigo-500/30 dark:bg-indigo-950/30">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900/50">
              <Loader2 className="h-5 w-5 animate-spin text-indigo-600 dark:text-indigo-300" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-indigo-900 dark:text-indigo-100">
                Discovering papers...
              </p>
              <p className="text-xs text-indigo-700 dark:text-indigo-300">
                Searching {manualFormState.sources.length} source{manualFormState.sources.length !== 1 ? 's' : ''} for relevant papers. This may take up to 30 seconds.
              </p>
            </div>
          </div>
          {/* Source list during search */}
          <div className="mt-3 grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
            {manualFormState.sources.map((source) => (
              <div
                key={source}
                className="flex items-center gap-2 rounded-lg bg-white/60 px-2.5 py-1.5 text-xs dark:bg-slate-900/40"
              >
                <Loader2 className="h-3 w-3 animate-spin text-indigo-500 dark:text-indigo-400" />
                <span className="text-indigo-700 dark:text-indigo-300">{getSourceLabel(source)}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-indigo-200 dark:bg-indigo-900/50">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-indigo-500 dark:bg-indigo-400" style={{ animation: 'progress 2s ease-in-out infinite' }} />
          </div>
        </div>
      )}

      {/* Source stats after discovery */}
      {!runDiscovery.isPending && lastSourceStats && lastSourceStats.length > 0 && (
        <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900/50">
          <div className="flex items-center justify-between gap-2 mb-3">
            <h3 className="text-sm font-medium text-gray-700 dark:text-slate-200">
              Search results by source
            </h3>
            <button
              type="button"
              onClick={() => setLastSourceStats(null)}
              className="text-gray-400 hover:text-gray-600 dark:text-slate-500 dark:hover:text-slate-300"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {[...lastSourceStats]
              .sort((a, b) => {
                // Sort by: success with high count first, then success with low count, then failed/skipped at bottom
                const aFailed = a.status === 'error' || a.status === 'timeout' || a.status === 'rate_limited' || a.status === 'cancelled'
                const bFailed = b.status === 'error' || b.status === 'timeout' || b.status === 'rate_limited' || b.status === 'cancelled'
                if (aFailed && !bFailed) return 1  // a goes to bottom
                if (!aFailed && bFailed) return -1 // b goes to bottom
                // Both same status category, sort by count descending
                return b.count - a.count
              })
              .map((stat) => {
              const isSuccess = stat.status === 'success'
              const isTimeout = stat.status === 'timeout'
              const isError = stat.status === 'error'
              const isRateLimited = stat.status === 'rate_limited'
              const isCancelled = stat.status === 'cancelled'
              const isFailed = isTimeout || isError || isRateLimited

              return (
                <div
                  key={stat.source}
                  className={`flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-xs ${
                    isSuccess
                      ? 'bg-emerald-50 dark:bg-emerald-900/20'
                      : isRateLimited
                        ? 'bg-amber-50 dark:bg-amber-900/20'
                        : isFailed
                          ? 'bg-rose-50 dark:bg-rose-900/20'
                          : isCancelled
                            ? 'bg-slate-50 dark:bg-slate-800/50'
                            : 'bg-gray-50 dark:bg-slate-800/50'
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    {isSuccess && <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0 text-emerald-600 dark:text-emerald-400" />}
                    {isTimeout && <AlertCircle className="h-3.5 w-3.5 flex-shrink-0 text-amber-600 dark:text-amber-400" />}
                    {isRateLimited && <AlertCircle className="h-3.5 w-3.5 flex-shrink-0 text-amber-600 dark:text-amber-400" />}
                    {isError && <XCircle className="h-3.5 w-3.5 flex-shrink-0 text-rose-600 dark:text-rose-400" />}
                    {isCancelled && <MinusCircle className="h-3.5 w-3.5 flex-shrink-0 text-slate-400 dark:text-slate-500" />}
                    <span className={`truncate ${
                      isSuccess
                        ? 'text-emerald-700 dark:text-emerald-300'
                        : isRateLimited
                          ? 'text-amber-700 dark:text-amber-300'
                          : isFailed
                            ? 'text-rose-700 dark:text-rose-300'
                            : isCancelled
                              ? 'text-slate-500 dark:text-slate-400'
                              : 'text-gray-600 dark:text-slate-400'
                    }`}>
                      {getSourceLabel(stat.source)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {isSuccess && (
                      <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-emerald-700 dark:bg-emerald-800/40 dark:text-emerald-300">
                        {stat.count} found
                      </span>
                    )}
                    {isTimeout && (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-700 dark:bg-amber-800/40 dark:text-amber-300">
                        Timeout
                      </span>
                    )}
                    {isRateLimited && (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-700 dark:bg-amber-800/40 dark:text-amber-300" title="API rate limit exceeded - try again later">
                        Rate limited
                      </span>
                    )}
                    {isError && (
                      <span className="rounded-full bg-rose-100 px-2 py-0.5 text-rose-700 dark:bg-rose-800/40 dark:text-rose-300" title={stat.error || 'Error'}>
                        Failed
                      </span>
                    )}
                    {isCancelled && (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600 dark:bg-slate-700/50 dark:text-slate-400" title="Search was skipped (enough results found from other sources)">
                        Skipped
                      </span>
                    )}
                    {isFailed && (
                      <button
                        type="button"
                        onClick={() => {
                          // Retry with only this source
                          updateManualForm((prev) => ({ ...prev, sources: [stat.source] }))
                          setTimeout(() => runDiscovery.mutate(), 100)
                        }}
                        disabled={discoveryCooldown > 0}
                        className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-gray-600 hover:bg-gray-100 disabled:opacity-50 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600"
                        title="Retry this source"
                      >
                        <RefreshCw className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
          {/* Retry all failed sources button */}
          {lastSourceStats.some((s) => s.status === 'error' || s.status === 'timeout' || s.status === 'rate_limited') && (
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={() => {
                  const failedSources = lastSourceStats
                    .filter((s) => s.status === 'error' || s.status === 'timeout' || s.status === 'rate_limited')
                    .map((s) => s.source)
                  updateManualForm((prev) => ({ ...prev, sources: failedSources }))
                  setTimeout(() => runDiscovery.mutate(), 100)
                }}
                disabled={discoveryCooldown > 0 || runDiscovery.isPending}
                className="inline-flex items-center gap-2 rounded-full border border-rose-200 px-3 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-rose-400/40 dark:text-rose-300 dark:hover:bg-rose-500/10"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Retry failed sources
              </button>
            </div>
          )}
        </div>
      )}

      <section className="space-y-4 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900/50">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-slate-100">
            <Sparkles className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
            Manual results
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-gray-600 dark:text-slate-300">
            <div className="inline-flex items-center gap-1 rounded-full border border-gray-200 px-2 py-1 dark:border-slate-600 dark:bg-slate-800/60">
              <Filter className="h-3.5 w-3.5" /> Status
            </div>
            {STATUS_FILTERS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => handleStatusFilterChange(option.value)}
                className={`inline-flex items-center rounded-full px-3 py-1.5 ${
                  statusFilter === option.value
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-slate-800/60 dark:text-slate-300 dark:hover:bg-slate-700'
                }`}
              >
                {option.label}
              </button>
            ))}
            <span className="mx-1 text-gray-300 dark:text-slate-600">|</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 focus:border-indigo-500 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setShowPdfOnly(!showPdfOnly)}
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 ${
                showPdfOnly
                  ? 'bg-emerald-600 text-white'
                  : 'border border-gray-200 text-gray-600 hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700'
              }`}
            >
              <FileText className="h-3.5 w-3.5" />
              PDF only
            </button>
            <button
              type="button"
              onClick={() => resultsQuery.refetch()}
              className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              <RotateCcw className="h-3.5 w-3.5" /> Refresh
            </button>
            {statusFilter === 'dismissed' && (
              <button
                type="button"
                onClick={() => clearDismissedResults.mutate()}
                disabled={clearDismissedResults.isPending}
                className="inline-flex items-center gap-2 rounded-full border border-rose-200 px-3 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-rose-400/40 dark:text-rose-200 dark:hover:bg-rose-500/10"
              >
                {clearDismissedResults.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Trash2 className="h-3.5 w-3.5" />
                )}
                Clear dismissed
              </button>
            )}
          </div>
        </div>

        {/* Batch actions for pending results */}
        {pendingManualResults.length > 0 && statusFilter === 'pending' && !isDeleteMode && (
          <div className="flex items-center gap-2 rounded-lg border border-indigo-100 bg-indigo-50/50 px-3 py-2 dark:border-indigo-500/30 dark:bg-indigo-950/30">
            <span className="text-xs text-indigo-700 dark:text-indigo-200">
              {pendingManualResults.length} pending paper{pendingManualResults.length !== 1 ? 's' : ''}
            </span>
            <div className="flex-1" />
            <button
              type="button"
              onClick={() => bulkPromoteResults.mutate(pendingManualResults.map((r) => r.id))}
              disabled={isBulkPromoting || isBulkDismissing}
              className="inline-flex items-center gap-1.5 rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isBulkPromoting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Check className="h-3.5 w-3.5" />
              )}
              Add All
            </button>
            <button
              type="button"
              onClick={() => bulkDismissResults.mutate(pendingManualResults.map((r) => r.id))}
              disabled={isBulkPromoting || isBulkDismissing}
              className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-500 hover:bg-gray-50 hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
            >
              {isBulkDismissing ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <X className="h-3.5 w-3.5" />
              )}
              Dismiss All
            </button>
          </div>
        )}

        <div className="space-y-3">
          {resultsQuery.isLoading && (
            <div className="space-y-2">
              <div className="h-16 w-full animate-pulse rounded-xl bg-gray-100 dark:bg-slate-800/60" />
              <div className="h-16 w-full animate-pulse rounded-xl bg-gray-100 dark:bg-slate-800/60" />
            </div>
          )}

          {!resultsQuery.isLoading && manualResults.length === 0 && (
            <div className="rounded-xl border border-dashed border-gray-200 px-4 py-12 text-center text-xs text-gray-500 dark:border-slate-700 dark:text-slate-400">
              No manual runs recorded for this project yet.
            </div>
          )}

          {!resultsQuery.isLoading && manualResults.length > 0 && (
            <div className="space-y-3">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <span className="text-xs text-gray-500 dark:text-slate-400">
                  {isDeleteMode
                    ? `${selectedResults.length} selected`
                    : `${manualResults.length} result${manualResults.length === 1 ? '' : 's'}`}
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={toggleDeleteMode}
                    disabled={!deletableManualResults.length || isDeleting}
                    className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium ${
                      isDeleteMode
                        ? 'border border-gray-300 text-gray-600 hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700'
                        : 'border border-rose-200 text-rose-600 hover:bg-rose-50 dark:border-rose-400/40 dark:text-rose-200 dark:hover:bg-rose-500/10'
                    } disabled:cursor-not-allowed disabled:opacity-60`}
                  >
                    {isDeleteMode ? <X className="h-3.5 w-3.5" /> : <Trash2 className="h-3.5 w-3.5" />}
                    {isDeleteMode ? 'Cancel selection' : 'Delete results'}
                  </button>
                  {isDeleteMode && (
                    <>
                      <button
                        type="button"
                        onClick={handleSelectAll}
                        className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                      >
                        {selectedResults.length === deletableManualResults.length
                          ? 'Clear selection'
                          : 'Select all'}
                      </button>
                      <button
                        type="button"
                        onClick={handleBulkDelete}
                        disabled={!selectedResults.length || isDeleting}
                        className="inline-flex items-center gap-2 rounded-full border border-rose-200 px-3 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-rose-400/40 dark:text-rose-200 dark:hover:bg-rose-500/10"
                      >
                        {isDeleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                        Delete selected
                      </button>
                    </>
                  )}
                </div>
              </div>

              {manualResults.map((item: ProjectDiscoveryResultItem) => (
                <DiscoveryResultCard
                  key={item.id}
                  item={item}
                  onPromote={(id) => promoteResult.mutate(id)}
                  onDismiss={(id) => dismissResult.mutate(id)}
                  isPromoting={promotingIds.has(item.id)}
                  isDismissing={dismissingIds.has(item.id)}
                  isDeleteMode={isDeleteMode}
                  isSelected={selectedResults.includes(item.id)}
                  onToggleSelect={toggleResultSelection}
                  isDisabled={isClearingResults}
                />
              ))}

              {hasMoreResults && (
                <div className="flex justify-center pt-4">
                  <button
                    type="button"
                    onClick={() => setResultsLimit((prev) => prev + 20)}
                    disabled={resultsQuery.isFetching}
                    className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    {resultsQuery.isFetching ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <RotateCcw className="h-4 w-4" />
                    )}
                    Load more ({totalResults - allResults.length} remaining)
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  )

  const renderActiveContent = () => {
    const refreshSummary = activeFormState.autoRefresh
      ? formatRefreshIntervalSummary(activeFormState.refreshIntervalMinutes)
      : 'Auto-refresh off'
    const isActiveDirty = activeFormDirtyRef.current

    return (
      <div className="space-y-6">
        <section className="rounded-2xl border border-indigo-100 bg-white shadow-sm transition-colors dark:border-indigo-500/30 dark:bg-slate-900/40">
          {/* Header */}
          <div className="flex items-center gap-3 border-b border-indigo-50 px-5 py-4 dark:border-indigo-500/20">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-100 dark:bg-indigo-500/20">
              <Clock className="h-4.5 w-4.5 text-indigo-600 dark:text-indigo-300" />
            </div>
            <div className="flex-1">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-slate-100">Auto-Discovery Settings</h2>
              <p className="text-xs text-gray-500 dark:text-slate-400">
                Configure background paper discovery
              </p>
            </div>
            <div className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
              activeFormState.autoRefresh
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300'
                : 'bg-gray-100 text-gray-500 dark:bg-slate-800 dark:text-slate-400'
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full ${activeFormState.autoRefresh ? 'bg-emerald-500 animate-pulse' : 'bg-gray-400'}`} />
              {activeFormState.autoRefresh ? refreshSummary : 'Off'}
            </div>
          </div>

          {/* Main content */}
          <div className="space-y-4 p-5">
            {activeErrorMessage && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-400/40 dark:bg-rose-500/10 dark:text-rose-200">
                {activeErrorMessage}
              </div>
            )}
            {activeStatusMessage && (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:border-emerald-400/40 dark:bg-emerald-500/15 dark:text-emerald-200">
                {activeStatusMessage}
              </div>
            )}

            {/* Auto-refresh toggle - prominent */}
            <div className={`flex items-center justify-between rounded-lg border p-4 transition-colors ${
              activeFormState.autoRefresh
                ? 'border-emerald-200 bg-emerald-50/50 dark:border-emerald-500/30 dark:bg-emerald-950/20'
                : 'border-gray-200 bg-gray-50/50 dark:border-slate-700 dark:bg-slate-800/30'
            }`}>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => updateActiveForm((prev) => ({ ...prev, autoRefresh: !prev.autoRefresh }))}
                  className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 ${
                    activeFormState.autoRefresh ? 'bg-emerald-500' : 'bg-gray-300 dark:bg-slate-600'
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                      activeFormState.autoRefresh ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-slate-100">
                    Auto-refresh
                  </p>
                  <p className="text-xs text-gray-500 dark:text-slate-400">
                    Automatically discover new papers on a schedule
                  </p>
                </div>
              </div>
              {activeFormState.autoRefresh && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 dark:text-slate-400">Every</span>
                  <input
                    type="number"
                    min={MIN_REFRESH_INTERVAL_MINUTES}
                    step={5}
                    value={activeFormState.refreshIntervalMinutes}
                    onChange={(event) =>
                      updateActiveForm((prev) => ({
                        ...prev,
                        refreshIntervalMinutes: event.target.value,
                      }))
                    }
                    onBlur={(event) => {
                      const rawValue = event.target.value
                      if (rawValue === '') return
                      const minutes = Number(rawValue)
                      if (Number.isFinite(minutes) && minutes < MIN_REFRESH_INTERVAL_MINUTES) {
                        updateActiveForm((prev) => ({
                          ...prev,
                          refreshIntervalMinutes: String(MIN_REFRESH_INTERVAL_MINUTES),
                        }))
                      }
                    }}
                    className="w-20 rounded-md border border-gray-200 px-2 py-1 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                  />
                  <span className="text-xs text-gray-500 dark:text-slate-400">minutes</span>
                </div>
              )}
            </div>

            {/* Search query - full width */}
            <div>
              <label className="text-xs font-medium text-gray-700 dark:text-slate-300">
                Search query
              </label>
              <div className="relative mt-1.5">
                <input
                  type="text"
                  value={activeFormState.query}
                  onChange={(event) =>
                    updateActiveForm((prev) => ({ ...prev, query: event.target.value }))
                  }
                  placeholder="e.g. machine learning healthcare, transformer NLP..."
                  className="w-full rounded-lg border border-gray-200 bg-gray-50/50 px-4 py-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-800/50 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:bg-slate-800"
                />
              </div>
              {projectKeywordPreset && (
                <p className="mt-1.5 text-xs text-gray-500 dark:text-slate-400">
                  Project keywords: <span className="text-indigo-600 dark:text-indigo-400">{projectKeywordPreset}</span>
                </p>
              )}
            </div>

            {/* Source presets */}
            <div>
              <label className="text-xs font-medium text-gray-700 dark:text-slate-300">Quick presets</label>
              <div className="mt-2 flex flex-wrap gap-2">
                {Object.entries(SOURCE_PRESETS).map(([key, preset]) => {
                  const isActive = preset.sources.length === activeFormState.sources.length &&
                    preset.sources.every((s) => activeFormState.sources.includes(s))
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => updateActiveForm((prev) => ({ ...prev, sources: [...preset.sources] }))}
                      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-all ${
                        isActive
                          ? 'bg-indigo-600 text-white shadow-sm'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                      }`}
                      title={preset.description}
                    >
                      {key === 'fast' && <Zap className="h-3 w-3" />}
                      {preset.label}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Compact source chips */}
            <div>
              <label className="text-xs font-medium text-gray-700 dark:text-slate-300">
                Sources ({activeFormState.sources.length} selected)
              </label>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {AVAILABLE_SOURCES.map((source) => {
                  const checked = activeFormState.sources.includes(source.value)
                  return (
                    <button
                      key={source.value}
                      type="button"
                      onClick={() => handleActiveSourceToggle(source.value)}
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs transition-all ${
                        checked
                          ? 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-200 dark:bg-indigo-500/20 dark:text-indigo-200 dark:ring-indigo-500/40'
                          : 'bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
                      }`}
                    >
                      {checked && <Check className="h-3 w-3" />}
                      {source.label}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Collapsible advanced options */}
            <div className="rounded-lg border border-gray-100 dark:border-slate-700/50">
              <button
                type="button"
                onClick={() => setShowAdvancedOptions(!showAdvancedOptions)}
                className="flex w-full items-center justify-between px-3 py-2.5 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:text-slate-400 dark:hover:bg-slate-800/50"
              >
                <span className="flex items-center gap-2">
                  <Settings2 className="h-3.5 w-3.5" />
                  Advanced options
                </span>
                {showAdvancedOptions ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </button>
              {showAdvancedOptions && (
                <div className="grid gap-4 border-t border-gray-100 px-3 py-3 dark:border-slate-700/50 sm:grid-cols-2">
                  <label className="text-xs font-medium text-gray-600 dark:text-slate-400">
                    Max results per run
                    <input
                      type="number"
                      min={1}
                      max={100}
                      value={activeFormState.maxResults}
                      onChange={(event) =>
                        updateActiveForm((prev) => ({ ...prev, maxResults: event.target.value }))
                      }
                      placeholder="20"
                      className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                    />
                  </label>
                  <label className="text-xs font-medium text-gray-600 dark:text-slate-400">
                    Relevance threshold (0-1)
                    <input
                      type="number"
                      min={0}
                      max={1}
                      step={0.05}
                      value={activeFormState.relevanceThreshold}
                      onChange={(event) =>
                        updateActiveForm((prev) => ({
                          ...prev,
                          relevanceThreshold: event.target.value,
                        }))
                      }
                      placeholder="0.5"
                      className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                    />
                  </label>
                </div>
              )}
            </div>
          </div>

          {/* Footer with action buttons */}
          <div className="flex items-center justify-between border-t border-indigo-50 bg-gray-50/50 px-5 py-3 dark:border-indigo-500/20 dark:bg-slate-900/50">
            <div className="flex items-center gap-2">
              {isActiveDirty && !saveSettings.isPending && (
                <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                  Unsaved changes
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={resetActiveForm}
                disabled={saveSettings.isPending}
                className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Reset
              </button>
              <button
                type="button"
                onClick={() => saveSettings.mutate()}
                disabled={saveSettings.isPending || !isActiveDirty}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saveSettings.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Check className="h-3.5 w-3.5" />
                )}
                Save Settings
              </button>
            </div>
          </div>
        </section>

        <section className="space-y-4 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900/50">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-slate-100">
              <Clock className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
              Active search feed
            </div>
            <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600 dark:text-slate-300">
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-1 dark:bg-slate-800/60 dark:text-slate-300">
                {refreshSummary}
              </span>
              <div className="flex items-center gap-2">
                {STATUS_FILTERS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => handleStatusFilterChange(option.value)}
                    className={`inline-flex items-center rounded-full px-3 py-1.5 ${
                      statusFilter === option.value
                        ? 'bg-indigo-600 text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-slate-800/60 dark:text-slate-300 dark:hover:bg-slate-700'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortOption)}
                className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 focus:border-indigo-500 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300"
              >
                {SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setShowPdfOnly(!showPdfOnly)}
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 ${
                  showPdfOnly
                    ? 'bg-emerald-600 text-white'
                    : 'border border-gray-200 text-gray-600 hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700'
                }`}
              >
                <FileText className="h-3.5 w-3.5" />
                PDF only
              </button>
              <button
                type="button"
                onClick={() => resultsQuery.refetch()}
                className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1.5 font-medium text-gray-600 hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                <RotateCcw className="h-3.5 w-3.5" /> Refresh
              </button>
              {statusFilter === 'dismissed' && (
                <button
                  type="button"
                  onClick={() => clearDismissedResults.mutate()}
                  disabled={clearDismissedResults.isPending}
                  className="inline-flex items-center gap-2 rounded-full border border-rose-200 px-3 py-1.5 font-medium text-rose-600 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-rose-400/40 dark:text-rose-200 dark:hover:bg-rose-500/10"
                >
                  {clearDismissedResults.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5" />
                  )}
                  Clear dismissed
                </button>
              )}
            </div>
          </div>

          {!activeFormState.autoRefresh && (
            <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs text-indigo-700 dark:border-indigo-400/40 dark:bg-indigo-500/15 dark:text-indigo-200">
              Turn on <span className="font-medium">Enable background auto-refresh</span> above to let ScholarHub refresh this feed automatically.
            </div>
          )}

          {hiddenAutoCount > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-300/40 dark:bg-amber-300/20 dark:text-amber-100">
              Hiding {hiddenAutoCount} duplicate suggestion{hiddenAutoCount === 1 ? '' : 's'} already shown in References.
            </div>
          )}

          {/* Batch actions for pending auto results */}
          {pendingAutoResults.length > 0 && statusFilter === 'pending' && (
            <div className="flex items-center gap-2 rounded-lg border border-indigo-100 bg-indigo-50/50 px-3 py-2 dark:border-indigo-500/30 dark:bg-indigo-950/30">
              <span className="text-xs text-indigo-700 dark:text-indigo-200">
                {pendingAutoResults.length} pending paper{pendingAutoResults.length !== 1 ? 's' : ''}
              </span>
              <div className="flex-1" />
              <button
                type="button"
                onClick={() => bulkPromoteResults.mutate(pendingAutoResults.map((r) => r.id))}
                disabled={isBulkPromoting || isBulkDismissing}
                className="inline-flex items-center gap-1.5 rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isBulkPromoting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Check className="h-3.5 w-3.5" />
                )}
                Add All
              </button>
              <button
                type="button"
                onClick={() => bulkDismissResults.mutate(pendingAutoResults.map((r) => r.id))}
                disabled={isBulkPromoting || isBulkDismissing}
                className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-500 hover:bg-gray-50 hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
              >
                {isBulkDismissing ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <X className="h-3.5 w-3.5" />
                )}
                Dismiss All
              </button>
            </div>
          )}

          <div className="space-y-3">
            {resultsQuery.isLoading && (
              <div className="space-y-2">
                <div className="h-16 w-full animate-pulse rounded-xl bg-gray-100" />
                <div className="h-16 w-full animate-pulse rounded-xl bg-gray-100" />
              </div>
            )}

            {!resultsQuery.isLoading && autoResults.length === 0 && (
              <div className="rounded-xl border border-dashed border-gray-200 px-4 py-12 text-center text-xs text-gray-500 dark:border-slate-700 dark:text-slate-400">
                {activeFormState.autoRefresh
                  ? 'No new suggestions from the active feed yet. They will appear here as soon as the background run finishes.'
                  : 'Turn on auto-refresh to populate this feed with background discovery suggestions.'}
              </div>
            )}

            {!resultsQuery.isLoading && autoResults.length > 0 && (
              <div className="space-y-3">
                {autoResults.map((item: ProjectDiscoveryResultItem) => (
                  <DiscoveryResultCard
                    key={item.id}
                    item={item}
                    onPromote={(id) => promoteResult.mutate(id)}
                    onDismiss={(id) => dismissResult.mutate(id)}
                    isPromoting={promotingIds.has(item.id)}
                    isDismissing={dismissingIds.has(item.id)}
                    isDisabled={isClearingResults}
                  />
                ))}

                {hasMoreResults && (
                  <div className="flex justify-center pt-4">
                    <button
                      type="button"
                      onClick={() => setResultsLimit((prev) => prev + 20)}
                      disabled={resultsQuery.isFetching}
                      className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                    >
                      {resultsQuery.isFetching ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <RotateCcw className="h-4 w-4" />
                      )}
                      Load more ({totalResults - allResults.length} remaining)
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    )
  }


  if (isViewer) {
    return <Navigate to={`/projects/${project.id}/related-papers`} replace />
  }

  return (
    <div className="space-y-6">
      <div className="inline-flex items-center gap-2 rounded-2xl border border-gray-200 bg-white p-2 shadow-sm text-sm dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-200">
        <button
          type="button"
          onClick={() => {
            setActiveTab('manual')
            setLastSourceStats(null) // Clear source stats when switching tabs
          }}
          className={`rounded-full px-4 py-2 font-medium transition-colors ${
            activeTab === 'manual' ? 'bg-indigo-600 text-white shadow' : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-800'
          }`}
        >
          Manual discovery
        </button>
        <button
          type="button"
          onClick={() => {
            setActiveTab('active')
            setLastSourceStats(null) // Clear source stats when switching tabs
          }}
          className={`rounded-full px-4 py-2 font-medium transition-colors ${
            activeTab === 'active' ? 'bg-indigo-600 text-white shadow' : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-800'
          }`}
        >
          Active search feed
        </button>
      </div>

      {activeTab === 'manual' ? renderManualContent() : renderActiveContent()}
    </div>
  )
}

export default ProjectDiscovery
