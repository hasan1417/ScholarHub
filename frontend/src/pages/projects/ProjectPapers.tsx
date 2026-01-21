import { useMemo, useState } from 'react'
import { FileText, Plus, FileCode, ChevronDown, Search } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useProjectContext } from './ProjectLayout'
import { researchPapersAPI } from '../../services/api'

type SortOption = 'newest' | 'oldest' | 'title-az' | 'title-za'
type CategoryFilter = 'all' | 'literature_review' | 'research' | 'review' | 'survey' | 'other'
type EditorFilter = 'all' | 'latex' | 'rich'

const ProjectPapers = () => {
  const { project, currentRole } = useProjectContext()
  const navigate = useNavigate()

  // Filter & sort state
  const [searchTerm, setSearchTerm] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>('all')
  const [editorFilter, setEditorFilter] = useState<EditorFilter>('all')
  const [sortBy, setSortBy] = useState<SortOption>('newest')

  const { data, isLoading } = useQuery({
    queryKey: ['project-papers', project.id],
    queryFn: async () => {
      const response = await researchPapersAPI.getPapers({ projectId: project.id, limit: 200 })
      return response.data
    },
  })

  const allPapers = useMemo(() => data?.papers ?? [], [data])
  const canCreatePaper = currentRole !== 'viewer'

  // Get unique categories from papers
  const _availableCategories = useMemo(() => {
    const categories = new Set<string>()
    allPapers.forEach((paper) => {
      if (paper.paper_type) {
        categories.add(paper.paper_type.toLowerCase())
      }
    })
    return Array.from(categories)
  }, [allPapers])

  // Filter and sort papers
  const papers = useMemo(() => {
    let filtered = [...allPapers]

    // Search filter
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase()
      filtered = filtered.filter((paper) =>
        paper.title?.toLowerCase().includes(term) ||
        paper.paper_type?.toLowerCase().includes(term)
      )
    }

    // Category filter
    if (categoryFilter !== 'all') {
      filtered = filtered.filter((paper) => {
        const type = paper.paper_type?.toLowerCase() || ''
        if (categoryFilter === 'literature_review') return type.includes('literature')
        if (categoryFilter === 'research') return type.includes('research')
        if (categoryFilter === 'review') return type.includes('review') && !type.includes('literature')
        if (categoryFilter === 'survey') return type.includes('survey')
        if (categoryFilter === 'other') return !type.includes('literature') && !type.includes('research') && !type.includes('review') && !type.includes('survey')
        return true
      })
    }

    // Editor filter
    if (editorFilter !== 'all') {
      filtered = filtered.filter((paper) => {
        const isLatex = paper.content_json?.authoring_mode === 'latex'
        if (editorFilter === 'latex') return isLatex
        if (editorFilter === 'rich') return !isLatex
        return true
      })
    }

    // Sort
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'newest':
          return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
        case 'oldest':
          return new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime()
        case 'title-az':
          return (a.title || '').localeCompare(b.title || '')
        case 'title-za':
          return (b.title || '').localeCompare(a.title || '')
        default:
          return 0
      }
    })

    return filtered
  }, [allPapers, searchTerm, categoryFilter, editorFilter, sortBy])

  const getStatusColor = (status: string) => {
    const normalized = status?.toLowerCase() || 'draft'
    switch (normalized) {
      case 'published':
        return 'bg-green-100 text-green-700 dark:bg-green-400/10 dark:text-green-200'
      case 'in review':
      case 'review':
        return 'bg-yellow-100 text-yellow-700 dark:bg-amber-400/10 dark:text-amber-200'
      case 'draft':
      default:
        return 'bg-gray-100 text-gray-600 dark:bg-slate-700 dark:text-slate-200'
    }
  }

  const formatRelativeTime = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString()
  }

  const formatPaperType = (paperType?: string) => {
    if (!paperType) return null
    return paperType
      .split('_')
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ')
  }

  // Category styling based on paper type
  const getCategoryStyle = (paperType?: string) => {
    const type = paperType?.toLowerCase() || ''

    // Literature Review - emerald/green
    if (type.includes('literature')) {
      return {
        border: 'border-l-emerald-500',
        badge: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300',
        icon: 'bg-emerald-100 dark:bg-emerald-500/20',
        iconColor: 'text-emerald-600 dark:text-emerald-400',
      }
    }
    // Review (not literature review) - amber/orange
    if (type.includes('review')) {
      return {
        border: 'border-l-amber-500',
        badge: 'bg-amber-100 text-amber-700 dark:bg-amber-400/10 dark:text-amber-300',
        icon: 'bg-amber-100 dark:bg-amber-500/20',
        iconColor: 'text-amber-600 dark:text-amber-400',
      }
    }
    // Research - blue
    if (type.includes('research')) {
      return {
        border: 'border-l-blue-500',
        badge: 'bg-blue-100 text-blue-700 dark:bg-blue-400/10 dark:text-blue-300',
        icon: 'bg-blue-100 dark:bg-blue-500/20',
        iconColor: 'text-blue-600 dark:text-blue-400',
      }
    }
    // Survey - violet
    if (type.includes('survey')) {
      return {
        border: 'border-l-violet-500',
        badge: 'bg-violet-100 text-violet-700 dark:bg-violet-400/10 dark:text-violet-300',
        icon: 'bg-violet-100 dark:bg-violet-500/20',
        iconColor: 'text-violet-600 dark:text-violet-400',
      }
    }
    // Case Study - cyan
    if (type.includes('case') || type.includes('study')) {
      return {
        border: 'border-l-cyan-500',
        badge: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-400/10 dark:text-cyan-300',
        icon: 'bg-cyan-100 dark:bg-cyan-500/20',
        iconColor: 'text-cyan-600 dark:text-cyan-400',
      }
    }
    // Default - gray
    return {
      border: 'border-l-gray-300 dark:border-l-slate-600',
      badge: 'bg-gray-100 text-gray-700 dark:bg-slate-700 dark:text-slate-300',
      icon: 'bg-gray-100 dark:bg-slate-700',
      iconColor: 'text-gray-500 dark:text-slate-400',
    }
  }

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-indigo-600" />
          <h2 className="text-base font-semibold text-gray-900">Project papers</h2>
        </div>
        {canCreatePaper && (
          <button
            type="button"
            onClick={() => navigate(`/projects/${project.id}/papers/new`)}
            className="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
          >
            <Plus className="h-4 w-4" />
            New paper
          </button>
        )}
      </div>

      {/* Filter & Sort Bar */}
      {allPapers.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px] max-w-xs">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search papers..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="h-9 w-full rounded-lg border border-gray-200 bg-gray-50 pl-9 pr-3 text-sm placeholder:text-gray-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-300 dark:border-slate-600 dark:bg-slate-700 dark:text-white"
            />
          </div>

          {/* Category Filter */}
          <div className="relative">
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value as CategoryFilter)}
              className="h-9 appearance-none rounded-lg border border-gray-200 bg-gray-50 pl-3 pr-8 text-sm font-medium text-gray-700 focus:border-indigo-300 focus:outline-none focus:ring-1 focus:ring-indigo-300 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200"
            >
              <option value="all">All Categories</option>
              <option value="literature_review">Literature Review</option>
              <option value="research">Research</option>
              <option value="review">Review</option>
              <option value="survey">Survey</option>
              <option value="other">Other</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          </div>

          {/* Editor Filter */}
          <div className="relative">
            <select
              value={editorFilter}
              onChange={(e) => setEditorFilter(e.target.value as EditorFilter)}
              className="h-9 appearance-none rounded-lg border border-gray-200 bg-gray-50 pl-3 pr-8 text-sm font-medium text-gray-700 focus:border-indigo-300 focus:outline-none focus:ring-1 focus:ring-indigo-300 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200"
            >
              <option value="all">All Editors</option>
              <option value="latex">LaTeX</option>
              <option value="rich">Rich Text</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          </div>

          {/* Sort */}
          <div className="relative">
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className="h-9 appearance-none rounded-lg border border-gray-200 bg-gray-50 pl-3 pr-8 text-sm font-medium text-gray-700 focus:border-indigo-300 focus:outline-none focus:ring-1 focus:ring-indigo-300 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200"
            >
              <option value="newest">Newest First</option>
              <option value="oldest">Oldest First</option>
              <option value="title-az">Title A-Z</option>
              <option value="title-za">Title Z-A</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          </div>

          {/* Results count */}
          <span className="text-xs text-gray-500 dark:text-slate-400">
            {papers.length} of {allPapers.length} paper{allPapers.length !== 1 ? 's' : ''}
          </span>
        </div>
      )}

      {isLoading ? (
        <div className="mt-6 space-y-3">
          {Array.from({ length: 3 }).map((_, idx) => (
            <div key={idx} className="h-20 animate-pulse rounded-lg bg-gray-100 dark:bg-slate-800/60" />
          ))}
        </div>
      ) : papers.length === 0 ? (
        <div className="mt-6 rounded-xl border border-dashed border-gray-300 bg-gray-50 p-8 text-sm text-gray-500 transition-colors dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-300">
          {canCreatePaper
            ? 'No papers linked yet. Create one to start writing within this project scope.'
            : 'No papers linked yet. Ask an editor or admin to create the first draft.'}
        </div>
      ) : (
        <div className="mt-6 space-y-2">
          {papers.map((paper) => {
            // Detect editor type from authoring_mode in content_json
            const authoringMode = paper.content_json?.authoring_mode
            const isLatex = authoringMode === 'latex'
            const objectiveList = Array.isArray(paper.objectives)
              ? paper.objectives.filter(Boolean)
              : paper.objectives
              ? [paper.objectives]
              : []
            const formattedType = formatPaperType(paper.paper_type)
            const categoryStyle = getCategoryStyle(paper.paper_type)

            return (
              <Link
                key={paper.id}
                to={`/projects/${project.id}/papers/${paper.id}`}
                className={`group flex items-center gap-4 rounded-xl border border-l-4 border-gray-100 bg-gray-50/50 px-4 py-3.5 transition hover:bg-white hover:shadow-sm dark:border-slate-700 dark:bg-slate-800/50 dark:hover:bg-slate-800 ${categoryStyle.border}`}
              >
                {/* Icon - color based on category */}
                <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg ${categoryStyle.icon}`}>
                  {isLatex ? (
                    <FileCode className={`h-5 w-5 ${categoryStyle.iconColor}`} />
                  ) : (
                    <FileText className={`h-5 w-5 ${categoryStyle.iconColor}`} />
                  )}
                </div>

                {/* Content - fixed width sections */}
                <div className="flex-1 min-w-0 grid grid-cols-[1fr,auto,auto] gap-x-4 items-center">
                  {/* Left: Title and metadata */}
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-gray-900 truncate dark:text-slate-100 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                      {paper.title}
                    </h3>

                    {/* Metadata row - fixed order: time | category | editor */}
                    <div className="mt-1.5 flex items-center gap-2 text-xs">
                      {/* Time - always first, fixed width */}
                      <span className="text-gray-400 dark:text-slate-500 w-16 flex-shrink-0">
                        {formatRelativeTime(paper.updated_at)}
                      </span>

                      {/* Category badge - colored based on type */}
                      {formattedType && (
                        <span className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${categoryStyle.badge}`}>
                          {formattedType}
                        </span>
                      )}

                      {/* Editor type badge */}
                      <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                        isLatex
                          ? 'bg-purple-100 text-purple-700 dark:bg-purple-400/10 dark:text-purple-300'
                          : 'bg-sky-100 text-sky-700 dark:bg-sky-400/10 dark:text-sky-300'
                      }`}>
                        {isLatex ? 'LaTeX' : 'Rich'}
                      </span>
                    </div>
                  </div>

                  {/* Middle: Objectives - separate column for breathing room */}
                  {objectiveList.length > 0 ? (
                    <span className="text-xs text-indigo-600 dark:text-indigo-400 font-medium whitespace-nowrap">
                      {objectiveList.length} objective{objectiveList.length > 1 ? 's' : ''}
                    </span>
                  ) : (
                    <span />
                  )}

                  {/* Right: Status badge - always in same position */}
                  <span
                    className={`flex-shrink-0 inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getStatusColor(paper.status || 'draft')}`}
                  >
                    {paper.status || 'draft'}
                  </span>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default ProjectPapers
