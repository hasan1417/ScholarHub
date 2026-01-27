import { useEffect, useMemo, useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  LayoutGrid,
  List,
  RefreshCcw,
  Search,
  Clock,
  ArrowUpDown,
  ChevronDown,
  Pin,
  Star,
  Sparkles,
  FolderPlus,
  FileText,
  BookOpen,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { projectsAPI } from '../../services/api'
import { useAuth } from '../../contexts/AuthContext'
import { ProjectCreateInput, ProjectSummary } from '../../types'
import ProjectFormModal from '../../components/projects/ProjectFormModal'
import { getProjectUrlId } from '../../utils/urlId'

const PINNED_STORAGE_KEY = 'scholarhub_pinned_projects'

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

const getStatusColor = (status: string) => {
  switch (status?.toLowerCase()) {
    case 'active':
      return 'bg-green-100 text-green-800 dark:bg-green-500/20 dark:text-green-400'
    case 'completed':
      return 'bg-blue-100 text-blue-800 dark:bg-blue-500/20 dark:text-blue-400'
    case 'archived':
      return 'bg-gray-100 text-gray-800 dark:bg-gray-500/20 dark:text-gray-400'
    case 'draft':
      return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-500/20 dark:text-yellow-400'
    default:
      return 'bg-gray-100 text-gray-800 dark:bg-gray-500/20 dark:text-gray-400'
  }
}

type FilterTab = 'all' | 'my' | 'shared'
type SortOption = 'updated' | 'created' | 'title'

const ProjectsHome = () => {
  const [searchTerm, setSearchTerm] = useState('')
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid')
  const [filterTab, setFilterTab] = useState<FilterTab>('all')
  const [sortOption, setSortOption] = useState<SortOption>('updated')
  const [showSortMenu, setShowSortMenu] = useState(false)
  const [pinnedIds, setPinnedIds] = useState<string[]>([])
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [creationError, setCreationError] = useState<string | null>(null)
  const [editingProject, setEditingProject] = useState<ProjectSummary | null>(null)
  const [editError, setEditError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const navigate = useNavigate()
  const userId = user?.id

  // Load pinned from localStorage
  useEffect(() => {
    try {
      const stored = localStorage.getItem(PINNED_STORAGE_KEY)
      if (stored) setPinnedIds(JSON.parse(stored))
    } catch {}
  }, [])

  // Toggle pin
  const togglePin = useCallback((projectId: string) => {
    setPinnedIds((prev) => {
      const next = prev.includes(projectId)
        ? prev.filter((id) => id !== projectId)
        : [...prev, projectId]
      localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }, [])

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

  // Filter, sort, and separate pinned
  const { pinnedProjects, unpinnedProjects, filteredProjects } = useMemo(() => {
    let filtered = projects

    // Filter by tab
    if (filterTab === 'my') {
      filtered = filtered.filter((p) => p.created_by === userId)
    } else if (filterTab === 'shared') {
      filtered = filtered.filter((p) => p.created_by !== userId)
    }

    // Filter by search
    const term = searchTerm.trim().toLowerCase()
    if (term) {
      filtered = filtered.filter((project) => {
        const keywords = Array.isArray(project.keywords) ? project.keywords : []
        return (
          project.title.toLowerCase().includes(term) ||
          (project.idea?.toLowerCase().includes(term) ?? false) ||
          keywords.some((kw) => kw.toLowerCase().includes(term))
        )
      })
    }

    // Sort
    const sorted = [...filtered].sort((a, b) => {
      switch (sortOption) {
        case 'title':
          return a.title.localeCompare(b.title)
        case 'created':
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        case 'updated':
        default:
          return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      }
    })

    // Separate pinned
    const pinned = sorted.filter((p) => pinnedIds.includes(p.id))
    const unpinned = sorted.filter((p) => !pinnedIds.includes(p.id))

    return { pinnedProjects: pinned, unpinnedProjects: unpinned, filteredProjects: sorted }
  }, [projects, filterTab, searchTerm, sortOption, pinnedIds, userId])

  const totalProjects = data?.total ?? 0

  // Handle opening a project
  const handleOpenProject = (project: ProjectSummary) => {
    navigate(`/projects/${getProjectUrlId(project)}`)
  }

  const sortLabels: Record<SortOption, string> = {
    updated: 'Recently Updated',
    created: 'Recently Created',
    title: 'Alphabetical',
  }

  // Project card component - Option 5: Gradient Header
  const ProjectCard = ({ project, isPinned }: { project: ProjectSummary; isPinned: boolean }) => {
    const keywords = Array.isArray(project.keywords) ? project.keywords : []
    const memberCount = project.members?.filter((m) => m.status === 'accepted').length ?? 0

    return (
      <article
        className={`group relative flex h-full flex-col rounded-xl border bg-white overflow-hidden transition-all hover:shadow-md dark:bg-slate-800 ${
          isPinned
            ? 'border-amber-200 dark:border-amber-500/30'
            : 'border-gray-200 dark:border-slate-700'
        }`}
      >
        {/* Header Stripe */}
        <div className={`h-1 sm:h-1.5 ${isPinned ? 'bg-amber-500' : 'bg-indigo-500'}`}></div>

        {/* Quick Actions - always visible on mobile, hover on desktop */}
        <div className="absolute top-3 sm:top-4 right-3 sm:right-4 flex items-center gap-1 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity z-10">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              togglePin(project.id)
            }}
            className={`p-1 sm:p-1.5 rounded-lg transition-colors ${
              isPinned
                ? 'bg-amber-100 text-amber-600 dark:bg-amber-500/20 dark:text-amber-400'
                : 'bg-white/90 dark:bg-slate-700/90 hover:bg-gray-100 dark:hover:bg-slate-600 text-gray-400 hover:text-amber-500 shadow-sm'
            }`}
            title={isPinned ? 'Unpin project' : 'Pin project'}
          >
            {isPinned ? <Star className="h-3.5 w-3.5 sm:h-4 sm:w-4 fill-current" /> : <Pin className="h-3.5 w-3.5 sm:h-4 sm:w-4" />}
          </button>
        </div>

        <div className="p-3 sm:p-5 flex flex-col flex-1">
          {/* Title */}
          <div className="flex items-start gap-1.5 sm:gap-2">
            {isPinned && (
              <Star className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-amber-500 fill-amber-500 mt-0.5 flex-shrink-0" />
            )}
            <h3 className="text-sm sm:text-base font-semibold text-gray-900 dark:text-white line-clamp-2 sm:line-clamp-1 pr-6">
              {project.title}
            </h3>
          </div>

          {/* Description */}
          {project.idea && (
            <p className="mt-1.5 sm:mt-2 text-xs sm:text-sm text-gray-500 dark:text-slate-400 line-clamp-2">
              {project.idea}
            </p>
          )}

          {/* Keywords */}
          {keywords.length > 0 && (
            <div className="mt-2 sm:mt-3 flex flex-wrap gap-1 sm:gap-1.5">
              {keywords.slice(0, 3).map((kw) => (
                <span
                  key={kw}
                  className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] sm:text-xs font-medium text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400"
                >
                  {kw}
                </span>
              ))}
              {keywords.length > 3 && (
                <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] sm:text-xs font-medium text-gray-500 dark:bg-slate-700 dark:text-slate-400">
                  +{keywords.length - 3}
                </span>
              )}
            </div>
          )}

          {/* Spacer */}
          <div className="flex-1 min-h-3 sm:min-h-4" />

          {/* Footer with stats */}
          <div className="mt-3 sm:mt-4 flex items-center justify-between text-[10px] sm:text-xs text-gray-400 dark:text-slate-500">
            <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
              <span>{project.paper_count ?? 0} papers</span>
              <span className="hidden xs:inline">·</span>
              <span className="hidden xs:inline">{project.reference_count ?? 0} refs</span>
              <span className="hidden sm:inline">·</span>
              <span className="hidden sm:inline">{memberCount} members</span>
            </div>
            <button
              type="button"
              onClick={() => handleOpenProject(project)}
              className="font-medium text-indigo-600 transition-colors hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300 text-xs sm:text-sm"
            >
              Open →
            </button>
          </div>
        </div>
      </article>
    )
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <header className="flex flex-col gap-4 sm:gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2 sm:gap-3">
            <h1 className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-white">Projects</h1>
            <span className="rounded-full bg-indigo-50 px-2 py-0.5 sm:px-3 sm:py-1 text-[10px] sm:text-xs font-medium text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300">
              {totalProjects} total
            </span>
          </div>
          <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-slate-400 hidden sm:block">
            Spin up new initiatives or jump back into active collaborations.
          </p>
        </div>
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="relative hidden sm:flex" data-tour="search">
            <div className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
              <Search className="h-4 w-4 text-gray-400" />
            </div>
            <input
              type="search"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              className="h-10 w-full rounded-full border border-gray-200 bg-white pl-9 pr-4 text-sm text-gray-700 shadow-sm placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-white dark:placeholder:text-slate-400"
              placeholder="Search projects"
            />
          </div>
          {/* Hide view mode toggle on mobile - always use grid on small screens */}
          <div className="hidden sm:flex rounded-full border border-gray-200 bg-white p-1 shadow-sm dark:border-slate-600 dark:bg-slate-700" data-tour="view-mode">
            <button
              type="button"
              onClick={() => setViewMode('grid')}
              className={`inline-flex h-9 w-9 items-center justify-center rounded-full ${
                viewMode === 'grid' ? 'bg-indigo-600 text-white' : 'text-gray-500 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-600'
              }`}
              aria-label="Grid view"
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setViewMode('table')}
              className={`inline-flex h-9 w-9 items-center justify-center rounded-full ${
                viewMode === 'table' ? 'bg-indigo-600 text-white' : 'text-gray-500 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-600'
              }`}
              aria-label="Table view"
            >
              <List className="h-4 w-4" />
            </button>
          </div>
          <button
            type="button"
            onClick={() => setIsCreateOpen(true)}
            className="inline-flex items-center rounded-full bg-indigo-600 px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
            data-tour="create-project"
          >
            <span className="sm:hidden">+ New</span>
            <span className="hidden sm:inline">New Project</span>
          </button>
        </div>
      </header>

      {/* Mobile Search */}
      <div className="sm:hidden">
        <div className="relative">
          <div className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
            <Search className="h-4 w-4 text-gray-400 dark:text-slate-500" />
          </div>
          <input
            type="search"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            className="h-11 w-full rounded-full border border-gray-200 bg-white pl-9 pr-4 text-sm text-gray-700 shadow-sm placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-white dark:placeholder:text-slate-400"
            placeholder="Search projects"
          />
        </div>
      </div>

      {/* Filter & Sort Bar */}
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        {/* Filter Tabs */}
        <div className="flex rounded-lg border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700 p-0.5 sm:p-1 overflow-x-auto">
          <button
            type="button"
            onClick={() => setFilterTab('all')}
            className={`px-2 py-1 sm:px-3 sm:py-1.5 text-xs sm:text-sm font-medium rounded-md transition-colors whitespace-nowrap ${
              filterTab === 'all'
                ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300'
                : 'text-gray-600 dark:text-slate-300 hover:text-gray-900 dark:hover:text-white'
            }`}
          >
            All
          </button>
          <button
            type="button"
            onClick={() => setFilterTab('my')}
            className={`px-2 py-1 sm:px-3 sm:py-1.5 text-xs sm:text-sm font-medium rounded-md transition-colors whitespace-nowrap ${
              filterTab === 'my'
                ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300'
                : 'text-gray-600 dark:text-slate-300 hover:text-gray-900 dark:hover:text-white'
            }`}
          >
            <span className="sm:hidden">Mine</span>
            <span className="hidden sm:inline">My Projects</span>
          </button>
          <button
            type="button"
            onClick={() => setFilterTab('shared')}
            className={`px-2 py-1 sm:px-3 sm:py-1.5 text-xs sm:text-sm font-medium rounded-md transition-colors whitespace-nowrap ${
              filterTab === 'shared'
                ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300'
                : 'text-gray-600 dark:text-slate-300 hover:text-gray-900 dark:hover:text-white'
            }`}
          >
            <span className="sm:hidden">Shared</span>
            <span className="hidden sm:inline">Shared with Me</span>
          </button>
        </div>

        <div className="flex-1 min-w-0" />

        {/* Sort Dropdown */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowSortMenu(!showSortMenu)}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 dark:text-slate-200 bg-white dark:bg-slate-700 border border-gray-200 dark:border-slate-600 rounded-lg hover:bg-gray-50 dark:hover:bg-slate-600 transition-colors"
          >
            <ArrowUpDown className="h-4 w-4" />
            <span className="hidden sm:inline">{sortLabels[sortOption]}</span>
            <ChevronDown className="h-4 w-4" />
          </button>
          {showSortMenu && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowSortMenu(false)} />
              <div className="absolute right-0 mt-2 w-48 rounded-lg border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-700 shadow-lg z-20">
                {(Object.entries(sortLabels) as [SortOption, string][]).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => {
                      setSortOption(key)
                      setShowSortMenu(false)
                    }}
                    className={`w-full px-4 py-2 text-left text-sm transition-colors first:rounded-t-lg last:rounded-b-lg ${
                      sortOption === key
                        ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300'
                        : 'text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-600'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Pending Invitations */}
      {pendingInvitesQuery.isLoading ? (
        <div className="rounded-2xl border border-gray-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-800">
          <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-3">Pending invitations</h3>
          <div className="text-sm text-gray-600 dark:text-slate-400">Loading…</div>
        </div>
      ) : pendingInvitesQuery.isError ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700 dark:border-red-800/50 dark:bg-red-500/10 dark:text-red-300">
          <h3 className="text-base font-semibold">Pending invitations</h3>
          <p className="mt-1">We couldn&apos;t load project invitations right now.</p>
        </div>
      ) : pendingInvites.length > 0 ? (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">Pending invitations</h2>
            <span className="text-xs font-medium text-gray-500 dark:text-slate-400">{pendingInvites.length} pending</span>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {pendingInvites.map((invite) => (
              <div
                key={invite.member_id}
                className="flex h-full flex-col justify-between rounded-xl border border-dashed border-amber-300 bg-amber-50 p-5 shadow-sm dark:border-amber-500/50 dark:bg-amber-500/10"
              >
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
                    <Clock className="h-4 w-4" /> Pending invitation
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white truncate" title={invite.project_title}>
                    {invite.project_title}
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-slate-300 capitalize">Role: {invite.role.toLowerCase()}</p>
                  {invite.invited_by && (
                    <p className="text-xs text-gray-500 dark:text-slate-400">Invited by {invite.invited_by}</p>
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
                    className="inline-flex flex-1 items-center justify-center rounded-full border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-600 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-red-800/50 dark:bg-red-500/10 dark:text-red-400"
                  >
                    Decline
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {/* Main Content */}
      {isError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700 dark:border-red-800/50 dark:bg-red-500/10 dark:text-red-300">
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
              className="h-48 animate-pulse rounded-2xl border border-gray-200 bg-gray-50 dark:border-slate-700 dark:bg-slate-800"
            />
          ))}
        </div>
      ) : filteredProjects.length === 0 ? (
        /* Enhanced Empty State */
        <div className="rounded-2xl border-2 border-dashed border-gray-300 bg-white p-12 text-center dark:border-slate-600 dark:bg-slate-800">
          <div className="mx-auto w-20 h-20 rounded-full bg-gradient-to-br from-indigo-100 to-purple-100 dark:from-indigo-500/20 dark:to-purple-500/20 flex items-center justify-center mb-6">
            <Sparkles className="h-10 w-10 text-indigo-500" />
          </div>
          <h3 className="text-xl font-semibold text-gray-900 dark:text-white">
            {searchTerm || filterTab !== 'all' ? 'No projects found' : 'Start your research journey'}
          </h3>
          <p className="mt-3 text-gray-500 dark:text-slate-400 max-w-md mx-auto">
            {searchTerm
              ? 'Try a different search term or clear the filter to see all projects.'
              : filterTab !== 'all'
              ? `No projects in this category yet.`
              : 'Create your first project to begin organizing papers, collaborating with your team, and tracking your research progress.'}
          </p>
          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
            <button
              type="button"
              onClick={() => setIsCreateOpen(true)}
              className="inline-flex items-center gap-2 px-5 py-3 bg-indigo-600 text-white rounded-full font-medium hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-500/25"
            >
              <FolderPlus className="h-5 w-5" />
              Create New Project
            </button>
          </div>
          {!searchTerm && filterTab === 'all' && (
            <div className="mt-10 pt-8 border-t border-gray-200 dark:border-slate-700">
              <p className="text-xs text-gray-400 dark:text-slate-500 uppercase tracking-wide font-medium mb-4">What you can do with projects</p>
              <div className="flex flex-wrap justify-center gap-6 text-sm text-gray-600 dark:text-slate-300">
                <span className="flex items-center gap-1.5">
                  <FileText className="h-4 w-4 text-indigo-500" /> Write papers
                </span>
                <span className="flex items-center gap-1.5">
                  <BookOpen className="h-4 w-4 text-indigo-500" /> Manage references
                </span>
                <span className="flex items-center gap-1.5">
                  <Sparkles className="h-4 w-4 text-indigo-500" /> AI assistance
                </span>
              </div>
            </div>
          )}
        </div>
      ) : viewMode === 'grid' || window.innerWidth < 640 ? (
        // Always use grid view on mobile (< 640px)
        <div className="space-y-6">
          {/* Pinned Projects */}
          {pinnedProjects.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3 sm:mb-4">
                <Star className="h-4 w-4 text-amber-500 fill-amber-500" />
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Pinned</h3>
                <span className="text-xs text-gray-500 dark:text-slate-400">{pinnedProjects.length}</span>
              </div>
              <div className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
                {pinnedProjects.map((project) => (
                  <ProjectCard key={project.id} project={project} isPinned={true} />
                ))}
              </div>
            </div>
          )}

          {/* All/Unpinned Projects */}
          {unpinnedProjects.length > 0 && (
            <div>
              {pinnedProjects.length > 0 && (
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 sm:mb-4">All Projects</h3>
              )}
              <div className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
                {unpinnedProjects.map((project) => (
                  <ProjectCard key={project.id} project={project} isPinned={false} />
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        // Table view - only shown on tablet and desktop
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-800 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-100 dark:divide-slate-700">
            <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:bg-slate-800/70 dark:text-slate-300">
              <tr>
                <th className="px-4 sm:px-6 py-3 w-8"></th>
                <th className="px-4 sm:px-6 py-3">Project</th>
                <th className="px-4 sm:px-6 py-3 hidden md:table-cell">Status</th>
                <th className="px-4 sm:px-6 py-3 hidden sm:table-cell">Updated</th>
                <th className="px-4 sm:px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 text-sm text-gray-700 dark:divide-slate-700 dark:text-slate-200">
              {filteredProjects.map((project) => {
                const isPinned = pinnedIds.includes(project.id)
                return (
                  <tr key={project.id} className="hover:bg-gray-50 dark:hover:bg-slate-700/40">
                    <td className="px-4 sm:px-6 py-4">
                      <button
                        type="button"
                        onClick={() => togglePin(project.id)}
                        className={`transition-colors ${isPinned ? 'text-amber-500' : 'text-gray-300 hover:text-amber-500'}`}
                      >
                        <Star className={`h-4 w-4 ${isPinned ? 'fill-current' : ''}`} />
                      </button>
                    </td>
                    <td className="px-4 sm:px-6 py-4">
                      <div className="font-medium text-gray-900 dark:text-slate-100">{project.title}</div>
                      {project.idea && (
                        <div className="text-xs text-gray-500 dark:text-slate-400 truncate max-w-[200px] sm:max-w-xs">{project.idea}</div>
                      )}
                    </td>
                    <td className="px-4 sm:px-6 py-4 hidden md:table-cell">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${getStatusColor(project.status)}`}>
                        {project.status || 'Active'}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 text-gray-500 dark:text-slate-300 hidden sm:table-cell">{formatDate(project.updated_at)}</td>
                    <td className="px-4 sm:px-6 py-4 text-right">
                      <div className="flex justify-end gap-2 sm:gap-3">
                        <button
                          type="button"
                          onClick={() => {
                            setEditError(null)
                            setEditingProject(project)
                          }}
                          className="text-xs sm:text-sm font-medium text-gray-500 hover:text-indigo-600 dark:text-slate-300 dark:hover:text-indigo-300"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => handleOpenProject(project)}
                          className="text-xs sm:text-sm font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-300 dark:hover:text-indigo-200"
                        >
                          Open
                        </button>
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
        <p className="text-xs text-gray-400 dark:text-slate-500">Refreshing projects…</p>
      )}
    </div>
  )
}

export default ProjectsHome
