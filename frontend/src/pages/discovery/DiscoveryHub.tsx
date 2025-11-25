import React, { useState } from 'react'
import { Search, FileText, TrendingUp } from 'lucide-react'
import PaperDiscovery from '../../components/discovery/PaperDiscovery'
import LiteratureReviewGenerator from '../../components/discovery/LiteratureReviewGenerator'

const DiscoveryHub: React.FC = () => {
  // const [activeTab, setActiveTab] = useState<'discover' | 'review'>('discover')
  const [showDiscovery, setShowDiscovery] = useState(false)
  const [showReviewGenerator, setShowReviewGenerator] = useState(false)

  const features = [
    {
      id: 'discover',
      title: 'Discover Papers',
      description: 'Search multiple academic databases with AI-powered relevance ranking',
      icon: <Search size={24} className="text-blue-600" />,
      features: [
        'Search arXiv, Semantic Scholar, Crossref, PubMed',
        'AI-enhanced query generation',
        'Relevance scoring and ranking',
        'One-click add to library'
      ],
      action: () => setShowDiscovery(true)
    },
    {
      id: 'review',
      title: 'Generate Literature Review',
      description: 'Create comprehensive literature reviews from your papers using AI',
      icon: <FileText size={24} className="text-green-600" />,
      features: [
        'Automated theme identification',
        'Multi-section review generation',
        'Research gap analysis',
        'Editable and downloadable output'
      ],
      action: () => setShowReviewGenerator(true)
    }
  ]

  return (
    <>
    <div className="min-h-screen bg-gray-50 dark:bg-slate-900 dark:text-slate-100">
      {/* Header */}
      <div className="bg-white dark:bg-slate-900 shadow-sm border-b border-gray-200 dark:border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="py-6">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-slate-100 flex items-center">
              <TrendingUp className="mr-3 text-indigo-500" size={32} />
              Discovery Hub
            </h1>
            <p className="mt-2 text-gray-600 dark:text-slate-300">
              AI-powered paper discovery and automated literature review generation
            </p>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {!showDiscovery && !showReviewGenerator ? (
          /* Feature Overview */
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {features.map(feature => (
              <div key={feature.id} className="bg-white dark:bg-slate-900 rounded-lg shadow-lg p-6 border border-gray-100 dark:border-slate-800">
                <div className="flex items-center mb-4">
                  {feature.icon}
                  <h2 className="ml-3 text-xl font-semibold text-gray-900 dark:text-slate-100">
                    {feature.title}
                  </h2>
                </div>
                
                <p className="text-gray-600 dark:text-slate-300 mb-6">
                  {feature.description}
                </p>

                <div className="space-y-2 mb-6">
                  {feature.features.map((item, index) => (
                    <div key={index} className="flex items-center text-sm text-gray-600 dark:text-slate-300">
                      <div className="w-1.5 h-1.5 bg-blue-600 rounded-full mr-2" />
                      {item}
                    </div>
                  ))}
                </div>

                <button
                  onClick={feature.action}
                  className={`w-full px-4 py-2 rounded-lg font-medium transition-colors ${
                    feature.id === 'discover'
                      ? 'bg-blue-600 hover:bg-blue-700 text-white'
                      : 'bg-green-600 hover:bg-green-700 text-white'
                  }`}
                >
                  {feature.id === 'discover' ? 'Start Discovering' : 'Generate Review'}
                </button>
              </div>
            ))}
          </div>
        ) : showDiscovery ? (
          /* Paper Discovery */
          <PaperDiscovery
            onClose={() => setShowDiscovery(false)}
            onAddPaper={(paper) => {
              console.log('Paper added:', paper)
              // Could show success notification here
            }}
          />
        ) : (
          /* Literature Review Generator */
          <LiteratureReviewGenerator
            onClose={() => setShowReviewGenerator(false)}
            onSave={(review) => {
              console.log('Review saved:', review)
              // Could integrate with paper creation here
            }}
          />
        )}

        {/* Quick Stats */}
        {!showDiscovery && !showReviewGenerator && (
          <div className="mt-12 bg-white dark:bg-slate-900 rounded-lg shadow-lg p-6 border border-gray-100 dark:border-slate-800">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-slate-100 mb-4">
              Phase 6: Literature Discovery & Automated Review Generation
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="text-center p-4 bg-blue-50 dark:bg-slate-800 rounded-lg">
                <div className="text-2xl font-bold text-blue-600 dark:text-blue-300">4</div>
                <div className="text-sm text-gray-600 dark:text-slate-200">Data Sources</div>
                <div className="text-xs text-gray-500 dark:text-slate-400">arXiv, Semantic Scholar, Crossref, PubMed</div>
              </div>
              <div className="text-center p-4 bg-green-50 dark:bg-slate-800 rounded-lg">
                <div className="text-2xl font-bold text-green-600 dark:text-green-300">AI</div>
                <div className="text-sm text-gray-600 dark:text-slate-200">Powered Ranking</div>
                <div className="text-xs text-gray-500 dark:text-slate-400">GPT relevance scoring</div>
              </div>
              <div className="text-center p-4 bg-purple-50 dark:bg-slate-800 rounded-lg">
                <div className="text-2xl font-bold text-purple-600 dark:text-purple-300">Auto</div>
                <div className="text-sm text-gray-600 dark:text-slate-200">Review Generation</div>
                <div className="text-xs text-gray-500 dark:text-slate-400">Comprehensive synthesis</div>
              </div>
              <div className="text-center p-4 bg-orange-50 dark:bg-slate-800 rounded-lg">
                <div className="text-2xl font-bold text-orange-600 dark:text-orange-300">∞</div>
                <div className="text-sm text-gray-600 dark:text-slate-200">Papers Available</div>
                <div className="text-xs text-gray-500 dark:text-slate-400">Millions of research papers</div>
              </div>
            </div>
          </div>
        )}

        {/* How It Works */}
        {!showDiscovery && !showReviewGenerator && (
          <div className="mt-8 bg-gradient-to-r from-blue-50 to-purple-50 dark:from-slate-800 dark:to-slate-900 rounded-lg p-8 border border-gray-100 dark:border-slate-800">
            <h3 className="text-xl font-semibold text-gray-900 dark:text-slate-100 mb-6 text-center">
              How Phase 6 Works
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="text-center">
                <div className="mx-auto w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center mb-4">
                  <Search size={24} className="text-blue-600" />
                </div>
                <h4 className="font-semibold text-gray-900 dark:text-slate-100 mb-2">1. Intelligent Discovery</h4>
                <p className="text-sm text-gray-600 dark:text-slate-300">
                  AI enhances your queries and searches multiple academic databases simultaneously
                </p>
              </div>
              <div className="text-center">
                <div className="mx-auto w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mb-4">
                  <TrendingUp size={24} className="text-green-600" />
                </div>
                <h4 className="font-semibold text-gray-900 dark:text-slate-100 mb-2">2. Smart Relevance Ranking</h4>
                <p className="text-sm text-gray-600 dark:text-slate-300">
                  Papers are ranked by AI-powered relevance scoring based on your research context
                </p>
              </div>
              <div className="text-center">
                <div className="mx-auto w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center mb-4">
                  <FileText size={24} className="text-purple-600" />
                </div>
                <h4 className="font-semibold text-gray-900 dark:text-slate-100 mb-2">3. Automated Review</h4>
                <p className="text-sm text-gray-600 dark:text-slate-300">
                  Generate comprehensive literature reviews with themes, gaps, and future directions
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>

  </>
  )
}

export default DiscoveryHub
