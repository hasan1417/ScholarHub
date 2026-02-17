import React, { useState } from 'react'
import { X, ChevronDown, ChevronRight, Loader2, FileSearch, AlertTriangle, Info, AlertCircle } from 'lucide-react'

export interface WritingIssue {
  type: string
  severity: string
  message: string
  line: number | null
  suggestion: string | null
}

export interface WritingAnalysisResult {
  issues: WritingIssue[]
  stats: Record<string, number>
  score: number
}

interface WritingAnalysisPanelProps {
  result: WritingAnalysisResult | null
  loading: boolean
  onAnalyze: (venue?: string) => void
  onClose: () => void
}

const VENUE_OPTIONS = [
  { value: '', label: 'No specific venue' },
  { value: 'ieee', label: 'IEEE' },
  { value: 'acm', label: 'ACM' },
  { value: 'nature', label: 'Nature' },
  { value: 'springer', label: 'Springer' },
  { value: 'arxiv', label: 'arXiv' },
]

const ISSUE_TYPE_LABELS: Record<string, string> = {
  citation_density: 'Citation Density',
  hedging: 'Hedging',
  structure: 'Structure',
  venue: 'Venue Conformance',
}

const SEVERITY_CONFIG: Record<string, { icon: typeof AlertCircle; color: string; bg: string }> = {
  error: {
    icon: AlertCircle,
    color: 'text-red-600 dark:text-red-400',
    bg: 'bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-800',
  },
  warning: {
    icon: AlertTriangle,
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-50 border-amber-200 dark:bg-amber-900/20 dark:border-amber-800',
  },
  info: {
    icon: Info,
    color: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-50 border-blue-200 dark:bg-blue-900/20 dark:border-blue-800',
  },
}

function scoreColor(score: number): string {
  if (score >= 90) return 'text-emerald-600 dark:text-emerald-400'
  if (score >= 70) return 'text-amber-600 dark:text-amber-400'
  return 'text-red-600 dark:text-red-400'
}

function scoreTrackColor(score: number): string {
  if (score >= 90) return 'stroke-emerald-500'
  if (score >= 70) return 'stroke-amber-500'
  return 'stroke-red-500'
}

function ScoreRing({ score }: { score: number }) {
  const radius = 36
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (score / 100) * circumference

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width="88" height="88" className="-rotate-90">
        <circle
          cx="44"
          cy="44"
          r={radius}
          fill="none"
          strokeWidth="6"
          className="stroke-slate-200 dark:stroke-slate-700"
        />
        <circle
          cx="44"
          cy="44"
          r={radius}
          fill="none"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className={`${scoreTrackColor(score)} transition-all duration-500`}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className={`text-xl font-bold ${scoreColor(score)}`}>{score}</span>
        <span className="text-[10px] text-slate-400 dark:text-slate-500">/ 100</span>
      </div>
    </div>
  )
}

