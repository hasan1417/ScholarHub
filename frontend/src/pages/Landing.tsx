import { useEffect, useMemo, useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Search,
  MessageSquare,
  ClipboardCheck,
  CheckCircle2,
  Users,
  FileText,
  Sparkles,
  Zap,
  Shield,
  BookOpen,
  GitBranch,
  Globe,
} from 'lucide-react'
import { Logo } from '../components/brand/Logo'

const heroPromises = [
  {
    icon: CheckCircle2,
    text: 'Live LaTeX and rich-text drafting with real-time collaboration',
  },
  {
    icon: Users,
    text: 'Role-based access, section locks, and full revision history',
  },
  {
    icon: FileText,
    text: 'Journal-ready exports in minutes with AI-powered assistance',
  },
]

const heroProofStats = [
  {
    value: '8',
    label: 'Academic Sources',
    sublabel: 'integrated',
  },
  {
    value: '28',
    label: 'AI Functions',
    sublabel: 'built in',
  },
  {
    value: '3',
    label: 'Export Formats',
    sublabel: 'PDF, DOCX, ZIP',
  },
]

const heroPlatformHighlight = {
  headline: 'Built for Academic Teams',
  description:
    'Search across Semantic Scholar, OpenAlex, CORE, CrossRef, PubMed, ArXiv, ScienceDirect, and EuropePMC. Write in LaTeX or rich-text with real-time collaboration, AI-powered tools, and journal-ready exports.',
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
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 })

  // Scroll animation refs
  const socialProof = useScrollAnimation(0.2)
  const features = useScrollAnimation(0.1)
  const howItWorks = useScrollAnimation(0.2)
  const finalCta = useScrollAnimation(0.2)

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

  // Track mouse for parallax effect
  useEffect(() => {
    if (prefersReducedMotion) return

    const handleMouseMove = (e: MouseEvent) => {
      setMousePosition({
        x: (e.clientX / window.innerWidth - 0.5) * 20,
        y: (e.clientY / window.innerHeight - 0.5) * 20,
      })
    }

    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [prefersReducedMotion])

  const heroAnimationCls = useMemo(() => {
    if (prefersReducedMotion) return 'opacity-100 translate-y-0'
    return isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
  }, [isVisible, prefersReducedMotion])

  const featuresList = [
    {
      Icon: Search,
      title: 'Smart Discovery Feed',
      description: 'AI surfaces relevant papers for your research with citation snippets ready to attach.',
      gradient: 'from-blue-500 to-cyan-500',
    },
    {
      Icon: MessageSquare,
      title: 'Integrated Discussions',
      description: 'Run lab meetings, capture decisions, and assign tasks without leaving your workspace.',
      gradient: 'from-violet-500 to-purple-500',
    },
    {
      Icon: ClipboardCheck,
      title: 'Paper Status Dashboard',
      description: 'Track milestones, reviewer ownership, and section locks at a glance.',
      gradient: 'from-amber-500 to-orange-500',
    },
    {
      Icon: Sparkles,
      title: 'AI Writing Assistant',
      description: 'Get intelligent suggestions, extend paragraphs, and improve your academic writing.',
      gradient: 'from-pink-500 to-rose-500',
    },
    {
      Icon: GitBranch,
      title: 'Version Control',
      description: 'Full revision history with the ability to compare and restore previous versions.',
      gradient: 'from-emerald-500 to-teal-500',
    },
    {
      Icon: Globe,
      title: 'Reference Management',
      description: 'Import from any source, organize collections, and auto-format citations.',
      gradient: 'from-indigo-500 to-blue-500',
    },
  ]

  const workflowSteps = [
    {
      icon: Zap,
      title: 'Create your workspace',
      detail: 'Set up a project in seconds. Invite collaborators with role-based permissions.',
    },
    {
      icon: BookOpen,
      title: 'Write together in real-time',
      detail: 'Draft in LaTeX or rich-text with live collaboration, comments, and instant previews.',
    },
    {
      icon: Shield,
      title: 'Submit with confidence',
      detail: 'Lock sections, track all changes, and export publication-ready manuscripts.',
    },
  ]

  return (
    <div className="min-h-screen bg-white dark:bg-slate-950 overflow-hidden">
      {/* CSS Animations */}
      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px) rotate(0deg); }
          50% { transform: translateY(-20px) rotate(2deg); }
        }
        @keyframes float-slow {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-30px); }
        }
        @keyframes float-reverse {
          0%, 100% { transform: translateY(-20px) rotate(-2deg); }
          50% { transform: translateY(0px) rotate(0deg); }
        }
        @keyframes pulse-glow {
          0%, 100% { opacity: 0.2; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(1.05); }
        }
        @keyframes shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        @keyframes gradient-x {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }
        @keyframes bounce-subtle {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-5px); }
        }
        @keyframes spin-slow {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes fade-in-up {
          from { opacity: 0; transform: translateY(30px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes scale-in {
          from { opacity: 0; transform: scale(0.9); }
          to { opacity: 1; transform: scale(1); }
        }
        .animate-float { animation: float 6s ease-in-out infinite; }
        .animate-float-slow { animation: float-slow 8s ease-in-out infinite; }
        .animate-float-reverse { animation: float-reverse 7s ease-in-out infinite; }
        .animate-pulse-glow { animation: pulse-glow 4s ease-in-out infinite; }
        .animate-shimmer {
          background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
          background-size: 200% 100%;
          animation: shimmer 2s infinite;
        }
        .animate-gradient-x {
          background-size: 200% 200%;
          animation: gradient-x 3s ease infinite;
        }
        .animate-bounce-subtle { animation: bounce-subtle 2s ease-in-out infinite; }
        .animate-spin-slow { animation: spin-slow 20s linear infinite; }
        .stagger-1 { animation-delay: 0.1s; }
        .stagger-2 { animation-delay: 0.2s; }
        .stagger-3 { animation-delay: 0.3s; }
        .stagger-4 { animation-delay: 0.4s; }
        .stagger-5 { animation-delay: 0.5s; }
        .stagger-6 { animation-delay: 0.6s; }
      `}</style>

      {/* Animated Background */}
      <div className="fixed inset-0 -z-10">
        {/* Light mode gradient with animated blobs */}
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-50 via-white to-purple-50 dark:opacity-0 transition-opacity duration-500" />
        <div className="absolute inset-0 dark:opacity-0 transition-opacity duration-500 overflow-hidden">
          <div
            className="absolute -top-32 -left-32 w-[500px] h-[500px] bg-indigo-200/50 rounded-full blur-[100px] animate-pulse-glow"
            style={{ transform: `translate(${mousePosition.x * 0.3}px, ${mousePosition.y * 0.3}px)` }}
          />
          <div
            className="absolute -bottom-32 -right-32 w-[500px] h-[500px] bg-purple-200/50 rounded-full blur-[100px] animate-pulse-glow"
            style={{ animationDelay: '2s', transform: `translate(${mousePosition.x * -0.2}px, ${mousePosition.y * -0.2}px)` }}
          />
          <div
            className="absolute top-1/3 right-1/4 w-[400px] h-[400px] bg-pink-200/30 rounded-full blur-[80px] animate-pulse-glow"
            style={{ animationDelay: '1s' }}
          />
          <div
            className="absolute bottom-1/3 left-1/4 w-[350px] h-[350px] bg-cyan-200/30 rounded-full blur-[80px] animate-pulse-glow"
            style={{ animationDelay: '3s' }}
          />
        </div>
        {/* Dark mode gradient with animated blobs */}
        <div className="absolute inset-0 opacity-0 dark:opacity-100 transition-opacity duration-500">
          <div className="absolute inset-0 bg-slate-950" />
          <div
            className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-indigo-500/20 rounded-full blur-[128px] animate-pulse-glow"
            style={{ transform: `translate(${mousePosition.x * 0.5}px, ${mousePosition.y * 0.5}px)` }}
          />
          <div
            className="absolute bottom-0 right-1/4 w-[600px] h-[600px] bg-purple-500/20 rounded-full blur-[128px] animate-pulse-glow"
            style={{ animationDelay: '2s', transform: `translate(${mousePosition.x * -0.3}px, ${mousePosition.y * -0.3}px)` }}
          />
          <div
            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-blue-500/10 rounded-full blur-[128px] animate-pulse-glow"
            style={{ animationDelay: '1s' }}
          />
        </div>
        {/* Grid pattern */}
        <div
          className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05]"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%236366f1' fill-opacity='0.4'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
          }}
        />
        {/* Floating particles for light mode */}
        <div className="absolute inset-0 dark:opacity-0 overflow-hidden pointer-events-none">
          <div className="absolute top-20 left-[10%] w-2 h-2 bg-indigo-400/40 rounded-full animate-float" />
          <div className="absolute top-40 right-[15%] w-3 h-3 bg-purple-400/30 rounded-full animate-float-slow" />
          <div className="absolute top-60 left-[30%] w-1.5 h-1.5 bg-pink-400/40 rounded-full animate-float-reverse" />
          <div className="absolute bottom-40 right-[25%] w-2 h-2 bg-indigo-400/30 rounded-full animate-float" style={{ animationDelay: '1s' }} />
          <div className="absolute bottom-60 left-[20%] w-2.5 h-2.5 bg-purple-400/35 rounded-full animate-float-slow" style={{ animationDelay: '2s' }} />
          <div className="absolute top-1/3 right-[10%] w-2 h-2 bg-cyan-400/30 rounded-full animate-float-reverse" style={{ animationDelay: '0.5s' }} />
        </div>
        {/* Floating particles for dark mode */}
        <div className="absolute inset-0 opacity-0 dark:opacity-100 overflow-hidden pointer-events-none">
          <div className="absolute top-20 left-[10%] w-2 h-2 bg-indigo-400/30 rounded-full animate-float" />
          <div className="absolute top-40 right-[15%] w-3 h-3 bg-purple-400/20 rounded-full animate-float-slow" />
          <div className="absolute top-60 left-[30%] w-1.5 h-1.5 bg-blue-400/30 rounded-full animate-float-reverse" />
          <div className="absolute bottom-40 right-[25%] w-2 h-2 bg-indigo-400/20 rounded-full animate-float" style={{ animationDelay: '1s' }} />
          <div className="absolute bottom-60 left-[20%] w-2.5 h-2.5 bg-purple-400/25 rounded-full animate-float-slow" style={{ animationDelay: '2s' }} />
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
              <Link
                to="/login"
                className="px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors dark:text-slate-400 dark:hover:text-white"
              >
                Sign in
              </Link>
              <Link
                to="/register"
                className="group px-3 py-2 sm:px-5 sm:py-2.5 text-xs sm:text-sm font-semibold text-white bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-600 rounded-xl transition-all shadow-lg shadow-indigo-500/25 hover:shadow-xl hover:shadow-indigo-500/30 hover:-translate-y-0.5 overflow-hidden relative"
              >
                <span className="relative z-10">Get started</span>
                <div className="absolute inset-0 animate-shimmer opacity-0 group-hover:opacity-100" />
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative px-4 sm:px-6 pt-12 sm:pt-20 pb-20 sm:pb-32">
        {/* Decorative floating elements - hidden on mobile for performance */}
        <div className="hidden sm:block absolute top-32 left-10 w-72 h-72 bg-gradient-to-br from-indigo-300/50 to-purple-300/50 dark:from-indigo-500/10 dark:to-purple-500/10 rounded-full blur-3xl animate-float-slow pointer-events-none" />
        <div className="hidden sm:block absolute bottom-20 right-10 w-96 h-96 bg-gradient-to-br from-purple-300/40 to-pink-300/40 dark:from-purple-500/10 dark:to-pink-500/10 rounded-full blur-3xl animate-float-reverse pointer-events-none" />
        <div className="hidden md:block absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-to-br from-cyan-200/20 to-indigo-200/20 dark:from-transparent dark:to-transparent rounded-full blur-3xl animate-pulse-glow pointer-events-none" />

        <div className="max-w-5xl mx-auto">
          <div className={`text-center transition-all duration-1000 ease-out ${heroAnimationCls}`}>
            {/* Badge */}
            <div
              className="inline-flex items-center gap-1.5 sm:gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-indigo-700 dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-300 hover:scale-105 transition-transform cursor-default"
              style={{ animationDelay: '0.2s' }}
            >
              <Sparkles className="h-3.5 w-3.5 sm:h-4 sm:w-4 animate-pulse" />
              <span>AI-Powered Research Platform</span>
            </div>

            {/* Main headline with gradient animation */}
            <h1 className="mt-6 sm:mt-8 text-3xl sm:text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight">
              <span className="bg-gradient-to-r from-gray-900 via-gray-800 to-gray-900 dark:from-white dark:via-gray-100 dark:to-white bg-clip-text text-transparent inline-block transition-transform hover:scale-[1.02] duration-300 pb-1">
                Ship papers faster
              </span>
              <br />
              <span className="bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-600 bg-clip-text text-transparent animate-gradient-x inline-block pb-2">
                with your team
              </span>
            </h1>

            {/* Subheadline */}
            <p className="mt-5 sm:mt-8 text-base sm:text-xl text-gray-600 max-w-2xl mx-auto leading-relaxed dark:text-slate-400 px-2 sm:px-0">
              The all-in-one workspace for research teams. Write in LaTeX or rich-text,
              collaborate in real-time, discover papers, and submit with confidence.
            </p>

            {/* CTA Button */}
            <div className="mt-8 sm:mt-12">
              <Link
                to="/register"
                className="group relative inline-flex items-center gap-2 px-6 py-3 sm:px-8 sm:py-4 text-sm sm:text-base font-semibold text-white bg-gradient-to-r from-indigo-600 to-purple-600 rounded-xl sm:rounded-2xl transition-all shadow-xl shadow-indigo-500/25 hover:shadow-2xl hover:shadow-indigo-500/40 hover:-translate-y-1 overflow-hidden"
              >
                <span className="absolute inset-0 rounded-xl sm:rounded-2xl bg-gradient-to-r from-indigo-600 to-purple-600 blur-xl opacity-50 group-hover:opacity-75 transition-opacity" />
                <span className="relative flex items-center gap-2">
                  Start for free
                  <ArrowRight className="h-4 w-4 sm:h-5 sm:w-5 group-hover:translate-x-1 transition-transform" />
                </span>
                <div className="absolute inset-0 animate-shimmer opacity-0 group-hover:opacity-100" />
              </Link>
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

      {/* Social Proof Section */}
      <section ref={socialProof.ref} className="relative px-4 sm:px-6 py-12 sm:py-20">
        <div className={`max-w-5xl mx-auto transition-all duration-700 ${socialProof.isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'}`}>
          <div className="relative rounded-2xl sm:rounded-[32px] bg-gradient-to-br from-slate-900 to-slate-800 dark:from-slate-800/50 dark:to-slate-900/50 p-1 overflow-hidden">
            <div className="absolute inset-0 rounded-2xl sm:rounded-[32px] bg-gradient-to-br from-indigo-500 to-purple-500 opacity-0 dark:opacity-20 blur-xl animate-pulse-glow" />
            <div className="relative rounded-xl sm:rounded-[28px] bg-gradient-to-br from-slate-900 to-slate-800 dark:from-slate-800 dark:to-slate-900 p-5 sm:p-8 lg:p-12 overflow-hidden">
              {/* Animated background pattern */}
              <div className="absolute inset-0 opacity-5">
                <div className="absolute top-0 left-0 w-full h-full" style={{
                  backgroundImage: 'radial-gradient(circle at 2px 2px, white 1px, transparent 0)',
                  backgroundSize: '40px 40px'
                }} />
              </div>

              <div className="relative grid lg:grid-cols-2 gap-6 sm:gap-10">
                {/* Stats */}
                <div className="grid grid-cols-3 gap-2 sm:gap-4">
                  {heroProofStats.map((stat, index) => (
                    <div
                      key={stat.label}
                      className={`relative group opacity-0 ${socialProof.isVisible ? 'animate-[scale-in_0.5s_ease-out_forwards]' : ''}`}
                      style={{ animationDelay: `${0.2 + index * 0.15}s` }}
                    >
                      <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/20 to-purple-500/20 rounded-xl sm:rounded-2xl blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                      <div className="relative rounded-xl sm:rounded-2xl bg-white/5 border border-white/10 p-3 sm:p-6 text-center hover:bg-white/10 transition-all duration-300 hover:scale-105 hover:-translate-y-1">
                        <p className="text-2xl sm:text-4xl font-bold bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">
                          {stat.value}
                        </p>
                        <p className="mt-1 sm:mt-2 text-xs sm:text-sm font-semibold text-white">{stat.label}</p>
                        <p className="text-[10px] sm:text-xs text-slate-400 hidden sm:block">{stat.sublabel}</p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Platform Highlight */}
                <div className={`flex flex-col justify-center opacity-0 ${socialProof.isVisible ? 'animate-[fade-in-up_0.6s_ease-out_0.4s_forwards]' : ''}`}>
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
              <Zap className="h-3.5 w-3.5 sm:h-4 sm:w-4 animate-pulse" />
              <span>Powerful Features</span>
            </div>
            <h2 className="text-2xl sm:text-4xl md:text-5xl font-bold text-gray-900 dark:text-white">
              Everything you need to
              <br />
              <span className="bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent animate-gradient-x">
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
                className={`group relative rounded-2xl sm:rounded-3xl bg-white/80 backdrop-blur-sm p-5 sm:p-8 shadow-lg shadow-indigo-500/5 border border-gray-200/80 hover:shadow-xl hover:shadow-indigo-500/10 hover:border-indigo-200/50 transition-all duration-500 hover:-translate-y-2 dark:bg-slate-800/50 dark:border-slate-700 dark:hover:bg-slate-800 dark:hover:border-slate-600 dark:shadow-none opacity-0 ${features.isVisible ? 'animate-[fade-in-up_0.5s_ease-out_forwards]' : ''}`}
                style={{ animationDelay: `${0.1 + index * 0.1}s` }}
              >
                {/* Hover glow effect */}
                <div className={`absolute inset-0 rounded-2xl sm:rounded-3xl bg-gradient-to-br ${gradient} opacity-0 group-hover:opacity-10 transition-opacity duration-500 blur-xl`} />

                <div className={`relative inline-flex items-center justify-center w-11 h-11 sm:w-14 sm:h-14 rounded-xl sm:rounded-2xl bg-gradient-to-br ${gradient} mb-4 sm:mb-6 shadow-lg group-hover:scale-110 group-hover:rotate-3 transition-all duration-300`}>
                  <Icon className="h-5 w-5 sm:h-7 sm:w-7 text-white" />
                </div>
                <h3 className="relative text-lg sm:text-xl font-semibold text-gray-900 mb-2 sm:mb-3 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">{title}</h3>
                <p className="relative text-sm sm:text-base text-gray-600 leading-relaxed dark:text-slate-400">{description}</p>

                {/* Arrow indicator on hover - hidden on mobile */}
                <div className="hidden sm:block absolute bottom-8 right-8 opacity-0 group-hover:opacity-100 transform translate-x-2 group-hover:translate-x-0 transition-all duration-300">
                  <ArrowRight className="h-5 w-5 text-indigo-500" />
                </div>
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
                <CheckCircle2 className="h-3.5 w-3.5 sm:h-4 sm:w-4 animate-bounce-subtle" />
                <span>Simple Workflow</span>
              </div>
              <h2 className="text-2xl sm:text-4xl md:text-5xl font-bold text-gray-900 dark:text-white leading-tight">
                From first draft to
                <br />
                <span className="bg-gradient-to-r from-emerald-600 to-teal-600 bg-clip-text text-transparent animate-gradient-x">
                  publication
                </span>
              </h2>
              <p className="mt-4 sm:mt-6 text-base sm:text-lg text-gray-600 dark:text-slate-400">
                ScholarHub streamlines your entire research workflow. No more scattered files,
                lost comments, or version confusion.
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
                  {/* Connecting line - hidden on mobile */}
                  {index < workflowSteps.length - 1 && (
                    <div className="hidden sm:block absolute left-[43px] top-[80px] w-0.5 h-[calc(100%-40px)] bg-gradient-to-b from-indigo-500/50 to-purple-500/50 dark:from-indigo-500/30 dark:to-purple-500/30" />
                  )}

                  <div className="flex-shrink-0 relative z-10">
                    <div className="flex h-11 w-11 sm:h-14 sm:w-14 items-center justify-center rounded-xl sm:rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-500 shadow-lg shadow-indigo-500/25 group-hover:scale-110 group-hover:rotate-6 transition-all duration-300">
                      <step.icon className="h-5 w-5 sm:h-7 sm:w-7 text-white" />
                    </div>
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
            <div className="absolute inset-0 rounded-2xl sm:rounded-[40px] bg-gradient-to-br from-indigo-600 to-purple-600 blur-2xl opacity-50 group-hover:opacity-75 transition-opacity duration-500 animate-pulse-glow" />
            <div className="relative rounded-xl sm:rounded-[36px] bg-gradient-to-br from-indigo-600 to-purple-600 px-5 py-10 sm:px-16 sm:py-20 text-center overflow-hidden">
              {/* Animated decorative elements - hidden on mobile for performance */}
              <div className="hidden sm:block absolute top-8 left-8 h-20 w-20 rounded-full bg-white/10 blur-2xl animate-float" />
              <div className="hidden sm:block absolute bottom-8 right-8 h-32 w-32 rounded-full bg-purple-400/20 blur-2xl animate-float-reverse" />
              <div className="hidden md:block absolute top-1/2 left-1/4 h-16 w-16 rounded-full bg-indigo-400/20 blur-xl animate-float-slow" />

              {/* Spinning gradient ring - hidden on mobile */}
              <div className="hidden md:block absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] opacity-20">
                <div className="absolute inset-0 rounded-full border-2 border-white/20 animate-spin-slow" />
                <div className="absolute inset-8 rounded-full border border-white/10 animate-spin-slow" style={{ animationDirection: 'reverse', animationDuration: '30s' }} />
              </div>

              <h2 className="relative text-2xl sm:text-4xl md:text-5xl font-bold text-white mb-4 sm:mb-6">
                Ready to transform your
                <br />
                research workflow?
              </h2>
              <p className="relative text-base sm:text-xl text-indigo-100 mb-8 sm:mb-10 max-w-2xl mx-auto px-2 sm:px-0">
                Write, collaborate, and publish research papers with your team.
                Start free, no credit card required.
              </p>
              <div className="relative flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4">
                <Link
                  to="/register"
                  className="group/btn inline-flex items-center gap-2 px-6 py-3 sm:px-8 sm:py-4 text-sm sm:text-base font-semibold text-indigo-600 bg-white hover:bg-gray-50 rounded-xl sm:rounded-2xl transition-all shadow-xl hover:shadow-2xl hover:-translate-y-1 hover:scale-105 w-full sm:w-auto justify-center"
                >
                  Get started for free
                  <ArrowRight className="h-4 w-4 sm:h-5 sm:w-5 group-hover/btn:translate-x-1 transition-transform" />
                </Link>
                <Link
                  to="/login"
                  className="inline-flex items-center gap-2 px-6 py-3 sm:px-8 sm:py-4 text-sm sm:text-base font-semibold text-white border-2 border-white/30 hover:bg-white/10 hover:border-white/50 rounded-xl sm:rounded-2xl transition-all hover:-translate-y-0.5 w-full sm:w-auto justify-center"
                >
                  Sign in to workspace
                </Link>
              </div>
            </div>
          </div>
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
                </ul>
              </div>
              <div>
                <h4 className="font-semibold text-gray-900 dark:text-white mb-3 sm:mb-4 text-xs sm:text-sm">Company</h4>
                <ul className="space-y-2 sm:space-y-3">
                  <li><span className="text-xs sm:text-sm text-gray-600 dark:text-slate-400">Contact</span></li>
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
