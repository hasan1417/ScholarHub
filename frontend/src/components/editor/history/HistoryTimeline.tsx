import React, { useState, useRef, useEffect } from 'react'
import { Clock, GitCompareArrows, Loader2, Tag } from 'lucide-react'
import type { Snapshot } from '../../../services/api'

interface HistoryTimelineProps {
  snapshots: Snapshot[]
  loading: boolean
  selectedSnapshotId: string | null
  onSelectSnapshot: (id: string, rangeFromId?: string) => void
  activeTab: 'all' | 'labels'
  onSetActiveTab: (tab: 'all' | 'labels') => void
  diffStats?: { additions: number; deletions: number } | null
  onUpdateLabel: (snapshotId: string, label: string | null) => Promise<void>
  selectedRange?: { from: string; to: string } | null
  currentStateId: string
}

function getTypeBadge(type: string) {
  switch (type) {
    case 'auto':
      return { label: 'Auto', cls: 'bg-slate-200 text-slate-600 dark:bg-slate-600 dark:text-slate-200' }
    case 'save':
      return { label: 'Saved', cls: 'bg-green-100 text-green-700 dark:bg-green-600/30 dark:text-green-300' }
    case 'manual':
      return { label: 'Manual', cls: 'bg-blue-100 text-blue-700 dark:bg-blue-600/30 dark:text-blue-300' }
    case 'restore':
      return { label: 'Restore', cls: 'bg-purple-100 text-purple-700 dark:bg-purple-600/30 dark:text-purple-300' }
    default:
      return { label: type, cls: 'bg-slate-200 text-slate-600' }
  }
}

function groupByDate(snapshots: Snapshot[]): Map<string, Snapshot[]> {
  const groups = new Map<string, Snapshot[]>()
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)

  for (const s of snapshots) {
    const d = new Date(s.created_at)
    let key: string
    if (d.toDateString() === today.toDateString()) key = 'Today'
    else if (d.toDateString() === yesterday.toDateString()) key = 'Yesterday'
    else key = d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })

    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(s)
  }
  return groups
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

