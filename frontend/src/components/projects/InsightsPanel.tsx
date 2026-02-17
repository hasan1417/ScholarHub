import { useState, useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Lightbulb,
  AlertTriangle,
  Search,
  FileText,
  ChevronDown,
  ChevronUp,
  X,
  Sparkles,
} from 'lucide-react'
import { projectsAPI } from '../../services/api'
import { ProactiveInsight } from '../../types'

const DISMISSED_KEY_PREFIX = 'insights_dismissed:'

const INSIGHT_ICONS: Record<string, typeof Lightbulb> = {
  citation_gap: AlertTriangle,
  coverage_gap: Search,
  new_papers: Search,
  writing_reminder: FileText,
  methodology_suggestion: Lightbulb,
}

const INSIGHT_ICON_STYLES: Record<string, string> = {
  citation_gap: 'bg-rose-100 text-rose-600 dark:bg-rose-500/20 dark:text-rose-400',
  coverage_gap: 'bg-amber-100 text-amber-600 dark:bg-amber-500/20 dark:text-amber-400',
  new_papers: 'bg-sky-100 text-sky-600 dark:bg-sky-500/20 dark:text-sky-400',
  writing_reminder: 'bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400',
  methodology_suggestion: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400',
}

const PRIORITY_DOT: Record<string, string> = {
  high: 'bg-rose-500',
  medium: 'bg-amber-500',
  low: 'bg-gray-400 dark:bg-slate-500',
}

interface InsightsPanelProps {
  projectId: string
}

/**
 * Deterministic key for deduplication/dismissal: type + first 60 chars of message.
 */
function insightKey(insight: ProactiveInsight): string {
  return `${insight.type}::${insight.message.slice(0, 60)}`
}

export default function InsightsPanel({ projectId }: InsightsPanelProps) {
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)

  const storageKey = `${DISMISSED_KEY_PREFIX}${projectId}`

  // Read dismissed IDs from localStorage
  const [dismissedSet, setDismissedSet] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      return raw ? new Set(JSON.parse(raw) as string[]) : new Set()
    } catch {
      return new Set()
    }
  })

  const dismiss = useCallback(
    (key: string) => {
      setDismissedSet((prev) => {
        const next = new Set(prev)
        next.add(key)
        try {
          localStorage.setItem(storageKey, JSON.stringify([...next]))
        } catch {
          // localStorage full -- ignore
        }
        return next
      })
    },
    [storageKey],
  )

  const insightsQuery = useQuery({
    queryKey: ['project', projectId, 'insights'],
    queryFn: async () => {
      const response = await projectsAPI.getInsights(projectId)
      return response.data.insights ?? []
    },
    enabled: Boolean(projectId),
    staleTime: 5 * 60_000, // 5 minutes
    refetchOnWindowFocus: false,
  })

  const visibleInsights = useMemo(() => {
    if (!insightsQuery.data) return []
    return insightsQuery.data.filter((i) => !dismissedSet.has(insightKey(i)))
  }, [insightsQuery.data, dismissedSet])

  // Nothing to show -- don't render
  if (insightsQuery.isLoading || visibleInsights.length === 0) {
    return null
  }

  const highCount = visibleInsights.filter((i) => i.priority === 'high').length

  const handleAction = (insight: ProactiveInsight) => {
    if (insight.action_type === 'search') {
      const query = (insight.action_data?.query as string) || ''
      navigate(`/projects/${projectId}/library/discover${query ? `?q=${encodeURIComponent(query)}` : ''}`)
    } else if (insight.action_type === 'navigate') {
      const paperId = insight.action_data?.paper_id as string | undefined
      if (paperId) {
        navigate(`/projects/${projectId}/papers/${paperId}`)
      }
    }
  }

  const actionLabel = (insight: ProactiveInsight): string => {
    if (insight.action_type === 'search') return 'Search'
    if (insight.action_type === 'navigate') return 'View'
    return 'Dismiss'
  }

  return (
    <section className="rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50/80 to-white shadow-sm transition-colors dark:border-indigo-500/30 dark:from-indigo-500/5 dark:to-slate-800">
      {/* Header */}
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        className="flex w-full items-center justify-between px-5 py-4 text-left"
      >
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-100 dark:bg-indigo-500/20">
            <Sparkles className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
          </span>
          <h2 className="text-sm font-semibold text-gray-900 dark:text-slate-100">
            AI Insights
          </h2>
          <span className="inline-flex items-center rounded-full bg-indigo-100 px-2 py-0.5 text-[11px] font-medium text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300">
            {visibleInsights.length} new
          </span>
          {highCount > 0 && (
            <span className="inline-flex items-center rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-medium text-rose-700 dark:bg-rose-500/20 dark:text-rose-300">
              {highCount} important
            </span>
          )}
        </div>
        {collapsed ? (
          <ChevronDown className="h-4 w-4 text-gray-400 dark:text-slate-500" />
        ) : (
          <ChevronUp className="h-4 w-4 text-gray-400 dark:text-slate-500" />
        )}
      </button>

      {/* Insight cards */}
      {!collapsed && (
        <div className="space-y-2 px-5 pb-5">
          {visibleInsights.map((insight) => {
            const key = insightKey(insight)
            const Icon = INSIGHT_ICONS[insight.type] || Lightbulb
            const iconStyle = INSIGHT_ICON_STYLES[insight.type] || 'bg-gray-100 text-gray-500 dark:bg-slate-700 dark:text-slate-400'
            const dotColor = PRIORITY_DOT[insight.priority] || PRIORITY_DOT.low

            return (
              <div
                key={key}
                className="group flex items-start gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 transition-colors hover:border-indigo-200 dark:border-slate-700 dark:bg-slate-800/80 dark:hover:border-indigo-500/40"
              >
                {/* Icon */}
                <span className={`mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg ${iconStyle}`}>
                  <Icon className="h-4 w-4" />
                </span>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full flex-shrink-0 ${dotColor}`} />
                    <p className="text-sm font-medium text-gray-900 dark:text-slate-100">
                      {insight.title}
                    </p>
                  </div>
                  <p className="mt-1 text-xs text-gray-600 dark:text-slate-400 leading-relaxed">
                    {insight.message}
                  </p>

                  {/* Actions */}
                  <div className="mt-2 flex items-center gap-2">
                    {insight.action_type !== 'dismiss' && (
                      <button
                        type="button"
                        onClick={() => handleAction(insight)}
                        className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 transition hover:bg-indigo-100 dark:bg-indigo-500/10 dark:text-indigo-300 dark:hover:bg-indigo-500/20"
                      >
                        {insight.action_type === 'search' && <Search className="h-3 w-3" />}
                        {insight.action_type === 'navigate' && <FileText className="h-3 w-3" />}
                        {actionLabel(insight)}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => dismiss(key)}
                      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:text-slate-500 dark:hover:bg-slate-700 dark:hover:text-slate-300"
                    >
                      <X className="h-3 w-3" />
                      Dismiss
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
