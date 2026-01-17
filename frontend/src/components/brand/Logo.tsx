interface LogoIconProps {
  className?: string
  variant?: 'gradient' | 'white' | 'dark'
  animate?: boolean
}

export const LogoIcon = ({ className = 'h-6 w-6', variant = 'gradient', animate = true }: LogoIconProps) => {
  const gradientId = `logo-grad-${Math.random().toString(36).substr(2, 9)}`

  const getColor = () => {
    switch (variant) {
      case 'white':
        return 'white'
      case 'dark':
        return '#1e293b'
      default:
        return `url(#${gradientId})`
    }
  }

  const fill = getColor()

  return (
    <>
      <style>{`
        @keyframes compass-wobble {
          0%, 100% { transform: rotate(0deg); }
          25% { transform: rotate(8deg); }
          75% { transform: rotate(-8deg); }
        }
        .animate-compass-wobble {
          animation: compass-wobble 2s ease-in-out infinite;
          transform-origin: center;
        }
      `}</style>
      <svg
        viewBox="0 0 48 48"
        className={`${className} ${animate ? 'animate-compass-wobble' : ''}`}
        fill="none"
      >
        {variant === 'gradient' && (
          <defs>
            <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#a855f7" />
            </linearGradient>
          </defs>
        )}
        {/* North point */}
        <path d="M24 2L29 20L24 24L19 20Z" fill={fill} />
        {/* East point */}
        <path d="M46 24L28 29L24 24L28 19Z" fill={fill} fillOpacity="0.75" />
        {/* South point */}
        <path d="M24 46L19 28L24 24L29 28Z" fill={fill} fillOpacity="0.5" />
        {/* West point */}
        <path d="M2 24L20 19L24 24L20 29Z" fill={fill} fillOpacity="0.35" />
        {/* Center */}
        <circle cx="24" cy="24" r="4" fill={fill} />
      </svg>
    </>
  )
}

interface LogoProps {
  className?: string
  iconClassName?: string
  textClassName?: string
  showText?: boolean
}

export const Logo = ({
  className = '',
  iconClassName = 'h-10 w-10',
  textClassName = 'text-xl font-bold',
  showText = true
}: LogoProps) => {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <LogoIcon className={iconClassName} variant="gradient" />
      {showText && (
        <span className={`bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300 bg-clip-text text-transparent ${textClassName}`}>
          ScholarHub
        </span>
      )}
    </div>
  )
}

export default Logo
