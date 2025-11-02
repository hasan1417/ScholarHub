import React, { useState } from 'react'
import { X, FileText, Users, Sparkles, BookOpen, ArrowRight } from 'lucide-react'

interface WelcomeModalProps {
  isOpen: boolean
  onClose: () => void
  onGetStarted: () => void
}

const features = [
  {
    icon: FileText,
    title: 'Write & Collaborate',
    description: 'Create research papers with LaTeX or rich text editor. Real-time collaboration with your team.',
    color: 'indigo',
  },
  {
    icon: BookOpen,
    title: 'Discover Research',
    description: 'AI-powered paper discovery with automated feeds. Find relevant research and build your library.',
    color: 'purple',
  },
  {
    icon: Users,
    title: 'Team Discussions',
    description: 'Organize conversations by channels. Video meetings with automatic transcription and AI summaries.',
    color: 'blue',
  },
]

const WelcomeModal: React.FC<WelcomeModalProps> = ({ isOpen, onClose, onGetStarted }) => {
  const [currentStep, setCurrentStep] = useState(0)

  if (!isOpen) return null

  const isLastStep = currentStep === features.length

  const handleNext = () => {
    if (isLastStep) {
      onGetStarted()
    } else {
      setCurrentStep(prev => prev + 1)
    }
  }

  const handleSkip = () => {
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-2xl rounded-2xl bg-white shadow-2xl overflow-hidden">
        {/* Close button */}
        <button
          onClick={handleSkip}
          className="absolute right-4 top-4 text-gray-400 hover:text-gray-600 transition-colors z-10"
          aria-label="Close welcome modal"
        >
          <X className="h-5 w-5" />
        </button>

        {/* Content */}
        <div className="p-8">
          {currentStep === 0 && (
            // Welcome screen
            <div className="text-center py-8">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 mb-6">
                <Sparkles className="h-8 w-8 text-white" />
              </div>
              <h1 className="text-3xl font-bold text-gray-900 mb-4">
                Welcome to ScholarHub
              </h1>
              <p className="text-lg text-gray-600 mb-8 max-w-md mx-auto">
                Your all-in-one platform for academic research collaboration. Let's show you what you can do.
              </p>
              <button
                onClick={handleNext}
                className="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-6 py-3 text-base font-medium text-white shadow-sm hover:bg-indigo-700 transition-colors"
              >
                Get Started
                <ArrowRight className="h-5 w-5" />
              </button>
              <button
                onClick={handleSkip}
                className="mt-4 block mx-auto text-sm text-gray-500 hover:text-gray-700 transition-colors"
              >
                Skip introduction
              </button>
            </div>
          )}

          {currentStep > 0 && currentStep <= features.length && (
            // Feature screens
            <div className="py-6">
              <div className="mb-8">
                {/* Progress indicator */}
                <div className="flex items-center justify-center gap-2 mb-6">
                  {features.map((_, index) => (
                    <div
                      key={index}
                      className={`h-1.5 rounded-full transition-all ${
                        index < currentStep
                          ? 'w-8 bg-indigo-600'
                          : index === currentStep - 1
                          ? 'w-12 bg-indigo-600'
                          : 'w-8 bg-gray-200'
                      }`}
                    />
                  ))}
                </div>

                {/* Feature content */}
                {currentStep <= features.length && (() => {
                  const feature = features[currentStep - 1]
                  const Icon = feature.icon
                  return (
                    <div className="text-center">
                      <div
                        className={`inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-${feature.color}-100 mb-6`}
                      >
                        <Icon
                          className={`h-8 w-8 text-${feature.color}-600`}
                        />
                      </div>
                      <h2 className="text-2xl font-bold text-gray-900 mb-4">
                        {feature.title}
                      </h2>
                      <p className="text-base text-gray-600 mb-8 max-w-md mx-auto">
                        {feature.description}
                      </p>
                    </div>
                  )
                })()}
              </div>

              {/* Navigation */}
              <div className="flex items-center justify-between">
                <button
                  onClick={() => setCurrentStep(prev => prev - 1)}
                  className="text-sm text-gray-600 hover:text-gray-900 transition-colors font-medium"
                >
                  Back
                </button>
                <div className="flex items-center gap-3">
                  <button
                    onClick={handleSkip}
                    className="text-sm text-gray-600 hover:text-gray-900 transition-colors font-medium"
                  >
                    Skip
                  </button>
                  <button
                    onClick={handleNext}
                    className="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 transition-colors"
                  >
                    {currentStep === features.length ? 'Create Your First Project' : 'Next'}
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default WelcomeModal
