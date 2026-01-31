import { useState, useRef, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, Sparkles, Check } from 'lucide-react'
import clsx from 'clsx'

import { openRouterAgentAPI, openRouterDiscussionAPI } from '../../services/api'
import { OpenRouterModel, OpenRouterModelsResponse } from '../../types'

export interface OpenRouterModelOption {
  id: string
  name: string
  provider: string
  supportsReasoning: boolean
}

// Fallback OpenRouter models (used if API is unavailable)
// supportsReasoning: true if the model supports OpenRouter's reasoning parameter
export const OPENROUTER_MODELS: OpenRouterModelOption[] = [
  // OpenAI (GPT-5.2 series - latest) - All GPT-5+ support reasoning via reasoning.effort
  { id: 'openai/gpt-5.2-20251211', name: 'GPT-5.2', provider: 'OpenAI', supportsReasoning: true },
  { id: 'openai/gpt-5.2-codex-20260114', name: 'GPT-5.2 Codex', provider: 'OpenAI', supportsReasoning: true },
  { id: 'openai/gpt-5.1-20251113', name: 'GPT-5.1', provider: 'OpenAI', supportsReasoning: true },
  { id: 'openai/gpt-4o', name: 'GPT-4o', provider: 'OpenAI', supportsReasoning: false },
  { id: 'openai/gpt-4o-mini', name: 'GPT-4o Mini', provider: 'OpenAI', supportsReasoning: false },
  // Anthropic (Claude 4.5 series - latest) - Claude 4.5+ supports extended thinking
  { id: 'anthropic/claude-4.5-opus-20251124', name: 'Claude 4.5 Opus', provider: 'Anthropic', supportsReasoning: true },
  { id: 'anthropic/claude-4.5-sonnet-20250929', name: 'Claude 4.5 Sonnet', provider: 'Anthropic', supportsReasoning: true },
  { id: 'anthropic/claude-4.5-haiku-20251001', name: 'Claude 4.5 Haiku', provider: 'Anthropic', supportsReasoning: true },
  { id: 'anthropic/claude-3.5-sonnet', name: 'Claude 3.5 Sonnet', provider: 'Anthropic', supportsReasoning: false },
  // Google (Gemini 3 series - latest) - Gemini 2.5+ supports thinking via thinkingLevel
  { id: 'google/gemini-3-pro-preview-20251117', name: 'Gemini 3 Pro', provider: 'Google', supportsReasoning: true },
  { id: 'google/gemini-3-flash-preview-20251217', name: 'Gemini 3 Flash', provider: 'Google', supportsReasoning: true },
  { id: 'google/gemini-2.5-pro', name: 'Gemini 2.5 Pro', provider: 'Google', supportsReasoning: true },
  { id: 'google/gemini-2.5-flash', name: 'Gemini 2.5 Flash', provider: 'Google', supportsReasoning: true },
  // DeepSeek (V3.2 series - latest) - R1 models have built-in reasoning, V3 supports via param
  { id: 'deepseek/deepseek-v3.2-20251201', name: 'DeepSeek V3.2', provider: 'DeepSeek', supportsReasoning: true },
  { id: 'deepseek/deepseek-chat-v3.1', name: 'DeepSeek V3.1', provider: 'DeepSeek', supportsReasoning: true },
  { id: 'deepseek/deepseek-r1', name: 'DeepSeek R1', provider: 'DeepSeek', supportsReasoning: true },
  { id: 'deepseek/deepseek-r1:free', name: 'DeepSeek R1 (Free)', provider: 'DeepSeek', supportsReasoning: true },
  // Meta - Llama doesn't have native reasoning support
  { id: 'meta-llama/llama-3.3-70b-instruct', name: 'Llama 3.3 70B', provider: 'Meta', supportsReasoning: false },
  // Qwen - No native reasoning support
  { id: 'qwen/qwen-2.5-72b-instruct', name: 'Qwen 2.5 72B', provider: 'Qwen', supportsReasoning: false },
]

const REASONING_MODEL_IDS = new Set(
  OPENROUTER_MODELS.filter((model) => model.supportsReasoning).map((model) => model.id)
)

// Helper function to check if a model supports reasoning
export function modelSupportsReasoning(modelId: string, models: OpenRouterModelOption[] = OPENROUTER_MODELS): boolean {
  const model = models.find((m) => m.id === modelId)
  return model?.supportsReasoning ?? false
}

const PROVIDER_ORDER = ['OpenAI', 'Anthropic', 'Google', 'DeepSeek', 'Meta', 'Qwen']

interface ModelSelectorProps {
  value: string
  onChange: (modelId: string) => void
  disabled?: boolean
  className?: string
  models?: OpenRouterModelOption[]
}

