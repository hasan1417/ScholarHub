import React, { useEffect, useMemo, useState } from 'react'
import { referencesAPI } from '../../services/api'
import ReferencePickerModal from '../references/ReferencePickerModal'
import { ResearchPaperCreate } from '../../types'
import { usePapers } from '../../contexts/PapersContext'
import { hasDuplicatePaperTitle, normalizePaperTitle } from '../../utils/papers'
import { PAPER_TEMPLATES } from '../../constants/paperTemplates'

interface CreatePaperModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (paperData: ResearchPaperCreate, selectedReferenceIds: string[]) => Promise<void>
  isLoading?: boolean
}

const CreatePaperModal: React.FC<CreatePaperModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  isLoading = false
}) => {
  const { papers } = usePapers()
  const [formData, setFormData] = useState<ResearchPaperCreate>({
    title: '',
    abstract: '',
    paper_type: 'research',
    keywords: '',
    is_public: false,
    references: ''
  })
  const [authoringMode, setAuthoringMode] = useState<'rich' | 'latex'>('rich')
  
  const [errors, setErrors] = useState<Partial<ResearchPaperCreate>>({})
  const [myRefs, setMyRefs] = useState<Array<{ id: string; title: string; authors?: string[]; year?: number }>>([])
  const [selectedRefIds, setSelectedRefIds] = useState<Set<string>>(new Set())
  const [showRefPicker, setShowRefPicker] = useState(false)
  const duplicateTitle = useMemo(() => {
    if (!formData.title) return false
    const existing = papers.map((paper) => ({
      title: paper.title,
      projectId: paper.project_id ?? null,
    }))
    return hasDuplicatePaperTitle(existing, formData.title, null)
  }, [formData.title, papers])

  const selectedTemplateDefinition = useMemo(() => {
    return PAPER_TEMPLATES.find((template) => template.id === formData.paper_type) ?? PAPER_TEMPLATES[0]
  }, [formData.paper_type])

  // Load user's references for dropdown
  useEffect(() => {
    let mounted = true
    const load = async () => {
      try {
        const res = await referencesAPI.listMy({ skip: 0, limit: 200 })
        if (!mounted) return
        const data = res.data as { references?: any[] } | any[] | null
        const items = Array.isArray(data)
          ? data
          : Array.isArray(data?.references)
            ? data.references
            : []
        setMyRefs(items.map((r: any) => ({ id: r.id, title: r.title, authors: r.authors, year: r.year })))
      } catch (e) {
        setMyRefs([])
      }
    }
    load()
    return () => { mounted = false }
  }, [])

  const validateForm = (): boolean => {
    const newErrors: Partial<ResearchPaperCreate> = {}
    
    if (!formData.title.trim()) {
      newErrors.title = 'Paper title is required'
    }
    
    if (formData.title.length > 255) {
      newErrors.title = 'Title must be less than 255 characters'
    }
    
    if (formData.abstract && formData.abstract.length > 2000) {
      newErrors.abstract = 'Abstract must be less than 2000 characters'
    }
    
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (validateForm()) {
      try {
        const payload: ResearchPaperCreate = { ...formData }
        // Normalize keywords to string[] for API
        if (typeof (payload as any).keywords === 'string') {
          const arr = ((payload as any).keywords as string)
            .split(',')
            .map(s => s.trim())
            .filter(Boolean)
          if (arr.length > 0) (payload as any).keywords = arr
          else delete (payload as any).keywords
        }
        // Seed template content based on paper type selection
        if (authoringMode === 'latex') {
          ;(payload as any).content_json = { authoring_mode: 'latex', latex_source: selectedTemplateDefinition.latexTemplate }
          payload.content = undefined
        } else {
          payload.content = selectedTemplateDefinition.richTemplate
          ;(payload as any).content_json = { authoring_mode: 'rich' }
        }
        await onSubmit(payload, Array.from(selectedRefIds))
        // Reset form on successful submission
        setFormData({
          title: '',
          abstract: '',
          paper_type: 'research',
          keywords: '',
          is_public: false,
          references: ''
        })
        setAuthoringMode('rich')
        setSelectedRefIds(new Set())
        setErrors({})
        onClose()
      } catch (error) {
        console.error('Error creating paper:', error)
        const detail = extractApiDetail(error) ?? 'Unable to create paper. Please try again.'
        setErrors((prev) => ({ ...prev, title: detail }))
      }
    }
  }

  const handleInputChange = (field: keyof ResearchPaperCreate, value: string | boolean) => {
    setFormData(prev => ({ ...prev, [field]: value }))
    // Clear error when user starts typing
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }))
    }
  }

  if (!isOpen) return null

  return (
    <>
    <div className="fixed inset-0 bg-black/50 dark:bg-black/70 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl dark:shadow-slate-900/50 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-slate-700">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-slate-100">Create New Research Paper</h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
              disabled={isLoading}
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-6">
          {/* Paper Title */}
          <div>
            <label htmlFor="title" className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">
              Paper Title *
            </label>
            <input
              type="text"
              id="title"
              value={formData.title}
              onChange={(e) => handleInputChange('title', e.target.value)}
              className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-slate-700 dark:text-slate-100 ${
                errors.title || duplicateTitle ? 'border-red-500' : 'border-gray-300 dark:border-slate-600'
              }`}
              placeholder="Enter paper title"
              maxLength={255}
            />
            {errors.title && (
              <p className="text-red-500 dark:text-red-400 text-sm mt-1">{errors.title}</p>
            )}
            {!errors.title && duplicateTitle && (
              <p className="text-red-500 dark:text-red-400 text-sm mt-1">
                A paper with this title already exists in this workspace.
              </p>
            )}
            <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
              {formData.title.length}/255 characters
            </p>
          </div>

          {/* Paper Type */}
          <div>
            <p className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">Paper Type & Template *</p>
            <div className="grid gap-3 md:grid-cols-3">
              {PAPER_TEMPLATES.map((template) => {
                const isSelected = template.id === selectedTemplateDefinition.id
                return (
                  <button
                    type="button"
                    key={template.id}
                    onClick={() => handleInputChange('paper_type', template.id)}
                    className={`rounded-xl border px-4 py-3 text-left transition ${
                      isSelected
                        ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-900 dark:text-indigo-100'
                        : 'border-gray-200 dark:border-slate-600 hover:border-indigo-200 dark:hover:border-indigo-500 dark:text-slate-200'
                    }`}
                  >
                    <p className="text-sm font-semibold">{template.label}</p>
                    <p className="mt-1 text-xs text-gray-600 dark:text-slate-400">{template.description}</p>
                  </button>
                )
              })}
            </div>
            <div className="mt-3 rounded-lg border border-dashed border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700/50 p-3">
              <p className="text-xs font-semibold uppercase text-gray-500 dark:text-slate-400">Template sections</p>
              <ul className="mt-1 list-disc pl-5 text-xs text-gray-700 dark:text-slate-300">
                {selectedTemplateDefinition.sections.map((section) => (
                  <li key={section}>{section}</li>
                ))}
              </ul>
            </div>
          </div>

          {/* Abstract */}
          <div>
            <label htmlFor="abstract" className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">
              Abstract
            </label>
            <textarea
              id="abstract"
              value={formData.abstract}
              onChange={(e) => handleInputChange('abstract', e.target.value)}
              rows={4}
              className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-slate-700 dark:text-slate-100 ${
                errors.abstract ? 'border-red-500' : 'border-gray-300 dark:border-slate-600'
              }`}
              placeholder="Enter paper abstract (optional)"
              maxLength={2000}
            />
            {errors.abstract && (
              <p className="text-red-500 dark:text-red-400 text-sm mt-1">{errors.abstract}</p>
            )}
            <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
              {formData.abstract?.length || 0}/2000 characters
            </p>
          </div>

          {/* Authoring Mode */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">
              Authoring Mode (required)
            </label>
            <div className="flex items-center gap-4">
              <label className="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-slate-300">
                <input type="radio" name="authoring_mode" checked={authoringMode==='rich'} onChange={() => setAuthoringMode('rich')} className="text-blue-600" />
                Rich Text
              </label>
              <label className="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-slate-300">
                <input type="radio" name="authoring_mode" checked={authoringMode==='latex'} onChange={() => setAuthoringMode('latex')} className="text-blue-600" />
                LaTeX
              </label>
            </div>
            <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">Papers are locked to one mode. No auto‑conversion between modes.</p>
          </div>

          {/* References selection via picker */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Reference</label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setShowRefPicker(true)}
                className="px-3 py-2 text-sm rounded-md border border-gray-300 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 dark:text-slate-200"
              >
                Choose from My References
              </button>
              <span className="text-xs text-gray-500 dark:text-slate-400">Selected: {selectedRefIds.size}</span>
            </div>
            {selectedRefIds.size > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {Array.from(selectedRefIds).slice(0, 6).map(id => {
                  const r = myRefs.find(m => m.id === id)
                  return (
                    <span key={id} className="px-2 py-1 text-xs bg-gray-100 dark:bg-slate-600 dark:text-slate-200 rounded">
                      {r?.title || id}
                    </span>
                  )
                })}
                {selectedRefIds.size > 6 && (
                  <span className="text-xs text-gray-500 dark:text-slate-400">+{selectedRefIds.size - 6} more</span>
                )}
              </div>
            )}
          </div>

          {/* Keywords */}
          <div>
            <label htmlFor="keywords" className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">
              Keywords
            </label>
            <input
              type="text"
              id="keywords"
              value={formData.keywords}
              onChange={(e) => handleInputChange('keywords', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-slate-700 dark:text-slate-100"
              placeholder="Enter keywords separated by commas"
            />
            <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
              Separate multiple keywords with commas
            </p>
          </div>

          {/* Removed free-text References box */}

          {/* Public/Private Toggle */}
          <div className="flex items-center">
            <input
              type="checkbox"
              id="is_public"
              checked={formData.is_public}
              onChange={(e) => handleInputChange('is_public', e.target.checked)}
              className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-slate-600 rounded"
            />
            <label htmlFor="is_public" className="ml-2 block text-sm text-gray-700 dark:text-slate-300">
              Make this paper public (visible to other users)
            </label>
          </div>

          {/* Action Buttons */}
          <div className="flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-slate-700">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-slate-200 bg-white dark:bg-slate-700 border border-gray-300 dark:border-slate-600 rounded-md hover:bg-gray-50 dark:hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              disabled={isLoading}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || duplicateTitle || !normalizePaperTitle(formData.title)}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {isLoading ? 'Creating...' : 'Create Paper'}
            </button>
          </div>
        </form>
      </div>
    </div>
    <ReferencePickerModal
      isOpen={showRefPicker}
      onClose={() => setShowRefPicker(false)}
      selectedIds={Array.from(selectedRefIds)}
      onConfirm={(ids) => setSelectedRefIds(new Set(ids))}
    />
    </>
  )
}

export default CreatePaperModal

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
