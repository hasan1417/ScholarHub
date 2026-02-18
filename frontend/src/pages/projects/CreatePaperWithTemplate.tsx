import React, { useEffect, useMemo, useState, useCallback, KeyboardEvent } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { researchPapersAPI } from '../../services/api'
import {
  ArrowLeft, ArrowRight, Check, CheckCircle,
  ChevronDown, ChevronUp, FileText, X, Target, Eye, Pencil
} from 'lucide-react'
import { useProjectContext } from './ProjectLayout'
import { hasDuplicatePaperTitle } from '../../utils/papers'
import { parseObjectives } from '../../utils/objectives'
import { PAPER_TEMPLATES, VENUE_FORMATS, VenueFormat, PaperTemplateDefinition } from '../../constants/paperTemplates'
import { getProjectUrlId, getPaperUrlId } from '../../utils/urlId'

type Step = 'title' | 'customize' | 'review'

const STEPS: { id: Step; label: string; description: string }[] = [
  { id: 'title', label: 'Title & Type', description: 'Name your paper and choose a template' },
  { id: 'customize', label: 'Customize Template', description: 'Adjust sections and venue format' },
  { id: 'review', label: 'Review & Create', description: 'Confirm settings and create' },
]

function assembleLatex(venue: VenueFormat, sections: string[], templateDef: PaperTemplateDefinition, title: string = 'Untitled Paper', author: string = 'Author Name'): string {
  const cmd = templateDef.id === 'thesis' ? '\\chapter' : '\\section'
  const sectionContent = sections
    .map((s) => `${cmd}{${s}}\n% TODO: Add content here.\n`)
    .join('\n')

  const preamble = venue.preamble
    .replace(/%TITLE%/g, title || 'Untitled Paper')
    .replace(/%AUTHOR%/g, author || 'Author Name')

  return `${preamble}\n\n${sectionContent}\n\\end{document}\n`
}

