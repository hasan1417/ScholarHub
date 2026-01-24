import React, { useState, useEffect, useMemo, useRef } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  BookOpen,
  Check,
  Eye,
  FileText,
  Link2,
  MoreHorizontal,
  Pencil,
  Plus,
  Save,
  Settings,
  Target,
  Trash2,
  Unlink,
  X,
} from 'lucide-react'

// Strip XML/HTML tags from text (e.g., <jats:p> from abstracts)
const stripXmlTags = (text: string | null | undefined): string => {
  if (!text) return ''
  return text.replace(/<[^>]*>/g, '').trim()
}


import {
  projectReferencesAPI,
  researchPapersAPI,
  teamAPI,
} from '../../services/api'
import {
  PaperReferenceAttachment,
  ResearchPaper,
  ResearchPaperUpdate,
} from '../../types'
import ConfirmationModal from '../../components/common/ConfirmationModal'
import AttachProjectReferenceModal from '../../components/projects/AttachProjectReferenceModal'
import TeamInviteModal from '../../components/team/TeamInviteModal'
import TeamMembersList from '../../components/team/TeamMembersList'
import { useAuth } from '../../contexts/AuthContext'
import { useProjectContext } from './ProjectLayout'
import { parseObjectives } from '../../utils/objectives'

const PaperDetail: React.FC = () => {
  const { projectId, paperId } = useParams<{ projectId?: string; paperId: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { project } = useProjectContext()

  const [paper, setPaper] = useState<ResearchPaper | null>(null)
  const [references, setReferences] = useState<PaperReferenceAttachment[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [showDeletePaperConfirm, setShowDeletePaperConfirm] = useState(false)
  const [showAttachModal, setShowAttachModal] = useState(false)
  const [isActionsMenuOpen, setIsActionsMenuOpen] = useState(false)
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [teamRefreshKey, setTeamRefreshKey] = useState(0)
  const [showObjectivesModal, setShowObjectivesModal] = useState(false)
  const [selectedObjectives, setSelectedObjectives] = useState<string[]>([])
  const [isSavingObjectives, setIsSavingObjectives] = useState(false)

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


  const handleInvite = async (email: string, role: string) => {
    if (!paperId) return
    await teamAPI.inviteTeamMember(paperId, email, role)
    // Trigger refresh of TeamMembersList
    setTeamRefreshKey((k) => k + 1)
  }

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

  const getPaperTypeLabel = (type: string) => {
    const mapping: Record<string, string> = {
      research: 'Research',
      review: 'Literature Review',
      literature_review: 'Literature Review',
      case_study: 'Case Study',
      methodology: 'Methodology',
      theoretical: 'Theoretical',
      experimental: 'Experimental',
      survey: 'Survey',
      tutorial: 'Tutorial',
      position: 'Position Paper',
    }
    // Format unknown types nicely: some_type -> Some Type
    return mapping[type] || type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  }

  const getPaperTypeColor = (type: string) => {
    const normalized = type?.toLowerCase() || ''
    if (normalized.includes('research')) return 'text-blue-600 dark:text-blue-400'
    if (normalized.includes('review') || normalized.includes('literature')) return 'text-emerald-600 dark:text-emerald-400'
    if (normalized.includes('case') || normalized.includes('study')) return 'text-cyan-600 dark:text-cyan-400'
    if (normalized.includes('methodology')) return 'text-violet-600 dark:text-violet-400'
    if (normalized.includes('theoretical')) return 'text-purple-600 dark:text-purple-400'
    if (normalized.includes('experimental')) return 'text-orange-600 dark:text-orange-400'
    return 'text-gray-600 dark:text-slate-300'
  }

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

  const projectObjectives = useMemo(() => parseObjectives(project?.scope), [project?.scope])

  const handleOpenObjectivesModal = () => {
    setSelectedObjectives(objectivesDisplay)
    setShowObjectivesModal(true)
  }

  const toggleObjectiveSelection = (objective: string) => {
    setSelectedObjectives((prev) =>
      prev.includes(objective)
        ? prev.filter((item) => item !== objective)
        : [...prev, objective]
    )
  }

  const handleSaveObjectives = async () => {
    if (!paper) return
    try {
      setIsSavingObjectives(true)
      const response = await researchPapersAPI.updatePaper(paper.id, {
        objectives: selectedObjectives,
      })
      setPaper(response.data)
      setShowObjectivesModal(false)
    } catch (err) {
      console.error('Failed to save objectives', err)
      alert('Failed to save objectives. Please try again.')
    } finally {
      setIsSavingObjectives(false)
    }
  }

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
      <header className="border-b bg-white transition-colors dark:border-slate-700 dark:bg-slate-900/70">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          {/* Top row: Back link + Actions */}
          <div className="mb-4 flex items-center justify-between">
            <Link
              to={resolveProjectPath('/papers')}
              className="inline-flex items-center gap-2 text-sm text-gray-500 transition-colors hover:text-gray-700 dark:text-slate-400 dark:hover:text-slate-200"
            >
              <ArrowLeft className="h-4 w-4" />
              Papers
            </Link>

            <div className="flex items-center gap-2">
              {!isEditing ? (
                <>
                  <button
                    onClick={handleViewPaper}
                    className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    <Eye className="h-4 w-4" />
                    View
                  </button>
                  {canEditPaper && (
                    <button
                      onClick={handleStartWriting}
                      className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-400"
                    >
                      <Pencil className="h-4 w-4" />
                      Write
                    </button>
                  )}
                  {(canEditPaper || canDeletePaper) && (
                    <div className="relative" ref={actionsMenuRef}>
                      <button
                        onClick={() => setIsActionsMenuOpen((prev) => !prev)}
                        className="inline-flex items-center justify-center rounded-lg border border-gray-200 p-1.5 text-gray-500 transition-colors hover:bg-gray-50 dark:border-slate-600 dark:text-slate-400 dark:hover:bg-slate-800"
                        aria-haspopup="menu"
                        aria-expanded={isActionsMenuOpen}
                        aria-label="Paper actions"
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                      {isActionsMenuOpen && (
                        <div className="absolute right-0 z-20 mt-2 w-48 rounded-lg border border-gray-200 bg-white py-1 shadow-lg transition-colors dark:border-slate-700 dark:bg-slate-900">
                          {canEditPaper && (
                            <button
                              onClick={() => {
                                setIsActionsMenuOpen(false)
                                setIsEditing(true)
                              }}
                              className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:text-slate-200 dark:hover:bg-slate-800"
                            >
                              <Pencil className="h-4 w-4 text-gray-400 dark:text-slate-400" />
                              Edit details
                            </button>
                          )}
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
                    className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-600 transition-colors hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    <X className="h-4 w-4" />
                    Cancel
                  </button>
                  <button
                    onClick={handleSaveChanges}
                    disabled={isSaving}
                    className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-60 dark:bg-indigo-500 dark:hover:bg-indigo-400"
                  >
                    <Save className="h-4 w-4" />
                    {isSaving ? 'Saving…' : 'Save changes'}
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Title row */}
          {isEditing ? (
            <div className="rounded-xl border border-indigo-100 bg-indigo-50/30 p-6 dark:border-indigo-500/20 dark:bg-indigo-500/5">
              <div className="mb-4 flex items-center gap-2 text-sm font-medium text-indigo-600 dark:text-indigo-400">
                <Pencil className="h-4 w-4" />
                Editing Paper Details
              </div>
              <input
                value={editForm.title || ''}
                onChange={(e) => setEditForm((prev) => ({ ...prev, title: e.target.value }))}
                className="mb-5 w-full rounded-lg border border-gray-200 bg-white px-4 py-3 text-xl font-semibold text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                placeholder="Paper title"
              />
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div>
                  <label className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-slate-300">
                    <div className="flex h-6 w-6 items-center justify-center rounded-md bg-amber-100 dark:bg-amber-500/20">
                      <Settings className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                    </div>
                    Status
                  </label>
                  <select
                    value={editForm.status || paper.status}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, status: e.target.value }))}
                    className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                  >
                    <option value="draft">Draft</option>
                    <option value="in_progress">In Progress</option>
                    <option value="completed">Completed</option>
                    <option value="published">Published</option>
                  </select>
                </div>
                <div>
                  <label className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-slate-300">
                    <div className="flex h-6 w-6 items-center justify-center rounded-md bg-blue-100 dark:bg-blue-500/20">
                      <FileText className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
                    </div>
                    Type
                  </label>
                  <select
                    value={editForm.paper_type || paper.paper_type}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, paper_type: e.target.value }))}
                    className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                  >
                    <option value="research">Research</option>
                    <option value="review">Literature Review</option>
                    <option value="case_study">Case Study</option>
                    <option value="methodology">Methodology</option>
                    <option value="theoretical">Theoretical</option>
                    <option value="experimental">Experimental</option>
                  </select>
                </div>
                <div>
                  <label className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-slate-300">
                    <div className="flex h-6 w-6 items-center justify-center rounded-md bg-gray-100 dark:bg-slate-700">
                      <Eye className="h-3.5 w-3.5 text-gray-600 dark:text-slate-400" />
                    </div>
                    Visibility
                  </label>
                  <select
                    value={(editForm.is_public ?? paper.is_public) ? 'true' : 'false'}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, is_public: e.target.value === 'true' }))}
                    className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                  >
                    <option value="false">Private</option>
                    <option value="true">Public</option>
                  </select>
                </div>
              </div>
            </div>
          ) : (
            <div>
              <h1 className="text-2xl font-semibold text-gray-900 dark:text-slate-100">
                {paper.title || 'Untitled Paper'}
              </h1>
              <div className="mt-2 flex items-center gap-2 text-sm text-gray-500 dark:text-slate-400">
                <span className={`capitalize font-medium ${
                  paper.status === 'draft' ? 'text-amber-600 dark:text-amber-400' :
                  paper.status === 'in_progress' ? 'text-blue-600 dark:text-blue-400' :
                  paper.status === 'completed' ? 'text-emerald-600 dark:text-emerald-400' :
                  paper.status === 'published' ? 'text-indigo-600 dark:text-indigo-400' :
                  'text-gray-600 dark:text-slate-300'
                }`}>{paper.status.replace('_', ' ')}</span>
                <span className="text-gray-300 dark:text-slate-600">•</span>
                <span className={getPaperTypeColor(paper.paper_type)}>{getPaperTypeLabel(paper.paper_type)}</span>
                <span className="text-gray-300 dark:text-slate-600">•</span>
                <span>Last edited {new Date(paper.updated_at).toLocaleDateString()}</span>
              </div>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800/60">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h2 className="flex items-center gap-2 text-lg font-semibold text-gray-900 dark:text-slate-100">
                    Research Goals
                    {objectivesDisplay.length > 0 && (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-sm font-normal text-gray-600 dark:bg-slate-700 dark:text-slate-300">
                        {objectivesDisplay.length}
                      </span>
                    )}
                  </h2>
                  <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">
                    Linked to project objectives
                  </p>
                </div>
                {canEditPaper && projectObjectives.length > 0 && (
                  <button
                    onClick={handleOpenObjectivesModal}
                    className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-600 transition-colors hover:bg-indigo-100 dark:border-indigo-400/40 dark:bg-indigo-500/10 dark:text-indigo-300 dark:hover:bg-indigo-500/20"
                  >
                    <Target className="h-4 w-4" />
                    Edit
                  </button>
                )}
              </div>
              {objectivesDisplay.length > 0 ? (
                <ol className="space-y-2">
                  {objectivesDisplay.map((objective, index) => (
                    <li
                      key={objective}
                      className="flex items-start gap-3 text-sm text-gray-700 dark:text-slate-300"
                    >
                      <span className="flex-shrink-0 flex items-center justify-center h-5 w-5 rounded-full bg-indigo-100 text-xs font-semibold text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
                        {index + 1}
                      </span>
                      <span className="leading-relaxed">{objective}</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-4 text-center dark:border-slate-700 dark:bg-slate-800/40">
                  <Target className="mx-auto h-8 w-8 text-gray-300 dark:text-slate-600" />
                  <p className="mt-2 text-sm text-gray-500 dark:text-slate-400">
                    No goals linked to this paper yet.
                  </p>
                  {canEditPaper && projectObjectives.length > 0 ? (
                    <button
                      onClick={handleOpenObjectivesModal}
                      className="mt-2 text-sm text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300"
                    >
                      Link project goals
                    </button>
                  ) : (
                    <p className="mt-1 text-xs text-gray-400 dark:text-slate-500">
                      {projectObjectives.length === 0
                        ? 'Define objectives in project settings first'
                        : 'Goals can be linked by editors'}
                    </p>
                  )}
                </div>
              )}
            </section>
            <section className="flex flex-col rounded-xl border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800/60">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="flex items-center gap-2 text-lg font-semibold text-gray-900 dark:text-slate-100">
                    Attached references
                    {references.length > 0 && (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-sm font-normal text-gray-600 dark:bg-slate-700 dark:text-slate-300">
                        {references.length}
                      </span>
                    )}
                  </h2>
                  <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">
                    Citations from your project library
                  </p>
                </div>
                {canManageReferences && (
                  <button
                    onClick={() => setShowAttachModal(true)}
                    className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-600 transition-colors hover:bg-indigo-100 dark:border-indigo-400/40 dark:bg-indigo-500/10 dark:text-indigo-300 dark:hover:bg-indigo-500/20"
                  >
                    <Plus className="h-4 w-4" />
                    Manage
                  </button>
                )}
              </div>

              {references.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 px-4 py-8 text-center transition-colors dark:border-slate-700 dark:bg-slate-800/40">
                  <BookOpen className="mx-auto h-8 w-8 text-gray-300 dark:text-slate-600" />
                  <p className="mt-2 text-sm text-gray-600 dark:text-slate-300">
                    No references attached yet
                  </p>
                  <p className="mt-1 text-xs text-gray-400 dark:text-slate-500">
                    Add references from your project library to cite them in this paper
                  </p>
                </div>
              ) : (
                <div className="-mr-2 max-h-[420px] space-y-3 overflow-y-auto pr-2 custom-scrollbar">
                  {references.map((ref) => (
                    <div
                      key={ref.paper_reference_id}
                      className="group rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition hover:border-gray-300 dark:border-slate-700 dark:bg-slate-800/40 dark:hover:border-slate-600"
                    >
                      <div className="flex flex-col gap-2.5 text-sm">
                        {/* Title row */}
                        <div className="flex items-start justify-between gap-3">
                          <h4 className="flex-1 font-semibold leading-snug text-gray-900 dark:text-slate-100">
                            {ref.title || 'Untitled reference'}
                          </h4>
                          {canManageReferences && ref.project_reference_id && (
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
                              className="flex-shrink-0 rounded-lg border border-gray-200 p-1.5 text-gray-400 opacity-0 transition-all hover:border-gray-300 hover:bg-gray-50 hover:text-gray-600 group-hover:opacity-100 dark:border-slate-600 dark:text-slate-500 dark:hover:border-slate-500 dark:hover:bg-slate-700 dark:hover:text-slate-300"
                              title="Remove from paper"
                            >
                              <Unlink className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </div>

                        {/* Authors, Year, Journal row */}
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-600 dark:text-slate-400">
                          {ref.authors?.length ? (
                            <span>{ref.authors.slice(0, 3).join(', ')}{ref.authors.length > 3 ? ' et al.' : ''}</span>
                          ) : null}
                          {ref.year && (
                            <span className="rounded bg-gray-100 px-1.5 py-0.5 font-medium text-gray-700 dark:bg-slate-700 dark:text-slate-300">
                              {ref.year}
                            </span>
                          )}
                          {ref.journal && (
                            <>
                              <span className="text-gray-300 dark:text-slate-600">•</span>
                              <span className="italic">{ref.journal}</span>
                            </>
                          )}
                        </div>

                        {/* Abstract - with XML stripped */}
                        {ref.abstract && (
                          <p className="text-xs leading-relaxed text-gray-500 line-clamp-2 dark:text-slate-400">
                            {stripXmlTags(ref.abstract)}
                          </p>
                        )}

                        {/* Footer: Links and date */}
                        <div className="flex items-center justify-between gap-3 pt-2 text-xs">
                          <div className="flex items-center gap-3">
                            {ref.doi && (
                              <a
                                href={`https://doi.org/${ref.doi}`}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                              >
                                <Link2 className="h-3 w-3" />
                                DOI
                              </a>
                            )}
                            {!ref.doi && ref.url && (
                              <a
                                href={ref.url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                              >
                                <Link2 className="h-3 w-3" />
                                Source
                              </a>
                            )}
                            {ref.project_reference_status && ref.project_reference_status !== 'approved' && (
                              <span className="rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-700 dark:bg-amber-500/20 dark:text-amber-300">
                                {ref.project_reference_status}
                              </span>
                            )}
                          </div>
                          {ref.attached_at && (
                            <span className="text-gray-400 dark:text-slate-500">
                              Added {new Date(ref.attached_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          <div className="space-y-6">
            <TeamMembersList
                paperId={paperId}
                onInviteMember={canEditPaper ? () => setShowInviteModal(true) : undefined}
                refreshKey={teamRefreshKey}
              />

            <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800/60">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">Keywords</h2>
                {!isEditing && keywordDisplay.length === 0 && canEditPaper && (
                  <button
                    onClick={() => setIsEditing(true)}
                    className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300"
                  >
                    <Plus className="h-3 w-3" />
                    Add
                  </button>
                )}
              </div>
              {isEditing ? (
                <input
                  value={keywordInputValue}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, keywords: e.target.value }))}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                  placeholder="e.g. generative AI, survey design"
                />
              ) : keywordDisplay.length === 0 ? (
                <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-4 text-center dark:border-slate-700 dark:bg-slate-800/40">
                  <p className="text-sm text-gray-500 dark:text-slate-400">No keywords yet</p>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {keywordDisplay.map((keyword) => (
                    <span
                      key={keyword}
                      className="rounded-full bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200"
                    >
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

      <TeamInviteModal
        isOpen={showInviteModal}
        onClose={() => setShowInviteModal(false)}
        onInvite={handleInvite}
        paperTitle={paper?.title || 'this paper'}
      />

      {/* Objectives Modal */}
      {showObjectivesModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div
            className="relative w-full max-w-lg rounded-2xl bg-white shadow-2xl dark:bg-slate-800"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-slate-700">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-slate-100">
                  Link Project Goals
                </h3>
                <p className="mt-0.5 text-sm text-gray-500 dark:text-slate-400">
                  Select which project objectives this paper addresses
                </p>
              </div>
              <button
                onClick={() => setShowObjectivesModal(false)}
                className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-slate-700 dark:hover:text-slate-200"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="max-h-[60vh] overflow-y-auto px-6 py-4">
              {projectObjectives.length === 0 ? (
                <p className="text-center text-sm text-gray-500 dark:text-slate-400">
                  No objectives defined in project settings.
                </p>
              ) : (
                <div className="space-y-2">
                  {projectObjectives.map((objective) => {
                    const isSelected = selectedObjectives.includes(objective)
                    return (
                      <button
                        key={objective}
                        type="button"
                        onClick={() => toggleObjectiveSelection(objective)}
                        className={`flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors ${
                          isSelected
                            ? 'border-indigo-500 bg-indigo-50 dark:border-indigo-400 dark:bg-indigo-900/30'
                            : 'border-gray-200 bg-white hover:border-indigo-300 hover:bg-gray-50 dark:border-slate-600 dark:bg-slate-800 dark:hover:border-indigo-500 dark:hover:bg-slate-700'
                        }`}
                      >
                        <div
                          className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded ${
                            isSelected
                              ? 'bg-indigo-600 text-white'
                              : 'border-2 border-gray-300 dark:border-slate-500'
                          }`}
                        >
                          {isSelected && <Check className="h-3 w-3" />}
                        </div>
                        <span
                          className={`text-sm ${
                            isSelected
                              ? 'font-medium text-indigo-700 dark:text-indigo-300'
                              : 'text-gray-700 dark:text-slate-300'
                          }`}
                        >
                          {objective}
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            <div className="flex items-center justify-between border-t border-gray-200 px-6 py-4 dark:border-slate-700">
              <span className="text-sm text-gray-500 dark:text-slate-400">
                {selectedObjectives.length} of {projectObjectives.length} selected
              </span>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setShowObjectivesModal(false)}
                  className="rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-700"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveObjectives}
                  disabled={isSavingObjectives}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-60 dark:bg-indigo-500 dark:hover:bg-indigo-600"
                >
                  {isSavingObjectives ? (
                    <>
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="h-4 w-4" />
                      Save
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default PaperDetail
