import { useCallback, useEffect, useState } from 'react'

const THEME_STORAGE_KEY = 'scholarhub.theme'

export type ThemeOption = 'light' | 'dark'

const resolveStoredTheme = (): ThemeOption => {
  if (typeof window === 'undefined') return 'light'
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'dark' || stored === 'light') return stored
  if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark'
  }
  return 'light'
}

const applyTheme = (theme: ThemeOption) => {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  const body = document.body
  root.classList.toggle('dark', theme === 'dark')
  body.classList.toggle('dark', theme === 'dark')
  root.setAttribute('data-theme', theme)
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch (error) {
    console.warn('Unable to persist theme preference', error)
  }
}

export const initializeThemePreference = (): ThemeOption => {
  const theme = resolveStoredTheme()
  applyTheme(theme)
  return theme
}

export const useThemePreference = () => {
  const [theme, setThemeState] = useState<ThemeOption>(() => {
    if (typeof window === 'undefined') return 'light'
    return resolveStoredTheme()
  })

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const setTheme = useCallback((next: ThemeOption) => {
    setThemeState(next)
  }, [])

  return { theme, setTheme }
}
