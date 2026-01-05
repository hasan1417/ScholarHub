import React from 'react'
import { Plus, Minus, Equal } from 'lucide-react'
import { DiffLine, DiffStats } from '../../services/api'

interface HistoryDiffViewProps {
  diffLines: DiffLine[]
  stats: DiffStats
  className?: string
}

const HistoryDiffView: React.FC<HistoryDiffViewProps> = ({
  diffLines,
  stats,
  className = ''
}) => {
  const getLineClass = (type: DiffLine['type']) => {
    switch (type) {
      case 'added':
        return 'bg-green-50 dark:bg-green-900/40 border-l-4 border-green-500'
      case 'deleted':
        return 'bg-red-50 dark:bg-red-900/40 border-l-4 border-red-500'
      default:
        return 'bg-gray-50 dark:bg-slate-800/50 border-l-4 border-gray-200 dark:border-slate-600'
    }
  }

  const getLineTextClass = (type: DiffLine['type']) => {
    switch (type) {
      case 'added':
        return 'text-green-800 dark:text-green-300'
      case 'deleted':
        return 'text-red-800 dark:text-red-300 line-through'
      default:
        return 'text-gray-600 dark:text-slate-400'
    }
  }

  const getLineIcon = (type: DiffLine['type']) => {
    switch (type) {
      case 'added':
        return <Plus size={14} className="text-green-600 dark:text-green-400 flex-shrink-0" />
      case 'deleted':
        return <Minus size={14} className="text-red-600 dark:text-red-400 flex-shrink-0" />
      default:
        return <Equal size={14} className="text-gray-400 dark:text-slate-500 flex-shrink-0" />
    }
  }

  if (diffLines.length === 0) {
    return (
      <div className={`flex items-center justify-center p-8 text-gray-500 dark:text-slate-400 ${className}`}>
        No differences found between these versions.
      </div>
    )
  }

  return (
    <div className={`bg-white dark:bg-slate-900 rounded-lg border border-gray-200 dark:border-slate-700 overflow-hidden ${className}`}>
      {/* Stats Header */}
      <div className="px-4 py-2 bg-gray-50 dark:bg-slate-800 border-b border-gray-200 dark:border-slate-700 flex items-center gap-4 text-sm">
        <span className="flex items-center gap-1 text-green-600 dark:text-green-400">
          <Plus size={14} />
          {stats.additions} added
        </span>
        <span className="flex items-center gap-1 text-red-600 dark:text-red-400">
          <Minus size={14} />
          {stats.deletions} deleted
        </span>
        <span className="text-gray-500 dark:text-slate-500">
          {stats.unchanged} unchanged
        </span>
      </div>

      {/* Diff Content */}
      <div className="max-h-[400px] overflow-y-auto font-mono text-sm">
        {diffLines.map((line, index) => (
          <div
            key={index}
            className={`flex items-start px-3 py-1 ${getLineClass(line.type)}`}
          >
            {/* Line Number */}
            <span className="w-10 text-right pr-3 text-gray-400 dark:text-slate-500 select-none flex-shrink-0">
              {line.line_number ?? ''}
            </span>

            {/* Icon */}
            <span className="w-5 flex items-center justify-center">
              {getLineIcon(line.type)}
            </span>

            {/* Content */}
            <span className={`flex-1 pl-2 whitespace-pre-wrap break-all ${getLineTextClass(line.type)}`}>
              {line.content || '\u00A0'}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default HistoryDiffView
