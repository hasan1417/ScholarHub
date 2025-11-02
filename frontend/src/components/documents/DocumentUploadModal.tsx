import React, { useState } from 'react'
import { ResearchPaper } from '../../types'
import DocumentUpload from './DocumentUpload'
import DuplicateWarningModal from './DuplicateWarningModal'

interface DocumentUploadModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (formData: FormData) => Promise<void>
  isLoading?: boolean
  papers: ResearchPaper[]
}

const DocumentUploadModal: React.FC<DocumentUploadModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  isLoading = false,
  papers
}) => {
  const [showDuplicateWarning, setShowDuplicateWarning] = useState(false)
  const [duplicateResults, setDuplicateResults] = useState<any>(null)
  const [pendingUpload, setPendingUpload] = useState<FormData | null>(null)

  if (!isOpen) return null



  const handleProceedWithUpload = () => {
    if (pendingUpload) {
      onSubmit(pendingUpload)
      setShowDuplicateWarning(false)
      setDuplicateResults(null)
      setPendingUpload(null)
    }
  }

  const handleCancelDuplicate = () => {
    setShowDuplicateWarning(false)
    setDuplicateResults(null)
    setPendingUpload(null)
  }

  const handleUpload = (formData: FormData) => {
    // Store the form data and proceed with upload
    // The backend will handle duplicate detection and return appropriate responses
    onSubmit(formData)
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-gray-900">Upload Document</h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
              disabled={isLoading}
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="p-6">
          <DocumentUpload
            papers={papers}
            onUpload={handleUpload}
            isLoading={isLoading}
          />
        </div>
      </div>

      {/* Duplicate Warning Modal */}
      <DuplicateWarningModal
        isOpen={showDuplicateWarning}
        onClose={handleCancelDuplicate}
        onProceed={handleProceedWithUpload}
        duplicateResults={duplicateResults}
      />
    </div>
  )
}

export default DocumentUploadModal
