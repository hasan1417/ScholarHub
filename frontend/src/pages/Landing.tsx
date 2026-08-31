import { useEffect, useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Search,
  MessageSquare,
  CheckCircle2,
  Zap,
  Shield,
  BookOpen,
  GitBranch,
  Globe,
  Bot,
  PenTool,
} from 'lucide-react'
import { Logo } from '../components/brand/Logo'
import HeroAnimatedMockup from '../components/landing/HeroAnimatedMockup'

const heroFeaturePills = [
  {
    label: 'LaTeX editor',
    sublabel: 'Live PDF preview as you type',
  },
  {
    label: 'Real-time collaboration',
    sublabel: 'Live cursors and section locks',
  },
  {
    label: 'IEEE, ACM, NeurIPS',
    sublabel: 'Export to your venue format',
  },
  {
    label: 'Paper discovery',
    sublabel: 'Nine databases, one search',
  },
]

const heroPlatformHighlight = {
  headline: 'Built for academic teams',
  description:
    'One search covers nine academic databases, PubMed, ArXiv and Semantic Scholar among them. Your Zotero references come across intact, and what your team writes exports as a manuscript ready to submit.',
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

  // Scroll animation refs

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
      title: 'AI research assistant',
      description: 'An assistant that can see your project. It searches papers, reads and summarizes your library, and answers questions without you leaving the discussion channel.',
      gradient: 'from-violet-500 to-purple-500',
    },
    {
      Icon: PenTool,
      title: 'AI editor copilot',
      description: 'Writing help built into the editor itself. Extend a paragraph, tighten the academic tone, or fix grammar, with suggestions appearing inline as you write.',
      gradient: 'from-pink-500 to-rose-500',
    },
    {
      Icon: Search,
      title: 'Paper discovery',
      description: 'One query searches Semantic Scholar, PubMed, ArXiv and six other databases. Results come back deduplicated across sources, with citation snippets you can attach in a click.',
      gradient: 'from-blue-500 to-cyan-500',
    },
    {
      Icon: MessageSquare,
      title: 'Team discussions',
      description: 'Channels for the research conversation, sitting next to the papers they are about. Run a lab meeting, record what was decided, and assign the follow-ups.',
      gradient: 'from-amber-500 to-orange-500',
    },
    {
      Icon: GitBranch,
      title: 'Real-time collaboration',
      description: 'Write together in LaTeX with live cursors, section locks, role-based access and full revision history. Tectonic compiles as you type, with full package support and a live PDF preview beside the source.',
      gradient: 'from-emerald-500 to-teal-500',
    },
    {
      Icon: Globe,
      title: 'Reference management',
      description: 'Import from Zotero or BibTeX and organize your collections. Citations reformat themselves to whichever journal style you need.',
      gradient: 'from-indigo-500 to-blue-500',
    },
  ]

  const workflowSteps = [
    {
      icon: Zap,
      title: 'Import your existing work',
      detail: 'Bring your Zotero library, your BibTeX files, and papers you have already started. Setting up a project and inviting your co-authors takes under a minute.',
    },
    {
      icon: BookOpen,
      title: 'Draft with AI in the editor',
      detail: 'Write in LaTeX with a copilot for the prose, an assistant for research questions, and discovery across nine databases. All of it in the same editor.',
    },
    {
      icon: Shield,
      title: 'Export and submit anywhere',
      detail: 'Generate submission-ready PDFs in IEEE, ACM, NeurIPS or another format. Your .tex source and .bib files stay downloadable at any point.',
    },
  ]

  return (
    <div className="min-h-screen bg-white dark:bg-[#0f172a] overflow-hidden">
      {/* Static Background */}
      <div className="fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-50 via-white to-purple-50 dark:opacity-0 transition-opacity duration-500" />
        <div className="absolute inset-0 opacity-0 dark:opacity-100 transition-opacity duration-500">
          <div className="absolute inset-0 bg-[#0f172a]" />
        </div>
      </div>

      {/* Navigation */}
      <nav className="sticky top-0 z-50 border-b border-gray-200/50 bg-white/80 backdrop-blur-xl dark:border-slate-700/50 dark:bg-[#0f172a]/80">
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
                className="px-3 py-2 sm:px-5 sm:py-2.5 text-xs sm:text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-all shadow-lg shadow-indigo-500/25 hover:shadow-xl hover:shadow-indigo-500/30 hover:-translate-y-0.5"
              >
                Start for free
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <HeroAnimatedMockup reduced={prefersReducedMotion} heroAnimationCls={heroAnimationCls} />

      {/* Platform Highlights */}
      <section ref={platformHighlights.ref} className="relative px-4 sm:px-6 py-12 sm:py-20">
        <div className={`max-w-5xl mx-auto transition-all duration-700 ${platformHighlights.isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'}`}>
          <div className="relative rounded-2xl sm:rounded-[32px] bg-gradient-to-br from-slate-900 to-slate-800 dark:from-slate-800/90 dark:to-slate-700/90 dark:border dark:border-slate-600/50 p-1 overflow-hidden">
            <div className="relative rounded-xl sm:rounded-[28px] bg-gradient-to-br from-slate-900 to-slate-800 dark:from-slate-800/90 dark:to-slate-700/90 p-5 sm:p-8 lg:p-12 overflow-hidden">
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
                      <div className="h-10 w-10 rounded-xl bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
                        <Globe className="h-5 w-5 text-white" />
                      </div>
                      <h3 className="font-serif text-xl font-bold text-white">{heroPlatformHighlight.headline}</h3>
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
            <div className="inline-flex items-center gap-1.5 sm:gap-2 rounded-full border border-purple-200 bg-purple-50 px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-purple-700 dark:border-purple-500/30 dark:bg-purple-500/10 dark:text-purple-300 mb-4 sm:mb-6">
              <Zap className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
              <span>Features</span>
            </div>
            <h2 className="font-serif text-2xl sm:text-4xl md:text-5xl font-bold text-gray-900 dark:text-white">
              What replaces
              <br />
              <span className="text-indigo-600 dark:text-indigo-400">
                your other five tabs
              </span>
            </h2>
            <p className="mt-4 sm:mt-6 text-base sm:text-xl text-gray-600 max-w-2xl mx-auto dark:text-slate-400 px-2 sm:px-0">
              Writing, references, discovery and team discussion all live in the same workspace.
            </p>
          </div>

          {/* Feature grid with staggered animations */}
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
            {featuresList.map(({ Icon, title, description, gradient }, index) => (
              <div
                key={title}
                className={`group relative rounded-2xl sm:rounded-3xl bg-white/80 backdrop-blur-sm p-5 sm:p-8 shadow-lg shadow-indigo-500/5 border border-gray-200/80 hover:shadow-xl hover:shadow-indigo-500/10 hover:border-indigo-200/50 transition-all duration-500 hover:-translate-y-2 dark:bg-slate-800/80 dark:border-slate-600/50 dark:hover:bg-slate-800 dark:hover:border-slate-500/60 dark:shadow-lg dark:shadow-black/20 opacity-0 ${features.isVisible ? 'animate-[fade-in-up_0.5s_ease-out_forwards]' : ''}`}
                style={{ animationDelay: `${0.1 + index * 0.1}s` }}
              >
                <div className={`relative inline-flex items-center justify-center w-11 h-11 sm:w-14 sm:h-14 rounded-xl sm:rounded-2xl bg-gradient-to-br ${gradient} mb-4 sm:mb-6 shadow-lg group-hover:scale-105 transition-transform duration-300`}>
                  <Icon className="h-5 w-5 sm:h-7 sm:w-7 text-white" />
                </div>
                <h3 className="font-serif relative text-lg sm:text-xl font-semibold text-gray-900 mb-2 sm:mb-3 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">{title}</h3>
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
              <div className="inline-flex items-center gap-1.5 sm:gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300 mb-4 sm:mb-6">
                <CheckCircle2 className={`h-3.5 w-3.5 sm:h-4 sm:w-4 ${prefersReducedMotion ? '' : 'animate-bounce-subtle'}`} />
                <span>How it works</span>
              </div>
              <h2 className="font-serif text-2xl sm:text-4xl md:text-5xl font-bold text-gray-900 dark:text-white leading-tight">
                From first draft to
                <br />
                <span className="text-emerald-600 dark:text-emerald-400">
                  publication
                </span>
              </h2>
              <p className="mt-4 sm:mt-6 text-base sm:text-lg text-gray-600 dark:text-slate-400">
                Your editor, your reference manager and your team chat stop being three separate places you have to keep open.
              </p>
            </div>

            {/* Right side - Steps */}
            <div className="space-y-4 sm:space-y-6">
              {workflowSteps.map((step, index) => (
                <div
                  key={step.title}
                  className={`group relative flex gap-4 sm:gap-6 p-4 sm:p-6 rounded-xl sm:rounded-2xl bg-white/80 backdrop-blur-sm border border-gray-200/80 shadow-lg shadow-indigo-500/5 hover:shadow-xl hover:shadow-indigo-500/10 hover:border-indigo-200/50 transition-all duration-500 hover:-translate-y-1 dark:bg-slate-800/80 dark:border-slate-600/50 dark:hover:bg-slate-800 dark:shadow-lg dark:shadow-black/20 opacity-0 ${howItWorks.isVisible ? 'animate-[fade-in-up_0.5s_ease-out_forwards]' : ''}`}
                  style={{ animationDelay: `${0.3 + index * 0.15}s` }}
                >
                  {/* Icon column with connecting line between steps */}
                  <div className="flex-shrink-0 relative z-10 flex flex-col items-center">
                    <div className="flex h-11 w-11 sm:h-14 sm:w-14 items-center justify-center rounded-xl sm:rounded-2xl bg-indigo-600 shadow-lg shadow-indigo-500/25 group-hover:scale-105 transition-transform duration-300">
                      <step.icon className="h-5 w-5 sm:h-7 sm:w-7 text-white" />
                    </div>
                    {/* Connecting line extends from bottom of icon to bottom of card */}
                    {index < workflowSteps.length - 1 && (
                      <div className="hidden sm:block w-0.5 flex-1 mt-2 bg-indigo-500/40 dark:bg-indigo-500/30" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 sm:gap-3 mb-1.5 sm:mb-2">
                      <span className="inline-flex items-center justify-center h-5 w-5 sm:h-6 sm:w-6 rounded-full bg-indigo-100 text-[10px] sm:text-xs font-bold text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400 group-hover:scale-110 transition-transform">
                        {index + 1}
                      </span>
                      <h3 className="font-serif text-base sm:text-lg font-semibold text-gray-900 dark:text-white">{step.title}</h3>
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
          <div className="relative rounded-2xl sm:rounded-[40px] bg-slate-900 p-1 group">
            <div className="relative rounded-xl sm:rounded-[36px] bg-slate-900 px-5 py-10 sm:px-16 sm:py-20 text-center overflow-hidden">
              <h2 className="font-serif relative text-2xl sm:text-4xl md:text-5xl font-bold text-white mb-4 sm:mb-6">
                Ready to stop
                <br />
                switching tabs?
              </h2>
              <p className="relative text-base sm:text-xl text-slate-300 mb-8 sm:mb-10 max-w-2xl mx-auto px-2 sm:px-0">
                Write and publish with your team in one workspace.
                Free to start, and we do not ask for a card.
              </p>
              <div className="relative flex flex-col items-center gap-3 sm:gap-4">
                <Link
                  to="/register"
                  className="group/btn inline-flex items-center gap-2 px-6 py-3 sm:px-8 sm:py-4 text-sm sm:text-base font-semibold text-slate-900 bg-white hover:bg-gray-50 rounded-xl sm:rounded-2xl transition-all shadow-xl hover:shadow-2xl hover:-translate-y-1 w-full sm:w-auto justify-center"
                >
                  Start for free
                  <ArrowRight className="h-4 w-4 sm:h-5 sm:w-5 group-hover/btn:translate-x-1 transition-transform" />
                </Link>
                <a
                  href="#features"
                  className="text-sm text-slate-400 hover:text-white transition-colors underline underline-offset-2"
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
          <h3 className="font-serif text-lg sm:text-xl font-semibold text-gray-900 dark:text-white mb-3 sm:mb-4">
            Why we built it
          </h3>
          <p className="text-sm sm:text-base text-gray-600 dark:text-slate-400 leading-relaxed">
            ScholarHub started as a frustration project. Every paper meant juggling Overleaf, Zotero, Slack and
            Semantic Scholar at the same time, so we built the thing we kept wishing existed: one workspace for
            writing LaTeX, keeping references straight, talking to your team and asking an AI for help, without
            switching tabs.
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative border-t border-gray-200/80 dark:border-slate-700/50 bg-gradient-to-b from-gray-50 to-white dark:from-slate-900/50 dark:to-[#0f172a]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
          <div className="flex flex-col lg:flex-row items-start justify-between gap-8">
            {/* Brand */}
            <div className="max-w-sm">
              <Link to="/" className="group">
                <Logo className="group-hover:scale-105 transition-transform" />
              </Link>
              <p className="mt-3 sm:mt-4 text-sm sm:text-base text-gray-600 dark:text-slate-400">
                A workspace for research teams, from the first search to the submitted manuscript.
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
                <h4 className="font-semibold text-gray-900 dark:text-white mb-3 sm:mb-4 text-xs sm:text-sm">Get started</h4>
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
