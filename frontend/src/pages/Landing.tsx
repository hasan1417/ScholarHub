import { useEffect, useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Search,
  MessageSquare,
  CheckCircle2,
  FileText,
  Sparkles,
  Zap,
  Shield,
  BookOpen,
  GitBranch,
  Globe,
  Bot,
  PenTool,
} from 'lucide-react'
import { Logo } from '../components/brand/Logo'
import heroEditor from '../assets/hero-editor.png'
import showcaseAI from '../assets/showcase-ai-assistant.png'
import showcaseLibrary from '../assets/showcase-library.png'
import showcaseOverview from '../assets/showcase-overview.png'

const showcaseTabs = [
  { label: 'LaTeX Editor', image: heroEditor, alt: 'ScholarHub LaTeX editor with live PDF preview and collaboration toolbar' },
  { label: 'AI Assistant', image: showcaseAI, alt: 'AI research assistant answering questions and finding papers in a discussion channel' },
  { label: 'Reference Library', image: showcaseLibrary, alt: 'Reference management with 183 papers, PDF analysis, Zotero import, and citation tools' },
  { label: 'Project Dashboard', image: showcaseOverview, alt: 'Project overview with AI-powered insights and topic coverage analysis' },
]

const heroPromises = [
  {
    icon: CheckCircle2,
    text: 'Live LaTeX and rich-text drafting with real-time collaboration',
  },
  {
    icon: Sparkles,
    text: 'AI research assistant and editor copilot built into every project',
  },
  {
    icon: FileText,
    text: 'Journal-ready exports for IEEE, ACM, NeurIPS, and more',
  },
]

const heroFeaturePills = [
  {
    label: 'LaTeX + Rich Text',
    sublabel: 'Write in your preferred format',
  },
  {
    label: 'Real-time Collaboration',
    sublabel: 'Work together seamlessly',
  },
  {
    label: 'IEEE, ACM, NeurIPS & More',
    sublabel: 'Templates for every major venue',
  },
  {
    label: 'AI-Powered Discovery',
    sublabel: 'Find relevant papers instantly',
  },
]

const heroPlatformHighlight = {
  headline: 'Built for Academic Teams',
  description:
    'Unified search across 8 major academic databases including PubMed, ArXiv, and Semantic Scholar. Import references from Zotero, collaborate in real-time, and export publication-ready manuscripts.',
}

// Custom hook for intersection observer animations
const useScrollAnimation = (threshold = 0.1) => {
  const ref = useRef<HTMLDivElement>(null)
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true)
          observer.disconnect()
        }
      },
      { threshold }
    )

    if (ref.current) {
      observer.observe(ref.current)
    }

    return () => observer.disconnect()
  }, [threshold])

  return { ref, isVisible }
}

