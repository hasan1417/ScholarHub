import React, { useState, useEffect } from 'react'
import { aiAPI } from '../../services/api'
import { Document } from '../../types'

interface DocumentProcessingModalProps {
  isOpen: boolean
  onClose: () => void
  document: Document | null
  onProcessingComplete?: () => void
}

interface ProcessingStatus {
  status: 'idle' | 'processing' | 'completed' | 'error'
  message: string
  progress?: number
}

const DocumentProcessingModal: React.FC<DocumentProcessingModalProps> = ({
  isOpen,
  onClose,
  document,
  onProcessingComplete
}) => {
  const [processingStatus, setProcessingStatus] = useState<ProcessingStatus>({
    status: 'idle',
    message: ''
  })
  const [isProcessing, setIsProcessing] = useState(false)

  useEffect(() => {
    if (isOpen && document) {
      // Check if document is already processed
      if (document.is_processed_for_ai) {
        setProcessingStatus({
          status: 'completed',
          message: 'This document has already been processed for AI analysis.'
        })
      } else {
        setProcessingStatus({
          status: 'idle',
          message: 'Ready to process document for AI analysis.'
        })
      }
    }
  }, [isOpen, document])

  const handleProcessDocument = async () => {
    if (!document || isProcessing) return

    setIsProcessing(true)
    setProcessingStatus({
      status: 'processing',
      message: 'Processing document for AI analysis...',
      progress: 0
    })

    try {
      // Simulate progress updates
      const progressInterval = setInterval(() => {
        setProcessingStatus(prev => ({
          ...prev,
          progress: Math.min((prev.progress || 0) + 10, 90)
        }))
      }, 500)

      const response = await aiAPI.processDocumentForAI(document.id)
      
      clearInterval(progressInterval)
      
      if (response.data.success) {
        setProcessingStatus({
          status: 'completed',
          message: 'Document successfully processed for AI analysis!',
          progress: 100
        })
        
        // Call callback to refresh document list
        if (onProcessingComplete) {
          setTimeout(() => {
            onProcessingComplete()
            onClose()
          }, 2000)
        }
      } else {
        throw new Error(response.data.message || 'Processing failed')
      }
    } catch (error: any) {
      console.error('Error processing document:', error)
      setProcessingStatus({
        status: 'error',
        message: error.response?.data?.detail || error.message || 'An error occurred during processing.'
      })
    } finally {
      setIsProcessing(false)
    }
  }

  const getStatusIcon = () => {
    switch (processingStatus.status) {
      case 'completed':
        return (
          <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
            <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
        )
      case 'error':
        return (
          <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
            <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
        )
      case 'processing':
        return (
          <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
            <svg className="w-6 h-6 text-blue-600 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </div>
        )
      default:
        return (
          <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center">
            <svg className="w-6 h-6 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
        )
    }
  }

  const getStatusColor = () => {
    switch (processingStatus.status) {
      case 'completed':
        return 'text-green-600'
      case 'error':
        return 'text-red-600'
      case 'processing':
        return 'text-blue-600'
      default:
        return 'text-gray-600'
    }
  }

  if (!isOpen || !document) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Process Document for AI</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            disabled={isProcessing}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-4">
          {/* Document Info */}
          <div className="mb-4 p-3 bg-gray-50 rounded-lg">
            <h3 className="font-medium text-gray-900 mb-1">{document.title || document.original_filename}</h3>
            <div className="text-sm text-gray-500 space-y-1">
              <div>Type: {document.document_type}</div>
              <div>Size: {(document.file_size || 0) / 1024} KB</div>
              {document.is_processed_for_ai && (
                <div className="text-green-600 font-medium">✓ Already processed for AI</div>
              )}
            </div>
          </div>

          {/* Processing Status */}
          <div className="mb-4">
            <div className="flex items-center space-x-3 mb-3">
              {getStatusIcon()}
              <div className="flex-1">
                <div className={`font-medium ${getStatusColor()}`}>
                  {processingStatus.status === 'completed' && 'Processing Complete'}
                  {processingStatus.status === 'error' && 'Processing Failed'}
                  {processingStatus.status === 'processing' && 'Processing...'}
                  {processingStatus.status === 'idle' && 'Ready to Process'}
                </div>
                <div className="text-sm text-gray-600">{processingStatus.message}</div>
              </div>
            </div>

            {/* Progress Bar */}
            {processingStatus.progress !== undefined && (
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${processingStatus.progress}%` }}
                ></div>
              </div>
            )}
          </div>

          {/* What happens during processing */}
          <div className="mb-4 p-3 bg-blue-50 rounded-lg">
            <h4 className="font-medium text-blue-900 mb-2">What happens during processing?</h4>
            <ul className="text-sm text-blue-800 space-y-1">
              <li>• Extract text content from your document</li>
              <li>• Split text into intelligent chunks</li>
              <li>• Generate AI embeddings for semantic search</li>
              <li>• Enable "Chat with Your References" feature</li>
            </ul>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end space-x-3 p-4 border-t border-gray-200">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
            disabled={isProcessing}
          >
            Cancel
          </button>
          
          {!document.is_processed_for_ai && (
            <button
              onClick={handleProcessDocument}
              disabled={isProcessing}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {isProcessing ? 'Processing...' : 'Process Document'}
            </button>
          )}
          
          {document.is_processed_for_ai && (
            <button
              onClick={onClose}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
            >
              Done
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default DocumentProcessingModal
