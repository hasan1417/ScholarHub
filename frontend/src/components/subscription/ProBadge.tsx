import { Crown, Sparkles, Lock } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

interface ProBadgeProps {
  variant?: 'badge' | 'tag' | 'locked' | 'inline'
  label?: string
  showUpgradeLink?: boolean
  className?: string
}

const ProBadge = ({
  variant = 'badge',
  label = 'Pro',
  showUpgradeLink = true,
  className = '',
}: ProBadgeProps) => {
  const navigate = useNavigate()

  if (variant === 'locked') {
    return (
      <button
        onClick={() => navigate('/pricing')}
        className={`group flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 hover:border-primary-300 dark:hover:border-primary-500 transition-colors ${className}`}
      >
        <Lock className="h-4 w-4 text-slate-400 dark:text-slate-500 group-hover:text-primary-500" />
        <span className="text-sm text-slate-500 dark:text-slate-400 group-hover:text-primary-600 dark:group-hover:text-primary-400">
          Pro feature
        </span>
      </button>
    )
  }

  if (variant === 'tag') {
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-gradient-to-r from-amber-100 to-orange-100 dark:from-amber-500/20 dark:to-orange-500/20 text-amber-700 dark:text-amber-300 text-xs font-medium ${className}`}>
        <Crown className="h-3 w-3" />
        {label}
      </span>
    )
  }

  if (variant === 'inline') {
    return (
      <span className={`inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 ${className}`}>
        <Sparkles className="h-3 w-3" />
        <span className="text-xs font-medium">{label}</span>
      </span>
    )
  }

  // Default badge variant
  return (
    <div
      onClick={showUpgradeLink ? () => navigate('/pricing') : undefined}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gradient-to-r from-amber-400 to-orange-500 text-white text-xs font-semibold shadow-sm ${showUpgradeLink ? 'cursor-pointer hover:from-amber-500 hover:to-orange-600 transition-colors' : ''} ${className}`}
    >
      <Crown className="h-3 w-3" />
      {label}
    </div>
  )
}

export default ProBadge
