import { useState, useCallback, useMemo } from 'react'
import { Plus, X, FileText, GripVertical } from 'lucide-react'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  horizontalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

interface FileSelectorProps {
  files: string[]
  activeFile: string
  onSelectFile: (filename: string) => void
  onCreateFile: (filename: string) => void
  onDeleteFile: (filename: string) => void
  onReorderFiles?: (reordered: string[]) => void
  readOnly?: boolean
}

// Individual sortable tab
const SortableTab: React.FC<{
  file: string
  isActive: boolean
  readOnly?: boolean
  onSelect: () => void
  onDelete: () => void
}> = ({ file, isActive, readOnly, onSelect, onDelete }) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: file })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 10 : undefined,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`group flex items-center gap-0.5 rounded px-1.5 py-0.5 text-xs font-medium transition-colors cursor-pointer select-none ${
        isActive
          ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white'
          : 'text-slate-500 hover:bg-slate-200/80 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-700/60 dark:hover:text-slate-300'
      } ${isDragging ? 'opacity-80 shadow-lg ring-1 ring-indigo-400/50' : ''}`}
      onClick={onSelect}
    >
      {!readOnly && (
        <span
          {...attributes}
          {...listeners}
          className="cursor-grab rounded p-0.5 text-slate-300 hover:text-slate-500 active:cursor-grabbing dark:text-slate-600 dark:hover:text-slate-400"
          onClick={(e) => e.stopPropagation()}
        >
          <GripVertical className="h-3 w-3" />
        </span>
      )}
      <FileText className="h-3 w-3 flex-shrink-0" />
      <span className="whitespace-nowrap">{file}</span>
      {file !== 'main.tex' && !readOnly && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            if (confirm(`Delete ${file}?`)) onDelete()
          }}
          className="ml-0.5 hidden rounded p-0.5 text-slate-400 transition-colors hover:bg-rose-100 hover:text-rose-500 group-hover:inline-flex dark:hover:bg-rose-900/30 dark:hover:text-rose-400"
          title={`Delete ${file}`}
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  )
}

export const FileSelector: React.FC<FileSelectorProps> = ({
  files,
  activeFile,
  onSelectFile,
  onCreateFile,
  onDeleteFile,
  onReorderFiles,
  readOnly,
}) => {
  const [isCreating, setIsCreating] = useState(false)
  const [newFileName, setNewFileName] = useState('')

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  )

  const fileIds = useMemo(() => files, [files])

  const handleCreate = useCallback(() => {
    let name = newFileName.trim()
    if (!name) return
    if (!name.endsWith('.tex')) name += '.tex'
    if (files.includes(name)) {
      setNewFileName('')
      setIsCreating(false)
      return
    }
    onCreateFile(name)
    setNewFileName('')
    setIsCreating(false)
  }, [newFileName, files, onCreateFile])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') handleCreate()
      else if (e.key === 'Escape') {
        setIsCreating(false)
        setNewFileName('')
      }
    },
    [handleCreate]
  )

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event
      if (!over || active.id === over.id) return
      const oldIndex = files.indexOf(active.id as string)
      const newIndex = files.indexOf(over.id as string)
      if (oldIndex === -1 || newIndex === -1) return
      const reordered = [...files]
      const [moved] = reordered.splice(oldIndex, 1)
      reordered.splice(newIndex, 0, moved)
      onReorderFiles?.(reordered)
    },
    [files, onReorderFiles]
  )

  if (files.length <= 1 && !isCreating) {
    return (
      <div className="flex items-center gap-1 border-b border-slate-200 bg-slate-100/80 px-2 py-1 dark:border-slate-700 dark:bg-slate-900">
        <div className="flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium text-slate-600 dark:text-slate-300">
          <FileText className="h-3 w-3" />
          <span>main.tex</span>
        </div>
        {!readOnly && (
          <button
            type="button"
            onClick={() => setIsCreating(true)}
            className="rounded p-0.5 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
            title="Add file"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        )}
        {isCreating && (
          <input
            type="text"
            autoFocus
            value={newFileName}
            onChange={(e) => setNewFileName(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => {
              if (newFileName.trim()) handleCreate()
              else setIsCreating(false)
            }}
            placeholder="filename.tex"
            className="ml-1 w-28 rounded border border-slate-300 bg-white px-1.5 py-0.5 text-xs outline-none focus:border-indigo-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
          />
        )}
      </div>
    )
  }

  return (
    <div className="flex items-center gap-0.5 overflow-x-auto border-b border-slate-200 bg-slate-100/80 px-2 py-1 dark:border-slate-700 dark:bg-slate-900">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={fileIds} strategy={horizontalListSortingStrategy}>
          {files.map((file) => (
            <SortableTab
              key={file}
              file={file}
              isActive={file === activeFile}
              readOnly={readOnly}
              onSelect={() => onSelectFile(file)}
              onDelete={() => onDeleteFile(file)}
            />
          ))}
        </SortableContext>
      </DndContext>
      {!readOnly && (
        <>
          {isCreating ? (
            <input
              type="text"
              autoFocus
              value={newFileName}
              onChange={(e) => setNewFileName(e.target.value)}
              onKeyDown={handleKeyDown}
              onBlur={() => {
                if (newFileName.trim()) handleCreate()
                else setIsCreating(false)
              }}
              placeholder="filename.tex"
              className="w-28 rounded border border-slate-300 bg-white px-1.5 py-0.5 text-xs outline-none focus:border-indigo-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            />
          ) : (
            <button
              type="button"
              onClick={() => setIsCreating(true)}
              className="rounded p-0.5 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
              title="Add file"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          )}
        </>
      )}
    </div>
  )
}
