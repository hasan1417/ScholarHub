import { useState } from 'react'
import {
  FileText,
  Target,
  Tag,
  Users,
  Clock,
  LayoutGrid,
  Columns,
  LayoutList,
  PanelTop,
  Sparkles,
} from 'lucide-react'

const mockProject = {
  description: "Investigate how deep learning models can accelerate the identification of potential drug candidates by predicting molecular properties and drug-target interactions.",
  objectives: [
    "Analyzing datasets for molecular property prediction",
    "Evaluating transformer-based models for drug-target interaction prediction",
    "Proposing improvements to current methodologies",
    "Benchmarking model performance across different drug discovery tasks",
    "Publishing findings in a peer-reviewed journal",
    "Developing open-source tools for the research community",
    "Collaborating with pharmaceutical industry partners",
  ],
  keywords: ["machine learning", "drug discovery", "deep learning", "molecular properties", "transformers", "pharmaceutical AI"],
  members: [
    { name: "Hassan", initials: "HA", color: "bg-blue-500" },
    { name: "Ahmed", initials: "AH", color: "bg-emerald-500" },
    { name: "Sara", initials: "SA", color: "bg-purple-500" },
    { name: "Omar", initials: "OM", color: "bg-amber-500" },
  ],
  activities: [
    { actor: "Hassan", action: "updated project", time: "35m ago" },
    { actor: "Ahmed", action: "added paper", time: "2h ago" },
    { actor: "Sara", action: "joined project", time: "1d ago" },
  ],
}

