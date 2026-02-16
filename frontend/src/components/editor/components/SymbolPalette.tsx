import React, { useState, useMemo } from 'react'
import { LATEX_SYMBOLS, SYMBOL_CATEGORIES } from '../data/latexSymbols'

interface SymbolPaletteProps {
  onInsertSymbol: (latex: string) => void
  onClose: () => void
}

export const SymbolPalette: React.FC<SymbolPaletteProps> = ({
  onInsertSymbol,
  onClose,
}) => {
  const [search, setSearch] = useState('')
  const [activeCategory, setActiveCategory] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return LATEX_SYMBOLS.filter((s) => {
      if (activeCategory && s.category !== activeCategory) return false
      if (q && !s.name.toLowerCase().includes(q) && !s.latex.toLowerCase().includes(q))
        return false
      return true
    })
  }, [search, activeCategory])

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-[280px] flex-col border-l border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2.5 dark:border-slate-700">
        <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
          Symbols
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          aria-label="Close symbols"
        >
          <span className="text-lg leading-none">&times;</span>
        </button>
      </div>

      {/* Search */}
      <div className="border-b border-slate-200 px-3 py-2 dark:border-slate-700">
        <div className="relative">
          <svg
            className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z"
            />
          </svg>
          <input
            type="text"
            placeholder="Search symbols..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-md border border-slate-200 bg-white py-1.5 pl-7 pr-2 text-xs text-slate-700 placeholder-slate-400 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:placeholder-slate-500 dark:focus:border-blue-500"
          />
        </div>
      </div>

      {/* Category pills */}
      <div className="flex gap-1 overflow-x-auto border-b border-slate-200 px-3 py-2 dark:border-slate-700">
        <button
          type="button"
          onClick={() => setActiveCategory(null)}
          className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors ${
            activeCategory === null
              ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
              : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
          }`}
        >
          All
        </button>
        {SYMBOL_CATEGORIES.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setActiveCategory(cat === activeCategory ? null : cat)}
            className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors ${
              activeCategory === cat
                ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Symbol grid */}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        {filtered.length > 0 ? (
          <div className="grid grid-cols-7 gap-1">
            {filtered.map((sym) => (
              <button
                key={sym.latex}
                type="button"
                title={`${sym.name}\n${sym.latex}`}
                onClick={() => onInsertSymbol(sym.latex)}
                className="flex h-9 w-9 items-center justify-center rounded text-base text-slate-700 transition-colors hover:bg-blue-50 hover:text-blue-700 dark:text-slate-200 dark:hover:bg-blue-900/30 dark:hover:text-blue-300"
              >
                {sym.unicode}
              </button>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              No symbols found
            </p>
            <p className="text-xs text-slate-400 dark:text-slate-500">
              Try a different search term or category
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
