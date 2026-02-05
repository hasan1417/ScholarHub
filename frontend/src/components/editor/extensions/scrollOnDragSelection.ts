import { ViewPlugin, EditorView } from '@codemirror/view'

/**
 * Extension that enables auto-scroll when dragging selection to edge of editor.
 * Scrolls the editor when mouse is near top or bottom edge during selection.
 * Uses pointer events with capture for reliable drag tracking.
 */
export const scrollOnDragSelection = ViewPlugin.fromClass(class {
  private scrollInterval: number | null = null
  private lastMouseY = 0
  private edgeThreshold = 50 // pixels from edge to trigger scroll
  private scrollSpeed = 12 // pixels per frame
  private scrollContainer: HTMLElement | null = null

  constructor(private view: EditorView) {
    this.onPointerDown = this.onPointerDown.bind(this)
    this.onPointerMove = this.onPointerMove.bind(this)
    this.onPointerUp = this.onPointerUp.bind(this)

    view.dom.addEventListener('pointerdown', this.onPointerDown)
  }

  // Find the actual scrollable parent (where scrollHeight > clientHeight)
  findScrollableContainer(): HTMLElement {
    let el: HTMLElement | null = this.view.dom
    while (el) {
      if (el.scrollHeight > el.clientHeight + 10) {
        const style = window.getComputedStyle(el)
        if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
          return el
        }
      }
      el = el.parentElement
    }
    return this.view.scrollDOM
  }

  onPointerDown(e: PointerEvent) {
    if (e.button !== 0) return

    // Find scrollable container on first use (lazy init)
    if (!this.scrollContainer) {
      this.scrollContainer = this.findScrollableContainer()
    }

    try {
      (e.target as HTMLElement).setPointerCapture(e.pointerId)
    } catch {}

    document.addEventListener('pointermove', this.onPointerMove)
    document.addEventListener('pointerup', this.onPointerUp)
  }

  onPointerMove(e: PointerEvent) {
    if (e.buttons !== 1 || !this.scrollContainer) {
      this.stopScrolling()
      return
    }

    this.lastMouseY = e.clientY
    const rect = this.scrollContainer.getBoundingClientRect()
    const mouseY = e.clientY

    const nearTop = mouseY < rect.top + this.edgeThreshold
    const nearBottom = mouseY > rect.bottom - this.edgeThreshold

    if (nearTop || nearBottom) {
      if (!this.scrollInterval) {
        const container = this.scrollContainer
        this.scrollInterval = window.setInterval(() => {
          const currentRect = container.getBoundingClientRect()
          const currentY = this.lastMouseY

          if (currentY < currentRect.top + this.edgeThreshold) {
            const distance = Math.max(0, currentRect.top + this.edgeThreshold - currentY)
            const speed = Math.min(this.scrollSpeed + Math.floor(distance / 10), 30)
            container.scrollTop -= speed
          } else if (currentY > currentRect.bottom - this.edgeThreshold) {
            const distance = Math.max(0, currentY - (currentRect.bottom - this.edgeThreshold))
            const speed = Math.min(this.scrollSpeed + Math.floor(distance / 10), 30)
            container.scrollTop += speed
          } else {
            this.stopScrolling()
          }
        }, 16)
      }
    } else {
      this.stopScrolling()
    }
  }

  onPointerUp(e: PointerEvent) {
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId)
    } catch {}
    this.stopScrolling()
    document.removeEventListener('pointermove', this.onPointerMove)
    document.removeEventListener('pointerup', this.onPointerUp)
  }

  stopScrolling() {
    if (this.scrollInterval) {
      clearInterval(this.scrollInterval)
      this.scrollInterval = null
    }
  }

  destroy() {
    this.stopScrolling()
    this.view.dom.removeEventListener('pointerdown', this.onPointerDown)
    document.removeEventListener('pointermove', this.onPointerMove)
    document.removeEventListener('pointerup', this.onPointerUp)
  }
})
