import React, { useState, useCallback, useMemo } from 'react'
import { X, ListTree, ChevronRight, ChevronDown, FileText } from 'lucide-react'
import type { EditorView } from '@codemirror/view'
import type { OutlineEntry } from '../hooks/useDocumentOutline'

interface OutlinePanelProps {
  outline: OutlineEntry[]
  viewRef: React.MutableRefObject<EditorView | null>
  onClose: () => void
}

// Build a tree structure from the flat outline entries
interface TreeNode {
  entry: OutlineEntry
  children: TreeNode[]
}

function buildTree(entries: OutlineEntry[]): TreeNode[] {
  const root: TreeNode[] = []
  const stack: { node: TreeNode; level: number }[] = []

  for (const entry of entries) {
    const node: TreeNode = { entry, children: [] }

    // Pop from stack until we find a parent with a lower level
    while (stack.length > 0 && stack[stack.length - 1].level >= entry.level) {
      stack.pop()
    }

    if (stack.length === 0) {
      root.push(node)
    } else {
      stack[stack.length - 1].node.children.push(node)
    }

    stack.push({ node, level: entry.level })
  }

  return root
}

const LEVEL_STYLES: Record<number, string> = {
  0: 'font-bold text-sm',       // \part
  1: 'font-bold text-sm',       // \chapter
  2: 'font-semibold text-sm',   // \section
  3: 'text-sm',                 // \subsection
  4: 'text-xs',                 // \subsubsection
  5: 'text-xs text-slate-500 dark:text-slate-400',   // \paragraph
  6: 'text-xs text-slate-400 dark:text-slate-500',   // \subparagraph
}

const OutlineNode: React.FC<{
  node: TreeNode
  depth: number
  onNavigate: (entry: OutlineEntry) => void
}> = ({ node, depth, onNavigate }) => {
  const [expanded, setExpanded] = useState(true)
  const hasChildren = node.children.length > 0

  return (
    <div>
      <button
        type="button"
        className={`group flex w-full items-center gap-1 rounded-md px-2 py-1 text-left transition-colors hover:bg-slate-100 dark:hover:bg-slate-700/60 ${
          LEVEL_STYLES[node.entry.level] ?? 'text-sm'
        }`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => onNavigate(node.entry)}
      >
        {hasChildren ? (
          <span
            className="flex h-4 w-4 shrink-0 items-center justify-center text-slate-400 dark:text-slate-500"
            onClick={(e) => {
              e.stopPropagation()
              setExpanded(!expanded)
            }}
          >
            {expanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </span>
        ) : (
          <span className="h-4 w-4 shrink-0" />
        )}
        <span className="truncate text-slate-700 dark:text-slate-200">
          {node.entry.title || `(${node.entry.command})`}
        </span>
        <span className="ml-auto shrink-0 text-[10px] text-slate-400 opacity-0 transition-opacity group-hover:opacity-100 dark:text-slate-500">
          L{node.entry.line}
        </span>
      </button>
      {hasChildren && expanded && (
        <div>
          {node.children.map((child, i) => (
            <OutlineNode
              key={`${child.entry.from}-${i}`}
              node={child}
              depth={depth + 1}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export const OutlinePanel: React.FC<OutlinePanelProps> = ({
  outline,
  viewRef,
  onClose,
}) => {
  const tree = useMemo(() => buildTree(outline), [outline])

  const handleNavigate = useCallback(
    (entry: OutlineEntry) => {
      const view = viewRef.current
      if (!view) return
      view.dispatch({
        selection: { anchor: entry.from },
        scrollIntoView: true,
      })
      view.focus()
    },
    [viewRef],
  )

  return (
    <div className="fixed inset-y-0 left-0 z-50 flex w-[280px] flex-col border-r border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2.5 dark:border-slate-700">
        <div className="flex items-center gap-2">
          <ListTree className="h-4 w-4 text-slate-500 dark:text-slate-400" />
          <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Outline
          </span>
          {outline.length > 0 && (
            <span className="rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
              {outline.length}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          aria-label="Close outline"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-1 py-2">
        {tree.length > 0 ? (
          tree.map((node, i) => (
            <OutlineNode
              key={`${node.entry.from}-${i}`}
              node={node}
              depth={0}
              onNavigate={handleNavigate}
            />
          ))
        ) : (
          <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
            <FileText className="h-8 w-8 text-slate-300 dark:text-slate-600" />
            <p className="text-sm text-slate-500 dark:text-slate-400">
              No sections found
            </p>
            <p className="text-xs text-slate-400 dark:text-slate-500">
              Add \section, \subsection, etc. to see the document outline
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
