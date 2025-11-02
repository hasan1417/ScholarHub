export interface ExportPdfOptions {
  title?: string
  fontCssUrls?: string[]
  marginCm?: number
  extraCss?: string
}

/**
 * Export editor content (inner HTML) to a content-only A4 PDF using the system print dialog.
 * - Applies the SAME computed font-family, font-size, and line-height as the on-screen editor.
 * - Targets bare elements (body, p, h1–h6) so it works without a .ProseMirror wrapper.
 * - Forces p { margin: 0 } and uses .page-break { break-after: page }.
 */
export async function exportContentAsPdf(pmElement: HTMLElement | null, opts: ExportPdfOptions = {}) {
  if (!pmElement) return
  const title = opts.title || 'Export'
  const margin = typeof opts.marginCm === 'number' ? opts.marginCm : 2.54

  // Read computed typography from the live editor for parity
  const cs = getComputedStyle(pmElement)
  const fontFamily = cs.fontFamily || `'Times New Roman', Times, serif`
  const fontSize = cs.fontSize || '12pt'
  const lineHeight = (cs.lineHeight && cs.lineHeight !== 'normal') ? cs.lineHeight : '1.4'

  const html = pmElement.innerHTML || ''
  const win = window.open('', '_blank')
  if (!win) return
  const doc = win.document

  // Build print CSS that targets bare elements (no .ProseMirror dependency)
  const baseCss = `@page { size: A4; margin: ${margin}cm; }
    html, body { background: #fff; color: #000; }
    body { -webkit-print-color-adjust: exact; print-color-adjust: exact; font-family: ${fontFamily}; font-size: ${fontSize}; line-height: ${lineHeight}; }
    p { margin: 0; }
    /* Hard page breaks without layout height */
    .page-break { break-after: page; page-break-after: always; height: 0; margin: 0; padding: 0; border: 0; }
    .page-break::before, .page-break::after { display: none !important; }
    /* Reasonable defaults for common blocks */
    h1 { font-size: 1.8em; margin: 0 0 0.6em; }
    h2 { font-size: 1.5em; margin: 1.2em 0 0.5em; }
    h3 { font-size: 1.25em; margin: 1em 0 0.5em; }
    ul, ol { margin: 0 0 0.75em 1.25em; }
    table { border-collapse: collapse; width: 100%; margin: 0 0 1em; }
    th, td { border: 1px solid #ddd; padding: 0.4em 0.6em; }
  `

  const css = `${baseCss}\n${opts.extraCss || ''}`

  // Collect parent page stylesheets to preserve fonts (best-effort)
  const parentLinks = Array.from(document.querySelectorAll('link[rel="stylesheet"]')) as HTMLLinkElement[]
  const linkTags = (opts.fontCssUrls && opts.fontCssUrls.length
    ? opts.fontCssUrls
    : parentLinks.map(l => l.href).filter(Boolean)
  ).map(href => `<link rel="stylesheet" href="${href}">`).join('')

  doc.open()
  doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(title)}</title>${linkTags}<style>${css}</style></head><body>${html}</body></html>`)
  doc.close()

  try {
    // Wait for fonts to be ready before printing for metric parity
    if ((win.document as any).fonts?.ready) {
      await (win.document as any).fonts.ready
    }
  } catch {}

  // Let layout settle, then print
  setTimeout(() => { try { win.focus(); win.print(); } catch {} }, 100)
  // Best effort auto-close after print
  win.addEventListener?.('afterprint', () => { try { win.close() } catch {} }, { once: true } as any)
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c] as string))
}
