import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileText, Loader2, Search, X, Check, BookOpen } from 'lucide-react'
import { researchPapersAPI, projectReferencesAPI } from '../../services/api'
import { ProjectReferenceSuggestion, ResearchPaper } from '../../types'
import { getPaperUrlId } from '../../utils/urlId'
import { makeBibKey } from '../editor/utils/bibKey'

interface CiteInPaperModalProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
  projectUrlId: string
  reference: ProjectReferenceSuggestion
}

export default function CiteInPaperModal({
  isOpen,
  onClose,
  projectId,
  projectUrlId,
  reference,
}: CiteInPaperModalProps) {
  const navigate = useNavigate()
  const [papers, setPapers] = useState<ResearchPaper[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [attaching, setAttaching] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const citedPaperIds = useMemo(
    () => new Set((reference.papers || []).map((p) => p.paper_id)),
    [reference.papers]
  )

  useEffect(() => {
    if (!isOpen) {
      setSearch('')
      return
    }
    let cancelled = false
    const load = async () => {
      setIsLoading(true)
      try {
        const res = await researchPapersAPI.getPapers({ projectId, limit: 200 })
        if (!cancelled) setPapers(res.data?.papers || [])
      } catch {
        if (!cancelled) setPapers([])
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [isOpen, projectId])

  const filtered = useMemo(() => {
    if (!search.trim()) return papers
    const needle = search.toLowerCase()
    return papers.filter((p) => p.title.toLowerCase().includes(needle))
  }, [papers, search])

  const handleCite = async (paper: ResearchPaper) => {
    const alreadyCited = citedPaperIds.has(paper.id)
    const bibKey = makeBibKey(reference.reference || {})
    const isLatex = paper.paper_type === 'latex'

    if (!alreadyCited) {
      setAttaching(paper.id)
      try {
        await projectReferencesAPI.attachToPaper(projectId, reference.id, paper.id)
      } catch {
        // Ignore — may already be attached
      } finally {
        setAttaching(null)
      }
    }

    onClose()
    const editorPath = `/projects/${projectUrlId}/papers/${getPaperUrlId(paper)}/editor`
    navigate(isLatex ? `${editorPath}?insertCite=${encodeURIComponent(bibKey)}` : editorPath)
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-5 dark:border-slate-800">
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">Cite in Paper</h2>
            <p className="mt-0.5 truncate text-sm text-gray-500 dark:text-slate-400">
              {reference.reference?.title || 'Untitled reference'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Search */}
        <div className="border-b border-gray-100 px-6 py-4 dark:border-slate-800">
          <div className="relative">
            <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-slate-500" />
            <input
              type="text"
              className="w-full rounded-xl border border-gray-200 bg-gray-50 py-2.5 pl-10 pr-4 text-sm text-gray-900 placeholder-gray-400 transition focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:bg-slate-800"
              placeholder="Search papers..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        {/* Paper list */}
        <div className="max-h-[400px] overflow-y-auto px-6 py-4">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-16 text-sm text-gray-500 dark:text-slate-400">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600 dark:text-indigo-400" />
              <p className="mt-3">Loading papers...</p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <BookOpen className="h-10 w-10 text-gray-300 dark:text-slate-600" />
              <p className="mt-3 text-sm text-gray-500 dark:text-slate-400">
                {papers.length === 0 ? 'No papers in this project yet' : 'No papers match your search'}
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              {filtered.map((paper) => {
                const isCited = citedPaperIds.has(paper.id)
                const isLatex = paper.paper_type === 'latex'
                const isAttaching = attaching === paper.id

                return (
                  <li
                    key={paper.id}
                    className="group flex items-center gap-3 rounded-xl border-2 border-gray-100 bg-gray-50/50 p-4 transition-all hover:border-gray-200 hover:bg-gray-50 dark:border-slate-800 dark:bg-slate-800/50 dark:hover:border-slate-700 dark:hover:bg-slate-800"
                  >
                    <FileText className="h-5 w-5 flex-shrink-0 text-gray-400 dark:text-slate-500" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-gray-900 dark:text-slate-100">
                        {paper.title || 'Untitled'}
                      </p>
                      <div className="mt-1 flex items-center gap-2 text-xs">
                        <span className="rounded bg-gray-200 px-1.5 py-0.5 font-medium text-gray-600 dark:bg-slate-700 dark:text-slate-300">
                          {isLatex ? 'LaTeX' : 'Rich Text'}
                        </span>
                        {isCited && (
                          <span className="inline-flex items-center gap-1 text-green-600 dark:text-green-400">
                            <Check className="h-3 w-3" />
                            Already cited
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => handleCite(paper)}
                      disabled={isAttaching}
                      className="flex-shrink-0 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-700 disabled:opacity-50 dark:bg-indigo-500 dark:hover:bg-indigo-400"
                    >
                      {isAttaching ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : isCited ? (
                        'Open'
                      ) : (
                        'Cite'
                      )}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-100 bg-gray-50 px-6 py-3 dark:border-slate-800 dark:bg-slate-800/50">
          <p className="text-xs text-gray-400 dark:text-slate-500">
            {papers.length} paper{papers.length !== 1 ? 's' : ''} in project
          </p>
        </div>
      </div>
    </div>
  )
}
