import { X } from 'lucide-react'
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
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-gray-900/40 dark:bg-black/60" aria-hidden="true" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-2xl bg-white shadow-xl transition-colors duration-200 dark:bg-slate-800">
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4 dark:border-slate-700">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">Workspace Settings</h2>
            <p className="text-sm text-gray-500 dark:text-slate-300">Adjust your appearance and AI preferences.</p>
          </div>
          <button
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-700"
            aria-label="Close settings"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="px-6 py-5 space-y-6 text-gray-700 dark:text-slate-200">
          {children ? (
            children
          ) : (
            <p className="text-sm text-gray-500 dark:text-slate-300">
              Settings configuration is coming soon. You&apos;ll be able to toggle themes and update AI provider details here.
            </p>
          )}
          <div className="pt-4 border-t border-gray-100 dark:border-slate-700">
            <button
              onClick={onLogout}
              className="w-full inline-flex items-center justify-center rounded-md border border-transparent bg-red-50 px-4 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-100 dark:bg-red-600/20 dark:text-red-200 dark:hover:bg-red-600/30"
            >
              Sign out
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default SettingsModal
