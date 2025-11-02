import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Calendar, Loader2, Mic, Sparkles, Video, X } from 'lucide-react'
import { useProjectContext } from './ProjectLayout'
import { projectMeetingsAPI, API_ROOT } from '../../services/api'
import {
  MeetingSummary,
  ProjectSyncSession,
  SyncSessionTokenResponse,
} from '../../types'

type JoinCallArgs = {
  session: ProjectSyncSession
  openWindow?: boolean
  targetWindow?: Window | null
}

const formatDateTime = (value?: string | null) => {
  if (!value) return '—'
  const date = new Date(value)
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
}

const statusLabel = (status: ProjectSyncSession['status']) => {
  switch (status) {
    case 'live':
      return 'Live'
    case 'scheduled':
      return 'Scheduled'
    case 'ended':
      return 'Ended'
    case 'cancelled':
      return 'Cancelled'
    default:
      return status
  }
}

const badgeStyles = (status: ProjectSyncSession['status']) => {
  switch (status) {
    case 'live':
      return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-100'
    case 'scheduled':
      return 'bg-sky-100 text-sky-700 dark:bg-sky-500/20 dark:text-sky-100'
    case 'ended':
      return 'bg-gray-200 text-gray-700 dark:bg-slate-700/60 dark:text-slate-200'
    case 'cancelled':
      return 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-200'
    default:
      return 'bg-gray-100 text-gray-600 dark:bg-slate-700/60 dark:text-slate-300'
  }
}

const appendTokenToUrl = (rawUrl: string, token: string, paramName: string = 't') => {
  try {
    const url = new URL(rawUrl)
    url.searchParams.set(paramName, token)
    return url.toString()
  } catch (error) {
    console.warn('Failed to append token to URL', error)
    return rawUrl
  }
}

