import React, { useEffect } from 'react'
import { ArrowLeft, FileText, Loader2, RotateCcw } from 'lucide-react'
import { HistoryTimeline } from './HistoryTimeline'
import { HistoryDiffViewer } from './HistoryDiffViewer'
import type { Snapshot, SnapshotDiffResponse } from '../../../services/api'
import { CURRENT_STATE_ID } from '../hooks/useHistoryView'

interface HistoryViewProps {
  paperId: string
  snapshots: Snapshot[]
  snapshotsLoading: boolean
  selectedSnapshotId: string | null
  onSelectSnapshot: (id: string, rangeFromId?: string) => void
  diffData: SnapshotDiffResponse | null
  diffLoading: boolean
  activeTab: 'all' | 'labels'
  onSetActiveTab: (tab: 'all' | 'labels') => void
  onBack: () => void
  onRestore: (snapshotId: string) => Promise<void>
  restoring: boolean
  onUpdateLabel: (snapshotId: string, label: string | null) => Promise<void>
  selectedRange?: { from: string; to: string } | null
  currentStateId: string
  // Multi-file
  activeHistoryFile: string | null
  onFileSelect: (file: string | null) => void
  snapshotFiles: string[]
}

function formatSnapshotDate(snapshots: Snapshot[], selectedId: string | null): string {
  if (!selectedId) return ''
  if (selectedId === CURRENT_STATE_ID) return 'Current state'
  const snap = snapshots.find(s => s.id === selectedId)
  if (!snap) return ''
  const d = new Date(snap.created_at)
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function countChangesLabel(diffData: SnapshotDiffResponse | null, file: string | null): string {
  if (!diffData) return ''
  const total = diffData.stats.additions + diffData.stats.deletions
  const fname = file || 'main.tex'
  if (total === 0) return `No changes in ${fname}`
  return `${total} change${total !== 1 ? 's' : ''} in ${fname}`
}

export const HistoryView: React.FC<HistoryViewProps> = ({
  snapshots,
  snapshotsLoading,
  selectedSnapshotId,
  onSelectSnapshot,
  diffData,
  diffLoading,
  activeTab,
  onSetActiveTab,
  onBack,
  onRestore,
  restoring,
  onUpdateLabel,
  selectedRange,
  currentStateId,
  activeHistoryFile,
  onFileSelect,
  snapshotFiles,
}) => {
  const dateLabel = formatSnapshotDate(snapshots, selectedSnapshotId)
  const changesLabel = countChangesLabel(diffData, activeHistoryFile)
  const allFiles = ['main.tex', ...snapshotFiles]

  // Escape key exits history mode
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onBack()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onBack])

  return (
    <div className="flex flex-1 min-h-0 flex-col bg-white dark:bg-slate-900">
      {/* Header bar */}
      <div className="relative flex h-10 flex-none items-center border-b border-slate-200 px-3 dark:border-slate-700">
        {/* Left: Back button */}
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 rounded px-2 py-1 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to editor
        </button>

        {/* Center: Date label */}
        {dateLabel && (
          <span className="pointer-events-none absolute inset-x-0 flex justify-center text-xs text-slate-500 dark:text-slate-400">
            Viewing {dateLabel}
          </span>
        )}

        {/* Right: Changes label + Restore button */}
        <div className="ml-auto flex items-center gap-3">
          {changesLabel && !diffLoading && (
            <span className="text-xs text-slate-500 dark:text-slate-400">
              {changesLabel}
            </span>
          )}
          {selectedSnapshotId && selectedSnapshotId !== CURRENT_STATE_ID && snapshots.length > 0 && selectedSnapshotId !== snapshots[0].id && (
            <button
              onClick={() => onRestore(selectedSnapshotId)}
              disabled={restoring}
              className="flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-emerald-700 disabled:opacity-50"
            >
              {restoring ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCcw className="h-3 w-3" />}
              Restore this version
            </button>
          )}
        </div>
      </div>

      {/* Content area */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left: File panel */}
        <div className="flex w-[180px] flex-none flex-col border-r border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900/50">
          <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            Files
          </div>
          {allFiles.map(file => {
            const isActive = (file === 'main.tex' && !activeHistoryFile) || file === activeHistoryFile
            return (
              <button
                key={file}
                onClick={() => onFileSelect(file === 'main.tex' ? null : file)}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors ${
                  isActive
                    ? 'bg-white dark:bg-slate-800'
                    : 'hover:bg-slate-100 dark:hover:bg-slate-800/50'
                }`}
              >
                <FileText className="h-3.5 w-3.5 flex-none text-slate-500 dark:text-slate-400" />
                <span className="flex-1 truncate text-xs font-medium text-slate-700 dark:text-slate-200">
                  {file}
                </span>
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-medium text-amber-700 dark:bg-amber-700/30 dark:text-amber-300">
                  Edited
                </span>
              </button>
            )
          })}
        </div>

        {/* Center: Diff pane */}
        <div className="flex-1 overflow-hidden bg-white dark:bg-slate-900">
          {diffLoading || snapshotsLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
              <span className="ml-2 text-xs text-slate-400">Loading diff...</span>
            </div>
          ) : !diffData ? (
            <div className="flex items-center justify-center py-20 text-xs text-slate-400 dark:text-slate-500">
              Select a version to view changes
            </div>
          ) : diffData.diff_lines.length === 0 ? (
            <div className="flex items-center justify-center py-20 text-xs text-slate-400 dark:text-slate-500">
              No changes in this version
            </div>
          ) : (
            <HistoryDiffViewer diffData={diffData} />
          )}
        </div>

        {/* Right: Timeline sidebar */}
        <div className="w-[280px] flex-none border-l border-slate-200 dark:border-slate-700">
          <HistoryTimeline
            snapshots={snapshots}
            loading={snapshotsLoading}
            selectedSnapshotId={selectedSnapshotId}
            onSelectSnapshot={onSelectSnapshot}
            activeTab={activeTab}
            onSetActiveTab={onSetActiveTab}
            diffStats={diffData ? { additions: diffData.stats.additions, deletions: diffData.stats.deletions } : null}
            onUpdateLabel={onUpdateLabel}
            selectedRange={selectedRange}
            currentStateId={currentStateId}
          />
        </div>
      </div>
    </div>
  )
}
