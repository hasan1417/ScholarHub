import { useState } from 'react'
import { Check, ChevronDown, ChevronUp, ExternalLink, FileText, Loader2, Lock, Unlock, X } from 'lucide-react'
import { ProjectDiscoveryResultItem } from '../../types'

interface DiscoveryResultCardProps {
  item: ProjectDiscoveryResultItem
  onPromote: (id: string) => void
  onDismiss: (id: string) => void
  isPromoting: boolean
  isDismissing: boolean
  // Delete mode props (optional, only for manual results)
  isDeleteMode?: boolean
  isSelected?: boolean
  onToggleSelect?: (id: string) => void
  // Compact mode for lists
  compact?: boolean
}

// Relevance bar component
const RelevanceBar = ({ score }: { score: number }) => {
  // Score is 0-1, map to percentage
  const percentage = Math.round(score * 100)

  // Color based on score
  let barColor = 'bg-gray-300 dark:bg-slate-600'
  if (score >= 0.8) barColor = 'bg-emerald-500'
  else if (score >= 0.6) barColor = 'bg-green-500'
  else if (score >= 0.4) barColor = 'bg-amber-500'
  else if (score >= 0.2) barColor = 'bg-orange-500'
  else barColor = 'bg-red-400'

  return (
    <div className="flex items-center gap-2" title={`Relevance: ${percentage}%`}>
      <div className="w-16 h-1.5 bg-gray-200 dark:bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className="text-[10px] text-gray-500 dark:text-slate-400 tabular-nums">
        {percentage}%
      </span>
    </div>
  )
}

// Source badge with link
const SourceBadge = ({ source, url, doi }: { source: string; url?: string | null; doi?: string | null }) => {
  const sourceColors: Record<string, string> = {
    arxiv: 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300',
    semantic_scholar: 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    openalex: 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300',
    crossref: 'bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
    pubmed: 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
    core: 'bg-cyan-50 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-300',
    europe_pmc: 'bg-teal-50 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300',
  }

  const color = sourceColors[source.toLowerCase()] || 'bg-gray-100 text-gray-700 dark:bg-slate-700 dark:text-slate-300'
  const displayName = source.replace(/_/g, ' ')
  const href = url || (doi ? `https://doi.org/${doi}` : null)

  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${color} hover:opacity-80 transition-opacity`}
      >
        {displayName}
        <ExternalLink className="h-2.5 w-2.5" />
      </a>
    )
  }

  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium ${color}`}>
      {displayName}
    </span>
  )
}