const CreatePaperWithTemplate: React.FC = () => {
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId?: string }>()
  const { project, currentRole } = useProjectContext()

  // Current step
  const [currentStep, setCurrentStep] = useState<Step>('title')

  // Form state
  const [selectedTypeId, setSelectedTypeId] = useState<string>(PAPER_TEMPLATES[0].id)
  const [paperTitle, setPaperTitle] = useState('')
  const [keywordTags, setKeywordTags] = useState<string[]>([])
  const [keywordInput, setKeywordInput] = useState('')
  const [objectives, setObjectives] = useState<string[]>(() => parseObjectives(project.scope))
  const [selectedObjectives, setSelectedObjectives] = useState<string[]>(() => {
    const parsed = parseObjectives(project.scope)
    return parsed.length ? [parsed[0]] : []
  })
  const [showSections, setShowSections] = useState(false)

  // Customize step state
  const [selectedVenueId, setSelectedVenueId] = useState('generic')
  const [enabledSections, setEnabledSections] = useState<string[]>([])
  const [customLatex, setCustomLatex] = useState('')
  const [showRawEditor, setShowRawEditor] = useState(false)
  const [hasManualEdits, setHasManualEdits] = useState(false)

  // UI state
  const [isCreating, setIsCreating] = useState(false)
  const [createdPaper, setCreatedPaper] = useState<any>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

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
    queryKey: ['project-papers', project.id],
    queryFn: async () => {
      if (!project.id) return []
      const response = await researchPapersAPI.getPapers({ projectId: project.id, limit: 500 })
      return response.data.papers ?? []
    },
    enabled: Boolean(project.id),
  })

  const duplicateTitle = useMemo(() => {
    if (!project.id) return false
    if (!paperTitle) return false
    const existing = (existingProjectPapers ?? []).map((paper) => ({
      title: paper.title,
      projectId: paper.project_id ?? null,
    }))
    return hasDuplicatePaperTitle(existing, paperTitle, project.id)
  }, [existingProjectPapers, paperTitle, project.id])

  const selectedTemplateDefinition = useMemo(() => {
    return PAPER_TEMPLATES.find((template) => template.id === selectedTypeId) ?? PAPER_TEMPLATES[0]
  }, [selectedTypeId])

  const selectedVenue = useMemo(() => {
    return VENUE_FORMATS.find((v) => v.id === selectedVenueId) ?? VENUE_FORMATS[0]
  }, [selectedVenueId])

  // Reset enabled sections when template changes
  useEffect(() => {
    setEnabledSections([...selectedTemplateDefinition.sections])
    setHasManualEdits(false)
    setShowRawEditor(false)
  }, [selectedTemplateDefinition])

  // Reassemble LaTeX when venue or sections change (unless user made manual edits)
  useEffect(() => {
    if (!hasManualEdits) {
      setCustomLatex(assembleLatex(selectedVenue, enabledSections, selectedTemplateDefinition, paperTitle.trim()))
    }
  }, [selectedVenue, enabledSections, selectedTemplateDefinition, hasManualEdits, paperTitle])

  // Step navigation
  const currentStepIndex = STEPS.findIndex((s) => s.id === currentStep)

  const canProceedFromTitle = paperTitle.trim().length > 0 && !duplicateTitle

  const goToNextStep = () => {
    setErrorMessage(null)
    if (currentStep === 'title') {
      if (!canProceedFromTitle) {
        setErrorMessage(duplicateTitle ? 'A paper with this title already exists.' : 'Please enter a paper title.')
        return
      }
      setCurrentStep('customize')
    } else if (currentStep === 'customize') {
      setCurrentStep('review')
    }
  }

  const goToPrevStep = () => {
    setErrorMessage(null)
    if (currentStep === 'customize') setCurrentStep('title')
    else if (currentStep === 'review') setCurrentStep('customize')
  }

  const toggleSection = (section: string) => {
    setEnabledSections((prev) => {
      if (prev.includes(section)) {
        return prev.filter((s) => s !== section)
      }
      return [...prev, section]
    })
    setHasManualEdits(false) // Toggling sections should regenerate LaTeX
  }

  const handleVenueChange = (venueId: string) => {
    setSelectedVenueId(venueId)
    setHasManualEdits(false) // Changing venue should regenerate LaTeX
  }

  const handleRawLatexChange = (value: string) => {
    setCustomLatex(value)
    setHasManualEdits(true)
  }

  const handleCreatePaper = async () => {
    setIsCreating(true)
    setErrorMessage(null)
    try {
      const templateDefinition = selectedTemplateDefinition
      const finalLatexSource = customLatex || assembleLatex(selectedVenue, enabledSections, templateDefinition, paperTitle.trim())

      const paperData: any = {
        title: paperTitle.trim(),
        paper_type: templateDefinition.id,
        status: 'draft',
        keywords: keywordTags,
        references: '',
        is_public: false,
        objectives: selectedObjectives,
      }

      paperData.content_json = { authoring_mode: 'latex', latex_source: finalLatexSource }

      if (project.id) {
        paperData.project_id = project.id
      }

      const response = await researchPapersAPI.createPaper(paperData)
      const newPaper = response.data
      setCreatedPaper(newPaper)

      setTimeout(() => {
        const targetProjectUrlId = getProjectUrlId(project) || projectId || newPaper.project_id
        if (targetProjectUrlId) {
          navigate(`/projects/${targetProjectUrlId}/papers/${getPaperUrlId(newPaper)}/editor`)
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
    navigate(projectId ? `/projects/${projectId}/papers` : '/projects')
  }

  if (currentRole === 'viewer') {
    return <Navigate to={projectId ? `/projects/${projectId}/papers` : '/projects'} replace />
  }

  // Success screen
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
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-8">
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
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
            <div>
              <h1 className="text-xl font-semibold text-gray-900 dark:text-slate-100">Create New Paper</h1>
              <p className="text-xs text-gray-500 dark:text-slate-400">{project.title}</p>
            </div>
          </div>
        </div>

        {/* Progress Steps */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            {STEPS.map((step, index) => {
              const isActive = step.id === currentStep
              const isCompleted = index < currentStepIndex
              const isLast = index === STEPS.length - 1

              return (
                <React.Fragment key={step.id}>
                  <div className="flex flex-col items-center">
                    <div
                      className={`flex h-10 w-10 items-center justify-center rounded-full border-2 transition-all ${
                        isCompleted
                          ? 'border-indigo-500 bg-indigo-500 text-white'
                          : isActive
                          ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400'
                          : 'border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-400 dark:text-slate-500'
                      }`}
                    >
                      {isCompleted ? <Check className="h-5 w-5" /> : <span className="text-sm font-semibold">{index + 1}</span>}
                    </div>
                    <span
                      className={`mt-2 text-xs font-medium ${
                        isActive ? 'text-indigo-600 dark:text-indigo-400' : isCompleted ? 'text-gray-700 dark:text-slate-300' : 'text-gray-400 dark:text-slate-500'
                      }`}
                    >
                      {step.label}
                    </span>
                  </div>
                  {!isLast && (
                    <div
                      className={`flex-1 h-0.5 mx-3 mt-[-20px] ${
                        index < currentStepIndex ? 'bg-indigo-500' : 'bg-gray-200 dark:bg-slate-700'
                      }`}
                    />
                  )}
                </React.Fragment>
              )
            })}
          </div>
        </div>

        {/* Step Content */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-200 dark:border-slate-700 overflow-hidden">
          {/* Step Header */}
          <div className="px-6 py-4 border-b border-gray-100 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/50">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">
              {STEPS[currentStepIndex].label}
            </h2>
            <p className="text-sm text-gray-500 dark:text-slate-400">{STEPS[currentStepIndex].description}</p>
          </div>

          {/* Step Body */}
          <div className="p-6">
            {/* Step 1: Title & Type */}
            {currentStep === 'title' && (
              <div className="space-y-6">
                {/* Paper Title */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                    Paper Title <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={paperTitle}
                    onChange={(e) => {
                      setPaperTitle(e.target.value)
                      if (errorMessage) setErrorMessage(null)
                    }}
                    className={`w-full px-4 py-3 border-2 rounded-xl bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 placeholder-gray-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition text-lg ${
                      duplicateTitle ? 'border-red-400 dark:border-red-500' : 'border-gray-200 dark:border-slate-600'
                    }`}
                    placeholder="Enter a descriptive title for your paper..."
                    autoFocus
                  />
                  {duplicateTitle && (
                    <p className="mt-2 text-sm text-red-600 dark:text-red-400">A paper with this title already exists in this project.</p>
                  )}
                </div>

                {/* Paper Type Selection */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-3">
                    Paper Template <span className="text-red-500">*</span>
                  </label>
                  <div className="grid gap-3 grid-cols-2">
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
                    <span>Preview template sections ({selectedTemplateDefinition.sections.length})</span>
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
                </div>

                {/* Keywords (optional) */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                    Keywords <span className="text-gray-400 dark:text-slate-500 font-normal">(optional)</span>
                  </label>
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
                  <p className="text-xs text-gray-500 dark:text-slate-400 mt-1.5">Press Enter or comma to add</p>
                </div>
              </div>
            )}

            {/* Step 2: Customize Template */}
            {currentStep === 'customize' && (
              <div className="space-y-6">
                {/* Venue / Format */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-3">
                    Venue / Format
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {VENUE_FORMATS.map((venue) => {
                      const isSelected = venue.id === selectedVenueId
                      return (
                        <button
                          key={venue.id}
                          type="button"
                          onClick={() => handleVenueChange(venue.id)}
                          className={`px-4 py-2 rounded-full text-sm font-medium transition-all border ${
                            isSelected
                              ? 'border-indigo-500 bg-indigo-500 text-white shadow-sm'
                              : 'border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-gray-700 dark:text-slate-300 hover:border-indigo-300 dark:hover:border-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-900/20'
                          }`}
                          title={venue.description}
                        >
                          {venue.label}
                        </button>
                      )
                    })}
                  </div>
                  <p className="text-xs text-gray-500 dark:text-slate-400 mt-2">
                    {selectedVenue.description}
                  </p>
                </div>

                {/* Section Toggles */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-3">
                    Sections
                  </label>
                  <div className="space-y-2">
                    {selectedTemplateDefinition.sections.map((section) => {
                      const isEnabled = enabledSections.includes(section)
                      return (
                        <label
                          key={section}
                          className={`flex items-center gap-3 px-4 py-2.5 rounded-lg border cursor-pointer transition-all ${
                            isEnabled
                              ? 'border-indigo-200 dark:border-indigo-700 bg-indigo-50/50 dark:bg-indigo-900/10'
                              : 'border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700/30 opacity-60'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={isEnabled}
                            onChange={() => toggleSection(section)}
                            className="h-4 w-4 rounded border-gray-300 dark:border-slate-500 text-indigo-600 focus:ring-indigo-500"
                          />
                          <span className={`text-sm font-medium ${
                            isEnabled ? 'text-gray-900 dark:text-slate-100' : 'text-gray-500 dark:text-slate-400'
                          }`}>
                            {section}
                          </span>
                        </label>
                      )
                    })}
                  </div>
                </div>

                {/* LaTeX Preview */}
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <label className="block text-sm font-medium text-gray-700 dark:text-slate-300">
                      LaTeX Preview
                    </label>
                    <button
                      type="button"
                      onClick={() => setShowRawEditor(!showRawEditor)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all border ${
                        showRawEditor
                          ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300'
                          : 'border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-gray-600 dark:text-slate-300 hover:border-indigo-300 dark:hover:border-indigo-500'
                      }`}
                    >
                      {showRawEditor ? <Eye className="h-3.5 w-3.5" /> : <Pencil className="h-3.5 w-3.5" />}
                      {showRawEditor ? 'Preview Mode' : 'Edit Raw LaTeX'}
                    </button>
                  </div>

                  {showRawEditor ? (
                    <textarea
                      value={customLatex}
                      onChange={(e) => handleRawLatexChange(e.target.value)}
                      className="w-full h-80 px-4 py-3 rounded-xl border-2 border-gray-200 dark:border-slate-600 bg-gray-900 text-green-400 font-mono text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 resize-y"
                      spellCheck={false}
                    />
                  ) : (
                    <div className="rounded-xl border border-gray-200 dark:border-slate-600 bg-gray-900 p-4 overflow-auto max-h-80">
                      <pre className="text-sm text-green-400 font-mono whitespace-pre-wrap leading-relaxed">
                        {customLatex}
                      </pre>
                    </div>
                  )}

                  {hasManualEdits && (
                    <div className="mt-2 flex items-center justify-between">
                      <p className="text-xs text-amber-600 dark:text-amber-400">
                        You have manual edits. Changing venue or sections will overwrite them.
                      </p>
                      <button
                        type="button"
                        onClick={() => {
                          setHasManualEdits(false)
                          setCustomLatex(assembleLatex(selectedVenue, enabledSections, selectedTemplateDefinition, paperTitle.trim()))
                        }}
                        className="text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline"
                      >
                        Reset to auto-generated
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Step 3: Review */}
            {currentStep === 'review' && (
              <div className="space-y-5">
                {/* Summary Cards */}
                <div className="grid gap-3 md:grid-cols-3">
                  <div className="rounded-xl border border-gray-200 dark:border-slate-700 p-4 bg-gray-50 dark:bg-slate-800/50">
                    <p className="text-xs font-medium text-gray-500 dark:text-slate-400 uppercase tracking-wide">Title</p>
                    <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-slate-100 truncate">{paperTitle}</p>
                  </div>
                  <div className="rounded-xl border border-gray-200 dark:border-slate-700 p-4 bg-gray-50 dark:bg-slate-800/50">
                    <p className="text-xs font-medium text-gray-500 dark:text-slate-400 uppercase tracking-wide">Template</p>
                    <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-slate-100">{selectedTemplateDefinition.label}</p>
                  </div>
                  <div className="rounded-xl border border-gray-200 dark:border-slate-700 p-4 bg-gray-50 dark:bg-slate-800/50">
                    <p className="text-xs font-medium text-gray-500 dark:text-slate-400 uppercase tracking-wide">Format</p>
                    <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-slate-100">
                      LaTeX ({selectedVenue.label})
                    </p>
                  </div>
                </div>

                {/* Enabled Sections */}
                {enabledSections.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium text-gray-500 dark:text-slate-400">Sections:</span>
                    {enabledSections.map((section) => (
                      <span
                        key={section}
                        className="inline-flex items-center rounded-full bg-gray-100 dark:bg-slate-700 px-2.5 py-1 text-xs font-medium text-gray-700 dark:text-slate-300 border border-gray-200 dark:border-slate-600"
                      >
                        {section}
                      </span>
                    ))}
                  </div>
                )}

                {/* Keywords */}
                {keywordTags.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium text-gray-500 dark:text-slate-400">Keywords:</span>
                    {keywordTags.map((tag) => (
                      <span
                        key={tag}
                        className="inline-flex items-center rounded-full bg-indigo-100 dark:bg-indigo-900/40 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:text-indigo-300"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                {/* Optional: Link to Project Goals */}
                {objectivesAvailable && (
                  <div className="rounded-xl border border-gray-200 dark:border-slate-700 p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <Target className="h-4 w-4 text-gray-400 dark:text-slate-500" />
                        <span className="text-sm font-medium text-gray-700 dark:text-slate-300">
                          Link to project goals
                        </span>
                        <span className="text-xs text-gray-400 dark:text-slate-500">(optional)</span>
                      </div>
                      {selectedObjectives.length > 0 && (
                        <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">
                          {selectedObjectives.length} selected
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {objectives.map((objective) => {
                        const checked = selectedObjectives.includes(objective)
                        return (
                          <button
                            type="button"
                            key={objective}
                            onClick={() => toggleObjectiveSelection(objective)}
                            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition border ${
                              checked
                                ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300'
                                : 'border-gray-200 dark:border-slate-600 text-gray-600 dark:text-slate-400 hover:border-indigo-300 dark:hover:border-indigo-500'
                            }`}
                          >
                            {checked && <Check className="h-3 w-3" />}
                            <span className="max-w-[200px] truncate">{objective}</span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}

                {errorMessage && (
                  <div className="rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-600 dark:text-red-400">
                    {errorMessage}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Error message for non-review steps */}
          {errorMessage && currentStep !== 'review' && (
            <div className="px-6 pb-4">
              <div className="rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-600 dark:text-red-400">
                {errorMessage}
              </div>
            </div>
          )}

          {/* Navigation */}
          <div className="px-6 py-4 border-t border-gray-100 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/50 flex items-center justify-between">
            <button
              onClick={currentStep === 'title' ? handleBack : goToPrevStep}
              className="px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-slate-300 bg-white dark:bg-slate-700 border border-gray-300 dark:border-slate-600 rounded-xl hover:bg-gray-50 dark:hover:bg-slate-600 transition flex items-center gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              {currentStep === 'title' ? 'Cancel' : 'Back'}
            </button>

            {currentStep !== 'review' ? (
              <button
                onClick={goToNextStep}
                className="px-5 py-2.5 text-sm font-medium bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 transition flex items-center gap-2 shadow-sm"
              >
                Continue
                <ArrowRight className="h-4 w-4" />
              </button>
            ) : (
              <button
                onClick={handleCreatePaper}
                disabled={isCreating}
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
            )}
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
