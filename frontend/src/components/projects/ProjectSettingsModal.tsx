import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { X, Bot, AlertCircle, CheckCircle } from 'lucide-react'
import { projectsAPI } from '../../services/api'
import { ProjectDetail } from '../../types'
import { useOpenRouterModels } from '../discussion/ModelSelector'

const PROVIDER_ORDER = ['OpenAI', 'Anthropic', 'Google', 'DeepSeek', 'Meta', 'Qwen']

interface ProjectSettingsModalProps {
  project: ProjectDetail
  isOpen: boolean
  onClose: () => void
}

export default function ProjectSettingsModal({ project, isOpen, onClose }: ProjectSettingsModalProps) {
  const queryClient = useQueryClient()
  const { models: openrouterModels } = useOpenRouterModels(project.id)

  const modelGroups = openrouterModels.reduce((acc, model) => {
    if (!acc[model.provider]) {
      acc[model.provider] = []
    }
    acc[model.provider].push(model)
    return acc
  }, {} as Record<string, typeof openrouterModels>)
  const orderedProviders = useMemo(() => {
    const known = PROVIDER_ORDER.filter((provider) => modelGroups[provider])
    const extras = Object.keys(modelGroups).filter((provider) => !PROVIDER_ORDER.includes(provider)).sort()
    return [...known, ...extras]
  }, [modelGroups])

  // Fetch current AI settings
  const settingsQuery = useQuery({
    queryKey: ['project-ai-settings', project.id],
    queryFn: async () => {
      const response = await projectsAPI.getDiscussionSettings(project.id)
      return response.data
    },
    enabled: isOpen,
    staleTime: 30000,
  })

  const settings = settingsQuery.data
  const aiModel = settings?.model || openrouterModels[0]?.id
  const ownerHasApiKey = settings?.owner_has_api_key ?? false

  // Update settings mutation
  const updateSettingsMutation = useMutation({
    mutationFn: async (updates: { model?: string }) => {
      const response = await projectsAPI.updateDiscussionSettings(project.id, updates)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-ai-settings', project.id] })
      queryClient.invalidateQueries({ queryKey: ['project-discussion-settings', project.id] })
    },
  })

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl dark:bg-slate-900">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-100 dark:bg-indigo-500/20">
              <Bot className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-slate-100">AI Settings</h3>
              <p className="text-xs text-gray-500 dark:text-slate-400">Configure AI for this project</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {settingsQuery.isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
          </div>
        ) : (
          <div className="space-y-5">
            {/* API Key Status */}
            <div className={`rounded-xl p-4 ${ownerHasApiKey ? 'bg-green-50 dark:bg-green-500/10' : 'bg-amber-50 dark:bg-amber-500/10'}`}>
              <div className="flex items-start gap-3">
                {ownerHasApiKey ? (
                  <CheckCircle className="h-5 w-5 text-green-500 mt-0.5" />
                ) : (
                  <AlertCircle className="h-5 w-5 text-amber-500 mt-0.5" />
                )}
                <div>
                  <p className={`text-sm font-medium ${ownerHasApiKey ? 'text-green-800 dark:text-green-300' : 'text-amber-800 dark:text-amber-300'}`}>
                    {ownerHasApiKey ? 'API key configured' : 'No API key configured'}
                  </p>
                  <p className="text-xs text-gray-600 dark:text-slate-400 mt-1">
                    {ownerHasApiKey
                      ? 'Your API key will be used for all AI features in this project.'
                      : 'Configure your OpenRouter API key in Settings → API Keys to enable AI features.'}
                  </p>
                </div>
              </div>
            </div>

            {/* AI Model Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                AI Model
              </label>
              <select
                value={aiModel}
                onChange={(e) => updateSettingsMutation.mutate({ model: e.target.value })}
                disabled={updateSettingsMutation.isPending}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              >
                {orderedProviders.map((provider) => (
                  <optgroup key={provider} label={provider}>
                    {modelGroups[provider].map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.name}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              <p className="mt-2 text-xs text-gray-500 dark:text-slate-400">
                This model will be used for Discussion AI and LaTeX Editor AI for all project members.
              </p>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="mt-6 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 dark:bg-slate-700 dark:text-slate-200 dark:hover:bg-slate-600"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  )
}