// Option 1: Bento Grid - Modern asymmetric layout
const Option1BentoGrid = () => {
  return (
    <div className="grid grid-cols-4 gap-4" style={{ minHeight: '420px' }}>
      {/* Objectives - Large card spanning 2x2 */}
      <div className="col-span-2 row-span-2 rounded-2xl bg-gradient-to-br from-orange-50 to-amber-50 dark:from-orange-900/20 dark:to-amber-900/10 border border-orange-200/50 dark:border-orange-800/30 p-6 flex flex-col">
        <div className="flex items-center gap-2 mb-4">
          <div className="p-2 rounded-xl bg-orange-100 dark:bg-orange-800/50">
            <Target className="h-5 w-5 text-orange-600 dark:text-orange-400" />
          </div>
          <h3 className="font-semibold text-gray-900 dark:text-slate-100">Objectives</h3>
          <span className="ml-auto text-xs bg-orange-200/70 dark:bg-orange-800/50 text-orange-700 dark:text-orange-300 px-2.5 py-1 rounded-full font-medium">{mockProject.objectives.length}</span>
        </div>
        <ul className="space-y-3 flex-1">
          {mockProject.objectives.map((obj, i) => (
            <li key={i} className="flex items-start gap-3 text-sm text-gray-700 dark:text-slate-300">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-orange-200/70 dark:bg-orange-800/50 text-xs font-bold text-orange-700 dark:text-orange-300">{i + 1}</span>
              <span className="leading-relaxed">{obj}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Description */}
      <div className="col-span-2 rounded-2xl bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-5">
        <div className="flex items-center gap-2 mb-3">
          <div className="p-2 rounded-xl bg-blue-100 dark:bg-blue-900/30">
            <FileText className="h-4 w-4 text-blue-600 dark:text-blue-400" />
          </div>
          <h3 className="font-semibold text-gray-900 dark:text-slate-100">Description</h3>
        </div>
        <p className="text-sm text-gray-600 dark:text-slate-400 leading-relaxed">{mockProject.description}</p>
      </div>

      {/* Team */}
      <div className="rounded-2xl bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-5">
        <div className="flex items-center gap-2 mb-3">
          <div className="p-2 rounded-xl bg-purple-100 dark:bg-purple-900/30">
            <Users className="h-4 w-4 text-purple-600 dark:text-purple-400" />
          </div>
          <h3 className="font-medium text-gray-900 dark:text-slate-100 text-sm">Team</h3>
        </div>
        <div className="flex -space-x-2">
          {mockProject.members.map((m, i) => (
            <div key={i} className={`h-9 w-9 rounded-full ${m.color} flex items-center justify-center text-white text-xs font-medium border-2 border-white dark:border-slate-800 shadow-sm`}>{m.initials}</div>
          ))}
          <div className="h-9 w-9 rounded-full bg-gray-100 dark:bg-slate-700 flex items-center justify-center text-gray-500 dark:text-slate-400 text-xs border-2 border-white dark:border-slate-800">+</div>
        </div>
      </div>

      {/* Keywords */}
      <div className="rounded-2xl bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-5">
        <div className="flex items-center gap-2 mb-3">
          <div className="p-2 rounded-xl bg-green-100 dark:bg-green-900/30">
            <Tag className="h-4 w-4 text-green-600 dark:text-green-400" />
          </div>
          <h3 className="font-medium text-gray-900 dark:text-slate-100 text-sm">Keywords</h3>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {mockProject.keywords.slice(0, 4).map((kw) => (
            <span key={kw} className="text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 px-2 py-1 rounded-full">{kw}</span>
          ))}
          {mockProject.keywords.length > 4 && <span className="text-xs text-gray-400 px-2 py-1">+{mockProject.keywords.length - 4}</span>}
        </div>
      </div>
    </div>
  )
}

// Option 2: Two-Column Split (Notion-style)
const Option2TwoColumn = () => {
  return (
    <div className="flex gap-8">
      {/* Main Content */}
      <div className="flex-1 space-y-8">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-slate-500 mb-3">About this project</h3>
          <p className="text-gray-700 dark:text-slate-300 leading-relaxed text-[15px]">{mockProject.description}</p>
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-slate-500 mb-4">Objectives</h3>
          <div className="space-y-2">
            {mockProject.objectives.map((obj, i) => (
              <div key={i} className="flex items-start gap-4 p-4 rounded-xl bg-gray-50 dark:bg-slate-800/50 hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors group">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-orange-100 dark:bg-orange-900/30 text-sm font-semibold text-orange-600 dark:text-orange-400 group-hover:scale-110 transition-transform">{i + 1}</div>
                <span className="text-[15px] text-gray-700 dark:text-slate-300 pt-0.5">{obj}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Sidebar */}
      <div className="w-80 shrink-0 space-y-5">
        <div className="rounded-2xl border border-gray-200 dark:border-slate-700 p-5 bg-white dark:bg-slate-800/50">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-slate-500 mb-4">Team Members</h3>
          <div className="space-y-3">
            {mockProject.members.map((m, i) => (
              <div key={i} className="flex items-center gap-3 p-2 -mx-2 rounded-lg hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors">
                <div className={`h-10 w-10 rounded-full ${m.color} flex items-center justify-center text-white text-sm font-medium shadow-sm`}>{m.initials}</div>
                <div>
                  <span className="text-sm font-medium text-gray-900 dark:text-slate-100">{m.name}</span>
                  <p className="text-xs text-gray-500 dark:text-slate-400">Member</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-gray-200 dark:border-slate-700 p-5 bg-white dark:bg-slate-800/50">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-slate-500 mb-4">Keywords</h3>
          <div className="flex flex-wrap gap-2">
            {mockProject.keywords.map((kw) => (
              <span key={kw} className="text-sm bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-slate-300 px-3 py-1.5 rounded-full hover:bg-gray-200 dark:hover:bg-slate-600 transition-colors cursor-default">{kw}</span>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-gray-200 dark:border-slate-700 p-5 bg-white dark:bg-slate-800/50">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-slate-500 mb-4">Activity</h3>
          <div className="space-y-3">
            {mockProject.activities.map((a, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-gray-700 dark:text-slate-300"><span className="font-medium">{a.actor}</span> {a.action}</span>
                <span className="text-xs text-gray-400 dark:text-slate-500">{a.time}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// Option 3: Horizontal Sections (Linear-style)
const Option3Horizontal = () => {
  return (
    <div className="space-y-8">
      {/* Meta strip */}
      <div className="flex items-center gap-8 pb-5 border-b border-gray-200 dark:border-slate-700">
        <div className="flex items-center gap-3">
          <div className="flex -space-x-2">
            {mockProject.members.map((m, i) => (
              <div key={i} className={`h-7 w-7 rounded-full ${m.color} flex items-center justify-center text-white text-[10px] font-medium border-2 border-white dark:border-slate-900`}>{m.initials}</div>
            ))}
          </div>
          <span className="text-sm text-gray-600 dark:text-slate-400">{mockProject.members.length} members</span>
        </div>
        <div className="h-5 w-px bg-gray-200 dark:bg-slate-700" />
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-orange-500" />
          <span className="text-sm text-gray-600 dark:text-slate-400">{mockProject.objectives.length} objectives</span>
        </div>
        <div className="h-5 w-px bg-gray-200 dark:bg-slate-700" />
        <div className="flex items-center gap-2 flex-1">
          {mockProject.keywords.slice(0, 4).map((kw) => (
            <span key={kw} className="text-xs bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-400 px-2.5 py-1 rounded-md">{kw}</span>
          ))}
          {mockProject.keywords.length > 4 && <span className="text-xs text-gray-400">+{mockProject.keywords.length - 4} more</span>}
        </div>
      </div>

      {/* Description */}
      <div>
        <p className="text-[15px] text-gray-700 dark:text-slate-300 leading-relaxed max-w-3xl">{mockProject.description}</p>
      </div>

      {/* Objectives grid */}
      <div>
        <h3 className="font-semibold text-gray-900 dark:text-slate-100 mb-5 flex items-center gap-2">
          <Target className="h-5 w-5 text-orange-500" />
          Project Objectives
        </h3>
        <div className="grid md:grid-cols-2 gap-4">
          {mockProject.objectives.map((obj, i) => (
            <div key={i} className="flex items-start gap-4 p-5 rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800/50 hover:border-orange-300 dark:hover:border-orange-700 transition-colors">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border-2 border-orange-200 dark:border-orange-700 text-sm font-bold text-orange-500">{i + 1}</div>
              <span className="text-sm text-gray-700 dark:text-slate-300 leading-relaxed pt-1">{obj}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Activity footer */}
      <div className="pt-5 border-t border-gray-200 dark:border-slate-700">
        <div className="flex items-center gap-6">
          <span className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-slate-500">Recent</span>
          {mockProject.activities.map((a, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-gray-600 dark:text-slate-400">
              <span className="font-medium text-gray-900 dark:text-slate-200">{a.actor}</span>
              <span>{a.action}</span>
              <span className="text-gray-400 dark:text-slate-500">· {a.time}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// Option 4: Tabbed with Header Card
const Option4Tabbed = () => {
  const [activeTab, setActiveTab] = useState<'overview' | 'objectives' | 'team'>('overview')

  return (
    <div>
      {/* Hero header */}
      <div className="rounded-2xl bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 p-6 text-white mb-6 shadow-lg">
        <p className="text-white/90 leading-relaxed text-[15px] max-w-2xl">{mockProject.description}</p>
        <div className="flex items-center gap-8 mt-5 pt-5 border-t border-white/20">
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-white/80" />
            <span className="font-semibold">{mockProject.objectives.length}</span>
            <span className="text-white/70 text-sm">Objectives</span>
          </div>
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-white/80" />
            <span className="font-semibold">{mockProject.members.length}</span>
            <span className="text-white/70 text-sm">Members</span>
          </div>
          <div className="flex items-center gap-2">
            <Tag className="h-5 w-5 text-white/80" />
            <span className="font-semibold">{mockProject.keywords.length}</span>
            <span className="text-white/70 text-sm">Keywords</span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-slate-700 mb-6">
        <div className="flex gap-1">
          {(['overview', 'objectives', 'team'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-5 py-3 text-sm font-medium border-b-2 transition-all ${
                activeTab === tab
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/20 rounded-t-lg'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-slate-400 dark:hover:text-slate-300'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="min-h-[300px]">
        {activeTab === 'overview' && (
          <div className="grid md:grid-cols-2 gap-8">
            <div>
              <h4 className="text-sm font-semibold text-gray-500 dark:text-slate-400 mb-4 uppercase tracking-wider">Keywords</h4>
              <div className="flex flex-wrap gap-2">
                {mockProject.keywords.map((kw) => (
                  <span key={kw} className="px-4 py-2 bg-gray-100 dark:bg-slate-800 text-gray-700 dark:text-slate-300 rounded-xl text-sm font-medium">{kw}</span>
                ))}
              </div>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-gray-500 dark:text-slate-400 mb-4 uppercase tracking-wider">Recent Activity</h4>
              <div className="space-y-3">
                {mockProject.activities.map((a, i) => (
                  <div key={i} className="flex justify-between items-center p-3 rounded-lg bg-gray-50 dark:bg-slate-800/50">
                    <span className="text-sm text-gray-700 dark:text-slate-300"><span className="font-semibold">{a.actor}</span> {a.action}</span>
                    <span className="text-xs text-gray-400 dark:text-slate-500 bg-gray-200 dark:bg-slate-700 px-2 py-1 rounded">{a.time}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'objectives' && (
          <div className="space-y-4">
            {mockProject.objectives.map((obj, i) => (
              <div key={i} className="flex items-start gap-5 p-5 rounded-xl border border-gray-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-600 hover:shadow-md transition-all bg-white dark:bg-slate-800/50">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 text-white font-bold shadow-sm">{i + 1}</div>
                <span className="text-gray-700 dark:text-slate-300 pt-2 text-[15px] leading-relaxed">{obj}</span>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'team' && (
          <div className="grid md:grid-cols-2 gap-4">
            {mockProject.members.map((m, i) => (
              <div key={i} className="flex items-center gap-4 p-5 rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800/50 hover:shadow-md transition-shadow">
                <div className={`h-14 w-14 rounded-2xl ${m.color} flex items-center justify-center text-white text-lg font-semibold shadow-sm`}>{m.initials}</div>
                <div>
                  <p className="font-semibold text-gray-900 dark:text-slate-100">{m.name}</p>
                  <p className="text-sm text-gray-500 dark:text-slate-400">Team Member</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// Option 5: Minimal Typography
const Option5Minimal = () => {
  return (
    <div className="max-w-3xl space-y-10">
      {/* Description as hero text */}
      <div>
        <p className="text-xl text-gray-700 dark:text-slate-300 leading-relaxed font-light">{mockProject.description}</p>
      </div>

      {/* Inline meta row */}
      <div className="flex flex-wrap items-center gap-4 py-4 border-y border-gray-200 dark:border-slate-700">
        <div className="flex -space-x-2">
          {mockProject.members.map((m, i) => (
            <div key={i} className={`h-9 w-9 rounded-full ${m.color} flex items-center justify-center text-white text-xs font-medium border-2 border-white dark:border-slate-900 shadow-sm`}>{m.initials}</div>
          ))}
        </div>
        <span className="text-gray-300 dark:text-slate-600">|</span>
        <div className="flex flex-wrap gap-2">
          {mockProject.keywords.map((kw) => (
            <span key={kw} className="text-sm text-gray-500 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 cursor-pointer transition-colors">#{kw.replace(/\s+/g, '-')}</span>
          ))}
        </div>
      </div>

      {/* Objectives with large numbers */}
      <div>
        <h3 className="text-xs font-bold uppercase tracking-[0.2em] text-gray-400 dark:text-slate-500 mb-6">Objectives</h3>
        <div className="space-y-6">
          {mockProject.objectives.map((obj, i) => (
            <div key={i} className="flex items-start gap-6 group">
              <span className="text-4xl font-extralight text-gray-200 dark:text-slate-700 group-hover:text-orange-400 dark:group-hover:text-orange-500 transition-colors tabular-nums">{String(i + 1).padStart(2, '0')}</span>
              <p className="text-gray-700 dark:text-slate-300 pt-2 leading-relaxed">{obj}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Activity footer */}
      <div className="pt-6 border-t border-gray-200 dark:border-slate-700">
        <div className="flex items-center gap-6 text-sm text-gray-500 dark:text-slate-400">
          <Clock className="h-4 w-4" />
          {mockProject.activities.slice(0, 2).map((a, i) => (
            <span key={i}><span className="font-medium text-gray-700 dark:text-slate-300">{a.actor}</span> {a.action} <span className="text-gray-400 dark:text-slate-500">{a.time}</span></span>
          ))}
        </div>
      </div>
    </div>
  )
}

// Main Showcase Component
const OverviewShowcase = () => {
  const options = [
    { id: 1, name: 'Bento Grid', description: 'Asymmetric cards with Objectives as the hero. Modern, iOS widget-inspired.', icon: LayoutGrid, component: Option1BentoGrid },
    { id: 2, name: 'Two-Column Split', description: 'Main content left, sidebar right. Clean Notion-style organization.', icon: Columns, component: Option2TwoColumn },
    { id: 3, name: 'Horizontal Sections', description: 'Full-width stacked sections. Linear/GitHub style with meta strip.', icon: LayoutList, component: Option3Horizontal },
    { id: 4, name: 'Tabbed with Header', description: 'Gradient hero card + tabbed navigation. Progressive disclosure.', icon: PanelTop, component: Option4Tabbed },
    { id: 5, name: 'Minimal Typography', description: 'Content-first, typography-focused. Large numbers, subtle UI.', icon: Sparkles, component: Option5Minimal },
  ]

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-slate-900 p-8">
      <div className="max-w-6xl mx-auto">
        <div className="mb-10">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-slate-100 mb-2">Project Overview Redesign</h1>
          <p className="text-gray-600 dark:text-slate-400 text-lg">Choose your preferred layout style. Tell me the option number to implement.</p>
        </div>

        <div className="space-y-12">
          {options.map((option) => (
            <div key={option.id} className="rounded-2xl bg-white dark:bg-slate-800 shadow-sm border border-gray-200 dark:border-slate-700 overflow-hidden">
              <div className="px-6 py-5 border-b border-gray-200 dark:border-slate-700 bg-gradient-to-r from-gray-50 to-white dark:from-slate-800/80 dark:to-slate-800">
                <div className="flex items-center gap-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-100 dark:bg-indigo-900/30 shadow-sm">
                    <option.icon className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">Option {option.id}: {option.name}</h2>
                    <p className="text-sm text-gray-500 dark:text-slate-400">{option.description}</p>
                  </div>
                </div>
              </div>
              <div className="p-6 bg-gray-50/50 dark:bg-slate-900/50">
                <option.component />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default OverviewShowcase
