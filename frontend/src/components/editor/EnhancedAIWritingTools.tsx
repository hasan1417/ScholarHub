import React, {
  useState,
  useEffect,
  useMemo,
  useCallback,
  useRef,
  useLayoutEffect
} from 'react'
import {
  Bot,
  Loader2,
  X,
  Sparkles,
  Check,
  Copy,
  RefreshCw,
  Highlighter
} from 'lucide-react'
import { streamAPI } from '../../services/api'

interface EnhancedAIWritingToolsProps {
  selectedText: string
  onReplaceText: (newText: string) => void
  onInsertText: (text: string) => void
  currentPaperContent?: string
  onCitationInsert?: (citation: string) => void
  open?: boolean
  onOpenChange?: (open: boolean) => void
  showLauncher?: boolean
  anchorElement?: HTMLElement | null
}

interface PromptTemplate {
  id: string
  title: string
  description: string
  prompt: string
}

interface AIResult {
  text: string
  citations?: string[]
}

type PanelPlacement = 'top' | 'bottom'

const PROMPT_TEMPLATES: PromptTemplate[] = [
  {
    id: 'literature_review',
    title: 'Literature Review',
    description: 'Build a related work section from linked references.',
    prompt:
      'Generate a literature review section that synthesizes the linked references into thematic paragraphs. Highlight key contributions and disagreements, and cite sources inline.'
  },
  {
    id: 'abstract',
    title: 'Draft Abstract',
    description: 'Summarize the paper in ~200 words.',
    prompt:
      'Draft an academic abstract summarizing the paper’s problem, methodology, key findings, and significance in under 200 words.'
  }
]

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'

