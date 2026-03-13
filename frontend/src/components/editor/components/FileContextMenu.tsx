import React, { useEffect, useRef, useCallback } from 'react'
import { Pencil, Download, Trash2, FilePlus, FolderPlus } from 'lucide-react'

interface FileContextMenuProps {
  x: number
  y: number
  filename: string
  isMainFile: boolean
  onRename: (oldName: string, newName: string) => void
  onDelete: (filename: string) => void
  onDownload?: (filename: string) => void
  onNewFile?: () => void
  onClose: () => void
}

export const FileContextMenu: React.FC<FileContextMenuProps> = ({
  x,
  y,
  filename,
  isMainFile,
  onRename,
  onDelete,
  onDownload,
  onNewFile,
  onClose,
}) => {
  const menuRef = useRef<HTMLDivElement>(null)

  // Adjust position so menu doesn't overflow viewport
  useEffect(() => {
    const el = menuRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    let ax = x
    let ay = y
    if (x + rect.width > window.innerWidth) ax = window.innerWidth - rect.width - 8
    if (y + rect.height > window.innerHeight) ay = window.innerHeight - rect.height - 8
    if (ax < 0) ax = 8
    if (ay < 0) ay = 8
    el.style.left = `${ax}px`
    el.style.top = `${ay}px`
  }, [x, y])

  // Close on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    // Use a short delay so the opening right-click doesn't immediately close it
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handleClick)
    }, 0)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('mousedown', handleClick)
    }
  }, [onClose])

  // Close on Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  const handleRename = useCallback(() => {
    if (isMainFile) return
    const newName = prompt(`Rename "${filename}" to:`, filename)
    if (newName && newName !== filename) {
      onRename(filename, newName)
    }
    onClose()
  }, [filename, isMainFile, onRename, onClose])

  const handleDelete = useCallback(() => {
    if (isMainFile) return
    onDelete(filename)
    onClose()
  }, [filename, isMainFile, onDelete, onClose])

  const handleDownload = useCallback(() => {
    onDownload?.(filename)
    onClose()
  }, [filename, onDownload, onClose])

  const handleNewFile = useCallback(() => {
    onNewFile?.()
    onClose()
  }, [onNewFile, onClose])

  return (
    <div
      ref={menuRef}
      className="fixed z-[100] min-w-[160px] rounded-lg border border-slate-700 bg-slate-800 py-1 shadow-xl"
      style={{ left: x, top: y }}
    >
      <button
        type="button"
        onClick={handleRename}
        disabled={isMainFile}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-slate-200 transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:text-slate-500"
      >
        <Pencil className="h-3.5 w-3.5" />
        Rename
      </button>
      <button
        type="button"
        onClick={handleDownload}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-slate-200 transition-colors hover:bg-slate-700"
      >
        <Download className="h-3.5 w-3.5" />
        Download
      </button>
      <button
        type="button"
        onClick={handleDelete}
        disabled={isMainFile}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:text-slate-500 enabled:text-red-400"
      >
        <Trash2 className="h-3.5 w-3.5" />
        Delete
      </button>

      <div className="mx-2 my-1 border-t border-slate-700" />

      <button
        type="button"
        onClick={handleNewFile}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-slate-200 transition-colors hover:bg-slate-700"
      >
        <FilePlus className="h-3.5 w-3.5" />
        New file
      </button>
      <button
        type="button"
        disabled
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-slate-500 cursor-not-allowed"
      >
        <FolderPlus className="h-3.5 w-3.5" />
        New folder
      </button>
    </div>
  )
}
