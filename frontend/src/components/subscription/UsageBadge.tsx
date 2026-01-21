import { Sparkles } from 'lucide-react'

interface UsageBadgeProps {
  current: number
  limit: number
  label?: string
  showLabel?: boolean
  size?: 'sm' | 'md'
  className?: string
}

const UsageBadge = ({
  current,
  limit,
  label,
  showLabel = true,
  size = 'md',
  className = '',
}: UsageBadgeProps) => {
  // Calculate percentage and status
  const isUnlimited = limit === -1
  const percentage = isUnlimited ? 0 : Math.min((current / limit) * 100, 100)
  const isNearLimit = !isUnlimited && percentage >= 80
  const isAtLimit = !isUnlimited && current >= limit

  // Determine colors based on status
  const getColors = () => {
    if (isAtLimit) {
      return {
        bg: 'bg-red-100 dark:bg-red-500/20',
        progress: 'bg-red-500',
        text: 'text-red-600 dark:text-red-400',
      }
    }
    if (isNearLimit) {
      return {
        bg: 'bg-amber-100 dark:bg-amber-500/20',
        progress: 'bg-amber-500',
        text: 'text-amber-600 dark:text-amber-400',
      }
    }
    return {
      bg: 'bg-gray-100 dark:bg-slate-700',
      progress: 'bg-primary-500',
      text: 'text-gray-600 dark:text-slate-300',
    }
  }

  const colors = getColors()

  const sizeClasses = {
    sm: {
      container: 'text-xs',
      bar: 'h-1',
      minWidth: 'min-w-[60px]',
    },
    md: {
      container: 'text-sm',
      bar: 'h-1.5',
      minWidth: 'min-w-[80px]',
    },
  }

  const sizes = sizeClasses[size]

  return (
    <div className={`inline-flex items-center gap-2 ${sizes.container} ${className}`}>
      {showLabel && label && (
        <span className="text-gray-500 dark:text-slate-400">{label}</span>
      )}
      <div className="flex items-center gap-1.5">
        <div className={`${sizes.minWidth} ${colors.bg} rounded-full overflow-hidden`}>
          <div
            className={`${sizes.bar} ${colors.progress} transition-all duration-300`}
            style={{ width: isUnlimited ? '100%' : `${percentage}%` }}
          />
        </div>
        <span className={`font-medium ${colors.text}`}>
          {isUnlimited ? (
            <span className="flex items-center gap-0.5">
              <Sparkles className="h-3 w-3" />
            </span>
          ) : (
            `${current}/${limit}`
          )}
        </span>
      </div>
    </div>
  )
}

export default UsageBadge
