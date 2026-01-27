import { useRef, useState } from 'react'
import { Check, Loader2, Plus, ExternalLink, Unlock, AlertTriangle, Upload, FileText, X } from 'lucide-react'

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

export type IngestionStatus = 'pending' | 'success' | 'failed' | 'no_pdf' | 'uploading'

interface DiscoveredPaperCardProps {
  paper: DiscoveredPaper
  onAdd: () => void
  isAdding: boolean
  isAdded: boolean
  // New props for ingestion tracking
  ingestionStatus?: IngestionStatus
  referenceId?: string
  onUploadPdf?: (file: File) => void
  onContinueWithAbstract?: () => void
  onDismiss?: () => void
}

export function DiscoveredPaperCard({
  paper,
  onAdd,
  isAdding,
  isAdded,
  ingestionStatus,
  referenceId: _referenceId,
  onUploadPdf,
  onContinueWithAbstract,
  onDismiss,
}: DiscoveredPaperCardProps) {
  // referenceId is passed for potential future use (e.g., linking to reference details)
  void _referenceId
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [showOptions, setShowOptions] = useState(false)

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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && onUploadPdf) {
      onUploadPdf(file)
      setShowOptions(false)
    }
    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleContinueWithAbstract = () => {
    if (onContinueWithAbstract) {
      onContinueWithAbstract()
      setShowOptions(false)
    }
  }

  // Render the action button based on state
  const renderActionButton = () => {
    // Not yet added - show Add button
    if (!isAdded) {
      return (
        <button
          type="button"
          onClick={onAdd}
          disabled={isAdding}
          className="shrink-0 inline-flex items-center gap-1 rounded-md px-2 py-1 sm:px-2.5 sm:py-1.5 text-[10px] sm:text-xs font-medium transition bg-indigo-600 text-white hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 disabled:bg-indigo-300 dark:disabled:bg-indigo-500/40"
        >
          {isAdding ? (
            <Loader2 className="h-2.5 w-2.5 sm:h-3 sm:w-3 animate-spin" />
          ) : (
            <>
              <Plus className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
              Add
            </>
          )}
        </button>
      )
    }

    // Added - show status based on ingestion result
    switch (ingestionStatus) {
      case 'uploading':
        return (
          <div className="shrink-0 inline-flex items-center gap-1 rounded-md px-2 py-1 sm:px-2.5 sm:py-1.5 text-[10px] sm:text-xs font-medium bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300">
            <Loader2 className="h-2.5 w-2.5 sm:h-3 sm:w-3 animate-spin" />
            <span className="hidden sm:inline">Uploading...</span>
            <span className="sm:hidden">...</span>
          </div>
        )

      case 'success':
        return (
          <div className="shrink-0 inline-flex items-center gap-1 rounded-md px-2 py-1 sm:px-2.5 sm:py-1.5 text-[10px] sm:text-xs font-medium bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-300">
            <Check className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
            <span className="hidden sm:inline">Full text</span>
            <span className="sm:hidden">Full</span>
          </div>
        )

      case 'failed':
        return (
          <div className="shrink-0 relative">
            <button
              type="button"
              onClick={() => setShowOptions(!showOptions)}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 sm:px-2.5 sm:py-1.5 text-[10px] sm:text-xs font-medium bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/50 transition"
            >
              <AlertTriangle className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
              <span className="hidden sm:inline">PDF failed</span>
              <span className="sm:hidden">Failed</span>
            </button>
            {showOptions && (
              <div className="absolute right-0 top-full mt-1 z-10 w-40 sm:w-48 rounded-md bg-white dark:bg-slate-800 shadow-lg ring-1 ring-black ring-opacity-5 py-1">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full flex items-center gap-2 px-2.5 py-1.5 sm:px-3 sm:py-2 text-[10px] sm:text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-slate-700"
                >
                  <Upload className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
                  Upload PDF
                </button>
                <button
                  type="button"
                  onClick={handleContinueWithAbstract}
                  className="w-full flex items-center gap-2 px-2.5 py-1.5 sm:px-3 sm:py-2 text-[10px] sm:text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-slate-700"
                >
                  <FileText className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
                  Use abstract
                </button>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileChange}
              className="hidden"
            />
          </div>
        )

      case 'no_pdf':
        return (
          <div className="shrink-0 flex items-center gap-1.5 sm:gap-2">
            <span className="hidden sm:inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium bg-gray-50 text-gray-500 dark:bg-gray-800/50 dark:text-gray-400">
              <FileText className="h-3 w-3" />
              Abstract only
            </span>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] sm:text-xs font-medium bg-indigo-50 text-indigo-600 hover:bg-indigo-100 dark:bg-indigo-900/30 dark:text-indigo-300 dark:hover:bg-indigo-900/50 transition"
            >
              <Upload className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
              <span className="hidden sm:inline">Upload PDF</span>
              <span className="sm:hidden">PDF</span>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileChange}
              className="hidden"
            />
          </div>
        )

      default:
        // Pending or just added
        return (
          <div className="shrink-0 inline-flex items-center gap-1 rounded-md px-2 py-1 sm:px-2.5 sm:py-1.5 text-[10px] sm:text-xs font-medium bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-300">
            <Check className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
            Added
          </div>
        )
    }
  }

  return (
    <div className={`border rounded-lg p-2.5 sm:p-3 bg-white dark:bg-slate-800/60 hover:border-indigo-300 dark:hover:border-indigo-500/50 transition-colors ${
      ingestionStatus === 'failed' ? 'border-amber-200 dark:border-amber-500/30' : ''
    }`}>
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-2 sm:gap-3">
        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-xs sm:text-sm leading-tight line-clamp-2 text-gray-900 dark:text-gray-100">
            {paper.title}
          </h4>
          <p className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400 mt-0.5 sm:mt-1">
            {formatAuthors()}
            {paper.year && ` • ${paper.year}`}
            {paper.journal && <span className="hidden sm:inline italic"> • {paper.journal}</span>}
          </p>
          {paper.abstract && (
            <p className="hidden sm:block text-xs text-gray-500 dark:text-gray-400 mt-1.5 line-clamp-2">
              {paper.abstract}
            </p>
          )}
          <div className="flex items-center gap-1.5 sm:gap-2 mt-1.5 sm:mt-2 flex-wrap">
            <span
              className={`inline-flex items-center rounded-full px-1.5 sm:px-2 py-0.5 text-[9px] sm:text-[10px] font-medium ${getSourceBadgeColor(paper.source)}`}
            >
              {paper.source.replace('_', ' ')}
            </span>
            {paper.is_open_access && (
              <span
                className="inline-flex items-center gap-0.5 rounded-full px-1.5 sm:px-2 py-0.5 text-[9px] sm:text-[10px] font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                title="Open Access - PDF can be automatically ingested"
              >
                <Unlock className="h-2 w-2 sm:h-2.5 sm:w-2.5" />
                <span className="hidden sm:inline">Open access</span>
                <span className="sm:hidden">OA</span>
              </span>
            )}
            {paper.doi && (
              <a
                href={`https://doi.org/${paper.doi}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 text-[9px] sm:text-[10px] text-indigo-600 dark:text-indigo-400 hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                DOI
                <ExternalLink className="h-2 w-2 sm:h-2.5 sm:w-2.5" />
              </a>
            )}
            {paper.url && !paper.doi && (
              <a
                href={paper.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 text-[9px] sm:text-[10px] text-indigo-600 dark:text-indigo-400 hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                Link
                <ExternalLink className="h-2 w-2 sm:h-2.5 sm:w-2.5" />
              </a>
            )}
          </div>
        </div>
        <div className="shrink-0 flex items-center gap-1.5 sm:gap-2 self-end sm:self-start">
          {renderActionButton()}
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="p-1 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-slate-700 transition"
              title="Dismiss"
            >
              <X className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
