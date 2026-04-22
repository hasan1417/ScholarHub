import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Sparkles, Check, Users, Send, Loader2, Search, BookmarkPlus, FileText } from 'lucide-react'

type Phase =
  | 'idle'
  | 'd-typing'
  | 'd-searching'
  | 'd-results'
  | 'd-adding'
  | 'lib-open'
  | 'lib-settled'
  | 'edit-open'
  | 'edit-prompting'
  | 'edit-sent'
  | 'edit-thinking'
  | 'edit-responding'
  | 'edit-proposing'
  | 'edit-applying'
  | 'edit-applied'

type Scene = 'discover' | 'library' | 'editor'

const getScene = (p: Phase): Scene => {
  if (p.startsWith('d-') || p === 'idle') return 'discover'
  if (p.startsWith('lib-')) return 'library'
  return 'editor'
}

const SEARCH_QUERY = 'neural architecture search efficiency'
const EDITOR_PROMPT = 'Enhance the intro with recent NAS trends'
const AI_REPLY = "Here's a tighter intro emphasising efficiency and hardware-aware trade-offs:"
const OLD_LINE = 'Recent work on neural architecture search has focused on reducing latency.'
const NEW_LINE_1 = 'Recent work on neural architecture search has explored efficiency,'
const NEW_LINE_2 = 'accuracy, and hardware-aware trade-offs across edge and datacenter deployments.'

const SOURCES = [
  'Semantic Scholar',
  'OpenAlex',
  'arXiv',
  'Crossref',
  'PubMed',
  'CORE',
  'Europe PMC',
  'ScienceDirect',
  'Google Scholar',
]

const PAPERS = [
  {
    title: 'EfficientNet: Rethinking Model Scaling for CNNs',
    authors: 'Tan, Le',
    year: '2019',
    source: 'Semantic Scholar',
  },
  {
    title: 'Neural Architecture Search: A Survey',
    authors: 'Elsken, Metzen, Hutter',
    year: '2019',
    source: 'OpenAlex',
  },
  {
    title: 'Once-for-All: Train One Network, Deploy Many',
    authors: 'Cai, Gan, Wang et al.',
    year: '2020',
    source: 'arXiv',
  },
]

interface Props {
  reduced: boolean
  heroAnimationCls: string
}

const useTyping = (target: string, active: boolean, speed = 28) => {
  const [typed, setTyped] = useState('')
  useEffect(() => {
    if (!active) {
      setTyped('')
      return
    }
    setTyped('')
    let i = 0
    const id = window.setInterval(() => {
      i += 1
      setTyped(target.slice(0, i))
      if (i >= target.length) window.clearInterval(id)
    }, speed)
    return () => window.clearInterval(id)
  }, [active, target, speed])
  return typed
}

