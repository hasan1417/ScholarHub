import React, { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react'
import { researchPapersAPI } from '../services/api'
import { ResearchPaper, ResearchPaperCreate, ResearchPaperUpdate } from '../types'
import { useAuth } from './AuthContext'

interface PapersContextType {
  papers: ResearchPaper[]
  isLoading: boolean
  error: string | null
  loadPapers: () => Promise<void>
  createPaper: (paperData: ResearchPaperCreate) => Promise<ResearchPaper>
  updatePaper: (id: string, paperData: ResearchPaperUpdate) => Promise<ResearchPaper>
  deletePaper: (id: string) => Promise<void>
  refreshPapers: () => Promise<void>
}

const PapersContext = createContext<PapersContextType | undefined>(undefined)

export const usePapers = () => {
  const context = useContext(PapersContext)
  if (context === undefined) {
    throw new Error('usePapers must be used within a PapersProvider')
  }
  return context
}

interface PapersProviderProps {
  children: ReactNode
}

export const PapersProvider: React.FC<PapersProviderProps> = ({ children }) => {
  const [papers, setPapers] = useState<ResearchPaper[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { user } = useAuth() // Get current user from auth context

  const loadPapers = useCallback(async () => {
    try {
      setIsLoading(true)
      setError(null)
      const response = await researchPapersAPI.getPapers(0, 100)
      setPapers(response.data.papers || [])
    } catch (error) {
      console.error('Error loading papers:', error)
      setError('Failed to load papers')
    } finally {
      setIsLoading(false)
    }
  }, [user])

  const createPaper = useCallback(async (paperData: ResearchPaperCreate): Promise<ResearchPaper> => {
    try {
      const response = await researchPapersAPI.createPaper(paperData)
      const newPaper = response.data
      setPapers(prev => [newPaper, ...prev])
      return newPaper
    } catch (error) {
      console.error('Error creating paper:', error)
      throw error
    }
  }, [])

  const updatePaper = useCallback(async (id: string, paperData: ResearchPaperUpdate): Promise<ResearchPaper> => {
    try {
      const response = await researchPapersAPI.updatePaper(id, paperData)
      const updatedPaper = response.data
      setPapers(prev => prev.map(p => p.id === id ? updatedPaper : p))
      return updatedPaper
    } catch (error) {
      console.error('Error updating paper:', error)
      throw error
    }
  }, [])

  const deletePaper = useCallback(async (id: string): Promise<void> => {
    try {
      await researchPapersAPI.deletePaper(id)
      setPapers(prev => prev.filter(p => p.id !== id))
    } catch (error) {
      console.error('Error deleting paper:', error)
      throw error
    }
  }, [])

  const refreshPapers = useCallback(async () => {
    await loadPapers()
  }, [loadPapers])

  // Clear papers when user changes (login/logout)
  useEffect(() => {
    if (!user) {
      // User logged out, clear papers
      setPapers([])
      setError(null)
    } else {
      // User logged in, load papers
      loadPapers()
    }
  }, [user, loadPapers])

  const value: PapersContextType = {
    papers,
    isLoading,
    error,
    loadPapers,
    createPaper,
    updatePaper,
    deletePaper,
    refreshPapers
  }

  return (
    <PapersContext.Provider value={value}>
      {children}
    </PapersContext.Provider>
  )
}