export const HistoryTimeline: React.FC<HistoryTimelineProps> = ({
  snapshots,
  loading,
  selectedSnapshotId,
  onSelectSnapshot,
  activeTab,
  onSetActiveTab,
  diffStats,
  onUpdateLabel,
  selectedRange,
  currentStateId,
}) => {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const editInputRef = useRef<HTMLInputElement>(null)

  // Compare mode: user clicks two snapshots to compare
  const [compareMode, setCompareMode] = useState(false)
  const [compareFrom, setCompareFrom] = useState<string | null>(null)

  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus()
    }
  }, [editingId])
  const filtered = activeTab === 'labels'
    ? snapshots.filter(s => s.label != null && s.label !== '')
    : snapshots

  const grouped = groupByDate(filtered)

  return (
    <div className="flex h-full flex-col bg-slate-50 dark:bg-slate-850 dark:bg-slate-900/50">
      {/* Tab bar */}
      <div className="flex-none px-3 pt-3 pb-2">
        <div className="flex rounded-lg bg-slate-200 p-0.5 dark:bg-slate-700">
          <button
            className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              activeTab === 'all'
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white'
            }`}
            onClick={() => onSetActiveTab('all')}
          >
            All history
          </button>
          <button
            className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              activeTab === 'labels'
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white'
            }`}
            onClick={() => onSetActiveTab('labels')}
          >
            <Tag className="mr-1 inline-block h-3 w-3" />
            Labels
          </button>
        </div>
      </div>

      {/* Diff stats summary */}
      {diffStats && (
        <div className="flex-none border-b border-slate-200 px-3 py-1.5 text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400">
          <span className="text-green-600 dark:text-green-400">+{diffStats.additions}</span>
          {' / '}
          <span className="text-red-500 dark:text-red-400">-{diffStats.deletions}</span>
          {' lines changed'}
        </div>
      )}

      {/* Compare mode toggle */}
      <div className="flex-none border-b border-slate-200 px-3 py-1.5 dark:border-slate-700">
        <button
          onClick={() => { setCompareMode(prev => !prev); setCompareFrom(null) }}
          className={`flex w-full items-center justify-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-colors ${
            compareMode
              ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-600/20 dark:text-indigo-300'
              : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200'
          }`}
        >
          <GitCompareArrows className="h-3.5 w-3.5" />
          {compareMode
            ? compareFrom ? 'Now select the second version' : 'Select the first version'
            : 'Compare versions'}
        </button>
      </div>

      {/* Snapshot list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-4 py-8 text-center text-xs text-slate-400 dark:text-slate-500">
            {activeTab === 'labels' ? 'No labelled versions yet' : 'No history available'}
          </div>
        ) : (
          <>
            {/* Current state entry — only in "All history" tab */}
            {activeTab === 'all' && filtered.length > 0 && (
              <button
                onClick={() => onSelectSnapshot(currentStateId)}
                className={`group w-full border-l-2 px-3 py-2 text-left transition-colors ${
                  selectedSnapshotId === currentStateId
                    ? 'border-l-emerald-500 bg-emerald-50 dark:bg-emerald-900/20'
                    : 'border-l-transparent hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
              >
                <div className="flex items-center gap-2">
                  <div className="h-2.5 w-2.5 flex-none rounded-full bg-emerald-500" />
                  <span className="text-xs font-medium text-slate-700 dark:text-slate-200">
                    Current state
                  </span>
                </div>
              </button>
            )}
            {Array.from(grouped.entries()).map(([dateLabel, items]) => (
            <div key={dateLabel}>
              {/* Date group header */}
              <div className="sticky top-0 z-10 bg-slate-100/90 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500 backdrop-blur dark:bg-slate-800/90 dark:text-slate-400">
                {dateLabel}
              </div>
              {/* Entries */}
              {items.map(snap => {
                const isSelected = snap.id === selectedSnapshotId
                const isInRange = selectedRange && (snap.id === selectedRange.from || snap.id === selectedRange.to)
                const isCompareFrom = compareMode && snap.id === compareFrom
                const badge = getTypeBadge(snap.snapshot_type)

                return (
                  <button
                    key={snap.id}
                    onClick={(e) => {
                      if (compareMode) {
                        if (!compareFrom) {
                          setCompareFrom(snap.id)
                        } else if (compareFrom !== snap.id) {
                          onSelectSnapshot(snap.id, compareFrom)
                          setCompareMode(false)
                          setCompareFrom(null)
                        }
                      } else if (e.shiftKey && selectedSnapshotId && selectedSnapshotId !== snap.id) {
                        onSelectSnapshot(snap.id, selectedSnapshotId)
                      } else {
                        onSelectSnapshot(snap.id)
                      }
                    }}
                    className={`group w-full border-l-2 px-3 py-2 text-left transition-colors ${
                      isCompareFrom
                        ? 'border-l-indigo-500 bg-indigo-50 dark:bg-indigo-900/20'
                        : isSelected || isInRange
                          ? 'border-l-emerald-500 bg-emerald-50 dark:bg-emerald-900/20'
                          : 'border-l-transparent hover:bg-slate-100 dark:hover:bg-slate-800'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Clock className="h-3 w-3 flex-none text-slate-400 dark:text-slate-500" />
                      <span className="text-xs font-medium text-slate-700 dark:text-slate-200">
                        {formatTime(snap.created_at)}
                      </span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${badge.cls}`}>
                        {badge.label}
                      </span>
                      <span className="ml-auto text-[10px] text-slate-400 dark:text-slate-500">
                        #{snap.sequence_number}
                      </span>
                    </div>
                    {/* Label area */}
                    {editingId === snap.id ? (
                      <div className="mt-1 pl-5">
                        <input
                          ref={editInputRef}
                          value={editValue}
                          onChange={e => setEditValue(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') {
                              e.preventDefault()
                              onUpdateLabel(snap.id, editValue.trim() || null)
                              setEditingId(null)
                            }
                            if (e.key === 'Escape') {
                              setEditingId(null)
                            }
                          }}
                          onBlur={() => {
                            onUpdateLabel(snap.id, editValue.trim() || null)
                            setEditingId(null)
                          }}
                          placeholder="Version label..."
                          className="w-full rounded border border-emerald-400 bg-white px-1.5 py-0.5 text-[11px] text-slate-700 outline-none focus:ring-1 focus:ring-emerald-400 dark:border-emerald-500 dark:bg-slate-800 dark:text-slate-200"
                          autoFocus
                        />
                      </div>
                    ) : snap.label ? (
                      <div
                        className="mt-1 cursor-pointer truncate pl-5 text-[11px] italic text-slate-500 hover:text-emerald-600 dark:text-slate-400 dark:hover:text-emerald-400"
                        onClick={e => { e.stopPropagation(); setEditingId(snap.id); setEditValue(snap.label || '') }}
                      >
                        "{snap.label}"
                      </div>
                    ) : (
                      <div
                        className="mt-1 cursor-pointer pl-5 text-[10px] text-slate-300 opacity-0 transition-opacity group-hover:opacity-100 hover:text-emerald-500 dark:text-slate-600 dark:hover:text-emerald-400"
                        onClick={e => { e.stopPropagation(); setEditingId(snap.id); setEditValue('') }}
                      >
                        + Add label
                      </div>
                    )}
                    {snap.text_length != null && (
                      <div className="mt-0.5 pl-5 text-[10px] text-slate-400 dark:text-slate-500">
                        {snap.text_length.toLocaleString()} characters
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          ))}
          </>
        )}
      </div>
    </div>
  )
}
