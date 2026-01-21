import React, { useEffect, useMemo, useState, useCallback, KeyboardEvent } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { researchPapersAPI } from '../../services/api'
import { AlertTriangle, ArrowLeft, Check, CheckCircle, ChevronDown, ChevronUp, FileText, X } from 'lucide-react'
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
  const [keywordTags, setKeywordTags] = useState<string[]>([])
  const [keywordInput, setKeywordInput] = useState('')
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
  const [showSections, setShowSections] = useState(false)

  // Keyword tag handlers
  const addKeyword = useCallback((keyword: string) => {
    const trimmed = keyword.trim().toLowerCase()
    if (trimmed && !keywordTags.includes(trimmed)) {
      setKeywordTags((prev) => [...prev, trimmed])
    }
    setKeywordInput('')
  }, [keywordTags])

  const removeKeyword = useCallback((keyword: string) => {
    setKeywordTags((prev) => prev.filter((k) => k !== keyword))
  }, [])

  const handleKeywordKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addKeyword(keywordInput)
    } else if (e.key === 'Backspace' && !keywordInput && keywordTags.length > 0) {
      removeKeyword(keywordTags[keywordTags.length - 1])
    }
  }, [keywordInput, keywordTags, addKeyword, removeKeyword])

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
      const paperData: any = {
        title: paperTitle.trim(),
        paper_type: templateDefinition.id,
        status: 'draft',
        keywords: keywordTags,
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
      <div className="min-h-screen bg-gradient-to-b from-indigo-50 via-white to-white dark:from-slate-900 dark:via-slate-900 dark:to-slate-900 flex items-center justify-center px-4">
        <div className="w-full max-w-xl rounded-3xl border border-indigo-100 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-xl p-8 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400">
            <CheckCircle className="h-8 w-8" />
          </div>
          <h2 className="mt-6 text-2xl font-semibold text-gray-900 dark:text-slate-100">Paper created successfully</h2>
          <p className="mt-2 text-sm text-gray-600 dark:text-slate-400">
            "{createdPaper.title}" is ready. We're opening the editor so you can start writing right away.
          </p>
          <div className="mt-6 flex items-center justify-center gap-2 text-sm font-medium text-indigo-600 dark:text-indigo-400">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-200 dark:border-indigo-800 border-t-indigo-600 dark:border-t-indigo-400" />
            Redirecting to editor…
          </div>
        </div>
      </div>
    )
  }

  const objectivesAvailable = objectives.length > 0

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-slate-900">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        {/* Header - aligned with form */}
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={handleBack}
            className="flex items-center justify-center h-10 w-10 rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200 hover:border-gray-300 dark:hover:border-slate-600 transition-colors shadow-sm"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2.5">
            <div className="flex items-center justify-center h-10 w-10 rounded-xl bg-indigo-100 dark:bg-indigo-900/30">
              <FileText className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-slate-100">Create New Paper</h1>
          </div>
        </div>

        {/* Form */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-200 dark:border-slate-700 p-6 md:p-8 space-y-8">
          {/* Paper Type Selection */}
          <section>
            <p className="text-sm font-medium text-gray-700 dark:text-slate-300 mb-3">Paper Type & Template *</p>
            <div className="grid gap-3 md:grid-cols-3">
              {PAPER_TEMPLATES.map((template) => {
                const isSelected = template.id === selectedTemplateDefinition.id
                return (
                  <button
                    key={template.id}
                    type="button"
                    onClick={() => setSelectedTypeId(template.id)}
                    className={`relative rounded-xl border-2 px-4 py-4 text-left transition-all ${
                      isSelected
                        ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20 ring-1 ring-indigo-500'
                        : 'border-gray-200 dark:border-slate-600 hover:border-indigo-300 dark:hover:border-indigo-500 hover:bg-gray-50 dark:hover:bg-slate-700/50'
                    }`}
                  >
                    {isSelected && (
                      <span className="absolute top-3 right-3 flex h-5 w-5 items-center justify-center rounded-full bg-indigo-500 text-white">
                        <Check className="h-3 w-3" />
                      </span>
                    )}
                    <p className={`text-sm font-semibold ${isSelected ? 'text-indigo-900 dark:text-indigo-200' : 'text-gray-900 dark:text-slate-100'}`}>
                      {template.label}
                    </p>
                    <p className={`mt-1 text-xs ${isSelected ? 'text-indigo-700 dark:text-indigo-300' : 'text-gray-500 dark:text-slate-400'}`}>
                      {template.description}
                    </p>
                  </button>
                )
              })}
            </div>

            {/* Collapsible Template Sections */}
            <button
              type="button"
              onClick={() => setShowSections(!showSections)}
              className="mt-3 flex w-full items-center justify-between rounded-lg border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700/50 px-4 py-2.5 text-left text-xs font-medium text-gray-600 dark:text-slate-300 transition hover:bg-gray-100 dark:hover:bg-slate-700"
            >
              <span>View template sections ({selectedTemplateDefinition.sections.length})</span>
              {showSections ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
            {showSections && (
              <div className="mt-2 rounded-lg border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700/50 p-4">
                <div className="flex flex-wrap gap-2">
                  {selectedTemplateDefinition.sections.map((section) => (
                    <span
                      key={section}
                      className="inline-flex items-center rounded-full bg-white dark:bg-slate-600 px-3 py-1 text-xs font-medium text-gray-700 dark:text-slate-200 border border-gray-200 dark:border-slate-500"
                    >
                      {section}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* Paper Title */}
          <section>
            <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">Paper Title *</label>
            <input
              type="text"
              value={paperTitle}
              onChange={(e) => {
                setPaperTitle(e.target.value)
                if (errorMessage) setErrorMessage(null)
              }}
              className={`w-full px-4 py-2.5 border-2 rounded-xl bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 placeholder-gray-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition ${
                errorMessage || duplicateTitle ? 'border-red-400 dark:border-red-500 bg-red-50 dark:bg-red-900/20' : 'border-gray-200 dark:border-slate-600'
              }`}
              placeholder="Enter your paper title..."
            />
            {errorMessage && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{errorMessage}</p>}
            {!errorMessage && duplicateTitle && (
              <p className="mt-2 text-sm text-red-600 dark:text-red-400">A paper with this title already exists in this project.</p>
            )}
          </section>

          {/* Keywords & Objectives - 2 column on desktop */}
          <div className="grid gap-6 md:grid-cols-2">
            {/* Keywords as Tags */}
            <section>
              <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">Keywords</label>
              <div className="min-h-[44px] flex flex-wrap items-center gap-2 rounded-xl border-2 border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500 transition">
                {keywordTags.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 rounded-full bg-indigo-100 dark:bg-indigo-900/40 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:text-indigo-300"
                  >
                    {tag}
                    <button
                      type="button"
                      onClick={() => removeKeyword(tag)}
                      className="ml-0.5 rounded-full p-0.5 hover:bg-indigo-200 dark:hover:bg-indigo-800 transition"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
                <input
                  type="text"
                  value={keywordInput}
                  onChange={(e) => setKeywordInput(e.target.value)}
                  onKeyDown={handleKeywordKeyDown}
                  onBlur={() => keywordInput && addKeyword(keywordInput)}
                  className="flex-1 min-w-[120px] border-0 bg-transparent py-1 text-sm text-gray-900 dark:text-slate-100 placeholder-gray-400 dark:placeholder-slate-500 focus:outline-none focus:ring-0"
                  placeholder={keywordTags.length === 0 ? "Type and press Enter..." : "Add more..."}
                />
              </div>
              <p className="text-xs text-gray-500 dark:text-slate-400 mt-1.5">Press Enter or comma to add a keyword</p>
            </section>

            {/* Objectives */}
            <section>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-slate-300">Research Goals *</label>
                <span className="text-xs text-gray-400 dark:text-slate-500">{selectedObjectives.length} selected</span>
              </div>
              {objectivesAvailable ? (
                <div className="space-y-1.5 rounded-xl border-2 border-gray-200 dark:border-slate-600 p-3 max-h-40 overflow-y-auto">
                  {objectives.map((objective) => {
                    const checked = selectedObjectives.includes(objective)
                    return (
                      <button
                        type="button"
                        key={objective}
                        onClick={() => toggleObjectiveSelection(objective)}
                        className={`w-full flex items-center gap-3 rounded-lg px-3 py-2.5 cursor-pointer transition text-left ${
                          checked
                            ? 'bg-indigo-100 dark:bg-indigo-600/30 ring-1 ring-indigo-500 dark:ring-indigo-400'
                            : 'hover:bg-gray-50 dark:hover:bg-slate-700 ring-1 ring-transparent'
                        }`}
                      >
                        <div className={`flex-shrink-0 h-5 w-5 rounded flex items-center justify-center transition ${
                          checked
                            ? 'bg-indigo-600 dark:bg-indigo-500'
                            : 'border-2 border-gray-300 dark:border-slate-500'
                        }`}>
                          {checked && <Check className="h-3.5 w-3.5 text-white" />}
                        </div>
                        <span className={`text-sm ${checked ? 'text-indigo-900 dark:text-indigo-100 font-medium' : 'text-gray-700 dark:text-slate-300'}`}>
                          {objective}
                        </span>
                      </button>
                    )
                  })}
                </div>
              ) : (
                <div className="rounded-xl border-2 border-dashed border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700/50 p-4 text-center">
                  <p className="text-sm text-gray-500 dark:text-slate-400">
                    No goals defined yet. Add research goals in Project Settings.
                  </p>
                </div>
              )}
              {objectiveError && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{objectiveError}</p>}
              {selectedObjectives.length === 0 && !objectiveError && objectivesAvailable && (
                <p className="mt-1.5 text-xs text-amber-600 dark:text-amber-400">Select at least one goal for this paper</p>
              )}
              <p className="mt-1.5 text-xs text-gray-400 dark:text-slate-500">
                Goals help organize papers within your project
              </p>
            </section>
          </div>

          {/* Authoring Mode - Prominent Warning Style */}
          <section className="rounded-xl border-2 border-amber-200 dark:border-amber-700/50 bg-amber-50 dark:bg-amber-900/20 p-5">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-amber-900 dark:text-amber-200 mb-1">Choose Authoring Mode</h3>
                <p className="text-xs text-amber-700 dark:text-amber-300/80 mb-4">
                  This choice is permanent. Papers cannot be converted between modes after creation.
                </p>
                <div className="flex flex-wrap gap-3">
                  <label
                    className={`flex items-center gap-3 rounded-lg border-2 px-4 py-3 cursor-pointer transition ${
                      authoringMode === 'rich'
                        ? 'border-amber-500 dark:border-amber-500 bg-white dark:bg-slate-700 shadow-sm'
                        : 'border-amber-200 dark:border-amber-700/50 bg-amber-50/50 dark:bg-amber-900/10 hover:bg-white dark:hover:bg-slate-700'
                    }`}
                  >
                    <input
                      type="radio"
                      name="authoring_mode"
                      checked={authoringMode === 'rich'}
                      onChange={() => setAuthoringMode('rich')}
                      className="h-4 w-4 text-amber-600 focus:ring-amber-500 dark:bg-slate-600 dark:border-slate-500"
                    />
                    <div>
                      <p className={`text-sm font-medium ${authoringMode === 'rich' ? 'text-amber-900 dark:text-amber-200' : 'text-amber-800 dark:text-amber-300'}`}>
                        Rich Text
                      </p>
                      <p className="text-xs text-amber-600 dark:text-amber-400">Visual editor, easy formatting</p>
                    </div>
                  </label>
                  <label
                    className={`flex items-center gap-3 rounded-lg border-2 px-4 py-3 cursor-pointer transition ${
                      authoringMode === 'latex'
                        ? 'border-amber-500 dark:border-amber-500 bg-white dark:bg-slate-700 shadow-sm'
                        : 'border-amber-200 dark:border-amber-700/50 bg-amber-50/50 dark:bg-amber-900/10 hover:bg-white dark:hover:bg-slate-700'
                    }`}
                  >
                    <input
                      type="radio"
                      name="authoring_mode"
                      checked={authoringMode === 'latex'}
                      onChange={() => setAuthoringMode('latex')}
                      className="h-4 w-4 text-amber-600 focus:ring-amber-500 dark:bg-slate-600 dark:border-slate-500"
                    />
                    <div>
                      <p className={`text-sm font-medium ${authoringMode === 'latex' ? 'text-amber-900 dark:text-amber-200' : 'text-amber-800 dark:text-amber-300'}`}>
                        LaTeX
                      </p>
                      <p className="text-xs text-amber-600 dark:text-amber-400">Full control, advanced math</p>
                    </div>
                  </label>
                </div>
              </div>
            </div>
          </section>

          {/* Action Buttons */}
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100 dark:border-slate-700">
            <button
              onClick={handleBack}
              className="px-5 py-2.5 text-sm font-medium text-gray-700 dark:text-slate-300 bg-white dark:bg-slate-700 border border-gray-300 dark:border-slate-600 rounded-xl hover:bg-gray-50 dark:hover:bg-slate-600 transition"
            >
              Cancel
            </button>
            <button
              onClick={handleCreatePaper}
              disabled={isCreating || !paperTitle.trim() || duplicateTitle || selectedObjectives.length === 0}
              className="px-6 py-2.5 text-sm font-medium bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition flex items-center gap-2 shadow-sm"
            >
              {isCreating ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                  Creating...
                </>
              ) : (
                <>
                  <FileText className="h-4 w-4" />
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
