import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Sparkles, ArrowRight, X } from 'lucide-react'
import { useState } from 'react'

interface UsageWarningProps {
  feature: string
  current: number
  limit: number
  featureLabel?: string
  onDismiss?: () => void
  className?: string
}

const UsageWarning = ({
  feature,
  current,
  limit,
  featureLabel,
  onDismiss,
  className = '',
}: UsageWarningProps) => {
  const navigate = useNavigate()
  const [dismissed, setDismissed] = useState(false)

  if (dismissed || limit === -1) return null

  const percentage = (current / limit) * 100
  const isAtLimit = current >= limit
  const isNearLimit = percentage >= 80 && !isAtLimit

  if (!isAtLimit && !isNearLimit) return null

  const label = featureLabel || feature.replace(/_/g, ' ')

  const handleDismiss = () => {
    setDismissed(true)
    onDismiss?.()
  }

  if (isAtLimit) {
    return (
      <div className={`rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 p-4 ${className}`}>
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 h-10 w-10 rounded-full bg-red-100 dark:bg-red-500/20 flex items-center justify-center">
            <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h4 className="font-semibold text-red-900 dark:text-red-200">
                  {label} limit reached
                </h4>
                <p className="text-sm text-red-700 dark:text-red-300 mt-0.5">
                  You've used all {limit} {label.toLowerCase()} this month
                </p>
              </div>
              {onDismiss && (
                <button
                  onClick={handleDismiss}
                  className="p-1 rounded-full text-red-400 hover:text-red-600 hover:bg-red-100 dark:hover:bg-red-500/20 transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
            <button
              onClick={() => navigate('/pricing')}
              className="mt-3 inline-flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              <Sparkles className="h-4 w-4" />
              Upgrade to Pro
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Near limit warning (80%+)
  return (
    <div className={`rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 p-4 ${className}`}>
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 h-10 w-10 rounded-full bg-amber-100 dark:bg-amber-500/20 flex items-center justify-center">
          <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h4 className="font-semibold text-amber-900 dark:text-amber-200">
                Running low on {label.toLowerCase()}
              </h4>
              <p className="text-sm text-amber-700 dark:text-amber-300 mt-0.5">
                You've used {current} of {limit} ({Math.round(percentage)}%)
              </p>
            </div>
            {onDismiss && (
              <button
                onClick={handleDismiss}
                className="p-1 rounded-full text-amber-400 hover:text-amber-600 hover:bg-amber-100 dark:hover:bg-amber-500/20 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
          <div className="mt-3 flex items-center gap-3">
            <div className="flex-1 h-2 bg-amber-200 dark:bg-amber-500/30 rounded-full overflow-hidden">
              <div
                className="h-full bg-amber-500 rounded-full transition-all"
                style={{ width: `${Math.min(percentage, 100)}%` }}
              />
            </div>
            <button
              onClick={() => navigate('/pricing')}
              className="flex-shrink-0 inline-flex items-center gap-1 text-sm font-medium text-amber-700 dark:text-amber-300 hover:text-amber-900 dark:hover:text-amber-100"
            >
              Upgrade
              <ArrowRight className="h-3 w-3" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default UsageWarning
