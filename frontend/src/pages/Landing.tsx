/* Hallmark · macrostructure: Workbench · genre: modern-minimal
 * nav: N5 floating pill · footer: Ft5 statement · theme: brand-indigo (single anchor hue)
 * enrichment: existing multi-scene product mockup (Tier-A, hand-built)
 * reveal: one orchestrated entrance on load; no scroll-triggered reveals
 * tone: utilitarian · anchor hue: indigo 600
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Search,
  MessageSquare,
  GitBranch,
  Globe,
  Bot,
  PenTool,
} from 'lucide-react'
import { Logo } from '../components/brand/Logo'
import HeroAnimatedMockup from '../components/landing/HeroAnimatedMockup'

const focusRing =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600 focus-visible:ring-offset-2 focus-visible:ring-offset-[#fcfcfd] dark:focus-visible:ring-offset-[#0f172a]'

const platformSummary =
  'One search covers nine academic databases, PubMed, ArXiv and Semantic Scholar among them. Your Zotero references come across intact, and what your team writes exports as a manuscript ready to submit.'

/* The tour. Workbench voice: what you do with it, not what it "empowers" you to do. */
const tour = [
  {
    Icon: Search,
    title: 'Paper discovery',
    description:
      'One query searches Semantic Scholar, PubMed, ArXiv and six other databases. Results come back deduplicated across sources, with citation snippets you can attach in a click.',
  },
  {
    Icon: Globe,
    title: 'Reference management',
    description:
      'Import from Zotero or BibTeX and organize your collections. Citations reformat themselves to whichever journal style you need.',
  },
  {
    Icon: GitBranch,
    title: 'Real-time collaboration',
    description:
      'Write together in LaTeX with live cursors, section locks, role-based access and full revision history. Tectonic compiles as you type, with full package support and a live PDF preview beside the source.',
  },
  {
    Icon: Bot,
    title: 'AI research assistant',
    description:
      'An assistant that can see your project. It searches papers, reads and summarizes your library, and answers questions without you leaving the discussion channel.',
  },
  {
    Icon: PenTool,
    title: 'AI editor copilot',
    description:
      'Writing help built into the editor itself. Extend a paragraph, tighten the academic tone, or fix grammar, with suggestions appearing inline as you write.',
  },
  {
    Icon: MessageSquare,
    title: 'Team discussions',
    description:
      'Channels for the research conversation, sitting next to the papers they are about. Run a lab meeting, record what was decided, and assign the follow-ups.',
  },
]

const workflowSteps = [
  {
    title: 'Import your existing work',
    detail:
      'Bring your Zotero library, your BibTeX files, and papers you have already started. Setting up a project and inviting your co-authors takes under a minute.',
  },
  {
    title: 'Draft with AI in the editor',
    detail:
      'Write in LaTeX with a copilot for the prose, an assistant for research questions, and discovery across nine databases. All of it in the same editor.',
  },
  {
    title: 'Export and submit anywhere',
    detail:
      'Generate submission-ready PDFs in IEEE, ACM, NeurIPS or another format. Your .tex source and .bib files stay downloadable at any point.',
  },
]

const footerLinks: { label: string; to?: string; href?: string }[] = [
  { label: 'Features', href: '#features' },
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Pricing', to: '/pricing' },
  { label: 'Contact', href: 'mailto:support@scholarhub.space' },
  { label: 'Privacy', to: '/privacy' },
  { label: 'Terms', to: '/terms' },
  { label: 'Sign in', to: '/login' },
]

const scrollTo = (id: string) => (e: React.MouseEvent) => {
  e.preventDefault()
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
}

