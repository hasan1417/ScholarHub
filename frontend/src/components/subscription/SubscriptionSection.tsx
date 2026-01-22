import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, Crown, ArrowRight, Zap } from 'lucide-react'
import { subscriptionAPI } from '../../services/api'

interface SubscriptionResponse {
  subscription: {
    tier_id: string
    tier_name: string
    status: string
    limits: Record<string, number>
    usage: {
      discussion_ai_calls: number
      paper_discovery_searches: number
    }
  } | null
  resource_counts: {
    projects: number
    references_total: number
  }
}

const SubscriptionSection = () => {
  const navigate = useNavigate()
  const [data, setData] = useState<SubscriptionResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await subscriptionAPI.getMySubscription()
        setData(res.data as SubscriptionResponse)
      } catch (err) {
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  if (loading) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-slate-300">
          <Zap className="h-4 w-4" />
          <span>Subscription</span>
        </div>
        <div className="animate-pulse h-20 bg-gray-100 dark:bg-slate-700 rounded-xl" />
      </div>
    )
  }

  const tier = data?.subscription?.tier_id || 'free'
  const isPro = tier === 'pro'
  const limits = data?.subscription?.limits || {}
  const usage = data?.subscription?.usage || { discussion_ai_calls: 0, paper_discovery_searches: 0 }

  // Get actual limits from API
  const aiLimit = limits.discussion_ai_calls || 20
  const aiUsed = usage.discussion_ai_calls || 0

  if (isPro) {
    // Pro user - show tier badge only (they have generous limits)
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-slate-300">
          <Zap className="h-4 w-4" />
          <span>Subscription</span>
        </div>
        <div className="flex items-center gap-3 rounded-xl bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-500/10 dark:to-orange-500/10 border border-amber-200 dark:border-amber-500/20 p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-amber-400 to-orange-500 shadow-md">
            <Crown className="h-5 w-5 text-white" />
          </div>
          <div className="flex-1">
            <div className="font-semibold text-amber-900 dark:text-amber-200">Pro Plan</div>
            <div className="text-sm text-amber-700 dark:text-amber-300/70">
              Full access to all features
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Free user - show upgrade prompt with usage info
  const aiPercentage = aiLimit > 0 ? Math.min(100, Math.round((aiUsed / aiLimit) * 100)) : 0

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-slate-300">
        <Zap className="h-4 w-4" />
        <span>Subscription</span>
      </div>

      {/* Current plan info */}
      <div className="rounded-xl border border-gray-200 dark:border-slate-700 p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="font-medium text-gray-900 dark:text-slate-100">Free Plan</div>
            <div className="text-sm text-gray-500 dark:text-slate-400">
              {aiUsed} / {aiLimit} AI calls used this month
            </div>
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-slate-100">$0</div>
        </div>

        {/* Usage bar */}
        <div className="h-2 bg-gray-100 dark:bg-slate-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              aiPercentage >= 80 ? 'bg-red-500' : aiPercentage >= 50 ? 'bg-amber-500' : 'bg-primary-500'
            }`}
            style={{ width: `${aiPercentage}%` }}
          />
        </div>
        {aiPercentage >= 80 && (
          <p className="mt-2 text-xs text-red-600 dark:text-red-400">
            Running low on AI calls this month
          </p>
        )}
      </div>

      {/* Upgrade CTA */}
      <button
        onClick={() => navigate('/pricing')}
        className="w-full group flex items-center justify-between gap-3 rounded-xl bg-gradient-to-r from-primary-500 to-primary-600 p-4 text-white shadow-lg shadow-primary-500/25 transition-all hover:from-primary-600 hover:to-primary-700 hover:shadow-xl"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/20">
            <Sparkles className="h-5 w-5" />
          </div>
          <div className="text-left">
            <div className="font-semibold">Upgrade to Pro</div>
            <div className="text-sm text-primary-100">500 AI calls/month + more</div>
          </div>
        </div>
        <ArrowRight className="h-5 w-5 group-hover:translate-x-1 transition-transform" />
      </button>
    </div>
  )
}

export default SubscriptionSection
