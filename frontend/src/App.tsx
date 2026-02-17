import { useEffect } from 'react'
import { useRoutes } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { PapersProvider } from './contexts/PapersContext'
import { OnboardingProvider } from './contexts/OnboardingContext'
import { ToastProvider } from './hooks/useToast'
import { appRouteConfig } from './routes'
import { initializeThemePreference } from './hooks/useThemePreference'

function App() {
  const routes = useRoutes(appRouteConfig)
  useEffect(() => {
    initializeThemePreference()
  }, [])

  return (
    <div className="min-h-screen font-sans bg-slate-50 text-slate-900 transition-colors duration-300 dark:bg-slate-900 dark:text-slate-100">
      <ToastProvider>
        <AuthProvider>
          <OnboardingProvider>
            <PapersProvider>
              {routes}
            </PapersProvider>
          </OnboardingProvider>
        </AuthProvider>
      </ToastProvider>
    </div>
  )
}

export default App
