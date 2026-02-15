import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { NavLink, Outlet, useNavigate, useOutletContext, useParams, useLocation } from 'react-router-dom'
import { ArrowLeft, Calendar, Users, Trash2, Home, MessageSquare, FileEdit, Search, Video, BookOpen, FileText, Settings, Sparkles } from 'lucide-react'
import { projectDiscoveryAPI, projectsAPI } from '../../services/api'
import { ProjectCreateInput, ProjectDetail } from '../../types'
import ProjectFormModal from '../../components/projects/ProjectFormModal'
import { useAuth } from '../../contexts/AuthContext'
import ConfirmationModal from '../../components/common/ConfirmationModal'
import ProjectSettingsModal from '../../components/projects/ProjectSettingsModal'
import { getProjectUrlId } from '../../utils/urlId'
import TabDropdown from '../../components/projects/TabDropdown'
import { getNavigationMode } from '../../config/navigation'

type ProjectOutletContext = {
  project: ProjectDetail
  currentRole: 'admin' | 'editor' | 'viewer'
}

export const useProjectContext = () => useOutletContext<ProjectOutletContext>()

// OLD NAVIGATION: Original 6-tab structure (will be used when USE_NEW_NAVIGATION = false)
const OLD_TAB_GROUPS = {
  standalone: [
    {
      label: 'Overview',
      path: '',
      exact: true,
      icon: Home,
      tooltip: 'Project overview, team, and recent activity'
    },
    {
      label: 'Papers',
      path: 'papers',
      icon: FileEdit,
      tooltip: 'Write and edit papers using LaTeX or rich editor'
    },
    {
      label: 'Discussion',
      path: 'discussion',
      icon: MessageSquare,
      tooltip: 'Team conversations with linked resources'
    },
    {
      label: 'Sync Space',
      path: 'sync-space',
      icon: Video,
      tooltip: 'Video calls with automatic transcription'
    },
  ],
  research: {
    label: 'Research',
    icon: Search,
    items: [
      {
        label: 'Find Papers',
        path: '/discovery',
        icon: Search,
        badge: 'discovery' as const,
        tooltip: 'Search for papers and run AI-powered discovery feeds'
      },
      {
        label: 'References',
        path: '/related-papers',
        icon: BookOpen,
        tooltip: 'Your collected papers for this project'
      },
    ]
  }
}

// NEW NAVIGATION: Simplified 4-tab structure with sub-sections
const NEW_TAB_GROUPS = {
  main: [
    {
      label: 'Overview',
      path: 'overview',
      icon: Home,
      tooltip: 'Project dashboard, team, and activity'
    },
    {
      label: 'Papers',
      path: 'papers',
      icon: FileText,
      tooltip: 'View and edit research papers'
    },
    {
      label: 'Scholar AI',
      path: 'discussion',
      icon: Sparkles,
      tooltip: 'AI-powered research assistant',
      animate: true,
    },
    {
      label: 'Library',
      path: 'library',
      icon: BookOpen,
      tooltip: 'Discover papers and manage references',
      badge: 'discovery' as const,
    },
  ]
}

