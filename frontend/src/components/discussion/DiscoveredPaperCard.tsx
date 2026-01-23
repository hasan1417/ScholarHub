import { Check, Loader2, Plus, ExternalLink, Unlock } from 'lucide-react'

export interface DiscoveredPaper {
  id: string
  title: string
  authors: string[]
  year?: number
  abstract?: string
  doi?: string
  url?: string
  source: string
  relevance_score?: number
  pdf_url?: string
  is_open_access?: boolean
  journal?: string
}

interface DiscoveredPaperCardProps {
  paper: DiscoveredPaper
  onAdd: () => void
  isAdding: boolean
  isAdded: boolean
}

export function DiscoveredPaperCard({
  paper,
  onAdd,
  isAdding,
  isAdded,
}: DiscoveredPaperCardProps) {
  const formatAuthors = () => {
    if (!paper.authors || paper.authors.length === 0) return 'Unknown authors'
    const displayAuthors = paper.authors.slice(0, 3).join(', ')
    return paper.authors.length > 3 ? `${displayAuthors} et al.` : displayAuthors
  }

  const getSourceBadgeColor = (source: string) => {
    const colors: Record<string, string> = {
      arxiv: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
      semantic_scholar: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
      openalex: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
      crossref: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
      pubmed: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
      core: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-300',
      europe_pmc: 'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300',
    }
    return colors[source.toLowerCase()] || 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'
  }

  return (
    <div className="border rounded-lg p-3 bg-white dark:bg-slate-800/60 hover:border-indigo-300 dark:hover:border-indigo-500/50 transition-colors">
      <div className="flex justify-between items-start gap-3">
        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-sm leading-tight line-clamp-2 text-gray-900 dark:text-gray-100">
            {paper.title}
          </h4>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {formatAuthors()}
            {paper.year && ` • ${paper.year}`}
            {paper.journal && <span className="italic"> • {paper.journal}</span>}
          </p>
          {paper.abstract && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 line-clamp-2">
              {paper.abstract}
            </p>
          )}
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${getSourceBadgeColor(paper.source)}`}
            >
              {paper.source.replace('_', ' ')}
            </span>
            {paper.is_open_access && (
              <span
                className="inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[10px] font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                title="Open Access - PDF can be automatically ingested"
              >
                <Unlock className="h-2.5 w-2.5" />
                Open access
              </span>
            )}
            {paper.doi && (
              <a
                href={`https://doi.org/${paper.doi}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 text-[10px] text-indigo-600 dark:text-indigo-400 hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                DOI
                <ExternalLink className="h-2.5 w-2.5" />
              </a>
            )}
            {paper.url && !paper.doi && (
              <a
                href={paper.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 text-[10px] text-indigo-600 dark:text-indigo-400 hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                Link
                <ExternalLink className="h-2.5 w-2.5" />
              </a>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onAdd}
          disabled={isAdding || isAdded}
          className={`shrink-0 inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium transition ${
            isAdded
              ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-300 cursor-default'
              : 'bg-indigo-600 text-white hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:bg-indigo-300 dark:disabled:bg-indigo-500/40'
          }`}
        >
          {isAdded ? (
            <>
              <Check className="h-3 w-3" />
              Added
            </>
          ) : isAdding ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <>
              <Plus className="h-3 w-3" />
              Add
            </>
          )}
        </button>
      </div>
    </div>
  )
}
