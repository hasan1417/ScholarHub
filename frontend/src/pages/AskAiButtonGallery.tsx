import { Sparkles } from 'lucide-react'

/**
 * Gallery of animated "Ask AI" button variants. Each variant is a standalone
 * implementation (no prop-driven conditional) so picking one is a copy-paste
 * job: lift the JSX + the relevant <style> rule into DocumentShell.tsx.
 *
 * Route: /ask-ai-gallery (see routes/index.tsx)
 */

type VariantProps = {
  id: string
  name: string
  description: string
  rationale: string
  button: React.ReactNode
}

const Wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="relative flex h-48 w-full items-center justify-center overflow-hidden rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
    {children}
  </div>
)

const AskAiButtonGallery = () => {
  const variants: VariantProps[] = [
    {
      id: 'v1-current',
      name: '1 · Current (baseline)',
      description: 'Static indigo→purple gradient pill with sparkle icon. No animation.',
      rationale: 'What we ship today. Reference point for comparison.',
      button: (
        <button className="inline-flex items-center gap-2 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 py-2.5 pl-3 pr-4 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-indigo-500/40">
          <Sparkles className="h-4 w-4" />
          <span>Ask AI</span>
        </button>
      ),
    },
    {
      id: 'v2-breathe',
      name: '2 · Breathe',
      description: 'Slow scale pulse (0.96 → 1.04) on loop. Calm, steady.',
      rationale: 'Draws attention without screaming. Good for always-available affordance.',
      button: (
        <button className="inline-flex animate-[breathe_3s_ease-in-out_infinite] items-center gap-2 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 py-2.5 pl-3 pr-4 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30">
          <Sparkles className="h-4 w-4" />
          <span>Ask AI</span>
        </button>
      ),
    },
    {
      id: 'v3-sparkle-spin',
      name: '3 · Sparkle Twinkle',
      description: 'Button is static. Only the sparkle icon rotates and scales periodically.',
      rationale: 'Focuses animation on the icon so it feels playful without distracting.',
      button: (
        <button className="group inline-flex items-center gap-2 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 py-2.5 pl-3 pr-4 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 hover:shadow-xl hover:shadow-indigo-500/40">
          <Sparkles className="h-4 w-4 animate-[twinkle_2.4s_ease-in-out_infinite]" />
          <span>Ask AI</span>
        </button>
      ),
    },
    {
      id: 'v4-shimmer',
      name: '4 · Shimmer Sweep',
      description: 'A soft light band sweeps across the button every 3s.',
      rationale: 'Premium feel — reads as "active" without bouncing. Similar to skeleton loaders but for a CTA.',
      button: (
        <button className="group relative inline-flex items-center gap-2 overflow-hidden rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 py-2.5 pl-3 pr-4 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30">
          <span className="pointer-events-none absolute inset-0 -translate-x-full animate-[shimmer_3s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-white/35 to-transparent" />
          <Sparkles className="relative h-4 w-4" />
          <span className="relative">Ask AI</span>
        </button>
      ),
    },
    {
      id: 'v5-halo',
      name: '5 · Halo Pulse',
      description: 'Concentric rings radiate outward every 2s. Button itself stays still.',
      rationale: 'Signals "available" and invites click. Bigger visual footprint — may compete with editor content.',
      button: (
        <span className="relative inline-flex">
          <span className="pointer-events-none absolute inset-0 animate-[halo_2s_ease-out_infinite] rounded-full bg-indigo-400/60" />
          <span className="pointer-events-none absolute inset-0 animate-[halo_2s_ease-out_infinite_0.6s] rounded-full bg-purple-400/40" />
          <button className="relative inline-flex items-center gap-2 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 py-2.5 pl-3 pr-4 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30">
            <Sparkles className="h-4 w-4" />
            <span>Ask AI</span>
          </button>
        </span>
      ),
    },
    {
      id: 'v6-aurora',
      name: '6 · Aurora',
      description: 'Multi-color conic gradient slowly rotates around the button border.',
      rationale: 'AI-coded visual language (rainbow gradient = GPT-ish). Trendy. May look busy.',
      button: (
        <button className="relative inline-flex items-center gap-2 rounded-full py-[3px] pl-[3px] pr-[3px] text-sm font-semibold text-white">
          <span className="pointer-events-none absolute inset-0 animate-[aurora_4s_linear_infinite] rounded-full [background:conic-gradient(from_var(--tw-rotate,0deg),#6366f1,#a855f7,#ec4899,#6366f1)]" />
          <span className="relative inline-flex items-center gap-2 rounded-full bg-slate-900 py-[9px] pl-[9px] pr-[13px] shadow-lg shadow-indigo-500/30">
            <Sparkles className="h-4 w-4" />
            <span>Ask AI</span>
          </span>
        </button>
      ),
    },
    {
      id: 'v7-thinking',
      name: '7 · Typing Dots',
      description: 'Three dots animate beside the label, as if the AI is "typing".',
      rationale: 'Conveys an agent that\'s "on" and ready. Works well for idle state.',
      button: (
        <button className="inline-flex items-center gap-2 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 py-2.5 pl-3 pr-4 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30">
          <Sparkles className="h-4 w-4" />
          <span>Ask AI</span>
          <span className="ml-0.5 inline-flex items-center gap-0.5">
            <span className="inline-block h-1 w-1 animate-[typing_1.4s_ease-in-out_infinite] rounded-full bg-white/90" />
            <span className="inline-block h-1 w-1 animate-[typing_1.4s_ease-in-out_infinite_0.2s] rounded-full bg-white/90" />
            <span className="inline-block h-1 w-1 animate-[typing_1.4s_ease-in-out_infinite_0.4s] rounded-full bg-white/90" />
          </span>
        </button>
      ),
    },
    {
      id: 'v8-magnetic',
      name: '8 · Magnetic Lift',
      description: 'On hover only: button lifts 4px, shadow intensifies, sparkle rotates 12°. No idle animation.',
      rationale: 'Most restrained. Best if you want the AI button to feel premium but not demand attention.',
      button: (
        <button className="group inline-flex items-center gap-2 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 py-2.5 pl-3 pr-4 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl hover:shadow-indigo-500/50">
          <Sparkles className="h-4 w-4 transition-transform duration-300 group-hover:rotate-12 group-hover:scale-110" />
          <span>Ask AI</span>
        </button>
      ),
    },
  ]

  return (
    <div className="min-h-screen bg-white px-6 py-10 dark:bg-slate-900">
      <style>{`
        @keyframes breathe {
          0%, 100% { transform: scale(0.96); box-shadow: 0 10px 20px -10px rgba(99,102,241,0.35); }
          50%      { transform: scale(1.04); box-shadow: 0 14px 28px -8px rgba(99,102,241,0.55); }
        }
        @keyframes twinkle {
          0%, 100% { transform: rotate(0deg) scale(1); opacity: 1; }
          50%      { transform: rotate(180deg) scale(1.3); opacity: 0.85; }
        }
        @keyframes shimmer {
          0%   { transform: translateX(-100%); }
          60%  { transform: translateX(200%); }
          100% { transform: translateX(200%); }
        }
        @keyframes halo {
          0%   { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(1.5); opacity: 0; }
        }
        @keyframes aurora {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes typing {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.35; }
          30%           { transform: translateY(-3px); opacity: 1; }
        }
      `}</style>

      <div className="mx-auto max-w-5xl">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            Ask AI — button animation variants
          </h1>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            Eight variants, from calmest to flashiest. Pick one; I'll wire it into the LaTeX editor.
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
            Tip: reduce motion preference should likely suppress the loop animations (variants 2–7). Variant 8 is already motion-safe.
          </p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          {variants.map((v) => (
            <div key={v.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800">
              <div className="mb-3 flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{v.name}</h2>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{v.description}</p>
                </div>
              </div>
              <Wrapper>{v.button}</Wrapper>
              <p className="mt-3 text-[11px] leading-relaxed text-slate-600 dark:text-slate-300">
                <span className="font-semibold text-slate-700 dark:text-slate-200">Why:</span> {v.rationale}
              </p>
            </div>
          ))}
        </div>

        <div className="mt-10 rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-900 dark:border-indigo-500/40 dark:bg-indigo-900/20 dark:text-indigo-100">
          <div className="font-semibold">My recommendation</div>
          <p className="mt-1 text-[13px] leading-relaxed">
            <strong>Variant 8 (Magnetic Lift)</strong> for production — hover-only motion respects <code className="rounded bg-indigo-100 px-1 dark:bg-indigo-900/50">prefers-reduced-motion</code> by default and won't distract users who are focused on writing.
          </p>
          <p className="mt-1 text-[13px] leading-relaxed">
            If you want a subtle always-on ambient signal: <strong>Variant 4 (Shimmer Sweep)</strong> — premium without being loud. Avoid <strong>Variant 5 (Halo)</strong> and <strong>Variant 6 (Aurora)</strong> on the editor page; they compete visually with the editor content.
          </p>
        </div>
      </div>
    </div>
  )
}

export default AskAiButtonGallery
