import { useMemo } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { X, Bot, AlertCircle, CheckCircle } from 'lucide-react'
import { projectsAPI } from '../../services/api'
import { ProjectDetail } from '../../types'
import { useOpenRouterModels } from '../discussion/ModelSelector'
import { useAuth } from '../../contexts/AuthContext'

const PROVIDER_ORDER = ['OpenAI', 'Anthropic', 'Google', 'DeepSeek', 'Meta', 'Qwen']

interface ProjectSettingsModalProps {
  project: ProjectDetail
  isOpen: boolean
  onClose: () => void
}

export default function ProjectSettingsModal({ project, isOpen, onClose }: ProjectSettingsModalProps) {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const { models: openrouterModels, warning: openrouterWarning } = useOpenRouterModels(project.id)

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
  const settingsLoaded = Boolean(settings)
  const aiModel = settings?.model || openrouterModels[0]?.id
  const ownerHasApiKey = settings?.owner_has_api_key ?? false
  const viewerHasApiKey = settings?.viewer_has_api_key ?? false
  const serverKeyAvailable = settings?.server_key_available ?? false
  const useOwnerKeyForTeam = settings?.use_owner_key_for_team ?? false
  const isOwner = user?.id === project.created_by
  const ownerKeyAvailableForViewer = isOwner ? ownerHasApiKey : ownerHasApiKey && useOwnerKeyForTeam
  const hasAnyApiKey = settingsLoaded && (viewerHasApiKey || serverKeyAvailable || ownerKeyAvailableForViewer)

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

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-sm">
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
            {settingsQuery.isError && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-700 dark:border-amber-400/40 dark:bg-amber-900/30 dark:text-amber-300">
                <AlertCircle className="mr-2 inline-block h-4 w-4" />
                Unable to load AI settings. Please refresh and try again.
              </div>
            )}
            {/* API Key Status */}
            <div className={`rounded-xl p-4 ${hasAnyApiKey ? 'bg-green-50 dark:bg-green-500/10' : 'bg-amber-50 dark:bg-amber-500/10'}`}>
              <div className="flex items-start gap-3">
                {hasAnyApiKey ? (
                  <CheckCircle className="h-5 w-5 text-green-500 mt-0.5" />
                ) : (
                  <AlertCircle className="h-5 w-5 text-amber-500 mt-0.5" />
                )}
                <div>
                  <p className={`text-sm font-medium ${hasAnyApiKey ? 'text-green-800 dark:text-green-300' : 'text-amber-800 dark:text-amber-300'}`}>
                    {settingsLoaded ? (hasAnyApiKey ? 'API key configured' : 'No API key configured') : 'API status unavailable'}
                  </p>
                  <p className="text-xs text-gray-600 dark:text-slate-400 mt-1">
                    {settingsLoaded
                      ? viewerHasApiKey
                        ? 'Your API key will be used for AI features in this project.'
                        : serverKeyAvailable
                          ? 'Your subscription allows the platform key to be used for AI features.'
                          : ownerKeyAvailableForViewer
                            ? isOwner
                              ? 'Your API key will be used for AI features in this project.'
                              : 'The project owner has shared their API key with the team.'
                            : ownerHasApiKey && !isOwner
                              ? "The project owner has a key but hasn't enabled sharing. Add your own key or ask them to enable sharing."
                              : 'Configure your OpenRouter API key in Settings → API Keys to enable AI features.'
                      : 'We could not load your AI key status. Refresh or check your connection.'}
                  </p>
                </div>
              </div>
            </div>
            {hasAnyApiKey && openrouterWarning && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-700 dark:border-amber-400/40 dark:bg-amber-900/30 dark:text-amber-300">
                <AlertCircle className="mr-2 inline-block h-4 w-4" />
                {openrouterWarning}
              </div>
            )}

            {isOwner && settingsLoaded && (
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-200">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-medium">Share your API key with team members</p>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      When enabled, members without their own key can use yours.
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={!ownerHasApiKey || updateSettingsMutation.isPending}
                    onClick={() =>
                      updateSettingsMutation.mutate({ use_owner_key_for_team: !useOwnerKeyForTeam })
                    }
                    className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition ${
                      useOwnerKeyForTeam ? 'bg-indigo-600' : 'bg-slate-300 dark:bg-slate-600'
                    } ${!ownerHasApiKey ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <span
                      className={`inline-block h-5 w-5 transform rounded-full bg-white transition ${
                        useOwnerKeyForTeam ? 'translate-x-5' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
                {!ownerHasApiKey && (
                  <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                    Add your OpenRouter API key first to enable sharing.
                  </p>
                )}
              </div>
            )}

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
    </div>,
    document.body
  )
}
