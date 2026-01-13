import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Loader2, Search, AlertCircle } from 'lucide-react'
import { DiscoveredPaperCard, DiscoveredPaper } from './DiscoveredPaperCard'
import { projectDiscussionAPI } from '../../services/api'

interface ReferenceSearchResultsProps {
  papers: DiscoveredPaper[]
  query: string
  projectId: string
  onClose: () => void
  isSearching?: boolean
}

export function ReferenceSearchResults({
  papers,
  query,
  projectId,
  onClose,
  isSearching = false,
}: ReferenceSearchResultsProps) {
  const queryClient = useQueryClient()
  const [addedPapers, setAddedPapers] = useState<Set<string>>(new Set())
  const [addingPaper, setAddingPaper] = useState<string | null>(null)

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
      return response.data
    },
    onSuccess: (data, paper) => {
      if (data.success) {
        setAddedPapers((prev) => new Set([...prev, paper.id]))
        // Invalidate references query to refresh the list
        queryClient.invalidateQueries({ queryKey: ['projectReferences', projectId] })
      } else {
        alert(data.message || 'Failed to add reference')
      }
    },
    onError: (error: Error) => {
      alert(error.message || 'Failed to add reference')
    },
    onSettled: () => {
      setAddingPaper(null)
    },
  })

  const handleAdd = (paper: DiscoveredPaper) => {
    setAddingPaper(paper.id)
    addReferenceMutation.mutate(paper)
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
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
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

  return (
    <div className="mt-3 border rounded-lg p-3 bg-gray-50/50 dark:bg-slate-800/30">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
          <Search className="h-4 w-4" />
          Found {papers.length} papers for "{query}"
        </h4>
        <button
          type="button"
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
        {papers.map((paper) => (
          <DiscoveredPaperCard
            key={paper.id}
            paper={paper}
            onAdd={() => handleAdd(paper)}
            isAdding={addingPaper === paper.id}
            isAdded={addedPapers.has(paper.id)}
          />
        ))}
      </div>
      <div className="mt-3 pt-2 border-t border-gray-200 dark:border-gray-700">
        <p className="text-[10px] text-gray-400 dark:text-gray-500">
          Click "Add" to add a paper to your project references
        </p>
      </div>
    </div>
  )
}
