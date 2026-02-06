import { useState, useEffect, useCallback } from 'react'

interface UseMultiFileManagementOptions {
  realtimeDoc: any | null
  getYText: (filename: string) => any
  getFileList: () => string[]
  yTextReady: number
}

export function useMultiFileManagement({ realtimeDoc, getYText, getFileList, yTextReady }: UseMultiFileManagementOptions) {
  const [activeFile, setActiveFile] = useState('main.tex')
  const [fileList, setFileList] = useState<string[]>(['main.tex'])

  // Sync file list from Yjs when the doc changes
  useEffect(() => {
    if (!realtimeDoc) return
    const files = getFileList()
    setFileList(prev => {
      if (JSON.stringify(prev) === JSON.stringify(files)) return prev
      return files
    })
  }, [realtimeDoc, getFileList, yTextReady])

  const handleCreateFile = useCallback((filename: string) => {
    if (!realtimeDoc) return
    getYText(filename)
    setFileList(prev => prev.includes(filename) ? prev : [...prev, filename])
    setActiveFile(filename)
  }, [realtimeDoc, getYText])

  const handleDeleteFile = useCallback((filename: string) => {
    if (filename === 'main.tex') return
    if (realtimeDoc) {
      try {
        const yText = getYText(filename)
        if (yText && yText.length > 0) yText.delete(0, yText.length)
      } catch {}
    }
    setFileList(prev => prev.filter(f => f !== filename))
    if (activeFile === filename) setActiveFile('main.tex')
  }, [realtimeDoc, getYText, activeFile])

  const handleSelectFile = useCallback((filename: string) => {
    if (filename === activeFile) return
    setActiveFile(filename)
  }, [activeFile])

  return {
    activeFile,
    fileList,
    handleCreateFile,
    handleDeleteFile,
    handleSelectFile,
  }
}
