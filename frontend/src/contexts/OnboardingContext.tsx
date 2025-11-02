import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'

interface OnboardingState {
  hasSeenWelcome: boolean
  hasCreatedFirstProject: boolean
  hasCreatedFirstPaper: boolean
  hasUsedDiscovery: boolean
  hasUsedCollaboration: boolean
  currentTourStep: number | null
}

interface OnboardingContextValue {
  state: OnboardingState
  markWelcomeSeen: () => void
  markFirstProjectCreated: () => void
  markFirstPaperCreated: () => void
  markDiscoveryUsed: () => void
  markCollaborationUsed: () => void
  startTour: (step?: number) => void
  nextTourStep: () => void
  endTour: () => void
  resetOnboarding: () => void
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null)

const STORAGE_KEY = 'scholarhub_onboarding'

const defaultState: OnboardingState = {
  hasSeenWelcome: false,
  hasCreatedFirstProject: false,
  hasCreatedFirstPaper: false,
  hasUsedDiscovery: false,
  hasUsedCollaboration: false,
  currentTourStep: null,
}

export const OnboardingProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [state, setState] = useState<OnboardingState>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        return { ...defaultState, ...JSON.parse(stored) }
      }
    } catch (error) {
      console.warn('Failed to load onboarding state:', error)
    }
    return defaultState
  })

  // Persist to localStorage whenever state changes
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    } catch (error) {
      console.warn('Failed to save onboarding state:', error)
    }
  }, [state])

  const markWelcomeSeen = () => {
    setState(prev => ({ ...prev, hasSeenWelcome: true }))
  }

  const markFirstProjectCreated = () => {
    setState(prev => ({ ...prev, hasCreatedFirstProject: true }))
  }

  const markFirstPaperCreated = () => {
    setState(prev => ({ ...prev, hasCreatedFirstPaper: true }))
  }

  const markDiscoveryUsed = () => {
    setState(prev => ({ ...prev, hasUsedDiscovery: true }))
  }

  const markCollaborationUsed = () => {
    setState(prev => ({ ...prev, hasUsedCollaboration: true }))
  }

  const startTour = (step: number = 0) => {
    setState(prev => ({ ...prev, currentTourStep: step }))
  }

  const nextTourStep = () => {
    setState(prev => ({
      ...prev,
      currentTourStep: prev.currentTourStep !== null ? prev.currentTourStep + 1 : 0,
    }))
  }

  const endTour = () => {
    setState(prev => ({ ...prev, currentTourStep: null }))
  }

  const resetOnboarding = () => {
    setState(defaultState)
    localStorage.removeItem(STORAGE_KEY)
  }

  return (
    <OnboardingContext.Provider
      value={{
        state,
        markWelcomeSeen,
        markFirstProjectCreated,
        markFirstPaperCreated,
        markDiscoveryUsed,
        markCollaborationUsed,
        startTour,
        nextTourStep,
        endTour,
        resetOnboarding,
      }}
    >
      {children}
    </OnboardingContext.Provider>
  )
}

export const useOnboarding = () => {
  const context = useContext(OnboardingContext)
  if (!context) {
    throw new Error('useOnboarding must be used within OnboardingProvider')
  }
  return context
}
