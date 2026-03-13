import { useState, useCallback, useRef, useEffect } from 'react'
import {
  snapshotsAPI,
  type Snapshot,
  type SnapshotDiffResponse,
} from '../../../services/api'

export const CURRENT_STATE_ID = '__current__'

function computeClientDiff(oldText: string, newText: string): { lines: Array<{ type: 'added' | 'deleted' | 'unchanged'; content: string; line_number: number }>; stats: { additions: number; deletions: number; unchanged: number } } {
  const oldLines = oldText.split('\n')
  const newLines = newText.split('\n')
  const result: Array<{ type: 'added' | 'deleted' | 'unchanged'; content: string; line_number: number }> = []
  let additions = 0, deletions = 0, unchanged = 0
  let lineNum = 1

  // Simple LCS-based approach: find common prefix, common suffix, diff the middle
  let i = 0
  while (i < oldLines.length && i < newLines.length && oldLines[i] === newLines[i]) {
    result.push({ type: 'unchanged', content: newLines[i], line_number: lineNum++ })
    unchanged++
    i++
  }
  let j = 0
  while (j < oldLines.length - i && j < newLines.length - i && oldLines[oldLines.length - 1 - j] === newLines[newLines.length - 1 - j]) {
    j++
  }
  // Middle section: old[i..old.length-j] vs new[i..new.length-j]
  for (let k = i; k < oldLines.length - j; k++) {
    result.push({ type: 'deleted', content: oldLines[k], line_number: lineNum++ })
    deletions++
  }
  for (let k = i; k < newLines.length - j; k++) {
    result.push({ type: 'added', content: newLines[k], line_number: lineNum++ })
    additions++
  }
  // Common suffix
  for (let k = oldLines.length - j; k < oldLines.length; k++) {
    const idx = newLines.length - (oldLines.length - k)
    result.push({ type: 'unchanged', content: newLines[idx], line_number: lineNum++ })
    unchanged++
  }

  return { lines: result, stats: { additions, deletions, unchanged } }
}

interface UseHistoryViewOptions {
  paperId: string | undefined
  currentContent: string
}

interface UseHistoryViewReturn {
  historyMode: boolean
  enterHistoryMode: () => void
  exitHistoryMode: () => void

  snapshots: Snapshot[]
  snapshotsLoading: boolean
  snapshotsError: string | null
  refreshSnapshots: () => Promise<void>

  selectedSnapshotId: string | null
  selectedRange: { from: string; to: string } | null
  selectSnapshot: (snapshotId: string, rangeFromId?: string) => void
  diffData: SnapshotDiffResponse | null
  diffLoading: boolean
  CURRENT_STATE_ID: string

  activeTab: 'all' | 'labels'
  setActiveTab: (tab: 'all' | 'labels') => void

  updateLabel: (snapshotId: string, label: string | null) => Promise<void>
  restoreSnapshot: (snapshotId: string) => Promise<string | null>
}

