import React, { useState, useEffect, useCallback } from 'react'
import {
  X,
  Clock,
  Tag,
  RotateCcw,
  Loader2,
  Check,
  Trash2,
  ChevronDown,
  ChevronRight,
  Plus,
  Minus,
  Eye,
  EyeOff,
  RefreshCw,
} from 'lucide-react'
import {
  snapshotsAPI,
  Snapshot,
  SnapshotDiffResponse,
  DiffLine,
} from '../../services/api'

interface HistoryPanelProps {
  paperId: string
  isOpen: boolean
  onClose: () => void
  onRestore: (content: string, snapshotId: string) => void
  currentContent?: string // Current editor content to show unsaved changes
}

// Simple diff function for client-side comparison
function computeSimpleDiff(oldText: string, newText: string): { added: string[], deleted: string[], hasChanges: boolean } {
  const oldLines = (oldText || '').split('\n')
  const newLines = (newText || '').split('\n')

  const oldSet = new Set(oldLines)
  const newSet = new Set(newLines)

  const added = newLines.filter(line => !oldSet.has(line) && line.trim())
  const deleted = oldLines.filter(line => !newSet.has(line) && line.trim())

  return {
    added,
    deleted,
    hasChanges: added.length > 0 || deleted.length > 0
  }
}

const HistoryPanel: React.FC<HistoryPanelProps> = ({
  paperId,
  isOpen,
  onClose,
  onRestore,
  currentContent,
}) => {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [total, setTotal] = useState(0)

  // Expanded snapshot state
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [expandedDiff, setExpandedDiff] = useState<SnapshotDiffResponse | null>(null)
  const [expandedContent, setExpandedContent] = useState<string | null>(null)
  const [loadingExpanded, setLoadingExpanded] = useState(false)
  const [showAllChanges, setShowAllChanges] = useState(false)

  // Unsaved changes state
  const [unsavedChanges, setUnsavedChanges] = useState<{ added: string[], deleted: string[], hasChanges: boolean } | null>(null)
  const [showUnsavedExpanded, setShowUnsavedExpanded] = useState(true)

  // Label editing
  const [editingLabelId, setEditingLabelId] = useState<string | null>(null)
  const [editingLabelValue, setEditingLabelValue] = useState('')

  // Action states
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const loadSnapshots = useCallback(async () => {
    if (!paperId) return
    setLoading(true)
    setError(null)

    try {
      const response = await snapshotsAPI.listSnapshots(paperId, { limit: 50 })
      setSnapshots(response.data.snapshots)
      setTotal(response.data.total)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load history')
    } finally {
      setLoading(false)
    }
  }, [paperId])

  useEffect(() => {
    if (isOpen && paperId) {
      loadSnapshots()
    }
  }, [isOpen, paperId, loadSnapshots])

  const handleRefresh = async () => {
    setRefreshing(true)
    await loadSnapshots()
    setRefreshing(false)
  }

  // Load last snapshot content for unsaved changes comparison
  useEffect(() => {
    const loadLastSnapshotContent = async () => {
      if (snapshots.length > 0 && currentContent !== undefined) {
        try {
          const lastSnapshot = snapshots[0] // First is newest
          const detail = await snapshotsAPI.getSnapshot(paperId, lastSnapshot.id)
          const lastContent = detail.data.materialized_text || ''

          // Compute diff
          const diff = computeSimpleDiff(lastContent, currentContent)
          setUnsavedChanges(diff)
        } catch (err) {
          console.error('Failed to load last snapshot for comparison:', err)
          setUnsavedChanges(null)
        }
      } else {
        setUnsavedChanges(null)
      }
    }

    loadLastSnapshotContent()
  }, [snapshots, currentContent, paperId])

  // Find the previous snapshot for a given snapshot
  const findPreviousSnapshot = (snapshotId: string): Snapshot | null => {
    const index = snapshots.findIndex(s => s.id === snapshotId)
    // Snapshots are sorted newest first, so previous snapshot is at index + 1
    if (index >= 0 && index < snapshots.length - 1) {
      return snapshots[index + 1]
    }
    return null
  }

  const handleExpand = async (snapshot: Snapshot) => {
    if (expandedId === snapshot.id) {
      // Collapse
      setExpandedId(null)
      setExpandedDiff(null)
      setExpandedContent(null)
      setShowAllChanges(false)
      return
    }

    setExpandedId(snapshot.id)
    setLoadingExpanded(true)
    setExpandedDiff(null)
    setExpandedContent(null)
    setShowAllChanges(false)

    try {
      const previousSnapshot = findPreviousSnapshot(snapshot.id)

      if (previousSnapshot) {
        // Load diff between this snapshot and the previous one
        const diffResponse = await snapshotsAPI.getSnapshotDiff(paperId, previousSnapshot.id, snapshot.id)
        setExpandedDiff(diffResponse.data)
      } else {
        // This is the first snapshot, just show its content
        const detailResponse = await snapshotsAPI.getSnapshot(paperId, snapshot.id)
        setExpandedContent(detailResponse.data.materialized_text || '')
      }
    } catch (err: any) {
      console.error('Failed to load expanded content:', err)
    } finally {
      setLoadingExpanded(false)
    }
  }

  const handleRestore = async (snapshot: Snapshot) => {
    setRestoringId(snapshot.id)
    try {
      const detail = await snapshotsAPI.getSnapshot(paperId, snapshot.id)
      const content = detail.data.materialized_text || ''
      await snapshotsAPI.restoreSnapshot(paperId, snapshot.id)
      onRestore(content, snapshot.id)
      loadSnapshots()
    } catch (err: any) {
      console.error('Failed to restore:', err)
    } finally {
      setRestoringId(null)
    }
  }

  const handleUpdateLabel = async (snapshotId: string) => {
    try {
      await snapshotsAPI.updateSnapshotLabel(paperId, snapshotId, editingLabelValue || null)
      setSnapshots((prev) =>
        prev.map((s) => (s.id === snapshotId ? { ...s, label: editingLabelValue || null } : s))
      )
      setEditingLabelId(null)
      setEditingLabelValue('')
    } catch (err: any) {
      console.error('Failed to update label:', err)
    }
  }

  const handleDelete = async (snapshotId: string) => {
    if (!confirm('Are you sure you want to delete this snapshot?')) return
    setDeletingId(snapshotId)
    try {
      await snapshotsAPI.deleteSnapshot(paperId, snapshotId)
      setSnapshots((prev) => prev.filter((s) => s.id !== snapshotId))
      if (expandedId === snapshotId) {
        setExpandedId(null)
        setExpandedDiff(null)
        setExpandedContent(null)
      }
    } catch (err: any) {
      console.error('Failed to delete:', err)
    } finally {
      setDeletingId(null)
    }
  }

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)

    if (date.toDateString() === today.toDateString()) {
      return 'Today'
    } else if (date.toDateString() === yesterday.toDateString()) {
      return 'Yesterday'
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
  }

  const getSnapshotTypeLabel = (type: string) => {
    switch (type) {
      case 'auto':
        return { label: 'Auto', className: 'bg-gray-200 text-gray-700 dark:bg-slate-600 dark:text-slate-200' }
      case 'save':
        return { label: 'Saved', className: 'bg-green-100 text-green-700 dark:bg-green-600/30 dark:text-green-300' }
      case 'manual':
        return { label: 'Manual', className: 'bg-blue-100 text-blue-700 dark:bg-blue-600/30 dark:text-blue-300' }
      case 'restore':
        return { label: 'Restore', className: 'bg-purple-100 text-purple-700 dark:bg-purple-600/30 dark:text-purple-300' }
      default:
        return { label: type, className: 'bg-gray-200 text-gray-700 dark:bg-slate-600 dark:text-slate-200' }
    }
  }

  // Inline diff line component
  const DiffLineItem: React.FC<{ line: DiffLine }> = ({ line }) => {
    const bgClass = line.type === 'added'
      ? 'bg-green-50 dark:bg-green-900/30'
      : line.type === 'deleted'
      ? 'bg-red-50 dark:bg-red-900/30'
      : ''

    const textClass = line.type === 'added'
      ? 'text-green-700 dark:text-green-300'
      : line.type === 'deleted'
      ? 'text-red-700 dark:text-red-300'
      : 'text-gray-600 dark:text-slate-400'

    const icon = line.type === 'added'
      ? <Plus size={12} className="text-green-600 dark:text-green-400" />
      : line.type === 'deleted'
      ? <Minus size={12} className="text-red-600 dark:text-red-400" />
      : null

    return (
      <div className={`flex items-start gap-1 px-2 py-0.5 font-mono text-xs ${bgClass}`}>
        <span className="w-4 flex-shrink-0">{icon}</span>
        <span className={`${textClass} ${line.type === 'deleted' ? 'line-through' : ''}`}>
          {line.content || '\u00A0'}
        </span>
      </div>
    )
  }

  // Group snapshots by date
  const groupedSnapshots = snapshots.reduce((groups, snapshot) => {
    const date = formatDate(snapshot.created_at)
    if (!groups[date]) groups[date] = []
    groups[date].push(snapshot)
    return groups
  }, {} as Record<string, Snapshot[]>)

  if (!isOpen) return null

  return (
    <div className="fixed inset-y-0 right-0 w-[480px] bg-white dark:bg-slate-900 shadow-xl border-l border-gray-200 dark:border-slate-700 z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800">
        <div className="flex items-center gap-2">
          <Clock size={20} className="text-gray-600 dark:text-slate-300" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">Document History</h2>
          <span className="text-sm text-gray-500 dark:text-slate-400">({total})</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-slate-700 transition-colors disabled:opacity-50"
            title="Refresh history"
          >
            <RefreshCw size={18} className={`text-gray-600 dark:text-slate-300 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-slate-700 transition-colors"
          >
            <X size={20} className="text-gray-600 dark:text-slate-300" />
          </button>
        </div>
      </div>

      {/* Hint */}
      <div className="px-4 py-2 bg-gray-50 dark:bg-slate-800/50 border-b border-gray-200 dark:border-slate-700">
        <p className="text-xs text-gray-500 dark:text-slate-400">
          Click on a snapshot to see what changed
        </p>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 size={24} className="animate-spin text-gray-400 dark:text-slate-500" />
          </div>
        ) : error ? (
          <div className="p-4 text-center text-red-600 dark:text-red-400">{error}</div>
        ) : snapshots.length === 0 ? (
          <div className="p-8 text-center text-gray-500 dark:text-slate-400">
            <Clock size={48} className="mx-auto mb-4 text-gray-300 dark:text-slate-600" />
            <p>No history yet</p>
            <p className="text-sm mt-1 text-gray-400 dark:text-slate-500">
              Snapshots are created when you save your document.
            </p>
          </div>
        ) : (
          <div className="p-4 space-y-6">
            {/* Current Unsaved Changes Section */}
            {currentContent !== undefined && unsavedChanges && (
              <div className="mb-4">
                <h3 className="text-xs font-semibold text-gray-500 dark:text-slate-500 uppercase tracking-wider mb-2">
                  Current Changes (Unsaved)
                </h3>
                <div
                  className={`rounded-lg border transition-all ${
                    unsavedChanges.hasChanges
                      ? 'border-amber-400 dark:border-amber-500 bg-amber-50 dark:bg-amber-900/20'
                      : 'border-green-400 dark:border-green-500 bg-green-50 dark:bg-green-900/20'
                  }`}
                >
                  <div
                    className="p-3 cursor-pointer"
                    onClick={() => setShowUnsavedExpanded(!showUnsavedExpanded)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {showUnsavedExpanded ? (
                          <ChevronDown size={16} className="text-amber-600 dark:text-amber-400 flex-shrink-0" />
                        ) : (
                          <ChevronRight size={16} className="text-amber-600 dark:text-amber-400 flex-shrink-0" />
                        )}
                        <span className="text-sm font-medium text-gray-900 dark:text-slate-100">
                          Now
                        </span>
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          unsavedChanges.hasChanges
                            ? 'bg-amber-200 text-amber-800 dark:bg-amber-600/40 dark:text-amber-200'
                            : 'bg-green-200 text-green-800 dark:bg-green-600/40 dark:text-green-200'
                        }`}>
                          {unsavedChanges.hasChanges ? 'Unsaved' : 'No changes'}
                        </span>
                      </div>
                    </div>
                    {unsavedChanges.hasChanges && (
                      <div className="mt-1 ml-6 text-xs text-gray-500 dark:text-slate-400">
                        {unsavedChanges.added.length} line(s) added, {unsavedChanges.deleted.length} line(s) removed since last save
                      </div>
                    )}
                  </div>

                  {/* Expanded unsaved changes */}
                  {showUnsavedExpanded && unsavedChanges.hasChanges && (
                    <div className="border-t border-amber-200 dark:border-amber-700 bg-white dark:bg-slate-800/50">
                      <div className="px-3 py-2 border-b border-gray-200 dark:border-slate-700 flex items-center gap-4 text-xs">
                        <span className="flex items-center gap-1 text-green-600 dark:text-green-400">
                          <Plus size={12} />
                          {unsavedChanges.added.length} added
                        </span>
                        <span className="flex items-center gap-1 text-red-600 dark:text-red-400">
                          <Minus size={12} />
                          {unsavedChanges.deleted.length} deleted
                        </span>
                      </div>
                      <div className="max-h-[200px] overflow-y-auto">
                        {unsavedChanges.deleted.slice(0, 20).map((line, i) => (
                          <div key={`del-${i}`} className="flex items-start gap-1 px-2 py-0.5 font-mono text-xs bg-red-50 dark:bg-red-900/30">
                            <span className="w-4 flex-shrink-0">
                              <Minus size={12} className="text-red-600 dark:text-red-400" />
                            </span>
                            <span className="text-red-700 dark:text-red-300 line-through">
                              {line || '\u00A0'}
                            </span>
                          </div>
                        ))}
                        {unsavedChanges.added.slice(0, 20).map((line, i) => (
                          <div key={`add-${i}`} className="flex items-start gap-1 px-2 py-0.5 font-mono text-xs bg-green-50 dark:bg-green-900/30">
                            <span className="w-4 flex-shrink-0">
                              <Plus size={12} className="text-green-600 dark:text-green-400" />
                            </span>
                            <span className="text-green-700 dark:text-green-300">
                              {line || '\u00A0'}
                            </span>
                          </div>
                        ))}
                        {(unsavedChanges.added.length > 20 || unsavedChanges.deleted.length > 20) && (
                          <div className="px-3 py-2 text-center text-xs text-gray-500 dark:text-slate-400 bg-gray-50 dark:bg-slate-700">
                            ... and more changes
                          </div>
                        )}
                      </div>
                      <div className="px-3 py-2 text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 border-t border-amber-200 dark:border-amber-700">
                        💡 Save your document to create a snapshot of these changes
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
            {Object.entries(groupedSnapshots).map(([date, dateSnapshots]) => (
              <div key={date}>
                <h3 className="text-xs font-semibold text-gray-500 dark:text-slate-500 uppercase tracking-wider mb-2">
                  {date}
                </h3>
                <div className="space-y-2">
                  {dateSnapshots.map((snapshot) => {
                    const typeInfo = getSnapshotTypeLabel(snapshot.snapshot_type)
                    const isExpanded = expandedId === snapshot.id
                    const previousSnapshot = findPreviousSnapshot(snapshot.id)

                    return (
                      <div
                        key={snapshot.id}
                        className={`rounded-lg border transition-all ${
                          isExpanded
                            ? 'border-blue-500 dark:border-blue-400'
                            : 'border-gray-200 dark:border-slate-700 hover:border-gray-300 dark:hover:border-slate-600'
                        }`}
                      >
                        {/* Snapshot Header */}
                        <div
                          className={`p-3 cursor-pointer ${
                            isExpanded ? 'bg-blue-50 dark:bg-blue-900/20' : 'hover:bg-gray-50 dark:hover:bg-slate-800'
                          }`}
                          onClick={() => handleExpand(snapshot)}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex items-center gap-2">
                              {isExpanded ? (
                                <ChevronDown size={16} className="text-blue-500 dark:text-blue-400 flex-shrink-0" />
                              ) : (
                                <ChevronRight size={16} className="text-gray-400 dark:text-slate-500 flex-shrink-0" />
                              )}
                              <span className="text-sm font-medium text-gray-900 dark:text-slate-100">
                                {formatTime(snapshot.created_at)}
                              </span>
                              <span className={`text-xs px-1.5 py-0.5 rounded ${typeInfo.className}`}>
                                {typeInfo.label}
                              </span>
                              <span className="text-xs text-gray-400 dark:text-slate-500">
                                #{snapshot.sequence_number}
                              </span>
                            </div>
                            <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                              <button
                                onClick={() => {
                                  setEditingLabelId(snapshot.id)
                                  setEditingLabelValue(snapshot.label || '')
                                }}
                                className="p-1 rounded hover:bg-gray-200 dark:hover:bg-slate-700 opacity-0 group-hover:opacity-100"
                                title="Edit label"
                              >
                                <Tag size={14} className="text-gray-500 dark:text-slate-400" />
                              </button>
                              <button
                                onClick={() => handleRestore(snapshot)}
                                disabled={restoringId === snapshot.id}
                                className="p-1 rounded hover:bg-gray-200 dark:hover:bg-slate-700 disabled:opacity-50"
                                title="Restore this version"
                              >
                                {restoringId === snapshot.id ? (
                                  <Loader2 size={14} className="animate-spin text-gray-500 dark:text-slate-400" />
                                ) : (
                                  <RotateCcw size={14} className="text-gray-500 dark:text-slate-400" />
                                )}
                              </button>
                              {snapshot.snapshot_type !== 'auto' && (
                                <button
                                  onClick={() => handleDelete(snapshot.id)}
                                  disabled={deletingId === snapshot.id}
                                  className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/50 disabled:opacity-50"
                                  title="Delete snapshot"
                                >
                                  {deletingId === snapshot.id ? (
                                    <Loader2 size={14} className="animate-spin text-red-500 dark:text-red-400" />
                                  ) : (
                                    <Trash2 size={14} className="text-red-500 dark:text-red-400" />
                                  )}
                                </button>
                              )}
                            </div>
                          </div>

                          {/* Label display/edit */}
                          {editingLabelId === snapshot.id ? (
                            <div
                              className="mt-2 flex items-center gap-2 ml-6"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <input
                                type="text"
                                value={editingLabelValue}
                                onChange={(e) => setEditingLabelValue(e.target.value)}
                                placeholder="Add a label..."
                                className="flex-1 text-sm px-2 py-1 bg-white dark:bg-slate-800 border border-gray-300 dark:border-slate-600 rounded text-gray-900 dark:text-slate-200 placeholder-gray-400 dark:placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                                autoFocus
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') handleUpdateLabel(snapshot.id)
                                  if (e.key === 'Escape') {
                                    setEditingLabelId(null)
                                    setEditingLabelValue('')
                                  }
                                }}
                              />
                              <button
                                onClick={() => handleUpdateLabel(snapshot.id)}
                                className="p-1 rounded bg-blue-500 dark:bg-blue-600 text-white hover:bg-blue-600 dark:hover:bg-blue-500"
                              >
                                <Check size={14} />
                              </button>
                              <button
                                onClick={() => {
                                  setEditingLabelId(null)
                                  setEditingLabelValue('')
                                }}
                                className="p-1 rounded bg-gray-200 dark:bg-slate-700 hover:bg-gray-300 dark:hover:bg-slate-600 text-gray-700 dark:text-slate-300"
                              >
                                <X size={14} />
                              </button>
                            </div>
                          ) : snapshot.label ? (
                            <div className="mt-1 ml-6 text-sm text-gray-600 dark:text-slate-400 italic">
                              "{snapshot.label}"
                            </div>
                          ) : null}

                          {/* Size info */}
                          <div className="mt-1 ml-6 text-xs text-gray-400 dark:text-slate-500">
                            {snapshot.text_length?.toLocaleString() || 0} characters
                            {!previousSnapshot && ' (initial version)'}
                          </div>
                        </div>

                        {/* Expanded Content */}
                        {isExpanded && (
                          <div className="border-t border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/50">
                            {loadingExpanded ? (
                              <div className="flex items-center justify-center py-8">
                                <Loader2 size={20} className="animate-spin text-gray-400 dark:text-slate-500" />
                              </div>
                            ) : expandedDiff ? (
                              <div>
                                {/* Diff Stats */}
                                <div className="px-3 py-2 border-b border-gray-200 dark:border-slate-700 flex items-center justify-between text-xs">
                                  <div className="flex items-center gap-4">
                                    <span className="flex items-center gap-1 text-green-600 dark:text-green-400">
                                      <Plus size={12} />
                                      {expandedDiff.stats.additions} added
                                    </span>
                                    <span className="flex items-center gap-1 text-red-600 dark:text-red-400">
                                      <Minus size={12} />
                                      {expandedDiff.stats.deletions} deleted
                                    </span>
                                  </div>
                                  {expandedDiff.diff_lines.filter(l => l.type !== 'unchanged').length > 50 && (
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        setShowAllChanges(!showAllChanges)
                                      }}
                                      className="flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
                                    >
                                      {showAllChanges ? <EyeOff size={12} /> : <Eye size={12} />}
                                      {showAllChanges ? 'Show less' : 'View all'}
                                    </button>
                                  )}
                                </div>
                                {/* Diff Lines */}
                                <div className={showAllChanges ? "max-h-[400px] overflow-y-auto" : "max-h-[250px] overflow-y-auto"}>
                                  {expandedDiff.diff_lines.length === 0 ? (
                                    <div className="px-3 py-4 text-center text-sm text-gray-500 dark:text-slate-400">
                                      No changes in this snapshot
                                    </div>
                                  ) : (
                                    expandedDiff.diff_lines
                                      .filter(line => line.type !== 'unchanged')
                                      .slice(0, showAllChanges ? undefined : 50)
                                      .map((line, i) => (
                                        <DiffLineItem key={i} line={line} />
                                      ))
                                  )}
                                  {!showAllChanges && expandedDiff.diff_lines.filter(l => l.type !== 'unchanged').length > 50 && (
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        setShowAllChanges(true)
                                      }}
                                      className="w-full px-3 py-2 text-center text-xs text-blue-600 dark:text-blue-400 bg-gray-100 dark:bg-slate-700 hover:bg-gray-200 dark:hover:bg-slate-600 transition-colors"
                                    >
                                      View all {expandedDiff.diff_lines.filter(l => l.type !== 'unchanged').length} changes
                                    </button>
                                  )}
                                </div>
                              </div>
                            ) : expandedContent !== null ? (
                              <div>
                                <div className="px-3 py-2 border-b border-gray-200 dark:border-slate-700 flex items-center justify-between text-xs">
                                  <span className="text-gray-500 dark:text-slate-400">Initial document content</span>
                                  {expandedContent.length > 1000 && (
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        setShowAllChanges(!showAllChanges)
                                      }}
                                      className="flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
                                    >
                                      {showAllChanges ? <EyeOff size={12} /> : <Eye size={12} />}
                                      {showAllChanges ? 'Show less' : 'View all'}
                                    </button>
                                  )}
                                </div>
                                <div className={showAllChanges ? "max-h-[400px] overflow-y-auto p-3" : "max-h-[200px] overflow-y-auto p-3"}>
                                  <pre className="text-xs text-gray-700 dark:text-slate-300 font-mono whitespace-pre-wrap">
                                    {showAllChanges ? expandedContent : expandedContent.slice(0, 1000)}
                                    {!showAllChanges && expandedContent.length > 1000 && (
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          setShowAllChanges(true)
                                        }}
                                        className="block mt-2 text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
                                      >
                                        ... View full content ({expandedContent.length.toLocaleString()} characters)
                                      </button>
                                    )}
                                  </pre>
                                </div>
                              </div>
                            ) : (
                              <div className="px-3 py-4 text-center text-sm text-gray-500 dark:text-slate-400">
                                Unable to load changes
                              </div>
                            )}

                            {/* Restore Button */}
                            <div className="px-3 py-2 border-t border-gray-200 dark:border-slate-700">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  handleRestore(snapshot)
                                }}
                                disabled={restoringId === snapshot.id}
                                className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm bg-blue-500 dark:bg-blue-600 text-white rounded hover:bg-blue-600 dark:hover:bg-blue-500 disabled:opacity-50 transition-colors"
                              >
                                {restoringId === snapshot.id ? (
                                  <Loader2 size={14} className="animate-spin" />
                                ) : (
                                  <RotateCcw size={14} />
                                )}
                                Restore this version
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default HistoryPanel
