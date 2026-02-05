import { EditorState, StateEffect, StateField } from '@codemirror/state'
import { EditorView, Decoration, DecorationSet, WidgetType } from '@codemirror/view'

export type RemoteSelection = {
  id: string
  from: number
  to: number
  color: string
  name: string
}

export class RemoteCaretWidget extends WidgetType {
  constructor(private readonly color: string, private readonly name: string) {
    super()
  }

  toDOM(): HTMLElement {
    const span = document.createElement('span')
    span.className = 'remote-caret'
    span.setAttribute('data-peer', this.name)
    span.style.position = 'relative'
    span.style.borderLeft = `2px solid ${this.color}`
    span.style.marginLeft = '-1px'
    span.style.pointerEvents = 'none'
    span.style.height = '100%'

    const label = document.createElement('span')
    label.textContent = this.name
    label.style.position = 'absolute'
    label.style.top = '-1.4rem'
    label.style.left = '0'
    label.style.fontSize = '10px'
    label.style.fontWeight = '600'
    label.style.padding = '1px 4px'
    label.style.borderRadius = '3px'
    label.style.background = this.color
    label.style.color = '#ffffff'
    label.style.whiteSpace = 'nowrap'
    label.style.pointerEvents = 'none'
    label.style.boxShadow = '0 1px 2px rgba(15,23,42,0.25)'
    label.style.transform = 'translateY(-2px)'

    const idealContrast = computeIdealTextColor(this.color)
    label.style.color = idealContrast

    span.appendChild(label)
    return span
  }

  ignoreEvent(): boolean {
    return true
  }
}

export const setRemoteSelectionsEffect = StateEffect.define<DecorationSet>()

export const remoteSelectionsField = StateField.define<DecorationSet>({
  create() {
    return Decoration.none
  },
  update(value, tr) {
    for (const effect of tr.effects) {
      if (effect.is(setRemoteSelectionsEffect)) return effect.value
    }
    if (tr.docChanged) return value.map(tr.changes)
    return value
  },
  provide: field => EditorView.decorations.from(field),
})

export const highlightColor = (color: string): string => {
  if (!color) return 'rgba(59, 130, 246, 0.25)'
  if (color.startsWith('#') && color.length === 7) {
    return `${color}33`
  }
  return color
}

export const computeIdealTextColor = (bg: string): string => {
  if (!bg || typeof bg !== 'string') return '#ffffff'
  let hex = bg.replace('#', '')
  if (hex.length === 3) {
    hex = hex.split('').map(ch => ch + ch).join('')
  }
  if (hex.length !== 6) return '#ffffff'
  const r = parseInt(hex.slice(0, 2), 16)
  const g = parseInt(hex.slice(2, 4), 16)
  const b = parseInt(hex.slice(4, 6), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.6 ? '#111827' : '#ffffff'
}

export const createRemoteDecorations = (state: EditorState, selections: RemoteSelection[]): DecorationSet => {
  if (!selections || selections.length === 0) return Decoration.none
  const ranges: any[] = []
  const docLength = state.doc.length

  for (const sel of selections) {
    let from = Math.max(0, Math.min(sel.from, docLength))
    let to = Math.max(0, Math.min(sel.to, docLength))
    if (from > to) {
      const tmp = from
      from = to
      to = tmp
    }

    const color = sel.color || '#3B82F6'
    if (from === to) {
      const caret = Decoration.widget({
        widget: new RemoteCaretWidget(color, sel.name),
        side: 1,
      }).range(from)
      ranges.push(caret)
    } else {
      const mark = Decoration.mark({
        attributes: {
          style: `background-color: ${highlightColor(color)}; border-left: 2px solid ${color}; border-right: 2px solid ${color}; border-radius: 2px;`
        }
      }).range(from, to)
      ranges.push(mark)
      const caret = Decoration.widget({
        widget: new RemoteCaretWidget(color, sel.name),
        side: sel.to >= sel.from ? 1 : -1,
      }).range(sel.to)
      ranges.push(caret)
    }
  }

  return Decoration.set(ranges, true)
}
