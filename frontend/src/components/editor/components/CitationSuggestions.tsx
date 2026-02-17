import React, { useState, useEffect, useRef, useCallback } from 'react'
import { BookOpen, ChevronDown, ChevronRight, Plus, Loader2 } from 'lucide-react'
import { projectReferencesAPI } from '../../../services/api'
import type { CitationSuggestion } from '../../../types'

interface CitationSuggestionsProps {
  projectId: string
  currentText: string
  onInsertCitation: (citationKey: string) => void
}

const CitationSuggestions: React.FC<CitationSuggestionsProps> = ({
  projectId,
  currentText,
  onInsertCitation,
}) => {
  const [collapsed, setCollapsed] = useState(false)
  const [suggestions, setSuggestions] = useState<CitationSuggestion[]>([])
  const [loading, setLoading] = useState(false)
  const [lastQueriedText, setLastQueriedText] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const fetchSuggestions = useCallback(async (text: string) => {
    if (!text || text.trim().length < 20) {
      setSuggestions([])
      return
    }

    // Cancel previous in-flight request
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    try {
      const res = await projectReferencesAPI.suggestCitations(projectId, text.trim(), 3)
      if (!controller.signal.aborted) {
        setSuggestions(res.data.suggestions)
        setLastQueriedText(text)
      }
    } catch (err: any) {
      if (err?.code !== 'ERR_CANCELED' && !controller.signal.aborted) {
        setSuggestions([])
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false)
      }
    }
  }, [projectId])

  // Debounce text changes (2 seconds)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)

    // Skip if text hasn't changed meaningfully
    if (currentText === lastQueriedText) return
    if (!currentText || currentText.trim().length < 20) {
      setSuggestions([])
      return
    }

    debounceRef.current = setTimeout(() => {
      fetchSuggestions(currentText)
    }, 2000)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [currentText, fetchSuggestions, lastQueriedText])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort()
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  if (suggestions.length === 0 && !loading) return null

  const formatAuthors = (authors: string[]) => {
    if (!authors || authors.length === 0) return 'Unknown'
    if (authors.length === 1) return authors[0]
    if (authors.length === 2) return `${authors[0]} & ${authors[1]}`
    return `${authors[0]} et al.`
  }

  const similarityColor = (sim: number) => {
    if (sim >= 0.6) return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
    if (sim >= 0.4) return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
    return 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'
  }

  return (
    <div className="border-t border-slate-200 bg-slate-50/80 dark:border-slate-700 dark:bg-slate-900/60">
      <button
        onClick={() => setCollapsed(prev => !prev)}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
      >
        {collapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        <BookOpen className="h-3 w-3" />
        <span>Suggested Citations</span>
        {loading && <Loader2 className="ml-1 h-3 w-3 animate-spin" />}
        {!loading && suggestions.length > 0 && (
          <span className="ml-1 rounded-full bg-indigo-100 px-1.5 text-[10px] font-semibold text-indigo-600 dark:bg-indigo-900/40 dark:text-indigo-300">
            {suggestions.length}
          </span>
        )}
      </button>

      {!collapsed && (
        <div className="space-y-1 px-3 pb-2">
          {suggestions.map((s) => (
            <div
              key={s.reference_id}
              className="group flex items-start gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs transition-colors hover:border-indigo-300 dark:border-slate-700 dark:bg-slate-800/60 dark:hover:border-indigo-600"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-1.5">
                  <span className="font-medium text-slate-700 dark:text-slate-200">
                    {formatAuthors(s.authors)}
                  </span>
                  {s.year && (
                    <span className="text-slate-500 dark:text-slate-400">
                      ({s.year})
                    </span>
                  )}
                </div>
                <p className="mt-0.5 line-clamp-1 text-slate-500 dark:text-slate-400">
                  {s.title}
                </p>
              </div>
              <span className={`mt-0.5 shrink-0 rounded px-1 py-0.5 text-[10px] font-medium ${similarityColor(s.similarity)}`}>
                {Math.round(s.similarity * 100)}%
              </span>
              <button
                onClick={() => onInsertCitation(s.citation_key)}
                className="mt-0.5 shrink-0 rounded p-0.5 text-slate-400 opacity-0 transition-all hover:bg-indigo-100 hover:text-indigo-600 group-hover:opacity-100 dark:hover:bg-indigo-900/40 dark:hover:text-indigo-300"
                title={`Insert \\cite{${s.citation_key}}`}
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default CitationSuggestions
