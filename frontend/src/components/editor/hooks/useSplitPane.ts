import { useRef, useState, useEffect, useCallback } from 'react'

interface UseSplitPaneReturn {
  splitPosition: number
  splitContainerRef: React.RefObject<HTMLDivElement>
  isDragging: boolean
  handleSplitDragStart: (e: React.MouseEvent) => void
}

export function useSplitPane(): UseSplitPaneReturn {
  const [splitPosition, setSplitPosition] = useState(() => {
    const saved = localStorage.getItem('latex-editor-split-position')
    return saved ? parseFloat(saved) : 50
  })
  const splitContainerRef = useRef<HTMLDivElement | null>(null)
  const isDraggingRef = useRef(false)

  // Keep a ref in sync so the mouseup handler can read the latest value
  const splitPositionRef = useRef(splitPosition)
  useEffect(() => {
    splitPositionRef.current = splitPosition
  }, [splitPosition])

  const handleSplitDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    isDraggingRef.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    // Add overlay to prevent iframe from capturing mouse events
    const overlay = document.createElement('div')
    overlay.id = 'split-drag-overlay'
    overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;cursor:col-resize;'
    document.body.appendChild(overlay)

    const handleMouseMove = (moveEvent: MouseEvent) => {
      // Check if mouse button is still pressed
      if (moveEvent.buttons === 0) {
        handleMouseUp()
        return
      }
      if (!splitContainerRef.current) return
      const rect = splitContainerRef.current.getBoundingClientRect()
      const newPosition = ((moveEvent.clientX - rect.left) / rect.width) * 100
      // Clamp between 20% and 80%
      const clamped = Math.min(80, Math.max(20, newPosition))
      setSplitPosition(clamped)
    }

    const handleMouseUp = () => {
      isDraggingRef.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      // Remove overlay
      const existingOverlay = document.getElementById('split-drag-overlay')
      if (existingOverlay) existingOverlay.remove()
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      // Save current position from ref
      localStorage.setItem('latex-editor-split-position', String(splitPositionRef.current))
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [])

  return {
    splitPosition,
    splitContainerRef,
    isDragging: isDraggingRef.current,
    handleSplitDragStart,
  }
}
