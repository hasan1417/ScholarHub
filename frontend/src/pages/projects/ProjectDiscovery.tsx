import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Check,
  Clock,
  Filter,
  Lightbulb,
  Loader2,
  RotateCcw,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import { projectDiscoveryAPI, projectReferencesAPI } from '../../services/api'
import { Navigate } from 'react-router-dom'
import {
  ProjectDiscoveryPreferences,
  ProjectDiscoverySettingsPayload,
  ProjectDiscoveryResultItem,
  ProjectDiscoveryResultStatus,
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

const sanitizeKeywords = (value: string) => {
  const trimmed = value.trim()
  if (!trimmed) return ''
  if (trimmed.toLowerCase() === 'ai') return ''
  return trimmed
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
  const [activeStatusMessage, setActiveStatusMessage] = useState<string | null>(null)
  const [activeErrorMessage, setActiveErrorMessage] = useState<string | null>(null)
  const [manualStatusMessage, setManualStatusMessage] = useState<string | null>(null)
  const [manualErrorMessage, setManualErrorMessage] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'manual' | 'active'>('manual')
  const [isDeleteMode, setIsDeleteMode] = useState(false)
  const [selectedResults, setSelectedResults] = useState<string[]>([])
  const [promotingIds, setPromotingIds] = useState<Set<string>>(new Set())
  const [dismissingIds, setDismissingIds] = useState<Set<string>>(new Set())
  const [resultsLimit, setResultsLimit] = useState(20)
  const [discoveryCooldown, setDiscoveryCooldown] = useState(0) // Seconds remaining
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

  const manualResults = useMemo(
    () => allResults.filter((item) => item.run_type === 'manual'),
    [allResults]
  )

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
    () =>
      autoResultsRaw.filter((item) => {
        const doiKey = item.doi ? `doi:${item.doi.toLowerCase()}` : null
        if (doiKey && suggestionKeys.has(doiKey)) return false
        const titleKey = item.title ? `title:${item.title.toLowerCase()}` : null
        if (titleKey && suggestionKeys.has(titleKey)) return false
        return true
      }),
    [autoResultsRaw, suggestionKeys]
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
    onError: (_error, resultId) => {
      setPromotingIds((prev) => {
        const next = new Set(prev)
        next.delete(resultId)
        return next
      })
    },
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

  const isDeleting = bulkDeleteResults.isPending

  const runDiscovery = useMutation({
    onMutate: () => {
      setManualStatusMessage(null)
      setManualErrorMessage(null)
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
      const resultsCreated = data?.results_created ?? 0
      if (resultsCreated === 0) {
        setManualStatusMessage('No new discovery results — everything in your project already matches this search.')
      } else {
        setManualStatusMessage(null)
      }
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryResults'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'discoveryPendingCount'] })
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'referenceSuggestions'] })
    },
    onError: (error: unknown) => {
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
  const lastRunAt = settingsQuery.data?.last_run_at ?? fallbackPrefs?.last_run_at

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
      <section className="space-y-4 rounded-2xl border border-indigo-100 bg-white p-6 shadow-sm transition-colors dark:border-indigo-500/30 dark:bg-slate-900/40">
        <div className="flex items-center gap-3 text-indigo-700 dark:text-indigo-200">
          <Lightbulb className="h-5 w-5" />
          <div>
            <h2 className="text-base font-semibold">Manual discovery</h2>
            <p className="text-xs text-indigo-600/80">
              Tweak the next run without changing your saved preferences. Persistent settings now live in the
              <span className="font-medium"> Active search feed</span> tab.
            </p>
          </div>
        </div>

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
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-xs font-medium text-gray-700 dark:text-slate-300">
            Base query
            <input
              type="text"
              value={manualFormState.query}
              onChange={(event) =>
                updateManualForm((prev) => ({ ...prev, query: event.target.value }))
              }
              placeholder="e.g. generative AI for systematic reviews"
              className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-400"
            />
          </label>
          {projectKeywordPreset && (
            <div className="text-xs font-medium text-gray-700 dark:text-slate-300">
              Project keywords
              <div className="mt-1 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-800 dark:border-slate-600 dark:bg-slate-800/60 dark:text-slate-200">
                {projectKeywordPreset.split(',').map((kw) => kw.trim()).filter(Boolean).join(', ') || 'No keywords provided'}
              </div>
            </div>
          )}
          <label className="text-xs font-medium text-gray-700 dark:text-slate-300">
            Max results per run
            <input
              type="number"
              min={1}
              max={100}
              value={manualFormState.maxResults}
              onChange={(event) =>
                updateManualForm((prev) => ({ ...prev, maxResults: event.target.value }))
              }
              placeholder="20"
              className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-400"
            />
          </label>
          <label className="text-xs font-medium text-gray-700 dark:text-slate-300">
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
              className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-400"
            />
          </label>
        </div>

        <div className="text-xs font-medium text-gray-700 dark:text-slate-300">
          Sources
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {AVAILABLE_SOURCES.map((source) => {
              const checked = manualFormState.sources.includes(source.value)
              return (
                <label
                  key={source.value}
                  className="flex items-center gap-2 rounded-md border border-gray-200 px-3 py-2 text-xs text-gray-600 hover:border-indigo-200 dark:border-slate-600 dark:text-slate-300 dark:hover:border-indigo-400/60"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => handleManualSourceToggle(source.value)}
                    className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60"
                  />
                  {source.label}
                </label>
              )
            })}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 text-xs">
          <button
            type="button"
            onClick={() => runDiscovery.mutate()}
            disabled={runDiscovery.isPending || discoveryCooldown > 0}
            className="inline-flex items-center gap-2 rounded-full bg-green-700 px-4 py-2 font-medium text-white hover:bg-green-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {runDiscovery.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            {runDiscovery.isPending
              ? 'Running...'
              : discoveryCooldown > 0
                ? `Wait ${discoveryCooldown}s`
                : 'Run Discovery'}
          </button>
          <span className="inline-flex items-center gap-2 rounded-full bg-gray-100 px-3 py-1.5 text-xs text-gray-600 dark:bg-slate-800/60 dark:text-slate-300">
            <Clock className="h-3.5 w-3.5" /> Last run {formatDateTime(lastRunAt)} • {pendingCount} pending
          </span>
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
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-indigo-200 dark:bg-indigo-900/50">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-indigo-500 dark:bg-indigo-400" style={{ animation: 'progress 2s ease-in-out infinite' }} />
          </div>
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
        <section className="space-y-4 rounded-2xl border border-indigo-100 bg-white p-6 shadow-sm transition-colors dark:border-indigo-500/30 dark:bg-slate-900/40">
          <div className="flex items-center gap-3 text-indigo-700 dark:text-indigo-200">
            <Sparkles className="h-5 w-5" />
            <div>
              <h2 className="text-base font-semibold">Active feed preferences</h2>
              <p className="text-xs text-indigo-600/80">
                Configure the background discovery job that keeps References fresh.
              </p>
            </div>
          </div>

          <div className="inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1.5 text-xs text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-200">
            <Clock className="h-3.5 w-3.5" /> {refreshSummary}
          </div>

          {activeErrorMessage && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-400/40 dark:bg-rose-500/10 dark:text-rose-200">
              {activeErrorMessage}
            </div>
          )}
          {activeStatusMessage && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
              {activeStatusMessage}
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-xs font-medium text-gray-700 dark:text-slate-300">
              Base query
              <input
                type="text"
                value={activeFormState.query}
                onChange={(event) =>
                  updateActiveForm((prev) => ({ ...prev, query: event.target.value }))
                }
                placeholder="e.g. multimodal summarization for biomedical reviews"
                className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-400"
              />
            </label>
            {projectKeywordPreset ? (
              <div className="text-xs font-medium text-gray-700 dark:text-slate-300">
                Project keywords
                <div className="mt-1 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-800 dark:border-slate-600 dark:bg-slate-800/60 dark:text-slate-200">
                  {projectKeywordPreset.split(',').map((kw) => kw.trim()).filter(Boolean).join(', ')}
                </div>
              </div>
            ) : (
              <div className="text-xs font-medium text-gray-500 dark:text-slate-400">
                Project keywords
                <div className="mt-1 rounded-md border border-dashed border-gray-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300">No keywords set on project</div>
              </div>
            )}
            <label className="text-xs font-medium text-gray-700 dark:text-slate-300">
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
                className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-400"
              />
            </label>
            <label className="text-xs font-medium text-gray-700 dark:text-slate-300">
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
                className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-400"
              />
            </label>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-xs font-medium text-gray-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={activeFormState.autoRefresh}
                onChange={(event) =>
                  updateActiveForm((prev) => ({ ...prev, autoRefresh: event.target.checked }))
                }
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60"
              />
              Enable background auto-refresh
            </label>
            <label className="text-xs font-medium text-gray-700 dark:text-slate-300">
              Refresh interval (minutes, minimum {MIN_REFRESH_INTERVAL_MINUTES})
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
                placeholder={String(DEFAULT_REFRESH_INTERVAL_MINUTES)}
                disabled={!activeFormState.autoRefresh}
                className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:disabled:bg-slate-800/60"
              />
            </label>
          </div>

          <div className="text-xs font-medium text-gray-700 dark:text-slate-300">
            Sources
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {AVAILABLE_SOURCES.map((source) => {
                const checked = activeFormState.sources.includes(source.value)
                return (
                  <label
                    key={source.value}
                    className="flex items-center gap-2 rounded-md border border-gray-200 px-3 py-2 text-xs text-gray-600 hover:border-indigo-200 dark:border-slate-600 dark:text-slate-300 dark:hover:border-indigo-400/60"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => handleActiveSourceToggle(source.value)}
                      className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60"
                    />
                    {source.label}
                  </label>
                )
              })}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600 dark:text-slate-300">
            <button
              type="button"
              onClick={() => saveSettings.mutate()}
              disabled={saveSettings.isPending || !isActiveDirty}
              className="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saveSettings.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Check className="h-3.5 w-3.5" />
              )}
              Save preferences
            </button>
            <button
              type="button"
              onClick={resetActiveForm}
              disabled={saveSettings.isPending}
              className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-4 py-2 font-medium text-gray-600 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              <RotateCcw className="h-3.5 w-3.5" /> Reset to saved
            </button>
            {isActiveDirty && !saveSettings.isPending && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-3 py-1.5 text-amber-700 dark:bg-amber-500/20 dark:text-amber-200">
                <Sparkles className="h-3 w-3" /> Unsaved changes
              </span>
            )}
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
          onClick={() => setActiveTab('manual')}
          className={`rounded-full px-4 py-2 font-medium transition-colors ${
            activeTab === 'manual' ? 'bg-indigo-600 text-white shadow' : 'text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-800'
          }`}
        >
          Manual discovery
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('active')}
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