const ProjectLayout = () => {
  const { projectId, paperId } = useParams<{ projectId: string; paperId?: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [isEditOpen, setIsEditOpen] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const deleteProjectMutation = useMutation({
    mutationFn: async (projectId: string) => {
      await projectsAPI.delete(projectId)
    },
    onSuccess: () => {
      setShowDeleteConfirm(false)
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      navigate('/projects')
    },
    onError: () => {
      alert('Failed to delete project. Please try again.')
    },
  })
  const { user } = useAuth()

  const {
    data,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['project', projectId],
    queryFn: async () => {
      if (!projectId) throw new Error('Missing project id')
      const response = await projectsAPI.get(projectId)
      return response.data
    },
    enabled: Boolean(projectId),
  })

  const project = data

  const memberCount = useMemo(() => project?.members?.filter(m => m.status === 'accepted').length ?? 0, [project])
  const currentUserId = user?.id
  const membership = project?.members?.find((member) => member.user_id === currentUserId)
  const membershipStatus = membership?.status?.toLowerCase()

  const normalizedRole = useMemo<'admin' | 'editor' | 'viewer'>(() => {
    if (!project || !currentUserId) {
      return 'viewer'
    }
    if (project.created_by === currentUserId) {
      return 'admin'
    }
    if (!membership || membershipStatus !== 'accepted') {
      return 'viewer'
    }
    const rawRole = (membership.role || '').toLowerCase()
    if (rawRole === 'owner') {
      return 'admin'
    }
    if (rawRole === 'reviewer') {
      return 'viewer'
    }
    if (rawRole === 'admin' || rawRole === 'editor') {
      return rawRole
    }
    return 'viewer'
  }, [project, currentUserId, membership, membershipStatus])

  // For viewers, hide the Research group (which contains Find Papers/Discovery)
  const showResearchGroup = normalizedRole !== 'viewer'

  const pendingDiscovery = useQuery({
    queryKey: ['project', projectId, 'discoveryPendingCount', 'auto'],
    queryFn: async () => {
      if (!projectId) return 0
      const response = await projectDiscoveryAPI.getPendingCount(projectId, 'auto')
      return response.data.pending
    },
    enabled: Boolean(projectId) && normalizedRole !== 'viewer',
    refetchInterval: 60000,
  })
  const pendingCount = pendingDiscovery.data ?? 0
  const hideProjectChrome = Boolean(paperId)

  const canEditProject = normalizedRole === 'admin'

  // Track whether user has viewed discovery since the last increase (dot indicator only)
  const storageKey = `library-discovery-${projectId}`
  const location = useLocation()

  const [prevCount, setPrevCount] = useState<number>(() => {
    const stored = localStorage.getItem(`${storageKey}-count`)
    return stored ? parseInt(stored, 10) : 0
  })

  const [hasViewedDiscovery, setHasViewedDiscovery] = useState<boolean>(() => {
    const stored = localStorage.getItem(`${storageKey}-viewed`)
    return stored === 'true'
  })

  const isOnDiscoveryPage = location.pathname.includes('/discovery') || location.pathname.includes('/library/discover')

  useEffect(() => {
    if (isOnDiscoveryPage && pendingCount > 0) {
      setHasViewedDiscovery(true)
      localStorage.setItem(`${storageKey}-viewed`, 'true')
    }
  }, [isOnDiscoveryPage, pendingCount, storageKey])

  useEffect(() => {
    if (pendingCount > prevCount && prevCount >= 0) {
      setHasViewedDiscovery(false)
      localStorage.setItem(`${storageKey}-viewed`, 'false')
    }
    setPrevCount(pendingCount)
    localStorage.setItem(`${storageKey}-count`, pendingCount.toString())
  }, [pendingCount, prevCount, storageKey])

  // Dot indicator only; numeric badge comes from pendingCount elsewhere
  const hasLibraryNotifications = pendingCount > 0 && !hasViewedDiscovery

  useEffect(() => {
    if (hideProjectChrome && isEditOpen) {
      setEditError(null)
      setIsEditOpen(false)
    }
  }, [hideProjectChrome, isEditOpen])

  const updateProject = useMutation({
    mutationFn: async ({ projectId: id, payload }: { projectId: string; payload: ProjectCreateInput }) => {
      const response = await projectsAPI.update(id, payload)
      return response.data
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['project', variables.projectId] })
      setIsEditOpen(false)
      setEditError(null)
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } }
      setEditError(axiosError?.response?.data?.detail ?? 'Unable to update project right now.')
    },
  })

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-28 w-full animate-pulse rounded-2xl bg-white shadow-sm" />
        <div className="h-64 w-full animate-pulse rounded-2xl bg-white shadow-sm" />
      </div>
    )
  }

  if (isError || !project) {
    return (
      <div className="max-w-xl rounded-2xl border border-red-200 bg-red-50 p-8 text-sm text-red-700">
        <h2 className="text-base font-semibold">Project unavailable</h2>
        <p className="mt-2">
          We couldn&apos;t load that project. It may have been removed or you may no longer have access.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => navigate('/projects')}
            className="inline-flex items-center rounded-full bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            Back to projects
          </button>
          <button
            type="button"
            onClick={() => refetch()}
            className="inline-flex items-center rounded-full border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-100"
          >
            Try again
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {!hideProjectChrome && (
      <div className="rounded-2xl border border-gray-200 bg-white p-4 sm:p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            onClick={() => navigate('/projects')}
            className="inline-flex items-center gap-2 text-sm font-medium text-gray-500 transition-colors hover:text-gray-700 dark:text-slate-300 dark:hover:text-slate-100"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="sm:inline">All projects</span>
          </button>
          <div className="flex items-center gap-2">
            {canEditProject && (
              <button
                type="button"
                onClick={() => setIsSettingsOpen(true)}
                className="inline-flex items-center gap-1 sm:gap-2 rounded-full border border-gray-200 px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                title="Project AI Settings"
              >
                <Settings className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                <span className="hidden sm:inline">Settings</span>
              </button>
            )}
            {canEditProject && (
              <button
                type="button"
                onClick={() => {
                  setEditError(null)
                  setIsEditOpen(true)
                }}
                className="inline-flex items-center rounded-full border border-indigo-200 px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-indigo-600 transition-colors hover:bg-indigo-50 dark:border-indigo-400/50 dark:text-indigo-200 dark:hover:bg-indigo-400/10"
              >
                <span className="hidden sm:inline">Edit project</span>
                <span className="sm:hidden">Edit</span>
              </button>
            )}
            {canEditProject && (
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                className="inline-flex items-center gap-1 sm:gap-2 rounded-full border border-red-200 px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-red-600 transition-colors hover:bg-red-50 dark:border-red-400/40 dark:text-red-200 dark:hover:bg-red-500/10"
              >
                <Trash2 className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                <span className="hidden sm:inline">Delete</span>
              </button>
            )}
          </div>
        </div>
        <div className="space-y-3 sm:space-y-4">
          {/* Title */}
          <h1 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-slate-100 break-words">{project.title}</h1>

          {/* Metadata Row - compact inline display */}
          <div className="flex flex-wrap items-center gap-x-4 sm:gap-x-5 gap-y-2 text-xs sm:text-sm text-gray-500 dark:text-slate-400">
            <div className="flex items-center gap-1.5">
              <Calendar className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
              <span>Updated {new Date(project.updated_at).toLocaleDateString()}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Users className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
              <span>{memberCount} member{memberCount === 1 ? '' : 's'}</span>
            </div>
          </div>
        </div>
        <nav className="mt-6 sm:mt-8 flex flex-wrap items-center gap-1.5 sm:gap-2 text-xs sm:text-sm font-medium overflow-x-auto pb-1">
          {getNavigationMode() === 'new' ? (
            // NEW NAVIGATION: 4 simple tabs
            NEW_TAB_GROUPS.main.map(({ label, path, icon: Icon, tooltip, badge, animate }) => (
              <div key={label} className="relative flex-shrink-0">
                <NavLink
                  to={`/projects/${getProjectUrlId(project)}/${path}`}
                  end={path === 'discussion'}
                  title={tooltip}
                  className={({ isActive }) =>
                    `inline-flex items-center gap-1 sm:gap-1.5 rounded-full px-2.5 py-1 sm:px-3 sm:py-1.5 transition-colors whitespace-nowrap ${
                      isActive ? 'bg-indigo-600 text-white' : 'text-gray-500 hover:bg-gray-100 dark:text-slate-400 dark:hover:bg-slate-700'
                    }${animate ? ' group' : ''}`
                  }
                >
                  {Icon && <Icon className={`h-3.5 w-3.5 sm:h-4 sm:w-4${animate ? ' transition-all duration-300 group-hover:scale-110 group-hover:drop-shadow-[0_0_6px_rgba(99,102,241,0.6)]' : ''}`} />}
                  <span className="hidden xs:inline sm:inline">{label}</span>
                </NavLink>
                {badge === 'discovery' && hasLibraryNotifications && (
                  <span
                    className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-red-500 shadow-sm ring-2 ring-white"
                    title={`${pendingCount} new paper${pendingCount === 1 ? '' : 's'} discovered`}
                  />
                )}
              </div>
            ))
          ) : (
            // OLD NAVIGATION: Original 6 tabs with dropdown
            <>
              {OLD_TAB_GROUPS.standalone.map(({ label, path, exact, icon: Icon, tooltip }) => (
                <NavLink
                  key={label}
                  to={path ? `/projects/${getProjectUrlId(project)}/${path}` : `/projects/${getProjectUrlId(project)}`}
                  end={Boolean(exact)}
                  title={tooltip}
                  className={({ isActive }) =>
                    `inline-flex items-center gap-1 sm:gap-1.5 rounded-full px-2.5 py-1 sm:px-3 sm:py-1.5 transition-colors whitespace-nowrap flex-shrink-0 ${
                      isActive ? 'bg-indigo-600 text-white' : 'text-gray-500 hover:bg-gray-100 dark:text-slate-400 dark:hover:bg-slate-700'
                    }`
                  }
                >
                  {Icon && <Icon className="h-3.5 w-3.5 sm:h-4 sm:w-4" />}
                  <span className="hidden xs:inline sm:inline">{label}</span>
                </NavLink>
              ))}

              {showResearchGroup && (
                <TabDropdown
                  label={OLD_TAB_GROUPS.research.label}
                  icon={OLD_TAB_GROUPS.research.icon}
                  items={OLD_TAB_GROUPS.research.items.map(item => ({
                    ...item,
                    badge: item.badge === 'discovery' ? pendingCount : undefined
                  }))}
                  projectId={project.id}
                />
              )}
            </>
          )}
        </nav>
      </div>
      )}

      <Outlet context={{ project, currentRole: normalizedRole }} />

      {!hideProjectChrome && (
      <ProjectFormModal
        isOpen={isEditOpen}
        mode="edit"
        isSubmitting={updateProject.isPending}
        error={editError}
        initialProject={{
          title: project.title,
          idea: project.idea ?? undefined,
          scope: project.scope ?? undefined,
          keywords: Array.isArray(project.keywords) ? project.keywords : project.keywords ? [project.keywords] : [],
        }}
        onClose={() => {
          setEditError(null)
          setIsEditOpen(false)
        }}
        onSubmit={(payload) => {
          if (!projectId) return
          updateProject.mutate({ projectId, payload })
        }}
      />
      )}
      <ConfirmationModal
        isOpen={showDeleteConfirm}
        title="Delete project"
        description="This will permanently remove the project and its membership. This action cannot be undone."
        confirmLabel={deleteProjectMutation.isPending ? 'Deleting…' : 'Delete project'}
        confirmTone="danger"
        isSubmitting={deleteProjectMutation.isPending}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={() => {
          if (!projectId) return
          deleteProjectMutation.mutate(projectId)
        }}
      />
      {project && (
        <ProjectSettingsModal
          project={project}
          isOpen={isSettingsOpen}
          onClose={() => setIsSettingsOpen(false)}
        />
      )}
    </div>
  )
}

export default ProjectLayout
