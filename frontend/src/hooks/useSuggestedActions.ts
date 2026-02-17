import { useState, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { DiscussionAssistantSuggestedAction } from '../types'
import { projectDiscussionAPI } from '../services/api'
import { getProjectUrlId } from '../utils/urlId'
import { useToast } from './useToast'
import type { AssistantExchange } from './useAssistantChat'

export function useSuggestedActions({
  projectId,
  project,
  activeChannelId,
  markActionApplied,
}: {
  projectId: string
  project: { id: string; slug?: string | null; short_id?: string | null }
  activeChannelId: string | null
  markActionApplied: (exchangeId: string, actionKey: string) => void
}) {
  const { toast } = useToast()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Paper creation dialog state
  const [paperCreationDialog, setPaperCreationDialog] = useState<{
    open: boolean
    exchangeId: string
    actionIndex: number
    suggestedTitle: string
    suggestedType: string
    suggestedMode: string
    suggestedAbstract: string
    suggestedKeywords: string[]
  } | null>(null)

  // Paper form state
  const [paperFormData, setPaperFormData] = useState({
    title: '',
    paperType: 'research',
    authoringMode: 'latex',
    abstract: '',
    keywords: [] as string[],
    objectives: [] as string[],
  })
  const [keywordInput, setKeywordInput] = useState('')

  // Paper action mutation
  const paperActionMutation = useMutation({
    mutationFn: async ({
      actionType,
      payload,
    }: {
      actionType: string
      payload: Record<string, unknown>
    }) => {
      const response = await projectDiscussionAPI.executePaperAction(projectId, actionType, payload)
      return response.data
    },
    onSuccess: (data) => {
      if (data.paper_id) {
        queryClient.invalidateQueries({ queryKey: ['papers', projectId] })
        queryClient.invalidateQueries({ queryKey: ['paper', data.paper_id] })
      }
    },
    onError: (error) => {
      console.error('Paper action failed:', error)
      toast.error('Failed to perform paper action. Please try again.')
    },
  })

  const handleAddKeyword = useCallback(() => {
    const kw = keywordInput.trim()
    if (kw && !paperFormData.keywords.includes(kw)) {
      setPaperFormData((prev) => ({ ...prev, keywords: [...prev.keywords, kw] }))
    }
    setKeywordInput('')
  }, [keywordInput, paperFormData.keywords])

  const handleRemoveKeyword = useCallback((keyword: string) => {
    setPaperFormData((prev) => ({
      ...prev,
      keywords: prev.keywords.filter((k) => k !== keyword),
    }))
  }, [])

  const handleToggleObjective = useCallback((objective: string) => {
    setPaperFormData((prev) => {
      if (prev.objectives.includes(objective)) {
        return { ...prev, objectives: prev.objectives.filter((o) => o !== objective) }
      }
      return { ...prev, objectives: [...prev.objectives, objective] }
    })
  }, [])

  const handlePaperCreationSubmit = useCallback(async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!paperFormData.title.trim()) {
      toast.warning('Paper title is required.')
      return
    }
    if (!paperCreationDialog) return

    paperActionMutation.mutate(
      {
        actionType: 'create_paper',
        payload: {
          title: paperFormData.title.trim(),
          paper_type: paperFormData.paperType,
          authoring_mode: paperFormData.authoringMode,
          abstract: paperFormData.abstract.trim() || undefined,
          keywords: paperFormData.keywords.length > 0 ? paperFormData.keywords : undefined,
          objectives: paperFormData.objectives.length > 0 ? paperFormData.objectives : undefined,
        },
      },
      {
        onSuccess: (data) => {
          if (data.paper_id && paperCreationDialog) {
            markActionApplied(paperCreationDialog.exchangeId, `${paperCreationDialog.exchangeId}:${paperCreationDialog.actionIndex}`)
          }
          setPaperCreationDialog(null)
          setPaperFormData({
            title: '',
            paperType: 'research',
            authoringMode: 'latex',
            abstract: '',
            keywords: [],
            objectives: [],
          })
        },
      }
    )
  }, [paperFormData, paperCreationDialog, paperActionMutation, markActionApplied, toast])

  const handleSuggestedAction = useCallback((
    exchange: AssistantExchange,
    action: DiscussionAssistantSuggestedAction,
    index: number
  ) => {
    if (!activeChannelId) {
      toast.warning('Select a channel before accepting assistant suggestions.')
      return
    }

    const actionKey = `${exchange.id}:${index}`
    if (exchange.appliedActions.includes(actionKey)) return

    if (action.action_type === 'create_paper') {
      const title = String(action.payload?.title || '').trim()
      const paperType = String(action.payload?.paper_type || 'research').trim()
      const authoringMode = String(action.payload?.authoring_mode || 'latex').trim()
      const abstract = String(action.payload?.abstract || '').trim()
      const suggestedKeywords = Array.isArray(action.payload?.keywords) ? action.payload.keywords : []

      setPaperCreationDialog({
        open: true,
        exchangeId: exchange.id,
        actionIndex: index,
        suggestedTitle: title,
        suggestedType: paperType,
        suggestedMode: authoringMode,
        suggestedAbstract: abstract,
        suggestedKeywords: suggestedKeywords,
      })
      setPaperFormData({
        title: title,
        paperType: paperType,
        authoringMode: authoringMode,
        abstract: abstract,
        keywords: suggestedKeywords,
        objectives: [],
      })
      return
    }

    if (action.action_type === 'artifact_created') {
      const title = String(action.payload?.title || 'download').trim()
      const filename = String(action.payload?.filename || `${title}.md`).trim()
      const contentBase64 = String(action.payload?.content_base64 || '')
      const mimeType = String(action.payload?.mime_type || 'text/plain')

      if (!contentBase64) {
        toast.warning('The artifact is missing content.')
        return
      }

      try {
        const binaryString = atob(contentBase64)
        const bytes = new Uint8Array(binaryString.length)
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i)
        }
        const blob = new Blob([bytes], { type: mimeType })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        markActionApplied(exchange.id, actionKey)
        queryClient.invalidateQueries({ queryKey: ['channel-artifacts', projectId, activeChannelId] })
      } catch (e) {
        console.error('Failed to decode artifact:', e)
        toast.error('Failed to download artifact.')
      }
      return
    }

    toast.info('This assistant suggestion type is not yet supported.')
  }, [activeChannelId, markActionApplied, queryClient, projectId, toast])

  const navigateToPaper = useCallback((urlId: string) => {
    navigate(`/projects/${getProjectUrlId(project)}/papers/${urlId}`)
  }, [navigate, project])

  return {
    paperCreationDialog,
    setPaperCreationDialog,
    paperFormData,
    setPaperFormData,
    keywordInput,
    setKeywordInput,
    paperActionMutation,
    handleAddKeyword,
    handleRemoveKeyword,
    handleToggleObjective,
    handlePaperCreationSubmit,
    handleSuggestedAction,
    navigateToPaper,
  }
}
