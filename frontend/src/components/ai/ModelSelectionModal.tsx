import React, { useState, useEffect } from 'react'
import { aiAPI } from '../../services/api'

interface ModelConfiguration {
  current_provider: string
  provider_name: string
  embedding_model: string
  chat_model: string
  available_providers: {
    [key: string]: {
      name: string
      embedding_models: string[]
      chat_models: string[]
    }
  }
  model_descriptions?: {
    [key: string]: string
  }
}

interface ModelSelectionModalProps {
  isOpen: boolean
  onClose: () => void
}

const ModelSelectionModal: React.FC<ModelSelectionModalProps> = ({ isOpen, onClose }) => {
  const [config, setConfig] = useState<ModelConfiguration | null>(null)
  const [loading, setLoading] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState('')
  const [selectedEmbeddingModel, setSelectedEmbeddingModel] = useState('')
  const [selectedChatModel, setSelectedChatModel] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (isOpen) {
      loadModelConfiguration()
    }
  }, [isOpen])

  const loadModelConfiguration = async () => {
    try {
      setLoading(true)
      const response = await aiAPI.getModelConfiguration()
      setConfig(response.data)
      setSelectedProvider(response.data.current_provider)
      setSelectedEmbeddingModel(response.data.embedding_model)
      setSelectedChatModel(response.data.chat_model)
    } catch (error) {
      console.error('Error loading model configuration:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      await aiAPI.updateModelConfiguration(
        selectedProvider,
        selectedEmbeddingModel,
        selectedChatModel
      )
      onClose()
      // Optionally reload the configuration
      await loadModelConfiguration()
    } catch (error) {
      console.error('Error updating model configuration:', error)
    } finally {
      setSaving(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 dark:bg-black/70 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-slate-800 rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-slate-100">AI Model Configuration</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : config ? (
          <div className="space-y-6">
            {/* Provider Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                AI Provider
              </label>
              <select
                value={selectedProvider}
                onChange={(e) => {
                  setSelectedProvider(e.target.value)
                  // Reset model selections when provider changes
                  setSelectedEmbeddingModel('')
                  setSelectedChatModel('')
                }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-slate-700 dark:text-slate-100"
              >
                {Object.entries(config.available_providers).map(([key, provider]) => (
                  <option key={key} value={key}>
                    {provider.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Embedding Model Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                Embedding Model
              </label>
              <select
                value={selectedEmbeddingModel}
                onChange={(e) => setSelectedEmbeddingModel(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-slate-700 dark:text-slate-100"
              >
                <option value="">Select an embedding model</option>
                {config.available_providers[selectedProvider]?.embedding_models.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            </div>

            {/* Chat Model Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                Chat Model
              </label>
              <select
                value={selectedChatModel}
                onChange={(e) => setSelectedChatModel(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white dark:bg-slate-700 dark:text-slate-100"
              >
                <option value="">Select a chat model</option>
                {config.available_providers[selectedProvider]?.chat_models.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>

              {/* Model Description */}
              {selectedChatModel && config.model_descriptions?.[selectedChatModel] && (
                <div className="mt-2 p-3 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-md">
                  <div className="text-sm text-blue-800 dark:text-blue-200">
                    <span className="font-medium">Description:</span> {config.model_descriptions[selectedChatModel]}
                  </div>
                </div>
              )}
            </div>

            {/* Current Configuration Display */}
            <div className="bg-gray-50 dark:bg-slate-700/50 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">Current Configuration</h3>
              <div className="text-sm text-gray-600 dark:text-slate-400 space-y-1">
                <div><span className="font-medium">Provider:</span> {config.provider_name}</div>
                <div><span className="font-medium">Embedding Model:</span> {config.embedding_model}</div>
                <div><span className="font-medium">Chat Model:</span> {config.chat_model}</div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex justify-end space-x-3 pt-4">
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-slate-200 bg-white dark:bg-slate-700 border border-gray-300 dark:border-slate-600 rounded-md hover:bg-gray-50 dark:hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !selectedProvider || !selectedEmbeddingModel || !selectedChatModel}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? 'Saving...' : 'Save Configuration'}
              </button>
            </div>
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500 dark:text-slate-400">
            Failed to load model configuration
          </div>
        )}
      </div>
    </div>
  )
}

export default ModelSelectionModal
