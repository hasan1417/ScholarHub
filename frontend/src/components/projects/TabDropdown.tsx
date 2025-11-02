import React, { useState, useRef, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ChevronDown, LucideIcon } from 'lucide-react'

interface TabDropdownItem {
  label: string
  path: string
  icon?: LucideIcon
  badge?: number
  tooltip?: string
}

interface TabDropdownProps {
  label: string
  icon?: LucideIcon
  items: TabDropdownItem[]
  projectId: string
}

const TabDropdown: React.FC<TabDropdownProps> = ({ label, icon: Icon, items, projectId }) => {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const location = useLocation()

  // Create a unique key for localStorage based on project and dropdown
  const storageKey = `dropdown-${projectId}-${label.toLowerCase()}`

  // Track the previous count to detect increases - persist in localStorage
  const [prevCount, setPrevCount] = useState<number>(() => {
    const stored = localStorage.getItem(`${storageKey}-count`)
    return stored ? parseInt(stored, 10) : 0
  })

  // Track if user has viewed the current papers - persist in localStorage
  const [hasViewed, setHasViewed] = useState<boolean>(() => {
    const stored = localStorage.getItem(`${storageKey}-viewed`)
    return stored === 'true'
  })

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Check if any child item is active
  const hasActiveChild = items.some(item =>
    location.pathname.includes(item.path)
  )

  // Calculate total badge count
  const totalBadgeCount = items.reduce((sum, item) => sum + (item.badge || 0), 0)

  // Track when user navigates to/from Find Papers page
  const isOnFindPapers = items.some(item => item.badge && item.badge > 0 && location.pathname.includes(item.path))

  useEffect(() => {
    // When user visits Find Papers, mark as viewed
    if (isOnFindPapers) {
      setHasViewed(true)
      setPrevCount(totalBadgeCount)
      localStorage.setItem(`${storageKey}-viewed`, 'true')
      localStorage.setItem(`${storageKey}-count`, totalBadgeCount.toString())
    }
  }, [isOnFindPapers, totalBadgeCount, storageKey])

  useEffect(() => {
    // If count increased, mark as not viewed (new papers arrived)
    if (totalBadgeCount > prevCount && prevCount > 0) {
      setHasViewed(false)
      localStorage.setItem(`${storageKey}-viewed`, 'false')
    }
    setPrevCount(totalBadgeCount)
    localStorage.setItem(`${storageKey}-count`, totalBadgeCount.toString())
  }, [totalBadgeCount, prevCount, storageKey])

  // Show notification if:
  // 1. There are badges AND user hasn't viewed them yet
  const hasNotifications = totalBadgeCount > 0 && !hasViewed

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Dropdown Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 transition-colors ${
          hasActiveChild || isOpen
            ? 'bg-indigo-600 text-white'
            : 'text-gray-500 hover:bg-gray-100'
        }`}
      >
        {Icon && <Icon className="h-4 w-4" />}
        <span>{label}</span>
        <ChevronDown
          className={`h-3.5 w-3.5 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>
      {hasNotifications && (
        <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-red-500 shadow-sm ring-2 ring-white pointer-events-none" />
      )}

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute left-0 top-full mt-1 min-w-[200px] rounded-lg border border-gray-200 bg-white py-1 shadow-lg z-50">
          {items.map((item) => {
            const ItemIcon = item.icon
            const isActive = location.pathname.includes(item.path)

            return (
              <Link
                key={item.path}
                to={`/projects/${projectId}${item.path}`}
                title={item.tooltip}
                onClick={() => setIsOpen(false)}
                className={`flex items-center gap-2 px-4 py-2 text-sm transition-colors ${
                  isActive
                    ? 'bg-indigo-50 text-indigo-700 font-medium'
                    : 'text-gray-700 hover:bg-gray-50'
                }`}
              >
                <div className="relative inline-flex items-center gap-2">
                  {ItemIcon && <ItemIcon className="h-4 w-4" />}
                  <span className="flex-1">{item.label}</span>
                  {item.badge && item.badge > 0 && !hasViewed && (
                    <span
                      className="h-2 w-2 rounded-full bg-red-500 shadow-sm"
                      title={`${item.badge} new item${item.badge === 1 ? '' : 's'}`}
                    />
                  )}
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default TabDropdown
