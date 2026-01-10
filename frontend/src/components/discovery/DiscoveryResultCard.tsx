import { Check, Clock, FileDown, Loader2, ShieldCheck, X } from 'lucide-react'
import { ProjectDiscoveryResultItem, ProjectDiscoveryResultStatus } from '../../types'

const formatDateTime = (value?: string | null) => {
  if (!value) return '—'
  const date = new Date(value)
  return date.toLocaleString()
}

const statusBadge = (status: ProjectDiscoveryResultStatus) => {
  switch (status) {
    case 'pending':
      return 'bg-amber-100 text-amber-800 border border-amber-200 dark:bg-amber-300/25 dark:text-amber-100 dark:border-amber-300/40'
    case 'promoted':
      return 'bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/20 dark:text-emerald-200 dark:border-emerald-400/40'
    case 'dismissed':
      return 'bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-500/20 dark:text-rose-200 dark:border-rose-400/40'
    default:
      return 'bg-gray-100 text-gray-600 dark:bg-slate-700/60 dark:text-slate-300'
  }
}

const statusLabel = (status: ProjectDiscoveryResultStatus) => {
  switch (status) {
    case 'pending':
      return 'Pending'
    case 'promoted':
      return 'Promoted'
    case 'dismissed':
      return 'Dismissed'
    default:
      return status
  }
}

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
}: DiscoveryResultCardProps) => {
  const hasPdf = Boolean(item.has_pdf ?? item.pdf_url)
  const isOpenAccess = Boolean(item.is_open_access)
  const pdfUrl = item.pdf_url ?? undefined
  const isDeletable = item.status !== 'promoted'
  const isActionDisabled = isPromoting || isDismissing

  const renderScoreBadge = (score?: number | null) => {
    if (score == null) return null
    let cls = 'bg-gray-100 text-gray-700 dark:bg-slate-800/60 dark:text-slate-200'
    if (score >= 0.7) cls = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-200'
    else if (score >= 0.4) cls = 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-200'
    else cls = 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-200'
    return (
      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium ${cls} whitespace-nowrap shrink-0`}>
        Score {score.toFixed(2)}
      </span>
    )
  }

  return (
    <article
      className={`space-y-3 rounded-xl border px-4 py-4 text-sm text-gray-700 transition dark:text-slate-200 ${
        isDeleteMode && isSelected
          ? 'border-rose-300 bg-rose-50/40 dark:border-rose-400/50 dark:bg-rose-500/10'
          : 'border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-900/60'
      }`}
    >
      {/* Header row */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p className="text-base font-semibold text-gray-900 dark:text-slate-100">
            {item.title ?? 'Untitled result'}
          </p>
          <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-slate-400">
            <span>{item.source}</span>
            {item.doi && <span className="truncate">DOI: {item.doi}</span>}
            {item.published_year && <span>{item.published_year}</span>}
            {hasPdf && (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-200">
                <FileDown className="h-3 w-3" /> PDF available
              </span>
            )}
            {isOpenAccess && (
              <span className="inline-flex items-center gap-1 rounded-full bg-sky-50 px-2 py-1 text-sky-700 dark:bg-sky-500/20 dark:text-sky-200">
                <ShieldCheck className="h-3 w-3" /> Open access
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 self-start">
          {renderScoreBadge(item.relevance_score)}
          <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${statusBadge(item.status)}`}>
            {statusLabel(item.status)}
          </span>
          {isDeleteMode && isDeletable && onToggleSelect && (
            <label className="inline-flex items-center gap-2 text-xs text-gray-500 dark:text-slate-400">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-gray-300 text-rose-600 focus:ring-rose-500 dark:border-slate-600 dark:bg-slate-900/60"
                checked={isSelected}
                onChange={() => onToggleSelect(item.id)}
              />
              Select
            </label>
          )}
        </div>
      </div>

      {/* Summary */}
      {item.summary && (
        <p className="text-xs text-gray-600 line-clamp-3 dark:text-slate-300">{item.summary}</p>
      )}

      {/* Footer row */}
      <div className="flex flex-col gap-2 text-xs text-gray-500 dark:text-slate-400 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-1 text-gray-600 dark:bg-slate-800/60 dark:text-slate-300">
            <Clock className="h-3 w-3" /> Discovered {formatDateTime(item.created_at)}
          </span>
          {pdfUrl && (
            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-1 text-emerald-700 hover:bg-emerald-200 dark:bg-emerald-500/20 dark:text-emerald-200 dark:hover:bg-emerald-500/30"
            >
              <FileDown className="h-3 w-3" /> View PDF
            </a>
          )}
          <a
            href={item.source_url || (item.doi ? `https://doi.org/${item.doi}` : '#')}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-2 py-1 text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-500/20 dark:text-indigo-200 dark:hover:bg-indigo-500/30"
          >
            View Source
          </a>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          {!isDeleteMode && item.status === 'pending' && (
            <>
              <button
                type="button"
                onClick={() => onPromote(item.id)}
                disabled={isActionDisabled}
                className="inline-flex items-center gap-2 rounded-full bg-emerald-600 px-3 py-1.5 font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isPromoting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Check className="h-3.5 w-3.5" />
                )}
                Add to project
              </button>
              <button
                type="button"
                onClick={() => onDismiss(item.id)}
                disabled={isActionDisabled}
                className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1.5 font-medium text-gray-600 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                {isDismissing ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <X className="h-3.5 w-3.5" />
                )}
                Dismiss
              </button>
            </>
          )}
          {item.status !== 'pending' && item.promoted_at && (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-200">
              <Check className="h-3 w-3" /> Promoted {formatDateTime(item.promoted_at)}
            </span>
          )}
          {item.status === 'dismissed' && item.dismissed_at && (
            <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2 py-1 text-rose-700 dark:bg-rose-500/20 dark:text-rose-200">
              <X className="h-3 w-3" /> Dismissed {formatDateTime(item.dismissed_at)}
            </span>
          )}
        </div>
      </div>
    </article>
  )
}
