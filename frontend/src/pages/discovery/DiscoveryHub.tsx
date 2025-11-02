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
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="py-6">
            <h1 className="text-3xl font-bold text-gray-900 flex items-center">
              <TrendingUp className="mr-3" size={32} />
              Discovery Hub
            </h1>
            <p className="mt-2 text-gray-600">
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
              <div key={feature.id} className="bg-white rounded-lg shadow-lg p-6">
                <div className="flex items-center mb-4">
                  {feature.icon}
                  <h2 className="ml-3 text-xl font-semibold text-gray-900">
                    {feature.title}
                  </h2>
                </div>
                
                <p className="text-gray-600 mb-6">
                  {feature.description}
                </p>

                <div className="space-y-2 mb-6">
                  {feature.features.map((item, index) => (
                    <div key={index} className="flex items-center text-sm text-gray-600">
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
          <div className="mt-12 bg-white rounded-lg shadow-lg p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              Phase 6: Literature Discovery & Automated Review Generation
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="text-center p-4 bg-blue-50 rounded-lg">
                <div className="text-2xl font-bold text-blue-600">4</div>
                <div className="text-sm text-gray-600">Data Sources</div>
                <div className="text-xs text-gray-500">arXiv, Semantic Scholar, Crossref, PubMed</div>
              </div>
              <div className="text-center p-4 bg-green-50 rounded-lg">
                <div className="text-2xl font-bold text-green-600">AI</div>
                <div className="text-sm text-gray-600">Powered Ranking</div>
                <div className="text-xs text-gray-500">GPT relevance scoring</div>
              </div>
              <div className="text-center p-4 bg-purple-50 rounded-lg">
                <div className="text-2xl font-bold text-purple-600">Auto</div>
                <div className="text-sm text-gray-600">Review Generation</div>
                <div className="text-xs text-gray-500">Comprehensive synthesis</div>
              </div>
              <div className="text-center p-4 bg-orange-50 rounded-lg">
                <div className="text-2xl font-bold text-orange-600">∞</div>
                <div className="text-sm text-gray-600">Papers Available</div>
                <div className="text-xs text-gray-500">Millions of research papers</div>
              </div>
            </div>
          </div>
        )}

        {/* How It Works */}
        {!showDiscovery && !showReviewGenerator && (
          <div className="mt-8 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg p-8">
            <h3 className="text-xl font-semibold text-gray-900 mb-6 text-center">
              How Phase 6 Works
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="text-center">
                <div className="mx-auto w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center mb-4">
                  <Search size={24} className="text-blue-600" />
                </div>
                <h4 className="font-semibold text-gray-900 mb-2">1. Intelligent Discovery</h4>
                <p className="text-sm text-gray-600">
                  AI enhances your queries and searches multiple academic databases simultaneously
                </p>
              </div>
              <div className="text-center">
                <div className="mx-auto w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mb-4">
                  <TrendingUp size={24} className="text-green-600" />
                </div>
                <h4 className="font-semibold text-gray-900 mb-2">2. Smart Relevance Ranking</h4>
                <p className="text-sm text-gray-600">
                  Papers are ranked by AI-powered relevance scoring based on your research context
                </p>
              </div>
              <div className="text-center">
                <div className="mx-auto w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center mb-4">
                  <FileText size={24} className="text-purple-600" />
                </div>
                <h4 className="font-semibold text-gray-900 mb-2">3. Automated Review</h4>
                <p className="text-sm text-gray-600">
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
