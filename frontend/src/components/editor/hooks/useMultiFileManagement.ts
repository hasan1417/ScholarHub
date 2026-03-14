import { useState, useEffect, useCallback } from 'react'
// activeFile state is now owned by the parent (LaTeXEditor) and passed in

interface UseMultiFileManagementOptions {
  realtimeDoc: any | null
  getYText: (filename: string) => any
  getFileList: () => string[]
  yTextReady: number
  activeFile: string
  onActiveFileChange: (file: string) => void
}

export function useMultiFileManagement({ realtimeDoc, getYText, getFileList, yTextReady, activeFile, onActiveFileChange }: UseMultiFileManagementOptions) {
  const [fileList, setFileList] = useState<string[]>(['main.tex'])

  // Sync file list from Yjs when the doc changes or new types arrive via sync
  useEffect(() => {
    if (!realtimeDoc) return
    const refreshFiles = () => {
      const files = getFileList()
      setFileList(prev => {
        if (JSON.stringify(prev) === JSON.stringify(files)) return prev
        return files
      })
    }
    refreshFiles()
    // Listen for doc updates (e.g. when server-bootstrapped files arrive)
    realtimeDoc.on('update', refreshFiles)
    return () => { realtimeDoc.off('update', refreshFiles) }
  }, [realtimeDoc, getFileList, yTextReady])

  const handleCreateFile = useCallback((filename: string) => {
    if (!realtimeDoc) return
    getYText(filename)
    setFileList(prev => prev.includes(filename) ? prev : [...prev, filename])
    onActiveFileChange(filename)
  }, [realtimeDoc, getYText, onActiveFileChange])

  const handleDeleteFile = useCallback((filename: string) => {
    if (filename === 'main.tex') return
    if (realtimeDoc) {
      try {
        const yText = getYText(filename)
        if (yText && yText.length > 0) yText.delete(0, yText.length)
      } catch {}
    }
    setFileList(prev => prev.filter(f => f !== filename))
    if (activeFile === filename) onActiveFileChange('main.tex')
  }, [realtimeDoc, getYText, activeFile, onActiveFileChange])

  const handleSelectFile = useCallback((filename: string) => {
    if (filename === activeFile) return
    onActiveFileChange(filename)
  }, [activeFile, onActiveFileChange])

  return {
    activeFile,
    fileList,
    handleCreateFile,
    handleDeleteFile,
    handleSelectFile,
  }
}