const EnhancedAIWritingTools: React.FC<EnhancedAIWritingToolsProps> = ({
  selectedText,
  onReplaceText,
  onInsertText,
  currentPaperContent = '',
  onCitationInsert,
  open,
  onOpenChange,
  showLauncher = true,
  anchorElement,
}) => {
  const isControlled = typeof open === 'boolean'
  const [internalOpen, setInternalOpen] = useState(false)
  const isOpen = isControlled ? Boolean(open) : internalOpen
  const setOpen = useCallback(
    (value: boolean) => {
      if (!isControlled) {
        setInternalOpen(value)
      }
      onOpenChange?.(value)
    },
    [isControlled, onOpenChange]
  )

  const dialogRef = useRef<HTMLDivElement | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const triggerRef = useRef<HTMLElement | null>(null)
  const animationFrameRef = useRef<number>()

  const hasSelection = selectedText.trim().length > 0

  const [activeTemplateId, setActiveTemplateId] = useState<string>('literature_review')
  const [promptText, setPromptText] = useState<string>(PROMPT_TEMPLATES[0].prompt)
  const [includeSelection, setIncludeSelection] = useState<boolean>(false)
  const [result, setResult] = useState<AIResult | null>(null)
  const [streamedText, setStreamedText] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [isProcessing, setIsProcessing] = useState<boolean>(false)
  const [lastRequest, setLastRequest] = useState<{ instruction: string; text: string; context: string } | null>(null)
  const [copied, setCopied] = useState<boolean>(false)
  const [position, setPosition] = useState<{ top: number; left: number; placement: PanelPlacement; arrowLeft: number } | null>(null)
  const [positionReady, setPositionReady] = useState(false)
  const [reduceMotion, setReduceMotion] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduceMotion(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  useEffect(() => {
    if (anchorElement) {
      triggerRef.current = anchorElement
    }
  }, [anchorElement])

  useEffect(() => {
    if (isOpen && hasSelection) {
      setIncludeSelection(true)
    } else if (!hasSelection) {
      setIncludeSelection(false)
    }
  }, [isOpen, hasSelection])

  const handleTemplateSelect = useCallback((template: PromptTemplate) => {
    setActiveTemplateId(template.id)
    setPromptText(template.prompt)
  }, [])

  const selectionPreview = useMemo(() => {
    if (!hasSelection) return ''
    return selectedText.length > 400 ? `${selectedText.slice(0, 400)}…` : selectedText
  }, [selectedText, hasSelection])

  const updatePosition = useCallback(() => {
    if (!isOpen) return
    const panel = dialogRef.current
    const anchor = anchorElement
    if (!panel) return

    const safeMargin = 16
    const offset = 12
    const panelRect = panel.getBoundingClientRect()
    const panelWidth = panelRect.width || panel.offsetWidth
    const panelHeight = panelRect.height || panel.offsetHeight

    let top = safeMargin
    let left = safeMargin
    let placement: PanelPlacement = 'bottom'
    let arrowLeft = panelWidth / 2

    if (anchor) {
      const rect = anchor.getBoundingClientRect()
      const anchorCenterX = rect.left + rect.width / 2
      const maxLeft = window.innerWidth - panelWidth - safeMargin
      const minLeft = safeMargin
      left = Math.min(maxLeft, Math.max(minLeft, anchorCenterX - panelWidth / 2))

      const enoughBottomSpace = window.innerHeight - rect.bottom - safeMargin
      const enoughTopSpace = rect.top - safeMargin
      const shouldPlaceBottom = enoughBottomSpace >= panelHeight + offset || enoughBottomSpace >= enoughTopSpace

      placement = shouldPlaceBottom ? 'bottom' : 'top'
      if (placement === 'bottom') {
        top = Math.min(window.innerHeight - panelHeight - safeMargin, rect.bottom + offset)
      } else {
        top = Math.max(safeMargin, rect.top - panelHeight - offset)
        if (top < safeMargin) {
          placement = 'bottom'
          top = Math.min(window.innerHeight - panelHeight - safeMargin, rect.bottom + offset)
        }
      }

      const rawArrowLeft = anchorCenterX - left
      const arrowPadding = 18

      if (rawArrowLeft < arrowPadding) {
        const shift = rawArrowLeft - arrowPadding
        const adjustedLeft = Math.max(minLeft, left + shift)
        left = adjustedLeft
      } else if (rawArrowLeft > panelWidth - arrowPadding) {
        const shift = rawArrowLeft - (panelWidth - arrowPadding)
        const adjustedLeft = Math.min(maxLeft, left + shift)
        left = adjustedLeft
      }

      arrowLeft = anchorCenterX - left
      arrowLeft = Math.max(arrowPadding, Math.min(panelWidth - arrowPadding, arrowLeft))
    } else {
      // fallback to top-right corner with margin
      left = Math.min(window.innerWidth - panelWidth - safeMargin, Math.max(safeMargin, window.innerWidth - panelWidth - safeMargin))
      top = safeMargin
      placement = 'bottom'
      arrowLeft = panelWidth - 24
    }

    setPosition({ top, left, placement, arrowLeft })
    setPositionReady(true)
  }, [anchorElement, isOpen])

  useLayoutEffect(() => {
    if (!isOpen) {
      setPosition(null)
      setPositionReady(false)
      return
    }
    setPositionReady(false)
    if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current)
    // Add small delay to ensure anchor has rendered
    const timeoutId = setTimeout(() => {
      animationFrameRef.current = window.requestAnimationFrame(() => updatePosition())
    }, 50)
    return () => {
      clearTimeout(timeoutId)
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current)
    }
  }, [isOpen, updatePosition])

  useEffect(() => {
    if (!isOpen) return
    const handle = () => updatePosition()
    window.addEventListener('resize', handle)
    window.addEventListener('scroll', handle, true)
    return () => {
      window.removeEventListener('resize', handle)
      window.removeEventListener('scroll', handle, true)
    }
  }, [isOpen, updatePosition])

  useEffect(() => {
    if (!isOpen) {
      if (triggerRef.current) {
        triggerRef.current.focus()
      }
      return
    }

    const previouslyFocused = document.activeElement as HTMLElement | null
    const focusTarget = textareaRef.current

    window.requestAnimationFrame(() => {
      if (focusTarget) {
        focusTarget.focus()
        focusTarget.select()
      } else if (dialogRef.current) {
        dialogRef.current.focus()
      }
    })

    return () => {
      if (previouslyFocused && previouslyFocused.focus) {
        previouslyFocused.focus()
      }
    }
  }, [isOpen])

  const getFocusableElements = useCallback((): HTMLElement[] => {
    if (!dialogRef.current) return []
    const nodes = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
    return nodes.filter((el) => !el.hasAttribute('disabled') && el.getAttribute('aria-hidden') !== 'true')
  }, [])

  const closeAssistant = useCallback(() => {
    setOpen(false)
    setResult(null)
    setError(null)
  }, [setOpen])

  const buildContextString = useCallback(() => {
    if (currentPaperContent) {
      return `Paper context (excerpt): ${currentPaperContent.substring(0, 700)}...`
    }
    return ''
  }, [currentPaperContent])

  const handleGenerate = useCallback(async () => {
    if (!promptText.trim()) {
      setError('Enter a prompt before generating.')
      return
    }

    if (includeSelection && !hasSelection) {
      const proceed = window.confirm('No highlighted LaTeX found. Run using the entire document instead?')
      if (!proceed) return
      setIncludeSelection(false)
    }

    const textPayload = includeSelection && hasSelection ? selectedText : ''
    const contextPayload = buildContextString()

    try {
      setIsProcessing(true)
      setError(null)
      setResult(null)
      setStreamedText('')
      setCopied(false)

      const response = await streamAPI.writingGenerateStream(
        textPayload,
        promptText.trim(),
        contextPayload || undefined,
        600
      )
      if (!response.ok) {
        const errText = await response.text()
        throw new Error(errText || 'Failed to generate content.')
      }
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      let fullText = ''
      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const chunk = decoder.decode(value || new Uint8Array(), { stream: true })
          fullText += chunk
          setStreamedText((prev) => (prev || '') + chunk)
        }
      }

      if (!fullText.trim()) {
        throw new Error('The AI response did not contain any text.')
      }

      setResult({
        text: fullText,
        citations: []
      })
      setLastRequest({ instruction: promptText.trim(), text: textPayload, context: contextPayload })
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to generate content.')
    } finally {
      setIsProcessing(false)
    }
  }, [promptText, includeSelection, hasSelection, selectedText, buildContextString])

  const handleRegenerate = useCallback(async () => {
    if (!lastRequest) return
    try {
      setIsProcessing(true)
      setError(null)
      setResult(null)
      setStreamedText('')
      setCopied(false)

      const response = await streamAPI.writingGenerateStream(
        lastRequest.text,
        lastRequest.instruction,
        lastRequest.context || undefined,
        600
      )
      if (!response.ok) {
        const errText = await response.text()
        throw new Error(errText || 'Failed to regenerate content.')
      }
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      let fullText = ''
      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const chunk = decoder.decode(value || new Uint8Array(), { stream: true })
          fullText += chunk
          setStreamedText((prev) => (prev || '') + chunk)
        }
      }
      if (!fullText.trim()) {
        throw new Error('The AI response did not contain any text.')
      }

      setResult({
        text: fullText,
        citations: []
      })
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to regenerate content.')
    } finally {
      setIsProcessing(false)
    }
  }, [lastRequest])

  const handleApply = useCallback(() => {
    if (!result) return
    if (includeSelection && hasSelection) {
      onReplaceText(result.text)
    } else {
      onInsertText(result.text)
    }
    setResult(null)
    setStreamedText('')
  }, [result, includeSelection, hasSelection, onReplaceText, onInsertText])

  const handleCopy = useCallback(async () => {
    if (!result) return
    try {
      await navigator.clipboard.writeText(result.text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {}
  }, [result])

  const handlePromptNavigation = useCallback((direction: 1 | -1) => {
    const index = PROMPT_TEMPLATES.findIndex((template) => template.id === activeTemplateId)
    const nextIndex = (index + direction + PROMPT_TEMPLATES.length) % PROMPT_TEMPLATES.length
    handleTemplateSelect(PROMPT_TEMPLATES[nextIndex])
  }, [activeTemplateId, handleTemplateSelect])

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (!isOpen) return

      if (event.key === 'Escape') {
        event.preventDefault()
        closeAssistant()
        return
      }

      if (event.key === 'Tab') {
        const focusables = getFocusableElements()
        if (focusables.length === 0) {
          event.preventDefault()
          return
        }
        const current = document.activeElement as HTMLElement
        const currentIndex = focusables.indexOf(current)
        let nextIndex = currentIndex
        if (event.shiftKey) {
          nextIndex = currentIndex <= 0 ? focusables.length - 1 : currentIndex - 1
        } else {
          nextIndex = currentIndex === focusables.length - 1 ? 0 : currentIndex + 1
        }
        focusables[nextIndex]?.focus()
        event.preventDefault()
        return
      }

      const isTextarea = event.target instanceof HTMLTextAreaElement

      if (event.key === 'Enter' && !event.shiftKey) {
        if (isTextarea && (event.metaKey || event.ctrlKey)) {
          event.preventDefault()
          if (!hasSelection) {
            const proceed = window.confirm('No highlighted LaTeX found. Run using the entire document instead?')
            if (!proceed) return
            setIncludeSelection(false)
          } else {
            setIncludeSelection(true)
          }
          handleGenerate()
          return
        }

        if (isTextarea && !(event.metaKey || event.ctrlKey)) {
          event.preventDefault()
          handleGenerate()
          return
        }

        if (!isTextarea) {
          event.preventDefault()
          handleGenerate()
          return
        }
      }

      if ((event.key === 'ArrowLeft' || event.key === 'ArrowRight') && !isTextarea) {
        event.preventDefault()
        handlePromptNavigation(event.key === 'ArrowRight' ? 1 : -1)
        return
      }

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'enter') {
        event.preventDefault()
        if (!hasSelection) {
          const proceed = window.confirm('No highlighted LaTeX found. Run using the entire document instead?')
          if (!proceed) return
          setIncludeSelection(false)
        } else {
          setIncludeSelection(true)
        }
        handleGenerate()
      }
    },
    [isOpen, closeAssistant, getFocusableElements, handleGenerate, handlePromptNavigation, hasSelection]
  )

  const panelStyle: React.CSSProperties = position
    ? {
        position: 'fixed',
        top: position.top,
        left: position.left,
        transformOrigin: position.placement === 'bottom' ? 'center top' : 'center bottom',
        opacity: positionReady ? 1 : 0,
        transform: reduceMotion || !positionReady ? 'scale(1)' : 'scale(0.96)',
        transition: reduceMotion
          ? 'opacity 0.01s linear'
          : 'opacity 0.18s ease, transform 0.18s ease'
      }
    : {
        position: 'fixed',
        top: -9999,
        left: -9999,
        opacity: 0
      }

  return (
    <>
      {showLauncher && !isOpen && (
        <button
          className="fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-lg hover:bg-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
          onClick={() => setOpen(true)}
        >
          <Bot className="h-4 w-4" />
          AI Assistant
        </button>
      )}

      {isOpen && (
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby="ai-assistant-title"
          tabIndex={-1}
          onKeyDown={handleKeyDown}
          className="z-50 w-full max-w-md rounded-xl border border-slate-200 bg-white shadow-2xl focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          style={panelStyle}
        >
          {position && (
            <div
              aria-hidden="true"
              className={`pointer-events-none absolute h-3 w-3 border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900 ${
                position.placement === 'bottom'
                  ? '-top-1 border-b-0 border-r-0'
                  : '-bottom-1 border-t-0 border-l-0'
              }`}
              style={{
                left: position.arrowLeft,
                transform: 'translateX(-50%) rotate(45deg)'
              }}
            />
          )}

          <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2 dark:border-slate-700">
            <div className="flex items-center gap-2 text-slate-800 dark:text-slate-100">
              <Bot className="h-5 w-5" />
              <span id="ai-assistant-title" className="text-sm font-semibold">
                AI Assistant
              </span>
            </div>
            <button
              className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              onClick={closeAssistant}
              aria-label="Close AI assistant"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="max-h-[70vh] overflow-y-auto px-4 py-4 space-y-4">
            <section className="space-y-2">
              <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2 dark:text-slate-100">
                <Sparkles className="h-4 w-4 text-indigo-500" /> Quick Prompts
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {PROMPT_TEMPLATES.map((template) => (
                  <button
                    key={template.id}
                    type="button"
                    onClick={() => handleTemplateSelect(template)}
                    className={`rounded-lg border px-3 py-2 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 ${
                      template.id === activeTemplateId
                        ? 'border-indigo-400 bg-indigo-50 text-indigo-700 dark:border-indigo-500/60 dark:bg-indigo-500/10 dark:text-indigo-100'
                        : 'border-slate-200 hover:border-indigo-300 hover:bg-indigo-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:hover:border-indigo-500/60 dark:hover:bg-indigo-500/10'
                    }`}
                  >
                    <div className="text-sm font-medium">{template.title}</div>
                    <div className="text-xs text-slate-500 mt-1 dark:text-slate-300">{template.description}</div>
                  </button>
                ))}
              </div>
            </section>

            <section className="space-y-2">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-100" htmlFor="ai-prompt-textarea">
                Prompt
              </label>
              <textarea
                id="ai-prompt-textarea"
                ref={textareaRef}
                rows={3}
                data-autofocus
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-200 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:border-indigo-500 dark:focus:ring-indigo-500/40"
                placeholder="Describe what you want the assistant to do..."
                value={promptText}
                onChange={(event) => setPromptText(event.target.value)}
              />
            </section>

            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-100">
                  <input
                    type="checkbox"
                    className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-800"
                    checked={includeSelection && hasSelection}
                    onChange={(event) => setIncludeSelection(event.target.checked)}
                    disabled={!hasSelection}
                  />
                  <span className="flex items-center gap-1">
                    <Highlighter className="h-4 w-4" />
                    Use highlighted LaTeX
                  </span>
                </label>
                {!hasSelection && (
                  <span className="text-xs text-slate-400 dark:text-slate-500">
                    Highlight text in the editor to add context.
                  </span>
                )}
              </div>
              {includeSelection && hasSelection && (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
                  <div className="text-xs font-semibold text-slate-500 mb-1 dark:text-slate-300">Selection preview</div>
                  <pre className="max-h-32 overflow-y-auto whitespace-pre-wrap text-xs text-slate-700 dark:text-slate-200">
                    {selectionPreview}
                  </pre>
                </div>
              )}
            </section>

            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-200">
                {error}
              </div>
            )}

            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                onClick={closeAssistant}
              >
                Close
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
                onClick={handleGenerate}
                disabled={isProcessing}
                aria-busy={isProcessing}
              >
                {isProcessing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {isProcessing ? 'Generating…' : 'Run Prompt'}
              </button>
            </div>

            {result && (
              <section className="space-y-3 border-t border-slate-200 pt-4 dark:border-slate-700">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-100">AI Response</h3>
                  <div className="flex items-center gap-2">
                    <button
                      className="rounded-md border border-slate-200 p-2 text-slate-500 hover:text-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:border-slate-700 dark:text-slate-300 dark:hover:text-slate-100"
                      onClick={handleRegenerate}
                      disabled={isProcessing}
                      title="Regenerate response"
                    >
                      <RefreshCw className={`h-4 w-4 ${isProcessing ? 'animate-spin' : ''}`} />
                    </button>
                    <button
                      className={`rounded-md border border-slate-200 p-2 ${
                        copied ? 'text-emerald-500' : 'text-slate-500 hover:text-slate-700'
                      } focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:border-slate-700 dark:text-slate-300 dark:hover:text-slate-100`}
                      onClick={handleCopy}
                      title="Copy to clipboard"
                    >
                      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 whitespace-pre-wrap dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200">
                  {streamedText || result.text}
                </div>
                {result.citations && result.citations.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300">
                      Citations
                    </h4>
                    <div className="space-y-1">
                      {result.citations.map((citation, index) => (
                        <button
                          key={index}
                          onClick={() => onCitationInsert?.(citation)}
                          className="w-full text-left text-xs text-indigo-600 hover:text-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:text-indigo-300 dark:hover:text-indigo-200"
                        >
                          {citation}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <button
                    className="flex-1 inline-flex items-center justify-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
                    onClick={handleApply}
                  >
                    <Check className="h-4 w-4" />
                    Apply to document
                  </button>
                  <button
                    className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                    onClick={() => setResult(null)}
                  >
                    Clear
                  </button>
                </div>
              </section>
            )}
          </div>
        </div>
      )}
    </>
  )
}

export default EnhancedAIWritingTools
