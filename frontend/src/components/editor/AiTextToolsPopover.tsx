import React, { useState, useEffect, useRef } from 'react'
import { X, Loader2, Sparkles, Type, FileText, Lightbulb, Book } from 'lucide-react'
import { useToast } from '../../hooks/useToast'

interface AiTextToolsPopoverProps {
  isOpen: boolean
  onClose: () => void
  anchorElement: HTMLElement | null
  selectedText: string
  onReplaceText: (newText: string) => void
}

type AiAction = 'paraphrase' | 'tone' | 'summarize' | 'explain' | 'synonyms'
type ToneType = 'formal' | 'casual' | 'academic' | 'friendly' | 'professional'

const AiTextToolsPopover: React.FC<AiTextToolsPopoverProps> = ({
  isOpen,
  onClose,
  anchorElement,
  selectedText,
  onReplaceText,
}) => {
  const { toast } = useToast()
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [result, setResult] = useState<string>('')
  const [selectedAction, setSelectedAction] = useState<AiAction | null>(null)
  const [selectedTone, setSelectedTone] = useState<ToneType>('formal')
  const popoverRef = useRef<HTMLDivElement>(null)

  const actions = [
    { key: 'paraphrase' as AiAction, label: 'Paraphrase', icon: Sparkles, description: 'Rewrite in different words' },
    { key: 'tone' as AiAction, label: 'Change Tone', icon: Type, description: 'Adjust writing style' },
    { key: 'summarize' as AiAction, label: 'Summarize', icon: FileText, description: 'Create brief summary' },
    { key: 'explain' as AiAction, label: 'Explain', icon: Lightbulb, description: 'Clarify meaning' },
    { key: 'synonyms' as AiAction, label: 'Find Synonyms', icon: Book, description: 'Get alternative words' },
  ]

  const tones: ToneType[] = ['formal', 'casual', 'academic', 'friendly', 'professional']

  // Calculate position relative to anchor
  useEffect(() => {
    if (!isOpen || !anchorElement) {
      setPosition(null)
      return
    }

    const updatePosition = () => {
      const rect = anchorElement.getBoundingClientRect()
      const popoverWidth = 400
      const popoverHeight = 500
      const spacing = 8

      let top = rect.bottom + spacing
      let left = rect.left

      // Adjust if popover goes off-screen
      if (left + popoverWidth > window.innerWidth) {
        left = window.innerWidth - popoverWidth - 20
      }
      if (top + popoverHeight > window.innerHeight) {
        top = rect.top - popoverHeight - spacing
      }

      setPosition({ top, left })
    }

    updatePosition()
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition)

    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition)
    }
  }, [isOpen, anchorElement])

  const handleClose = () => {
    setResult('')
    setSelectedAction(null)
    setIsProcessing(false)
    onClose()
  }

  const handleAction = async (action: AiAction) => {
    if (!selectedText.trim()) {
      toast.warning('Please select some text first')
      return
    }

    setSelectedAction(action)
    setIsProcessing(true)
    setResult('')

    try {
      const payload: any = {
        text: selectedText,
        action: action,
      }

      if (action === 'tone') {
        payload.tone = selectedTone
      }

      const response = await fetch('/api/v1/ai/text-tools', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`)
      }

      const data = await response.json()
      setResult(data.result || '')
    } catch (error) {
      console.error('AI action failed:', error)
      toast.error('Failed to process text. Please try again.')
    } finally {
      setIsProcessing(false)
    }
  }

  const handleUseResult = () => {
    if (result) {
      onReplaceText(result)
      handleClose()
    }
  }

  if (!isOpen || !position) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/20"
        onClick={handleClose}
      />

      {/* Popover */}
      <div
        ref={popoverRef}
        className="fixed z-50 w-[400px] rounded-lg bg-white shadow-2xl"
        style={{ top: position.top, left: position.left }}
      >
        {/* Header */}
        <div className="border-b border-gray-200 px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-indigo-600" />
              <h3 className="text-sm font-semibold text-gray-900">AI Text Tools</h3>
            </div>
            <button
              onClick={handleClose}
              className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          {selectedText && (
            <p className="mt-2 text-xs text-gray-500">
              {selectedText.length} characters selected
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="p-3">
          <div className="space-y-2">
            {actions.map((action) => {
              const Icon = action.icon
              const isActive = selectedAction === action.key

              return (
                <div key={action.key}>
                  <button
                    onClick={() => handleAction(action.key)}
                    disabled={isProcessing || !selectedText.trim()}
                    className={`w-full rounded-lg border p-3 text-left transition-all disabled:cursor-not-allowed disabled:opacity-50 ${
                      isActive
                        ? 'border-indigo-500 bg-indigo-50'
                        : 'border-gray-200 bg-white hover:border-indigo-300 hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <Icon className={`h-4 w-4 flex-shrink-0 ${isActive ? 'text-indigo-600' : 'text-gray-600'}`} />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-900">{action.label}</div>
                        <div className="text-xs text-gray-500">{action.description}</div>
                      </div>
                    </div>
                  </button>

                  {/* Tone selector for tone change */}
                  {action.key === 'tone' && isActive && (
                    <div className="mt-2 ml-7 space-y-2">
                      <label className="text-xs font-medium text-gray-700">Select Tone:</label>
                      <div className="flex flex-wrap gap-2">
                        {tones.map((tone) => (
                          <button
                            key={tone}
                            onClick={() => setSelectedTone(tone)}
                            className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                              selectedTone === tone
                                ? 'border-indigo-500 bg-indigo-500 text-white'
                                : 'border-gray-300 bg-white text-gray-700 hover:border-indigo-300 hover:bg-indigo-50'
                            }`}
                          >
                            {tone.charAt(0).toUpperCase() + tone.slice(1)}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Processing indicator */}
        {isProcessing && (
          <div className="border-t border-gray-200 bg-gray-50 px-4 py-3">
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Processing...</span>
            </div>
          </div>
        )}

        {/* Result */}
        {result && !isProcessing && (
          <div className="border-t border-gray-200 bg-gray-50 p-4">
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-700">Result:</label>
                <div className="mt-1 max-h-[200px] overflow-y-auto rounded border border-gray-200 bg-white p-3 text-sm text-gray-900">
                  {result}
                </div>
              </div>
              <div className="flex items-center justify-end gap-2">
                <button
                  onClick={() => setResult('')}
                  className="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100"
                >
                  Clear
                </button>
                <button
                  onClick={handleUseResult}
                  className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
                >
                  Use This Text
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  )
}

export default AiTextToolsPopover
