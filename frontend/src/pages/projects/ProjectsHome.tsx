import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LayoutGrid, List, RefreshCcw, Search, Clock } from 'lucide-react'
import { Link } from 'react-router-dom'
import { projectsAPI } from '../../services/api'
import { useAuth } from '../../contexts/AuthContext'
import { ProjectCreateInput, ProjectSummary } from '../../types'
import ProjectFormModal from '../../components/projects/ProjectFormModal'
// DISABLED FOR DEMO RECORDING
// import { useOnboarding } from '../../contexts/OnboardingContext'
// import WelcomeModal from '../../components/onboarding/WelcomeModal'
// import FeatureTour, { TourStep } from '../../components/onboarding/FeatureTour'

const formatDate = (value: string) => {
  try {
    return new Date(value).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return value
  }
}

const ProjectsHome = () => {
  const [searchTerm, setSearchTerm] = useState('')
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid')
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [creationError, setCreationError] = useState<string | null>(null)
  const [editingProject, setEditingProject] = useState<ProjectSummary | null>(null)
  const [editError, setEditError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const { user } = useAuth()
  // DISABLED FOR DEMO RECORDING
  // const { state: onboardingState, markWelcomeSeen, startTour, nextTourStep, endTour, markFirstProjectCreated } = useOnboarding()

  // Show welcome modal for first-time users
  // const [showWelcome, setShowWelcome] = useState(false)

  // useEffect(() => {
  //   // Show welcome modal if user hasn't seen it yet
  //   if (!onboardingState.hasSeenWelcome) {
  //     setShowWelcome(true)
  //   }
  // }, [onboardingState.hasSeenWelcome])

  // Tour steps for ProjectsHome
  // const tourSteps: TourStep[] = [
  //   {
  //     target: '[data-tour="create-project"]',
  //     title: 'Create Your First Project',
  //     content: 'Start by creating a project to organize your research. Projects help you collaborate with your team and keep everything in one place.',
  //     placement: 'bottom',
  //     action: {
  //       label: 'Create a project',
  //       onClick: () => {
  //         setIsCreateOpen(true)
  //         endTour()
  //       }
  //     }
  //   },
  //   {
  //     target: '[data-tour="search"]',
  //     title: 'Search Projects',
  //     content: 'Quickly find projects by searching for keywords, titles, or topics.',
  //     placement: 'bottom',
  //   },
  //   {
  //     target: '[data-tour="view-mode"]',
  //     title: 'Change View Mode',
  //     content: 'Switch between grid and table views to see your projects in the layout that works best for you.',
  //     placement: 'left',
  //   },
  // ]

  // const handleWelcomeClose = () => {
  //   setShowWelcome(false)
  //   markWelcomeSeen()
  // }

  // const handleWelcomeGetStarted = () => {
  //   setShowWelcome(false)
  //   markWelcomeSeen()
  //   // Start the feature tour if no projects exist
  //   if (projects.length === 0) {
  //     startTour(0)
  //   }
  // }

  const {
    data,
    isLoading,
    isFetching,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['projects'],
    queryFn: async () => {
      const response = await projectsAPI.list()
      return response.data
    },
  })

  const createProject = useMutation({
    mutationFn: async (payload: ProjectCreateInput) => {
      setCreationError(null)
      const response = await projectsAPI.create(payload)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setIsCreateOpen(false)
      // Mark first project as created for onboarding - DISABLED FOR DEMO RECORDING
      // if (!onboardingState.hasCreatedFirstProject) {
      //   markFirstProjectCreated()
      // }
    },
    onError: (error: unknown) => {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setCreationError(detail ?? 'Unable to create project. Please try again.')
    },
  })

  const updateProject = useMutation({
    mutationFn: async ({ projectId, payload }: { projectId: string; payload: ProjectCreateInput }) => {
      const response = await projectsAPI.update(projectId, payload)
      return response.data
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['project', variables.projectId] })
      setEditingProject(null)
      setEditError(null)
    },
    onError: (error: unknown) => {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setEditError(detail ?? 'Unable to update project. Please try again.')
    },
  })

  const projects = data?.projects ?? []
  const userId = user?.id

  const pendingInvitesQuery = useQuery({
    queryKey: ['project-invitations'],
    queryFn: async () => {
      const response = await projectsAPI.listPendingInvitations()
      return response.data?.invitations ?? []
    },
  })

  const acceptInvite = useMutation({
    mutationFn: async ({ projectId, memberId }: { projectId: string; memberId: string }) => {
      await projectsAPI.acceptInvitation(projectId, memberId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-invitations'] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
    onError: () => {
      alert('Failed to accept invitation. Please try again.')
    },
  })

  const declineInvite = useMutation({
    mutationFn: async ({ projectId, memberId }: { projectId: string; memberId: string }) => {
      await projectsAPI.declineInvitation(projectId, memberId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-invitations'] })
    },
    onError: () => {
      alert('Failed to decline invitation. Please try again.')
    },
  })

  const pendingInvites = pendingInvitesQuery.data ?? []

  const filteredProjects: ProjectSummary[] = useMemo(() => {
    const term = searchTerm.trim().toLowerCase()
    if (!term) return projects

    return projects.filter((project) => {
      const keywords = Array.isArray(project.keywords) ? project.keywords : []
      return (
        project.title.toLowerCase().includes(term) ||
        (project.idea?.toLowerCase().includes(term) ?? false) ||
        keywords.some((kw) => kw.toLowerCase().includes(term))
      )
    })
  }, [projects, searchTerm])

  const totalProjects = data?.total ?? 0

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-gray-900">Projects</h1>
            <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">
              {totalProjects} total
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-500">
            Spin up new initiatives or jump back into active collaborations.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative hidden sm:flex" data-tour="search">
            <div className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
              <Search className="h-4 w-4 text-gray-400" />
            </div>
            <input
              type="search"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              className="h-10 w-full rounded-full border border-gray-200 bg-white pl-9 pr-4 text-sm text-gray-700 shadow-sm placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="Search projects"
            />
          </div>
          <div className="flex rounded-full border border-gray-200 bg-white p-1 shadow-sm" data-tour="view-mode">
            <button
              type="button"
              onClick={() => setViewMode('grid')}
              className={`inline-flex h-9 w-9 items-center justify-center rounded-full ${
                viewMode === 'grid' ? 'bg-indigo-600 text-white' : 'text-gray-500 hover:bg-gray-100'
              }`}
              aria-label="Grid view"
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setViewMode('table')}
              className={`inline-flex h-9 w-9 items-center justify-center rounded-full ${
                viewMode === 'table' ? 'bg-indigo-600 text-white' : 'text-gray-500 hover:bg-gray-100'
              }`}
              aria-label="Table view"
            >
              <List className="h-4 w-4" />
            </button>
          </div>
          <button
            type="button"
            onClick={() => setIsCreateOpen(true)}
            className="inline-flex items-center rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
            data-tour="create-project"
          >
            New Project
          </button>
        </div>
      </header>

      <div className="sm:hidden">
        <div className="relative">
          <div className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
            <Search className="h-4 w-4 text-gray-400" />
      </div>
      <input
        type="search"
        value={searchTerm}
        onChange={(event) => setSearchTerm(event.target.value)}
        className="h-11 w-full rounded-full border border-gray-200 bg-white pl-9 pr-4 text-sm text-gray-700 shadow-sm placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        placeholder="Search projects"
      />
    </div>
  </div>

  {pendingInvitesQuery.isLoading ? (
    <div className="rounded-2xl border border-gray-200 bg-white p-6">
      <h3 className="text-base font-semibold text-gray-900 mb-3">Pending invitations</h3>
      <div className="text-sm text-gray-600">Loading…</div>
    </div>
  ) : pendingInvitesQuery.isError ? (
    <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
      <h3 className="text-base font-semibold">Pending invitations</h3>
      <p className="mt-1">We couldn&apos;t load project invitations right now.</p>
    </div>
  ) : pendingInvites.length > 0 ? (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-gray-900">Pending invitations</h2>
        <span className="text-xs font-medium text-gray-500">{pendingInvites.length} pending</span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {pendingInvites.map((invite) => (
          <div
            key={invite.member_id}
            className="flex h-full flex-col justify-between rounded-xl border border-dashed border-amber-300 bg-amber-50 p-5 shadow-sm"
          >
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-amber-700">
                <Clock className="h-4 w-4" /> Pending invitation
              </div>
              <h3 className="text-lg font-semibold text-gray-900 truncate" title={invite.project_title}>
                {invite.project_title}
              </h3>
              <p className="text-sm text-gray-600 capitalize">Role: {invite.role.toLowerCase()}</p>
              {invite.invited_at && (
                <p className="text-xs text-gray-500">Invited {new Date(invite.invited_at).toLocaleString()}</p>
              )}
              {invite.invited_by && (
                <p className="text-xs text-gray-500">Invited by {invite.invited_by}</p>
              )}
            </div>
            <div className="mt-4 flex items-center gap-2">
              <button
                type="button"
                onClick={() => acceptInvite.mutate({ projectId: invite.project_id, memberId: invite.member_id })}
                disabled={acceptInvite.isPending || declineInvite.isPending}
                className="inline-flex flex-1 items-center justify-center rounded-full bg-green-600 px-3 py-2 text-xs font-medium text-white shadow-sm hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Accept
              </button>
              <button
                type="button"
                onClick={() => declineInvite.mutate({ projectId: invite.project_id, memberId: invite.member_id })}
                disabled={acceptInvite.isPending || declineInvite.isPending}
                className="inline-flex flex-1 items-center justify-center rounded-full border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-600 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Decline
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  ) : null}

  {isError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
          <p className="font-medium">We couldn&apos;t load your projects.</p>
          <p className="mt-1">Try refreshing or check back in a moment.</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="mt-4 inline-flex items-center gap-2 rounded-md border border-transparent bg-red-600 px-3 py-2 text-xs font-medium text-white hover:bg-red-700"
          >
            <RefreshCcw className="h-4 w-4" /> Retry
          </button>
        </div>
      ) : isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, idx) => (
            <div
              key={idx}
              className="h-40 animate-pulse rounded-xl border border-gray-200 bg-white"
            />
          ))}
        </div>
      ) : filteredProjects.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-12 text-center">
          <h3 className="text-lg font-semibold text-gray-900">No projects yet</h3>
          <p className="mt-2 text-sm text-gray-500">
            {searchTerm
              ? 'Try a different search term or clear the filter to see all projects.'
              : 'Create your first project to begin tracking research ideas, references, and papers.'}
          </p>
          <button
            type="button"
            onClick={() => setIsCreateOpen(true)}
            className="mt-6 inline-flex items-center rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
          >
            Create a project
          </button>
        </div>
      ) : viewMode === 'grid' ? (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {filteredProjects.map((project) => {
          const keywords = Array.isArray(project.keywords) ? project.keywords : []
          const membershipStatus = project.current_user_status?.toLowerCase()
          const membershipRole = project.current_user_role?.toLowerCase()
          const canEditProject =
            project.created_by === userId ||
            (membershipStatus === 'accepted' && membershipRole === 'admin')
          return (
            <article
              key={project.id}
              className="flex h-full flex-col justify-between rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition hover:border-indigo-200 hover:shadow-md dark:border-slate-700 dark:bg-slate-800 dark:hover:border-indigo-400/60"
            >
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-slate-100">{project.title}</h3>
                    {project.idea && (
                      <p className="mt-2 line-clamp-2 text-sm text-gray-500 dark:text-slate-300">{project.idea}</p>
                    )}
                  </div>
                  <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600 dark:bg-slate-700 dark:text-slate-200">
                    {project.status || 'Active'}
                  </span>
                </div>
                {keywords.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {keywords.slice(0, 4).map((keyword) => (
                      <span
                        key={keyword}
                        className="inline-flex rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-400/10 dark:text-indigo-200"
                      >
                        {keyword}
                      </span>
                    ))}
                    {keywords.length > 4 && (
                      <span className="inline-flex rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-400/10 dark:text-indigo-200">
                        +{keywords.length - 4}
                      </span>
                    )}
                  </div>
                )}
              </div>
              <div className="mt-6 flex items-center justify-between text-xs text-gray-500 dark:text-slate-300">
                <span>Updated {formatDate(project.updated_at)}</span>
                <div className="flex items-center gap-3">
                  {canEditProject && (
                    <button
                      type="button"
                      onClick={() => {
                        setEditError(null)
                        setEditingProject(project)
                      }}
                      className="text-sm font-medium text-gray-500 transition-colors hover:text-indigo-600 dark:text-slate-300 dark:hover:text-indigo-300"
                    >
                      Edit
                    </button>
                  )}
                  <Link
                    to={`/projects/${project.id}`}
                    className="text-sm font-medium text-indigo-600 transition-colors hover:text-indigo-700 dark:text-indigo-300 dark:hover:text-indigo-200"
                  >
                    Open project →
                  </Link>
                </div>
              </div>
            </article>
          )
        })}
      </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-800">
          <table className="min-w-full divide-y divide-gray-100 dark:divide-slate-700">
            <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:bg-slate-800/70 dark:text-slate-300">
              <tr>
                <th className="px-6 py-3">Project</th>
                <th className="px-6 py-3">Scope</th>
                <th className="px-6 py-3">Keywords</th>
                <th className="px-6 py-3">Updated</th>
                <th className="px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 text-sm text-gray-700 dark:divide-slate-700 dark:text-slate-200">
              {filteredProjects.map((project) => {
                const keywords = Array.isArray(project.keywords) ? project.keywords : []
                return (
                  <tr key={project.id} className="hover:bg-gray-50 dark:hover:bg-slate-700/40">
                    <td className="px-6 py-4">
                      <div className="font-medium text-gray-900 dark:text-slate-100">{project.title}</div>
                      {project.idea && (
                        <div className="mt-1 text-xs text-gray-500 line-clamp-1 dark:text-slate-300">{project.idea}</div>
                      )}
                    </td>
                    <td className="px-6 py-4 text-gray-500 dark:text-slate-300">{project.scope || '—'}</td>
                    <td className="px-6 py-4 text-gray-500 dark:text-slate-300">
                      {keywords.length ? keywords.slice(0, 3).join(', ') : '—'}
                      {keywords.length > 3 && `, +${keywords.length - 3}`}
                    </td>
                    <td className="px-6 py-4 text-gray-500 dark:text-slate-300">{formatDate(project.updated_at)}</td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex justify-end gap-3">
                        <button
                          type="button"
                          onClick={() => {
                            setEditError(null)
                            setEditingProject(project)
                          }}
                          className="text-sm font-medium text-gray-500 hover:text-indigo-600"
                        >
                          Edit
                        </button>
                        <Link
                          to={`/projects/${project.id}`}
                          className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
                        >
                          Open
                        </Link>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <ProjectFormModal
        isOpen={isCreateOpen}
        mode="create"
        isSubmitting={createProject.isPending}
        error={creationError}
        onClose={() => {
          setCreationError(null)
          setIsCreateOpen(false)
        }}
        onSubmit={(payload) => createProject.mutate(payload)}
      />

      <ProjectFormModal
        isOpen={Boolean(editingProject)}
        mode="edit"
        isSubmitting={updateProject.isPending}
        error={editError}
        initialProject={editingProject ? {
          ...editingProject,
          keywords: Array.isArray(editingProject.keywords)
            ? editingProject.keywords
            : editingProject.keywords
            ? [editingProject.keywords]
            : [],
        } : undefined}
        onClose={() => {
          setEditError(null)
          setEditingProject(null)
        }}
        onSubmit={(payload) => {
          if (!editingProject) return
          updateProject.mutate({ projectId: editingProject.id, payload })
        }}
      />

      {isFetching && !isLoading && (
        <p className="text-xs text-gray-400">Refreshing projects…</p>
      )}

      {/* Onboarding Components - DISABLED FOR DEMO RECORDING */}
      {/*
      <WelcomeModal
        isOpen={showWelcome}
        onClose={handleWelcomeClose}
        onGetStarted={handleWelcomeGetStarted}
      />

      {onboardingState.currentTourStep !== null && (
        <FeatureTour
          steps={tourSteps}
          currentStep={onboardingState.currentTourStep}
          onNext={nextTourStep}
          onPrevious={() => {
            if (onboardingState.currentTourStep !== null && onboardingState.currentTourStep > 0) {
              startTour(onboardingState.currentTourStep - 1)
            }
          }}
          onSkip={endTour}
          onComplete={endTour}
        />
      )}
      */}
    </div>
  )
}

export default ProjectsHome
