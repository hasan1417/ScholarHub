import { useState } from 'react'
import {
  Search,
  Loader2,
  X,
  BookPlus,
  FolderPlus,
  ExternalLink,
  FileText,
  Trash2,
  Info,
} from 'lucide-react'
import { DiscoveredPaper } from './DiscoveredPaperCard'

interface DiscoveryQueuePanelProps {
  papers: DiscoveredPaper[]
  query: string
  isSearching: boolean
  notification: string | null
  onAddToChannel: (paper: DiscoveredPaper) => Promise<void>
  onAddToLibrary: (paper: DiscoveredPaper) => Promise<void>
  onDismiss: (paperId: string) => void
  onDismissAll: () => void
  onClearNotification: () => void
}

export function DiscoveryQueuePanel({
  papers,
  query,
  isSearching,
  notification,
  onAddToChannel,
  onAddToLibrary,
  onDismiss,
  onDismissAll,
  onClearNotification,
}: DiscoveryQueuePanelProps) {
  const [processingPapers, setProcessingPapers] = useState<Record<string, 'channel' | 'library'>>({})
  const [addedPapers, setAddedPapers] = useState<Record<string, 'channel' | 'library' | 'both'>>({})

  const handleAddToChannel = async (paper: DiscoveredPaper) => {
    setProcessingPapers((prev) => ({ ...prev, [paper.id]: 'channel' }))
    try {
      await onAddToChannel(paper)
      setAddedPapers((prev) => ({
        ...prev,
        [paper.id]: prev[paper.id] === 'library' ? 'both' : 'channel',
      }))
    } finally {
      setProcessingPapers((prev) => {
        const newState = { ...prev }
        delete newState[paper.id]
        return newState
      })
    }
  }

  const handleAddToLibrary = async (paper: DiscoveredPaper) => {
    setProcessingPapers((prev) => ({ ...prev, [paper.id]: 'library' }))
    try {
      await onAddToLibrary(paper)
      setAddedPapers((prev) => ({
        ...prev,
        [paper.id]: prev[paper.id] === 'channel' ? 'both' : 'library',
      }))
    } finally {
      setProcessingPapers((prev) => {
        const newState = { ...prev }
        delete newState[paper.id]
        return newState
      })
    }
  }

  const formatAuthors = (authors: string[]) => {
    if (!authors || authors.length === 0) return 'Unknown authors'
    const displayAuthors = authors.slice(0, 3).join(', ')
    return authors.length > 3 ? `${displayAuthors} et al.` : displayAuthors
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

  // Loading state
  if (isSearching) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
        <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
          Searching for papers...
        </p>
        {query && (
          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
            Query: "{query}"
          </p>
        )}
      </div>
    )
  }

  // Empty state
  if (papers.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <Search className="h-12 w-12 text-gray-300 dark:text-slate-600" />
        <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
          No discoveries yet
        </p>
        <p className="mt-1 text-xs text-gray-400 dark:text-gray-500 text-center max-w-xs">
          Ask the AI to search for papers related to your discussion
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Notification banner */}
      {notification && (
        <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 dark:bg-amber-900/20 border-b border-amber-200 dark:border-amber-800">
          <Info className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0" />
          <p className="text-xs text-amber-700 dark:text-amber-300 flex-1">
            {notification}
          </p>
          <button
            onClick={onClearNotification}
            className="p-0.5 rounded hover:bg-amber-200 dark:hover:bg-amber-800 transition-colors"
          >
            <X className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
          </button>
        </div>
      )}

      {/* Header with query and actions */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-slate-700">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
            {papers.length} paper{papers.length !== 1 ? 's' : ''} found
          </span>
          {query && (
            <span className="text-xs text-gray-400 dark:text-gray-500 truncate">
              for "{query}"
            </span>
          )}
        </div>
        <button
          onClick={onDismissAll}
          className="text-xs text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400 transition-colors"
        >
          Clear All
        </button>
      </div>

      {/* Papers list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {papers.map((paper) => {
          const isProcessing = !!processingPapers[paper.id]
          const addedState = addedPapers[paper.id]
          const addedToChannel = addedState === 'channel' || addedState === 'both'
          const addedToLibrary = addedState === 'library' || addedState === 'both'

          return (
            <div
              key={paper.id}
              className="border rounded-lg p-3 bg-white dark:bg-slate-800/60 border-gray-200 dark:border-slate-700"
            >
              {/* Paper info */}
              <div className="mb-2">
                <h4 className="font-medium text-sm leading-tight line-clamp-2 text-gray-900 dark:text-gray-100">
                  {paper.title}
                </h4>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {formatAuthors(paper.authors)}
                  {paper.year && ` • ${paper.year}`}
                </p>
                {paper.abstract && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 line-clamp-2">
                    {paper.abstract}
                  </p>
                )}

                {/* Badges */}
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${getSourceBadgeColor(paper.source)}`}
                  >
                    {paper.source.replace('_', ' ')}
                  </span>
                  {paper.pdf_url && (
                    <span className="inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[10px] font-medium bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300">
                      <FileText className="h-2.5 w-2.5" />
                      PDF
                    </span>
                  )}
                  {paper.is_open_access && !paper.pdf_url && (
                    <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
                      Open Access
                    </span>
                  )}
                  {paper.doi && (
                    <a
                      href={`https://doi.org/${paper.doi}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-0.5 text-[10px] text-indigo-600 dark:text-indigo-400 hover:underline"
                    >
                      DOI
                      <ExternalLink className="h-2.5 w-2.5" />
                    </a>
                  )}
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center gap-1.5 pt-2 border-t border-gray-100 dark:border-slate-700">
                {/* Add to Channel */}
                <button
                  onClick={() => handleAddToChannel(paper)}
                  disabled={isProcessing || addedToChannel}
                  className={`flex-1 inline-flex items-center justify-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium transition ${
                    addedToChannel
                      ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-300 cursor-default'
                      : 'bg-indigo-600 text-white hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:opacity-50'
                  }`}
                >
                  {processingPapers[paper.id] === 'channel' ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : addedToChannel ? (
                    <>
                      <FolderPlus className="h-3 w-3" />
                      In Channel
                    </>
                  ) : (
                    <>
                      <FolderPlus className="h-3 w-3" />
                      Channel
                    </>
                  )}
                </button>

                {/* Add to Library */}
                <button
                  onClick={() => handleAddToLibrary(paper)}
                  disabled={isProcessing || addedToLibrary}
                  className={`flex-1 inline-flex items-center justify-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium transition ${
                    addedToLibrary
                      ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-300 cursor-default'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-slate-700 dark:text-gray-200 dark:hover:bg-slate-600 disabled:opacity-50'
                  }`}
                >
                  {processingPapers[paper.id] === 'library' ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : addedToLibrary ? (
                    <>
                      <BookPlus className="h-3 w-3" />
                      In Library
                    </>
                  ) : (
                    <>
                      <BookPlus className="h-3 w-3" />
                      Library
                    </>
                  )}
                </button>

                {/* Dismiss */}
                <button
                  onClick={() => onDismiss(paper.id)}
                  disabled={isProcessing}
                  className="p-1.5 rounded-md text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:text-red-400 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50"
                  title="Dismiss"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
