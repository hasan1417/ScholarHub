import React from 'react'



interface DuplicateWarningModalProps {
  isOpen: boolean
  onClose: () => void
  onProceed: () => void
  duplicateResults: {
    message: string
    duplicate_document: {
      id: string
      title: string
      uploaded_at: string
    }
    duplicate_check_results: {
      recommendation: string
      exact_duplicate?: any
      filename_similarities: any[]
      content_similarities: any[]
    }
  }
}

const DuplicateWarningModal: React.FC<DuplicateWarningModalProps> = ({
  isOpen,
  onClose,
  onProceed,
  duplicateResults
}) => {
  if (!isOpen) return null

  // Determine warning level based on backend response
  const getWarningLevel = () => {
    const recommendation = duplicateResults.duplicate_check_results?.recommendation
    if (recommendation === 'exact_duplicate_found') return 'high'
    if (recommendation === 'high_filename_similarity' || recommendation === 'high_content_similarity') return 'high'
    if (recommendation === 'moderate_similarity') return 'medium'
    return 'low'
  }

  const warningLevel = getWarningLevel()

  const getWarningColor = (level: string) => {
    switch (level) {
      case 'high': return 'text-red-600 bg-red-50 border-red-200'
      case 'medium': return 'text-yellow-600 bg-yellow-50 border-yellow-200'
      case 'low': return 'text-blue-600 bg-blue-50 border-blue-200'
      default: return 'text-gray-600 bg-gray-50 border-gray-200'
    }
  }

  const getWarningIcon = (level: string) => {
    switch (level) {
      case 'high': return (
        <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
        </svg>
      )
      case 'medium': return (
        <svg className="w-6 h-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
        </svg>
      )
      case 'low': return (
        <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      )
      default: return (
        <svg className="w-6 h-6 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      )
    }
  }



  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              {getWarningIcon(warningLevel)}
              <h2 className="text-xl font-semibold text-gray-900">Duplicate Document Warning</h2>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="p-6">
          {/* Warning Message */}
          <div className={`mb-6 p-4 rounded-lg border ${getWarningColor(warningLevel)}`}>
            <div className="flex items-start space-x-3">
              {getWarningIcon(warningLevel)}
              <div>
                <h3 className="font-medium mb-2">
                  {warningLevel === 'high' ? 'High Risk of Duplicate' :
                   warningLevel === 'medium' ? 'Potential Duplicate Detected' :
                   'Similarity Detected'}
                </h3>
                <p className="text-sm">{duplicateResults.message}</p>
              </div>
            </div>
          </div>



          {/* Recommendations */}
          <div className="bg-gray-50 rounded-lg p-4 mb-6">
            <h3 className="font-medium text-gray-900 mb-2">Recommendations</h3>
            <ul className="text-sm text-gray-600 space-y-1">
              {warningLevel === 'high' && (
                <>
                  <li>• This appears to be an exact duplicate. Consider not uploading.</li>
                  <li>• If you need a different version, rename the file clearly.</li>
                </>
              )}
              {warningLevel === 'medium' && (
                <>
                  <li>• Review the similar documents before proceeding.</li>
                  <li>• Ensure this is a different version or document.</li>
                  <li>• Consider adding a version number or date to the filename.</li>
                </>
              )}
              {warningLevel === 'low' && (
                <>
                  <li>• Some similarity detected, but likely safe to proceed.</li>
                  <li>• Review if this adds value to your collection.</li>
                </>
              )}
            </ul>
          </div>

          {/* Action Buttons */}
          <div className="flex justify-end space-x-3">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 transition-colors"
            >
              Cancel Upload
            </button>
            <button
              onClick={onProceed}
              className={`px-4 py-2 rounded-md transition-colors ${
                warningLevel === 'high' 
                  ? 'bg-red-600 text-white hover:bg-red-700' 
                  : warningLevel === 'medium'
                  ? 'bg-yellow-600 text-white hover:bg-yellow-700'
                  : 'bg-blue-600 text-white hover:bg-blue-700'
              }`}
            >
              {warningLevel === 'high' ? 'Upload Anyway (Not Recommended)' :
               warningLevel === 'medium' ? 'Upload with Caution' :
               'Proceed with Upload'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default DuplicateWarningModal
