import { Outlet, useNavigate, Link, useLocation } from 'react-router-dom'
import { useMemo, useState } from 'react'
import { FolderKanban, UserCircle, Settings as SettingsIcon, Sun, Moon, Sparkles } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import SettingsModal from '../settings/SettingsModal'
import ModelSelectionModal from '../ai/ModelSelectionModal'
import { useThemePreference } from '../../hooks/useThemePreference'

const Layout = () => {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [isModelModalOpen, setIsModelModalOpen] = useState(false)

  const { theme, setTheme } = useThemePreference()

  const handleLogout = () => {
    setIsSettingsOpen(false)
    logout()
    navigate('/')
  }

  const navItems = [
    {
      to: '/projects',
      label: 'Projects',
      icon: FolderKanban,
      isActive: location.pathname === '/' || location.pathname.startsWith('/projects'),
    },
    {
      to: '/profile',
      label: 'Profile',
      icon: UserCircle,
      isActive: location.pathname.startsWith('/profile'),
    },
  ]

  const settingsContent = useMemo(() => (
    <div className="space-y-6">
      <section>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-slate-100">Appearance</h3>
        <p className="mt-1 text-xs text-gray-500 dark:text-slate-300">Switch between light and dark modes for the UI shell.</p>
        <div className="mt-4 flex gap-3">
          <button
            type="button"
            onClick={() => setTheme('light')}
            className={`flex flex-1 items-center gap-2 rounded-lg border px-3 py-2 text-sm transition ${
              theme === 'light'
                ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-400/10 dark:text-indigo-200'
                : 'border-gray-200 text-gray-600 hover:border-gray-300 dark:border-slate-700 dark:text-slate-200 dark:hover:border-slate-500'
            }`}
          >
            <Sun className="h-4 w-4" /> Light
          </button>
          <button
            type="button"
            onClick={() => setTheme('dark')}
            className={`flex flex-1 items-center gap-2 rounded-lg border px-3 py-2 text-sm transition ${
              theme === 'dark'
                ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-400/10 dark:text-indigo-200'
                : 'border-gray-200 text-gray-600 hover:border-gray-300 dark:border-slate-700 dark:text-slate-200 dark:hover:border-slate-500'
            }`}
          >
            <Moon className="h-4 w-4" /> Dark
          </button>
        </div>
      </section>

      <section>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-slate-100">AI configuration</h3>
        <p className="mt-1 text-xs text-gray-500 dark:text-slate-300">
          Update the provider, model, and embeddings used across assistants and writing tools.
        </p>
        <button
          type="button"
          onClick={() => setIsModelModalOpen(true)}
          className="mt-4 inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-700 transition-colors hover:border-indigo-300 hover:bg-indigo-100 dark:border-indigo-400/40 dark:bg-indigo-400/10 dark:text-indigo-200 dark:hover:border-indigo-300/50 dark:hover:bg-indigo-400/20"
        >
          <Sparkles className="h-4 w-4" /> Configure AI models
        </button>
      </section>

      <section>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-slate-100">Profile</h3>
        <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-600 transition-colors dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-200">
          <div className="font-medium text-gray-900 dark:text-slate-100">{user?.first_name ? `${user.first_name} ${user.last_name ?? ''}`.trim() : user?.email}</div>
          <div className="text-xs text-gray-500 dark:text-slate-300">{user?.email}</div>
        </div>
      </section>
    </div>
  ), [theme, user])

  return (
    <div className="min-h-screen transition-colors duration-200">
      <header className="border-b border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-800">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link
            to="/projects"
            className="text-lg font-semibold tracking-tight text-gray-900 transition-colors hover:text-gray-700 dark:text-slate-100 dark:hover:text-slate-300"
          >
            ScholarHub
          </Link>
          <div className="flex items-center space-x-2">
            {navItems.map(({ to, label, icon: Icon, isActive }) => (
              <Link
                key={label}
                to={to}
                aria-label={label}
                className={`inline-flex h-10 w-10 items-center justify-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-500 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-700'
                }`}
              >
                <Icon className="h-5 w-5" />
              </Link>
            ))}
            <button
              type="button"
              onClick={() => setIsSettingsOpen(true)}
              aria-label="Open settings"
              className="inline-flex h-10 w-10 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              <SettingsIcon className="h-5 w-5" />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <Outlet />
      </main>

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        onLogout={handleLogout}
      >
        {settingsContent}
      </SettingsModal>
      <ModelSelectionModal isOpen={isModelModalOpen} onClose={() => setIsModelModalOpen(false)} />
    </div>
  )
}

export default Layout