const Landing = () => {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    setPrefersReducedMotion(query.matches)

    if (typeof query.addEventListener === 'function') {
      const listener = (event: MediaQueryListEvent) => setPrefersReducedMotion(event.matches)
      query.addEventListener('change', listener)
      return () => query.removeEventListener('change', listener)
    }

    return undefined
  }, [])

  return (
    <div className="min-h-screen bg-[#fcfcfd] dark:bg-[#0f172a]">
      {/* N5 - floating pill nav. Detached, content-sized, blurs over the page beneath it. */}
      <nav
        aria-label="Primary"
        className="fixed left-1/2 top-4 z-50 w-[calc(100%-2rem)] -translate-x-1/2 sm:w-auto"
      >
        <div className="mx-auto flex items-center justify-between gap-3 rounded-full border border-gray-200/80 bg-white/80 px-3 py-2 shadow-[0_8px_24px_-12px_rgba(15,23,42,0.18)] backdrop-blur-md sm:gap-6 dark:border-slate-700/70 dark:bg-slate-900/80">
          <Link to="/" className={`rounded-full ${focusRing}`} aria-label="ScholarHub home">
            <Logo textClassName="text-sm sm:text-base" />
          </Link>

          <div className="hidden items-center gap-1 sm:flex">
            <a
              href="#features"
              onClick={scrollTo('features')}
              className={`rounded-full px-3 py-1.5 text-sm text-gray-600 transition-[color] duration-150 ease-out hover:text-gray-900 dark:text-slate-400 dark:hover:text-white ${focusRing}`}
            >
              Features
            </a>
            <a
              href="#how-it-works"
              onClick={scrollTo('how-it-works')}
              className={`rounded-full px-3 py-1.5 text-sm text-gray-600 transition-[color] duration-150 ease-out hover:text-gray-900 dark:text-slate-400 dark:hover:text-white ${focusRing}`}
            >
              How it works
            </a>
          </div>

          <div className="flex items-center gap-1 sm:gap-2">
            <Link
              to="/login"
              className={`rounded-full px-3 py-1.5 text-sm text-gray-600 transition-[color] duration-150 ease-out hover:text-gray-900 dark:text-slate-400 dark:hover:text-white ${focusRing}`}
            >
              Sign in
            </Link>
            <Link
              to="/register"
              className={`rounded-full bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition-[background-color] duration-150 ease-out hover:bg-indigo-700 ${focusRing}`}
            >
              Start free
            </Link>
          </div>
        </div>
      </nav>

      <HeroAnimatedMockup
        reduced={prefersReducedMotion}
        heroAnimationCls="opacity-100 translate-y-0"
      />

      {/* Summary band. Left-biased, hairline-ruled, no card, no nested container. */}
      <section className="border-y border-gray-200/80 bg-white px-4 sm:px-6 dark:border-slate-800 dark:bg-slate-900/40">
        <div className="mx-auto grid max-w-6xl gap-6 py-12 sm:py-16 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-16">
          <h2 className="font-serif text-2xl font-semibold leading-snug text-gray-900 sm:text-3xl dark:text-white">
            Built for academic teams
          </h2>
          <p className="text-base leading-relaxed text-gray-600 sm:text-lg dark:text-slate-400">
            {platformSummary}
          </p>
        </div>
      </section>

      {/* The tour. Sticky label left, ruled list right. No cards, no icon tiles, no grid of thirds. */}
      <section id="features" className="px-4 py-20 sm:px-6 sm:py-28">
        <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[minmax(0,3fr)_minmax(0,9fr)] lg:gap-20">
          <div className="lg:sticky lg:top-28 lg:self-start">
            <h2 className="font-serif text-2xl font-semibold leading-tight text-gray-900 sm:text-4xl dark:text-white">
              What replaces your
              <br className="hidden sm:block" /> other five tabs
            </h2>
            <p className="mt-4 max-w-sm text-sm text-gray-600 sm:text-base dark:text-slate-400">
              Writing, references, discovery and team discussion all live in the same workspace.
            </p>
          </div>

          <ul className="divide-y divide-gray-200/80 border-t border-gray-200/80 dark:divide-slate-800 dark:border-slate-800">
            {tour.map(({ Icon, title, description }) => (
              <li key={title} className="py-6 sm:py-8">
                <h3 className="flex items-center gap-3 font-serif text-lg font-semibold text-gray-900 sm:text-xl dark:text-white">
                  <Icon className="h-5 w-5 shrink-0 text-indigo-600 dark:text-indigo-400" aria-hidden />
                  {title}
                </h3>
                <p className="mt-2 max-w-2xl text-sm leading-relaxed text-gray-600 sm:text-base dark:text-slate-400">
                  {description}
                </p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Workflow. Numbered stages on a single rule. Deliberately narrower than the tour above. */}
      <section
        id="how-it-works"
        className="border-t border-gray-200/80 bg-white px-4 py-16 sm:px-6 sm:py-20 dark:border-slate-800 dark:bg-slate-900/40"
      >
        <div className="mx-auto max-w-3xl">
          <h2 className="font-serif text-2xl font-semibold text-gray-900 sm:text-4xl dark:text-white">
            From first draft to publication
          </h2>
          <p className="mt-4 max-w-xl text-base text-gray-600 dark:text-slate-400">
            Your editor, your reference manager and your team chat stop being three separate places
            you have to keep open.
          </p>

          <ol className="mt-10 border-l border-gray-200 dark:border-slate-800">
            {workflowSteps.map((step, index) => (
              <li key={step.title} className="relative pb-8 pl-8 last:pb-0 sm:pl-10">
                <span
                  className="absolute -left-[9px] top-1 flex h-[18px] w-[18px] items-center justify-center rounded-full bg-indigo-600 text-2xs font-bold text-white"
                  aria-hidden
                >
                  {index + 1}
                </span>
                <h3 className="font-serif text-base font-semibold text-gray-900 sm:text-lg dark:text-white">
                  {step.title}
                </h3>
                <p className="mt-1.5 text-sm leading-relaxed text-gray-600 sm:text-base dark:text-slate-400">
                  {step.detail}
                </p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Why we built it. Kept plain: it is the one first-person passage on the page. */}
      <section className="px-4 py-14 sm:px-6 sm:py-20">
        <div className="mx-auto max-w-2xl">
          <h2 className="font-serif text-lg font-semibold text-gray-900 sm:text-xl dark:text-white">
            Why we built it
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-gray-600 sm:text-base dark:text-slate-400">
            ScholarHub started as a frustration project. Every paper meant juggling Overleaf, Zotero,
            Slack and Semantic Scholar at the same time, so we built the thing we kept wishing
            existed: one workspace for writing LaTeX, keeping references straight, talking to your
            team and asking an AI for help, without switching tabs.
          </p>
        </div>
      </section>

      {/* CTA band. Left-biased, not a centred hero-in-a-box. */}
      <section className="bg-gray-900 px-4 py-14 sm:px-6 sm:py-16 dark:bg-slate-800/60">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="font-serif text-2xl font-semibold leading-tight text-white sm:text-4xl">
              Ready to stop switching tabs?
            </h2>
            <p className="mt-3 max-w-md text-sm text-gray-300 sm:text-base">
              Write and publish with your team in one workspace. Free to start, and we do not ask for
              a card.
            </p>
          </div>
          <Link
            to="/register"
            className="group inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-white px-6 py-3 text-sm font-semibold text-gray-900 transition-[background-color] duration-150 ease-out hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 sm:text-base"
          >
            Start for free
            <ArrowRight
              className="h-4 w-4 transition-[transform] duration-150 ease-out group-hover:translate-x-0.5"
              aria-hidden
            />
          </Link>
        </div>
      </section>

      {/* Ft5 - Statement footer. A closing line, not a sitemap. */}
      <footer className="px-4 py-14 sm:px-6 sm:py-20">
        <div className="mx-auto max-w-6xl">
          <p className="font-serif max-w-[24ch] text-2xl font-semibold leading-[1.1] tracking-tight text-gray-900 sm:text-4xl dark:text-white">
            One workspace, from the first search to the submitted manuscript.
          </p>

          <div className="mt-10 flex flex-col gap-4 border-t border-gray-200 pt-6 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800">
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
              {footerLinks.map((link) =>
                link.to ? (
                  <Link
                    key={link.label}
                    to={link.to}
                    className={`rounded text-xs text-gray-600 transition-[color] duration-150 ease-out hover:text-gray-900 sm:text-sm dark:text-slate-400 dark:hover:text-white ${focusRing}`}
                  >
                    {link.label}
                  </Link>
                ) : (
                  <a
                    key={link.label}
                    href={link.href}
                    onClick={link.href?.startsWith('#') ? scrollTo(link.href.slice(1)) : undefined}
                    className={`rounded text-xs text-gray-600 transition-[color] duration-150 ease-out hover:text-gray-900 sm:text-sm dark:text-slate-400 dark:hover:text-white ${focusRing}`}
                  >
                    {link.label}
                  </a>
                )
              )}
            </div>
            <p className="text-xs text-gray-500 dark:text-slate-400">
              © {new Date().getFullYear()} ScholarHub
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default Landing
