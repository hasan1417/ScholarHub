import { X, LogOut, Settings } from 'lucide-react'
import { ReactNode } from 'react'

type SettingsModalProps = {
  isOpen: boolean
  onClose: () => void
  onLogout: () => void
  children?: ReactNode
}

const SettingsModal = ({ isOpen, onClose, onLogout, children }: SettingsModalProps) => {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-gray-900/50 backdrop-blur-sm dark:bg-black/60"
        aria-hidden="true"
        onClick={onClose}
      />
      <div className="relative w-full max-w-sm rounded-2xl bg-white shadow-2xl transition-all duration-200 dark:bg-slate-800 animate-in fade-in zoom-in-95">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gray-100 dark:bg-slate-700">
              <Settings className="h-5 w-5 text-gray-600 dark:text-slate-300" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">Settings</h2>
              <p className="text-xs text-gray-500 dark:text-slate-400">Preferences & account</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
            aria-label="Close settings"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Divider */}
        <div className="mx-5 h-px bg-gray-100 dark:bg-slate-700" />

        {/* Content */}
        <div className="px-5 py-5 text-gray-700 dark:text-slate-200 overflow-y-auto max-h-[calc(100vh-10rem)]">
          {children ? (
            children
          ) : (
            <p className="text-sm text-gray-500 dark:text-slate-300">
              Settings configuration is coming soon.
            </p>
          )}
        </div>

        {/* Footer with Sign Out */}
        <div className="px-5 pb-5">
          <button
            onClick={onLogout}
            className="group w-full flex items-center justify-center gap-2 rounded-xl border border-gray-200 bg-gray-50 px-4 py-2.5 text-sm font-medium text-gray-600 transition-all hover:border-red-200 hover:bg-red-50 hover:text-red-600 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-300 dark:hover:border-red-500/30 dark:hover:bg-red-500/10 dark:hover:text-red-400"
          >
            <LogOut className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" />
            Sign out
          </button>
        </div>
      </div>
    </div>
  )
}

export default SettingsModal