const ProjectSyncSpace = () => {
  const { project } = useProjectContext()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  const projectId = project?.id
  const [callToken, setCallToken] = useState<SyncSessionTokenResponse | null>(null)
  const [expandedTranscriptSessionId, setExpandedTranscriptSessionId] = useState<string | null>(null)
  const [chatModalSession, setChatModalSession] = useState<ProjectSyncSession | null>(null)

  const extractTranscriptText = useCallback((value: unknown): string => {
    if (!value) return ''
    if (typeof value === 'string') return value
    if (Array.isArray(value)) {
      return value
        .map((item) => {
          if (item && typeof item === 'object' && 'text' in item) {
            const text = (item as { text?: unknown }).text
            return typeof text === 'string' ? text : JSON.stringify(item)
          }
          return typeof item === 'string' ? item : JSON.stringify(item)
        })
        .join('\n')
    }
    if (typeof value === 'object') {
      const record = value as Record<string, unknown>
      if (typeof record.text === 'string') {
        return record.text
      }
      if (Array.isArray(record.segments)) {
        return (record.segments as Array<{ text?: string }> )
          .map((segment) => (typeof segment.text === 'string' ? segment.text : ''))
          .filter(Boolean)
          .join('\n')
      }
      return JSON.stringify(value, null, 2)
    }
    return String(value)
  }, [])
  const sessionsQuery = useQuery({
    queryKey: ['project', projectId, 'sync-sessions'],
    queryFn: async () => {
      if (!projectId) return { sessions: [] as ProjectSyncSession[] }
      const response = await projectMeetingsAPI.listSyncSessions(projectId)
      return response.data
    },
    enabled: Boolean(projectId),
  })

  const sessions = sessionsQuery.data?.sessions ?? []
  const liveSessions = sessions.filter((session) => session.status === 'live')
  const scheduledSessions = sessions.filter((session) => session.status === 'scheduled')
  const endedSessions = sessions.filter((session) => session.status === 'ended')
  const cancelledSessions = sessions.filter((session) => session.status === 'cancelled')

  const viewMode = searchParams.get('view') || 'summary'
  const firstPreferred = liveSessions[0] || scheduledSessions[0] || endedSessions[0] || cancelledSessions[0] || null

  const [selectedSessionId, setSelectedSessionId] = useState<string | undefined>(
    searchParams.get('session') ?? firstPreferred?.id
  )
  const selectedSession = sessions.find((session) => session.id === selectedSessionId) || null
  const activeChatSession = chatModalSession || (viewMode === 'chat' ? selectedSession : null)
  const previousViewModeRef = useRef(viewMode)

  useEffect(() => {
    if (!selectedSessionId && firstPreferred) {
      setSelectedSessionId(firstPreferred.id)
    }
  }, [selectedSessionId, firstPreferred])

  useEffect(() => {
    const sessionParam = searchParams.get('session')
    if (sessionParam && sessionParam !== selectedSessionId) {
      setSelectedSessionId(sessionParam)
    }
  }, [searchParams, selectedSessionId])

  useEffect(() => {
    const next = new URLSearchParams(searchParams)
    if (selectedSessionId) {
      next.set('session', selectedSessionId)
    } else {
      next.delete('session')
    }
    if ((selectedSessionId && searchParams.get('session') !== selectedSessionId) || (!selectedSessionId && searchParams.get('session'))) {
      setSearchParams(next, { replace: true })
    }
  }, [selectedSessionId, searchParams, setSearchParams])

  useEffect(() => {
    if (selectedSessionId && !sessions.some((session) => session.id === selectedSessionId)) {
      setSelectedSessionId(firstPreferred?.id)
      setCallToken(null)
    }
  }, [selectedSessionId, sessions, firstPreferred])

  useEffect(() => {
    if (callToken && selectedSession && callToken.session_id !== selectedSession.id) {
      setCallToken(null)
    }
  }, [callToken, selectedSession])

  const openChatModal = useCallback(
    (session: ProjectSyncSession, options?: { syncUrl?: boolean }) => {
      setSelectedSessionId((prev) => (prev === session.id ? prev : session.id))
      setChatModalSession(session)
      if (options?.syncUrl) {
        const next = new URLSearchParams(searchParams)
        next.set('session', session.id)
        next.set('view', 'chat')
        setSearchParams(next, { replace: true })
      }
    },
    [searchParams, setSearchParams]
  )

  const closeChatModal = useCallback(
    (options?: { syncUrl?: boolean }) => {
      setChatModalSession(null)
      if (options?.syncUrl) {
        const next = new URLSearchParams(searchParams)
        next.delete('view')
        setSearchParams(next, { replace: true })
      }
    },
    [searchParams, setSearchParams]
  )

  useEffect(() => {
    if (viewMode === 'chat') {
      const sessionParam = searchParams.get('session')
      const target = sessionParam
        ? sessions.find((item) => item.id === sessionParam)
        : selectedSession || null
      if (target) {
        openChatModal(target)
      }
    } else if (previousViewModeRef.current === 'chat' && viewMode !== 'chat') {
      closeChatModal()
    }
    previousViewModeRef.current = viewMode
  }, [viewMode, searchParams, sessions, selectedSession, openChatModal, closeChatModal])

  const startSession = useMutation({
    mutationFn: async () => {
      if (!projectId) return null
      const response = await projectMeetingsAPI.createSyncSession(projectId, {
        provider: 'daily',
        status: 'live',
      })
      return response.data
    },
    onSuccess: (data) => {
      if (data?.id) {
        setSelectedSessionId(data.id)
      }
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'sync-sessions'] })
    },
  })

  const endSession = useMutation({
    mutationFn: async (session: ProjectSyncSession) => {
      if (!projectId) throw new Error('Missing project')
      const response = await projectMeetingsAPI.endSyncSession(projectId, session.id, {
        status: 'ended',
      })
      return response.data
    },
    onSuccess: () => {
      setCallToken(null)
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'sync-sessions'] })
    },
  })

  const clearEndedSessions = useMutation({
    mutationFn: async (sessionIds: string[]) => {
      if (!projectId || sessionIds.length === 0) {
        return
      }
      for (const id of sessionIds) {
        await projectMeetingsAPI.deleteSyncSession(projectId, id)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'sync-sessions'] })
    },
  })

  const {
    mutate: triggerJoinCall,
    isPending: isJoinCallPending,
    variables: lastJoinCallVars,
  } = useMutation<SyncSessionTokenResponse, unknown, JoinCallArgs>({
    mutationFn: async ({ session }: JoinCallArgs) => {
      if (!projectId) throw new Error('Missing project')
      const response = await projectMeetingsAPI.createCallToken(projectId, session.id)
      return response.data
    },
    onSuccess: (data, variables) => {
      setCallToken(data)
      console.log('[SyncSpace] Received call token', data)
      const windowUrl = data.join_url || (data.room_url ? appendTokenToUrl(data.room_url, data.token) : null)
      if (variables?.openWindow && windowUrl) {
        if (variables.targetWindow && !variables.targetWindow.closed) {
          try {
            variables.targetWindow.location.href = windowUrl
            // sever the opener relationship once navigation occurs
            variables.targetWindow.opener = null
          } catch (error) {
            console.warn('Failed to reuse call window', error)
            window.open(windowUrl, '_blank', 'noopener')
          }
        } else {
          window.open(windowUrl, '_blank', 'noopener')
        }
      }
    },
  })

  useEffect(() => {
    if (callToken && selectedSession && selectedSession.status !== 'live') {
      setCallToken(null)
    }
  }, [callToken, selectedSession])

  const handleOpenChatWindow = (session: ProjectSyncSession) => {
    openChatModal(session)
  }

  const renderSessionCard = (session: ProjectSyncSession) => {
    const recording = session.recording as MeetingSummary | undefined | null
    const isSelected = session.id === selectedSessionId
    const isLive = session.status === 'live'
    const callTokenForSession = callToken?.session_id === session.id ? callToken : null
    const callUrl = isLive
      ? callTokenForSession?.join_url
          || (callTokenForSession?.room_url ? appendTokenToUrl(callTokenForSession.room_url, callTokenForSession.token) : null)
      : null
    const callWindowUrl = callTokenForSession?.join_url
      || (callTokenForSession?.room_url ? appendTokenToUrl(callTokenForSession.room_url, callTokenForSession.token) : null)

    const isTranscriptExpanded = expandedTranscriptSessionId === session.id
    const recordingUrl = recording?.audio_url || null
    const recordingHref = (() => {
      if (!recordingUrl) return null
      if (recordingUrl.startsWith('http://') || recordingUrl.startsWith('https://')) {
        return recordingUrl
      }
      try {
        const root = new URL(API_ROOT)
        root.pathname = recordingUrl.startsWith('/')
          ? recordingUrl
          : `/${recordingUrl}`
        return root.toString()
      } catch (error) {
        console.warn('Failed to build recording URL', error)
        return recordingUrl
      }
    })()

    const transcriptDisplay = (() => {
      if (!recording) {
        return <span className="text-xs text-gray-500 dark:text-slate-400">Attach a recording to bind the transcript here.</span>
      }

      const status = recording.status
      if (status === 'transcribing') {
        return (
          <span className="inline-flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-300">
            <Loader2 className="h-3 w-3 animate-spin" /> Transcription in progress…
          </span>
        )
      }
      if (status === 'uploaded') {
        return <span className="text-xs text-gray-500 dark:text-slate-400">Preparing transcription…</span>
      }
      if (status === 'failed') {
        return <span className="text-xs text-rose-600 dark:text-rose-300">Transcription failed. Try attaching the recording again.</span>
      }
      if (recording.transcript) {
        const transcriptText = extractTranscriptText(recording.transcript)
        return (
          <div className="flex flex-col gap-1">
            {transcriptText && (
              <button
                type="button"
                onClick={() =>
                  setExpandedTranscriptSessionId(isTranscriptExpanded ? null : session.id)
                }
                className="self-start text-xs font-medium text-indigo-600 transition hover:text-indigo-500 dark:text-indigo-200 dark:hover:text-indigo-100"
              >
                {isTranscriptExpanded ? 'Hide transcript' : 'View transcript'}
              </button>
            )}
            {isTranscriptExpanded && transcriptText && (
              <div className="max-h-60 w-full overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-200">
                <pre className="whitespace-pre-wrap break-words">{transcriptText}</pre>
              </div>
            )}
          </div>
        )
      }
      return <span className="text-xs text-gray-500 dark:text-slate-400">Transcript not available yet.</span>
    })()

    return (
      <div
        key={session.id}
        className={`rounded-2xl border p-5 shadow-sm transition-colors ${isSelected ? 'border-indigo-200 bg-indigo-50/60 dark:border-indigo-500/40 dark:bg-indigo-500/10' : 'border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-900/50'}`}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-1">
            <div className={`${badgeStyles(session.status)} inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold capitalize leading-none`}>
              {statusLabel(session.status)}
            </div>
            <div className="text-xs text-gray-500 dark:text-slate-400">
              Started {formatDateTime(session.started_at || session.created_at)}
            </div>
            {session.ended_at && (
              <div className="text-xs text-gray-500 dark:text-slate-400">Completed {formatDateTime(session.ended_at)}</div>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setSelectedSessionId(session.id)}
              className="inline-flex items-center gap-2 rounded-full border border-indigo-200 px-3 py-1.5 text-xs font-medium text-indigo-600 transition hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
            >
              View details
            </button>
            <button
              type="button"
              onClick={() => handleOpenChatWindow(session)}
              className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              View transcript
            </button>
            {isLive && (
              <button
                type="button"
                onClick={() => {
                  setSelectedSessionId(session.id)
                  if (callTokenForSession && callWindowUrl) {
                    window.open(callWindowUrl, '_blank', 'noopener')
                  } else {
                    const popup = window.open('', '_blank')
                    triggerJoinCall({ session, openWindow: true, targetWindow: popup ?? undefined })
                  }
                }}
                disabled={
                  isJoinCallPending && lastJoinCallVars?.session.id === session.id
                }
                className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                {(isJoinCallPending && lastJoinCallVars?.session.id === session.id)
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <Video className="h-3.5 w-3.5" />}
                Open call window
              </button>
            )}
            {isLive && (
              <button
                type="button"
                onClick={() => endSession.mutate(session)}
                disabled={endSession.isPending}
                className="inline-flex items-center gap-2 rounded-full border border-indigo-200 px-3 py-1.5 text-xs font-medium text-indigo-600 transition hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
              >
                {endSession.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Calendar className="h-3.5 w-3.5" />}
                {endSession.isPending ? 'Ending…' : 'End session'}
              </button>
            )}
          </div>
        </div>

        <div className="mt-4 space-y-2 text-sm text-gray-600 dark:text-slate-300">
          <div>Provider: {session.provider || '—'}</div>
          <div>Room ID: {session.provider_room_id || '—'}</div>
          {callUrl && (
            <div className="break-all text-xs text-gray-500 dark:text-slate-400">Call URL: {callUrl}</div>
          )}
          <div className="flex items-center gap-2">
            <span>Transcript:</span>
            {transcriptDisplay}
          </div>
          {recordingHref && (
            <div>
              <a
                href={recordingHref}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-full border border-indigo-200 px-3 py-1.5 text-xs font-medium text-indigo-600 transition hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
              >
                <Mic className="h-3.5 w-3.5" /> Open call recording
              </a>
            </div>
          )}
        </div>

      </div>
    )
  }

  const renderChatModal = (session: ProjectSyncSession) => {
    const handleClose = () => {
      const shouldSyncUrl = viewMode === 'chat'
      closeChatModal({ syncUrl: shouldSyncUrl })
    }

    const recording = session.recording as MeetingSummary | undefined | null
    const transcriptText = recording ? extractTranscriptText(recording.transcript) : ''
    const startedAtLabel = formatDateTime(session.started_at || session.created_at)
    const endedAtLabel = session.ended_at ? formatDateTime(session.ended_at) : null
    const statusClass = badgeStyles(session.status)
    const recordingUrl = recording?.audio_url || null
    const recordingHref = (() => {
      if (!recordingUrl) return null
      if (recordingUrl.startsWith('http://') || recordingUrl.startsWith('https://')) {
        return recordingUrl
      }
      try {
        const root = new URL(API_ROOT)
        root.pathname = recordingUrl.startsWith('/') ? recordingUrl : `/${recordingUrl}`
        return root.toString()
      } catch (error) {
        console.warn('Failed to build recording URL', error)
        return recordingUrl
      }
    })()

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center px-4 py-6 sm:px-6">
        <div
          className="absolute inset-0 bg-gray-900/30 dark:bg-black/70"
          onClick={handleClose}
          aria-hidden="true"
        />
        <div className="relative flex h-[80vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-xl transition-colors dark:border-slate-700 dark:bg-slate-900/90">
          <div className="flex items-start justify-between gap-4 border-b border-gray-200 px-6 py-5 dark:border-slate-700">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">Session details</h2>
                <span className={`${statusClass} inline-flex items-center rounded-full px-3 py-1 text-[11px] font-semibold capitalize`}>
                  {statusLabel(session.status)}
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-slate-400">Started {startedAtLabel}</p>
              {endedAtLabel && <p className="text-xs text-gray-500 dark:text-slate-400">Ended {endedAtLabel}</p>}
            </div>
            <button
              type="button"
              onClick={handleClose}
              className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-gray-200 text-gray-500 transition hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
              aria-label="Close session details"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto bg-gray-50 px-6 py-6 dark:bg-slate-900/40">
            <section className="space-y-3 rounded-xl border border-gray-200 bg-white p-5 transition-colors dark:border-slate-700 dark:bg-slate-900/70">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-slate-100">Call information</h3>
              <dl className="grid grid-cols-1 gap-3 text-sm text-gray-600 dark:text-slate-300 sm:grid-cols-2">
                <div>
                  <dt className="text-xs uppercase tracking-wide text-gray-400 dark:text-slate-500">Provider</dt>
                  <dd>{session.provider || '—'}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-gray-400 dark:text-slate-500">Room ID</dt>
                  <dd>{session.provider_room_id || '—'}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-gray-400 dark:text-slate-500">Started by</dt>
                  <dd>{session.started_by || '—'}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-gray-400 dark:text-slate-500">Recording status</dt>
                  <dd>{recording?.status ?? '—'}</dd>
                </div>
              </dl>
              {recordingHref && (
                <a
                  href={recordingHref}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 self-start rounded-full border border-indigo-200 px-3 py-1.5 text-xs font-medium text-indigo-600 transition hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
                >
                  <Mic className="h-3.5 w-3.5" /> Open recording
                </a>
              )}
            </section>

            <section className="mt-6 space-y-3 rounded-xl border border-gray-200 bg-white p-5 transition-colors dark:border-slate-700 dark:bg-slate-900/70">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-slate-100">Transcript</h3>
              {transcriptText ? (
                <div className="max-h-72 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-4 text-xs text-gray-700 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-200">
                  <pre className="whitespace-pre-wrap break-words">{transcriptText}</pre>
                </div>
              ) : (
                <p className="text-xs text-gray-500 dark:text-slate-400">Transcript will appear here once the recording has been processed.</p>
              )}
            </section>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-indigo-100 bg-white p-6 shadow-sm transition-colors dark:border-indigo-500/30 dark:bg-slate-900/40">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3 text-indigo-700 dark:text-indigo-200">
            <Video className="h-6 w-6 text-indigo-600 dark:text-indigo-300" />
            <div>
              <h1 className="text-xl font-semibold text-indigo-900 dark:text-indigo-100">Sync Space</h1>
              <p className="text-sm text-indigo-600 dark:text-indigo-200">
                Start a live call, keep the transcript, and let GPT-5 craft follow-ups for your team.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => startSession.mutate()}
            disabled={startSession.isPending || !projectId}
            className="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {startSession.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
            {startSession.isPending ? 'Starting...' : 'Start a call'}
          </button>
        </div>
      </section>

      <div className="space-y-4">
        {sessionsQuery.isLoading && (
          <div className="h-32 animate-pulse rounded-2xl border border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-900/50" />
        )}

        {!sessionsQuery.isLoading && sessions.length === 0 && (
          <div className="rounded-2xl border border-dashed border-gray-200 bg-white p-6 text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-300">
            No sync sessions yet. Start your first call to unlock collaborative notes and AI summaries.
          </div>
        )}

        {[...liveSessions, ...scheduledSessions].map((session) => renderSessionCard(session))}

        {endedSessions.length > 0 && (
          <div className="flex items-center justify-end">
            <button
              type="button"
              onClick={() => clearEndedSessions.mutate(endedSessions.map((session) => session.id))}
              disabled={clearEndedSessions.isPending}
              className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              {clearEndedSessions.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              {clearEndedSessions.isPending ? 'Clearing…' : 'Clear ended sessions'}
            </button>
          </div>
        )}

        {[...endedSessions, ...cancelledSessions].map((session) => renderSessionCard(session))}

      </div>

      {activeChatSession && renderChatModal(activeChatSession)}
    </div>
  )
}

export default ProjectSyncSpace
