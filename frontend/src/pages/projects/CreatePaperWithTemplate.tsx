import React, { useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { researchPapersAPI } from '../../services/api'
import AcademicPaperTemplate from '../../components/editor/AcademicPaperTemplate'
import { ArrowLeft, FileText, CheckCircle } from 'lucide-react'
import { useProjectContext } from './ProjectLayout'

const CreatePaperWithTemplate: React.FC = () => {
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId?: string }>()
  const { currentRole } = useProjectContext()
  const [selectedTemplate, setSelectedTemplate] = useState<any>(null)
  const [paperTitle, setPaperTitle] = useState('')
  const [paperAbstract, setPaperAbstract] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [authoringMode, setAuthoringMode] = useState<'rich' | 'latex'>('rich')
  const [createdPaper, setCreatedPaper] = useState<any>(null)

  const handleTemplateSelect = (template: any) => {
    setSelectedTemplate(template)
    setPaperTitle(template.name)
    setPaperAbstract(template.description)
  }

  const handleCreatePaper = async () => {
    if (!paperTitle.trim() || !selectedTemplate) {
      alert('Please provide a paper title and select a template')
      return
    }

    setIsCreating(true)
    try {
      const paperData: any = {
        title: paperTitle.trim(),
        abstract: paperAbstract.trim(),
        paper_type: selectedTemplate.category,
        status: 'draft',
        keywords: [],
        references: '',
        is_public: false
      }
      if (authoringMode === 'latex') {
        // Start LaTeX papers blank (no default template)
        paperData.content_json = { authoring_mode: 'latex', latex_source: '' }
      } else {
        paperData.content = selectedTemplate.structure
        paperData.content_json = { authoring_mode: 'rich' }
      }

      if (projectId) {
        paperData.project_id = projectId
      }

      const response = await researchPapersAPI.createPaper(paperData)
      const newPaper = response.data
      setCreatedPaper(newPaper)

      // Navigate to the editor after a short delay
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
      alert('Failed to create paper. Please try again.')
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
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full text-center">
          <CheckCircle size={64} className="text-green-500 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Paper Created Successfully!</h2>
          <p className="text-gray-600 mb-6">
            Your paper "{createdPaper.title}" has been created and is ready for editing.
          </p>
          <div className="animate-pulse text-blue-600">
            Redirecting to editor...
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-4">
              <button
                onClick={handleBack}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
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

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {!selectedTemplate ? (
          /* Template Selection */
          <AcademicPaperTemplate onSelectTemplate={handleTemplateSelect} />
        ) : (
          /* Paper Configuration */
          <div className="max-w-4xl mx-auto">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-gray-900">Configure Your Paper</h2>
                <button
                  onClick={() => setSelectedTemplate(null)}
                  className="text-gray-500 hover:text-gray-700 text-sm"
                >
                  Change Template
                </button>
              </div>
              
              <div className="grid grid-cols-1 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Paper Title *
                  </label>
                  <input
                    type="text"
                    value={paperTitle}
                    onChange={(e) => setPaperTitle(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="Enter your paper title..."
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Abstract
                  </label>
                  <textarea
                    value={paperAbstract}
                    onChange={(e) => setPaperAbstract(e.target.value)}
                    rows={4}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="Brief description of your paper..."
                  />
                </div>

                <div className="bg-gray-50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-gray-700 mb-2">Selected Template</h3>
                  <div className="flex items-center gap-3">
                    <div className="text-blue-600">
                      {selectedTemplate.icon}
                    </div>
                    <div>
                      <p className="font-medium text-gray-900">{selectedTemplate.name}</p>
                      <p className="text-sm text-gray-600">{selectedTemplate.description}</p>
                    </div>
                  </div>
                </div>

                <div className="bg-gray-50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-gray-700 mb-2">Authoring Mode</h3>
                  <div className="flex items-center gap-4 text-sm">
                    <label className="inline-flex items-center gap-2">
                      <input type="radio" name="authoring_mode" checked={authoringMode==='rich'} onChange={() => setAuthoringMode('rich')} />
                      Rich Text
                    </label>
                    <label className="inline-flex items-center gap-2">
                      <input type="radio" name="authoring_mode" checked={authoringMode==='latex'} onChange={() => setAuthoringMode('latex')} />
                      LaTeX
                    </label>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">Papers are locked to one mode. No auto‑conversion between modes.</p>
                </div>
              </div>
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
                disabled={isCreating || !paperTitle.trim()}
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
        )}
      </div>
    </div>
  )
}

export default CreatePaperWithTemplate
