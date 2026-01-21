import { useNavigate } from 'react-router-dom'
import { Sparkles, ArrowRight, X } from 'lucide-react'
import { useState } from 'react'

interface UpgradeBannerProps {
  variant?: 'inline' | 'floating' | 'sidebar'
  message?: string
  dismissible?: boolean
  className?: string
}

const UpgradeBanner = ({
  variant = 'inline',
  message = 'Unlock more features with Pro',
  dismissible = false,
  className = '',
}: UpgradeBannerProps) => {
  const navigate = useNavigate()
  const [dismissed, setDismissed] = useState(false)

  if (dismissed) return null

  if (variant === 'sidebar') {
    return (
      <div className={`p-3 ${className}`}>
        <button
          onClick={() => navigate('/pricing')}
          className="w-full group flex flex-col items-center gap-2 p-4 rounded-xl bg-gradient-to-br from-amber-50 to-orange-50 dark:from-amber-500/10 dark:to-orange-500/10 border border-amber-200 dark:border-amber-500/20 hover:border-amber-300 dark:hover:border-amber-500/30 transition-all"
        >
          <div className="flex items-center justify-center h-10 w-10 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 shadow-lg shadow-amber-500/25">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div className="text-center">
            <div className="font-semibold text-amber-900 dark:text-amber-200 text-sm">
              Upgrade to Pro
            </div>
            <div className="text-xs text-amber-700 dark:text-amber-300/70 mt-0.5">
              Get 25x more AI calls
            </div>
          </div>
          <div className="flex items-center gap-1 text-xs font-medium text-amber-600 dark:text-amber-400 group-hover:gap-2 transition-all">
            View plans
            <ArrowRight className="h-3 w-3" />
          </div>
        </button>
      </div>
    )
  }

  if (variant === 'floating') {
    return (
      <div className={`fixed bottom-4 right-4 z-40 ${className}`}>
        <div className="relative bg-gradient-to-r from-primary-500 to-primary-600 text-white rounded-2xl shadow-2xl shadow-primary-500/25 p-4 pr-12 max-w-sm">
          {dismissible && (
            <button
              onClick={() => setDismissed(true)}
              className="absolute top-2 right-2 p-1 rounded-full hover:bg-white/20 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          )}
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 h-10 w-10 rounded-full bg-white/20 flex items-center justify-center">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <div className="font-semibold">{message}</div>
              <p className="text-sm text-primary-100 mt-1">
                Upgrade now and get 500 AI calls/month
              </p>
              <button
                onClick={() => navigate('/pricing')}
                className="mt-3 inline-flex items-center gap-1 text-sm font-medium bg-white text-primary-600 px-3 py-1.5 rounded-lg hover:bg-primary-50 transition-colors"
              >
                See pricing
                <ArrowRight className="h-3 w-3" />
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Default inline variant
  return (
    <div className={`relative overflow-hidden rounded-xl bg-gradient-to-r from-primary-500 to-primary-600 p-4 ${className}`}>
      {dismissible && (
        <button
          onClick={() => setDismissed(true)}
          className="absolute top-2 right-2 p-1 rounded-full text-white/70 hover:text-white hover:bg-white/20 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      )}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0 h-10 w-10 rounded-full bg-white/20 flex items-center justify-center">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div className="text-white">
            <div className="font-semibold">{message}</div>
            <p className="text-sm text-primary-100">Get more AI calls, searches & storage</p>
          </div>
        </div>
        <button
          onClick={() => navigate('/pricing')}
          className="flex-shrink-0 inline-flex items-center gap-1 bg-white text-primary-600 font-medium px-4 py-2 rounded-lg hover:bg-primary-50 transition-colors"
        >
          Upgrade
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
      {/* Decorative elements */}
      <div className="absolute -top-6 -right-6 h-24 w-24 rounded-full bg-white/10" />
      <div className="absolute -bottom-4 -left-4 h-16 w-16 rounded-full bg-white/10" />
    </div>
  )
}

export default UpgradeBanner