export const DiscoveryResultCard = ({
  item,
  onPromote,
  onDismiss,
  isPromoting,
  isDismissing,
  isDeleteMode = false,
  isSelected = false,
  onToggleSelect,
  compact = false,
}: DiscoveryResultCardProps) => {
  const [isExpanded, setIsExpanded] = useState(false)

  const hasPdf = Boolean(item.has_pdf ?? item.pdf_url)
  const isOpenAccess = Boolean(item.is_open_access)
  const pdfUrl = item.pdf_url ?? undefined
  const isDeletable = item.status !== 'promoted'
  const isActionDisabled = isPromoting || isDismissing
  const isPending = item.status === 'pending'

  // Truncate abstract for preview
  const abstractPreview = item.summary && item.summary.length > 200
    ? item.summary.slice(0, 200) + '...'
    : item.summary

  const showExpandButton = item.summary && item.summary.length > 200

  return (
    <article
      className={`rounded-xl border transition ${
        isDeleteMode && isSelected
          ? 'border-rose-300 bg-rose-50/40 dark:border-rose-400/50 dark:bg-rose-500/10'
          : 'border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-900/60'
      } ${compact ? 'px-3 py-2.5' : 'px-4 py-3'}`}
    >
      {/* Main content row */}
      <div className="flex gap-3">
        {/* Delete mode checkbox */}
        {isDeleteMode && isDeletable && onToggleSelect && (
          <div className="flex items-start pt-1">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-gray-300 text-rose-600 focus:ring-rose-500 dark:border-slate-600 dark:bg-slate-900/60"
              checked={isSelected}
              onChange={() => onToggleSelect(item.id)}
            />
          </div>
        )}

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Title row with relevance */}
          <div className="flex items-start justify-between gap-3">
            <h3 className={`font-semibold text-gray-900 dark:text-slate-100 leading-tight ${compact ? 'text-sm' : 'text-base'}`}>
              {item.title ?? 'Untitled result'}
            </h3>

            {/* Relevance bar + status */}
            <div className="flex items-center gap-2 shrink-0">
              {item.relevance_score != null && (
                <RelevanceBar score={item.relevance_score} />
              )}
              {!isPending && (
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  item.status === 'promoted'
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-200'
                    : 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-200'
                }`}>
                  {item.status === 'promoted' ? 'Added' : 'Dismissed'}
                </span>
              )}
            </div>
          </div>

          {/* Metadata row */}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1.5 text-xs text-gray-500 dark:text-slate-400">
            <SourceBadge source={item.source} url={item.source_url} doi={item.doi} />

            {item.doi && (
              <a
                href={`https://doi.org/${item.doi}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                DOI
              </a>
            )}

            {item.published_year && (
              <span>{item.published_year}</span>
            )}

            {item.journal && (
              <span className="italic text-gray-600 dark:text-slate-300 truncate max-w-[200px]" title={item.journal}>
                {item.journal}
              </span>
            )}

            {/* PDF/Open Access combined badge */}
            {(hasPdf || isOpenAccess) && (
              <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                hasPdf
                  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-200'
                  : 'bg-sky-100 text-sky-700 dark:bg-sky-500/20 dark:text-sky-200'
              }`}>
                {hasPdf ? (
                  <>
                    <FileText className="h-3 w-3" />
                    PDF
                  </>
                ) : (
                  <>
                    <Unlock className="h-3 w-3" />
                    OA
                  </>
                )}
              </span>
            )}

            {!hasPdf && !isOpenAccess && (
              <span className="inline-flex items-center gap-1 text-gray-400 dark:text-slate-500">
                <Lock className="h-3 w-3" />
              </span>
            )}
          </div>

          {/* Abstract */}
          {item.summary && (
            <div className="mt-2">
              <p className="text-xs text-gray-600 dark:text-slate-300 leading-relaxed">
                {isExpanded ? item.summary : abstractPreview}
              </p>
              {showExpandButton && (
                <button
                  type="button"
                  onClick={() => setIsExpanded(!isExpanded)}
                  className="inline-flex items-center gap-0.5 mt-1 text-[10px] text-indigo-600 dark:text-indigo-400 hover:underline"
                >
                  {isExpanded ? (
                    <>
                      Show less <ChevronUp className="h-3 w-3" />
                    </>
                  ) : (
                    <>
                      Show more <ChevronDown className="h-3 w-3" />
                    </>
                  )}
                </button>
              )}
            </div>
          )}

          {/* Action buttons */}
          {!isDeleteMode && (
            <div className="flex items-center gap-2 mt-3">
              {isPending ? (
                <>
                  {/* View PDF button */}
                  {pdfUrl && (
                    <a
                      href={pdfUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                    >
                      <FileText className="h-3.5 w-3.5" />
                      View PDF
                    </a>
                  )}

                  {/* Spacer */}
                  <div className="flex-1" />

                  {/* Add to project */}
                  <button
                    type="button"
                    onClick={() => onPromote(item.id)}
                    disabled={isActionDisabled}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isPromoting ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Check className="h-3.5 w-3.5" />
                    )}
                    Add
                  </button>

                  {/* Dismiss */}
                  <button
                    type="button"
                    onClick={() => onDismiss(item.id)}
                    disabled={isActionDisabled}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-500 hover:bg-gray-50 hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                  >
                    {isDismissing ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <X className="h-3.5 w-3.5" />
                    )}
                    Dismiss
                  </button>
                </>
              ) : (
                // Already processed status
                <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-slate-400">
                  {item.status === 'promoted' && (
                    <span className="inline-flex items-center gap-1">
                      <Check className="h-3.5 w-3.5 text-emerald-500" />
                      Added to project
                    </span>
                  )}
                  {item.status === 'dismissed' && (
                    <span className="inline-flex items-center gap-1">
                      <X className="h-3.5 w-3.5 text-rose-500" />
                      Dismissed
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </article>
  )
}
