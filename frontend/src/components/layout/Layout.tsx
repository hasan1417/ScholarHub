import { Outlet, useNavigate, Link, useLocation } from 'react-router-dom'
import { useMemo, useState, useEffect, useCallback, useRef } from 'react'
import { FolderKanban, UserCircle, Settings as SettingsIcon, Sun, Moon, ChevronRight, Palette, Sparkles, Mail, X, RefreshCw, Menu } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import SettingsModal from '../settings/SettingsModal'
import { useThemePreference } from '../../hooks/useThemePreference'
import { useToast } from '../../hooks/useToast'
import { Logo } from '../brand/Logo'
import { UpgradeModal, SubscriptionSection } from '../subscription'
import { subscriptionAPI, authAPI } from '../../services/api'
import CommandPalette from '../ui/CommandPalette'

const Layout = () => {
  const { user, logout } = useAuth()
  const { toast } = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [isFreeTier, setIsFreeTier] = useState(false)
  const [tierLoaded, setTierLoaded] = useState(false)
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const drawerCloseRef = useRef<HTMLButtonElement>(null)

  const { theme, setTheme } = useThemePreference()

  // Close mobile nav on route change
  useEffect(() => {
    setMobileNavOpen(false)
  }, [location.pathname])

  // Escape key closes drawer
  useEffect(() => {
    if (!mobileNavOpen) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMobileNavOpen(false)
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [mobileNavOpen])

  // Lock body scroll when drawer is open
  useEffect(() => {
    if (!mobileNavOpen) return
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [mobileNavOpen])

  // Focus close button when drawer opens
  useEffect(() => {
    if (mobileNavOpen) {
      // Small delay to allow the DOM to render
      requestAnimationFrame(() => drawerCloseRef.current?.focus())
    }
  }, [mobileNavOpen])

  // Email verification banner state
  const [verificationBannerDismissed, setVerificationBannerDismissed] = useState(false)
  const [resendingVerification, setResendingVerification] = useState(false)
  const [verificationResent, setVerificationResent] = useState(false)

  // Cmd+K / Ctrl+K to open command palette
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setIsCommandPaletteOpen((prev) => !prev)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

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

  // Listen for verification required events
  useEffect(() => {
    const handleVerificationRequired = () => {
      // Show the banner if it was dismissed
      setVerificationBannerDismissed(false)
    }
    window.addEventListener('verification-required', handleVerificationRequired)
    return () => window.removeEventListener('verification-required', handleVerificationRequired)
  }, [])

  const handleResendVerification = useCallback(async () => {
    if (!user?.email || resendingVerification) return
    setResendingVerification(true)
    try {
      await authAPI.resendVerification(user.email)
      setVerificationResent(true)
      setTimeout(() => setVerificationResent(false), 5000)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to resend verification email')
    } finally {
      setResendingVerification(false)
    }
  }, [user?.email, resendingVerification])

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

  // Hide the global header on full-screen editor pages
  const isEditorPage = /\/(editor|collaborate)$/.test(location.pathname)

  return (
    <div className="min-h-screen transition-colors duration-200">
      {!isEditorPage && <header className="border-b border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-800">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2">
            {/* Mobile hamburger */}
            <button
              type="button"
              onClick={() => setMobileNavOpen(true)}
              aria-label="Open navigation"
              className="inline-flex h-11 w-11 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 dark:text-slate-300 dark:hover:bg-slate-700 sm:hidden"
            >
              <Menu className="h-5 w-5" />
            </button>
            <Link to="/projects" className="transition-opacity hover:opacity-80">
              <Logo textClassName="text-lg font-semibold" />
            </Link>
          </div>
          <div className="hidden sm:flex items-center space-x-2">
            {/* Upgrade button for free tier users */}
            {tierLoaded && isFreeTier && (
              <Link
                to="/pricing"
                className="group relative mr-3 inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-amber-500 to-orange-500 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition-all hover:from-amber-600 hover:to-orange-600 hover:shadow-md overflow-hidden"
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
          {/* Mobile: settings button stays visible */}
          <button
            type="button"
            onClick={() => setIsSettingsOpen(true)}
            aria-label="Open settings"
            className="inline-flex h-11 w-11 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 dark:text-slate-300 dark:hover:bg-slate-700 sm:hidden"
          >
            <SettingsIcon className="h-5 w-5" />
          </button>
        </div>
      </header>}

      {/* Mobile slide-out nav drawer */}
      {mobileNavOpen && (
        <div className="fixed inset-0 z-50 sm:hidden" role="dialog" aria-modal="true">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            onClick={() => setMobileNavOpen(false)}
          />
          {/* Drawer panel */}
          <nav className="absolute inset-y-0 left-0 w-72 max-w-[80vw] bg-white dark:bg-slate-800 shadow-xl flex flex-col animate-slide-in-left">
            <div className="flex items-center justify-between border-b border-gray-200 px-4 py-4 dark:border-slate-700">
              <Logo textClassName="text-lg font-semibold" />
              <button
                ref={drawerCloseRef}
                type="button"
                onClick={() => setMobileNavOpen(false)}
                aria-label="Close navigation"
                className="inline-flex h-11 w-11 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
              {navItems.map(({ to, label, icon: Icon, isActive }) => (
                <Link
                  key={label}
                  to={to}
                  className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300'
                      : 'text-gray-700 hover:bg-gray-100 dark:text-slate-200 dark:hover:bg-slate-700'
                  }`}
                >
                  <Icon className="h-5 w-5" />
                  {label}
                </Link>
              ))}
            </div>
            {/* Upgrade CTA in mobile drawer */}
            {tierLoaded && isFreeTier && (
              <div className="border-t border-gray-200 px-4 py-3 dark:border-slate-700">
                <Link
                  to="/pricing"
                  className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 px-4 py-3 text-sm font-medium text-white shadow-sm transition-all hover:from-amber-600 hover:to-orange-600"
                >
                  <Sparkles className="h-4 w-4" />
                  Upgrade plan
                </Link>
              </div>
            )}
            <div className="border-t border-gray-200 px-4 py-3 dark:border-slate-700">
              <button
                type="button"
                onClick={() => { setMobileNavOpen(false); setIsSettingsOpen(true) }}
                className="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-slate-200 dark:hover:bg-slate-700"
              >
                <SettingsIcon className="h-5 w-5" />
                Settings
              </button>
            </div>
          </nav>
        </div>
      )}

      {/* Email Verification Banner */}
      {!isEditorPage && user && !user.is_verified && !verificationBannerDismissed && (
        <div className="border-b border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-2 sm:px-6 lg:px-8">
            <div className="flex items-center gap-3">
              <Mail className="h-4 w-4 text-amber-600 dark:text-amber-400" />
              <p className="text-sm text-amber-800 dark:text-amber-200">
                {verificationResent ? (
                  <span className="font-medium">Verification email sent! Check your inbox.</span>
                ) : (
                  <>
                    Please verify your email to access all features.{' '}
                    <button
                      type="button"
                      onClick={handleResendVerification}
                      disabled={resendingVerification}
                      className="inline-flex items-center gap-1 font-medium text-amber-700 underline hover:text-amber-900 disabled:opacity-50 dark:text-amber-300 dark:hover:text-amber-100"
                    >
                      {resendingVerification && <RefreshCw className="h-3 w-3 animate-spin" />}
                      Resend verification email
                    </button>
                  </>
                )}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setVerificationBannerDismissed(true)}
              className="rounded p-1 text-amber-600 hover:bg-amber-100 dark:text-amber-400 dark:hover:bg-amber-900"
              aria-label="Dismiss"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      <main aria-hidden={mobileNavOpen || undefined} className={isEditorPage ? 'flex flex-col h-[100vh]' : 'mx-auto max-w-7xl px-3 py-4 sm:px-6 sm:py-8 lg:px-8'}>
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

      {/* Command Palette (Cmd+K / Ctrl+K) */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
      />
    </div>
  )
}

export default Layout
