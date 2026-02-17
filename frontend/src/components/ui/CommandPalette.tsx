import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Search,
  FolderKanban,
  FileText,
  Plus,
} from 'lucide-react'
import { projectsAPI } from '../../services/api'
import { ProjectSummary } from '../../types'

interface RecentPaper {
  id: string
  title: string
  projectId: string
  projectTitle: string
}

interface CommandResult {
  id: string
  label: string
  description?: string
  icon: React.ReactNode
  category: 'projects' | 'papers' | 'actions'
  onSelect: () => void
}

const RECENT_PAPERS_KEY = 'scholarhub-recent-papers'

export function getRecentPapers(): RecentPaper[] {
  try {
    const stored = localStorage.getItem(RECENT_PAPERS_KEY)
    return stored ? JSON.parse(stored) : []
  } catch {
    return []
  }
}

export function trackRecentPaper(paper: RecentPaper) {
  const existing = getRecentPapers().filter((p) => p.id !== paper.id)
  const updated = [paper, ...existing].slice(0, 5)
  localStorage.setItem(RECENT_PAPERS_KEY, JSON.stringify(updated))
}

interface CommandPaletteProps {
  isOpen: boolean
  onClose: () => void
}

const CommandPalette: React.FC<CommandPaletteProps> = ({ isOpen, onClose }) => {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const { data: projectsData } = useQuery({
    queryKey: ['projects-command-palette'],
    queryFn: async () => {
      const response = await projectsAPI.list({ limit: 50 })
      return response.data
    },
    enabled: isOpen,
    staleTime: 30000,
  })

  const projects: ProjectSummary[] = projectsData?.projects ?? []
  const recentPapers = useMemo(() => (isOpen ? getRecentPapers() : []), [isOpen])

  const results = useMemo(() => {
    const items: CommandResult[] = []
    const q = query.toLowerCase().trim()

    // Actions (always shown, filtered by query)
    const actions: CommandResult[] = [
      {
        id: 'action-create-project',
        label: 'Create Project',
        description: 'Start a new research project',
        icon: <Plus className="h-4 w-4" />,
        category: 'actions',
        onSelect: () => {
          onClose()
          navigate('/projects')
          // Dispatch a custom event so ProjectsHome can open the modal
          setTimeout(() => window.dispatchEvent(new CustomEvent('open-create-project')), 100)
        },
      },
      {
        id: 'action-search-papers',
        label: 'Search Papers',
        description: 'Find academic papers',
        icon: <Search className="h-4 w-4" />,
        category: 'actions',
        onSelect: () => {
          onClose()
          // Navigate to first project's library discover if available
          if (projects.length > 0) {
            const p = projects[0]
            navigate(`/projects/${p.url_id || p.id}/library/discover`)
          }
        },
      },
    ]

    // Filter projects
    const matchedProjects = q
      ? projects.filter((p) => p.title.toLowerCase().includes(q))
      : projects.slice(0, 5)

    for (const p of matchedProjects) {
      const urlId = p.url_id || p.id
      items.push({
        id: `project-${p.id}`,
        label: p.title,
        description: p.status ? `Status: ${p.status}` : undefined,
        icon: <FolderKanban className="h-4 w-4" />,
        category: 'projects',
        onSelect: () => {
          onClose()
          navigate(`/projects/${urlId}/overview`)
        },
      })
    }

    // Recent papers
    const matchedPapers = q
      ? recentPapers.filter((p) => p.title.toLowerCase().includes(q))
      : recentPapers

    for (const p of matchedPapers) {
      items.push({
        id: `paper-${p.id}`,
        label: p.title,
        description: p.projectTitle,
        icon: <FileText className="h-4 w-4" />,
        category: 'papers',
        onSelect: () => {
          onClose()
          navigate(`/projects/${p.projectId}/papers/${p.id}`)
        },
      })
    }

    // Actions
    const matchedActions = q
      ? actions.filter((a) => a.label.toLowerCase().includes(q) || a.description?.toLowerCase().includes(q))
      : actions

    items.push(...matchedActions)

    return items
  }, [query, projects, recentPapers, navigate, onClose])

  // Group results by category
  const grouped = useMemo(() => {
    const groups: { label: string; items: CommandResult[] }[] = []
    const projectItems = results.filter((r) => r.category === 'projects')
    const paperItems = results.filter((r) => r.category === 'papers')
    const actionItems = results.filter((r) => r.category === 'actions')

    if (projectItems.length > 0) groups.push({ label: 'Projects', items: projectItems })
    if (paperItems.length > 0) groups.push({ label: 'Recent Papers', items: paperItems })
    if (actionItems.length > 0) groups.push({ label: 'Actions', items: actionItems })
    return groups
  }, [results])

  // Reset state on open/close
  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isOpen])

  // Scroll selected item into view
  useEffect(() => {
    if (!listRef.current) return
    const selected = listRef.current.querySelector('[data-selected="true"]')
    if (selected) {
      selected.scrollIntoView({ block: 'nearest' })
    }
  }, [selectedIndex])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex((prev) => (prev + 1) % results.length)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex((prev) => (prev - 1 + results.length) % results.length)
      } else if (e.key === 'Enter') {
        e.preventDefault()
        const selected = results[selectedIndex]
        if (selected) selected.onSelect()
      } else if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    },
    [results, selectedIndex, onClose]
  )

  // Clamp selected index when results change
  useEffect(() => {
    if (selectedIndex >= results.length) {
      setSelectedIndex(Math.max(0, results.length - 1))
    }
  }, [results.length, selectedIndex])

  if (!isOpen) return null

  let flatIndex = -1

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] animate-in fade-in duration-150"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />

      {/* Palette */}
      <div
        className="relative w-full max-w-lg rounded-xl border border-gray-200 bg-white shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150 dark:border-slate-700 dark:bg-slate-800"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 border-b border-gray-200 px-4 py-3 dark:border-slate-700">
          <Search className="h-5 w-5 text-gray-400 dark:text-slate-500" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setSelectedIndex(0)
            }}
            onKeyDown={handleKeyDown}
            placeholder="Search projects, papers, actions..."
            className="flex-1 bg-transparent text-sm text-gray-900 placeholder-gray-400 outline-none dark:text-slate-100 dark:placeholder-slate-500"
          />
          <kbd className="hidden sm:inline-flex items-center rounded border border-gray-200 px-1.5 py-0.5 text-[10px] font-medium text-gray-400 dark:border-slate-600 dark:text-slate-500">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-80 overflow-y-auto py-2">
          {results.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-gray-500 dark:text-slate-400">
              No results found
            </div>
          ) : (
            grouped.map((group) => (
              <div key={group.label}>
                <div className="px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-gray-400 dark:text-slate-500">
                  {group.label}
                </div>
                {group.items.map((item) => {
                  flatIndex++
                  const idx = flatIndex
                  const isSelected = idx === selectedIndex
                  return (
                    <button
                      key={item.id}
                      type="button"
                      data-selected={isSelected}
                      className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors ${
                        isSelected
                          ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300'
                          : 'text-gray-700 hover:bg-gray-50 dark:text-slate-300 dark:hover:bg-slate-700/50'
                      }`}
                      onClick={item.onSelect}
                      onMouseEnter={() => setSelectedIndex(idx)}
                    >
                      <span className={`flex-shrink-0 ${isSelected ? 'text-indigo-500 dark:text-indigo-400' : 'text-gray-400 dark:text-slate-500'}`}>
                        {item.icon}
                      </span>
                      <div className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{item.label}</span>
                        {item.description && (
                          <span className="block truncate text-xs text-gray-500 dark:text-slate-400">
                            {item.description}
                          </span>
                        )}
                      </div>
                    </button>
                  )
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer hint */}
        <div className="flex items-center gap-4 border-t border-gray-200 px-4 py-2 text-[11px] text-gray-400 dark:border-slate-700 dark:text-slate-500">
          <span className="inline-flex items-center gap-1">
            <kbd className="rounded border border-gray-200 px-1 py-0.5 text-[10px] dark:border-slate-600">↑↓</kbd>
            Navigate
          </span>
          <span className="inline-flex items-center gap-1">
            <kbd className="rounded border border-gray-200 px-1 py-0.5 text-[10px] dark:border-slate-600">↵</kbd>
            Select
          </span>
          <span className="inline-flex items-center gap-1">
            <kbd className="rounded border border-gray-200 px-1 py-0.5 text-[10px] dark:border-slate-600">esc</kbd>
            Close
          </span>
        </div>
      </div>
    </div>
  )
}

export default CommandPalette