const normalizeModels = (models: OpenRouterModel[]): OpenRouterModelOption[] =>
  models.map((model) => ({
    id: model.id,
    name: model.name,
    provider: model.provider,
    supportsReasoning:
      typeof model.supports_reasoning === 'boolean' ? model.supports_reasoning : REASONING_MODEL_IDS.has(model.id),
  }))

export function useOpenRouterModels(projectId?: string, enabled: boolean = true) {
  const query = useQuery({
    queryKey: ['openrouter-models', 'v3', projectId ?? 'agent'],
    queryFn: async () => {
      const response = projectId
        ? await openRouterDiscussionAPI.listModels(projectId)
        : await openRouterAgentAPI.listModels()
      return response.data
    },
    staleTime: 24 * 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
    enabled,
  })

  const resolvedData = query.data
  const payload = Array.isArray(resolvedData)
    ? resolvedData
    : (resolvedData as OpenRouterModelsResponse | undefined)?.models
  const warning = Array.isArray(resolvedData)
    ? undefined
    : (resolvedData as OpenRouterModelsResponse | undefined)?.warning
  const source = Array.isArray(resolvedData)
    ? undefined
    : (resolvedData as OpenRouterModelsResponse | undefined)?.source

  const models = payload && payload.length > 0 ? normalizeModels(payload) : OPENROUTER_MODELS

  return {
    models,
    isLoading: query.isLoading,
    error: query.error,
    warning,
    source,
  }
}

export function ModelSelector({ value, onChange, disabled = false, className, models }: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const shouldFetch = !models || models.length === 0
  const { models: fetchedModels } = useOpenRouterModels(undefined, shouldFetch)
  const resolvedModels = models && models.length > 0 ? models : fetchedModels

  const selectedModel = resolvedModels.find((m) => m.id === value) || resolvedModels[0]
  const modelGroups = useMemo(() => {
    return resolvedModels.reduce((acc, model) => {
      if (!acc[model.provider]) {
        acc[model.provider] = []
      }
      acc[model.provider].push(model)
      return acc
    }, {} as Record<string, OpenRouterModelOption[]>)
  }, [resolvedModels])

  const orderedProviders = useMemo(() => {
    const known = PROVIDER_ORDER.filter((provider) => modelGroups[provider])
    const extras = Object.keys(modelGroups).filter((provider) => !PROVIDER_ORDER.includes(provider)).sort()
    return [...known, ...extras]
  }, [modelGroups])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Close on escape
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  const handleSelect = (modelId: string) => {
    onChange(modelId)
    setIsOpen(false)
  }

  return (
    <div className={clsx('relative', className)} ref={dropdownRef}>
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={clsx(
          'flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium transition-all',
          'bg-white dark:bg-slate-800',
          disabled
            ? 'cursor-not-allowed border-gray-200 text-gray-400 dark:border-slate-700 dark:text-slate-500'
            : 'border-gray-300 text-gray-700 hover:border-indigo-400 hover:bg-indigo-50 dark:border-slate-600 dark:text-slate-200 dark:hover:border-indigo-500 dark:hover:bg-indigo-900/20'
        )}
      >
        <Sparkles className="h-4 w-4 text-indigo-500 dark:text-indigo-400" />
        <span className="max-w-[120px] truncate">{selectedModel.name}</span>
        <span className="text-xs text-gray-400 dark:text-slate-500">{selectedModel.provider}</span>
        <ChevronDown
          className={clsx(
            'h-4 w-4 text-gray-400 transition-transform dark:text-slate-500',
            isOpen && 'rotate-180'
          )}
        />
      </button>

      {isOpen && (
        <div className="absolute left-0 top-full z-50 mt-1 w-72 rounded-xl border border-gray-200 bg-white py-2 shadow-xl dark:border-slate-700 dark:bg-slate-800">
          <div className="px-3 pb-2">
            <div className="text-xs font-medium text-gray-500 dark:text-slate-400">
              Select AI Model
            </div>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {orderedProviders.map((provider) => (
              <div key={provider}>
                <div className="sticky top-0 bg-white px-3 py-1.5 text-xs font-semibold text-gray-400 dark:bg-slate-800 dark:text-slate-500">
                  {provider}
                </div>
                {modelGroups[provider].map((model) => (
                  <button
                    key={model.id}
                    type="button"
                    onClick={() => handleSelect(model.id)}
                    className={clsx(
                      'flex w-full items-center justify-between px-3 py-2 text-sm transition-colors',
                      model.id === value
                        ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300'
                        : 'text-gray-700 hover:bg-gray-50 dark:text-slate-200 dark:hover:bg-slate-700/50'
                    )}
                  >
                    <span className="font-medium">{model.name}</span>
                    {model.id === value && (
                      <Check className="h-4 w-4 text-indigo-500 dark:text-indigo-400" />
                    )}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default ModelSelector
