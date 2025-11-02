import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePapers } from '../../contexts/PapersContext'
import CreatePaperModal from '../../components/projects/CreatePaperModal'
import { referencesAPI } from '../../services/api'

const ResearchPapers: React.FC = () => {
  const navigate = useNavigate()
  const { papers, isLoading, deletePaper, updatePaper, createPaper } = usePapers()
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [paperTypeFilter, setPaperTypeFilter] = useState<string>('all')
  
  // Get unique statuses from papers for dynamic filter options
  const uniqueStatuses = React.useMemo(() => {
    if (!papers) return []
    const statuses = papers.map(p => p.status).filter(Boolean)
    return Array.from(new Set(statuses)).sort()
  }, [papers])



  const [showCreatePaper, setShowCreatePaper] = useState(false)
  const [creating, setCreating] = useState(false)

  const handleCreatePaper = () => {
    setShowCreatePaper(true)
  }

  const handleCreateSubmit = async (paperData: any, selectedReferenceIds: string[] = []) => {
    try {
      setCreating(true)
      const newPaper = await createPaper(paperData)
      for (const refId of selectedReferenceIds || []) {
        try { await referencesAPI.attachToPaper(refId, newPaper.id) } catch {}
      }
      setShowCreatePaper(false)
      navigate(`/papers/${newPaper.id}/edit`)
    } finally {
      setCreating(false)
    }
  }

  const handleViewPaper = (paper: any) => {
    navigate(`/papers/${paper.id}`)
  }

  const handleEditPaper = (paper: any) => {
    navigate(`/papers/${paper.id}`)
  }

  const handleDeletePaper = async (paperId: string) => {
    if (window.confirm('Are you sure you want to delete this research paper?')) {
      try {
        await deletePaper(paperId)
      } catch (error) {
        console.error('Error deleting paper:', error)
        alert('Error deleting paper. Please try again.')
      }
    }
  }

  const handleStatusChange = async (paperId: string, newStatus: string) => {
    try {
      // Normalize the status to ensure consistency
      const normalizedStatus = newStatus.toLowerCase().trim()
      await updatePaper(paperId, { status: normalizedStatus })
    } catch (error) {
      console.error('Error updating paper status:', error)
    }
  }


  // Filter and search papers
  const filteredPapers = papers ? papers.filter(paper => {
    const matchesSearch = paper.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         (paper.abstract && paper.abstract.toLowerCase().includes(searchTerm.toLowerCase()))
    const matchesStatus = statusFilter === 'all' || paper.status === statusFilter
    const matchesType = paperTypeFilter === 'all' || paper.paper_type === paperTypeFilter
    
    return matchesSearch && matchesStatus && matchesType
  }) : []

  const getStatusColor = (status: string) => {
    // Normalize status to handle variations
    const normalizedStatus = status?.toLowerCase().trim() || 'unknown'
    
    switch (normalizedStatus) {
      case 'completed':
      case 'complete':
      case 'finished':
        return 'bg-green-100 text-green-800'
      case 'in_progress':
      case 'in progress':
      case 'progress':
      case 'working':
        return 'bg-yellow-100 text-yellow-800'
      case 'published':
      case 'publish':
        return 'bg-blue-100 text-blue-800'
      case 'draft':
      case 'drafts':
        return 'bg-gray-100 text-gray-800'
      case 'review':
      case 'reviewing':
        return 'bg-purple-100 text-purple-800'
      case 'submitted':
      case 'submit':
        return 'bg-indigo-100 text-indigo-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const getPaperTypeLabel = (type: string) => {
    const typeLabels: { [key: string]: string } = {
      'research': 'Research',
      'review': 'Literature Review',
      'case_study': 'Case Study',
      'methodology': 'Methodology',
      'theoretical': 'Theoretical',
      'experimental': 'Experimental'
    }
    return typeLabels[type] || type
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
          <p className="mt-6 text-lg text-gray-600 font-medium">Loading your research papers...</p>
          <p className="mt-2 text-sm text-gray-500">This may take a moment</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-8">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 tracking-tight">Research Papers</h1>
            <p className="mt-2 text-lg text-gray-600">Manage and organize your research papers</p>
          </div>
          <div className="flex space-x-3">
            <button
              onClick={handleCreatePaper}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-all duration-200 flex items-center shadow-sm hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            >
              <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Create New Paper
            </button>
            {/* Standardize Statuses temporarily removed */}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* Filters and Search */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Search Papers</label>
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search by title or abstract..."
                className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Status Filter</label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              >
                <option value="all">All Statuses ({papers.length})</option>
                {uniqueStatuses.map(status => (
                  <option key={status} value={status}>
                    {status.charAt(0).toUpperCase() + status.slice(1).replace('_', ' ')} ({papers.filter(p => p.status === status).length})
                  </option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Paper Type</label>
              <select
                value={paperTypeFilter}
                onChange={(e) => setPaperTypeFilter(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              >
                <option value="all">All Types</option>
                <option value="research">Research</option>
                <option value="review">Literature Review</option>
                <option value="case_study">Case Study</option>
                <option value="methodology">Methodology</option>
                <option value="theoretical">Theoretical</option>
                <option value="experimental">Experimental</option>
              </select>
            </div>
            
            <div className="flex items-end">
              <button
                onClick={() => {
                  setSearchTerm('')
                  setStatusFilter('all')
                  setPaperTypeFilter('all')
                }}
                className="w-full px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 transition-colors focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-1"
              >
                Clear Filters
              </button>
            </div>
          </div>
        </div>

        {/* Papers Grid */}
        {filteredPapers.length === 0 ? (
          <div className="text-center py-16">
            {papers.length === 0 ? (
              <div className="max-w-md mx-auto">
                <svg className="mx-auto h-16 w-16 text-gray-300 mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <h3 className="text-xl font-semibold text-gray-900 mb-3">No papers yet</h3>
                <p className="text-gray-600 mb-6 text-lg">Get started by creating your first research paper</p>
                <button
                  onClick={handleCreatePaper}
                  className="px-8 py-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-all duration-200 shadow-sm hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 text-lg font-medium"
                >
                  Create Your First Paper
                </button>
              </div>
            ) : (
              <div className="max-w-md mx-auto">
                <svg className="mx-auto h-16 w-16 text-gray-300 mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <h3 className="text-xl font-semibold text-gray-900 mb-3">No papers match your search</h3>
                <p className="text-gray-600 text-lg">Try adjusting your search criteria or filters</p>
              </div>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredPapers.map(paper => (
              <div key={paper.id} className="border border-gray-200 rounded-lg p-6 hover:shadow-lg transition-all duration-200 flex flex-col h-full bg-white hover:border-gray-300">
                <div className="flex justify-between items-start mb-4">
                  <div className="flex-1 mr-3">
                    <h4 className="font-semibold text-gray-900 text-base leading-tight">{paper.title}</h4>
                    {paper.updated_at !== paper.created_at && (
                      <div className="flex items-center mt-1">
                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          <svg className="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                          </svg>
                          Recently Updated
                        </span>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-end space-y-2">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(paper.status)}`}>
                      {paper.status ? paper.status.replace('_', ' ') : 'Unknown'}
                    </span>
                    <span className="text-xs text-gray-500 font-medium">{getPaperTypeLabel(paper.paper_type)}</span>
                  </div>
                </div>
                
                {/* Status Dropdown - Always at the top */}
                <div className="mb-4 p-3 bg-gray-50 rounded-md border border-gray-200">
                  <label className="block text-xs font-medium text-gray-700 mb-2">Update Status:</label>
                  <select
                    value={paper.status}
                    onChange={(e) => handleStatusChange(paper.id, e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors bg-white"
                  >
                    <option value="draft">Draft</option>
                    <option value="in_progress">In Progress</option>
                    <option value="review">Review</option>
                    <option value="submitted">Submitted</option>
                    <option value="completed">Completed</option>
                    <option value="published">Published</option>
                  </select>
                </div>
                
                {paper.abstract && (
                  <p className="text-xs text-gray-600 mb-3 line-clamp-3">{paper.abstract}</p>
                )}
                
                {/* Metadata section - Below abstract */}
                <div className="text-xs text-gray-500 mb-3">
                  <div className="flex items-center space-x-4 mb-2">
                    <span className="flex items-center">
                      <svg className="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                      Created: {new Date(paper.created_at).toLocaleDateString()}
                    </span>
                    {paper.updated_at !== paper.created_at && (
                      <span className="flex items-center text-blue-600">
                        <svg className="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Updated: {new Date(paper.updated_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                  {paper.keywords && (
                    <div className="flex items-center">
                      <svg className="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                      </svg>
                      <span className="line-clamp-1">{paper.keywords}</span>
                    </div>
                  )}
                </div>
                
                <div className="flex space-x-2 mt-auto pt-3 border-t border-gray-100">
                  <button
                    onClick={() => handleViewPaper(paper)}
                    className="flex-1 px-3 py-2 bg-blue-50 text-blue-700 rounded-md text-sm font-medium hover:bg-blue-100 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
                  >
                    View
                  </button>
                  <button
                    onClick={() => handleEditPaper(paper)}
                    className="flex-1 px-3 py-2 bg-green-50 text-green-700 rounded-md text-sm font-medium hover:bg-green-100 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-1"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDeletePaper(paper.id)}
                    className="px-3 py-2 bg-red-50 text-red-700 rounded-md text-sm font-medium hover:bg-red-100 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1"
                    title="Delete paper"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create Paper Modal */}
      <CreatePaperModal
        isOpen={showCreatePaper}
        onClose={() => setShowCreatePaper(false)}
        onSubmit={handleCreateSubmit}
        isLoading={creating}
      />
    </div>
  )
}

export default ResearchPapers
