import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Check,
  X,
  Sparkles,
  Crown,
  Zap,
  BookOpen,
  Users,
  FolderOpen,
  MessageSquare,
  Search,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Key
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { subscriptionAPI } from '../services/api'
import { SubscriptionTier } from '../types'

const Pricing = () => {
  const navigate = useNavigate()
  const { user, subscription: subState } = useAuth()
  const [tiers, setTiers] = useState<SubscriptionTier[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedFaq, setExpandedFaq] = useState<number | null>(null)

  const currentTier = subState.subscription?.tier_id

  useEffect(() => {
    Promise.resolve(subscriptionAPI.listTiers())
      .then(res => setTiers(res.data.tiers))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const freeTier = tiers.find(t => t.id === 'free')
  const proTier = tiers.find(t => t.id === 'pro')

  const features = [
    {
      name: 'AI Discussion Calls',
      description: 'Ask AI questions about your research',
      icon: MessageSquare,
      free: freeTier?.limits.discussion_ai_calls || 20,
      pro: proTier?.limits.discussion_ai_calls || 500,
      unit: '/month'
    },
    {
      name: 'Paper Discovery Searches',
      description: 'Find relevant papers across multiple sources',
      icon: Search,
      free: freeTier?.limits.paper_discovery_searches || 10,
      pro: proTier?.limits.paper_discovery_searches || 200,
      unit: '/month'
    },
    {
      name: 'Projects',
      description: 'Organize your research into projects',
      icon: FolderOpen,
      free: freeTier?.limits.projects || 3,
      pro: proTier?.limits.projects || 25,
      unit: ''
    },
    {
      name: 'Papers per Project',
      description: 'Documents you can add to each project',
      icon: BookOpen,
      free: freeTier?.limits.papers_per_project || 10,
      pro: proTier?.limits.papers_per_project || 100,
      unit: ''
    },
    {
      name: 'Collaborators per Project',
      description: 'Team members you can invite',
      icon: Users,
      free: freeTier?.limits.collaborators_per_project || 2,
      pro: proTier?.limits.collaborators_per_project || 10,
      unit: ''
    },
    {
      name: 'References Library',
      description: 'Total references you can save',
      icon: BookOpen,
      free: freeTier?.limits.references_total || 50,
      pro: proTier?.limits.references_total || 500,
      unit: ' total'
    },
  ]

  const faqs = [
    {
      question: 'When will the Pro plan be available?',
      answer: 'We\'re working on launching the Pro plan soon. Sign up for notifications and we\'ll let you know as soon as it\'s ready.'
    },
    {
      question: 'What happens when I hit my limit?',
      answer: 'You\'ll see a prompt to upgrade to Pro. Your existing work is never deleted - you just can\'t create new items until you upgrade or wait for the monthly reset.'
    },
    {
      question: 'Do limits reset every month?',
      answer: 'Yes, AI calls and paper searches reset on the 1st of each month. Project and reference limits are total counts, not monthly.'
    },
    {
      question: 'Is the free plan really free?',
      answer: 'Yes, the free plan is completely free with no credit card required. You can also use BYOK (Bring Your Own Key) to get unlimited AI calls at your own API cost.'
    },
    {
      question: 'Is my data secure?',
      answer: 'Absolutely. We use industry-standard encryption and never share your research data with third parties.'
    },
  ]

  const [showProInterest, setShowProInterest] = useState(false)

  const handleUpgrade = () => {
    if (!user) {
      navigate('/login?redirect=/pricing')
      return
    }
    setShowProInterest(true)
  }

  const handleGetStarted = () => {
    if (!user) {
      navigate('/register')
    } else {
      navigate('/projects')
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white dark:from-slate-900 dark:to-slate-800">
      {/* Header */}
      <header className="border-b border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 text-xl font-bold text-slate-900 dark:text-white"
          >
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center">
              <BookOpen className="h-5 w-5 text-white" />
            </div>
            ScholarHub
          </button>
          <div className="flex items-center gap-3">
            {user ? (
              <button
                onClick={() => navigate('/projects')}
                className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"
              >
                Dashboard
              </button>
            ) : (
              <>
                <button
                  onClick={() => navigate('/login')}
                  className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"
                >
                  Sign in
                </button>
                <button
                  onClick={() => navigate('/register')}
                  className="px-4 py-2 text-sm font-medium text-white bg-primary-500 rounded-lg hover:bg-primary-600"
                >
                  Get Started
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="pt-16 pb-12 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary-100 dark:bg-primary-500/20 text-primary-700 dark:text-primary-300 text-sm font-medium mb-6">
            <Sparkles className="h-4 w-4" />
            Simple, transparent pricing
          </div>
          <h1 className="text-4xl md:text-5xl font-bold text-slate-900 dark:text-white mb-4">
            Supercharge Your Research
          </h1>
          <p className="text-xl text-slate-600 dark:text-slate-300 max-w-2xl mx-auto">
            Start free and upgrade when you need more power. No hidden fees, cancel anytime.
          </p>
        </div>
      </section>

      {/* Pricing Cards */}
      <section className="pb-16 px-4">
        <div className="max-w-5xl mx-auto">
          {loading ? (
            <div className="flex justify-center py-12">
              <div className="h-10 w-10 animate-spin rounded-full border-2 border-primary-500 border-t-transparent" />
            </div>
          ) : (
            <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
              {/* Free Tier */}
              <div className="relative rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-8 shadow-sm">
                {currentTier === 'free' && (
                  <div className="absolute -top-3 left-6 px-3 py-1 bg-slate-200 dark:bg-slate-600 text-slate-700 dark:text-slate-200 text-xs font-medium rounded-full">
                    Current Plan
                  </div>
                )}
                <div className="mb-6">
                  <h3 className="text-xl font-semibold text-slate-900 dark:text-white mb-2">Free</h3>
                  <p className="text-slate-500 dark:text-slate-400 text-sm">Perfect for getting started</p>
                </div>
                <div className="mb-6">
                  <span className="text-4xl font-bold text-slate-900 dark:text-white">$0</span>
                  <span className="text-slate-500 dark:text-slate-400">/month</span>
                </div>
                <button
                  onClick={handleGetStarted}
                  disabled={currentTier === 'free'}
                  className="w-full py-3 px-4 rounded-xl border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 font-medium hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {currentTier === 'free' ? 'Current Plan' : 'Get Started Free'}
                </button>
                <ul className="mt-8 space-y-4">
                  {features.map((feature) => (
                    <li key={feature.name} className="flex items-start gap-3">
                      <Check className="h-5 w-5 text-slate-400 dark:text-slate-500 flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-slate-600 dark:text-slate-300">
                        <strong>{feature.free}</strong>{feature.unit} {feature.name.toLowerCase()}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Pro Tier */}
              <div className="relative rounded-2xl border-2 border-primary-500 bg-white dark:bg-slate-800 p-8 shadow-xl shadow-primary-500/10">
                <div className="absolute -top-3 left-6 px-3 py-1 bg-gradient-to-r from-amber-400 to-orange-500 text-white text-xs font-medium rounded-full flex items-center gap-1">
                  <Crown className="h-3 w-3" />
                  Coming Soon
                </div>
                {currentTier === 'pro' && (
                  <div className="absolute -top-3 right-6 px-3 py-1 bg-green-500 text-white text-xs font-medium rounded-full">
                    Current Plan
                  </div>
                )}
                <div className="mb-6">
                  <h3 className="text-xl font-semibold text-slate-900 dark:text-white mb-2 flex items-center gap-2">
                    Pro
                    <Zap className="h-5 w-5 text-amber-500" />
                  </h3>
                  <p className="text-slate-500 dark:text-slate-400 text-sm">For serious researchers</p>
                </div>
                <div className="mb-6">
                  <span className="text-4xl font-bold text-slate-900 dark:text-white">$15</span>
                  <span className="text-slate-500 dark:text-slate-400">/month</span>
                </div>
                <button
                  onClick={handleUpgrade}
                  disabled={currentTier === 'pro'}
                  className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-primary-500 to-primary-600 text-white font-medium hover:from-primary-600 hover:to-primary-700 transition-all shadow-lg shadow-primary-500/25 hover:shadow-xl hover:shadow-primary-500/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {currentTier === 'pro' ? (
                    'Current Plan'
                  ) : (
                    <>
                      Coming Soon — Notify Me
                      <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </button>
                <ul className="mt-8 space-y-4">
                  {features.map((feature) => (
                    <li key={feature.name} className="flex items-start gap-3">
                      <Check className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-slate-600 dark:text-slate-300">
                        <strong className="text-primary-600 dark:text-primary-400">{feature.pro}</strong>{feature.unit} {feature.name.toLowerCase()}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* BYOK Tier */}
              <div className="relative rounded-2xl border-2 border-emerald-500 bg-white dark:bg-slate-800 p-8 shadow-xl shadow-emerald-500/10">
                <div className="absolute -top-3 left-6 px-3 py-1 bg-gradient-to-r from-emerald-400 to-teal-500 text-white text-xs font-medium rounded-full flex items-center gap-1">
                  <Key className="h-3 w-3" />
                  Unlimited AI
                </div>
                {currentTier === 'byok' && (
                  <div className="absolute -top-3 right-6 px-3 py-1 bg-green-500 text-white text-xs font-medium rounded-full">
                    Current Plan
                  </div>
                )}
                <div className="mb-6">
                  <h3 className="text-xl font-semibold text-slate-900 dark:text-white mb-2 flex items-center gap-2">
                    BYOK
                    <Key className="h-5 w-5 text-emerald-500" />
                  </h3>
                  <p className="text-slate-500 dark:text-slate-400 text-sm">Bring Your Own API Key</p>
                </div>
                <div className="mb-6">
                  <span className="text-4xl font-bold text-slate-900 dark:text-white">$0</span>
                  <span className="text-slate-500 dark:text-slate-400"> + your API costs</span>
                </div>
                <button
                  onClick={() => navigate('/profile')}
                  disabled={currentTier === 'byok'}
                  className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 text-white font-medium hover:from-emerald-600 hover:to-teal-700 transition-all shadow-lg shadow-emerald-500/25 hover:shadow-xl hover:shadow-emerald-500/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {currentTier === 'byok' ? (
                    'Current Plan'
                  ) : (
                    <>
                      Add Your API Key
                      <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </button>
                <ul className="mt-8 space-y-4">
                  <li className="flex items-start gap-3">
                    <Check className="h-5 w-5 text-emerald-500 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-slate-600 dark:text-slate-300">
                      <strong className="text-emerald-600 dark:text-emerald-400">Unlimited</strong> AI discussion calls
                    </span>
                  </li>
                  <li className="flex items-start gap-3">
                    <Check className="h-5 w-5 text-emerald-500 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-slate-600 dark:text-slate-300">
                      <strong className="text-emerald-600 dark:text-emerald-400">All models</strong> via OpenRouter
                    </span>
                  </li>
                  <li className="flex items-start gap-3">
                    <Check className="h-5 w-5 text-emerald-500 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-slate-600 dark:text-slate-300">
                      Same limits as <strong className="text-emerald-600 dark:text-emerald-400">Free</strong> for projects & refs
                    </span>
                  </li>
                  <li className="flex items-start gap-3">
                    <Check className="h-5 w-5 text-emerald-500 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-slate-600 dark:text-slate-300">
                      <strong className="text-emerald-600 dark:text-emerald-400">You control</strong> your API spend
                    </span>
                  </li>
                </ul>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Feature Comparison Table */}
      <section className="py-16 px-4 bg-slate-50 dark:bg-slate-800/50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white text-center mb-8">
            Compare Plans
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-700">
                  <th className="text-left py-4 px-4 text-sm font-medium text-slate-500 dark:text-slate-400">Feature</th>
                  <th className="text-center py-4 px-4 text-sm font-medium text-slate-500 dark:text-slate-400">Free</th>
                  <th className="text-center py-4 px-4 text-sm font-medium text-slate-500 dark:text-slate-400">
                    <span className="inline-flex items-center gap-1">
                      Pro <Crown className="h-3 w-3 text-amber-500" />
                    </span>
                  </th>
                  <th className="text-center py-4 px-4 text-sm font-medium text-slate-500 dark:text-slate-400">
                    <span className="inline-flex items-center gap-1">
                      BYOK <Key className="h-3 w-3 text-emerald-500" />
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {features.map((feature, i) => (
                  <tr key={feature.name} className={i % 2 === 0 ? 'bg-white dark:bg-slate-800' : ''}>
                    <td className="py-4 px-4">
                      <div className="flex items-center gap-3">
                        <feature.icon className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                        <div>
                          <div className="text-sm font-medium text-slate-900 dark:text-white">{feature.name}</div>
                          <div className="text-xs text-slate-500 dark:text-slate-400">{feature.description}</div>
                        </div>
                      </div>
                    </td>
                    <td className="text-center py-4 px-4 text-sm text-slate-600 dark:text-slate-300">
                      {feature.free}{feature.unit}
                    </td>
                    <td className="text-center py-4 px-4 text-sm font-medium text-primary-600 dark:text-primary-400">
                      {feature.pro}{feature.unit}
                    </td>
                    <td className="text-center py-4 px-4 text-sm text-slate-600 dark:text-slate-300">
                      {feature.name === 'AI Discussion Calls' ? (
                        <strong className="text-emerald-600 dark:text-emerald-400">Unlimited</strong>
                      ) : (
                        <>{feature.free}{feature.unit}</>
                      )}
                    </td>
                  </tr>
                ))}
                <tr className="bg-white dark:bg-slate-800">
                  <td className="py-4 px-4">
                    <div className="flex items-center gap-3">
                      <Sparkles className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                      <div>
                        <div className="text-sm font-medium text-slate-900 dark:text-white">Priority Support</div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">Get help when you need it</div>
                      </div>
                    </div>
                  </td>
                  <td className="text-center py-4 px-4">
                    <X className="h-5 w-5 text-slate-300 dark:text-slate-600 mx-auto" />
                  </td>
                  <td className="text-center py-4 px-4">
                    <Check className="h-5 w-5 text-primary-500 mx-auto" />
                  </td>
                  <td className="text-center py-4 px-4">
                    <X className="h-5 w-5 text-slate-300 dark:text-slate-600 mx-auto" />
                  </td>
                </tr>
                <tr>
                  <td className="py-4 px-4">
                    <div className="flex items-center gap-3">
                      <Zap className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                      <div>
                        <div className="text-sm font-medium text-slate-900 dark:text-white">Early Access Features</div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">Try new features first</div>
                      </div>
                    </div>
                  </td>
                  <td className="text-center py-4 px-4">
                    <X className="h-5 w-5 text-slate-300 dark:text-slate-600 mx-auto" />
                  </td>
                  <td className="text-center py-4 px-4">
                    <Check className="h-5 w-5 text-primary-500 mx-auto" />
                  </td>
                  <td className="text-center py-4 px-4">
                    <X className="h-5 w-5 text-slate-300 dark:text-slate-600 mx-auto" />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="py-16 px-4">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white text-center mb-8">
            Frequently Asked Questions
          </h2>
          <div className="space-y-3">
            {faqs.map((faq, i) => (
              <div
                key={i}
                className="border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden"
              >
                <button
                  onClick={() => setExpandedFaq(expandedFaq === i ? null : i)}
                  className="w-full flex items-center justify-between p-4 text-left bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors"
                >
                  <span className="font-medium text-slate-900 dark:text-white">{faq.question}</span>
                  {expandedFaq === i ? (
                    <ChevronUp className="h-5 w-5 text-slate-400" />
                  ) : (
                    <ChevronDown className="h-5 w-5 text-slate-400" />
                  )}
                </button>
                {expandedFaq === i && (
                  <div className="px-4 pb-4 bg-white dark:bg-slate-800">
                    <p className="text-slate-600 dark:text-slate-300 text-sm">{faq.answer}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-16 px-4 bg-gradient-to-r from-primary-500 to-primary-600">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-2xl md:text-3xl font-bold text-white mb-4">
            Ready to accelerate your research?
          </h2>
          <p className="text-primary-100 mb-8">
            Start using ScholarHub to discover, organize, and write better papers.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <button
              onClick={handleGetStarted}
              className="px-6 py-3 bg-white text-primary-600 font-medium rounded-xl hover:bg-primary-50 transition-colors"
            >
              Start Free
            </button>
            <button
              onClick={handleUpgrade}
              className="px-6 py-3 bg-primary-700 text-white font-medium rounded-xl hover:bg-primary-800 transition-colors flex items-center justify-center gap-2"
            >
              <Crown className="h-4 w-4" />
              Pro — Coming Soon
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-4 border-t border-slate-200 dark:border-slate-700">
        <div className="max-w-6xl mx-auto text-center text-sm text-slate-500 dark:text-slate-400">
          © {new Date().getFullYear()} ScholarHub. All rights reserved.
        </div>
      </footer>

      {/* Pro Interest Modal */}
      {showProInterest && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-8 max-w-md mx-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="h-10 w-10 rounded-full bg-primary-100 dark:bg-primary-500/20 flex items-center justify-center">
                <Crown className="h-5 w-5 text-primary-500" />
              </div>
              <h3 className="text-xl font-bold text-slate-900 dark:text-white">Pro Plan — Coming Soon</h3>
            </div>
            <p className="text-slate-600 dark:text-slate-300 mb-6">
              We are still building the Pro plan. In the meantime, you can use the free plan or bring your own API key for unlimited AI calls. We will notify you when Pro is available.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowProInterest(false)}
                className="flex-1 py-2.5 px-4 rounded-xl border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 font-medium hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
              >
                Close
              </button>
              <button
                onClick={() => {
                  setShowProInterest(false)
                  navigate('/profile')
                }}
                className="flex-1 py-2.5 px-4 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 text-white font-medium hover:from-emerald-600 hover:to-teal-700 transition-all flex items-center justify-center gap-2"
              >
                <Key className="h-4 w-4" />
                Try BYOK Instead
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Pricing
