import React, { useEffect, useMemo, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { researchPapersAPI } from '../../services/api'
import { ArrowLeft, CheckCircle, FileText } from 'lucide-react'
import { useProjectContext } from './ProjectLayout'
import { hasDuplicatePaperTitle } from '../../utils/papers'
import { parseObjectives } from '../../utils/objectives'
import { PAPER_TEMPLATES } from '../../constants/paperTemplates'

const CreatePaperWithTemplate: React.FC = () => {
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId?: string }>()
  const { project, currentRole } = useProjectContext()

  const [selectedTypeId, setSelectedTypeId] = useState<string>(PAPER_TEMPLATES[0].id)
  const [paperTitle, setPaperTitle] = useState('')
  const [paperKeywords, setPaperKeywords] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [authoringMode, setAuthoringMode] = useState<'rich' | 'latex'>('rich')
  const [createdPaper, setCreatedPaper] = useState<any>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [objectiveError, setObjectiveError] = useState<string | null>(null)
  const [objectives, setObjectives] = useState<string[]>(() => parseObjectives(project.scope))
  const [selectedObjectives, setSelectedObjectives] = useState<string[]>(() => {
    const parsed = parseObjectives(project.scope)
    return parsed.length ? [parsed[0]] : []
  })

  const toggleObjectiveSelection = (objective: string) => {
    setSelectedObjectives((prev) => {
      if (prev.includes(objective)) {
        return prev.filter((item) => item !== objective)
      }
      return [...prev, objective]
    })
    setObjectiveError(null)
  }

  useEffect(() => {
    const parsed = parseObjectives(project.scope)
    setObjectives(parsed)
    setSelectedObjectives((current) => {
      const filtered = current.filter((item) => parsed.includes(item))
      if (filtered.length > 0) return filtered
      return parsed.length ? [parsed[0]] : []
    })
  }, [project.scope])

  const { data: existingProjectPapers } = useQuery({
    queryKey: ['project-papers', projectId],
    queryFn: async () => {
      if (!projectId) return []
      const response = await researchPapersAPI.getPapers({ projectId, limit: 500 })
      return response.data.papers ?? []
    },
    enabled: Boolean(projectId),
  })

  const duplicateTitle = useMemo(() => {
    if (!projectId) return false
    if (!paperTitle) return false
    const existing = (existingProjectPapers ?? []).map((paper) => ({
      title: paper.title,
      projectId: paper.project_id ?? null,
    }))
    return hasDuplicatePaperTitle(existing, paperTitle, projectId)
  }, [existingProjectPapers, paperTitle, projectId])

  const selectedTemplateDefinition = useMemo(() => {
    return PAPER_TEMPLATES.find((template) => template.id === selectedTypeId) ?? PAPER_TEMPLATES[0]
  }, [selectedTypeId])

  const handleCreatePaper = async () => {
    if (!paperTitle.trim()) {
      setErrorMessage('Paper title is required.')
      return
    }
    if (selectedObjectives.length === 0) {
      setObjectiveError('Please choose or create at least one objective before continuing.')
      return
    }
    if (duplicateTitle) {
      setErrorMessage('A paper with this title already exists in this project.')
      return
    }

    setIsCreating(true)
    setErrorMessage(null)
    try {
      const templateDefinition = selectedTemplateDefinition
      const keywordsArray = paperKeywords
        .split(',')
        .map((kw) => kw.trim())
        .filter(Boolean)
      const paperData: any = {
        title: paperTitle.trim(),
        paper_type: templateDefinition.id,
        status: 'draft',
        keywords: keywordsArray,
        references: '',
        is_public: false,
        objectives: selectedObjectives,
      }

      if (authoringMode === 'latex') {
        paperData.content_json = { authoring_mode: 'latex', latex_source: templateDefinition.latexTemplate }
      } else {
        paperData.content = templateDefinition.richTemplate
        paperData.content_json = { authoring_mode: 'rich' }
      }

      if (projectId) {
        paperData.project_id = projectId
      }

      const response = await researchPapersAPI.createPaper(paperData)
      const newPaper = response.data
      setCreatedPaper(newPaper)

      setTimeout(() => {
        const targetProjectId = projectId || newPaper.project_id
        if (targetProjectId) {
          navigate(`/projects/${targetProjectId}/papers/${newPaper.id}/editor`)
        } else {
          navigate(`/projects`)
        }
      }, 2000)
    } catch (error: any) {
      console.error('Error creating paper:', error)
      const detail = extractApiDetail(error) ?? 'Failed to create paper. Please try again.'
      setErrorMessage(detail)
    } finally {
      setIsCreating(false)
    }
  }

  const handleBack = () => {
    navigate(projectId ? `/projects/${projectId}` : '/projects')
  }

  if (currentRole === 'viewer') {
    return <Navigate to={projectId ? `/projects/${projectId}/papers` : '/projects'} replace />
  }

  if (createdPaper) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-indigo-50 via-white to-white flex items-center justify-center px-4">
        <div className="w-full max-w-xl rounded-3xl border border-indigo-100 bg-white shadow-xl p-8 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-green-100 text-green-600">
            <CheckCircle className="h-8 w-8" />
          </div>
          <h2 className="mt-6 text-2xl font-semibold text-gray-900">Paper created successfully</h2>
          <p className="mt-2 text-sm text-gray-600">
            “{createdPaper.title}” is ready. We’re opening the editor so you can start writing right away.
          </p>
          <div className="mt-6 flex items-center justify-center gap-2 text-sm font-medium text-indigo-600">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />
            Redirecting to editor…
          </div>
        </div>
      </div>
    )
  }

  const objectivesAvailable = objectives.length > 0

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-4">
              <button onClick={handleBack} className="text-gray-400 hover:text-gray-600 transition-colors">
                <ArrowLeft size={24} />
              </button>
              <div className="flex items-center gap-2">
                <FileText size={24} className="text-blue-600" />
                <h1 className="text-xl font-semibold text-gray-900">Create New Paper</h1>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 space-y-6">
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Paper Type & Template *</p>
            <div className="grid gap-3 md:grid-cols-3">
              {PAPER_TEMPLATES.map((template) => {
                const isSelected = template.id === selectedTemplateDefinition.id
                return (
                  <button
                    key={template.id}
                    type="button"
                    onClick={() => setSelectedTypeId(template.id)}
                    className={`rounded-xl border px-4 py-3 text-left transition ${
                      isSelected ? 'border-indigo-500 bg-indigo-50 text-indigo-900' : 'border-gray-200 hover:border-indigo-200'
                    }`}
                  >
                    <p className="text-sm font-semibold">{template.label}</p>
                    <p className="mt-1 text-xs text-gray-600">{template.description}</p>
                  </button>
                )
              })}
            </div>
            <div className="mt-3 rounded-lg border border-dashed border-gray-200 bg-gray-50 p-3">
              <p className="text-xs font-semibold uppercase text-gray-500">Template sections</p>
              <ul className="mt-1 list-disc pl-5 text-xs text-gray-700">
                {selectedTemplateDefinition.sections.map((section) => (
                  <li key={section}>{section}</li>
                ))}
              </ul>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Paper Title *</label>
            <input
              type="text"
              value={paperTitle}
              onChange={(e) => {
                setPaperTitle(e.target.value)
                if (errorMessage) setErrorMessage(null)
              }}
              className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                errorMessage || duplicateTitle ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder="Enter your paper title..."
            />
            {errorMessage && <p className="mt-2 text-sm text-red-600">{errorMessage}</p>}
            {!errorMessage && duplicateTitle && (
              <p className="mt-2 text-sm text-red-600">A paper with this title already exists in this project.</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Keywords</label>
            <input
              type="text"
              value={paperKeywords}
              onChange={(e) => setPaperKeywords(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g., robotics, haptics, perception"
            />
            <p className="text-xs text-gray-500 mt-1">Separate keywords with commas.</p>
          </div>

          <div>
            <p className="block text-sm font-medium text-gray-700 mb-2">Objectives *</p>
            {objectivesAvailable ? (
              <div className="space-y-2 rounded-md border border-gray-200 p-3 max-h-48 overflow-y-auto">
                {objectives.map((objective) => {
                  const checked = selectedObjectives.includes(objective)
                  return (
                    <label key={objective} className="flex items-start gap-2 text-sm text-gray-700">
                      <input
                        type="checkbox"
                        className="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        checked={checked}
                        onChange={() => toggleObjectiveSelection(objective)}
                      />
                      <span>{objective}</span>
                    </label>
                  )
                })}
              </div>
            ) : (
              <p className="text-sm text-gray-500">No objectives recorded yet for this project. Add objectives from the Project context before creating a paper.</p>
            )}
            {objectiveError && <p className="mt-2 text-sm text-red-600">{objectiveError}</p>}
            {selectedObjectives.length === 0 && !objectiveError && (
              <p className="mt-1 text-xs text-rose-500">Select at least one objective for this paper.</p>
            )}
          </div>

          <div className="bg-gray-50 rounded-lg p-4">
            <h3 className="text-sm font-medium text-gray-700 mb-2">Authoring Mode</h3>
            <div className="flex items-center gap-4">
              <label className="inline-flex items-center gap-2 text-sm">
                <input type="radio" name="authoring_mode" checked={authoringMode === 'rich'} onChange={() => setAuthoringMode('rich')} />
                Rich Text
              </label>
              <label className="inline-flex items-center gap-2 text-sm">
                <input type="radio" name="authoring_mode" checked={authoringMode === 'latex'} onChange={() => setAuthoringMode('latex')} />
                LaTeX
              </label>
            </div>
            <p className="text-xs text-gray-500 mt-1">Papers are locked to one mode. No auto-conversion between modes.</p>
          </div>

          <div className="flex justify-end gap-3">
            <button
              onClick={handleBack}
              className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleCreatePaper}
              disabled={isCreating || !paperTitle.trim() || duplicateTitle || selectedObjectives.length === 0}
              className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              {isCreating ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  Creating...
                </>
              ) : (
                <>
                  <FileText size={16} />
                  Create Paper
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default CreatePaperWithTemplate

const extractApiDetail = (error: unknown): string | null => {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response
    const detail = response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
  }
  return null
}