export function useHistoryView({
  paperId,
  currentContent,
}: UseHistoryViewOptions): UseHistoryViewReturn {
  const paperIdRef = useRef(paperId)
  paperIdRef.current = paperId

  const currentContentRef = useRef(currentContent)
  currentContentRef.current = currentContent

  const [historyMode, setHistoryMode] = useState(false)
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [snapshotsLoading, setSnapshotsLoading] = useState(false)
  const [snapshotsError, setSnapshotsError] = useState<string | null>(null)

  const [selectedRange, setSelectedRange] = useState<{ from: string; to: string } | null>(null)
  const selectedSnapshotId = selectedRange?.to ?? null
  const [diffData, setDiffData] = useState<SnapshotDiffResponse | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)

  const [activeTab, setActiveTab] = useState<'all' | 'labels'>('all')

  // Track whether snapshots have been loaded for the current history session
  const loadedRef = useRef(false)

  const refreshSnapshots = useCallback(async () => {
    const pid = paperIdRef.current
    if (!pid) return

    setSnapshotsLoading(true)
    setSnapshotsError(null)
    try {
      const res = await snapshotsAPI.listSnapshots(pid, { limit: 50 })
      setSnapshots(res.data.snapshots)
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to load snapshots'
      setSnapshotsError(msg)
    } finally {
      setSnapshotsLoading(false)
    }
  }, [])

  const selectSnapshot = useCallback(async (snapshotId: string, rangeFromId?: string) => {
    const pid = paperIdRef.current
    if (!pid) return

    setDiffLoading(true)
    setDiffData(null)

    const currentSnapshots = snapshotsRef.current

    try {
      if (rangeFromId) {
        // Comparing two specific snapshots
        setSelectedRange({ from: rangeFromId, to: snapshotId })

        if (snapshotId === CURRENT_STATE_ID) {
          // Diff current content vs a snapshot
          const res = await snapshotsAPI.getSnapshot(pid, rangeFromId)
          const snapshotText = res.data.materialized_text || ''
          const currentText = currentContentRef.current
          const diffLines = computeClientDiff(snapshotText, currentText)
          const snap = currentSnapshots.find(s => s.id === rangeFromId)
          const syntheticDiff: SnapshotDiffResponse = {
            from_snapshot: snap || currentSnapshots[0],
            to_snapshot: { ...(snap || currentSnapshots[0]), id: CURRENT_STATE_ID as any, snapshot_type: 'current' as any, label: 'Current state', sequence_number: 0 },
            diff_lines: diffLines.lines,
            stats: diffLines.stats,
          }
          setDiffData(syntheticDiff)
        } else if (rangeFromId === CURRENT_STATE_ID) {
          // Diff a snapshot vs current content (reversed)
          const res = await snapshotsAPI.getSnapshot(pid, snapshotId)
          const snapshotText = res.data.materialized_text || ''
          const currentText = currentContentRef.current
          const diffLines = computeClientDiff(currentText, snapshotText)
          const snap = currentSnapshots.find(s => s.id === snapshotId)
          const syntheticDiff: SnapshotDiffResponse = {
            from_snapshot: { ...(snap || currentSnapshots[0]), id: CURRENT_STATE_ID as any, snapshot_type: 'current' as any, label: 'Current state', sequence_number: 0 },
            to_snapshot: snap || currentSnapshots[0],
            diff_lines: diffLines.lines,
            stats: diffLines.stats,
          }
          setDiffData(syntheticDiff)
        } else {
          const res = await snapshotsAPI.getFullDiff(pid, rangeFromId, snapshotId)
          setDiffData(res.data)
        }
      } else {
        // Single snapshot selected — diff against its predecessor (existing behavior)

        if (snapshotId === CURRENT_STATE_ID) {
          // Current state vs newest snapshot
          setSelectedRange({ from: '', to: CURRENT_STATE_ID })
          const newest = currentSnapshots[0]
          if (newest) {
            const res = await snapshotsAPI.getSnapshot(pid, newest.id)
            const snapshotText = res.data.materialized_text || ''
            const currentText = currentContentRef.current
            const diffLines = computeClientDiff(snapshotText, currentText)
            setDiffData({
              from_snapshot: newest,
              to_snapshot: { ...newest, id: CURRENT_STATE_ID as any, snapshot_type: 'current' as any, label: 'Current state', sequence_number: 0 },
              diff_lines: diffLines.lines,
              stats: diffLines.stats,
            })
          }
          setDiffLoading(false)
          return
        }

        setSelectedRange({ from: '', to: snapshotId })
        const idx = currentSnapshots.findIndex((s) => s.id === snapshotId)
        if (idx < 0) { setDiffLoading(false); return }

        const previousSnapshot = currentSnapshots[idx + 1]
        if (previousSnapshot) {
          const res = await snapshotsAPI.getFullDiff(pid, previousSnapshot.id, snapshotId)
          setDiffData(res.data)
        } else {
          // Oldest snapshot — synthesize all-added diff
          const res = await snapshotsAPI.getSnapshot(pid, snapshotId)
          const text = res.data.materialized_text || ''
          const lines = text.split('\n')
          const snapshot = currentSnapshots[idx]
          setDiffData({
            from_snapshot: snapshot,
            to_snapshot: snapshot,
            diff_lines: lines.map((line, i) => ({ type: 'added' as const, content: line, line_number: i + 1 })),
            stats: { additions: lines.length, deletions: 0, unchanged: 0 },
          })
        }
      }
    } catch (err) {
      console.warn('[useHistoryView] selectSnapshot failed', err)
      setDiffData(null)
    } finally {
      setDiffLoading(false)
    }
  }, [])

  // Keep a ref of snapshots for use inside selectSnapshot without re-creating it
  const snapshotsRef = useRef(snapshots)
  snapshotsRef.current = snapshots

  const enterHistoryMode = useCallback(() => {
    setHistoryMode(true)
  }, [])

  const exitHistoryMode = useCallback(() => {
    setHistoryMode(false)
    setSelectedRange(null)
    setDiffData(null)
    setDiffLoading(false)
    loadedRef.current = false
  }, [])

  const updateLabel = useCallback(async (snapshotId: string, label: string | null) => {
    const pid = paperIdRef.current
    if (!pid) return

    try {
      const res = await snapshotsAPI.updateSnapshotLabel(pid, snapshotId, label)
      const updated = res.data
      setSnapshots((prev) =>
        prev.map((s) => (s.id === snapshotId ? { ...s, label: updated.label } : s)),
      )
    } catch (err: any) {
      console.warn('[useHistoryView] updateLabel failed', err)
      throw err
    }
  }, [])

  const restoreSnapshot = useCallback(async (snapshotId: string): Promise<string | null> => {
    const pid = paperIdRef.current
    if (!pid) return null

    try {
      // First restore on the backend
      await snapshotsAPI.restoreSnapshot(pid, snapshotId)
      // Then fetch the snapshot content to return to the editor
      const res = await snapshotsAPI.getSnapshot(pid, snapshotId)
      return res.data.materialized_text || null
    } catch (err: any) {
      console.warn('[useHistoryView] restoreSnapshot failed', err)
      return null
    }
  }, [])

  // Auto-load snapshots when entering history mode
  useEffect(() => {
    if (historyMode && !loadedRef.current) {
      loadedRef.current = true
      refreshSnapshots()
    }
  }, [historyMode, refreshSnapshots])

  // Auto-select newest snapshot when snapshots load and none is selected
  useEffect(() => {
    if (historyMode && snapshots.length > 0 && selectedRange === null) {
      selectSnapshot(snapshots[0].id)
    }
  }, [historyMode, snapshots, selectedRange, selectSnapshot])

  return {
    historyMode,
    enterHistoryMode,
    exitHistoryMode,

    snapshots,
    snapshotsLoading,
    snapshotsError,
    refreshSnapshots,

    selectedSnapshotId,
    selectedRange,
    selectSnapshot,
    diffData,
    diffLoading,
    CURRENT_STATE_ID,

    activeTab,
    setActiveTab,

    updateLabel,
    restoreSnapshot,
  }
}
