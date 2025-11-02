// Minimal UI store for view mode persistence via localStorage

export type ViewMode = 'editor' | 'split' | 'preview'

const VIEW_MODE_KEY = 'latex.view.mode'

function readViewMode(): ViewMode {
  try {
    const stored = localStorage.getItem(VIEW_MODE_KEY) as ViewMode | null
    return (stored === 'editor' || stored === 'split' || stored === 'preview') ? stored : 'editor'
  } catch { return 'editor' }
}

function writeViewMode(mode: ViewMode) {
  try { localStorage.setItem(VIEW_MODE_KEY, mode) } catch {}
}

let viewMode: ViewMode = readViewMode()

type Listener = () => void
const listeners = new Set<Listener>()

function notify() {
  listeners.forEach((l) => { try { l() } catch {} })
}

export const uiStore = {
  getViewMode(): ViewMode { return viewMode },
  setViewMode(mode: ViewMode) { viewMode = mode; writeViewMode(mode); notify() },
  subscribe(fn: Listener) { listeners.add(fn); return () => listeners.delete(fn) },
}

