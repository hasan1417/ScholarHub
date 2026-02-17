import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Loader2, Search } from 'lucide-react'
import { DiscoveredPaperCard, DiscoveredPaper, IngestionStatus } from './DiscoveredPaperCard'
import { projectDiscussionAPI } from '../../services/api'
import api from '../../services/api'
import { useToast } from '../../hooks/useToast'

// Ingestion state for a single paper - managed by parent
export interface PaperIngestionState {
  referenceId: string
  status: IngestionStatus
  isAdding: boolean
}

// Type for ingestion states map
export type IngestionStatesMap = Record<string, PaperIngestionState>

interface DiscoveryQueuePanelProps {
  papers: DiscoveredPaper[]
  query: string
  projectId: string
  isSearching: boolean
  notification: string | null
  onDismiss: (paperId: string) => void
  onDismissAll: () => void
  onClearNotification: () => void
  // Ingestion state - controlled by parent
  ingestionStates: IngestionStatesMap
  onIngestionStateChange: (paperId: string, state: Partial<PaperIngestionState>) => void
}

export function DiscoveryQueuePanel({
  papers,
  query,
  projectId,
  isSearching,
  notification,
  onDismiss,
  onDismissAll,
  onClearNotification,
  ingestionStates,
  onIngestionStateChange,
}: DiscoveryQueuePanelProps) {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const addReferenceMutation = useMutation({
    mutationFn: async (paper: DiscoveredPaper) => {
      const response = await projectDiscussionAPI.executePaperAction(
        projectId,
        'add_reference',
        {
          title: paper.title,
          authors: paper.authors,
          year: paper.year,
          doi: paper.doi,
          url: paper.url,
          abstract: paper.abstract,
          source: paper.source,
          pdf_url: paper.pdf_url,
          is_open_access: paper.is_open_access,
        }
      )
      return { data: response.data, paper }
    },
    onSuccess: ({ data, paper }) => {
      if (data.success && data.reference_id) {
        let ingestionStatus: IngestionStatus = 'pending'
        if (data.ingestion_status === 'success') {
          ingestionStatus = 'success'
        } else if (data.ingestion_status === 'failed') {
          ingestionStatus = 'failed'
        } else if (data.ingestion_status === 'no_pdf') {
          ingestionStatus = 'no_pdf'
        } else if (!paper.pdf_url) {
          ingestionStatus = 'no_pdf'
        }

        onIngestionStateChange(paper.id, {
          referenceId: data.reference_id as string,
          status: ingestionStatus,
          isAdding: false,
        })

        queryClient.invalidateQueries({ queryKey: ['projectReferences', projectId] })
      } else {
        onIngestionStateChange(paper.id, { isAdding: false })
        toast.error(data.message || 'Failed to add reference')
      }
    },
    onError: (error: Error, paper) => {
      onIngestionStateChange(paper.id, { isAdding: false })
      toast.error(error.message || 'Failed to add reference')
    },
  })

  const uploadPdfMutation = useMutation({
    mutationFn: async ({ referenceId, file, paperId }: { referenceId: string; file: File; paperId: string }) => {
      const formData = new FormData()
      formData.append('file', file)
      const response = await api.post(`/references/${referenceId}/upload-pdf`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return { data: response.data, paperId }
    },
    onMutate: ({ paperId }) => {
      onIngestionStateChange(paperId, { status: 'uploading' })
    },
    onSuccess: ({ paperId }) => {
      onIngestionStateChange(paperId, { status: 'success' })
      queryClient.invalidateQueries({ queryKey: ['projectReferences', projectId] })
    },
    onError: (error: Error, { paperId }) => {
      onIngestionStateChange(paperId, { status: 'failed' })
      toast.error(`Failed to upload PDF: ${error.message}`)
    },
  })

  const handleAdd = (paper: DiscoveredPaper) => {
    // Immediately update state to show adding
    onIngestionStateChange(paper.id, {
      referenceId: '',
      status: 'pending',
      isAdding: true,
    })
    addReferenceMutation.mutate(paper)
  }

  const handleUploadPdf = (paperId: string, file: File) => {
    const state = ingestionStates[paperId]
    if (state?.referenceId) {
      uploadPdfMutation.mutate({ referenceId: state.referenceId, file, paperId })
    }
  }

  const handleContinueWithAbstract = (paperId: string) => {
    onIngestionStateChange(paperId, { status: 'no_pdf' })
  }

  // Derived counts from ingestion states
  const addedCount = Object.values(ingestionStates).filter(s => s.referenceId).length
  const successCount = Object.values(ingestionStates).filter(s => s.status === 'success').length
  const failedCount = Object.values(ingestionStates).filter(s => s.status === 'failed' || s.status === 'no_pdf').length

  return (
    <div className="flex flex-col">
      {/* Notification banner */}
      {notification && (
        <div className="flex items-center justify-between px-3 py-1.5 sm:px-4 sm:py-2 bg-amber-50 dark:bg-amber-900/20 border-b border-amber-200 dark:border-amber-800">
          <p className="text-[10px] sm:text-xs text-amber-700 dark:text-amber-300">{notification}</p>
          <button
            onClick={onClearNotification}
            className="p-0.5 rounded hover:bg-amber-200 dark:hover:bg-amber-800 transition-colors flex-shrink-0"
          >
            <X className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-amber-600 dark:text-amber-400" />
          </button>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {isSearching ? (
          <div className="flex flex-col items-center justify-center py-8 sm:py-12 px-4">
            <Loader2 className="h-5 w-5 sm:h-6 sm:w-6 animate-spin text-indigo-500" />
            <p className="mt-2 sm:mt-3 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
              Searching for papers...
            </p>
            {query && (
              <p className="mt-1 text-[10px] sm:text-xs text-gray-400 dark:text-gray-500 text-center max-w-[200px] sm:max-w-none truncate">
                "{query}"
              </p>
            )}
          </div>
        ) : papers.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 sm:py-12 px-4">
            <Search className="h-8 w-8 sm:h-10 sm:w-10 text-gray-300 dark:text-slate-600" />
            <p className="mt-2 sm:mt-3 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
              No papers found
            </p>
            <p className="mt-1 text-[10px] sm:text-xs text-gray-400 dark:text-gray-500 text-center">
              Ask the AI to search for papers
            </p>
          </div>
        ) : (
          <>
            {/* Query and actions header */}
            <div className="flex items-center justify-between px-3 py-1.5 sm:px-4 sm:py-2 border-b border-gray-100 dark:border-slate-800 gap-2">
              <div className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400 min-w-0">
                <span>{papers.length} paper{papers.length !== 1 ? 's' : ''}</span>
                <span className="hidden sm:inline"> for "{query}"</span>
                {addedCount > 0 && (
                  <span className="ml-1 sm:ml-2 text-gray-400 dark:text-gray-500">
                    ({successCount} full{failedCount > 0 && <span className="hidden sm:inline">, {failedCount} need PDF</span>})
                  </span>
                )}
              </div>
              <button
                onClick={onDismissAll}
                className="text-[10px] sm:text-xs text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400 transition-colors flex-shrink-0"
              >
                Clear
              </button>
            </div>

            {/* Papers list */}
            <div className="p-2 sm:p-3 space-y-2">
              {papers.map((paper) => {
                const state = ingestionStates[paper.id]
                return (
                  <DiscoveredPaperCard
                    key={paper.id}
                    paper={paper}
                    onAdd={() => handleAdd(paper)}
                    isAdding={state?.isAdding || false}
                    isAdded={Boolean(state?.referenceId)}
                    ingestionStatus={state?.status}
                    referenceId={state?.referenceId}
                    onUploadPdf={(file) => handleUploadPdf(paper.id, file)}
                    onContinueWithAbstract={() => handleContinueWithAbstract(paper.id)}
                    onDismiss={() => onDismiss(paper.id)}
                  />
                )
              })}
            </div>
          </>
        )}
      </div>

      {/* Footer hint */}
      {papers.length > 0 && (
        <div className="mt-2 sm:mt-3 pt-2 border-t border-gray-200 dark:border-gray-700">
          <p className="text-[9px] sm:text-[10px] text-gray-400 dark:text-gray-500">
            <span className="hidden sm:inline">Click "Add" to add to your library. Papers marked "PDF failed" can have PDFs uploaded manually.</span>
            <span className="sm:hidden">Tap "Add" to add papers to your library.</span>
          </p>
        </div>
      )}
    </div>
  )
}
