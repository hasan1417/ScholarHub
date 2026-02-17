import { useState, useCallback, type MutableRefObject } from 'react'
import type { EditorView } from '@codemirror/view'
import { buildApiUrl } from '../../../services/api'
import { useToast } from '../../../hooks/useToast'

interface UseAiTextToolsOptions {
  viewRef: MutableRefObject<EditorView | null>
  readOnly: boolean
  projectId?: string
  onOpenAiChatWithMessage?: (message: string) => void
}

export function useAiTextTools({ viewRef, readOnly, projectId, onOpenAiChatWithMessage }: UseAiTextToolsOptions) {
  const { toast } = useToast()
  const [aiActionLoading, setAiActionLoading] = useState<string | null>(null)

  const getSelectedText = useCallback(() => {
    try {
      const view = viewRef.current
      if (!view) return ''
      const sel = view.state.selection.main
      return view.state.doc.sliceString(sel.from, sel.to)
    } catch {
      return ''
    }
  }, [])

  const replaceSelectedText = useCallback((text: string) => {
    try {
      const view = viewRef.current
      if (!view) return
      const sel = view.state.selection.main
      view.dispatch({
        changes: { from: sel.from, to: sel.to, insert: text || '' }
      })
      view.focus()
    } catch {}
  }, [])

  const handleAiAction = useCallback(async (action: string, tone?: string) => {
    if (readOnly || aiActionLoading) return

    const selectedText = getSelectedText()
    if (!selectedText.trim()) {
      toast.warning('Please select some text first')
      return
    }

    // For explain/summarize/synonyms: redirect to AI chat panel (non-destructive)
    const chatActions = ['explain', 'summarize', 'synonyms']
    if (chatActions.includes(action) && onOpenAiChatWithMessage) {
      const actionLabels: Record<string, string> = {
        explain: 'Explain this text',
        summarize: 'Summarize this text',
        synonyms: 'Suggest synonyms for key terms in this text',
      }
      const prompt = `${actionLabels[action]}:\n\n"${selectedText}"`
      onOpenAiChatWithMessage(prompt)
      return
    }

    // For paraphrase/tone: in-place replacement via API
    const loadingKey = action === 'tone' && tone ? `tone_${tone}` : action
    setAiActionLoading(loadingKey)

    try {
      const payload: any = {
        text: selectedText,
        action: action,
        project_id: projectId,
      }
      if (tone) payload.tone = tone

      const token = localStorage.getItem('access_token')
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (token) headers['Authorization'] = `Bearer ${token}`

      const response = await fetch(buildApiUrl('/ai/text-tools'), {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify(payload),
      })

      if (!response.ok) throw new Error(`Request failed: ${response.status}`)

      const data = await response.json()
      if (data.result) replaceSelectedText(data.result)
    } catch (error) {
      console.error('AI action failed:', error)
      toast.error('Failed to process text. Please try again.')
    } finally {
      setAiActionLoading(null)
    }
  }, [readOnly, getSelectedText, replaceSelectedText, projectId, aiActionLoading, onOpenAiChatWithMessage])

  return {
    aiActionLoading,
    handleAiAction,
  }
}
