import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { NavLink, Outlet, useNavigate, useOutletContext, useParams, useLocation } from 'react-router-dom'
import { ArrowLeft, Calendar, Users as UsersIcon, Trash2, Home, MessageSquare, FileEdit, Search, Video, BookOpen, FileText } from 'lucide-react'
import { projectDiscoveryAPI, projectsAPI } from '../../services/api'
import { ProjectCreateInput, ProjectDetail } from '../../types'
import ProjectFormModal from '../../components/projects/ProjectFormModal'
import { useAuth } from '../../contexts/AuthContext'
import ConfirmationModal from '../../components/common/ConfirmationModal'
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
      path: '',
      exact: true,
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
      label: 'Collaborate',
      path: 'collaborate',
      icon: UsersIcon,
      tooltip: 'Team chat and video meetings'
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
  const location = useLocation()
  const queryClient = useQueryClient()
  const [isEditOpen, setIsEditOpen] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
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

  const memberCount = useMemo(() => project?.members?.length ?? 0, [project])
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
    queryKey: ['project', projectId, 'discoveryPendingCount'],
    queryFn: async () => {
      if (!projectId) return 0
      const response = await projectDiscoveryAPI.getPendingCount(projectId)
      return response.data.pending
    },
    enabled: Boolean(projectId) && normalizedRole !== 'viewer',
    refetchInterval: 60000,
  })
  const pendingCount = pendingDiscovery.data ?? 0
  const hideProjectChrome = Boolean(paperId)

  const canEditProject = normalizedRole === 'admin'

  // localStorage tracking for Library/Discovery notifications (NEW NAVIGATION only)
  const storageKey = `library-discovery-${projectId}`

  const [prevCount, setPrevCount] = useState<number>(() => {
    const stored = localStorage.getItem(`${storageKey}-count`)
    return stored ? parseInt(stored, 10) : 0
  })

  const [hasViewedDiscovery, setHasViewedDiscovery] = useState<boolean>(() => {
    const stored = localStorage.getItem(`${storageKey}-viewed`)
    return stored === 'true'
  })

  // Check if user is on discovery page (both old and new routes)
  const isOnDiscoveryPage = location.pathname.includes('/discovery') || location.pathname.includes('/library/discover')

  // Track when user navigates to discovery page
  useEffect(() => {
    if (isOnDiscoveryPage && pendingCount > 0) {
      setHasViewedDiscovery(true)
      setPrevCount(pendingCount)
      localStorage.setItem(`${storageKey}-viewed`, 'true')
      localStorage.setItem(`${storageKey}-count`, pendingCount.toString())
    }
  }, [isOnDiscoveryPage, pendingCount, storageKey])

  // If count increased, mark as not viewed (new papers arrived)
  useEffect(() => {
    if (pendingCount > prevCount && prevCount > 0) {
      setHasViewedDiscovery(false)
      localStorage.setItem(`${storageKey}-viewed`, 'false')
    }
    setPrevCount(pendingCount)
    localStorage.setItem(`${storageKey}-count`, pendingCount.toString())
  }, [pendingCount, prevCount, storageKey])

  // Show notification if: there are badges AND user hasn't viewed them yet
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
      <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            onClick={() => navigate('/projects')}
            className="inline-flex items-center gap-2 text-sm font-medium text-gray-500 transition-colors hover:text-gray-700 dark:text-slate-300 dark:hover:text-slate-100"
          >
            <ArrowLeft className="h-4 w-4" />
            All projects
          </button>
          <div className="flex items-center gap-2">
            {canEditProject && (
              <button
                type="button"
                onClick={() => {
                  setEditError(null)
                  setIsEditOpen(true)
                }}
                className="inline-flex items-center rounded-full border border-indigo-200 px-4 py-2 text-sm font-medium text-indigo-600 transition-colors hover:bg-indigo-50 dark:border-indigo-400/50 dark:text-indigo-200 dark:hover:bg-indigo-400/10"
              >
                Edit project
              </button>
            )}
            {canEditProject && (
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                className="inline-flex items-center gap-2 rounded-full border border-red-200 px-4 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 dark:border-red-400/40 dark:text-red-200 dark:hover:bg-red-500/10"
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </button>
            )}
          </div>
        </div>
        <div className="space-y-4">
          {/* Title */}
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-slate-100">{project.title}</h1>

          {/* Metadata Row - compact inline display */}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-gray-500 dark:text-slate-400">
            <div className="flex items-center gap-1.5">
              <Calendar className="h-3.5 w-3.5" />
              <span>Updated {new Date(project.updated_at).toLocaleDateString()}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <UsersIcon className="h-3.5 w-3.5" />
              <span>{memberCount} member{memberCount === 1 ? '' : 's'}</span>
            </div>
          </div>
        </div>
        <nav className="mt-8 flex flex-wrap items-center gap-2 text-sm font-medium">
          {getNavigationMode() === 'new' ? (
            // NEW NAVIGATION: 4 simple tabs
            NEW_TAB_GROUPS.main.map(({ label, path, exact, icon: Icon, tooltip, badge }) => (
              <div key={label} className="relative">
                <NavLink
                  to={path ? `/projects/${project.id}/${path}` : `/projects/${project.id}`}
                  end={Boolean(exact)}
                  title={tooltip}
                  className={({ isActive }) =>
                    `inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 transition-colors ${
                      isActive ? 'bg-indigo-600 text-white' : 'text-gray-500 hover:bg-gray-100'
                    }`
                  }
                >
                  {Icon && <Icon className="h-4 w-4" />}
                  <span>{label}</span>
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
                  to={path ? `/projects/${project.id}/${path}` : `/projects/${project.id}`}
                  end={Boolean(exact)}
                  title={tooltip}
                  className={({ isActive }) =>
                    `inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 transition-colors ${
                      isActive ? 'bg-indigo-600 text-white' : 'text-gray-500 hover:bg-gray-100'
                    }`
                  }
                >
                  {Icon && <Icon className="h-4 w-4" />}
                  <span>{label}</span>
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
    </div>
  )
}

export default ProjectLayout
