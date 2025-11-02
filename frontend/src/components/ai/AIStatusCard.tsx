import React, { useState, useEffect } from 'react'
import { aiAPI } from '../../services/api'
import ModelSelectionModal from './ModelSelectionModal'

interface AIStatusCardProps {
  className?: string
}

interface AIStatus {
  status: string
  progress: number
  message: string
  ai_service_ready?: boolean
  embedding_model?: string | null
  model_loaded?: boolean
}

const AIStatusCard: React.FC<AIStatusCardProps> = ({ className = '' }) => {
  const [aiStatus, setAiStatus] = useState<AIStatus | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [lastChecked, setLastChecked] = useState<Date | null>(null)
  const [isModelModalOpen, setIsModelModalOpen] = useState(false)

  useEffect(() => {
    loadAIStatus()
    
    // Refresh status every 30 seconds
    const interval = setInterval(loadAIStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  const loadAIStatus = async () => {
    try {
      const response = await aiAPI.getAIStatus()
      setAiStatus(response.data)
      setLastChecked(new Date())
    } catch (error) {
      console.error('Error loading AI status:', error)
      setAiStatus({
        status: 'error',
        progress: 0,
        message: 'Error loading AI status'
      })
    } finally {
      setIsLoading(false)
    }
  }

  const getStatusColor = () => {
    if (isLoading) return 'bg-gray-100 text-gray-600'
    if (aiStatus?.status === 'ready') return 'bg-green-100 text-green-800'
    if (aiStatus?.status === 'error') return 'bg-red-100 text-red-800'
    return 'bg-yellow-100 text-yellow-800'
  }

  const getStatusIcon = () => {
    if (isLoading) {
      return (
        <svg className="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      )
    }
    
    if (aiStatus?.status === 'ready') {
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      )
    }
    
    if (aiStatus?.status === 'error') {
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      )
    }
    
    return (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    )
  }

  const getStatusText = () => {
    if (isLoading) return 'Checking status...'
    if (aiStatus?.status === 'ready') return 'OpenAI API Ready'
    if (aiStatus?.status === 'error') return 'OpenAI API Error'
    if (aiStatus?.status === 'initializing') return 'OpenAI API Initializing'
    return 'OpenAI API Unknown'
  }

  const getStatusDescription = () => {
    if (isLoading) return 'Verifying OpenAI API status...'
    if (aiStatus?.status === 'ready') return 'Ready to process documents and answer questions using OpenAI'
    if (aiStatus?.status === 'error') return 'There was an error with the OpenAI API'
    if (aiStatus?.status === 'initializing') return 'OpenAI API is initializing, please wait...'
    return 'Unable to determine OpenAI API status'
  }

  return (
    <div className={`bg-white rounded-lg shadow-sm border border-gray-200 p-4 ${className}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-900">AI Service Status</h3>
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setIsModelModalOpen(true)}
            className="text-blue-600 hover:text-blue-700 text-sm font-medium px-3 py-1 rounded-md border border-blue-200 hover:border-blue-300 transition-colors"
            title="Configure AI models"
          >
            Configure Models
          </button>
          <button
            onClick={loadAIStatus}
            disabled={isLoading}
            className="text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
            title="Refresh status"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      <div className="flex items-center space-x-3 mb-3">
        <div className={`w-10 h-10 rounded-full flex items-center justify-center ${getStatusColor()}`}>
          {getStatusIcon()}
        </div>
        <div className="flex-1">
          <div className="font-medium text-gray-900">{getStatusText()}</div>
          <div className="text-sm text-gray-500">{getStatusDescription()}</div>
        </div>
      </div>

      {/* Status Details */}
      {aiStatus && (
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Service Status:</span>
            <span className={`font-medium ${
              aiStatus.status === 'ready' ? 'text-green-600' : 'text-yellow-600'
            }`}>
              {aiStatus.status}
            </span>
          </div>
        </div>
      )}

      {/* Progress Bar and Message */}
      {aiStatus && (aiStatus.status === 'starting' || aiStatus.status === 'initializing') && (
        <div className="mt-3 space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">Initialization Progress:</span>
            <span className="font-medium text-blue-600">{aiStatus.progress}%</span>
          </div>
          
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div 
              className="bg-blue-600 h-2 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${aiStatus.progress}%` }}
            ></div>
          </div>
          
          <div className="text-sm text-gray-600 italic">
            {aiStatus.message}
          </div>
        </div>
      )}

      {/* Last Updated */}
      {lastChecked && (
        <div className="mt-3 pt-3 border-t border-gray-100 text-xs text-gray-400">
          Last updated: {lastChecked.toLocaleTimeString()}
        </div>
      )}

      {/* Quick Actions */}
      <div className="mt-4 pt-3 border-t border-gray-100">
        <div className="text-xs text-gray-500 mb-2">Quick Actions:</div>
        <div className="flex space-x-2">
          <button
            onClick={loadAIStatus}
            disabled={isLoading}
            className="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition-colors disabled:opacity-50"
          >
            Refresh
          </button>
          {aiStatus?.status === 'ready' && (
            <span className="px-2 py-1 text-xs bg-green-100 text-green-700 rounded">
              Ready to use
            </span>
          )}
        </div>
      </div>

      {/* Model Selection Modal */}
      <ModelSelectionModal
        isOpen={isModelModalOpen}
        onClose={() => setIsModelModalOpen(false)}
      />
    </div>
  )
}

export default AIStatusCard
