import { useEffect, type MutableRefObject } from 'react'
import type { EditorView } from '@codemirror/view'

/**
 * Listens for custom window events dispatched by the sidebar
 * (bibliography, cite, nocite) and inserts LaTeX into the editor.
 */
export function useLatexEventListeners(viewRef: MutableRefObject<EditorView | null>) {
  useEffect(() => {
    const onInsertBib = () => {
      try {
        const v = viewRef.current
        if (!v) return
        const doc = v.state.doc.toString()
        if (/\\bibliography\{/.test(doc)) return
        const insert = ['', '% Bibliography', '\\bibliographystyle{plain}', '\\bibliography{main}', ''].join('\n')
        const endIdx = doc.lastIndexOf('\\end{document}')
        const pos = endIdx >= 0 ? endIdx : v.state.doc.length
        v.dispatch({ changes: { from: pos, to: pos, insert } })
        v.focus()
      } catch {}
    }

    const onInsertNoCite = (e: Event) => {
      try {
        const v = viewRef.current
        if (!v) return
        const ev = e as CustomEvent
        const keys: string[] = Array.isArray(ev.detail?.keys) ? ev.detail.keys : []
        if (!keys.length) return
        const doc = v.state.doc.toString()
        const line = `\\nocite{${Array.from(new Set(keys)).join(',')}}\n`
        const endIdx = doc.lastIndexOf('\\end{document}')
        const pos = endIdx >= 0 ? endIdx : v.state.doc.length
        v.dispatch({ changes: { from: pos, to: pos, insert: '\n' + line } })
        v.focus()
      } catch {}
    }

    const onInsertCite = (e: Event) => {
      try {
        const v = viewRef.current
        if (!v) return
        const ev = e as CustomEvent
        const key = ev.detail?.key
        if (!key) return
        const sel = v.state.selection.main
        const insert = `\\cite{${key}}`
        v.dispatch({ changes: { from: sel.from, to: sel.to, insert } })
        v.focus()
      } catch {}
    }

    window.addEventListener('SH_LATEX_INSERT_BIB', onInsertBib)
    window.addEventListener('SH_LATEX_INSERT_NOCITE', onInsertNoCite as any)
    window.addEventListener('SH_LATEX_INSERT_CITE', onInsertCite as any)
    return () => {
      window.removeEventListener('SH_LATEX_INSERT_BIB', onInsertBib)
      window.removeEventListener('SH_LATEX_INSERT_NOCITE', onInsertNoCite as any)
      window.removeEventListener('SH_LATEX_INSERT_CITE', onInsertCite as any)
    }
  }, [])
}
