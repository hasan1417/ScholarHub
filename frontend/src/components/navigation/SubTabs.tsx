import { NavLink } from 'react-router-dom'
import { LucideIcon } from 'lucide-react'

export interface SubTab {
  label: string
  path: string
  icon: LucideIcon
  badge?: number
  tooltip?: string
}

interface SubTabsProps {
  tabs: SubTab[]
  basePath: string
}

const SubTabs = ({ tabs, basePath }: SubTabsProps) => {
  return (
    <div className="border-b border-gray-200 bg-white">
      <nav className="flex gap-6 px-6">
        {tabs.map((tab) => (
          <NavLink
            key={tab.path}
            to={`${basePath}/${tab.path}`}
            end
            title={tab.tooltip}
            className={({ isActive }) =>
              `flex items-center gap-2 border-b-2 px-1 py-3 text-sm font-medium transition-colors ${
                isActive
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'
              }`
            }
          >
            <tab.icon className="h-4 w-4" />
            <span>{tab.label}</span>
            {tab.badge !== undefined && tab.badge > 0 && (
              <span className="ml-1 inline-flex items-center justify-center rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-600">
                {tab.badge}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

export default SubTabs
