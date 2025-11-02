import React, { useEffect, useState, useRef } from 'react'
import { X, ArrowRight, ArrowLeft } from 'lucide-react'

export interface TourStep {
  target: string // CSS selector for element to highlight
  title: string
  content: string
  placement?: 'top' | 'bottom' | 'left' | 'right'
  action?: {
    label: string
    onClick: () => void
  }
}

interface FeatureTourProps {
  steps: TourStep[]
  currentStep: number
  onNext: () => void
  onPrevious: () => void
  onSkip: () => void
  onComplete: () => void
}

const FeatureTour: React.FC<FeatureTourProps> = ({
  steps,
  currentStep,
  onNext,
  onPrevious,
  onSkip,
  onComplete,
}) => {
  const [position, setPosition] = useState({ top: 0, left: 0, width: 0, height: 0 })
  const [tooltipPosition, setTooltipPosition] = useState({ top: 0, left: 0 })
  const tooltipRef = useRef<HTMLDivElement>(null)

  const step = steps[currentStep]
  const isLastStep = currentStep === steps.length - 1
  const isFirstStep = currentStep === 0

  useEffect(() => {
    if (!step) return

    const updatePosition = () => {
      const element = document.querySelector(step.target)
      if (!element) {
        console.warn(`Tour target not found: ${step.target}`)
        return
      }

      const rect = element.getBoundingClientRect()
      setPosition({
        top: rect.top + window.scrollY,
        left: rect.left + window.scrollX,
        width: rect.width,
        height: rect.height,
      })

      // Calculate tooltip position
      const tooltipEl = tooltipRef.current
      if (!tooltipEl) return

      const tooltipRect = tooltipEl.getBoundingClientRect()
      const placement = step.placement || 'bottom'
      let top = 0
      let left = 0

      switch (placement) {
        case 'top':
          top = rect.top + window.scrollY - tooltipRect.height - 16
          left = rect.left + window.scrollX + rect.width / 2 - tooltipRect.width / 2
          break
        case 'bottom':
          top = rect.bottom + window.scrollY + 16
          left = rect.left + window.scrollX + rect.width / 2 - tooltipRect.width / 2
          break
        case 'left':
          top = rect.top + window.scrollY + rect.height / 2 - tooltipRect.height / 2
          left = rect.left + window.scrollX - tooltipRect.width - 16
          break
        case 'right':
          top = rect.top + window.scrollY + rect.height / 2 - tooltipRect.height / 2
          left = rect.right + window.scrollX + 16
          break
      }

      // Keep tooltip within viewport
      const padding = 16
      if (left < padding) left = padding
      if (left + tooltipRect.width > window.innerWidth - padding) {
        left = window.innerWidth - tooltipRect.width - padding
      }
      if (top < padding) top = padding

      setTooltipPosition({ top, left })

      // Scroll element into view
      element.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }

    updatePosition()
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition)

    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition)
    }
  }, [step, currentStep])

  if (!step) return null

  const handleNext = () => {
    if (isLastStep) {
      onComplete()
    } else {
      onNext()
    }
  }

  return (
    <>
      {/* Overlay */}
      <div className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" onClick={onSkip} />

      {/* Highlight box */}
      <div
        className="fixed z-40 pointer-events-none"
        style={{
          top: `${position.top - 4}px`,
          left: `${position.left - 4}px`,
          width: `${position.width + 8}px`,
          height: `${position.height + 8}px`,
        }}
      >
        <div className="w-full h-full rounded-lg ring-4 ring-indigo-500 shadow-2xl bg-white/5 animate-pulse" />
      </div>

      {/* Tooltip */}
      <div
        ref={tooltipRef}
        className="fixed z-50 w-80 rounded-xl bg-white shadow-2xl border border-gray-200"
        style={{
          top: `${tooltipPosition.top}px`,
          left: `${tooltipPosition.left}px`,
        }}
      >
        <div className="p-5">
          {/* Header */}
          <div className="flex items-start justify-between mb-3">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-medium text-indigo-600">
                  Step {currentStep + 1} of {steps.length}
                </span>
              </div>
              <h3 className="text-base font-semibold text-gray-900">{step.title}</h3>
            </div>
            <button
              onClick={onSkip}
              className="text-gray-400 hover:text-gray-600 transition-colors"
              aria-label="Skip tour"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Content */}
          <p className="text-sm text-gray-600 mb-4">{step.content}</p>

          {/* Action button (optional) */}
          {step.action && (
            <button
              onClick={step.action.onClick}
              className="w-full mb-3 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-100 transition-colors"
            >
              {step.action.label}
            </button>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between pt-3 border-t border-gray-100">
            <button
              onClick={onPrevious}
              disabled={isFirstStep}
              className="inline-flex items-center gap-1 text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </button>
            <div className="flex items-center gap-2">
              <button
                onClick={onSkip}
                className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
              >
                Skip tour
              </button>
              <button
                onClick={handleNext}
                className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 transition-colors"
              >
                {isLastStep ? 'Finish' : 'Next'}
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

export default FeatureTour
