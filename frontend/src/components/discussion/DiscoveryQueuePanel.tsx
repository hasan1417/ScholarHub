import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Loader2, Search, Sparkles } from 'lucide-react'
import { DiscoveredPaperCard, DiscoveredPaper, IngestionStatus } from './DiscoveredPaperCard'
import { projectDiscussionAPI } from '../../services/api'
import api from '../../services/api'

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

interface DiscoveryQueuePanelProps {
  papers: DiscoveredPaper[]
  query: string
  projectId: string
  isSearching: boolean
  notification: string | null
  onDismiss: (paperId: string) => void
  onDismissAll: () => void
  onClearNotification: () => void
  onClose: () => void
  // External ingestion updates from AI's add_to_library tool
  externalUpdates?: LibraryUpdateItem[]
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
  onClose,
  externalUpdates,
}: DiscoveryQueuePanelProps) {
  const queryClient = useQueryClient()
  const [addedPapers, setAddedPapers] = useState<Set<string>>(new Set())
  const [addingPapers, setAddingPapers] = useState<Set<string>>(new Set())
  const [ingestionStates, setIngestionStates] = useState<Record<string, PaperIngestionState>>({})

  // Apply external updates from AI's add_to_library action
  useEffect(() => {
    if (!externalUpdates || externalUpdates.length === 0) return

    setAddedPapers(prev => {
      const next = new Set(prev)
      for (const update of externalUpdates) {
        const paper = papers[update.index]
        if (paper) next.add(paper.id)
      }
      return next
    })

    setIngestionStates(prev => {
      const next = { ...prev }
      for (const update of externalUpdates) {
        const paper = papers[update.index]
        if (paper) {
          next[paper.id] = {
            referenceId: update.reference_id,
            status: update.ingestion_status,
          }
        }
      }
      return next
    })

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
      setAddingPapers(prev => {
        const next = new Set(prev)
        next.delete(paperId)
        return next
      })

      if (data.success && data.reference_id) {
        setAddedPapers(prev => new Set([...prev, paperId]))

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

        setIngestionStates(prev => ({
          ...prev,
          [paperId]: {
            referenceId: data.reference_id as string,
            status: ingestionStatus,
          },
        }))

        queryClient.invalidateQueries({ queryKey: ['projectReferences', projectId] })
      } else {
        alert(data.message || 'Failed to add reference')
      }
    },
    onError: (error: Error, paper) => {
      setAddingPapers(prev => {
        const next = new Set(prev)
        next.delete(paper.id)
        return next
      })
      alert(error.message || 'Failed to add reference')
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
      setIngestionStates(prev => ({
        ...prev,
        [paperId]: { ...prev[paperId], status: 'uploading' },
      }))
    },
    onSuccess: ({ paperId }) => {
      setIngestionStates(prev => ({
        ...prev,
        [paperId]: { ...prev[paperId], status: 'success' },
      }))
      queryClient.invalidateQueries({ queryKey: ['projectReferences', projectId] })
    },
    onError: (error: Error, { paperId }) => {
      setIngestionStates(prev => ({
        ...prev,
        [paperId]: { ...prev[paperId], status: 'failed' },
      }))
      alert(`Failed to upload PDF: ${error.message}`)
    },
  })

  const handleAdd = (paper: DiscoveredPaper) => {
    setAddingPapers(prev => new Set([...prev, paper.id]))
    addReferenceMutation.mutate(paper)
  }

  const handleUploadPdf = (paperId: string, file: File) => {
    const state = ingestionStates[paperId]
    if (state?.referenceId) {
      uploadPdfMutation.mutate({ referenceId: state.referenceId, file, paperId })
    }
  }

  const handleContinueWithAbstract = (paperId: string) => {
    setIngestionStates(prev => ({
      ...prev,
      [paperId]: { ...prev[paperId], status: 'no_pdf' },
    }))
  }

  // Count statuses for summary
  const addedCount = addedPapers.size
  const successCount = Object.values(ingestionStates).filter(s => s.status === 'success').length
  const failedCount = Object.values(ingestionStates).filter(s => s.status === 'failed').length

  return (
    <div className="flex flex-col h-full bg-white dark:bg-slate-900 border-l border-gray-200 dark:border-slate-700">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-slate-700">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-indigo-500" />
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Paper Discoveries
          </h3>
          {papers.length > 0 && (
            <span className="inline-flex items-center justify-center h-5 min-w-5 px-1.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-300">
              {papers.length}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-slate-700 transition"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Notification banner */}
      {notification && (
        <div className="flex items-center justify-between px-4 py-2 bg-amber-50 dark:bg-amber-900/20 border-b border-amber-200 dark:border-amber-800">
          <p className="text-xs text-amber-700 dark:text-amber-300">{notification}</p>
          <button
            onClick={onClearNotification}
            className="p-0.5 rounded hover:bg-amber-200 dark:hover:bg-amber-800 transition-colors"
          >
            <X className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
          </button>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {isSearching ? (
          <div className="flex flex-col items-center justify-center py-12 px-4">
            <Loader2 className="h-6 w-6 animate-spin text-indigo-500" />
            <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
              Searching for papers...
            </p>
            {query && (
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500 text-center">
                "{query}"
              </p>
            )}
          </div>
        ) : papers.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 px-4">
            <Search className="h-10 w-10 text-gray-300 dark:text-slate-600" />
            <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
              No papers found
            </p>
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500 text-center">
              Ask the AI to search for papers
            </p>
          </div>
        ) : (
          <>
            {/* Query and actions header */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100 dark:border-slate-800">
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {papers.length} paper{papers.length !== 1 ? 's' : ''} for "{query}"
                {addedCount > 0 && (
                  <span className="ml-2 text-gray-400 dark:text-gray-500">
                    ({successCount} with full text{failedCount > 0 && `, ${failedCount} need PDF`})
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
            <div className="p-3 space-y-2">
              {papers.map((paper) => (
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
                  onDismiss={() => onDismiss(paper.id)}
                />
              ))}
            </div>
          </>
        )}
      </div>

      {/* Footer hint */}
      {papers.length > 0 && (
        <div className="px-4 py-2 border-t border-gray-100 dark:border-slate-800">
          <p className="text-[10px] text-gray-400 dark:text-gray-500">
            Click "Add" to add to your library. Papers marked "PDF failed" can have PDFs uploaded manually.
          </p>
        </div>
      )}
    </div>
  )
}
