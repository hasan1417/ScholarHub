import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import * as Y from 'yjs'
import { EditorState, EditorSelection, type Extension } from '@codemirror/state'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UseTrackChangesOptions {
  yText: Y.Text | null
  enabled: boolean
  userId: string
  userName: string
  userColor?: string
}

export interface TrackedChange {
  id: string
  type: 'insert' | 'delete'
  position: number
  length: number
  text: string
  userId: string
  userName: string
  userColor?: string
  timestamp: number
}

interface TrackMeta {
  userId: string
  userName: string
  userColor?: string
  timestamp: number
}

interface UseTrackChangesReturn {
  trackChangesEnabled: boolean
  trackedChanges: TrackedChange[]
  acceptChange: (changeId: string) => void
  rejectChange: (changeId: string) => void
  acceptAllChanges: () => void
  rejectAllChanges: () => void
  getTransactionFilter: () => Extension
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Generate a stable ID for a tracked change based on its properties. */
function changeId(type: 'insert' | 'delete', pos: number, userId: string, timestamp: number): string {
  return `${type}-${pos}-${userId}-${timestamp}`
}

function parseTrackMeta(raw: string | undefined | null): TrackMeta | null {
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

/**
 * Check whether every character in [from, to) of yText has a trackInsert attribute.
 * If so, the text is a "proposed insertion" and can be directly deleted instead of
 * being marked with trackDelete.
 */
function isRangeAllTrackedInsert(yText: Y.Text, from: number, to: number): boolean {
  if (from >= to) return false
  const delta = yText.toDelta()
  let pos = 0
  for (const op of delta) {
    if (typeof op.insert === 'string') {
      const len = op.insert.length
      const opEnd = pos + len
      // Check overlap with [from, to)
      if (opEnd > from && pos < to) {
        if (!(op.attributes && op.attributes.trackInsert)) return false
      }
      pos += len
      if (pos >= to) break
    }
  }
  return true
}

/**
 * Walk the Y.Text delta and collect all tracked changes.
 */
function collectTrackedChanges(yText: Y.Text): TrackedChange[] {
  const delta = yText.toDelta()
  const changes: TrackedChange[] = []
  let pos = 0

  for (const op of delta) {
    if (typeof op.insert === 'string') {
      const len = op.insert.length
      const attrs = op.attributes || {}

      const insertMeta = parseTrackMeta(attrs.trackInsert)
      if (insertMeta) {
        changes.push({
          id: changeId('insert', pos, insertMeta.userId, insertMeta.timestamp),
          type: 'insert',
          position: pos,
          length: len,
          text: op.insert,
          userId: insertMeta.userId,
          userName: insertMeta.userName,
          userColor: insertMeta.userColor,
          timestamp: insertMeta.timestamp,
        })
      }

      const deleteMeta = parseTrackMeta(attrs.trackDelete)
      if (deleteMeta) {
        changes.push({
          id: changeId('delete', pos, deleteMeta.userId, deleteMeta.timestamp),
          type: 'delete',
          position: pos,
          length: len,
          text: op.insert,
          userId: deleteMeta.userId,
          userName: deleteMeta.userName,
          userColor: deleteMeta.userColor,
          timestamp: deleteMeta.timestamp,
        })
      }

      pos += len
    }
  }

  // Merge adjacent changes of the same type from the same user.
  // Without this, deleting characters one by one creates separate entries
  // in the review panel (one per character) instead of a single word.
  return mergeAdjacentChanges(changes)
}

function mergeAdjacentChanges(changes: TrackedChange[]): TrackedChange[] {
  if (changes.length <= 1) return changes
  const merged: TrackedChange[] = [changes[0]]
  for (let i = 1; i < changes.length; i++) {
    const prev = merged[merged.length - 1]
    const curr = changes[i]
    if (
      curr.type === prev.type &&
      curr.userId === prev.userId &&
      curr.position === prev.position + prev.length
    ) {
      // Merge: extend the previous change
      prev.length += curr.length
      prev.text += curr.text
      // Keep the earlier timestamp
      if (curr.timestamp < prev.timestamp) prev.timestamp = curr.timestamp
      // Regenerate ID for the merged range
      prev.id = changeId(prev.type, prev.position, prev.userId, prev.timestamp)
    } else {
      merged.push(curr)
    }
  }
  return merged
}

/** Build a compact signature string so we can cheaply compare two change lists. */
function changesSignature(changes: TrackedChange[]): string {
  if (changes.length === 0) return ''
  return changes.map(c => `${c.id}:${c.length}`).join('|')
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTrackChanges({
  yText,
  enabled,
  userId,
  userName,
  userColor,
}: UseTrackChangesOptions): UseTrackChangesReturn {
  const [trackedChanges, setTrackedChanges] = useState<TrackedChange[]>([])

  // Ref to latest enabled state so callbacks/observers always see current value
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled

  // Guard flag: when true, we're applying track-changes metadata ourselves
  // and should not re-process those mutations in the observer.
  const applyingTrackRef = useRef(false)

  // Stable refs for user info
  const userRef = useRef({ userId, userName, userColor })
  userRef.current = { userId, userName, userColor }

  // FIX: Use a ref for yText so the transaction filter closure doesn't
  // need yText as a dependency. This keeps the filter extension stable
  // and prevents CM from reconfiguring on every yText change.
  const yTextRef = useRef(yText)
  yTextRef.current = yText

  // Keep a ref to the last changes signature to avoid unnecessary state updates
  const lastSigRef = useRef('')

  // -------------------------------------------------------------------
  // Refresh tracked changes list from Y.Text
  // -------------------------------------------------------------------
  const refreshChanges = useCallback(() => {
    if (!yText) {
      if (lastSigRef.current !== '') {
        lastSigRef.current = ''
        setTrackedChanges([])
      }
      return
    }
    const next = collectTrackedChanges(yText)
    const sig = changesSignature(next)
    // FIX: Skip state update if the tracked changes haven't actually changed.
    // This prevents unnecessary React re-renders and CM decoration dispatches
    // on every keystroke when there are no tracked changes (the common case).
    if (sig === lastSigRef.current) return
    lastSigRef.current = sig
    setTrackedChanges(next)
  }, [yText])

  // Stable ref for refreshChanges so the transaction filter can call it
  const refreshChangesRef = useRef(refreshChanges)
  refreshChangesRef.current = refreshChanges

  // -------------------------------------------------------------------
  // Y.Text observer: mark local insertions with trackInsert attribute
  // -------------------------------------------------------------------
  useEffect(() => {
    if (!yText) return

    const observer = (event: Y.YTextEvent, transaction: Y.Transaction) => {
      // Always refresh the changes list when Y.Text changes
      refreshChanges()

      // Skip our own track-changes metadata operations
      if (applyingTrackRef.current) return
      if (!transaction.local) return
      // Skip marking during history restore operations
      if (transaction.origin === 'history-restore') return

      // When track changes is DISABLED, strip any inherited trackInsert/
      // trackDelete attributes from newly inserted text. Y.js inherits
      // formatting attributes from adjacent text on insert (by design for
      // rich text), which causes new text to appear "tracked" even though
      // track changes is off. We detect and null them out here.
      if (!enabledRef.current) {
        const pendingStrips: Array<{ pos: number; len: number; attrs: Record<string, null> }> = []
        let pos = 0
        for (const delta of event.delta) {
          if (delta.retain != null) {
            pos += delta.retain
          } else if (delta.insert != null) {
            const text = typeof delta.insert === 'string' ? delta.insert : ''
            const len = text.length
            if (len > 0) {
              const attrs = delta.attributes || {}
              const toStrip: Record<string, null> = {}
              let needsStrip = false
              if (attrs.trackInsert) { toStrip.trackInsert = null; needsStrip = true }
              if (attrs.trackDelete) { toStrip.trackDelete = null; needsStrip = true }
              if (needsStrip) {
                pendingStrips.push({ pos, len, attrs: toStrip })
              }
            }
            pos += len
          }
        }
        if (pendingStrips.length > 0) {
          queueMicrotask(() => {
            if (!yText || yText.doc === null) return
            applyingTrackRef.current = true
            try {
              for (const { pos: p, len: l, attrs } of pendingStrips) {
                yText.format(p, l, attrs)
              }
            } finally {
              applyingTrackRef.current = false
            }
            refreshChangesRef.current()
          })
        }
        return
      }

      // Walk the delta to find insertions that need trackInsert marking.
      // IMPORTANT: We must NOT call yText.format() synchronously here.
      // This observer fires during the y-codemirror ViewPlugin's update(),
      // which runs inside CodeMirror's view.update(). If we call format()
      // synchronously, the resulting Yjs transaction cleanup fires yCollab's
      // observer, which calls view.dispatch() while CM is still updating,
      // throwing "Calls to EditorView.update are not allowed while an update
      // is in progress". CM catches this and deactivates the yCollab plugin,
      // breaking realtime sync for all subsequent edits.
      //
      // Instead, we collect insertions to mark and defer the format() calls
      // to a microtask, which runs after CM's view.update() completes.
      const pendingFormats: Array<{ pos: number; len: number }> = []
      let pos = 0
      for (const delta of event.delta) {
        if (delta.retain != null) {
          pos += delta.retain
        } else if (delta.insert != null) {
          const text = typeof delta.insert === 'string' ? delta.insert : ''
          const len = text.length
          if (len > 0) {
            // Check if this insertion already has a trackInsert attribute
            // (e.g., from accept/reject operations or from this very observer)
            const attrs = delta.attributes || {}
            if (!attrs.trackInsert) {
              pendingFormats.push({ pos, len })
            }
          }
          pos += len
        }
        // delete deltas don't advance position (text was removed)
      }

      // Defer format() calls to a microtask so they run after CM's update cycle
      if (pendingFormats.length > 0) {
        const meta = JSON.stringify({
          userId: userRef.current.userId,
          userName: userRef.current.userName,
          userColor: userRef.current.userColor,
          timestamp: Date.now(),
        })
        queueMicrotask(() => {
          if (!yText || yText.doc === null) return
          applyingTrackRef.current = true
          try {
            for (const { pos: p, len: l } of pendingFormats) {
              yText.format(p, l, { trackInsert: meta })
            }
          } finally {
            applyingTrackRef.current = false
          }
          refreshChangesRef.current()
        })
      }
    }

    yText.observe(observer)
    // Initial scan
    refreshChanges()

    return () => {
      yText.unobserve(observer)
    }
  }, [yText, refreshChanges])

  // -------------------------------------------------------------------
  // Transaction filter: intercept deletions in CodeMirror
  // FIX: Uses refs instead of closure captures so the returned Extension
  // is stable (never changes), preventing CM from reconfiguring.
  // -------------------------------------------------------------------
  const getTransactionFilter = useCallback((): Extension => {
    return EditorState.transactionFilter.of((tr) => {
      if (!enabledRef.current || !tr.docChanged) return tr

      // Let through our own accept/reject operations. When acceptChange
      // calls yText.delete(), yCollab dispatches a CM transaction to sync.
      // Without this check, the filter would block that sync transaction,
      // causing Y.js and CM to desync (text deleted in Y.js but still shown in CM).
      if (applyingTrackRef.current) return tr

      // FIX: If yText isn't available yet, don't block — let the
      // transaction through so the user can still edit normally.
      const currentYText = yTextRef.current
      if (!currentYText) return tr

      // Check if there are any pure deletions (no accompanying insertion).
      // Replace operations (select + type) are let through untracked to
      // avoid a race condition between the microtask-deferred trackDelete
      // formatting and the synchronous insertion transaction.
      let hasPureDeletion = false
      tr.changes.iterChanges((fromA, toA, _fromB, _toB, inserted) => {
        if (fromA < toA && inserted.length === 0) {
          hasPureDeletion = true
        }
      })

      // If no pure deletions, let the transaction through
      // (insertions are handled by the Y.Text observer, replace operations
      // pass through as normal edits without track-changes marking)
      if (!hasPureDeletion) return tr

      // Collect deletion ranges (in the original doc coordinates)
      const deletions: Array<{ from: number; to: number }> = []
      tr.changes.iterChanges((fromA, toA, _fromB, _toB, inserted) => {
        if (fromA < toA && inserted.length === 0) {
          deletions.push({ from: fromA, to: toA })
        }
      })

      // If ALL deleted text is tracked inserts (green text), let the
      // deletion through. Tracked inserts are "proposed" text that hasn't
      // been accepted yet — deleting them is effectively rejecting them,
      // which should remove the text outright (like Word / Google Docs).
      const allTrackedInserts = deletions.every(
        del => isRangeAllTrackedInsert(currentYText, del.from, del.to)
      )
      if (allTrackedInserts) return tr

      // For non-tracked-insert text (original document text), block the
      // deletion and mark with trackDelete (shown as strikethrough).
      // Defer format() to a microtask to avoid nested CM dispatch errors.
      const capturedDeletions = deletions.filter(
        del => !isRangeAllTrackedInsert(currentYText, del.from, del.to)
      )
      const meta = JSON.stringify({
        userId: userRef.current.userId,
        userName: userRef.current.userName,
        userColor: userRef.current.userColor,
        timestamp: Date.now(),
      })
      queueMicrotask(() => {
        const yt = yTextRef.current
        if (!yt || yt.doc === null) return
        applyingTrackRef.current = true
        try {
          for (const del of capturedDeletions) {
            yt.format(del.from, del.to - del.from, { trackDelete: meta })
          }
        } finally {
          applyingTrackRef.current = false
        }
        refreshChangesRef.current()
      })

      // Block the deletion but move the cursor so the user isn't stuck.
      // Backspace: cursor is after the deleted char → move left to del.from
      // Delete key: cursor is at del.from → move right to del.to
      // Selection: collapse to del.from
      const del = deletions[0]
      if (!del) return []
      const mainHead = tr.startState.selection.main.head
      const cursorTo = mainHead > del.from ? del.from : del.to
      return { selection: EditorSelection.cursor(cursorTo) }
    })
  }, []) // FIX: No dependencies — uses refs for all mutable state

  // -------------------------------------------------------------------
  // Accept / reject change
  // -------------------------------------------------------------------
  const acceptChange = useCallback((id: string) => {
    if (!yText) return

    const changes = collectTrackedChanges(yText)
    const change = changes.find(c => c.id === id)
    if (!change) return

    applyingTrackRef.current = true
    try {
      if (change.type === 'insert') {
        // Accept insert: remove the trackInsert attribute, text becomes normal
        yText.format(change.position, change.length, { trackInsert: null })
      } else {
        // Accept delete: actually delete the text
        yText.delete(change.position, change.length)
      }
    } finally {
      applyingTrackRef.current = false
    }
    refreshChanges()
  }, [yText, refreshChanges])

  const rejectChange = useCallback((id: string) => {
    if (!yText) return

    const changes = collectTrackedChanges(yText)
    const change = changes.find(c => c.id === id)
    if (!change) return

    applyingTrackRef.current = true
    try {
      if (change.type === 'insert') {
        // Reject insert: delete the text
        yText.delete(change.position, change.length)
      } else {
        // Reject delete: remove the trackDelete attribute, text reappears as normal
        yText.format(change.position, change.length, { trackDelete: null })
      }
    } finally {
      applyingTrackRef.current = false
    }
    refreshChanges()
  }, [yText, refreshChanges])

  // -------------------------------------------------------------------
  // Accept / reject all
  // -------------------------------------------------------------------
  const acceptAllChanges = useCallback(() => {
    if (!yText) return

    applyingTrackRef.current = true
    try {
      // Process in reverse order so position shifts from deletions
      // don't affect earlier changes
      const changes = collectTrackedChanges(yText).sort((a, b) => b.position - a.position)
      for (const change of changes) {
        if (change.type === 'insert') {
          yText.format(change.position, change.length, { trackInsert: null })
        } else {
          yText.delete(change.position, change.length)
        }
      }
    } finally {
      applyingTrackRef.current = false
    }
    refreshChanges()
  }, [yText, refreshChanges])

  const rejectAllChanges = useCallback(() => {
    if (!yText) return

    applyingTrackRef.current = true
    try {
      // Process in reverse order
      const changes = collectTrackedChanges(yText).sort((a, b) => b.position - a.position)
      for (const change of changes) {
        if (change.type === 'insert') {
          yText.delete(change.position, change.length)
        } else {
          yText.format(change.position, change.length, { trackDelete: null })
        }
      }
    } finally {
      applyingTrackRef.current = false
    }
    refreshChanges()
  }, [yText, refreshChanges])

  // -------------------------------------------------------------------
  // Memoized return
  // -------------------------------------------------------------------
  return useMemo(() => ({
    trackChangesEnabled: enabled,
    trackedChanges,
    acceptChange,
    rejectChange,
    acceptAllChanges,
    rejectAllChanges,
    getTransactionFilter,
  }), [enabled, trackedChanges, acceptChange, rejectChange, acceptAllChanges, rejectAllChanges, getTransactionFilter])
}
