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
    <div className="border-b border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800">
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
                  ? 'border-indigo-600 dark:border-indigo-400 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-gray-500 dark:text-slate-400 hover:border-gray-300 dark:hover:border-slate-500 hover:text-gray-700 dark:hover:text-slate-200'
              }`
            }
          >
            <tab.icon className="h-4 w-4" />
            <span>{tab.label}</span>
            {tab.badge !== undefined && tab.badge > 0 && (
              <span className="ml-1 inline-flex items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900/40 px-2 py-0.5 text-xs font-medium text-indigo-600 dark:text-indigo-300">
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
