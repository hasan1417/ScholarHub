import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { CheckCircle, XCircle, Info, AlertTriangle, X } from 'lucide-react'

type ToastType = 'success' | 'error' | 'info' | 'warning'

interface ToastAction {
  label: string
  onClick: () => void
}

interface Toast {
  id: number
  type: ToastType
  message: string
  action?: ToastAction
}

interface ToastContextValue {
  toast: {
    success: (message: string, action?: ToastAction) => void
    error: (message: string, action?: ToastAction) => void
    info: (message: string, action?: ToastAction) => void
    warning: (message: string, action?: ToastAction) => void
  }
}

const ToastContext = createContext<ToastContextValue | null>(null)

let nextId = 0

const ICONS: Record<ToastType, typeof CheckCircle> = {
  success: CheckCircle,
  error: XCircle,
  info: Info,
  warning: AlertTriangle,
}

const TYPE_CLASSES: Record<ToastType, string> = {
  success:
    'border-green-200 bg-green-50 text-green-800 dark:border-green-700 dark:bg-green-900/80 dark:text-green-100',
  error:
    'border-red-200 bg-red-50 text-red-800 dark:border-red-700 dark:bg-red-900/80 dark:text-red-100',
  info:
    'border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-700 dark:bg-blue-900/80 dark:text-blue-100',
  warning:
    'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-700 dark:bg-amber-900/80 dark:text-amber-100',
}

const ICON_CLASSES: Record<ToastType, string> = {
  success: 'text-green-500 dark:text-green-400',
  error: 'text-red-500 dark:text-red-400',
  info: 'text-blue-500 dark:text-blue-400',
  warning: 'text-amber-500 dark:text-amber-400',
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const addToast = useCallback(
    (type: ToastType, message: string, action?: ToastAction) => {
      const id = ++nextId
      setToasts((prev) => [...prev, { id, type, message, action }])
      const duration = type === 'error' ? 6000 : 4000
      setTimeout(() => removeToast(id), duration)
    },
    [removeToast],
  )

  const toast = {
    success: (message: string, action?: ToastAction) => addToast('success', message, action),
    error: (message: string, action?: ToastAction) => addToast('error', message, action),
    info: (message: string, action?: ToastAction) => addToast('info', message, action),
    warning: (message: string, action?: ToastAction) => addToast('warning', message, action),
  }

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}

      {/* Toast container */}
      <div className="fixed bottom-4 right-4 z-[9999] flex flex-col-reverse gap-2 pointer-events-none">
        {toasts.map((t) => {
          const Icon = ICONS[t.type]
          return (
            <div
              key={t.id}
              className={`pointer-events-auto flex items-start gap-3 rounded-lg border px-4 py-3 shadow-lg backdrop-blur-sm animate-toast-in min-w-[300px] max-w-[420px] ${TYPE_CLASSES[t.type]}`}
            >
              <Icon className={`h-5 w-5 flex-shrink-0 mt-0.5 ${ICON_CLASSES[t.type]}`} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium leading-snug">{t.message}</p>
                {t.action && (
                  <button
                    type="button"
                    onClick={t.action.onClick}
                    className="mt-1 text-xs font-semibold underline underline-offset-2 opacity-80 hover:opacity-100 transition-opacity"
                  >
                    {t.action.label}
                  </button>
                )}
              </div>
              <button
                type="button"
                onClick={() => removeToast(t.id)}
                className="flex-shrink-0 rounded p-0.5 opacity-60 hover:opacity-100 transition-opacity"
                aria-label="Dismiss"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return ctx
}
