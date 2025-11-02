import React, { useState, useEffect } from 'react'
import { MergeRequest, Branch, branchService } from '../../services/branchService'
import { GitMerge, GitPullRequest, CheckCircle, XCircle, AlertTriangle, Clock, User } from 'lucide-react'
import VisualDiffTool from './VisualDiffTool'

interface MergeRequestManagerProps {
  paperId: string
  branches: Branch[]
  onMergeComplete: (mergedContent: string) => void
  className?: string
}

const MergeRequestManager: React.FC<MergeRequestManagerProps> = ({
  paperId,
  branches,
  onMergeComplete,
  className = ''
}) => {
  const [mergeRequests, setMergeRequests] = useState<MergeRequest[]>([])
  const [showCreateMR, setShowCreateMR] = useState(false)
  const [selectedMR, setSelectedMR] = useState<MergeRequest | null>(null)
  const [loading, setLoading] = useState(false)
  
  // Create MR form state
  const [sourceBranchId, setSourceBranchId] = useState('')
  const [targetBranchId, setTargetBranchId] = useState('')
  const [mrTitle, setMrTitle] = useState('')
  const [mrDescription, setMrDescription] = useState('')

  useEffect(() => {
    loadMergeRequests()
  }, [paperId])

  const loadMergeRequests = async () => {
    try {
      const requests = await branchService.getMergeRequests(paperId)
      setMergeRequests(requests)
    } catch (error) {
      console.error('Failed to load merge requests:', error)
    }
  }

  const handleCreateMR = async () => {
    if (!sourceBranchId || !targetBranchId || !mrTitle.trim()) return

    try {
      setLoading(true)
      const newMR = await branchService.createMergeRequest(
        sourceBranchId,
        targetBranchId,
        mrTitle.trim(),
        mrDescription.trim()
      )
      
      setMergeRequests(prev => [newMR, ...prev])
      setShowCreateMR(false)
      resetForm()
    } catch (error) {
      console.error('Failed to create merge request:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleMerge = async (mr: MergeRequest) => {
    try {
      setLoading(true)
      const result = await branchService.mergeBranches(
        mr.sourceBranchId,
        mr.targetBranchId,
        'auto'
      )
      
      if (result.success) {
        // Update MR status
        const updatedMRs = mergeRequests.map(m => 
          m.id === mr.id ? { ...m, status: 'merged' as const } : m
        )
        setMergeRequests(updatedMRs)
        
        // Call callback with merged content
        if (result.mergedContent) {
          onMergeComplete(result.mergedContent)
        }
        
        setSelectedMR(null)
      } else if (result.conflicts) {
        // Update MR with conflicts
        const updatedMRs = mergeRequests.map(m => 
          m.id === mr.id ? { ...m, status: 'conflicted' as const, conflicts: result.conflicts } : m
        )
        setMergeRequests(updatedMRs)
        
        // Select MR to show conflicts
        setSelectedMR({ ...mr, status: 'conflicted', conflicts: result.conflicts })
      }
    } catch (error) {
      console.error('Failed to merge branches:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleResolveConflict = async (conflictId: string, resolvedContent: string) => {
    try {
      await branchService.resolveConflict(conflictId, resolvedContent)
      
      // Update conflicts in selected MR
      if (selectedMR?.conflicts) {
        const updatedConflicts = selectedMR.conflicts.map(c => 
          c.id === conflictId ? { ...c, status: 'resolved' as const, resolvedContent } : c
        )
        setSelectedMR({ ...selectedMR, conflicts: updatedConflicts })
      }
      
      // Check if all conflicts are resolved
      if (selectedMR?.conflicts?.every(c => c.status === 'resolved')) {
        // Try to merge again
        await handleMerge(selectedMR)
      }
    } catch (error) {
      console.error('Failed to resolve conflict:', error)
    }
  }

  const handleAutoResolve = async (_conflictId: string, strategy: 'source-wins' | 'target-wins') => {
    try {
      const resolvedConflicts = await branchService.autoMergeStrategy(
        selectedMR?.conflicts || [],
        strategy
      )
      
      // Update conflicts
      if (selectedMR?.conflicts) {
        setSelectedMR({ ...selectedMR, conflicts: resolvedConflicts })
      }
      
      // Check if all conflicts are resolved
      if (resolvedConflicts.every(c => c.status === 'resolved')) {
        await handleMerge(selectedMR!)
      }
    } catch (error) {
      console.error('Failed to auto-resolve conflicts:', error)
    }
  }

  const resetForm = () => {
    setSourceBranchId('')
    setTargetBranchId('')
    setMrTitle('')
    setMrDescription('')
  }

  const getStatusIcon = (status: MergeRequest['status']) => {
    switch (status) {
      case 'open':
        return <Clock className="w-4 h-4 text-blue-500" />
      case 'merged':
        return <CheckCircle className="w-4 h-4 text-green-500" />
      case 'closed':
        return <XCircle className="w-4 h-4 text-red-500" />
      case 'conflicted':
        return <AlertTriangle className="w-4 h-4 text-yellow-500" />
      default:
        return <Clock className="w-4 h-4 text-gray-500" />
    }
  }

  const getStatusColor = (status: MergeRequest['status']) => {
    switch (status) {
      case 'open':
        return 'bg-blue-100 text-blue-800'
      case 'merged':
        return 'bg-green-100 text-green-800'
      case 'closed':
        return 'bg-red-100 text-red-800'
      case 'conflicted':
        return 'bg-yellow-100 text-yellow-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  return (
    <div className={`bg-white rounded-lg shadow-lg ${className}`}>
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-medium text-gray-900 flex items-center">
            <GitPullRequest className="w-5 h-5 mr-2" />
            Merge Requests
          </h3>
          <button
            onClick={() => setShowCreateMR(true)}
            className="px-3 py-1 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center text-sm"
          >
            <GitMerge className="w-4 h-4 mr-1" />
            New Merge Request
          </button>
        </div>
      </div>

      <div className="p-6">
        {/* Merge Requests List */}
        <div className="space-y-4">
          {mergeRequests.map((mr) => (
            <div
              key={mr.id}
              className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                selectedMR?.id === mr.id
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
              onClick={() => setSelectedMR(mr)}
            >
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    {getStatusIcon(mr.status)}
                    <h4 className="font-medium text-gray-900">{mr.title}</h4>
                    <span className={`px-2 py-1 text-xs rounded ${getStatusColor(mr.status)}`}>
                      {mr.status}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mb-2">{mr.description}</p>
                  <div className="flex items-center space-x-4 text-xs text-gray-500">
                    <span className="flex items-center">
                      <User className="w-3 h-3 mr-1" />
                      {mr.authorName}
                    </span>
                    <span>{formatDate(mr.createdAt)}</span>
                    <span>
                      {branches.find(b => b.id === mr.sourceBranchId)?.name} → {branches.find(b => b.id === mr.targetBranchId)?.name}
                    </span>
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  {mr.status === 'open' && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        handleMerge(mr)
                      }}
                      disabled={loading}
                      className="px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                    >
                      Merge
                    </button>
                  )}
                  {mr.status === 'conflicted' && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelectedMR(mr)
                      }}
                      className="px-3 py-1 bg-yellow-600 text-white rounded hover:bg-yellow-700"
                    >
                      Resolve Conflicts
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
          
          {mergeRequests.length === 0 && (
            <div className="text-center text-gray-500 py-8">
              <GitPullRequest className="w-12 h-12 mx-auto mb-2 text-gray-300" />
              <p>No merge requests yet</p>
            </div>
          )}
        </div>

        {/* Conflict Resolution */}
        {selectedMR?.status === 'conflicted' && selectedMR.conflicts && (
          <div className="mt-6">
            <VisualDiffTool
              conflicts={selectedMR.conflicts}
              onResolveConflict={handleResolveConflict}
              onAutoResolve={handleAutoResolve}
            />
          </div>
        )}
      </div>

      {/* Create Merge Request Modal */}
      {showCreateMR && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96">
            <h3 className="text-lg font-medium text-gray-900 mb-4">Create Merge Request</h3>
            
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Source Branch
              </label>
              <select
                value={sourceBranchId}
                onChange={(e) => setSourceBranchId(e.target.value)}
                className="w-full p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">Select source branch</option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name} {branch.isMain ? '(Main)' : ''}
                  </option>
                ))}
              </select>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Target Branch
              </label>
              <select
                value={targetBranchId}
                onChange={(e) => setTargetBranchId(e.target.value)}
                className="w-full p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">Select target branch</option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name} {branch.isMain ? '(Main)' : ''}
                  </option>
                ))}
              </select>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Title
              </label>
              <input
                type="text"
                value={mrTitle}
                onChange={(e) => setMrTitle(e.target.value)}
                placeholder="Brief description of changes"
                className="w-full p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Description
              </label>
              <textarea
                value={mrDescription}
                onChange={(e) => setMrDescription(e.target.value)}
                placeholder="Detailed description of changes..."
                rows={3}
                className="w-full p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div className="flex items-center justify-end space-x-3">
              <button
                onClick={() => {
                  setShowCreateMR(false)
                  resetForm()
                }}
                className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateMR}
                disabled={!sourceBranchId || !targetBranchId || !mrTitle.trim() || loading}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Creating...' : 'Create MR'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default MergeRequestManager
