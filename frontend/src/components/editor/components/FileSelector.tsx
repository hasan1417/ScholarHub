import { useState, useCallback } from 'react'
import { Plus, X, FileText } from 'lucide-react'

interface FileSelectorProps {
  files: string[]
  activeFile: string
  onSelectFile: (filename: string) => void
  onCreateFile: (filename: string) => void
  onDeleteFile: (filename: string) => void
  readOnly?: boolean
}

export const FileSelector: React.FC<FileSelectorProps> = ({
  files,
  activeFile,
  onSelectFile,
  onCreateFile,
  onDeleteFile,
  readOnly,
}) => {
  const [isCreating, setIsCreating] = useState(false)
  const [newFileName, setNewFileName] = useState('')

  const handleCreate = useCallback(() => {
    let name = newFileName.trim()
    if (!name) return
    if (!name.endsWith('.tex')) name += '.tex'
    // Prevent duplicates
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

  if (files.length <= 1 && !isCreating) {
    // Single file mode — show minimal UI with just the add button
    return (
      <div className="flex items-center gap-1 border-b border-slate-200 bg-slate-100/80 px-2 py-1 dark:border-slate-700 dark:bg-slate-800/60">
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
    <div className="flex items-center gap-0.5 overflow-x-auto border-b border-slate-200 bg-slate-100/80 px-2 py-1 dark:border-slate-700 dark:bg-slate-800/60">
      {files.map((file) => (
        <div
          key={file}
          className={`group flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium transition-colors cursor-pointer ${
            file === activeFile
              ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white'
              : 'text-slate-500 hover:bg-slate-200/80 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-700/60 dark:hover:text-slate-300'
          }`}
          onClick={() => onSelectFile(file)}
        >
          <FileText className="h-3 w-3 flex-shrink-0" />
          <span className="whitespace-nowrap">{file}</span>
          {file !== 'main.tex' && !readOnly && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                if (confirm(`Delete ${file}?`)) onDeleteFile(file)
              }}
              className="ml-0.5 hidden rounded p-0.5 text-slate-400 transition-colors hover:bg-rose-100 hover:text-rose-500 group-hover:inline-flex dark:hover:bg-rose-900/30 dark:hover:text-rose-400"
              title={`Delete ${file}`}
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      ))}
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
