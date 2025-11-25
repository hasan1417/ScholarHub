import React, { useState, useEffect, useMemo, useRef } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  BookOpen,
  CalendarDays,
  Clock,
  Crown,
  Edit,
  Eye,
  FileText,
  Link2,
  MoreHorizontal,
  Pencil,
  Save,
  Share2,
  Shield,
  Trash2,
  Users,
  X,
} from 'lucide-react'

import {
  documentsAPI,
  projectReferencesAPI,
  researchPapersAPI,
} from '../../services/api'
import {
  Document,
  PaperReferenceAttachment,
  ResearchPaper,
  ResearchPaperUpdate,
} from '../../types'
import ConfirmationModal from '../../components/common/ConfirmationModal'
import AttachProjectReferenceModal from '../../components/projects/AttachProjectReferenceModal'
import { useAuth } from '../../contexts/AuthContext'
import { useProjectContext } from './ProjectLayout'

const PaperDetail: React.FC = () => {
  const { projectId, paperId } = useParams<{ projectId?: string; paperId: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { project } = useProjectContext()

  const [paper, setPaper] = useState<ResearchPaper | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [references, setReferences] = useState<PaperReferenceAttachment[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [showDeletePaperConfirm, setShowDeletePaperConfirm] = useState(false)
  const [showAttachModal, setShowAttachModal] = useState(false)
  const [isActionsMenuOpen, setIsActionsMenuOpen] = useState(false)

  const projectMembers = project?.members ?? []
  const currentUserId = user?.id

  const projectRole = useMemo<'admin' | 'editor' | 'viewer'>(() => {
    if (!project || !currentUserId) {
      return 'viewer'
    }
    if (project.created_by === currentUserId) {
      return 'admin'
    }
    const membership = projectMembers.find((member) => member.user_id === currentUserId)
    if (!membership) {
      return 'viewer'
    }
    if ((membership.status || '').toLowerCase() !== 'accepted') {
      return 'viewer'
    }
    const normalizedRole = (membership.role || '').toLowerCase()
    if (normalizedRole === 'owner') return 'admin'
    if (normalizedRole === 'reviewer') return 'viewer'
    if (normalizedRole === 'admin' || normalizedRole === 'editor') return normalizedRole
    return 'viewer'
  }, [project, projectMembers, currentUserId])

  const canEditPaper = ['admin', 'editor'].includes(projectRole)
  const canDeletePaper = projectRole === 'admin'
  const canManageReferences = ['admin', 'editor'].includes(projectRole)
  const handleViewPaper = () => {
    if (!paper) return
    navigate(resolveProjectPath(`/papers/${paper.id}/view`))
  }

  const resolveProjectPath = (suffix = '') => {
    const id = projectId || project?.id || paper?.project_id
    if (!id) return `/projects${suffix}`
    return `/projects/${id}${suffix}`
  }

  const navigateBackToProject = () => {
    navigate(resolveProjectPath())
  }

  const [editForm, setEditForm] = useState<Partial<ResearchPaperUpdate>>({})
  const actionsMenuRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!paperId) return
    void loadPaperData()
  }, [paperId])

  useEffect(() => {
    if (!paperId || !project?.id) return
    void refreshReferences()
  }, [paperId, project?.id])

  useEffect(() => {
    if (!canEditPaper && isEditing) {
      setIsEditing(false)
    }
  }, [canEditPaper, isEditing])

  useEffect(() => {
    if (!isActionsMenuOpen) return
    const handleClickOutside = (event: MouseEvent) => {
      if (actionsMenuRef.current && !actionsMenuRef.current.contains(event.target as Node)) {
        setIsActionsMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isActionsMenuOpen])

  useEffect(() => {
    if (isEditing) {
      setIsActionsMenuOpen(false)
    }
  }, [isEditing])

  const loadPaperData = async () => {
    if (!paperId) return
    setIsLoading(true)
    try {
      const paperResponse = await researchPapersAPI.getPaper(paperId)
      const paperData = paperResponse.data
      setPaper(paperData)
      setEditForm({
        title: paperData.title,
        abstract: paperData.abstract,
        status: paperData.status,
        paper_type: paperData.paper_type,
        keywords: paperData.keywords,
        references: paperData.references,
        is_public: paperData.is_public,
      })

      try {
        const documentsResponse = await documentsAPI.getDocuments(paperId, 0, 50)
        setDocuments(documentsResponse.data.documents)
      } catch (docError: unknown) {
        const axiosError = docError as { response?: { status?: number } } | undefined
        if (axiosError?.response?.status === 403) {
          setDocuments([])
        } else {
          console.error('Error loading paper documents:', docError)
          setDocuments([])
        }
      }
    } catch (error: unknown) {
      const axiosError = error as { response?: { status?: number } } | undefined
      if (axiosError) {
        const status = axiosError.response?.status
        if (status === 404) {
          navigate('/projects')
          return
        }
        if (status === 403) {
          setLoadError('You do not have permission to view this paper.')
        } else {
          setLoadError('Failed to load paper.')
        }
      } else {
        console.error('Error loading paper data:', error)
        setLoadError('Failed to load paper.')
      }
    } finally {
      setIsLoading(false)
    }
  }

  const refreshReferences = async () => {
    try {
      if (!project?.id || !paperId) return
      const resp = await projectReferencesAPI.listPaperReferences(project.id, paperId)
      setReferences((resp.data?.references as PaperReferenceAttachment[]) || [])
    } catch (error) {
      console.error('Error loading references:', error)
      setReferences([])
    }
  }

  const handleSaveChanges = async () => {
    if (!paper) return
    if (!canEditPaper) {
      alert('You do not have permission to update this paper.')
      return
    }

    try {
      setIsSaving(true)
      const response = await researchPapersAPI.updatePaper(paper.id, editForm)
      setPaper(response.data)
      setIsEditing(false)
    } catch (error) {
      console.error('Error updating paper:', error)
      alert('Error updating paper. Please try again.')
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancelEdit = () => {
    setEditForm({
      title: paper?.title,
      abstract: paper?.abstract,
      status: paper?.status,
      paper_type: paper?.paper_type,
      keywords: paper?.keywords,
      references: paper?.references,
      is_public: paper?.is_public,
    })
    setIsEditing(false)
  }

  const handleStartWriting = () => {
    if (!canEditPaper) {
      alert('You do not have permission to edit this paper.')
      return
    }
    const targetProjectId = projectId || paper?.project_id
    if (!targetProjectId) return
    navigate(`/projects/${targetProjectId}/papers/${paperId}/editor`)
  }

  const handleDeletePaper = () => {
    if (!canDeletePaper) {
      alert('You do not have permission to delete this paper.')
      return
    }
    setShowDeletePaperConfirm(true)
  }

  const confirmDeletePaper = async () => {
    if (!paper) return
    if (!canDeletePaper) {
      setShowDeletePaperConfirm(false)
      alert('You do not have permission to delete this paper.')
      return
    }

    try {
      await researchPapersAPI.deletePaper(paper.id)
      navigate(resolveProjectPath())
    } catch (error) {
      console.error('Error deleting paper:', error)
      alert('Error deleting paper. Please try again.')
    } finally {
      setShowDeletePaperConfirm(false)
    }
  }

  const getStatusClassName = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800 dark:bg-emerald-500/20 dark:text-emerald-200'
      case 'in_progress':
        return 'bg-yellow-100 text-yellow-800 dark:bg-amber-300/20 dark:text-amber-200'
      case 'published':
        return 'bg-indigo-100 text-indigo-800 dark:bg-indigo-500/20 dark:text-indigo-200'
      case 'draft':
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-slate-800/60 dark:text-slate-200'
    }
  }

  const getPaperTypeLabel = (type: string) => {
    const mapping: Record<string, string> = {
      research: 'Research',
      review: 'Literature Review',
      case_study: 'Case Study',
      methodology: 'Methodology',
      theoretical: 'Theoretical',
      experimental: 'Experimental',
    }
    return mapping[type] || type
  }

  const normalizeMemberRole = (role?: string | null): 'admin' | 'editor' | 'viewer' => {
    const value = (role || '').toLowerCase()
    if (value === 'admin' || value === 'editor' || value === 'viewer') {
      return value as 'admin' | 'editor' | 'viewer'
    }
    if (value === 'owner') return 'admin'
    if (value === 'reviewer') return 'viewer'
    return 'viewer'
  }

  const renderRoleIcon = (role: 'admin' | 'editor' | 'viewer') => {
    switch (role) {
      case 'admin':
        return <Shield className="h-4 w-4 text-purple-600 dark:text-purple-300" />
      case 'editor':
        return <Edit className="h-4 w-4 text-green-600 dark:text-emerald-300" />
      default:
        return <Eye className="h-4 w-4 text-gray-500 dark:text-slate-300" />
    }
  }

  const sortedProjectMembers = useMemo(() => {
    const priority: Record<'admin' | 'editor' | 'viewer', number> = {
      admin: 0,
      editor: 1,
      viewer: 2,
    }
    return [...projectMembers].sort((a, b) => {
      const roleA = a.user_id === project?.created_by ? 'admin' : normalizeMemberRole(a.role)
      const roleB = b.user_id === project?.created_by ? 'admin' : normalizeMemberRole(b.role)
      if (priority[roleA] === priority[roleB]) {
        return (a.user?.email || '').localeCompare(b.user?.email || '')
      }
      return priority[roleA] - priority[roleB]
    })
  }, [projectMembers, project?.created_by])

  const keywordDisplay = useMemo(() => {
    if (!paper?.keywords) return []
    if (Array.isArray(paper.keywords)) {
      return paper.keywords
        .map((item) => item.trim())
        .filter(Boolean)
    }
    return paper.keywords
      .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
  }, [paper?.keywords])

  const objectivesDisplay = useMemo(() => {
    const raw = paper?.objectives
    if (!raw) return []
    if (Array.isArray(raw)) {
      return raw
        .map((item) => (typeof item === 'string' ? item.trim() : ''))
        .filter(Boolean)
    }
    if (typeof raw === 'string' && raw.trim()) {
      return [raw.trim()]
    }
    return []
  }, [paper?.objectives])

  const keywordInputValue = useMemo(() => {
    if (typeof editForm.keywords === 'string') {
      return editForm.keywords
    }
    if (Array.isArray(editForm.keywords)) {
      return editForm.keywords.join(', ')
    }
    if (Array.isArray(paper?.keywords)) {
      return (paper?.keywords as string[]).join(', ')
    }
    return (paper?.keywords as string) || ''
  }, [editForm.keywords, paper?.keywords])

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 transition-colors dark:bg-slate-900">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-indigo-600 dark:border-indigo-500" />
          <p className="mt-4 text-gray-600 dark:text-slate-300">Loading paper...</p>
        </div>
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 transition-colors dark:bg-slate-900">
        <div className="max-w-md text-center">
          <div className="mb-4 rounded border border-amber-300 bg-amber-50 px-4 py-3 text-amber-700 dark:border-amber-400/40 dark:bg-amber-500/15 dark:text-amber-200">
            <h2 className="mb-1 text-lg font-semibold">Unable to open paper</h2>
            <p className="text-sm">{loadError}</p>
          </div>
          <button
            onClick={navigateBackToProject}
            className="rounded-md bg-indigo-600 px-4 py-2 text-white transition-colors hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-400"
          >
            Back to Papers
          </button>
        </div>
      </div>
    )
  }

  if (!paper) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 transition-colors dark:bg-slate-900">
        <div className="text-center">
          <h1 className="mb-3 text-2xl font-semibold text-gray-900 dark:text-slate-100">Paper Not Found</h1>
          <p className="mb-6 text-gray-600 dark:text-slate-400">
            The paper you&apos;re looking for doesn&apos;t exist or you don&apos;t have access to it.
          </p>
          <Link className="text-indigo-600 hover:text-indigo-800 dark:text-indigo-300 dark:hover:text-indigo-200" to={resolveProjectPath()}>
            ← Back to projects
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 transition-colors dark:bg-slate-900">
      <header className="border-b bg-white shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900/70">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-start justify-between gap-4">
            <div className="flex min-w-0 items-start gap-4">
              <Link to={resolveProjectPath()} className="text-gray-400 hover:text-gray-600 dark:text-slate-500 dark:hover:text-slate-300">
                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </Link>

              <div className="min-w-0 space-y-2">
                {project && (
                  <div className="text-xs font-medium text-indigo-600 dark:text-indigo-300">
                    <Link to={`/projects/${project.id}`} className="hover:underline">
                      {project.title}
                    </Link>
                  </div>
                )}

                {isEditing ? (
                  <input
                    value={editForm.title || ''}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, title: e.target.value }))}
                    className="w-full rounded border border-gray-300 px-3 py-2 text-xl font-semibold text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                    placeholder="Paper title"
                  />
                ) : (
                  <h1 className="truncate text-xl font-semibold text-gray-900 dark:text-slate-100" title={paper.title}>
                    {paper.title || 'Paper Details'}
                  </h1>
                )}

                {isEditing ? (
                  <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600 dark:text-slate-300">
                    <label className="flex items-center gap-2">
                      <span>Status</span>
                      <select
                        value={editForm.status || paper.status}
                        onChange={(e) => setEditForm((prev) => ({ ...prev, status: e.target.value }))}
                        className="rounded border border-gray-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                      >
                        <option value="draft">Draft</option>
                        <option value="in_progress">In Progress</option>
                        <option value="completed">Completed</option>
                        <option value="published">Published</option>
                      </select>
                    </label>
                    <label className="flex items-center gap-2">
                      <span>Type</span>
                      <select
                        value={editForm.paper_type || paper.paper_type}
                        onChange={(e) => setEditForm((prev) => ({ ...prev, paper_type: e.target.value }))}
                        className="rounded border border-gray-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                      >
                        <option value="research">Research</option>
                        <option value="review">Literature Review</option>
                        <option value="case_study">Case Study</option>
                        <option value="methodology">Methodology</option>
                        <option value="theoretical">Theoretical</option>
                        <option value="experimental">Experimental</option>
                      </select>
                    </label>
                    <label className="flex items-center gap-2">
                      <span>Visibility</span>
                      <select
                        value={(editForm.is_public ?? paper.is_public) ? 'true' : 'false'}
                        onChange={(e) => setEditForm((prev) => ({ ...prev, is_public: e.target.value === 'true' }))}
                        className="rounded border border-gray-300 px-2 py-1 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                      >
                        <option value="true">Public</option>
                        <option value="false">Private</option>
                      </select>
                    </label>
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600 dark:text-slate-400">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ${getStatusClassName(paper.status)}`}>
                      {paper.status.replace('_', ' ')}
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-gray-700 dark:bg-slate-800/60 dark:text-slate-200">
                      <BookOpen className="w-3 h-3" />
                      {getPaperTypeLabel(paper.paper_type)}
                    </span>
                    {paper.year ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-gray-700 dark:bg-slate-800/60 dark:text-slate-200">
                        <CalendarDays className="w-3 h-3" />
                        {paper.year}
                      </span>
                    ) : null}
                    {paper.doi ? (
                      <a
                        href={`https://doi.org/${paper.doi}`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-500/20 dark:text-indigo-200 dark:hover:bg-indigo-500/30"
                      >
                        <Link2 className="w-3 h-3" /> DOI
                      </a>
                    ) : null}
                    <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-gray-700 dark:bg-slate-800/60 dark:text-slate-200">
                      Docs: {documents.length}
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-full bg-gray-50 px-2 py-0.5 text-gray-600 dark:bg-slate-800/60 dark:text-slate-300">
                      Created: {new Date(paper.created_at).toLocaleDateString()}
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-full bg-gray-50 px-2 py-0.5 text-gray-600 dark:bg-slate-800/60 dark:text-slate-300">
                      Updated: {new Date(paper.updated_at).toLocaleDateString()}
                    </span>
                  </div>
                )}
              </div>
            </div>

          <div className="flex items-center gap-2">
            {!isEditing ? (
              <>
                <button
                  onClick={handleViewPaper}
                  className="inline-flex items-center gap-2 rounded-md border border-indigo-200 px-4 py-2 text-sm font-medium text-indigo-600 transition-colors hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
                >
                  <Eye className="w-4 h-4" />
                  View paper
                </button>
                {canEditPaper && (
                  <button
                    onClick={handleStartWriting}
                    className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-400"
                  >
                    <FileText className="w-4 h-4" />
                    Open editor
                  </button>
                )}
                {(canEditPaper || canDeletePaper) && (
                  <div className="relative" ref={actionsMenuRef}>
                    <button
                      onClick={() => setIsActionsMenuOpen((prev) => !prev)}
                      className="inline-flex items-center justify-center rounded-md border border-gray-200 p-2 text-gray-600 transition-colors hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                      aria-haspopup="menu"
                      aria-expanded={isActionsMenuOpen}
                      aria-label="Paper actions"
                    >
                      <MoreHorizontal className="w-4 h-4" />
                    </button>
                    {isActionsMenuOpen && (
                      <div className="absolute right-0 z-20 mt-2 w-48 rounded-lg border border-gray-200 bg-white py-2 shadow-lg transition-colors dark:border-slate-700 dark:bg-slate-900/75">
                        {canEditPaper && (
                          <button
                            onClick={() => {
                              setIsActionsMenuOpen(false)
                              setIsEditing(true)
                            }}
                            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:text-slate-200 dark:hover:bg-slate-800"
                          >
                            <Pencil className="h-4 w-4 text-gray-500 dark:text-slate-300" />
                            Edit details
                          </button>
                        )}
                        <button
                          onClick={() => {
                            setIsActionsMenuOpen(false)
                            /* TODO: implement share */
                          }}
                          className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:text-slate-200 dark:hover:bg-slate-800"
                        >
                          <Share2 className="h-4 w-4 text-gray-500 dark:text-slate-300" />
                          Share
                        </button>
                        {canDeletePaper && (
                          <button
                            onClick={() => {
                              setIsActionsMenuOpen(false)
                              handleDeletePaper()
                            }}
                            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-600 transition-colors hover:bg-red-50 dark:text-rose-300 dark:hover:bg-rose-500/10"
                          >
                            <Trash2 className="h-4 w-4" />
                            Delete paper
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </>
            ) : (
              <>
                <button
                  onClick={handleCancelEdit}
                  className="inline-flex items-center gap-2 rounded border border-gray-200 px-3 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                    <X className="w-4 h-4" />
                    Cancel
                  </button>
                  <button
                    onClick={handleSaveChanges}
                    disabled={isSaving}
                    className="inline-flex items-center gap-2 rounded bg-indigo-600 px-3 py-2 text-sm text-white transition-colors hover:bg-indigo-700 disabled:opacity-60 dark:bg-indigo-500 dark:hover:bg-indigo-400"
                  >
                    <Save className="w-4 h-4" />
                    {isSaving ? 'Saving…' : 'Save changes'}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800/60">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">Objectives</h2>
                <span className="text-xs uppercase tracking-wide text-gray-400">Project sourced</span>
              </div>
              {objectivesDisplay.length > 0 ? (
                <ul className="list-disc space-y-2 pl-5 text-sm text-gray-700 dark:text-slate-200">
                  {objectivesDisplay.map((objective) => (
                    <li key={objective}>{objective}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-gray-500 dark:text-slate-400">
                  No objectives linked to this paper. Objectives can be managed from the Project context page.
                </p>
              )}
            </section>
            <section className="flex flex-col rounded-lg border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800/60">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="flex items-center gap-2 text-lg font-semibold text-gray-900 dark:text-slate-100">
                    Attached references
                    <span className="text-sm font-normal text-gray-500 dark:text-slate-400">({references.length})</span>
                  </h2>
                  <p className="text-sm text-gray-600 dark:text-slate-300">
                    References stay aligned with the project library
                  </p>
                </div>
                {canManageReferences ? (
                  <button
                    onClick={() => setShowAttachModal(true)}
                    className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-2 text-sm text-white transition-colors hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-400"
                  >
                    Manage
                  </button>
                ) : null}
              </div>

              {references.length === 0 ? (
                <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-8 text-center text-sm text-gray-600 transition-colors dark:border-slate-700 dark:bg-slate-800/40 dark:text-slate-300">
                  <p>
                    No references attached yet. Pull approved references from the project library to cite them here.
                  </p>
                </div>
              ) : (
                <div className="-mr-2 max-h-96 space-y-3 overflow-y-auto pr-2 custom-scrollbar">
                  {references.map((ref) => (
                    <div
                      key={ref.paper_reference_id}
                      className="rounded-lg border border-gray-200 bg-gradient-to-br from-white to-gray-50/50 p-4 shadow-sm transition-shadow hover:shadow-md dark:border-slate-700 dark:from-slate-900/35 dark:to-slate-900/20"
                    >
                      <div className="flex flex-col gap-2.5 text-sm text-gray-700 dark:text-slate-200">
                        <div className="flex items-start justify-between gap-3">
                          <p className="flex-1 leading-snug font-semibold text-gray-900 dark:text-slate-100" title={ref.title || undefined}>
                            {ref.title || 'Untitled reference'}
                          </p>
                          {canManageReferences && ref.project_reference_id ? (
                            <button
                              onClick={async () => {
                                if (!project?.id || !paperId || !ref.project_reference_id) return
                                try {
                                  await projectReferencesAPI.detachFromPaper(
                                    project.id,
                                    ref.project_reference_id,
                                    paperId,
                                  )
                                  await refreshReferences()
                                } catch (error) {
                                  console.error('Error detaching reference', error)
                                  alert('Unable to detach this reference right now.')
                                }
                              }}
                              className="flex-shrink-0 rounded-md border border-red-200 px-2 py-1 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 dark:border-red-400/40 dark:text-red-200 dark:hover:bg-red-500/10"
                              title="Detach reference"
                            >
                              Detach
                            </button>
                          ) : null}
                        </div>

                        <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600 dark:text-slate-300">
                          {ref.authors?.length ? (
                            <span className="font-medium">{ref.authors.slice(0, 3).join(', ')}{ref.authors.length > 3 ? ' et al.' : ''}</span>
                          ) : null}
                          {ref.year ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 font-medium text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200">
                              {ref.year}
                            </span>
                          ) : null}
                          {ref.journal ? <span className="text-gray-500 dark:text-slate-400">• {ref.journal}</span> : null}
                        </div>

                        {ref.abstract ? (
                          <p className="text-xs leading-relaxed text-gray-600 dark:text-slate-300 line-clamp-2">{ref.abstract}</p>
                        ) : null}

                        <div className="flex items-center justify-between gap-3 border-t border-gray-100 pt-1 text-xs dark:border-slate-700">
                          <div className="flex items-center gap-3">
                            {ref.doi ? (
                              <a
                                href={`https://doi.org/${ref.doi}`}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 font-medium text-indigo-600 hover:text-indigo-700 hover:underline dark:text-indigo-300 dark:hover:text-indigo-200"
                              >
                                <Link2 className="w-3 h-3" />
                                DOI
                              </a>
                            ) : ref.url ? (
                              <a
                                href={ref.url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 font-medium text-indigo-600 hover:text-indigo-700 hover:underline dark:text-indigo-300 dark:hover:text-indigo-200"
                              >
                                <Link2 className="w-3 h-3" />
                                Link
                              </a>
                            ) : null}
                            {ref.project_reference_status && ref.project_reference_status !== 'approved' ? (
                              <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 font-medium text-amber-700 dark:bg-amber-300/20 dark:text-amber-200">
                                {ref.project_reference_status}
                              </span>
                            ) : null}
                          </div>
                          {ref.attached_at ? (
                            <span className="text-gray-500 dark:text-slate-400">Added {new Date(ref.attached_at).toLocaleDateString()}</span>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          <div className="space-y-6">
            <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-800 dark:bg-slate-800/60">
              <div className="mb-3 flex items-center gap-2">
                <Users className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">Team</h2>
              </div>
              <p className="mb-4 text-sm text-gray-600 dark:text-slate-300">
                Paper access follows the project roster.
              </p>
              {sortedProjectMembers.length === 0 ? (
                <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-800/40 dark:text-slate-400">
                  No collaborators yet.
                </div>
              ) : (
                <ul className="space-y-3">
                  {sortedProjectMembers.map((member) => {
                    const effectiveRole = normalizeMemberRole(member.role)
                    const status = (member.status || 'accepted').toLowerCase()
                    const isPending = status === 'invited'
                    const isDeclined = status === 'declined'
                    const isOwner = member.user_id === project?.created_by
                    const displayName = member.user?.display_name
                      || [member.user?.first_name, member.user?.last_name].filter(Boolean).join(' ').trim()
                      || member.user?.email
                      || member.user_id

                    return (
                      <li
                        key={member.id || member.user_id}
                        className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-sm transition-colors dark:border-slate-600/80 dark:bg-slate-800 dark:shadow-slate-950/30 dark:shadow-sm sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div className="flex items-start gap-3">
                          <div className="mt-1 flex h-8 w-8 items-center justify-center rounded-full bg-gray-100 dark:bg-slate-700/60">
                            {renderRoleIcon(effectiveRole)}
                          </div>
                          <div className="min-w-0">
                            <p className="flex items-center gap-2 truncate text-sm font-semibold text-gray-900 dark:text-slate-100">
                              <span className="truncate">{displayName}</span>
                              {member.user_id === currentUserId && (
                                <span className="text-[10px] uppercase tracking-wide text-indigo-500 dark:text-indigo-300">You</span>
                              )}
                              {isOwner && <Crown className="h-3 w-3 text-yellow-500 dark:text-amber-300" aria-label="Project owner" />}
                              {isPending && <Clock className="h-3 w-3 text-amber-500 dark:text-amber-300" aria-label="Invitation pending" />}
                            </p>
                            {member.user?.email && (
                              <p className="truncate text-xs text-gray-500 dark:text-slate-400">{member.user.email}</p>
                            )}
                            {status !== 'accepted' && (
                              <p
                                className={`mt-1 text-xs ${
                                  isPending ? 'text-amber-600' : isDeclined ? 'text-red-600' : 'text-gray-500'
                                }`}
                              >
                                Status: {status}
                              </p>
                            )}
                          </div>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </section>

            <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-800 dark:bg-slate-800/60">
              <h2 className="mb-3 text-lg font-semibold text-gray-900 dark:text-slate-100">Keywords</h2>
              {isEditing ? (
                <input
                  value={keywordInputValue}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, keywords: e.target.value }))}
                  className="w-full rounded border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                  placeholder="e.g. generative AI, survey design"
                />
              ) : keywordDisplay.length === 0 ? (
                <p className="text-sm text-gray-600 dark:text-slate-300">No keywords yet.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {keywordDisplay.map((keyword) => (
                    <span key={keyword} className="rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200">
                      {keyword}
                    </span>
                  ))}
                </div>
              )}
            </section>
          </div>
        </div>
      </main>

      {project?.id && paperId ? (
        <AttachProjectReferenceModal
          isOpen={showAttachModal}
          projectId={project.id}
          paperId={paperId}
          attachedProjectReferenceIds={references
            .map((ref) => ref.project_reference_id)
            .filter((id): id is string => Boolean(id))}
          onClose={() => setShowAttachModal(false)}
          onUpdated={async () => {
            setShowAttachModal(false)
            await refreshReferences()
          }}
        />
      ) : null}

      <ConfirmationModal
        isOpen={showDeletePaperConfirm}
        onClose={() => setShowDeletePaperConfirm(false)}
        onConfirm={confirmDeletePaper}
        title="Delete Research Paper"
        message="Are you sure you want to delete this research paper? This action cannot be undone."
        confirmText="Delete Paper"
        cancelText="Cancel"
        confirmButtonColor="red"
        icon="warning"
      />
    </div>
  )
}

export default PaperDetail
