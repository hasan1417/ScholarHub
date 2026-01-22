import { Outlet, useNavigate, Link, useLocation } from 'react-router-dom'
import { useMemo, useState, useEffect } from 'react'
import { FolderKanban, UserCircle, Settings as SettingsIcon, Sun, Moon, ChevronRight, Palette, Sparkles } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import SettingsModal from '../settings/SettingsModal'
import { useThemePreference } from '../../hooks/useThemePreference'
import { Logo } from '../brand/Logo'
import { UpgradeModal, SubscriptionSection } from '../subscription'
import { subscriptionAPI } from '../../services/api'

const Layout = () => {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [isFreeTier, setIsFreeTier] = useState(false)
  const [tierLoaded, setTierLoaded] = useState(false)

  const { theme, setTheme } = useThemePreference()

  // Check subscription tier
  useEffect(() => {
    const checkTier = async () => {
      try {
        const res = await subscriptionAPI.getMySubscription()
        const tier = res.data?.subscription?.tier_id || 'free'
        setIsFreeTier(tier === 'free')
      } catch {
        setIsFreeTier(true)
      } finally {
        setTierLoaded(true)
      }
    }
    checkTier()
  }, [])

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

  const getInitials = () => {
    const first = user?.first_name?.charAt(0) || user?.email?.charAt(0) || '?'
    const last = user?.last_name?.charAt(0) || ''
    return (first + last).toUpperCase()
  }

  const settingsContent = useMemo(() => (
    <div className="space-y-5">
      {/* User Profile Card */}
      <Link
        to="/profile"
        onClick={() => setIsSettingsOpen(false)}
        className="flex items-center gap-4 rounded-xl border border-gray-100 bg-gradient-to-r from-gray-50 to-white p-4 transition-all hover:border-gray-200 hover:shadow-sm dark:border-slate-700 dark:from-slate-800 dark:to-slate-800/50 dark:hover:border-slate-600"
      >
        <div className="h-12 w-12 flex-shrink-0 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-semibold shadow-md">
          {getInitials()}
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-gray-900 dark:text-slate-100 truncate">
            {user?.first_name ? `${user.first_name} ${user.last_name ?? ''}`.trim() : 'User'}
          </div>
          <div className="text-sm text-gray-500 dark:text-slate-400 truncate">{user?.email}</div>
        </div>
        <ChevronRight className="h-5 w-5 text-gray-400 dark:text-slate-500" />
      </Link>

      {/* Appearance Section */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-slate-300">
          <Palette className="h-4 w-4" />
          <span>Appearance</span>
        </div>
        <div className="flex rounded-lg bg-gray-100 p-1 dark:bg-slate-700/50">
          <button
            type="button"
            onClick={() => setTheme('light')}
            className={`flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-all ${
              theme === 'light'
                ? 'bg-white text-gray-900 shadow-sm dark:bg-slate-600 dark:text-white'
                : 'text-gray-600 hover:text-gray-900 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            <Sun className="h-4 w-4" />
            <span>Light</span>
          </button>
          <button
            type="button"
            onClick={() => setTheme('dark')}
            className={`flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-all ${
              theme === 'dark'
                ? 'bg-white text-gray-900 shadow-sm dark:bg-slate-600 dark:text-white'
                : 'text-gray-600 hover:text-gray-900 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            <Moon className="h-4 w-4" />
            <span>Dark</span>
          </button>
        </div>
      </div>

      {/* Subscription Section */}
      <SubscriptionSection />
    </div>
  ), [theme, user, setIsSettingsOpen])

  return (
    <div className="min-h-screen transition-colors duration-200">
      <header className="border-b border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-800">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link to="/projects" className="transition-opacity hover:opacity-80">
            <Logo textClassName="text-lg font-semibold" />
          </Link>
          <div className="flex items-center space-x-2">
            {/* Upgrade button for free tier users */}
            {tierLoaded && isFreeTier && (
              <Link
                to="/pricing"
                className="group relative mr-3 hidden sm:inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-amber-500 to-orange-500 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition-all hover:from-amber-600 hover:to-orange-600 hover:shadow-md overflow-hidden"
              >
                {/* Gleam animation */}
                <span className="absolute inset-0 animate-gleam bg-gradient-to-r from-transparent via-white/30 to-transparent" />
                <Sparkles className="h-3.5 w-3.5 relative z-10" />
                <span className="relative z-10">Upgrade</span>
              </Link>
            )}
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

      {/* Global upgrade modal - listens for limit-exceeded events */}
      <UpgradeModal />
    </div>
  )
}

export default Layout
