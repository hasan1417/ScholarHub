import { ReactNode, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, Bell, FilePenLine, FilePlus, Loader2, Settings, Video } from 'lucide-react'
import ProjectTeamManager from '../../components/projects/ProjectTeamManager'
import { useProjectContext } from './ProjectLayout'
import { projectNotificationsAPI } from '../../services/api'
import { ProjectNotification } from '../../types'

const ProjectOverview = () => {
  const { project } = useProjectContext()
  const projectId = project?.id

  const notificationsQuery = useQuery<ProjectNotification[]>({
    queryKey: ['project', projectId, 'notifications'],
    queryFn: async () => {
      if (!projectId) return []
      const response = await projectNotificationsAPI.listProjectNotifications(projectId)
      return response.data.notifications
    },
    enabled: Boolean(projectId),
    staleTime: 30_000,
  })

  const notifications = notificationsQuery.data ?? []
  const descriptionText = project.idea?.trim() || project.scope?.trim() || ''
  const objectivesList = useMemo(() => {
    if (!project.scope) return []

    const segments = project.scope
      .split(/\r?\n|[•]/)
      .map((segment) => segment.replace(/^\d+[\).\s-]*/, '').trim())
      .filter(Boolean)

    if (segments.length > 0) {
      return segments
    }

    return project.scope.trim() ? [project.scope.trim()] : []
  }, [project.scope])

  const formatDateTime = (value?: string | null) => {
    if (!value) return ''
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ''
    return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
  }

  const formatRelativeTime = (value?: string | null) => {
    if (!value) return ''
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ''
    const diff = Date.now() - date.getTime()
    const minute = 60 * 1000
    const hour = 60 * minute
    const day = 24 * hour
    const week = 7 * day
    if (diff < minute) return 'just now'
    if (diff < hour) {
      const value = Math.floor(diff / minute)
      return `${value} min ago`
    }
    if (diff < day) {
      const value = Math.floor(diff / hour)
      return `${value} hr${value === 1 ? '' : 's'} ago`
    }
    if (diff < week) {
      const value = Math.floor(diff / day)
      return `${value} day${value === 1 ? '' : 's'} ago`
    }
    return date.toLocaleDateString()
  }

  const toSentence = (value?: string | null) => {
    if (!value) return 'unknown'
    return value.charAt(0).toUpperCase() + value.slice(1)
  }

  const formatDuration = (seconds?: number | null) => {
    if (seconds === undefined || seconds === null || Number.isNaN(Number(seconds))) return null
    const total = Math.max(0, Math.floor(Number(seconds)))
    const mins = Math.floor(total / 60)
    const secs = total % 60
    if (mins === 0) return `${secs}s`
    return `${mins}m ${secs.toString().padStart(2, '0')}s`
  }

  const renderNotificationCard = ({
    key,
    icon,
    iconClassName,
    title,
    subtitle,
    badges,
    recordedAt,
    recordedRelative,
    meta,
    content,
  }: {
    key: string
    icon: ReactNode
    iconClassName: string
    title: string
    subtitle?: string
    badges?: Array<{ label: string; tone: 'default' | 'positive' | 'neutral' | 'warning' | 'danger' }>
    recordedAt?: string
    recordedRelative?: string
    meta?: ReactNode
    content?: ReactNode
  }) => {
    const badgeToneClass = (tone: 'default' | 'positive' | 'neutral' | 'warning' | 'danger') => {
      switch (tone) {
        case 'positive':
          return 'bg-emerald-100 dark:bg-emerald-400/10 text-emerald-700 dark:text-emerald-200'
        case 'warning':
          return 'bg-amber-100 dark:bg-amber-400/10 text-amber-700 dark:text-amber-200'
        case 'danger':
          return 'bg-rose-100 dark:bg-rose-400/10 text-rose-700 dark:text-rose-200'
        case 'neutral':
          return 'bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-slate-200'
        default:
          return 'bg-indigo-100 dark:bg-indigo-400/10 text-indigo-600 dark:text-indigo-200'
      }
    }

    return (
      <li key={key} className="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4 shadow-sm min-h-[120px]">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:gap-4">
          <div className="flex items-center gap-3 md:w-56 md:flex-shrink-0">
            <span className={`flex h-9 w-9 items-center justify-center rounded-full ${iconClassName}`}>
              {icon}
            </span>
            <div className="space-y-0.5">
              <p className="text-sm font-semibold text-gray-900 dark:text-slate-100">{title}</p>
              {subtitle && <p className="text-xs text-gray-500 dark:text-slate-300">{subtitle}</p>}
            </div>
          </div>
          <div className="flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
              {recordedRelative && (
                <span title={recordedAt}>{recordedRelative}</span>
              )}
              {badges?.map((badge) => (
                <span
                  key={badge.label}
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${badgeToneClass(badge.tone)}`}
                >
                  {badge.label}
                </span>
              ))}
              {meta}
            </div>
            {content}
          </div>
        </div>
      </li>
    )
  }

  const renderNotification = (notification: ProjectNotification) => {
    const payload = (notification.payload ?? {}) as Record<string, unknown>
    const recordedAtIso = typeof payload.recorded_at === 'string' ? payload.recorded_at : notification.created_at
    const recordedAtLabel = formatDateTime(recordedAtIso)
    const recordedRelative = formatRelativeTime(recordedAtIso)

    if (notification.type.startsWith('sync-session.')) {
      const action = typeof payload.action === 'string' ? payload.action : notification.type.split('.').pop() ?? 'updated'
      const actor = (payload.actor ?? {}) as Record<string, unknown>
      const actorName = typeof actor.name === 'string' && actor.name.trim()
        ? actor.name
        : (typeof actor.email === 'string' ? actor.email : 'Team member')
      const provider = typeof payload.provider === 'string' ? payload.provider : 'daily'
      const status = typeof payload.status === 'string' ? payload.status : null
      const startedAt = typeof payload.started_at === 'string' ? payload.started_at : null
      const endedAt = typeof payload.ended_at === 'string' ? payload.ended_at : null
      const duration = formatDuration(typeof payload.duration_seconds === 'number' ? payload.duration_seconds : Number(payload.duration_seconds))

      const statusKey = (typeof status === 'string' ? status : action).toLowerCase()
      const badgeText = toSentence(statusKey)
      return renderNotificationCard({
        key: notification.id,
        icon: <Video className="h-4 w-4" />,
        iconClassName: 'bg-sky-100 text-sky-600',
        title: `Call ${action}`,
        subtitle: `${actorName} • ${provider}`,
        badges: badgeText ? [{ label: badgeText, tone: statusKey === 'cancelled' ? 'danger' : statusKey === 'ended' ? 'neutral' : 'positive' }] : undefined,
        recordedAt: recordedAtLabel,
        recordedRelative,
        meta: (
          <div className="flex items-center gap-2 text-[11px] text-gray-400">
            {startedAt && <span title={formatDateTime(startedAt)}>Started {formatRelativeTime(startedAt)}</span>}
            {endedAt && <span title={formatDateTime(endedAt)}>Ended {formatRelativeTime(endedAt)}</span>}
            {duration && <span className="text-gray-500">Duration {duration}</span>}
          </div>
        ),
        content: (
          <div className="rounded-lg border border-gray-100 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/60 p-2.5 text-sm text-gray-700 dark:text-slate-300">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Session summary</p>
            <p className="mt-1 text-xs text-gray-700 dark:text-slate-300">Status: {toSentence(status ?? action)}.</p>
          </div>
        ),
      })
    }

    if (notification.type.startsWith('paper.')) {
      const action = typeof payload.action === 'string' ? payload.action : notification.type.split('.').pop() ?? 'updated'
      const actor = (payload.actor ?? {}) as Record<string, unknown>
      const actorName = typeof actor.name === 'string' && actor.name.trim()
        ? actor.name
        : (typeof actor.email === 'string' ? actor.email : 'Contributor')
      const title = typeof payload.paper_title === 'string' ? payload.paper_title : 'Untitled paper'
      const updatedFields = Array.isArray(payload.updated_fields)
        ? (payload.updated_fields as Array<unknown>).filter((item): item is string => typeof item === 'string')
        : []

      const isCreated = notification.type === 'paper.created'
      const icon = isCreated ? <FilePlus className="h-4 w-4" /> : <FilePenLine className="h-4 w-4" />
      const iconBg = isCreated ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'

      return renderNotificationCard({
        key: notification.id,
        icon,
        iconClassName: iconBg,
        title: `Paper ${action}`,
        subtitle: actorName,
        badges: !isCreated && updatedFields.length > 0
          ? [{ label: `Fields: ${updatedFields.join(', ')}`, tone: 'neutral' }]
          : undefined,
        recordedAt: recordedAtLabel,
        recordedRelative,
        content: (
          <div className="rounded-lg border border-gray-100 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/60 p-2.5">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Paper</p>
            <p className="mt-1 text-xs text-gray-700 dark:text-slate-300">{title}</p>
          </div>
        ),
      })
    }

    if (notification.type === 'project.updated') {
      const actor = (payload.actor ?? {}) as Record<string, unknown>
      const actorName = typeof actor.name === 'string' && actor.name.trim()
        ? actor.name
        : (typeof actor.email === 'string' ? actor.email : 'Project owner')
      const updatedFields = Array.isArray(payload.updated_fields)
        ? (payload.updated_fields as Array<unknown>).filter((item): item is string => typeof item === 'string')
        : []
      const projectTitle = typeof payload.project_title === 'string' && payload.project_title
        ? payload.project_title
        : project.title
      const fieldLabelMap: Record<string, string> = {
        idea: 'Description',
        keywords: 'Keywords',
        scope: 'Objectives',
      }
      const normalizedFieldLabels = updatedFields.map((field) => {
        const normalized = field.toLowerCase()
        if (fieldLabelMap[normalized]) return fieldLabelMap[normalized]
        return toSentence(field.replace(/_/g, ' '))
      })

      return renderNotificationCard({
        key: notification.id,
        icon: <Settings className="h-4 w-4" />,
        iconClassName: 'bg-indigo-100 text-indigo-600',
        title: 'Project updated',
        subtitle: actorName,
        badges: normalizedFieldLabels.length > 0
          ? [{ label: normalizedFieldLabels.join(', '), tone: 'neutral' }]
          : undefined,
        recordedAt: recordedAtLabel,
        recordedRelative,
        content: (
          <div className="rounded-lg border border-gray-100 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/60 p-2.5 text-sm text-gray-700 dark:text-slate-300">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Project</p>
            <p className="mt-1 text-xs text-gray-700 dark:text-slate-300">{projectTitle}</p>
          </div>
        ),
      })
    }

    if (notification.type.startsWith('project-reference.')) {
      const actor = (payload.actor ?? {}) as Record<string, unknown>
      const actorName = typeof actor.name === 'string' && actor.name.trim()
        ? actor.name
        : (typeof actor.email === 'string' ? actor.email : 'Team member')
      const referenceTitle = typeof payload.reference_title === 'string' && payload.reference_title
        ? payload.reference_title
        : 'Untitled reference'
      const paperTitle = typeof payload.paper_title === 'string' && payload.paper_title
        ? payload.paper_title
        : null
      const confidence = typeof payload.confidence === 'number'
        ? `${Math.round(payload.confidence * 100)}%`
        : null
      const source = typeof payload.source === 'string' ? payload.source : null
      const action = notification.type.split('.').pop() ?? 'updated'

      const badges: Array<{ label: string; tone: 'default' | 'positive' | 'neutral' | 'warning' | 'danger' }> = []
      if (confidence) {
        badges.push({ label: `Confidence ${confidence}`, tone: 'positive' })
      }
      if (source) {
        badges.push({ label: toSentence(source.replace('-', ' ')), tone: 'neutral' })
      }

      return renderNotificationCard({
        key: notification.id,
        icon: <FilePenLine className="h-4 w-4" />,
        iconClassName: 'bg-purple-100 text-purple-700',
        title: `Related paper ${action}`,
        subtitle: actorName,
        badges,
        recordedAt: recordedAtLabel,
        recordedRelative,
        content: (
          <div className="space-y-2">
            <div className="rounded-lg border border-gray-100 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/60 p-2.5">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Related paper</p>
              <p className="mt-1 text-xs text-gray-700 dark:text-slate-300">{referenceTitle}</p>
            </div>
            {paperTitle && (
              <div className="rounded-lg border border-indigo-100 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-400/10 p-2.5 text-sm text-indigo-700 dark:text-indigo-200">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-indigo-500 dark:text-indigo-300">Linked paper</p>
                <p className="mt-1 text-xs">{paperTitle}</p>
              </div>
            )}
          </div>
        ),
      })
    }

    return renderNotificationCard({
      key: notification.id,
      icon: <AlertCircle className="h-5 w-5" />,
      iconClassName: 'bg-gray-100 text-gray-500',
      title: notification.type,
      subtitle: 'Activity details not yet captured',
      recordedAt: recordedAtLabel,
      recordedRelative,
    })
  }

  const activityContent = useMemo(() => {
    if (notificationsQuery.isLoading) {
      return (
        <div className="flex items-center gap-2 rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-3 text-sm text-gray-500 dark:text-slate-300">
          <Loader2 className="h-4 w-4 animate-spin text-indigo-600 dark:text-indigo-400" />
          Fetching recent activity…
        </div>
      )
    }

    if (notificationsQuery.isError) {
      return (
        <div className="flex items-start gap-2 rounded-xl border border-rose-200 dark:border-rose-800 bg-rose-50 dark:bg-rose-400/10 px-4 py-3 text-sm text-rose-600 dark:text-rose-200">
          <AlertCircle className="mt-0.5 h-4 w-4" />
          Unable to load updates right now. Please refresh and try again.
        </div>
      )
    }

    if (notifications.length === 0) {
      return (
        <div className="rounded-xl border border-dashed border-gray-300 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/60 p-6 text-sm text-gray-500 dark:text-slate-300">
          Project activity will appear here once teammates start collaborating (calls, paper edits, references, and more).
        </div>
      )
    }

    const topNotifications = notifications.slice(0, 10)
    return (
      <ol className="space-y-3">
        {topNotifications.map((item) => renderNotification(item))}
      </ol>
    )
  }, [notifications, notificationsQuery.isError, notificationsQuery.isLoading])

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[2fr,1fr]">
        <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800">
          <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">Project context</h2>
          <dl className="mt-4 space-y-5 text-sm text-gray-600 dark:text-slate-300">
            <div>
              <dt className="font-medium text-gray-700 dark:text-slate-200">Description</dt>
              <dd className="mt-1 whitespace-pre-line">
                {descriptionText ? (
                  descriptionText
                ) : (
                  <span className="text-gray-400 dark:text-slate-500">No description captured yet.</span>
                )}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-gray-700 dark:text-slate-200">Objectives</dt>
              <dd className="mt-2">
                <ol className="list-decimal space-y-1 pl-5 text-sm text-gray-700 dark:text-slate-300">
                  {objectivesList.length > 0 ? (
                    objectivesList.map((objective, index) => (
                      <li key={`${objective}-${index}`}>{objective}</li>
                    ))
                  ) : (
                    <li className="text-gray-400 dark:text-slate-500">No objectives defined yet.</li>
                  )}
                </ol>
              </dd>
            </div>
          </dl>
        </section>
        <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800">
          <ProjectTeamManager />
        </section>
      </div>

      {/* Recent Activity Section */}
      <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800">
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">Recent Activity</h2>
        </div>
        <div className="mt-4 max-h-[600px] overflow-y-auto">
          {activityContent}
        </div>
      </section>
    </div>
  )
}

export default ProjectOverview
