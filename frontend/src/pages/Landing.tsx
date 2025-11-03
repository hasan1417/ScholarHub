import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Search, MessageSquare, ClipboardCheck, CheckCircle2, Users, FileText } from 'lucide-react'

const heroPromises = [
  {
    icon: CheckCircle2,
    text: 'Live LaTeX and rich-text drafting with reviewer presence.',
  },
  {
    icon: Users,
    text: 'Roles, locks, and decision history keep ownership clear.',
  },
  {
    icon: FileText,
    text: 'Journal-ready exports delivered in minutes, not days.',
  },
]

const heroProofStats = [
  {
    value: '18 labs',
    label: 'shipping weekly updates',
  },
  {
    value: '43% fewer',
    label: 'revision loops recorded',
  },
  {
    value: '<2 minutes',
    label: 'to export journal-ready LaTeX',
  },
]

const heroTestimonial = {
  quote:
    'ScholarHub let us keep timelines and reviewer decisions in one place—every submission closes with complete context.',
  author: 'Dr. Laila Hassan',
  role: 'PI, Precision Therapeutics Lab',
}

const Landing = () => {
  const [isVisible, setIsVisible] = useState(false)
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)

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

    if (typeof query.addListener === 'function') {
      const legacyListener = (event: MediaQueryListEvent) => handleChange(event)
      query.addListener(legacyListener)
      return () => query.removeListener(legacyListener)
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

  const heroAnimationCls = useMemo(() => {
    if (prefersReducedMotion) return 'opacity-100 translate-y-0'
    return isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
  }, [isVisible, prefersReducedMotion])

  const features = [
    {
      Icon: Search,
      title: 'Library Discovery feed',
      description: 'Surface new papers for your lab automatically, with inline citation snippets ready to attach to manuscripts.',
    },
    {
      Icon: MessageSquare,
      title: 'Meeting workspace',
      description: 'Run lab stand-ups, capture decisions, and assign follow-ups without leaving your manuscript workspace.',
    },
    {
      Icon: ClipboardCheck,
      title: 'Paper status at a glance',
      description: 'Track drafting milestones, reviewer ownership, and section locks so nothing stalls before submission.',
    },
  ]

  const workflowSteps = [
    {
      title: 'Create a shared paper space',
      detail: 'Invite your lab in seconds—no juggling Git, shared drives, or stale drafts.',
    },
    {
      title: 'Draft and review together',
      detail: 'Write, comment, and resolve feedback directly in the LaTeX editor with instant PDF previews.',
    },
    {
      title: 'Submit with confidence',
      detail: 'Track versions, lock critical sections, and export the final manuscript without surprises.',
    },
  ]

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
      {/* Navigation */}
      <nav className="border-b border-gray-200 bg-white/80 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/80">
        <div className="max-w-6xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <Link to="/" className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              ScholarHub
            </Link>
            <div className="flex items-center gap-4">
              <Link
                to="/login"
                className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors dark:text-gray-300 dark:hover:text-white"
              >
                Sign in
              </Link>
              <Link
                to="/register"
                className="px-5 py-2.5 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors shadow-sm dark:shadow-indigo-900/50"
              >
                Get started
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="px-6 py-28">
        <div className="max-w-4xl mx-auto">
          <div
            className={`text-center transition-all duration-700 ${heroAnimationCls}`}
          >
            <span className="inline-flex items-center gap-2 rounded-full border border-indigo-100 bg-indigo-50 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.28em] text-indigo-600">
              Research-ready by design
            </span>
            <h1 className="mt-6 text-5xl sm:text-6xl font-bold text-gray-900 leading-tight dark:text-gray-100">
              Ship papers faster with one workspace for your lab
            </h1>

            <p className="mt-6 text-xl text-gray-600 max-w-2xl mx-auto dark:text-gray-300">
              Keep your team aligned from first draft to submission. ScholarHub ties LaTeX, rich-text, comments, and exports into one cadence so every milestone stays visible.
            </p>

            <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link
                to="/register"
                className="group inline-flex items-center gap-2 px-7 py-3.5 text-base font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-all shadow-lg hover:shadow-xl dark:shadow-indigo-900/60"
              >
                Get started free
                <ArrowRight className="h-5 w-5 group-hover:translate-x-1 transition-transform" />
              </Link>
              <Link
                to="/docs/overview"
                className="inline-flex items-center gap-2 px-7 py-3.5 text-base font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors border border-indigo-100 dark:text-indigo-200 dark:bg-indigo-500/10 dark:border-indigo-500/40 dark:hover:bg-indigo-500/20"
              >
                Explore overview
                <ArrowRight className="h-5 w-5" />
              </Link>
            </div>

            <ul className="mt-10 grid gap-3 text-left sm:grid-cols-3">
              {heroPromises.map(({ icon: Icon, text }) => (
                <li
                  key={text}
                  className="flex items-start gap-3 rounded-2xl border border-indigo-100 bg-white/80 px-4 py-4 shadow-sm shadow-indigo-100/60 dark:bg-gray-900/70 dark:border-indigo-900 dark:shadow-indigo-950/40"
                >
                  <Icon className="mt-0.5 h-5 w-5 text-emerald-600" aria-hidden />
                  <span className="text-sm text-slate-700 leading-relaxed dark:text-gray-300">{text}</span>
                </li>
              ))}
            </ul>

            <div className="mt-12 flex flex-col gap-6 rounded-[28px] border border-indigo-100 bg-white/90 px-6 py-8 shadow-lg shadow-indigo-100/60 lg:flex-row lg:items-center lg:justify-between dark:border-indigo-900 dark:bg-gray-900/80 dark:shadow-indigo-950/40">
              <div className="grid flex-1 gap-4 sm:grid-cols-3">
                {heroProofStats.map(stat => (
                  <div
                    key={stat.label}
                    className="rounded-2xl border border-indigo-100 bg-indigo-50/60 px-4 py-4 text-left shadow-sm shadow-indigo-100/50 dark:border-indigo-900 dark:bg-indigo-500/15 dark:shadow-indigo-950/30"
                  >
                    <p className="text-xl font-semibold text-slate-900 dark:text-gray-100">{stat.value}</p>
                    <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-300">
                      {stat.label}
                    </p>
                  </div>
                ))}
              </div>
              <div className="flex-1 rounded-2xl border border-slate-200 bg-white px-6 py-5 text-left shadow-sm shadow-slate-100 lg:max-w-md dark:border-slate-700 dark:bg-slate-900/80 dark:shadow-slate-950/40">
                <p className="text-sm text-slate-700 leading-relaxed dark:text-gray-300">“{heroTestimonial.quote}”</p>
                <p className="mt-3 text-xs text-slate-500 dark:text-gray-400">
                  {heroTestimonial.author} · {heroTestimonial.role}
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Trust Builder */}
      <section className="px-6 pb-16">
        <div className="max-w-5xl mx-auto rounded-2xl border border-indigo-100 bg-white shadow-sm px-8 py-10">
          <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-8">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">Why lab leads stay with ScholarHub</p>
              <h2 className="mt-3 text-2xl font-semibold text-gray-900">
                Keep manuscript pipelines moving without chasing status updates across tools.
              </h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 text-left w-full lg:w-auto">
              <div className="rounded-xl border border-gray-100 bg-gray-50 px-4 py-3">
                <p className="text-sm font-semibold text-gray-900">Every decision stays linked</p>
                <p className="mt-1 text-sm text-gray-600">Live meeting notes and action lists stay beside the manuscript so no follow-up gets lost.</p>
              </div>
              <div className="rounded-xl border border-gray-100 bg-gray-50 px-4 py-3">
                <p className="text-sm font-semibold text-gray-900">No more progress ambiguity</p>
                <p className="mt-1 text-sm text-gray-600">Paper status dashboards show drafting milestones, reviewer ownership, and locks in real time.</p>
              </div>
              <div className="rounded-xl border border-gray-100 bg-gray-50 px-4 py-3">
                <p className="text-sm font-semibold text-gray-900">References arrive pre-contextualized</p>
                <p className="mt-1 text-sm text-gray-600">Discovery feed delivers suggested papers with ready-to-cite snippets—no manual triage spreadsheets.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="px-6 py-20">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-center text-3xl font-bold text-gray-900 mb-4">Run your lab from a single command center</h2>
          <p className="mx-auto mb-12 max-w-2xl text-center text-gray-600">
            ScholarHub rolls discovery, meeting operations, and paper health into one dashboard so lab leads can steer writing efforts without hopping between tools.
          </p>
          <div className="grid md:grid-cols-3 gap-8">
            {features.map(({ Icon, title, description }) => (
              <div key={title} className="p-7 rounded-2xl bg-white shadow-sm border border-gray-100 hover:shadow-lg transition-shadow">
                <div className="inline-flex items-center justify-center w-12 h-12 rounded-lg bg-indigo-600 mb-5">
                  <Icon className="h-6 w-6 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
                <p className="text-gray-600 leading-relaxed">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it Works */}
      <section id="how-it-works" className="px-6 pb-20">
        <div className="max-w-5xl mx-auto">
          <div className="rounded-3xl bg-white shadow-sm border border-gray-100 p-10">
            <div className="flex flex-col lg:flex-row gap-10 items-start">
              <div className="lg:w-1/3">
                <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">How it works</p>
                <h2 className="mt-3 text-3xl font-bold text-gray-900">From first draft to submission with less friction</h2>
                <p className="mt-4 text-gray-600">
                  ScholarHub replaces patchwork workflows with a single place to draft, discuss, and finalize manuscripts alongside your team.
                </p>
              </div>
              <div className="lg:flex-1 space-y-6">
                {workflowSteps.map((step, index) => (
                  <div key={step.title} className="flex items-start gap-4">
                    <div className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-indigo-50 text-indigo-600 font-semibold">
                      {index + 1}
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900">{step.title}</h3>
                      <p className="mt-1 text-gray-600 leading-relaxed">{step.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Final CTA Section */}
      <section className="px-6 py-24">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
            Ready to start your next paper?
          </h2>
          <p className="text-lg text-gray-600 mb-8">
            Join research teams who keep every collaborator aligned from outline to submission.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              to="/register"
              className="group inline-flex items-center gap-2 px-7 py-3.5 text-base font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-all shadow-lg hover:shadow-xl"
            >
              Create your account
              <ArrowRight className="h-5 w-5 group-hover:translate-x-1 transition-transform" />
            </Link>
            <Link
              to="/login"
              className="inline-flex items-center gap-2 px-7 py-3.5 text-base font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-all shadow-sm hover:shadow"
            >
              Sign in to your workspace
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-200 py-8 px-6 bg-white/50">
        <div className="max-w-6xl mx-auto">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-6">
            <div className="flex flex-col items-center sm:items-start gap-2">
              <span className="text-lg font-bold text-gray-900">ScholarHub</span>
              <p className="text-sm text-gray-500 text-center sm:text-left">
                Purpose-built for researchers who ship manuscripts together.
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-4 text-sm text-gray-500">
              <Link to="/register" className="hover:text-gray-900 transition-colors">Create account</Link>
              <Link to="/login" className="hover:text-gray-900 transition-colors">Sign in</Link>
              <a href="#features" className="hover:text-gray-900 transition-colors">Product</a>
              <a href="mailto:support@scholarhub.ai" className="hover:text-gray-900 transition-colors">Contact support</a>
            </div>
            <span className="text-sm text-gray-400 text-center sm:text-right">
              © 2025 ScholarHub. All rights reserved.
            </span>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default Landing
