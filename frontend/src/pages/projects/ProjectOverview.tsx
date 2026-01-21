import { ReactNode, useMemo, useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  AlertCircle, Bell, FilePenLine, FilePlus, FolderPlus, Loader2, Settings,
  UserMinus, UserPlus, UserX, Video, Check, ChevronDown,
  FileText, BookOpen, Search, MessageSquare, Sparkles, X, Target
} from 'lucide-react'
import ProjectTeamManager from '../../components/projects/ProjectTeamManager'
import { useProjectContext } from './ProjectLayout'
import { projectNotificationsAPI, researchPapersAPI, projectReferencesAPI } from '../../services/api'
import { ProjectNotification } from '../../types'

const ProjectOverview = () => {
  const { project } = useProjectContext()
  const projectId = project?.id
  const navigate = useNavigate()

  // Objectives completion state (stored in localStorage)
  const [completedObjectives, setCompletedObjectives] = useState<Set<number>>(() => {
    if (typeof window === 'undefined') return new Set()
    const stored = localStorage.getItem(`project-objectives-${projectId}`)
    return stored ? new Set(JSON.parse(stored)) : new Set()
  })

  // Objectives modal state
  const [objectivesModalOpen, setObjectivesModalOpen] = useState(false)
  const VISIBLE_OBJECTIVES_COUNT = 8

  // Parse objectives from project scope
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

  // Save completed objectives to localStorage
  useEffect(() => {
    if (projectId) {
      localStorage.setItem(
        `project-objectives-${projectId}`,
        JSON.stringify([...completedObjectives])
      )
    }
  }, [completedObjectives, projectId])

  const toggleObjective = (index: number) => {
    setCompletedObjectives(prev => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  // Fetch project stats
  const papersQuery = useQuery({
    queryKey: ['project', projectId, 'papers'],
    queryFn: async () => {
      if (!projectId) return { papers: [], total: 0 }
      const response = await researchPapersAPI.getPapers({ projectId, limit: 100 })
      return response.data
    },
    enabled: Boolean(projectId),
    staleTime: 60_000,
  })

  const referencesQuery = useQuery({
    queryKey: ['project', projectId, 'references'],
    queryFn: async () => {
      if (!projectId) return { references: [] }
      const response = await projectReferencesAPI.list(projectId, { status: 'approved' })
      return response.data
    },
    enabled: Boolean(projectId),
    staleTime: 60_000,
  })

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

  const paperCount = papersQuery.data?.total ?? papersQuery.data?.papers?.length ?? 0
  const referenceCount = referencesQuery.data?.references?.length ?? 0
  const notifications = notificationsQuery.data ?? []

  const descriptionText = project.idea?.trim() || ''

  const completionPercentage = objectivesList.length > 0
    ? Math.round((completedObjectives.size / objectivesList.length) * 100)
    : 0

  const visibleObjectives = objectivesList.slice(0, VISIBLE_OBJECTIVES_COUNT)
  const hasMoreObjectives = objectivesList.length > VISIBLE_OBJECTIVES_COUNT

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

    // Empty state with quick actions
    if (notifications.length === 0) {
      return (
        <div className="rounded-xl border border-dashed border-gray-300 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/60 p-6">
          <div className="text-center mb-4">
            <Sparkles className="h-8 w-8 text-indigo-400 mx-auto mb-2" />
            <p className="text-sm text-gray-600 dark:text-slate-300 font-medium">Get started with your project</p>
            <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">Activity will appear here as you collaborate</p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <button
              onClick={() => navigate(`/projects/${projectId}/papers`)}
              className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:border-indigo-300 dark:hover:border-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition-colors group"
            >
              <FileText className="h-5 w-5 text-gray-400 group-hover:text-indigo-600 dark:group-hover:text-indigo-400" />
              <span className="text-xs font-medium text-gray-600 dark:text-slate-300 group-hover:text-indigo-600 dark:group-hover:text-indigo-400">New Paper</span>
            </button>
            <button
              onClick={() => navigate(`/projects/${projectId}/library/discover`)}
              className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:border-indigo-300 dark:hover:border-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition-colors group"
            >
              <Search className="h-5 w-5 text-gray-400 group-hover:text-indigo-600 dark:group-hover:text-indigo-400" />
              <span className="text-xs font-medium text-gray-600 dark:text-slate-300 group-hover:text-indigo-600 dark:group-hover:text-indigo-400">Find Papers</span>
            </button>
            <button
              onClick={() => navigate(`/projects/${projectId}/collaborate`)}
              className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:border-indigo-300 dark:hover:border-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition-colors group"
            >
              <MessageSquare className="h-5 w-5 text-gray-400 group-hover:text-indigo-600 dark:group-hover:text-indigo-400" />
              <span className="text-xs font-medium text-gray-600 dark:text-slate-300 group-hover:text-indigo-600 dark:group-hover:text-indigo-400">Discussion</span>
            </button>
            <button
              onClick={() => navigate(`/projects/${projectId}/library`)}
              className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:border-indigo-300 dark:hover:border-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition-colors group"
            >
              <BookOpen className="h-5 w-5 text-gray-400 group-hover:text-indigo-600 dark:group-hover:text-indigo-400" />
              <span className="text-xs font-medium text-gray-600 dark:text-slate-300 group-hover:text-indigo-600 dark:group-hover:text-indigo-400">References</span>
            </button>
          </div>
        </div>
      )
    }

    const topNotifications = notifications.slice(0, 15)
    return (
      <ul className="divide-y-0">
        {topNotifications.map((item) => renderNotification(item))}
      </ul>
    )
  }, [notifications, notificationsQuery.isError, notificationsQuery.isLoading, projectId, navigate])

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1.2fr,1fr] items-start">
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

            {/* Objectives with progress tracking */}
            <div>
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">Objectives</h3>
                {objectivesList.length > 0 && (
                  <div className="flex items-center gap-2">
                    <div className="w-20 h-1.5 bg-gray-200 dark:bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-emerald-500 dark:bg-emerald-400 rounded-full transition-all duration-300"
                        style={{ width: `${completionPercentage}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-500 dark:text-slate-400">{completionPercentage}%</span>
                  </div>
                )}
              </div>
              <div className="mt-2">
                {objectivesList.length > 0 ? (
                  <>
                    <ul className="space-y-2">
                      {visibleObjectives.map((objective, index) => (
                        <li
                          key={`${objective}-${index}`}
                          className="flex items-start gap-2.5 group cursor-pointer"
                          onClick={() => toggleObjective(index)}
                        >
                          <button
                            type="button"
                            className={`flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border-2 transition-all ${
                              completedObjectives.has(index)
                                ? 'bg-emerald-500 border-emerald-500 dark:bg-emerald-400 dark:border-emerald-400'
                                : 'border-gray-300 dark:border-slate-600 group-hover:border-indigo-400 dark:group-hover:border-indigo-400'
                            }`}
                          >
                            {completedObjectives.has(index) ? (
                              <Check className="h-3 w-3 text-white" />
                            ) : (
                              <span className="text-[10px] font-semibold text-gray-400 dark:text-slate-500 group-hover:text-indigo-500">{index + 1}</span>
                            )}
                          </button>
                          <span className={`text-sm transition-all ${
                            completedObjectives.has(index)
                              ? 'text-gray-400 dark:text-slate-500 line-through'
                              : 'text-gray-700 dark:text-slate-300'
                          }`}>
                            {objective}
                          </span>
                        </li>
                      ))}
                    </ul>
                    {hasMoreObjectives && (
                      <button
                        onClick={() => setObjectivesModalOpen(true)}
                        className="mt-3 flex items-center gap-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors"
                      >
                        <ChevronDown className="h-3.5 w-3.5" />
                        View all {objectivesList.length} objectives
                      </button>
                    )}
                  </>
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

        {/* Right column: Stats + Team */}
        <div className="space-y-6">
          {/* Project Stats */}
          <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800">
            <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100 mb-4">Project Stats</h2>
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center p-3 rounded-xl bg-gray-50 dark:bg-slate-700/50">
                <div className="text-2xl font-bold text-gray-900 dark:text-slate-100">{paperCount}</div>
                <div className="text-xs text-gray-500 dark:text-slate-400 mt-1">Papers</div>
              </div>
              <div className="text-center p-3 rounded-xl bg-gray-50 dark:bg-slate-700/50">
                <div className="text-2xl font-bold text-gray-900 dark:text-slate-100">{referenceCount}</div>
                <div className="text-xs text-gray-500 dark:text-slate-400 mt-1">References</div>
              </div>
              <div className="text-center p-3 rounded-xl bg-gray-50 dark:bg-slate-700/50">
                <div className="text-2xl font-bold text-gray-900 dark:text-slate-100">{project.members?.length ?? 1}</div>
                <div className="text-xs text-gray-500 dark:text-slate-400 mt-1">Members</div>
              </div>
            </div>
          </section>

          {/* Team Section */}
          <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800">
            <ProjectTeamManager />
          </section>
        </div>
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

      {/* Objectives Modal */}
      {objectivesModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setObjectivesModalOpen(false)}
          />
          <div className="relative z-10 w-full max-w-lg mx-4 max-h-[80vh] flex flex-col rounded-2xl border border-gray-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-800">
            {/* Header */}
            <div className="flex items-center justify-between p-5 border-b border-gray-200 dark:border-slate-700">
              <div className="flex items-center gap-2">
                <Target className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">
                  Project Objectives
                </h2>
              </div>
              <div className="flex items-center gap-3">
                {objectivesList.length > 0 && (
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1.5 bg-gray-200 dark:bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-emerald-500 dark:bg-emerald-400 rounded-full transition-all duration-300"
                        style={{ width: `${completionPercentage}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-500 dark:text-slate-400">{completionPercentage}%</span>
                  </div>
                )}
                <button
                  onClick={() => setObjectivesModalOpen(false)}
                  className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-slate-200 dark:hover:bg-slate-700 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-5">
              <ul className="space-y-3">
                {objectivesList.map((objective, index) => (
                  <li
                    key={`modal-${objective}-${index}`}
                    className="flex items-start gap-3 group cursor-pointer p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-slate-700/50 transition-colors"
                    onClick={() => toggleObjective(index)}
                  >
                    <button
                      type="button"
                      className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border-2 transition-all ${
                        completedObjectives.has(index)
                          ? 'bg-emerald-500 border-emerald-500 dark:bg-emerald-400 dark:border-emerald-400'
                          : 'border-gray-300 dark:border-slate-600 group-hover:border-indigo-400 dark:group-hover:border-indigo-400'
                      }`}
                    >
                      {completedObjectives.has(index) ? (
                        <Check className="h-3.5 w-3.5 text-white" />
                      ) : (
                        <span className="text-xs font-semibold text-gray-400 dark:text-slate-500 group-hover:text-indigo-500">{index + 1}</span>
                      )}
                    </button>
                    <span className={`text-sm transition-all ${
                      completedObjectives.has(index)
                        ? 'text-gray-400 dark:text-slate-500 line-through'
                        : 'text-gray-700 dark:text-slate-300'
                    }`}>
                      {objective}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ProjectOverview
