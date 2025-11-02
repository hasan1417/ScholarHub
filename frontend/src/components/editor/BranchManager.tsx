import React, { useState, useEffect } from 'react'
import { Branch, Commit, branchService } from '../../services/branchService'
import { GitBranch, GitCommit, Plus, Trash2, ChevronDown, ChevronRight } from 'lucide-react'

interface BranchManagerProps {
  paperId: string
  currentBranchId?: string
  onBranchSwitch: (branchId: string) => void
  onContentUpdate: (content: string) => void
  className?: string
}

const BranchManager: React.FC<BranchManagerProps> = ({
  paperId,
  currentBranchId,
  onBranchSwitch,
  onContentUpdate,
  className = ''
}) => {
  const [branches, setBranches] = useState<Branch[]>([])
  const [commits, setCommits] = useState<Commit[]>([])
  const [showCreateBranch, setShowCreateBranch] = useState(false)
  const [newBranchName, setNewBranchName] = useState('')
  const [selectedBranch, setSelectedBranch] = useState<Branch | null>(null)
  const [loading, setLoading] = useState(false)
  const [expandedCommits, setExpandedCommits] = useState<Set<string>>(new Set())

  useEffect(() => {
    loadBranches()
  }, [paperId])

  useEffect(() => {
    if (currentBranchId) {
      loadCommits(currentBranchId)
    }
  }, [currentBranchId])

  const loadBranches = async () => {
    try {
      setLoading(true)
      const branchList = await branchService.getBranches(paperId)
      setBranches(branchList)
      
      // Set current branch if not set
      if (!currentBranchId && branchList.length > 0) {
        const mainBranch = branchList.find(b => b.isMain) || branchList[0]
        setSelectedBranch(mainBranch)
      } else if (currentBranchId) {
        const currentBranch = branchList.find(b => b.id === currentBranchId)
        setSelectedBranch(currentBranch || null)
      }
    } catch (error) {
      console.error('Failed to load branches:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadCommits = async (branchId: string) => {
    try {
      const commitList = await branchService.getCommitHistory(branchId)
      setCommits(commitList)
    } catch (error) {
      console.error('Failed to load commits:', error)
    }
  }

  const handleCreateBranch = async () => {
    if (!newBranchName.trim() || !selectedBranch) return

    try {
      setLoading(true)
      const newBranch = await branchService.createBranch(
        paperId,
        newBranchName.trim(),
        selectedBranch.id
      )
      
      setBranches(prev => [...prev, newBranch])
      setNewBranchName('')
      setShowCreateBranch(false)
      
      // Switch to new branch
      await handleBranchSwitch(newBranch.id)
    } catch (error) {
      console.error('Failed to create branch:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleBranchSwitch = async (branchId: string) => {
    try {
      setLoading(true)
      const result = await branchService.switchBranch(paperId, branchId)
      setSelectedBranch(result.branch)
      onBranchSwitch(branchId)
      onContentUpdate(result.content)
      loadCommits(branchId)
    } catch (error) {
      console.error('Failed to switch branch:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteBranch = async (branchId: string) => {
    if (!confirm('Are you sure you want to delete this branch? This action cannot be undone.')) {
      return
    }

    try {
      setLoading(true)
      await branchService.deleteBranch(branchId)
      setBranches(prev => prev.filter(b => b.id !== branchId))
      
      // If deleted branch was selected, switch to main branch
      if (selectedBranch?.id === branchId) {
        const mainBranch = branches.find(b => b.isMain) || branches[0]
        if (mainBranch) {
          await handleBranchSwitch(mainBranch.id)
        }
      }
    } catch (error) {
      console.error('Failed to delete branch:', error)
    } finally {
      setLoading(false)
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

  const getBranchStatusColor = (branch: Branch) => {
    if (branch.isMain) return 'text-blue-600 bg-blue-100'
    if (branch.status === 'merged') return 'text-green-600 bg-green-100'
    if (branch.status === 'archived') return 'text-gray-600 bg-gray-100'
    return 'text-purple-600 bg-purple-100'
  }

  const toggleCommitExpansion = (commitId: string) => {
    setExpandedCommits(prev => {
      const newSet = new Set(prev)
      if (newSet.has(commitId)) {
        newSet.delete(commitId)
      } else {
        newSet.add(commitId)
      }
      return newSet
    })
  }

  const getChangeIcon = (changeType: string) => {
    switch (changeType) {
      case 'insert':
        return <Plus className="w-3 h-3 text-green-600" />
      case 'delete':
        return <Trash2 className="w-3 h-3 text-red-600" />
      case 'update':
        return <GitCommit className="w-3 h-3 text-blue-600" />
      default:
        return <GitCommit className="w-3 h-3 text-gray-600" />
    }
  }

  const getChangeColor = (changeType: string) => {
    switch (changeType) {
      case 'insert':
        return 'bg-green-50 border-green-200 text-green-800'
      case 'delete':
        return 'bg-red-50 border-red-200 text-red-800'
      case 'update':
        return 'bg-blue-50 border-blue-200 text-blue-800'
      default:
        return 'bg-gray-50 border-gray-200 text-gray-800'
    }
  }

  return (
    <div className={`bg-white rounded-lg shadow-lg ${className}`}>
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-medium text-gray-900 flex items-center">
            <GitBranch className="w-5 h-5 mr-2" />
            Branch Management
          </h3>
          <button
            onClick={() => setShowCreateBranch(true)}
            className="px-3 py-1 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center text-sm"
          >
            <Plus className="w-4 h-4 mr-1" />
            New Branch
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 p-6">
        {/* Branch List */}
        <div>
          <h4 className="text-md font-medium text-gray-900 mb-3">Branches</h4>
          <div className="space-y-2">
            {branches.map((branch) => (
              <div
                key={branch.id}
                className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                  selectedBranch?.id === branch.id
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
                onClick={() => handleBranchSwitch(branch.id)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <GitBranch className="w-4 h-4 mr-2 text-gray-500" />
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="font-medium text-gray-900">{branch.name}</span>
                        {branch.isMain && (
                          <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded">
                            Main
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-600">
                        Last commit: {branch.lastCommitMessage}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className={`px-2 py-1 text-xs rounded ${getBranchStatusColor(branch)}`}>
                      {branch.status}
                    </span>
                    {!branch.isMain && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDeleteBranch(branch.id)
                        }}
                        className="p-1 text-red-600 hover:bg-red-100 rounded"
                        title="Delete branch"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-2 text-xs text-gray-500">
                  Created by {branch.authorName} on {formatDate(branch.createdAt)}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Commit History */}
        <div>
          <h4 className="text-md font-medium text-gray-900 mb-3">Commit History</h4>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {commits.map((commit) => {
              const isExpanded = expandedCommits.has(commit.id)
              return (
                <div key={commit.id} className="border border-gray-200 rounded-lg overflow-hidden">
                  {/* Commit Header */}
                  <div 
                    className="p-3 cursor-pointer hover:bg-gray-50 transition-colors"
                    onClick={() => toggleCommitExpansion(commit.id)}
                  >
                    <div className="flex items-start space-x-3">
                      <div className="w-8 h-8 bg-gray-100 rounded-full flex items-center justify-center">
                        <GitCommit className="w-4 h-4 text-gray-600" />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center space-x-2">
                          <span className="font-medium text-gray-900">{commit.message}</span>
                          {commit.id === commits[0]?.id && (
                            <span className="px-2 py-1 text-xs bg-green-100 text-green-800 rounded">
                              Latest
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-gray-600">
                          {commit.authorName} • {formatDate(commit.timestamp)}
                        </p>
                        <div className="mt-2 flex items-center space-x-4">
                          <span className="text-xs text-gray-500">
                            {commit.changes.length} changes
                          </span>
                          <div className="flex items-center text-xs text-blue-600">
                            {isExpanded ? (
                              <ChevronDown className="w-4 h-4 mr-1" />
                            ) : (
                              <ChevronRight className="w-4 h-4 mr-1" />
                            )}
                            {isExpanded ? 'Hide changes' : 'Show changes'}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  {/* Expanded Changes */}
                  {isExpanded && (
                    <div className="border-t border-gray-200 bg-gray-50 p-4">
                      <h5 className="text-sm font-medium text-gray-900 mb-3">Changes in this commit:</h5>
                      <div className="space-y-2">
                        {commit.changes.map((change, index) => (
                          <div key={index} className={`p-3 rounded border ${getChangeColor(change.type)}`}>
                            <div className="flex items-center space-x-2 mb-2">
                              {getChangeIcon(change.type)}
                              <span className="text-sm font-medium capitalize">
                                {change.type} • {change.section}
                              </span>
                            </div>
                            
                            {change.type === 'insert' && change.newContent && (
                              <div className="text-sm">
                                <div className="text-green-700 font-medium mb-2 flex items-center">
                                  <Plus className="w-3 h-3 mr-1" />
                                  Added Content:
                                </div>
                                <div className="bg-green-50 border-l-4 border-green-400 rounded px-3 py-2 text-sm">
                                  <div className="text-green-800 leading-relaxed">
                                    {change.newContent}
                                  </div>
                                </div>
                              </div>
                            )}
                            
                            {change.type === 'delete' && change.oldContent && (
                              <div className="text-sm">
                                <div className="text-red-700 font-medium mb-2 flex items-center">
                                  <Trash2 className="w-3 h-3 mr-1" />
                                  Removed Content:
                                </div>
                                <div className="bg-red-50 border-l-4 border-red-400 rounded px-3 py-2 text-sm">
                                  <div className="text-red-800 leading-relaxed line-through">
                                    {change.oldContent}
                                  </div>
                                </div>
                              </div>
                            )}
                            
                            {change.type === 'update' && (
                              <div className="text-sm space-y-3">
                                {change.oldContent && (
                                  <div>
                                    <div className="text-red-700 font-medium mb-2 flex items-center">
                                      <Trash2 className="w-3 h-3 mr-1" />
                                      Previous Version:
                                    </div>
                                    <div className="bg-red-50 border-l-4 border-red-400 rounded px-3 py-2">
                                      <div className="text-red-800 leading-relaxed line-through">
                                        {change.oldContent}
                                      </div>
                                    </div>
                                  </div>
                                )}
                                {change.newContent && (
                                  <div>
                                    <div className="text-green-700 font-medium mb-2 flex items-center">
                                      <Plus className="w-3 h-3 mr-1" />
                                      Updated Version:
                                    </div>
                                    <div className="bg-green-50 border-l-4 border-green-400 rounded px-3 py-2">
                                      <div className="text-green-800 leading-relaxed font-medium">
                                        {change.newContent}
                                      </div>
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
            {commits.length === 0 && (
              <div className="text-center text-gray-500 py-8">
                <GitCommit className="w-12 h-12 mx-auto mb-2 text-gray-300" />
                <p>No commits yet</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Create Branch Modal */}
      {showCreateBranch && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-96">
            <h3 className="text-lg font-medium text-gray-900 mb-4">Create New Branch</h3>
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Branch Name
              </label>
              <input
                type="text"
                value={newBranchName}
                onChange={(e) => setNewBranchName(e.target.value)}
                placeholder="e.g., feature/methodology-section"
                className="w-full p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Based on Branch
              </label>
              <select
                value={selectedBranch?.id || ''}
                onChange={(e) => {
                  const branch = branches.find(b => b.id === e.target.value)
                  setSelectedBranch(branch || null)
                }}
                className="w-full p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name} {branch.isMain ? '(Main)' : ''}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center justify-end space-x-3">
              <button
                onClick={() => setShowCreateBranch(false)}
                className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateBranch}
                disabled={!newBranchName.trim() || !selectedBranch || loading}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Creating...' : 'Create Branch'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default BranchManager