const Landing = () => {
  const [isVisible, setIsVisible] = useState(false)
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)
  const [activeTab, setActiveTab] = useState(0)

  // Scroll animation refs
  const socialProof = useScrollAnimation(0.2)
  const platformHighlights = useScrollAnimation(0.2)
  const features = useScrollAnimation(0.1)
  const howItWorks = useScrollAnimation(0.2)
  const finalCta = useScrollAnimation(0.2)
  const aboutSection = useScrollAnimation(0.2)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const handleChange = (event: MediaQueryListEvent | MediaQueryList) => setPrefersReducedMotion(event.matches)
    setPrefersReducedMotion(query.matches)

    if (typeof query.addEventListener === 'function') {
      const listener = (event: MediaQueryListEvent) => handleChange(event)
      query.addEventListener('change', listener)
      return () => query.removeEventListener('change', listener)
    }

    return undefined
  }, [])

  useEffect(() => {
    if (prefersReducedMotion) {
      setIsVisible(true)
      return
    }
    const id = window.requestAnimationFrame(() => setIsVisible(true))
    return () => window.cancelAnimationFrame(id)
  }, [prefersReducedMotion])

  const heroAnimationCls = prefersReducedMotion || isVisible
    ? 'opacity-100 translate-y-0'
    : 'opacity-0 translate-y-8'

  const featuresList = [
    {
      Icon: Bot,
      title: 'AI Research Assistant',
      description: 'Chat with an AI that knows your project. It searches papers, analyzes your library, summarizes findings, and answers questions — right inside your discussion channels.',
      gradient: 'from-violet-500 to-purple-500',
    },
    {
      Icon: PenTool,
      title: 'AI Editor Copilot',
      description: 'Context-aware writing help built into the editor. Extend paragraphs, improve academic tone, fix grammar, and get inline suggestions as you write.',
      gradient: 'from-pink-500 to-rose-500',
    },
    {
      Icon: Search,
      title: 'Smart Paper Discovery',
      description: 'Search across Semantic Scholar, PubMed, ArXiv, and 5 more databases. Get citation snippets ready to attach in one click.',
      gradient: 'from-blue-500 to-cyan-500',
    },
    {
      Icon: MessageSquare,
      title: 'Team Discussions',
      description: 'Built-in channels for research talk. Run lab meetings, capture decisions, and assign tasks — all alongside your papers.',
      gradient: 'from-amber-500 to-orange-500',
    },
    {
      Icon: GitBranch,
      title: 'Real-time Collaboration',
      description: 'Write together in LaTeX or rich text with live cursors, section locks, role-based access, and full revision history.',
      gradient: 'from-emerald-500 to-teal-500',
    },
    {
      Icon: Globe,
      title: 'Reference Management',
      description: 'Import from Zotero or BibTeX, organize collections, and auto-format citations for any journal style.',
      gradient: 'from-indigo-500 to-blue-500',
    },
  ]

  const workflowSteps = [
    {
      icon: Zap,
      title: 'Import your existing work',
      detail: 'Bring your Zotero library, BibTeX files, and existing papers. Set up a project and invite your co-authors in under a minute.',
    },
    {
      icon: BookOpen,
      title: 'Write with AI by your side',
      detail: 'Draft in LaTeX with an AI copilot that helps you write, an AI assistant that answers research questions, and paper discovery across 8 databases — all in one editor.',
    },
    {
      icon: Shield,
      title: 'Export and submit anywhere',
      detail: 'Generate publication-ready PDFs in IEEE, ACM, NeurIPS, or any format. Download your .tex source and .bib files anytime.',
    },
  ]

  return (
    <div className="min-h-screen bg-white dark:bg-slate-950 overflow-hidden">
      {/* Static Background */}
      <div className="fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-50 via-white to-purple-50 dark:opacity-0 transition-opacity duration-500" />
        <div className="absolute inset-0 opacity-0 dark:opacity-100 transition-opacity duration-500">
          <div className="absolute inset-0 bg-slate-950" />
        </div>
      </div>

      {/* Navigation */}
      <nav className="sticky top-0 z-50 border-b border-gray-200/50 bg-white/80 backdrop-blur-xl dark:border-slate-800/50 dark:bg-slate-950/80">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3 sm:py-4">
          <div className="flex items-center justify-between">
            <Link to="/" className="group">
              <Logo className="group-hover:scale-105 transition-all" textClassName="text-base sm:text-lg" />
            </Link>
            <div className="flex items-center gap-2 sm:gap-3">
              <a
                href="#features"
                className="hidden sm:inline-block px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors dark:text-slate-400 dark:hover:text-white"
                onClick={(e) => { e.preventDefault(); document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' }) }}
              >
                Features
              </a>
              <a
                href="#how-it-works"
                className="hidden sm:inline-block px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors dark:text-slate-400 dark:hover:text-white"
                onClick={(e) => { e.preventDefault(); document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' }) }}
              >
                How it Works
              </a>
              <Link
                to="/login"
                className="px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors dark:text-slate-400 dark:hover:text-white"
              >
                Sign in
              </Link>
              <Link
                to="/register"
                className="px-3 py-2 sm:px-5 sm:py-2.5 text-xs sm:text-sm font-semibold text-white bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-600 rounded-xl transition-all shadow-lg shadow-indigo-500/25 hover:shadow-xl hover:shadow-indigo-500/30 hover:-translate-y-0.5"
              >
                Start for free
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative px-4 sm:px-6 pt-12 sm:pt-20 pb-20 sm:pb-32">
        <div className="max-w-5xl mx-auto">
          <div className={`text-center transition-all duration-1000 ease-out ${heroAnimationCls}`}>
            {/* Main headline */}
            <h1 className="mt-6 sm:mt-8 text-3xl sm:text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight">
              <span className="bg-gradient-to-r from-gray-900 via-gray-800 to-gray-900 dark:from-white dark:via-gray-100 dark:to-white bg-clip-text text-transparent inline-block transition-transform duration-300 pb-1">
                Write and publish
              </span>
              <br />
              <span className="bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-600 bg-clip-text text-transparent inline-block pb-2">
                research papers, together
              </span>
            </h1>

            {/* Subheadline */}
            <p className="mt-5 sm:mt-8 text-base sm:text-xl text-gray-600 max-w-2xl mx-auto leading-relaxed dark:text-slate-400 px-2 sm:px-0">
              Stop juggling Overleaf, Zotero, and Slack for every paper. Write in LaTeX with AI-powered assistance, discover papers across 8 databases, and export journal-ready manuscripts in one click.
            </p>

            {/* CTA Buttons */}
            <div className="mt-8 sm:mt-12 flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4">
              <Link
                to="/register"
                className="group relative inline-flex items-center gap-2 px-6 py-3 sm:px-8 sm:py-4 text-sm sm:text-base font-semibold text-white bg-gradient-to-r from-indigo-600 to-purple-600 rounded-xl sm:rounded-2xl transition-all shadow-xl shadow-indigo-500/25 hover:shadow-2xl hover:shadow-indigo-500/40 hover:-translate-y-1 overflow-hidden"
              >
                <span className="relative flex items-center gap-2">
                  Start for free
                  <ArrowRight className="h-4 w-4 sm:h-5 sm:w-5 group-hover:translate-x-1 transition-transform" />
                </span>
              </Link>
              <a
                href="#features"
                className="group inline-flex items-center gap-2 px-6 py-3 sm:px-8 sm:py-4 text-sm sm:text-base font-medium text-gray-700 dark:text-slate-300 bg-white/80 dark:bg-slate-800/80 backdrop-blur-sm border border-gray-200 dark:border-slate-700 rounded-xl sm:rounded-2xl transition-all hover:shadow-lg hover:-translate-y-0.5 hover:border-indigo-300 dark:hover:border-indigo-500/50"
                onClick={(e) => { e.preventDefault(); document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' }) }}
              >
                See what's inside
              </a>
            </div>
            <p className="mt-4 text-sm text-gray-500 dark:text-slate-400">
              Free for research teams — no credit card required
            </p>

            {/* Tabbed Product Showcase */}
            <div className="mt-12 max-w-4xl mx-auto">
              {/* Tab buttons */}
              <div className="flex flex-wrap items-center justify-center gap-1.5 sm:gap-2 mb-4">
                {showcaseTabs.map((tab, index) => (
                  <button
                    key={tab.label}
                    onClick={() => setActiveTab(index)}
                    className={`px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium rounded-lg sm:rounded-xl transition-all ${
                      activeTab === index
                        ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-lg shadow-indigo-500/25'
                        : 'text-gray-600 dark:text-slate-400 bg-white/80 dark:bg-slate-800/80 border border-gray-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-500/50 hover:text-gray-900 dark:hover:text-white'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              {/* Screenshot */}
              <div className="rounded-2xl border border-gray-200 dark:border-slate-700 shadow-2xl overflow-hidden">
                <img
                  src={showcaseTabs[activeTab].image}
                  alt={showcaseTabs[activeTab].alt}
                  className="w-full"
                  width={1440}
                  height={900}
                />
              </div>
            </div>

            {/* Social proof strip */}
            <div
              ref={socialProof.ref}
              className={`mt-10 sm:mt-14 transition-all duration-700 ${socialProof.isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'}`}
            >
              <p className="text-xs sm:text-sm font-medium text-gray-400 dark:text-slate-500 uppercase tracking-wider mb-4">
                Trusted by researchers at leading universities
              </p>
              <div className="flex flex-wrap items-center justify-center gap-x-6 sm:gap-x-10 gap-y-2">
                {['MIT', 'Stanford', 'Oxford', 'ETH Zurich', 'NUS'].map((name) => (
                  <span
                    key={name}
                    className="text-base sm:text-lg font-semibold text-gray-300 dark:text-slate-600 select-none"
                  >
                    {name}
                  </span>
                ))}
              </div>
            </div>

            {/* Promise pills with staggered animation */}
            <div className="mt-10 sm:mt-16 flex flex-wrap items-center justify-center gap-2 sm:gap-3 px-2 sm:px-0">
              {heroPromises.map(({ icon: Icon, text }, index) => (
                <div
                  key={text}
                  className={`inline-flex items-center gap-1.5 sm:gap-2 rounded-full bg-white/90 backdrop-blur-sm px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm text-gray-700 shadow-md shadow-indigo-500/5 border border-gray-200/80 dark:bg-slate-800/50 dark:border-slate-700 dark:text-slate-300 dark:shadow-none hover:shadow-lg hover:shadow-indigo-500/10 hover:-translate-y-0.5 transition-all cursor-default opacity-0 ${isVisible ? 'animate-[fade-in-up_0.5s_ease-out_forwards]' : ''}`}
                  style={{ animationDelay: `${0.5 + index * 0.15}s` }}
                >
                  <Icon className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-emerald-500 flex-shrink-0" />
                  <span className="text-left">{text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Platform Highlights */}
      <section ref={platformHighlights.ref} className="relative px-4 sm:px-6 py-12 sm:py-20">
        <div className={`max-w-5xl mx-auto transition-all duration-700 ${platformHighlights.isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'}`}>
          <div className="relative rounded-2xl sm:rounded-[32px] bg-gradient-to-br from-slate-900 to-slate-800 dark:from-slate-800 dark:to-slate-900 p-1 overflow-hidden">
            <div className="relative rounded-xl sm:rounded-[28px] bg-gradient-to-br from-slate-900 to-slate-800 dark:from-slate-800 dark:to-slate-900 p-5 sm:p-8 lg:p-12 overflow-hidden">
              {/* Background pattern */}
              <div className="absolute inset-0 opacity-5">
                <div className="absolute top-0 left-0 w-full h-full" style={{
                  backgroundImage: 'radial-gradient(circle at 2px 2px, white 1px, transparent 0)',
                  backgroundSize: '40px 40px'
                }} />
              </div>

              <div className="relative grid lg:grid-cols-2 gap-6 sm:gap-10">
                {/* Feature pills */}
                <div className="grid grid-cols-2 gap-2 sm:gap-4">
                  {heroFeaturePills.map((pill, index) => (
                    <div
                      key={pill.label}
                      className={`relative group opacity-0 ${platformHighlights.isVisible ? 'animate-[scale-in_0.5s_ease-out_forwards]' : ''}`}
                      style={{ animationDelay: `${0.2 + index * 0.1}s` }}
                    >
                      <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/20 to-purple-500/20 rounded-xl sm:rounded-2xl blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                      <div className="relative rounded-xl sm:rounded-2xl bg-white/5 border border-white/10 p-3 sm:p-5 hover:bg-white/10 transition-all duration-300 hover:scale-105 hover:-translate-y-1">
                        <p className="text-sm sm:text-base font-semibold text-white">{pill.label}</p>
                        <p className="mt-1 text-[11px] sm:text-sm text-slate-400">{pill.sublabel}</p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Platform Highlight */}
                <div className={`flex flex-col justify-center opacity-0 ${platformHighlights.isVisible ? 'animate-[fade-in-up_0.6s_ease-out_0.4s_forwards]' : ''}`}>
                  <div className="relative">
                    <div className="inline-flex items-center gap-2 mb-4">
                      <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center shadow-lg shadow-indigo-500/30">
                        <Globe className="h-5 w-5 text-white" />
                      </div>
                      <h3 className="text-xl font-bold text-white">{heroPlatformHighlight.headline}</h3>
                    </div>
                    <p className="text-lg text-slate-300 leading-relaxed">
                      {heroPlatformHighlight.description}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section ref={features.ref} id="features" className="relative px-4 sm:px-6 py-16 sm:py-24">
        <div className="max-w-6xl mx-auto">
          {/* Section header */}
          <div className={`text-center mb-10 sm:mb-16 transition-all duration-700 ${features.isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'}`}>
            <div className="inline-flex items-center gap-1.5 sm:gap-2 rounded-full border border-purple-200 bg-purple-50 px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-purple-700 dark:border-purple-500/30 dark:bg-purple-500/10 dark:text-purple-300 mb-4 sm:mb-6 hover:scale-105 transition-transform">
              <Zap className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
              <span>Powerful Features</span>
            </div>
            <h2 className="text-2xl sm:text-4xl md:text-5xl font-bold text-gray-900 dark:text-white">
              Everything you need to
              <br />
              <span className="bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
                accelerate your research
              </span>
            </h2>
            <p className="mt-4 sm:mt-6 text-base sm:text-xl text-gray-600 max-w-2xl mx-auto dark:text-slate-400 px-2 sm:px-0">
              One platform to write, collaborate, discover, and publish. No more juggling between tools.
            </p>
          </div>

          {/* Feature grid with staggered animations */}
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
            {featuresList.map(({ Icon, title, description, gradient }, index) => (
              <div
                key={title}
                className={`group relative rounded-2xl sm:rounded-3xl bg-white/80 backdrop-blur-sm p-5 sm:p-8 shadow-lg shadow-indigo-500/5 border border-gray-200/80 hover:shadow-xl hover:shadow-indigo-500/10 hover:border-indigo-200/50 transition-all duration-500 hover:-translate-y-2 dark:bg-slate-800 dark:border-slate-700 dark:hover:bg-slate-800 dark:hover:border-slate-600 dark:shadow-none opacity-0 ${features.isVisible ? 'animate-[fade-in-up_0.5s_ease-out_forwards]' : ''}`}
                style={{ animationDelay: `${0.1 + index * 0.1}s` }}
              >
                {/* Hover glow effect */}
                <div className={`absolute inset-0 rounded-2xl sm:rounded-3xl bg-gradient-to-br ${gradient} opacity-0 group-hover:opacity-10 transition-opacity duration-500 blur-xl`} />

                <div className={`relative inline-flex items-center justify-center w-11 h-11 sm:w-14 sm:h-14 rounded-xl sm:rounded-2xl bg-gradient-to-br ${gradient} mb-4 sm:mb-6 shadow-lg group-hover:scale-110 group-hover:rotate-3 transition-all duration-300`}>
                  <Icon className="h-5 w-5 sm:h-7 sm:w-7 text-white" />
                </div>
                <h3 className="relative text-lg sm:text-xl font-semibold text-gray-900 mb-2 sm:mb-3 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">{title}</h3>
                <p className="relative text-sm sm:text-base text-gray-600 leading-relaxed dark:text-slate-400">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it Works */}
      <section ref={howItWorks.ref} id="how-it-works" className="relative px-4 sm:px-6 py-16 sm:py-24">
        <div className="max-w-5xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-10 lg:gap-16 items-center">
            {/* Left side - Text */}
            <div className={`transition-all duration-700 ${howItWorks.isVisible ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-10'}`}>
              <div className="inline-flex items-center gap-1.5 sm:gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300 mb-4 sm:mb-6 hover:scale-105 transition-transform">
                <CheckCircle2 className={`h-3.5 w-3.5 sm:h-4 sm:w-4 ${prefersReducedMotion ? '' : 'animate-bounce-subtle'}`} />
                <span>Simple Workflow</span>
              </div>
              <h2 className="text-2xl sm:text-4xl md:text-5xl font-bold text-gray-900 dark:text-white leading-tight">
                From first draft to
                <br />
                <span className="bg-gradient-to-r from-emerald-600 to-teal-600 bg-clip-text text-transparent">
                  publication
                </span>
              </h2>
              <p className="mt-4 sm:mt-6 text-base sm:text-lg text-gray-600 dark:text-slate-400">
                Move your research workflow into one place. No more context-switching between your editor, reference manager, and team chat.
              </p>
            </div>

            {/* Right side - Steps */}
            <div className="space-y-4 sm:space-y-6">
              {workflowSteps.map((step, index) => (
                <div
                  key={step.title}
                  className={`group relative flex gap-4 sm:gap-6 p-4 sm:p-6 rounded-xl sm:rounded-2xl bg-white/80 backdrop-blur-sm border border-gray-200/80 shadow-lg shadow-indigo-500/5 hover:shadow-xl hover:shadow-indigo-500/10 hover:border-indigo-200/50 transition-all duration-500 hover:-translate-y-1 dark:bg-slate-800/50 dark:border-slate-700 dark:hover:bg-slate-800 dark:shadow-none opacity-0 ${howItWorks.isVisible ? 'animate-[fade-in-up_0.5s_ease-out_forwards]' : ''}`}
                  style={{ animationDelay: `${0.3 + index * 0.15}s` }}
                >
                  {/* Icon column with connecting line between steps */}
                  <div className="flex-shrink-0 relative z-10 flex flex-col items-center">
                    <div className="flex h-11 w-11 sm:h-14 sm:w-14 items-center justify-center rounded-xl sm:rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-500 shadow-lg shadow-indigo-500/25 group-hover:scale-110 group-hover:rotate-6 transition-all duration-300">
                      <step.icon className="h-5 w-5 sm:h-7 sm:w-7 text-white" />
                    </div>
                    {/* Connecting line extends from bottom of icon to bottom of card */}
                    {index < workflowSteps.length - 1 && (
                      <div className="hidden sm:block w-0.5 flex-1 mt-2 bg-gradient-to-b from-indigo-500/50 to-purple-500/50 dark:from-indigo-500/30 dark:to-purple-500/30" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 sm:gap-3 mb-1.5 sm:mb-2">
                      <span className="inline-flex items-center justify-center h-5 w-5 sm:h-6 sm:w-6 rounded-full bg-indigo-100 text-[10px] sm:text-xs font-bold text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400 group-hover:scale-110 transition-transform">
                        {index + 1}
                      </span>
                      <h3 className="text-base sm:text-lg font-semibold text-gray-900 dark:text-white">{step.title}</h3>
                    </div>
                    <p className="text-sm sm:text-base text-gray-600 dark:text-slate-400">{step.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Final CTA Section */}
      <section ref={finalCta.ref} className="relative px-4 sm:px-6 py-16 sm:py-32">
        <div className={`max-w-4xl mx-auto transition-all duration-700 ${finalCta.isVisible ? 'opacity-100 scale-100' : 'opacity-0 scale-95'}`}>
          <div className="relative rounded-2xl sm:rounded-[40px] bg-gradient-to-br from-indigo-600 to-purple-600 p-1 group">
            <div className="relative rounded-xl sm:rounded-[36px] bg-gradient-to-br from-indigo-600 to-purple-600 px-5 py-10 sm:px-16 sm:py-20 text-center overflow-hidden">
              <h2 className="relative text-2xl sm:text-4xl md:text-5xl font-bold text-white mb-4 sm:mb-6">
                Ready to transform your
                <br />
                research workflow?
              </h2>
              <p className="relative text-base sm:text-xl text-indigo-100 mb-8 sm:mb-10 max-w-2xl mx-auto px-2 sm:px-0">
                Write, collaborate, and publish research papers with your team.
                Start free, no credit card required.
              </p>
              <div className="relative flex flex-col items-center gap-3 sm:gap-4">
                <Link
                  to="/register"
                  className="group/btn inline-flex items-center gap-2 px-6 py-3 sm:px-8 sm:py-4 text-sm sm:text-base font-semibold text-indigo-600 bg-white hover:bg-gray-50 rounded-xl sm:rounded-2xl transition-all shadow-xl hover:shadow-2xl hover:-translate-y-1 hover:scale-105 w-full sm:w-auto justify-center"
                >
                  Start for free
                  <ArrowRight className="h-4 w-4 sm:h-5 sm:w-5 group-hover/btn:translate-x-1 transition-transform" />
                </Link>
                <a
                  href="#features"
                  className="text-sm text-indigo-200 hover:text-white transition-colors underline underline-offset-2"
                  onClick={(e) => { e.preventDefault(); document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' }) }}
                >
                  Or explore the features above
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* About / Mission */}
      <section ref={aboutSection.ref} className="relative px-4 sm:px-6 py-12 sm:py-20">
        <div className={`max-w-2xl mx-auto text-center transition-all duration-700 ${aboutSection.isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'}`}>
          <h3 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-white mb-3 sm:mb-4">
            Built by researchers, for researchers
          </h3>
          <p className="text-sm sm:text-base text-gray-600 dark:text-slate-400 leading-relaxed">
            ScholarHub was born from the frustration of managing research across too many disconnected tools.
            We're building the workspace we wished we had -- one place to write, discover, collaborate, and publish.
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative border-t border-gray-200/80 dark:border-slate-800 bg-gradient-to-b from-gray-50 to-white dark:from-slate-900/50 dark:to-slate-950">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
          <div className="flex flex-col lg:flex-row items-start justify-between gap-8">
            {/* Brand */}
            <div className="max-w-sm">
              <Link to="/" className="group">
                <Logo className="group-hover:scale-105 transition-transform" />
              </Link>
              <p className="mt-3 sm:mt-4 text-sm sm:text-base text-gray-600 dark:text-slate-400">
                The modern workspace for research teams. Write, collaborate, and publish together.
              </p>
            </div>

            {/* Links */}
            <div className="grid grid-cols-3 gap-6 sm:gap-8 text-sm w-full lg:w-auto">
              <div>
                <h4 className="font-semibold text-gray-900 dark:text-white mb-3 sm:mb-4 text-xs sm:text-sm">Product</h4>
                <ul className="space-y-2 sm:space-y-3">
                  <li><a href="#features" className="text-xs sm:text-sm text-gray-600 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white transition-colors hover:translate-x-1 inline-block">Features</a></li>
                  <li><a href="#how-it-works" className="text-xs sm:text-sm text-gray-600 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white transition-colors hover:translate-x-1 inline-block">How it works</a></li>
                  <li><Link to="/pricing" className="text-xs sm:text-sm text-gray-600 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white transition-colors hover:translate-x-1 inline-block">Pricing</Link></li>
                </ul>
              </div>
              <div>
                <h4 className="font-semibold text-gray-900 dark:text-white mb-3 sm:mb-4 text-xs sm:text-sm">Company</h4>
                <ul className="space-y-2 sm:space-y-3">
                  <li><a href="mailto:support@scholarhub.space" className="text-xs sm:text-sm text-gray-600 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white transition-colors hover:translate-x-1 inline-block">Contact</a></li>
                  <li><Link to="/privacy" className="text-xs sm:text-sm text-gray-600 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white transition-colors hover:translate-x-1 inline-block">Privacy Policy</Link></li>
                  <li><Link to="/terms" className="text-xs sm:text-sm text-gray-600 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white transition-colors hover:translate-x-1 inline-block">Terms of Service</Link></li>
                </ul>
              </div>
              <div>
                <h4 className="font-semibold text-gray-900 dark:text-white mb-3 sm:mb-4 text-xs sm:text-sm">Get Started</h4>
                <ul className="space-y-2 sm:space-y-3">
                  <li><Link to="/register" className="text-xs sm:text-sm text-gray-600 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white transition-colors hover:translate-x-1 inline-block">Create account</Link></li>
                  <li><Link to="/login" className="text-xs sm:text-sm text-gray-600 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white transition-colors hover:translate-x-1 inline-block">Sign in</Link></li>
                </ul>
              </div>
            </div>
          </div>

          <div className="mt-8 sm:mt-12 pt-6 sm:pt-8 border-t border-gray-200 dark:border-slate-800 flex items-center justify-center">
            <p className="text-xs sm:text-sm text-gray-500 dark:text-slate-500">
              © {new Date().getFullYear()} ScholarHub. All rights reserved.
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default Landing
