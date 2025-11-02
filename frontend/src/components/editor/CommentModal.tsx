import React, { useEffect, useState } from 'react'

interface CommentModalProps {
  open: boolean
  onClose: () => void
  onSubmit: (payload: { text: string; line?: number }) => Promise<void> | void
}

const CommentModal: React.FC<CommentModalProps> = ({ open, onClose, onSubmit }) => {
  const [text, setText] = useState('')
  const [line, setLine] = useState<string>('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setText('')
      setLine('')
      setError(null)
      setSending(false)
    }
  }, [open])

  if (!open) return null

  const submit = async () => {
    const trimmed = (text || '').trim()
    if (!trimmed) { setError('Please enter a comment'); return }
    setSending(true)
    try {
      const ln = line ? parseInt(line, 10) : undefined
      await onSubmit({ text: trimmed, line: (Number.isFinite(ln as any) ? ln : undefined) })
      onClose()
    } catch (e: any) {
      setError(e?.message || 'Failed to send comment')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black bg-opacity-30 flex items-center justify-center" onClick={onClose}>
      <div className="bg-white w-[520px] rounded-lg shadow-xl overflow-hidden" onClick={e=>e.stopPropagation()}>
        <div className="px-4 py-3 border-b flex items-center justify-between">
          <div className="text-base font-semibold">Add Comment</div>
          <button className="text-sm px-2 py-1 border rounded" onClick={onClose}>Close</button>
        </div>
        <div className="p-4 space-y-3">
          {error && <div className="text-sm text-red-700">{error}</div>}
          <div>
            <label className="block text-sm text-gray-700 mb-1">Comment</label>
            <textarea
              className="w-full border border-gray-300 rounded-md p-2 text-sm"
              rows={4}
              placeholder="Type your comment…"
              value={text}
              onChange={e=>setText(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-700 mb-1">Line (optional)</label>
            <input
              type="number"
              className="w-32 border border-gray-300 rounded-md p-1 text-sm"
              placeholder="e.g. 42"
              value={line}
              onChange={e=>setLine(e.target.value)}
              min={1}
            />
          </div>
        </div>
        <div className="px-4 py-3 border-t flex justify-end gap-2">
          <button className="px-3 py-1.5 border rounded" onClick={onClose} disabled={sending}>Cancel</button>
          <button className="px-3 py-1.5 rounded bg-blue-600 text-white disabled:opacity-50" onClick={submit} disabled={sending}>{sending ? 'Sending…' : 'Send'}</button>
        </div>
      </div>
    </div>
  )
}

export default CommentModal

