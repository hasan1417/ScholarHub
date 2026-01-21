import { useEffect, useState, useCallback } from 'react'
import { X, Sparkles, Check, AlertCircle } from 'lucide-react'
import { LimitExceededError, SubscriptionTier } from '../../types'
import { subscriptionAPI } from '../../services/api'

interface UpgradeModalProps {
  // If provided, modal shows immediately (controlled mode)
  limitError?: LimitExceededError | null
  onClose?: () => void
}

// Feature descriptions for display
const FEATURE_LABELS: Record<string, string> = {
  discussion_ai_calls: 'AI Discussion Calls',
  paper_discovery_searches: 'Paper Discovery Searches',
  projects: 'Projects',
  papers_per_project: 'Papers per Project',
  collaborators_per_project: 'Collaborators per Project',
  references_total: 'References in Library',
}

const UpgradeModal = ({ limitError: controlledError, onClose }: UpgradeModalProps) => {
  const [isOpen, setIsOpen] = useState(false)
  const [error, setError] = useState<LimitExceededError | null>(null)
  const [tiers, setTiers] = useState<SubscriptionTier[]>([])
  const [loading, setLoading] = useState(false)

  // Handle controlled mode
  useEffect(() => {
    if (controlledError) {
      setError(controlledError)
      setIsOpen(true)
    }
  }, [controlledError])

  // Listen for limit-exceeded events
  useEffect(() => {
    const handleLimitExceeded = (event: CustomEvent<LimitExceededError>) => {
      setError(event.detail)
      setIsOpen(true)
    }

    window.addEventListener('limit-exceeded', handleLimitExceeded as EventListener)
    return () => {
      window.removeEventListener('limit-exceeded', handleLimitExceeded as EventListener)
    }
  }, [])

  // Fetch tiers when modal opens
  useEffect(() => {
    if (isOpen && tiers.length === 0) {
      setLoading(true)
      Promise.resolve(subscriptionAPI.listTiers())
        .then(res => {
          setTiers(res.data.tiers)
        })
        .catch(console.error)
        .finally(() => setLoading(false))
    }
  }, [isOpen, tiers.length])

  const handleClose = useCallback(() => {
    setIsOpen(false)
    setError(null)
    onClose?.()
  }, [onClose])

  if (!isOpen) return null

  const featureName = error?.feature || error?.resource || 'feature'
  const featureLabel = FEATURE_LABELS[featureName] || featureName.replace(/_/g, ' ')
  const freeTier = tiers.find(t => t.id === 'free')
  const proTier = tiers.find(t => t.id === 'pro')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-gray-900/50 backdrop-blur-sm dark:bg-black/60"
        aria-hidden="true"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg rounded-2xl bg-white shadow-2xl transition-all duration-200 dark:bg-slate-800 animate-in fade-in zoom-in-95">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100 dark:border-slate-700">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-amber-400 to-orange-500">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">
                Upgrade to Pro
              </h2>
              <p className="text-sm text-gray-500 dark:text-slate-400">
                Unlock more features
              </p>
            </div>
          </div>
          <button
            onClick={handleClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Limit exceeded warning */}
        {error && (
          <div className="mx-6 mt-5 flex items-start gap-3 rounded-lg bg-amber-50 p-4 dark:bg-amber-500/10">
            <AlertCircle className="h-5 w-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                You've reached your {featureLabel.toLowerCase()} limit
              </p>
              <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">
                {error.current} / {error.limit} used on the {error.tier} plan
              </p>
            </div>
          </div>
        )}

        {/* Tier comparison */}
        <div className="px-6 py-5">
          {loading ? (
            <div className="flex justify-center py-8">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-500 border-t-transparent" />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              {/* Free tier */}
              <div className="rounded-xl border border-gray-200 p-4 dark:border-slate-700">
                <h3 className="font-semibold text-gray-900 dark:text-slate-100">Free</h3>
                <p className="text-2xl font-bold text-gray-900 dark:text-slate-100 mt-1">$0</p>
                <p className="text-xs text-gray-500 dark:text-slate-400">per month</p>
                <ul className="mt-4 space-y-2 text-sm">
                  {freeTier && Object.entries(freeTier.limits).map(([key, value]) => (
                    <li key={key} className="flex items-center gap-2 text-gray-600 dark:text-slate-300">
                      <Check className="h-4 w-4 text-gray-400 dark:text-slate-500" />
                      <span>{value === -1 ? 'Unlimited' : value} {FEATURE_LABELS[key]?.replace(/^[A-Z]/, c => c.toLowerCase()) || key}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Pro tier */}
              <div className="rounded-xl border-2 border-primary-500 bg-primary-50 p-4 dark:bg-primary-500/10 relative">
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary-500 text-white text-xs font-medium px-2 py-0.5 rounded-full">
                  Recommended
                </div>
                <h3 className="font-semibold text-gray-900 dark:text-slate-100">Pro</h3>
                <p className="text-2xl font-bold text-gray-900 dark:text-slate-100 mt-1">
                  ${proTier ? (proTier.price_monthly_cents / 100).toFixed(0) : '15'}
                </p>
                <p className="text-xs text-gray-500 dark:text-slate-400">per month</p>
                <ul className="mt-4 space-y-2 text-sm">
                  {proTier && Object.entries(proTier.limits).map(([key, value]) => (
                    <li key={key} className="flex items-center gap-2 text-gray-700 dark:text-slate-200">
                      <Check className="h-4 w-4 text-primary-500" />
                      <span className={key === featureName ? 'font-semibold text-primary-600 dark:text-primary-400' : ''}>
                        {value === -1 ? 'Unlimited' : value} {FEATURE_LABELS[key]?.replace(/^[A-Z]/, c => c.toLowerCase()) || key}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="px-6 pb-6">
          <button
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary-500 to-primary-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-primary-500/25 transition-all hover:from-primary-600 hover:to-primary-700 hover:shadow-xl hover:shadow-primary-500/30"
            onClick={() => {
              // TODO: Integrate with Stripe checkout
              window.open('mailto:support@scholarhub.app?subject=Upgrade%20to%20Pro', '_blank')
            }}
          >
            <Sparkles className="h-4 w-4" />
            Upgrade to Pro
          </button>
          <p className="mt-3 text-center text-xs text-gray-500 dark:text-slate-400">
            Contact us to upgrade. Stripe integration coming soon.
          </p>
        </div>
      </div>
    </div>
  )
}

export default UpgradeModal