const HeroAnimatedMockup = ({ reduced, heroAnimationCls }: Props) => {
  const [phase, setPhase] = useState<Phase>(reduced ? 'edit-applied' : 'idle')

  useEffect(() => {
    if (reduced) return
    const timers: number[] = []

    const schedule = () => {
      setPhase('idle')
      const seq: [Phase, number][] = [
        ['d-typing', 400],
        ['d-searching', 2200],
        ['d-results', 3600],
        ['d-adding', 5000],
        ['lib-open', 5600],
        ['lib-settled', 6200],
        ['edit-open', 7400],
        ['edit-prompting', 8000],
        ['edit-sent', 10100],
        ['edit-thinking', 10400],
        ['edit-responding', 11300],
        ['edit-proposing', 12700],
        ['edit-applying', 14100],
        ['edit-applied', 14600],
      ]
      seq.forEach(([p, delay]) => {
        timers.push(window.setTimeout(() => setPhase(p), delay))
      })
      timers.push(window.setTimeout(schedule, 17500))
    }

    timers.push(window.setTimeout(schedule, 400))
    return () => timers.forEach((t) => window.clearTimeout(t))
  }, [reduced])

  const scene = getScene(phase)
  const queryTyped = useTyping(SEARCH_QUERY, phase === 'd-typing', 32)
  const promptTyped = useTyping(EDITOR_PROMPT, phase === 'edit-prompting', 28)
  const replyTyped = useTyping(
    AI_REPLY,
    phase === 'edit-responding' || phase === 'edit-proposing' || phase === 'edit-applying' || phase === 'edit-applied',
    18,
  )

  // discovery scene flags
  const dSearching = phase === 'd-searching'
  const dResults = phase === 'd-results' || phase === 'd-adding'
  const dAdding = phase === 'd-adding'

  // editor scene flags
  const editUserVisible = ['edit-sent','edit-thinking','edit-responding','edit-proposing','edit-applying','edit-applied'].includes(phase)
  const editThinking = phase === 'edit-thinking'
  const editReplyVisible = ['edit-responding','edit-proposing','edit-applying','edit-applied'].includes(phase)
  const editProposalVisible = ['edit-proposing','edit-applying','edit-applied'].includes(phase)
  const editIsApplying = phase === 'edit-applying'
  const editIsApplied = phase === 'edit-applied'

  const windowTitle =
    scene === 'discover'
      ? 'Discover — ScholarHub'
      : scene === 'library'
      ? 'Library — ScholarHub'
      : 'nas-survey.tex — ScholarHub'

  return (
    <section className="relative px-4 sm:px-6 pt-10 sm:pt-16 pb-16 sm:pb-28">
      <div className="max-w-6xl mx-auto">
        <div className={`grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] gap-10 lg:gap-14 items-center transition-all duration-1000 ease-out ${heroAnimationCls}`}>
          {/* LEFT — copy */}
          <div className="text-center lg:text-left">
            <div className="inline-flex items-center gap-2 rounded-full border border-indigo-200/70 dark:border-indigo-500/30 bg-white/70 dark:bg-slate-900/60 backdrop-blur px-3 py-1 text-xs font-medium text-indigo-700 dark:text-indigo-300">
              <Sparkles className="h-3.5 w-3.5" />
              One workspace for the whole paper
            </div>
            <h1 className="font-serif mt-5 text-3xl sm:text-5xl md:text-6xl font-bold tracking-tight leading-[1.05]">
              <span className="bg-gradient-to-r from-gray-900 via-gray-800 to-gray-900 dark:from-white dark:via-gray-100 dark:to-white bg-clip-text text-transparent">
                One workspace
              </span>
              <br />
              <span className="bg-gradient-to-r from-gray-900 via-gray-800 to-gray-900 dark:from-white dark:via-gray-100 dark:to-white bg-clip-text text-transparent">
                instead of{' '}
              </span>
              <span className="text-indigo-600 dark:text-indigo-400">five.</span>
            </h1>
            <p className="mt-5 text-base sm:text-lg text-gray-600 dark:text-slate-300 max-w-xl mx-auto lg:mx-0 leading-relaxed">
              Discover across 9 academic databases, keep what matters in your library,
              and write in LaTeX with a project-grounded AI assistant that cites only
              papers you've saved.
            </p>
            <div className="mt-7 flex flex-col sm:flex-row items-center lg:items-start lg:justify-start justify-center gap-3">
              <Link
                to="/register"
                className="group relative inline-flex items-center gap-2 px-6 py-3 sm:px-7 sm:py-3.5 text-sm sm:text-base font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-all shadow-xl shadow-indigo-500/25 hover:shadow-2xl hover:shadow-indigo-500/40 hover:-translate-y-0.5"
              >
                Start for free
                <ArrowRight className="h-4 w-4 sm:h-5 sm:w-5 group-hover:translate-x-1 transition-transform" />
              </Link>
              <a
                href="#features"
                className="inline-flex items-center gap-2 px-6 py-3 sm:px-7 sm:py-3.5 text-sm sm:text-base font-medium text-gray-700 dark:text-slate-300 bg-white/80 dark:bg-slate-800/80 backdrop-blur-sm border border-gray-200 dark:border-slate-700 rounded-xl transition-all hover:shadow-lg hover:-translate-y-0.5 hover:border-indigo-300 dark:hover:border-indigo-500/50"
                onClick={(e) => { e.preventDefault(); document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' }) }}
              >
                See what's inside
              </a>
            </div>
            <p className="mt-3 text-xs sm:text-sm text-gray-500 dark:text-slate-500">
              Free for research teams · Your keys, your models
            </p>
          </div>

          {/* RIGHT — mockup window */}
          <div className="relative">
            <div aria-hidden className="pointer-events-none absolute -inset-6 rounded-[36px] bg-gradient-to-tr from-indigo-500/20 via-purple-500/10 to-fuchsia-500/20 blur-2xl" />

            <div className="relative rounded-2xl border border-gray-200 dark:border-slate-700/70 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden">
              {/* Window chrome */}
              <div className="flex items-center gap-2 px-4 py-2.5 border-b border-gray-200 dark:border-slate-700/70 bg-gray-50 dark:bg-slate-800/70">
                <div className="flex gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
                  <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
                </div>
                <div className="flex-1 text-center text-[11px] font-medium text-gray-500 dark:text-slate-400 transition-opacity duration-300">
                  {windowTitle}
                </div>
                <div className="inline-flex items-center gap-1 text-[10px] text-gray-500 dark:text-slate-400">
                  <Users className="h-3 w-3" /> 2
                </div>
              </div>

              {/* Tab strip — shows current product surface */}
              <div className="flex items-center gap-1 px-3 py-1.5 border-b border-gray-200 dark:border-slate-700/70 bg-slate-50 dark:bg-slate-900/60 text-[11px]">
                <SceneTab icon={<Search className="h-3 w-3" />} label="Discover" active={scene === 'discover'} />
                <SceneTab icon={<BookmarkPlus className="h-3 w-3" />} label="Library" active={scene === 'library'} />
                <SceneTab icon={<FileText className="h-3 w-3" />} label="Editor" active={scene === 'editor'} />
              </div>

              {/* Body — swaps per scene */}
              <div className="relative h-[400px] sm:h-[460px] bg-slate-950 overflow-hidden">
                {/* Scene 1: DISCOVER */}
                {scene === 'discover' && (
                  <div key="discover" className="absolute inset-0 p-4 flex flex-col gap-3 scene-enter">
                    {/* Search bar */}
                    <div className="flex items-center gap-2 rounded-md bg-slate-800/60 border border-slate-700/60 px-3 py-2">
                      <Search className="h-3.5 w-3.5 text-slate-400" />
                      <span className="flex-1 text-[12px] text-slate-200 truncate">
                        {phase === 'idle' ? (
                          <span className="text-slate-500">Search 9 academic databases…</span>
                        ) : (
                          <>
                            {queryTyped || SEARCH_QUERY}
                            {phase === 'd-typing' && (
                              <span className="inline-block w-[4px] h-[10px] translate-y-[1px] bg-indigo-400 animate-pulse ml-0.5" />
                            )}
                          </>
                        )}
                      </span>
                      <span className="text-[10px] text-slate-500">⌘K</span>
                    </div>

                    {/* Source chips */}
                    <div className="flex flex-wrap gap-1.5">
                      {SOURCES.map((src, i) => (
                        <SourceChip
                          key={src}
                          label={src}
                          state={dResults ? 'done' : dSearching ? 'searching' : 'idle'}
                          delay={i * 130}
                        />
                      ))}
                    </div>

                    {/* Results or empty */}
                    <div className="flex-1 flex flex-col gap-2 overflow-hidden">
                      {dResults ? (
                        PAPERS.map((p, i) => (
                          <div
                            key={p.title}
                            className="rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 flex items-start gap-2 paper-enter"
                            style={{ animationDelay: `${i * 140}ms` }}
                          >
                            <div className="flex-1 min-w-0">
                              <div className="text-[12px] font-semibold text-slate-100 truncate">{p.title}</div>
                              <div className="text-[10.5px] text-slate-400 truncate">
                                {p.authors} · {p.year}
                              </div>
                            </div>
                            <span className="shrink-0 text-[9.5px] font-medium text-indigo-300 bg-indigo-500/15 border border-indigo-400/30 rounded px-1.5 py-0.5">
                              {p.source}
                            </span>
                            <span
                              className={`shrink-0 inline-flex items-center justify-center h-5 w-5 rounded transition-all ${
                                dAdding ? 'bg-emerald-500 text-white' : 'bg-slate-800 text-slate-400'
                              }`}
                              title="Add to library"
                            >
                              {dAdding ? <Check className="h-3 w-3" /> : <BookmarkPlus className="h-3 w-3" />}
                            </span>
                          </div>
                        ))
                      ) : dSearching ? (
                        <div className="flex-1 flex items-center justify-center text-[11.5px] text-slate-400">
                          <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin text-indigo-400" />
                          Searching 9 sources, deduping across them…
                        </div>
                      ) : (
                        <div className="flex-1 flex items-center justify-center text-[11.5px] text-slate-600">
                          Ask a question. Search 9 databases at once.
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Scene 2: LIBRARY */}
                {scene === 'library' && (
                  <div key="library" className="absolute inset-0 p-4 flex flex-col gap-3 scene-enter">
                    <div className="flex items-center justify-between">
                      <div className="text-[12px] font-semibold text-slate-200">Your library</div>
                      <div className="text-[10.5px] text-emerald-400 inline-flex items-center gap-1 paper-enter">
                        <Check className="h-3 w-3" /> 3 added to project
                      </div>
                    </div>
                    <div className="flex-1 flex flex-col gap-2">
                      {PAPERS.map((p, i) => (
                        <div
                          key={p.title}
                          className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 paper-enter"
                          style={{ animationDelay: `${i * 110}ms` }}
                        >
                          <div className="flex items-start gap-2">
                            <div className="flex-1 min-w-0">
                              <div className="text-[12px] font-semibold text-slate-100 truncate">{p.title}</div>
                              <div className="text-[10.5px] text-slate-400 truncate">
                                {p.authors} · {p.year} · <span className="text-indigo-300">{p.source}</span>
                              </div>
                            </div>
                            <span className="shrink-0 text-[9.5px] font-mono text-slate-400 bg-slate-800/70 border border-slate-700/70 rounded px-1.5 py-0.5">
                              {p.authors.split(',')[0].toLowerCase()}{p.year}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="text-[10.5px] text-slate-500 text-center">
                      Ready to cite. Open the editor to start writing.
                    </div>
                  </div>
                )}

                {/* Scene 3: EDITOR + AI */}
                {scene === 'editor' && (
                  <div key="editor" className="absolute inset-0 grid grid-cols-[1.05fr_1fr] scene-enter">
                    {/* Editor */}
                    <div className="relative min-w-0 border-r border-slate-800">
                      <div className="flex items-center gap-1 px-3 py-1.5 border-b border-slate-800 bg-slate-900/80 text-[11px]">
                        <span className="rounded-md bg-slate-800 text-slate-200 px-2 py-0.5">main.tex</span>
                        <span className="text-slate-500 px-2 py-0.5">refs.bib</span>
                      </div>
                      <div className="flex font-mono text-[11.5px] sm:text-[12px] leading-[1.75]">
                        <div className="text-right select-none text-slate-600 px-2 pt-3 pb-3 w-8">
                          {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
                            <div key={n}>{n}</div>
                          ))}
                        </div>
                        <pre className="flex-1 text-slate-200 px-2 pt-3 pb-3 whitespace-pre-wrap">
<span className="text-slate-500">% NAS survey draft</span>{'\n'}
<span className="text-indigo-300">\section</span>{'{Introduction}'}{'\n'}
{'\n'}
<span className="text-slate-500">% TODO: sharpen</span>{'\n'}
                          {editIsApplied ? (
                            <>
                              <span className="block rounded-sm bg-emerald-500/15 ring-1 ring-emerald-400/40 px-0.5 transition-colors duration-300">
                                {NEW_LINE_1}
                              </span>
                              <span className="block rounded-sm bg-emerald-500/15 ring-1 ring-emerald-400/40 px-0.5">
                                {NEW_LINE_2}
                              </span>
                            </>
                          ) : (
                            <span className={`block transition-colors duration-200 ${editIsApplying ? 'bg-rose-500/10' : ''}`}>
                              {OLD_LINE}
                            </span>
                          )}
                          {'\n'}
<span className="text-slate-500">% refs</span>{'\n'}
<span className="text-indigo-300">\cite</span>{'{tan2019,elsken2019,cai2020}'}{'\n'}
                        </pre>
                      </div>
                    </div>

                    {/* AI Assistant panel */}
                    <div className="relative flex flex-col min-w-0 bg-slate-950">
                      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-slate-800 bg-slate-900/80">
                        <span className="inline-flex items-center justify-center h-5 w-5 rounded-md bg-gradient-to-br from-indigo-500 to-purple-500">
                          <Sparkles className="h-3 w-3 text-white" />
                        </span>
                        <span className="text-[11px] font-semibold text-slate-200">AI Assistant</span>
                        <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-slate-400">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> connected
                        </span>
                      </div>

                      <div className="flex-1 overflow-hidden px-3 py-3 space-y-2.5">
                        <div
                          className={`flex justify-end transition-all duration-300 ${
                            editUserVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'
                          }`}
                        >
                          <div className="max-w-[85%] rounded-lg rounded-br-sm bg-indigo-600 text-white px-2.5 py-1.5 text-[11.5px] leading-snug shadow">
                            {editUserVisible ? EDITOR_PROMPT : ''}
                          </div>
                        </div>

                        {editThinking && (
                          <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
                            <Loader2 className="h-3 w-3 animate-spin text-indigo-400" />
                            Reading main.tex · checking library
                          </div>
                        )}

                        {editReplyVisible && (
                          <div className="flex justify-start">
                            <div className="max-w-[92%] rounded-lg rounded-bl-sm bg-slate-800/70 text-slate-200 px-2.5 py-1.5 text-[11.5px] leading-snug border border-slate-700/60">
                              {replyTyped}
                              {replyTyped.length < AI_REPLY.length && (
                                <span className="inline-block w-[5px] h-[10px] translate-y-[1px] bg-slate-400 animate-pulse ml-0.5" />
                              )}
                            </div>
                          </div>
                        )}

                        {editProposalVisible && (
                          <div
                            className={`rounded-lg border transition-all duration-300 ${
                              editIsApplied
                                ? 'border-emerald-500/40 bg-emerald-500/5'
                                : 'border-indigo-400/40 bg-slate-900/60'
                            }`}
                            style={{ animation: 'edit-in 400ms ease-out both' }}
                          >
                            <div className="flex items-center justify-between px-2.5 py-1.5 border-b border-slate-800">
                              <div className="flex items-center gap-1.5 text-[10.5px] text-slate-300">
                                <span className="inline-flex items-center justify-center h-4 w-4 rounded bg-indigo-500/20 text-indigo-300 font-bold">1</span>
                                <span className="font-semibold">main.tex</span>
                                <span className="text-slate-500">· L5</span>
                              </div>
                              <span className="text-[9.5px] uppercase tracking-wide text-slate-500">
                                {editIsApplied ? 'applied' : 'proposed'}
                              </span>
                            </div>
                            <div className="px-2.5 py-1.5 font-mono text-[10.5px] leading-[1.5] space-y-0.5">
                              <div className="flex gap-1.5 items-start rounded bg-rose-500/10 text-rose-200 px-1 py-0.5">
                                <span className="text-rose-400 font-bold">−</span>
                                <span className="truncate">{OLD_LINE}</span>
                              </div>
                              <div className="flex gap-1.5 items-start rounded bg-emerald-500/10 text-emerald-200 px-1 py-0.5">
                                <span className="text-emerald-400 font-bold">+</span>
                                <span className="leading-[1.45]">
                                  {NEW_LINE_1} {NEW_LINE_2}
                                </span>
                              </div>
                            </div>
                            <div className="flex items-center gap-1.5 px-2.5 py-1.5 border-t border-slate-800">
                              <button
                                className={`inline-flex items-center gap-1 text-[10.5px] font-semibold rounded px-2 py-1 transition-all ${
                                  editIsApplied
                                    ? 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-400/40'
                                    : editIsApplying
                                    ? 'bg-emerald-500 text-white scale-[1.03]'
                                    : 'bg-indigo-600 text-white'
                                }`}
                              >
                                <Check className="h-3 w-3" />
                                {editIsApplied ? 'Applied' : 'Apply'}
                              </button>
                              {!editIsApplied && (
                                <button className="text-[10.5px] text-slate-400 rounded px-2 py-1">
                                  Reject
                                </button>
                              )}
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="border-t border-slate-800 bg-slate-900/80 px-3 py-2">
                        <div className="flex items-center gap-2 rounded-md bg-slate-800/70 border border-slate-700/60 px-2 py-1.5">
                          <span className="text-[11px] text-slate-300 flex-1 truncate">
                            {phase === 'edit-prompting' ? (
                              <>
                                {promptTyped}
                                <span className="inline-block w-[4px] h-[10px] translate-y-[1px] bg-indigo-400 animate-pulse ml-0.5" />
                              </>
                            ) : (
                              <span className="text-slate-500">Ask questions, request feedback, or ask for changes…</span>
                            )}
                          </span>
                          <span
                            className={`inline-flex items-center justify-center h-5 w-5 rounded transition-all ${
                              phase === 'edit-prompting' || phase === 'edit-sent'
                                ? 'bg-indigo-600 text-white'
                                : 'bg-slate-700 text-slate-400'
                            }`}
                          >
                            <Send className="h-3 w-3" />
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Status bar */}
              <div className="flex items-center justify-between px-4 py-1.5 border-t border-slate-800 bg-slate-900 text-[10px] text-slate-400">
                <div className="flex items-center gap-3">
                  <span className="inline-flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    {scene === 'discover' ? 'live · 9 sources' : scene === 'library' ? 'live · synced to Zotero' : 'live · 2 collaborators'}
                  </span>
                  <span>UTF-8</span>
                </div>
                <span>
                  {scene === 'editor' ? 'main.tex · Tectonic' : scene === 'library' ? 'project · nas-survey' : 'deduped · cross-source'}
                </span>
              </div>
            </div>

            <div className="mt-5 flex flex-wrap justify-center lg:justify-start gap-2 text-[11px] text-gray-600 dark:text-slate-400">
              <span className="rounded-full bg-white/70 dark:bg-slate-800/70 border border-gray-200 dark:border-slate-700 px-2.5 py-1">9 paper sources</span>
              <span className="rounded-full bg-white/70 dark:bg-slate-800/70 border border-gray-200 dark:border-slate-700 px-2.5 py-1">Project-grounded AI</span>
              <span className="rounded-full bg-white/70 dark:bg-slate-800/70 border border-gray-200 dark:border-slate-700 px-2.5 py-1">LaTeX + live PDF</span>
              <span className="rounded-full bg-white/70 dark:bg-slate-800/70 border border-gray-200 dark:border-slate-700 px-2.5 py-1">Real-time Y.js collab</span>
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes edit-in {
          0% { opacity: 0; transform: translateY(6px) scale(0.98); }
          100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes scene-in {
          0% { opacity: 0; transform: translateY(6px); }
          100% { opacity: 1; transform: translateY(0); }
        }
        .scene-enter { animation: scene-in 320ms ease-out both; }
        @keyframes paper-in {
          0% { opacity: 0; transform: translateY(4px); }
          100% { opacity: 1; transform: translateY(0); }
        }
        .paper-enter { animation: paper-in 280ms ease-out both; }
        @keyframes source-in {
          0% { opacity: 0; transform: scale(0.92); }
          100% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </section>
  )
}

const SceneTab = ({ icon, label, active }: { icon: React.ReactNode; label: string; active: boolean }) => (
  <div
    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-colors ${
      active
        ? 'bg-indigo-500/15 text-indigo-300 ring-1 ring-indigo-400/30'
        : 'text-slate-500'
    }`}
  >
    {icon}
    <span className="font-medium">{label}</span>
  </div>
)

const SourceChip = ({
  label,
  state,
  delay,
}: {
  label: string
  state: 'idle' | 'searching' | 'done'
  delay: number
}) => {
  const [visible, setVisible] = useState(state !== 'idle')
  useEffect(() => {
    if (state === 'idle') {
      setVisible(false)
      return
    }
    const id = window.setTimeout(() => setVisible(true), delay)
    return () => window.clearTimeout(id)
  }, [state, delay])

  const cls =
    state === 'done'
      ? 'border-emerald-400/40 bg-emerald-500/10 text-emerald-300'
      : state === 'searching' && visible
      ? 'border-indigo-400/40 bg-indigo-500/10 text-indigo-200'
      : 'border-slate-700/60 bg-slate-800/40 text-slate-500'

  return (
    <span
      className={`inline-flex items-center gap-1 text-[10px] font-medium rounded-full border px-2 py-0.5 transition-all ${cls}`}
      style={{ animation: visible ? `source-in 240ms ease-out both` : undefined }}
    >
      {state === 'done' ? (
        <Check className="h-2.5 w-2.5" />
      ) : state === 'searching' && visible ? (
        <Loader2 className="h-2.5 w-2.5 animate-spin" />
      ) : (
        <span className="h-1.5 w-1.5 rounded-full bg-current opacity-50" />
      )}
      {label}
    </span>
  )
}

export default HeroAnimatedMockup
