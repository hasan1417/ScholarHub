import { useMemo } from 'react'
import { FileText, Plus, FileCode } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useProjectContext } from './ProjectLayout'
import { researchPapersAPI } from '../../services/api'

const ProjectPapers = () => {
  const { project, currentRole } = useProjectContext()
  const navigate = useNavigate()

  const { data, isLoading } = useQuery({
    queryKey: ['project-papers', project.id],
    queryFn: async () => {
      const response = await researchPapersAPI.getPapers({ projectId: project.id, limit: 200 })
      return response.data
    },
  })

  const papers = useMemo(() => data?.papers ?? [], [data])
  const canCreatePaper = currentRole !== 'viewer'

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
        <div className="mt-6 grid gap-3">
          {papers.map((paper) => {
            // Detect editor type from authoring_mode in content_json
            const authoringMode = paper.content_json?.authoring_mode
            const isLatex = authoringMode === 'latex'

            return (
              <Link
                key={paper.id}
                to={`/projects/${project.id}/papers/${paper.id}`}
                className="flex items-start gap-4 rounded-xl border border-gray-200 bg-white px-4 py-4 shadow-sm transition hover:border-indigo-200 hover:shadow-md dark:border-slate-700 dark:bg-slate-800"
              >
                {/* Icon indicating editor type */}
                <div className="flex-shrink-0 pt-0.5">
                  {isLatex ? (
                    <FileCode className="h-5 w-5 text-purple-500" />
                  ) : (
                    <FileText className="h-5 w-5 text-indigo-500" />
                  )}
                </div>

                {/* Main content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-semibold text-gray-900 truncate dark:text-slate-100">
                      {paper.title}
                    </h3>
                    {/* Status badge with color */}
                    <span className={`flex-shrink-0 inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${getStatusColor(paper.status || 'draft')}`}>
                      {paper.status || 'Draft'}
                    </span>
                  </div>

                  {/* Metadata row */}
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-xs text-gray-500 dark:text-slate-300">
                      Updated {formatRelativeTime(paper.updated_at)}
                    </span>
                    <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium transition-colors ${
                      isLatex
                        ? 'bg-purple-50 text-purple-700 dark:bg-purple-400/10 dark:text-purple-200'
                        : 'bg-blue-50 text-blue-700 dark:bg-blue-400/10 dark:text-blue-200'
                    }`}>
                      {isLatex ? (
                        <>
                          <FileCode className="h-3 w-3" />
                          <span>LaTeX</span>
                        </>
                      ) : (
                        <>
                          <FileText className="h-3 w-3" />
                          <span>Rich</span>
                        </>
                      )}
                    </span>
                    {paper.paper_type && (
                      <span className="inline-flex items-center rounded bg-gray-50 px-2 py-0.5 text-xs font-medium text-gray-700 capitalize dark:bg-slate-700 dark:text-slate-200">
                        {paper.paper_type}
                      </span>
                    )}
                  </div>
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
