import { useState, useCallback, useRef } from 'react'
import { buildApiUrl, refreshAuthToken } from '../services/api'
import { stripActionsBlock, buildCitationLookup, formatAssistantMessage } from './useAssistantChat'
import type { AssistantExchange } from './useAssistantChat'
import type { DiscussionAssistantResponse } from '../types'

export function useDeepResearch({
  projectId,
  activeChannelId,
  setAssistantHistory,
}: {
  projectId: string
  activeChannelId: string | null
  setAssistantHistory: React.Dispatch<React.SetStateAction<AssistantExchange[]>>
}) {
  const [isRunning, setIsRunning] = useState(false)
  const [progress, setProgress] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  const startDeepResearch = useCallback(
    async (question: string, contextSummary: string, referenceIds: string[], exchangeId: string, model: string = 'openai/o4-mini-deep-research') => {
      if (!activeChannelId) return

      setIsRunning(true)
      setProgress('Starting deep research...')

      const entry: AssistantExchange = {
        id: exchangeId,
        channelId: activeChannelId,
        question: `[Deep Research] ${question}`,
        response: {
          message: '',
          citations: [],
          reasoning_used: false,
          model,
          usage: undefined,
          suggested_actions: [],
        },
        createdAt: new Date(),
        appliedActions: [],
        status: 'streaming',
        displayMessage: '',
        statusMessage: 'Starting deep research...',
        isWaitingForTools: true,
        model,
      }

      setAssistantHistory((prev) => [...prev, entry])

      const controller = new AbortController()
      abortRef.current = controller

      try {
        let token = localStorage.getItem('access_token')
        if (!token) {
          const refreshed = await refreshAuthToken()
          token = refreshed || localStorage.getItem('access_token')
        }

        const url = buildApiUrl(
          `/projects/${projectId}/discussion-or/channels/${activeChannelId}/deep-research`
        )

        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ question, context_summary: contextSummary, reference_ids: referenceIds, model }),
          signal: controller.signal,
        })

        if (!response.ok) {
          const errorText = await response.text()
          throw new Error(`Request failed: ${response.status} ${errorText}`)
        }

        if (!response.body) {
          throw new Error('No response body')
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let accumulatedContent = ''
        let finalResult: DiscussionAssistantResponse | null = null

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const jsonStr = line.slice(6).trim()
            if (!jsonStr || jsonStr === '[DONE]') continue

            try {
              const event = JSON.parse(jsonStr)

              if (event.type === 'keepalive') {
                continue
              } else if (event.type === 'status') {
                const msg = event.message || ''
                setProgress(msg)
                setAssistantHistory((prev) =>
                  prev.map((e) =>
                    e.id === exchangeId
                      ? { ...e, statusMessage: msg, isWaitingForTools: true }
                      : e
                  )
                )
              } else if (event.type === 'token') {
                accumulatedContent += event.content || ''
                setAssistantHistory((prev) =>
                  prev.map((e) =>
                    e.id === exchangeId
                      ? {
                          ...e,
                          displayMessage: stripActionsBlock(accumulatedContent),
                          isWaitingForTools: false,
                        }
                      : e
                  )
                )
              } else if (event.type === 'result') {
                finalResult = event.payload
              } else if (event.type === 'error') {
                throw new Error(event.message || 'Deep research error')
              }
            } catch (parseError) {
              if (parseError instanceof Error && parseError.message.includes('Deep research error')) {
                throw parseError
              }
              console.warn('Failed to parse SSE event:', parseError)
            }
          }
        }

        if (!finalResult) {
          finalResult = {
            message: accumulatedContent,
            citations: [],
            reasoning_used: false,
            model: 'openai/o4-mini-deep-research',
            usage: undefined,
            suggested_actions: [],
          }
        }

        const citationLookup = buildCitationLookup(finalResult.citations ?? [])
        const formattedMessage = formatAssistantMessage(finalResult.message ?? '', citationLookup)

        setAssistantHistory((prev) =>
          prev.map((e) =>
            e.id === exchangeId
              ? {
                  ...e,
                  response: finalResult!,
                  status: 'complete' as const,
                  completedAt: new Date(),
                  displayMessage: formattedMessage,
                  isWaitingForTools: false,
                  statusMessage: undefined,
                }
              : e
          )
        )
      } catch (error: any) {
        const isAbort = error?.name === 'AbortError' || error?.message?.includes('abort')
        if (!isAbort) {
          console.error('Deep research error:', error)
          setAssistantHistory((prev) =>
            prev.map((e) =>
              e.id === exchangeId
                ? {
                    ...e,
                    status: 'complete' as const,
                    completedAt: new Date(),
                    displayMessage: `Error: ${error?.message || 'Deep research failed'}`,
                    response: {
                      ...e.response,
                      message: `Error: ${error?.message || 'Deep research failed'}`,
                    },
                    isWaitingForTools: false,
                    statusMessage: undefined,
                  }
                : e
            )
          )
        }
      } finally {
        setIsRunning(false)
        setProgress('')
        abortRef.current = null
      }
    },
    [projectId, activeChannelId, setAssistantHistory]
  )

  const cancelDeepResearch = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  return { isRunning, progress, startDeepResearch, cancelDeepResearch }
}
