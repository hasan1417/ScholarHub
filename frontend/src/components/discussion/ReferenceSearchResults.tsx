import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Loader2, Search, AlertCircle } from 'lucide-react'
import { DiscoveredPaperCard, DiscoveredPaper, IngestionStatus } from './DiscoveredPaperCard'
import { projectDiscussionAPI } from '../../services/api'
import api from '../../services/api'
import { useToast } from '../../hooks/useToast'

interface PaperIngestionState {
  referenceId: string
  status: IngestionStatus
}

// External updates from AI's add_to_library action
export interface LibraryUpdateItem {
  index: number
  reference_id: string
  ingestion_status: IngestionStatus
}

interface ReferenceSearchResultsProps {
  papers: DiscoveredPaper[]
  query: string
  projectId: string
  onClose: () => void
  isSearching?: boolean
  // External ingestion updates from AI's add_to_library tool
  externalUpdates?: LibraryUpdateItem[]
  // Callback when a paper is dismissed
  onDismissPaper?: (paperId: string) => void
}

export function ReferenceSearchResults({
  papers,
  query,
  projectId,
  onClose,
  isSearching = false,
  externalUpdates,
  onDismissPaper,
}: ReferenceSearchResultsProps) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [addedPapers, setAddedPapers] = useState<Set<string>>(new Set())
  const [addingPapers, setAddingPapers] = useState<Set<string>>(new Set())
  // Track ingestion status per paper
  const [ingestionStates, setIngestionStates] = useState<Record<string, PaperIngestionState>>({})
  // Track dismissed papers
  const [dismissedPapers, setDismissedPapers] = useState<Set<string>>(new Set())

  const handleDismiss = (paperId: string) => {
    setDismissedPapers(prev => new Set([...prev, paperId]))
    // Also notify parent to remove from discovery queue
    onDismissPaper?.(paperId)
  }

  // Filter out dismissed papers
  const visiblePapers = papers.filter(p => !dismissedPapers.has(p.id))

  // Apply external updates from AI's add_to_library action
  useEffect(() => {
    console.log('[ReferenceSearchResults] externalUpdates received:', externalUpdates)
    if (!externalUpdates || externalUpdates.length === 0) return

    console.log('[ReferenceSearchResults] Processing', externalUpdates.length, 'updates')

    // Use functional updates to avoid stale closure issues
    setAddedPapers(prev => {
      const next = new Set(prev)
      for (const update of externalUpdates) {
        const paper = papers[update.index]
        console.log('[ReferenceSearchResults] Update for index', update.index, '-> paper:', paper?.title)
        if (paper) next.add(paper.id)
      }
      return next
    })

    setIngestionStates(prev => {
      const next = { ...prev }
      for (const update of externalUpdates) {
        const paper = papers[update.index]
        if (paper) {
          console.log('[ReferenceSearchResults] Setting status for', paper.title, '->', update.ingestion_status)
          next[paper.id] = {
            referenceId: update.reference_id,
            status: update.ingestion_status,
          }
        }
      }
      return next
    })

    // Invalidate references to refresh library
    queryClient.invalidateQueries({ queryKey: ['projectReferences', projectId] })
  }, [externalUpdates, papers, projectId, queryClient])

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
      return { data: response.data, paperId: paper.id, paper }
    },
    onSuccess: ({ data, paperId, paper }) => {
      // Remove from adding state
      setAddingPapers((prev) => {
        const next = new Set(prev)
        next.delete(paperId)
        return next
      })

      if (data.success && data.reference_id) {
        setAddedPapers((prev) => new Set([...prev, paperId]))

        // Use the actual ingestion_status from the backend response
        let ingestionStatus: IngestionStatus = 'pending'

        if (data.ingestion_status === 'success') {
          ingestionStatus = 'success'
        } else if (data.ingestion_status === 'failed') {
          ingestionStatus = 'failed'
        } else if (data.ingestion_status === 'no_pdf') {
          ingestionStatus = 'no_pdf'
        } else if (!paper.pdf_url) {
          // Fallback for older responses without ingestion_status
          ingestionStatus = 'no_pdf'
        }

        setIngestionStates((prev) => ({
          ...prev,
          [paperId]: {
            referenceId: data.reference_id as string,
            status: ingestionStatus,
          },
        }))

        // Invalidate references query to refresh the list
        queryClient.invalidateQueries({ queryKey: ['projectReferences', projectId] })
      } else {
        toast.error(data.message || 'Failed to add reference')
      }
    },
    onError: (error: Error, paper) => {
      // Remove from adding state on error
      setAddingPapers((prev) => {
        const next = new Set(prev)
        next.delete(paper.id)
        return next
      })
      toast.error(error.message || 'Failed to add reference')
    },
  })

  const uploadPdfMutation = useMutation({
    mutationFn: async ({ referenceId, file, paperId }: { referenceId: string; file: File; paperId: string }) => {
      const formData = new FormData()
      formData.append('file', file)

      const response = await api.post(`/references/${referenceId}/upload-pdf`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })
      return { data: response.data, paperId }
    },
    onMutate: ({ paperId }) => {
      // Set uploading status
      setIngestionStates((prev) => ({
        ...prev,
        [paperId]: {
          ...prev[paperId],
          status: 'uploading',
        },
      }))
    },
    onSuccess: ({ paperId }) => {
      // Update status to success
      setIngestionStates((prev) => ({
        ...prev,
        [paperId]: {
          ...prev[paperId],
          status: 'success',
        },
      }))
      // Refresh references
      queryClient.invalidateQueries({ queryKey: ['projectReferences', projectId] })
    },
    onError: (error: Error, { paperId }) => {
      // Revert to failed status
      setIngestionStates((prev) => ({
        ...prev,
        [paperId]: {
          ...prev[paperId],
          status: 'failed',
        },
      }))
      toast.error(`Failed to upload PDF: ${error.message}`)
    },
  })

  const handleAdd = (paper: DiscoveredPaper) => {
    setAddingPapers((prev) => new Set([...prev, paper.id]))
    addReferenceMutation.mutate(paper)
  }

  const handleUploadPdf = (paperId: string, file: File) => {
    const state = ingestionStates[paperId]
    if (state?.referenceId) {
      uploadPdfMutation.mutate({ referenceId: state.referenceId, file, paperId })
    }
  }

  const handleContinueWithAbstract = (paperId: string) => {
    // Mark as "no_pdf" - user chose to continue without full text
    setIngestionStates((prev) => ({
      ...prev,
      [paperId]: {
        ...prev[paperId],
        status: 'no_pdf',
      },
    }))
  }

  if (isSearching) {
    return (
      <div className="mt-3 border rounded-lg p-4 bg-gray-50/50 dark:bg-slate-800/30">
        <div className="flex items-center justify-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Searching for papers about "{query}"...</span>
        </div>
      </div>
    )
  }

  if (papers.length === 0) {
    return (
      <div className="mt-3 border rounded-lg p-4 bg-gray-50/50 dark:bg-slate-800/30">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
            <Search className="h-4 w-4" />
            Search Results
          </h4>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-200 dark:hover:text-gray-300 dark:hover:bg-slate-700 transition"
            title="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <AlertCircle className="h-4 w-4" />
          <span>No papers found for "{query}". Try a different search term.</span>
        </div>
      </div>
    )
  }

  // If all papers are dismissed, close the card
  if (visiblePapers.length === 0) {
    return null
  }

  // Count statuses for summary
  const addedCount = addedPapers.size
  const successCount = Object.values(ingestionStates).filter(s => s.status === 'success').length
  const failedCount = Object.values(ingestionStates).filter(s => s.status === 'failed').length

  return (
    <div className="mt-3 border rounded-lg p-3 bg-gray-50/50 dark:bg-slate-800/30">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
          <Search className="h-4 w-4" />
          Found {visiblePapers.length} papers for "{query}"
          {addedCount > 0 && (
            <span className="text-xs font-normal text-gray-500 dark:text-gray-400">
              ({successCount} with full text{failedCount > 0 && `, ${failedCount} need PDF`})
            </span>
          )}
        </h4>
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-200 dark:hover:text-gray-300 dark:hover:bg-slate-700 transition"
          title="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
        {visiblePapers.map((paper) => (
          <DiscoveredPaperCard
            key={paper.id}
            paper={paper}
            onAdd={() => handleAdd(paper)}
            isAdding={addingPapers.has(paper.id)}
            isAdded={addedPapers.has(paper.id)}
            ingestionStatus={ingestionStates[paper.id]?.status}
            referenceId={ingestionStates[paper.id]?.referenceId}
            onUploadPdf={(file) => handleUploadPdf(paper.id, file)}
            onContinueWithAbstract={() => handleContinueWithAbstract(paper.id)}
            onDismiss={() => handleDismiss(paper.id)}
          />
        ))}
      </div>
      <div className="mt-3 pt-2 border-t border-gray-200 dark:border-gray-700">
        <p className="text-[10px] text-gray-400 dark:text-gray-500">
          Click "Add" to add a paper to your project references. Papers marked "PDF failed" can have PDFs uploaded manually.
        </p>
      </div>
    </div>
  )
}
