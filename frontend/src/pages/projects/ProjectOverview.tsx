import { ReactNode, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, Bell, FilePenLine, FilePlus, FolderPlus, Loader2, Settings, UserMinus, UserPlus, UserX, Video } from 'lucide-react'
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

  // Simplified notification card - cleaner design
  const renderNotificationCard = ({
    key,
    icon,
    iconClassName,
    title,
    subtitle,
    badge,
    timestamp,
    detail,
  }: {
    key: string
    icon: ReactNode
    iconClassName: string
    title: string
    subtitle?: string
    badge?: { label: string; tone: 'positive' | 'neutral' | 'warning' | 'danger' }
    timestamp?: string
    detail?: string
  }) => {
    const badgeToneClass = {
      positive: 'bg-emerald-100 dark:bg-emerald-400/10 text-emerald-700 dark:text-emerald-300',
      warning: 'bg-amber-100 dark:bg-amber-400/10 text-amber-700 dark:text-amber-300',
      danger: 'bg-rose-100 dark:bg-rose-400/10 text-rose-700 dark:text-rose-300',
      neutral: 'bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-slate-300',
    }

    return (
      <li key={key} className="flex items-start gap-3 py-3 border-b border-gray-100 dark:border-slate-700/50 last:border-0">
        <span className={`flex h-8 w-8 items-center justify-center rounded-full flex-shrink-0 ${iconClassName}`}>
          {icon}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-medium text-gray-900 dark:text-slate-100">{title}</p>
            {badge && (
              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${badgeToneClass[badge.tone]}`}>
                {badge.label}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="text-xs text-gray-500 dark:text-slate-400 mt-0.5">{subtitle}</p>
          )}
          {detail && (
            <p className="text-xs text-gray-600 dark:text-slate-300 mt-1 truncate">{detail}</p>
          )}
        </div>
        {timestamp && (
          <span className="text-[11px] text-gray-400 dark:text-slate-500 flex-shrink-0">{timestamp}</span>
        )}
      </li>
    )
  }

  const renderNotification = (notification: ProjectNotification) => {
    const payload = (notification.payload ?? {}) as Record<string, unknown>
    const recordedAtIso = typeof payload.recorded_at === 'string' ? payload.recorded_at : notification.created_at
    const timestamp = formatRelativeTime(recordedAtIso)
    const actor = (payload.actor ?? {}) as Record<string, unknown>
    const actorName = typeof actor.name === 'string' && actor.name.trim()
      ? actor.name
      : (typeof actor.email === 'string' ? actor.email : 'Team member')

    // Sync session (calls)
    if (notification.type.startsWith('sync-session.')) {
      const action = notification.type.split('.').pop() ?? 'updated'
      const status = typeof payload.status === 'string' ? payload.status : action
      const duration = formatDuration(typeof payload.duration_seconds === 'number' ? payload.duration_seconds : Number(payload.duration_seconds))

      const titleMap: Record<string, string> = {
        started: 'Call started',
        ended: 'Call ended',
        cancelled: 'Call cancelled',
      }
      const badgeTone = status === 'cancelled' ? 'danger' : status === 'ended' ? 'neutral' : 'positive'

      return renderNotificationCard({
        key: notification.id,
        icon: <Video className="h-4 w-4" />,
        iconClassName: 'bg-sky-100 text-sky-600 dark:bg-sky-500/20 dark:text-sky-400',
        title: titleMap[action] || `Call ${action}`,
        subtitle: `${actorName}${duration ? ` · ${duration}` : ''}`,
        badge: { label: toSentence(status), tone: badgeTone },
        timestamp,
      })
    }

    // Project created
    if (notification.type === 'project.created') {
      return renderNotificationCard({
        key: notification.id,
        icon: <FolderPlus className="h-4 w-4" />,
        iconClassName: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400',
        title: 'Project created',
        subtitle: actorName,
        timestamp,
      })
    }

    // Project updated
    if (notification.type === 'project.updated') {
      const updatedFields = Array.isArray(payload.updated_fields)
        ? (payload.updated_fields as Array<unknown>).filter((item): item is string => typeof item === 'string')
        : []
      const fieldLabelMap: Record<string, string> = { idea: 'Description', keywords: 'Keywords', scope: 'Objectives' }
      const fieldLabels = updatedFields.map((f) => fieldLabelMap[f.toLowerCase()] || toSentence(f.replace(/_/g, ' ')))

      return renderNotificationCard({
        key: notification.id,
        icon: <Settings className="h-4 w-4" />,
        iconClassName: 'bg-indigo-100 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400',
        title: 'Project updated',
        subtitle: actorName,
        detail: fieldLabels.length > 0 ? `Changed: ${fieldLabels.join(', ')}` : undefined,
        timestamp,
      })
    }

    // Member events
    if (notification.type.startsWith('member.')) {
      const action = notification.type.split('.').pop() ?? 'updated'
      const invitedName = typeof payload.invited_user_name === 'string' ? payload.invited_user_name : null
      const removedName = typeof payload.removed_user_name === 'string' ? payload.removed_user_name : null
      const role = typeof payload.role === 'string' ? payload.role : null

      const config: Record<string, { icon: ReactNode; iconClass: string; title: string; subtitle: string }> = {
        invited: {
          icon: <UserPlus className="h-4 w-4" />,
          iconClass: 'bg-blue-100 text-blue-600 dark:bg-blue-500/20 dark:text-blue-400',
          title: 'Member invited',
          subtitle: `${actorName} invited ${invitedName || 'someone'}${role ? ` as ${role}` : ''}`,
        },
        joined: {
          icon: <UserPlus className="h-4 w-4" />,
          iconClass: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400',
          title: 'Member joined',
          subtitle: `${actorName} joined the project`,
        },
        declined: {
          icon: <UserX className="h-4 w-4" />,
          iconClass: 'bg-gray-100 text-gray-600 dark:bg-slate-700 dark:text-slate-400',
          title: 'Invitation declined',
          subtitle: `${actorName} declined the invitation`,
        },
        removed: {
          icon: <UserMinus className="h-4 w-4" />,
          iconClass: 'bg-rose-100 text-rose-600 dark:bg-rose-500/20 dark:text-rose-400',
          title: 'Member removed',
          subtitle: `${actorName} removed ${removedName || 'a member'}`,
        },
      }

      const c = config[action] || { icon: <UserPlus className="h-4 w-4" />, iconClass: 'bg-gray-100 text-gray-500', title: `Member ${action}`, subtitle: actorName }

      return renderNotificationCard({
        key: notification.id,
        icon: c.icon,
        iconClassName: c.iconClass,
        title: c.title,
        subtitle: c.subtitle,
        timestamp,
      })
    }

    // Paper events
    if (notification.type.startsWith('paper.')) {
      const action = notification.type.split('.').pop() ?? 'updated'
      const paperTitle = typeof payload.paper_title === 'string' ? payload.paper_title : null
      const referenceTitle = typeof payload.reference_title === 'string' ? payload.reference_title : null

      const config: Record<string, { icon: ReactNode; iconClass: string; title: string }> = {
        created: {
          icon: <FilePlus className="h-4 w-4" />,
          iconClass: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400',
          title: 'Paper created',
        },
        updated: {
          icon: <FilePenLine className="h-4 w-4" />,
          iconClass: 'bg-amber-100 text-amber-600 dark:bg-amber-500/20 dark:text-amber-400',
          title: 'Paper updated',
        },
        'reference-linked': {
          icon: <FilePenLine className="h-4 w-4" />,
          iconClass: 'bg-purple-100 text-purple-600 dark:bg-purple-500/20 dark:text-purple-400',
          title: 'Reference added',
        },
        'reference-unlinked': {
          icon: <FilePenLine className="h-4 w-4" />,
          iconClass: 'bg-gray-100 text-gray-600 dark:bg-slate-700 dark:text-slate-400',
          title: 'Reference removed',
        },
      }

      const c = config[action] || { icon: <FilePenLine className="h-4 w-4" />, iconClass: 'bg-gray-100 text-gray-500', title: `Paper ${action}` }

      return renderNotificationCard({
        key: notification.id,
        icon: c.icon,
        iconClassName: c.iconClass,
        title: c.title,
        subtitle: actorName,
        detail: (action.includes('reference') ? referenceTitle : paperTitle) ?? undefined,
        timestamp,
      })
    }

    // Project reference events (discovery)
    if (notification.type.startsWith('project-reference.')) {
      const action = notification.type.split('.').pop() ?? 'updated'
      const referenceTitle = typeof payload.reference_title === 'string' ? payload.reference_title : null

      const config: Record<string, { title: string; badge?: { label: string; tone: 'positive' | 'neutral' | 'warning' | 'danger' } }> = {
        suggested: { title: 'Reference suggested' },
        approved: { title: 'Reference approved', badge: { label: 'Approved', tone: 'positive' } },
        rejected: { title: 'Reference rejected', badge: { label: 'Rejected', tone: 'danger' } },
      }

      const c = config[action] || { title: `Reference ${action}` }

      return renderNotificationCard({
        key: notification.id,
        icon: <FilePenLine className="h-4 w-4" />,
        iconClassName: 'bg-purple-100 text-purple-600 dark:bg-purple-500/20 dark:text-purple-400',
        title: c.title,
        subtitle: actorName,
        badge: c.badge,
        detail: referenceTitle ?? undefined,
        timestamp,
      })
    }

    // Fallback
    return renderNotificationCard({
      key: notification.id,
      icon: <AlertCircle className="h-4 w-4" />,
      iconClassName: 'bg-gray-100 text-gray-500 dark:bg-slate-700 dark:text-slate-400',
      title: notification.type.replace(/[.-]/g, ' '),
      subtitle: actorName,
      timestamp,
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

    const topNotifications = notifications.slice(0, 15)
    return (
      <ul className="divide-y-0">
        {topNotifications.map((item) => renderNotification(item))}
      </ul>
    )
  }, [notifications, notificationsQuery.isError, notificationsQuery.isLoading])

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1.2fr,1fr]">
        <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800">
          <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">Project context</h2>
          <div className="mt-5 space-y-5">
            {/* Description */}
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Description</h3>
              <p className="mt-2 text-sm text-gray-700 dark:text-slate-300 whitespace-pre-line leading-relaxed">
                {descriptionText || <span className="text-gray-400 dark:text-slate-500 italic">No description captured yet.</span>}
              </p>
            </div>

            {/* Objectives */}
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Objectives</h3>
              <div className="mt-2">
                {objectivesList.length > 0 ? (
                  <ul className="space-y-2">
                    {objectivesList.map((objective, index) => (
                      <li key={`${objective}-${index}`} className="flex items-start gap-2.5">
                        <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700 dark:bg-indigo-400/20 dark:text-indigo-300">
                          {index + 1}
                        </span>
                        <span className="text-sm text-gray-700 dark:text-slate-300">{objective}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-400 dark:text-slate-500 italic">No objectives defined yet.</p>
                )}
              </div>
            </div>

            {/* Keywords */}
            {project.keywords && project.keywords.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Keywords</h3>
                <div className="mt-2 flex flex-wrap gap-2">
                  {project.keywords.map((keyword) => (
                    <span
                      key={keyword}
                      className="inline-flex rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300"
                    >
                      {keyword}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
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
