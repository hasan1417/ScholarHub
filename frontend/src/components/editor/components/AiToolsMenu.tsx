import React, { useState, useCallback } from 'react'
import { Loader2, Sparkles, Type, FileText, Lightbulb, Book } from 'lucide-react'

interface AiToolsMenuProps {
  readOnly: boolean
  hasTextSelected: boolean
  aiActionLoading: string | null
  onAiAction: (action: string, tone?: string) => void
}

export const AiToolsMenu: React.FC<AiToolsMenuProps> = ({
  readOnly,
  hasTextSelected,
  aiActionLoading,
  onAiAction,
}) => {
  const [menuOpen, setMenuOpen] = useState(false)
  const [toneMenuOpen, setToneMenuOpen] = useState(false)
  const [toneMenuAnchor, setToneMenuAnchor] = useState<HTMLElement | null>(null)

  const handleToneButtonClick = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    if (readOnly || !hasTextSelected) return
    setToneMenuAnchor(event.currentTarget)
    setToneMenuOpen(true)
  }, [readOnly, hasTextSelected])

  const handleToneSelect = useCallback(async (tone: string) => {
    setToneMenuOpen(false)
    await onAiAction('tone', tone)
    setToneMenuAnchor(null)
  }, [onAiAction])

  return (
    <>
      <div className="relative">
        <button
          type="button"
          onClick={() => !aiActionLoading && setMenuOpen(!menuOpen)}
          disabled={readOnly || (!hasTextSelected && !aiActionLoading)}
          className={`rounded p-1.5 transition-colors disabled:opacity-30 ${
            menuOpen || aiActionLoading
              ? 'bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-300'
              : 'text-slate-500 hover:bg-slate-200 dark:text-slate-400 dark:hover:bg-slate-700'
          }`}
          title={aiActionLoading ? `Processing: ${aiActionLoading}...` : hasTextSelected ? 'AI text tools' : 'Select text first'}
        >
          {aiActionLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="h-4 w-4" />
          )}
        </button>
        {(menuOpen || aiActionLoading) && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => !aiActionLoading && setMenuOpen(false)} />
            <div className="absolute right-0 top-full z-50 mt-1 min-w-[150px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-600 dark:bg-slate-800">
              <button
                onClick={() => { if (!aiActionLoading) { onAiAction('paraphrase') } }}
                disabled={!!aiActionLoading}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs ${aiActionLoading === 'paraphrase' ? 'bg-violet-50 text-violet-700 dark:bg-violet-500/20 dark:text-violet-300' : aiActionLoading ? 'opacity-40 cursor-not-allowed text-slate-400 dark:text-slate-500' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'}`}
              >
                {aiActionLoading === 'paraphrase' ? <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-500" /> : <Sparkles className="h-3.5 w-3.5 text-violet-500" />}
                Paraphrase
              </button>
              <button
                onClick={() => { if (!aiActionLoading) { onAiAction('summarize') } }}
                disabled={!!aiActionLoading}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs ${aiActionLoading === 'summarize' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300' : aiActionLoading ? 'opacity-40 cursor-not-allowed text-slate-400 dark:text-slate-500' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'}`}
              >
                {aiActionLoading === 'summarize' ? <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-500" /> : <FileText className="h-3.5 w-3.5 text-emerald-500" />}
                Summarize
              </button>
              <button
                onClick={() => { if (!aiActionLoading) { onAiAction('explain') } }}
                disabled={!!aiActionLoading}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs ${aiActionLoading === 'explain' ? 'bg-amber-50 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300' : aiActionLoading ? 'opacity-40 cursor-not-allowed text-slate-400 dark:text-slate-500' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'}`}
              >
                {aiActionLoading === 'explain' ? <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-500" /> : <Lightbulb className="h-3.5 w-3.5 text-amber-500" />}
                Explain
              </button>
              <button
                onClick={() => { if (!aiActionLoading) { onAiAction('synonyms') } }}
                disabled={!!aiActionLoading}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs ${aiActionLoading === 'synonyms' ? 'bg-blue-50 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300' : aiActionLoading ? 'opacity-40 cursor-not-allowed text-slate-400 dark:text-slate-500' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'}`}
              >
                {aiActionLoading === 'synonyms' ? <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" /> : <Book className="h-3.5 w-3.5 text-blue-500" />}
                Synonyms
              </button>
              <div className="my-1 border-t border-slate-200 dark:border-slate-600" />
              <button
                onClick={(e) => { if (!aiActionLoading) handleToneButtonClick(e) }}
                disabled={!!aiActionLoading}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs ${aiActionLoading?.startsWith('tone_') ? 'bg-rose-50 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300' : aiActionLoading ? 'opacity-40 cursor-not-allowed text-slate-400 dark:text-slate-500' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'}`}
              >
                {aiActionLoading?.startsWith('tone_') ? <Loader2 className="h-3.5 w-3.5 animate-spin text-rose-500" /> : <Type className="h-3.5 w-3.5 text-rose-500" />}
                Change Tone...
              </button>
            </div>
          </>
        )}
      </div>

      {/* Tone Selector Menu */}
      {(toneMenuOpen || aiActionLoading?.startsWith('tone_')) && toneMenuAnchor && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => {
              if (!aiActionLoading) {
                setToneMenuOpen(false)
                setToneMenuAnchor(null)
              }
            }}
          />
          <div
            className="fixed z-50 min-w-[160px] rounded-lg border border-slate-200 bg-white shadow-xl dark:border-slate-600 dark:bg-slate-800"
            style={{
              top: `${toneMenuAnchor.getBoundingClientRect().bottom + 8}px`,
              left: `${toneMenuAnchor.getBoundingClientRect().left}px`,
            }}
          >
            <div className="p-2">
              <div className="mb-2 px-2 text-xs font-semibold text-slate-600 dark:text-slate-400">
                {aiActionLoading?.startsWith('tone_') ? 'Processing...' : 'Select Tone'}
              </div>
              {['formal', 'casual', 'academic', 'friendly', 'professional'].map((tone) => (
                <button
                  key={tone}
                  onClick={() => !aiActionLoading && handleToneSelect(tone)}
                  disabled={!!aiActionLoading}
                  className={`flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm transition-colors ${
                    aiActionLoading === `tone_${tone}`
                      ? 'bg-rose-50 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300'
                      : aiActionLoading
                      ? 'cursor-not-allowed text-slate-400 opacity-40 dark:text-slate-500'
                      : 'text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'
                  }`}
                >
                  {aiActionLoading === `tone_${tone}` && <Loader2 className="h-3.5 w-3.5 animate-spin text-rose-500" />}
                  {tone.charAt(0).toUpperCase() + tone.slice(1)}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  )
}