export const WritingAnalysisPanel: React.FC<WritingAnalysisPanelProps> = ({
  result,
  loading,
  onAnalyze,
  onClose,
}) => {
  const [venue, setVenue] = useState('')
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())

  const toggleGroup = (group: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }

  // Group issues by type
  const groupedIssues: Record<string, WritingIssue[]> = {}
  if (result) {
    for (const issue of result.issues) {
      if (!groupedIssues[issue.type]) groupedIssues[issue.type] = []
      groupedIssues[issue.type].push(issue)
    }
  }

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-[320px] flex-col border-l border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2.5 dark:border-slate-700">
        <div className="flex items-center gap-2">
          <FileSearch className="h-4 w-4 text-indigo-500" />
          <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Writing Quality
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          aria-label="Close writing analysis"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Venue selector + Analyze button */}
      <div className="border-b border-slate-200 px-3 py-2.5 dark:border-slate-700">
        <label className="mb-1.5 block text-xs font-medium text-slate-500 dark:text-slate-400">
          Target venue (optional)
        </label>
        <select
          value={venue}
          onChange={e => setVenue(e.target.value)}
          className="mb-2 w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-700 focus:border-indigo-400 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
        >
          {VENUE_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => onAnalyze(venue || undefined)}
          disabled={loading}
          className="flex w-full items-center justify-center gap-2 rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-wait disabled:opacity-60"
        >
          {loading ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Analyzing...
            </>
          ) : (
            <>
              <FileSearch className="h-3.5 w-3.5" />
              Analyze Writing
            </>
          )}
        </button>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto">
        {!result && !loading && (
          <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
            <FileSearch className="h-8 w-8 text-slate-300 dark:text-slate-600" />
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Click "Analyze Writing" to check your document for writing quality issues.
            </p>
          </div>
        )}

        {result && (
          <>
            {/* Score */}
            <div className="flex flex-col items-center border-b border-slate-200 py-4 dark:border-slate-700">
              <ScoreRing score={result.score} />
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                {result.issues.length === 0
                  ? 'No issues found'
                  : `${result.issues.length} issue${result.issues.length === 1 ? '' : 's'} found`}
              </p>
            </div>

            {/* Issues grouped by type */}
            <div className="px-2 py-2">
              {Object.entries(groupedIssues).map(([type, typeIssues]) => {
                const collapsed = collapsedGroups.has(type)
                return (
                  <div key={type} className="mb-1">
                    <button
                      type="button"
                      onClick={() => toggleGroup(type)}
                      className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                    >
                      {collapsed
                        ? <ChevronRight className="h-3 w-3" />
                        : <ChevronDown className="h-3 w-3" />}
                      <span>{ISSUE_TYPE_LABELS[type] || type}</span>
                      <span className="ml-auto rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                        {typeIssues.length}
                      </span>
                    </button>
                    {!collapsed && (
                      <div className="ml-1 space-y-1 pb-1 pl-3">
                        {typeIssues.map((issue, idx) => {
                          const config = SEVERITY_CONFIG[issue.severity] || SEVERITY_CONFIG.info
                          const Icon = config.icon
                          return (
                            <div
                              key={idx}
                              className={`rounded border px-2.5 py-2 ${config.bg}`}
                            >
                              <div className="flex items-start gap-1.5">
                                <Icon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${config.color}`} />
                                <div className="min-w-0 flex-1">
                                  <p className="text-xs text-slate-700 dark:text-slate-200">
                                    {issue.message}
                                  </p>
                                  {issue.suggestion && (
                                    <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                                      {issue.suggestion}
                                    </p>
                                  )}
                                  {issue.line != null && (
                                    <span className="mt-1 inline-block rounded bg-slate-200/60 px-1 py-0.5 text-[10px] text-slate-500 dark:bg-slate-700/60 dark:text-slate-400">
                                      Line {issue.line}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}

              {result.issues.length === 0 && (
                <div className="flex flex-col items-center gap-1 py-4 text-center">
                  <span className="text-2xl">&#10003;</span>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    No issues detected. Your writing looks good!
                  </p>
                </div>
              )}
            </div>

            {/* Stats */}
            <div className="border-t border-slate-200 px-3 py-3 dark:border-slate-700">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                Document Stats
              </p>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { label: 'Words', value: result.stats.word_count },
                  { label: 'Citations', value: result.stats.citation_count },
                  { label: 'Sections', value: result.stats.section_count },
                  { label: 'Avg. para. length', value: result.stats.avg_paragraph_length },
                  { label: 'Citations / 1k words', value: result.stats.citations_per_1000 },
                ].map(stat => (
                  <div
                    key={stat.label}
                    className="rounded bg-slate-50 px-2 py-1.5 dark:bg-slate-800/60"
                  >
                    <p className="text-[10px] text-slate-400 dark:text-slate-500">{stat.label}</p>
                    <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                      {stat.value ?? 0}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
