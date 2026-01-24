import React, { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { researchPapersAPI } from '../../services/api'
import { ResearchPaper } from '../../types'
import DocumentShell from '../../components/editor/DocumentShell'
import OOAdapter from '../../components/editor/adapters/OOAdapter'
import LatexAdapter from '../../components/editor/adapters/LatexAdapter'
import { useProjectContext } from './ProjectLayout'
import { getPaperUrlId } from '../../utils/urlId'

const PaperEditor: React.FC = () => {
  const { projectId, paperId } = useParams<{ projectId?: string; paperId: string }>()
  const navigate = useNavigate()
  const { currentRole } = useProjectContext()
  const [paper, setPaper] = useState<ResearchPaper | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const autoSaveStatus: 'idle' | 'saving' | 'success' | 'error' = 'idle'

  const navigateBackToProject = () => {
    const id = projectId || paper?.project_id
    navigate(id ? `/projects/${id}` : '/projects')
  }

  // Enhanced state variables for TipTap JSON content
  const [contentJson, setContentJson] = useState<any>(null)
  const autoSaveTimeoutRef = useRef<number | null>(null)

  useEffect(() => {
    if (paperId) {
      // Clear prior content to avoid showing stale data before fresh load
      setPaper(null)
      setContentJson(null)
      loadPaper()
    }
  }, [paperId])

  useEffect(() => {
    if (currentRole === 'viewer' && paperId && paper) {
      const targetProjectId = projectId || paper.project_id
      if (targetProjectId) {
        navigate(`/projects/${targetProjectId}/papers/${getPaperUrlId(paper)}/view`, { replace: true })
      } else {
        navigateBackToProject()
      }
    }
    // we intentionally include paper so viewers coming from non-project routes still redirect once data loads
  }, [currentRole, paperId, projectId, paper])

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (autoSaveTimeoutRef.current) {
        window.clearTimeout(autoSaveTimeoutRef.current)
      }
    }
  }, [])

  // Initialize content from paper data (only when paper changes)
  useEffect(() => {
    if (paper) {
      // For LaTeX papers, keep JSON as source of truth; for rich, keep JSON null
      try {
        const mode = (paper.content_json as any)?.authoring_mode
        if (mode === 'latex') {
          setContentJson(paper.content_json)
        } else {
          setContentJson(null)
        }
      } catch {
        setContentJson(null)
      }
    }
  }, [paper]) // Only depend on paper

  // Enhanced content change handler supporting JSON content



  const loadPaper = async () => {
    if (!paperId) return

    try {
      setIsLoading(true)
      const response = await researchPapersAPI.getPaper(paperId)
      console.debug('[PaperEditor] Loaded paper', {
        paperId,
        htmlLen: (response?.data?.content || '').length,
        hasJson: Boolean(response?.data?.content_json),
      })
      setPaper(response.data)
      try {
        const mode = (response.data.content_json as any)?.authoring_mode
        if (mode === 'latex') {
          setContentJson(response.data.content_json)
        } else {
          setContentJson(null)
        }
      } catch {
        setContentJson(null)
      }
    } catch (error) {
      console.error('Error loading paper:', error)
      setError('Failed to load paper')
    } finally {
      setIsLoading(false)
    }
  }




  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 transition-colors dark:bg-slate-950">
        <div className="text-center">
          <div className="mx-auto h-16 w-16 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600 dark:border-blue-900 dark:border-t-blue-400"></div>
          <p className="mt-6 text-lg font-medium text-gray-600 dark:text-slate-300">Loading paper...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 transition-colors dark:bg-slate-950">
        <div className="max-w-md text-center">
          <div className="mb-4 rounded border border-red-400 bg-red-100 px-4 py-3 text-red-700 dark:border-red-500/60 dark:bg-red-500/10 dark:text-red-200">
            <svg className="mx-auto mb-2 h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
            <p className="font-medium">Error Loading Paper</p>
            <p className="mt-1 text-sm">{error}</p>
          </div>
          <div className="space-y-3">
            <button
              onClick={loadPaper}
              className="rounded-md bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-400"
            >
              Try Again
            </button>
            <button
              onClick={navigateBackToProject}
              className="ml-2 rounded-md bg-gray-600 px-4 py-2 text-white transition-colors hover:bg-gray-700 dark:bg-slate-600 dark:hover:bg-slate-500"
            >
              Back to Papers
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!paper) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 transition-colors dark:bg-slate-950">
        <div className="text-center">
          <h2 className="mb-2 text-xl font-semibold text-gray-900 dark:text-slate-100">Paper not found</h2>
          <p className="mb-4 text-gray-600 dark:text-slate-400">The paper you're looking for doesn't exist.</p>
          <button
            onClick={navigateBackToProject}
            className="rounded-md bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-400"
          >
            Back to Papers
          </button>
        </div>
      </div>
    )
  }

  // Check if this is a LaTeX paper based on content_json.authoring_mode
  const isLatexPaper = Boolean(
    (paper?.content_json && typeof paper.content_json === 'object' && 
     (paper.content_json as any).authoring_mode === 'latex') ||
    (contentJson && typeof contentJson === 'object' && 
     (contentJson as any).authoring_mode === 'latex')
  )

  const defaultPaperRole: 'admin' | 'editor' | 'viewer' = currentRole === 'admin'
    ? 'admin'
    : currentRole === 'editor'
      ? 'editor'
      : 'viewer'

  return (
    <div>
      {/* Auto-save Status Bar (hide for LaTeX mode; status shown in editor toolbar) */}
      {!isLatexPaper && autoSaveStatus !== 'idle' && (
        <div className={`fixed top-4 right-4 z-50 rounded-md border px-4 py-2 shadow-lg transition-all duration-300 ${
          autoSaveStatus === 'saving'
            ? 'border-blue-300 bg-blue-100 text-blue-700 dark:border-blue-500/40 dark:bg-blue-500/15 dark:text-blue-200'
            : autoSaveStatus === 'success'
              ? 'border-green-300 bg-green-100 text-green-700 dark:border-emerald-500/40 dark:bg-emerald-500/15 dark:text-emerald-200'
              : 'border-red-300 bg-red-100 text-red-700 dark:border-red-500/40 dark:bg-red-500/15 dark:text-red-200'
        }`}>
          <div className="flex items-center space-x-2">
            {autoSaveStatus === 'saving' && (
              <div className="animate-spin rounded-full h-4 w-4 border-2 border-blue-600 border-t-transparent"></div>
            )}
            {autoSaveStatus === 'success' && (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            )}
            {autoSaveStatus === 'error' && (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            )}
            <span className="text-sm font-medium">
              {autoSaveStatus === 'saving' ? 'Auto-saving...' :
               autoSaveStatus === 'success' ? 'Auto-saved!' :
               'Auto-save failed'}
            </span>
          </div>
        </div>
      )}
      
      {isLatexPaper ? (
        /* LaTeX papers now use DocumentShell header via LatexAdapter */
        <div className="fixed inset-0 bg-white transition-colors dark:bg-slate-950">
          <DocumentShell
            paperId={paper.id}
            projectId={projectId || paper.project_id || undefined}
            paperTitle={paper.title}
            initialContent={''}
            initialContentJson={contentJson || paper.content_json}
            Adapter={LatexAdapter as any}
            fullBleed
            initialPaperRole={defaultPaperRole}
          />
        </div>
      ) : (
        /* Rich text papers use OnlyOffice standalone (no DocumentShell wrapper) */
        <div className="fixed inset-0 bg-white transition-colors dark:bg-slate-950">
          <OOAdapter
            paperId={paper.id}
            paperTitle={paper.title}
            content={paper.content || ''}
            contentJson={paper.content_json}
            onContentChange={() => {}}
            onSelectionChange={() => {}}
            className="h-full w-full"
            readOnly={defaultPaperRole === 'viewer'}
            onNavigateBack={() => navigate(projectId ? `/projects/${projectId}` : '/projects')}
          />
        </div>
      )}
    </div>
  )
}

export default PaperEditor
