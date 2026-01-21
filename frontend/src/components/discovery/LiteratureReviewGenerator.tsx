import React, { useState, useEffect } from 'react'
import { FileText, BookOpen, Clock, Download, TrendingUp, Copy, Eye, Edit, Save } from 'lucide-react'
import { usePapers } from '../../contexts/PapersContext'
import { buildApiUrl } from '../../services/api'

interface LiteratureReviewSection {
  title: string
  content: string
  papers_cited: string[]
  themes: string[]
}

interface LiteratureReview {
  title: string
  abstract: string
  introduction: string
  methodology: string
  sections: LiteratureReviewSection[]
  synthesis: string
  research_gaps: string[]
  future_directions: string[]
  conclusion: string
  references: string[]
  total_papers: number
  generation_time: number
}

interface LiteratureReviewGeneratorProps {
  selectedPaperIds?: string[]
  onClose?: () => void
  onSave?: (review: LiteratureReview) => void
}

const LiteratureReviewGenerator: React.FC<LiteratureReviewGeneratorProps> = ({
  selectedPaperIds = [],
  onClose,
  onSave
}) => {
  const { papers } = usePapers()
  const [selectedPapers, setSelectedPapers] = useState<string[]>(selectedPaperIds)
  const [reviewTopic, setReviewTopic] = useState('')
  const [reviewType, setReviewType] = useState<'systematic' | 'narrative' | 'scoping'>('systematic')
  const [maxSections, setMaxSections] = useState(6)
  const [isGenerating, setIsGenerating] = useState(false)
  const [generatedReview, setGeneratedReview] = useState<LiteratureReview | null>(null)
  const [viewMode, setViewMode] = useState<'preview' | 'edit'>('preview')
  const [editedReview, setEditedReview] = useState<LiteratureReview | null>(null)

  // Initialize selected papers if provided
  useEffect(() => {
    if (selectedPaperIds.length > 0) {
      setSelectedPapers(selectedPaperIds)
    }
  }, [selectedPaperIds])

  const availablePapers = papers || []
  // const selectedPaperObjects = availablePapers.filter(p => selectedPapers.includes(p.id))

  const handlePaperToggle = (paperId: string) => {
    setSelectedPapers(prev =>
      prev.includes(paperId)
        ? prev.filter(id => id !== paperId)
        : [...prev, paperId]
    )
  }

  const handleGenerateReview = async () => {
    if (selectedPapers.length < 2) {
      alert('Please select at least 2 papers for literature review generation')
      return
    }

    if (!reviewTopic.trim()) {
      alert('Please enter a review topic')
      return
    }

    setIsGenerating(true)

    try {
      const response = await fetch(buildApiUrl('/discovery/literature-review/generate'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({
          paper_ids: selectedPapers,
          review_topic: reviewTopic.trim(),
          review_type: reviewType,
          max_sections: maxSections
        })
      })

      if (!response.ok) {
        throw new Error(`Review generation failed: ${response.statusText}`)
      }

      const review = await response.json()
      setGeneratedReview(review)
      setEditedReview(review)
      
    } catch (error) {
      console.error('Error generating literature review:', error)
      alert('Literature review generation failed. Please try again.')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleCopyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    alert('Content copied to clipboard!')
  }

  const handleSaveReview = () => {
    if (editedReview && onSave) {
      onSave(editedReview)
    }
  }

  const handleEditSection = (sectionIndex: number, newContent: string) => {
    if (editedReview) {
      const updatedSections = [...editedReview.sections]
      updatedSections[sectionIndex] = { ...updatedSections[sectionIndex], content: newContent }
      setEditedReview({ ...editedReview, sections: updatedSections })
    }
  }

  const formatReviewForDownload = (review: LiteratureReview) => {
    let content = `# ${review.title}\n\n`
    content += `## Abstract\n${review.abstract}\n\n`
    content += `## Introduction\n${review.introduction}\n\n`
    content += `## Methodology\n${review.methodology}\n\n`
    
    review.sections.forEach(section => {
      content += `## ${section.title}\n${section.content}\n\n`
    })
    
    content += `## Synthesis\n${review.synthesis}\n\n`
    
    if (review.research_gaps.length > 0) {
      content += `## Research Gaps\n`
      review.research_gaps.forEach(gap => {
        content += `- ${gap}\n`
      })
      content += '\n'
    }
    
    if (review.future_directions.length > 0) {
      content += `## Future Directions\n`
      review.future_directions.forEach(direction => {
        content += `- ${direction}\n`
      })
      content += '\n'
    }
    
    content += `## Conclusion\n${review.conclusion}\n\n`
    
    if (review.references.length > 0) {
      content += `## References\n`
      review.references.forEach((ref, index) => {
        content += `${index + 1}. ${ref}\n`
      })
    }
    
    return content
  }

  const handleDownload = () => {
    if (editedReview) {
      const content = formatReviewForDownload(editedReview)
      const blob = new Blob([content], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${editedReview.title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.md`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }
  }

  return (
    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg max-w-6xl mx-auto h-[90vh] flex flex-col">
      {/* Header */}
      <div className="p-6 border-b border-gray-200 dark:border-slate-700">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-slate-100 flex items-center">
            <FileText className="mr-2" size={24} />
            Literature Review Generator
          </h2>
          {onClose && (
            <button
              onClick={onClose}
              className="text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200"
            >
              ×
            </button>
          )}
        </div>

        {!generatedReview ? (
          /* Configuration Panel */
          <div className="space-y-6">
            {/* Topic Input */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                Review Topic/Research Question
              </label>
              <textarea
                value={reviewTopic}
                onChange={(e) => setReviewTopic(e.target.value)}
                placeholder="e.g., 'The impact of artificial intelligence on academic research methodologies'"
                rows={3}
                className="w-full px-4 py-2 border border-gray-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 placeholder-gray-400 dark:placeholder-slate-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            {/* Review Settings */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">Review Type</label>
                <select
                  value={reviewType}
                  onChange={(e) => setReviewType(e.target.value as 'systematic' | 'narrative' | 'scoping')}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100"
                >
                  <option value="systematic">Systematic Review</option>
                  <option value="narrative">Narrative Review</option>
                  <option value="scoping">Scoping Review</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">Max Sections</label>
                <select
                  value={maxSections}
                  onChange={(e) => setMaxSections(Number(e.target.value))}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100"
                >
                  <option value={4}>4 sections</option>
                  <option value={5}>5 sections</option>
                  <option value={6}>6 sections</option>
                  <option value={8}>8 sections</option>
                  <option value={10}>10 sections</option>
                </select>
              </div>

              <div className="flex items-end">
                <button
                  onClick={handleGenerateReview}
                  disabled={isGenerating || selectedPapers.length < 2 || !reviewTopic.trim()}
                  className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 dark:disabled:bg-slate-600 flex items-center justify-center space-x-2"
                >
                  {isGenerating ? (
                    <>
                      <Clock className="animate-spin" size={16} />
                      <span>Generating...</span>
                    </>
                  ) : (
                    <>
                      <TrendingUp size={16} />
                      <span>Generate Review</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Paper Selection */}
            <div>
              <div className="flex justify-between items-center mb-3">
                <label className="block text-sm font-medium text-gray-700 dark:text-slate-300">
                  Select Papers ({selectedPapers.length} selected)
                </label>
                <span className="text-xs text-gray-500 dark:text-slate-400">
                  Minimum 2 papers required
                </span>
              </div>

              <div className="border border-gray-300 dark:border-slate-600 rounded-lg max-h-64 overflow-y-auto">
                {availablePapers.length === 0 ? (
                  <div className="p-4 text-center text-gray-500 dark:text-slate-400">
                    <BookOpen className="mx-auto mb-2" size={24} />
                    <p>No papers available. Add some papers to your library first.</p>
                  </div>
                ) : (
                  <div className="divide-y divide-gray-200 dark:divide-slate-700">
                    {availablePapers.map(paper => (
                      <label key={paper.id} className="flex items-start p-3 hover:bg-gray-50 dark:hover:bg-slate-700 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedPapers.includes(paper.id)}
                          onChange={() => handlePaperToggle(paper.id)}
                          className="mt-1 mr-3 rounded dark:bg-slate-700 dark:border-slate-500"
                        />
                        <div className="flex-1 min-w-0">
                          <h4 className="font-medium text-gray-900 dark:text-slate-100 mb-1">{paper.title}</h4>
                          <p className="text-sm text-gray-600 dark:text-slate-400">
                            {paper.description?.substring(0, 120)}...
                          </p>
                          <div className="text-xs text-gray-500 dark:text-slate-500 mt-1">
                            {paper.year && `${paper.year} • `}
                            {paper.status && (
                              <span className="capitalize">{paper.status}</span>
                            )}
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          /* Review Controls */
          <div className="flex justify-between items-center">
            <div className="text-sm text-gray-600 dark:text-slate-400">
              Generated from {generatedReview.total_papers} papers in {generatedReview.generation_time.toFixed(1)}s
            </div>
            <div className="flex items-center space-x-2">
              <div className="flex bg-gray-100 dark:bg-slate-700 rounded-lg p-1">
                <button
                  onClick={() => setViewMode('preview')}
                  className={`px-3 py-1 text-sm rounded ${viewMode === 'preview' ? 'bg-white dark:bg-slate-600 shadow-sm text-gray-900 dark:text-slate-100' : 'text-gray-600 dark:text-slate-400'}`}
                >
                  <Eye size={14} className="mr-1 inline" />
                  Preview
                </button>
                <button
                  onClick={() => setViewMode('edit')}
                  className={`px-3 py-1 text-sm rounded ${viewMode === 'edit' ? 'bg-white dark:bg-slate-600 shadow-sm text-gray-900 dark:text-slate-100' : 'text-gray-600 dark:text-slate-400'}`}
                >
                  <Edit size={14} className="mr-1 inline" />
                  Edit
                </button>
              </div>
              <button
                onClick={handleDownload}
                className="px-3 py-2 bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 rounded-lg hover:bg-blue-200 dark:hover:bg-blue-900/50 flex items-center space-x-1"
              >
                <Download size={14} />
                <span>Download</span>
              </button>
              {onSave && (
                <button
                  onClick={handleSaveReview}
                  className="px-3 py-2 bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 rounded-lg hover:bg-green-200 dark:hover:bg-green-900/50 flex items-center space-x-1"
                >
                  <Save size={14} />
                  <span>Save</span>
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Content */}
      {isGenerating ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <Clock className="animate-spin h-12 w-12 text-blue-600 dark:text-blue-400 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-slate-100 mb-2">
              Generating Literature Review
            </h3>
            <p className="text-gray-600 dark:text-slate-400 mb-4">
              AI is analyzing {selectedPapers.length} papers, identifying themes, and synthesizing findings...
            </p>
            <div className="w-full bg-gray-200 dark:bg-slate-700 rounded-full h-2">
              <div className="bg-blue-600 h-2 rounded-full animate-pulse" style={{ width: '70%' }}></div>
            </div>
          </div>
        </div>
      ) : generatedReview ? (
        <div className="flex-1 overflow-y-auto p-6">
          <div className="prose max-w-none dark:prose-invert">
            {/* Title */}
            <h1 className="text-3xl font-bold text-gray-900 dark:text-slate-100 mb-6 flex items-center justify-between">
              {editedReview?.title}
              <button
                onClick={() => handleCopyToClipboard(editedReview?.title || '')}
                className="text-gray-400 dark:text-slate-500 hover:text-gray-600 dark:hover:text-slate-300"
              >
                <Copy size={20} />
              </button>
            </h1>

            {/* Abstract */}
            <section className="mb-8">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-slate-100 mb-3 flex items-center justify-between">
                Abstract
                <button
                  onClick={() => handleCopyToClipboard(editedReview?.abstract || '')}
                  className="text-gray-400 dark:text-slate-500 hover:text-gray-600 dark:hover:text-slate-300"
                >
                  <Copy size={16} />
                </button>
              </h2>
              {viewMode === 'edit' ? (
                <textarea
                  value={editedReview?.abstract}
                  onChange={(e) => setEditedReview(prev => prev ? {...prev, abstract: e.target.value} : null)}
                  className="w-full p-3 border border-gray-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100"
                  rows={4}
                />
              ) : (
                <p className="text-gray-700 dark:text-slate-300 bg-gray-50 dark:bg-slate-700/50 p-4 rounded-lg">
                  {editedReview?.abstract}
                </p>
              )}
            </section>

            {/* Introduction */}
            <section className="mb-8">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-slate-100 mb-3 flex items-center justify-between">
                Introduction
                <button
                  onClick={() => handleCopyToClipboard(editedReview?.introduction || '')}
                  className="text-gray-400 dark:text-slate-500 hover:text-gray-600 dark:hover:text-slate-300"
                >
                  <Copy size={16} />
                </button>
              </h2>
              {viewMode === 'edit' ? (
                <textarea
                  value={editedReview?.introduction}
                  onChange={(e) => setEditedReview(prev => prev ? {...prev, introduction: e.target.value} : null)}
                  className="w-full p-3 border border-gray-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100"
                  rows={6}
                />
              ) : (
                <div className="text-gray-700 dark:text-slate-300 whitespace-pre-line bg-gray-50 dark:bg-slate-700/50 p-4 rounded-lg">
                  {editedReview?.introduction}
                </div>
              )}
            </section>

            {/* Methodology */}
            <section className="mb-8">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-slate-100 mb-3 flex items-center justify-between">
                Methodology
                <button
                  onClick={() => handleCopyToClipboard(editedReview?.methodology || '')}
                  className="text-gray-400 dark:text-slate-500 hover:text-gray-600 dark:hover:text-slate-300"
                >
                  <Copy size={16} />
                </button>
              </h2>
              <div className="text-gray-700 dark:text-slate-300 whitespace-pre-line bg-gray-50 dark:bg-slate-700/50 p-4 rounded-lg">
                {editedReview?.methodology}
              </div>
            </section>

            {/* Main Sections */}
            {editedReview?.sections.map((section, index) => (
              <section key={index} className="mb-8">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-slate-100 mb-3 flex items-center justify-between">
                  {section.title}
                  <button
                    onClick={() => handleCopyToClipboard(section.content)}
                    className="text-gray-400 dark:text-slate-500 hover:text-gray-600 dark:hover:text-slate-300"
                  >
                    <Copy size={16} />
                  </button>
                </h2>
                {viewMode === 'edit' ? (
                  <textarea
                    value={section.content}
                    onChange={(e) => handleEditSection(index, e.target.value)}
                    className="w-full p-3 border border-gray-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100"
                    rows={8}
                  />
                ) : (
                  <div className="text-gray-700 dark:text-slate-300 whitespace-pre-line bg-gray-50 dark:bg-slate-700/50 p-4 rounded-lg">
                    {section.content}
                  </div>
                )}
                {section.themes.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {section.themes.map((theme, idx) => (
                      <span key={idx} className="px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 text-xs rounded-full">
                        {theme}
                      </span>
                    ))}
                  </div>
                )}
              </section>
            ))}

            {/* Synthesis */}
            <section className="mb-8">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-slate-100 mb-3 flex items-center justify-between">
                Synthesis
                <button
                  onClick={() => handleCopyToClipboard(editedReview?.synthesis || '')}
                  className="text-gray-400 dark:text-slate-500 hover:text-gray-600 dark:hover:text-slate-300"
                >
                  <Copy size={16} />
                </button>
              </h2>
              {viewMode === 'edit' ? (
                <textarea
                  value={editedReview?.synthesis}
                  onChange={(e) => setEditedReview(prev => prev ? {...prev, synthesis: e.target.value} : null)}
                  className="w-full p-3 border border-gray-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100"
                  rows={6}
                />
              ) : (
                <div className="text-gray-700 dark:text-slate-300 whitespace-pre-line bg-gray-50 dark:bg-slate-700/50 p-4 rounded-lg">
                  {editedReview?.synthesis}
                </div>
              )}
            </section>

            {/* Research Gaps */}
            {editedReview?.research_gaps && editedReview.research_gaps.length > 0 && (
              <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-slate-100 mb-3">Research Gaps</h2>
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/50 rounded-lg p-4">
                  <ul className="list-disc list-inside space-y-2">
                    {editedReview.research_gaps.map((gap, index) => (
                      <li key={index} className="text-red-800 dark:text-red-300">{gap}</li>
                    ))}
                  </ul>
                </div>
              </section>
            )}

            {/* Future Directions */}
            {editedReview?.future_directions && editedReview.future_directions.length > 0 && (
              <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-slate-100 mb-3">Future Directions</h2>
                <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800/50 rounded-lg p-4">
                  <ul className="list-disc list-inside space-y-2">
                    {editedReview.future_directions.map((direction, index) => (
                      <li key={index} className="text-green-800 dark:text-green-300">{direction}</li>
                    ))}
                  </ul>
                </div>
              </section>
            )}

            {/* Conclusion */}
            <section className="mb-8">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-slate-100 mb-3 flex items-center justify-between">
                Conclusion
                <button
                  onClick={() => handleCopyToClipboard(editedReview?.conclusion || '')}
                  className="text-gray-400 dark:text-slate-500 hover:text-gray-600 dark:hover:text-slate-300"
                >
                  <Copy size={16} />
                </button>
              </h2>
              {viewMode === 'edit' ? (
                <textarea
                  value={editedReview?.conclusion}
                  onChange={(e) => setEditedReview(prev => prev ? {...prev, conclusion: e.target.value} : null)}
                  className="w-full p-3 border border-gray-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100"
                  rows={6}
                />
              ) : (
                <div className="text-gray-700 dark:text-slate-300 whitespace-pre-line bg-gray-50 dark:bg-slate-700/50 p-4 rounded-lg">
                  {editedReview?.conclusion}
                </div>
              )}
            </section>

            {/* References */}
            {editedReview?.references && editedReview.references.length > 0 && (
              <section className="mb-8">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-slate-100 mb-3">References</h2>
                <div className="bg-gray-50 dark:bg-slate-700/50 p-4 rounded-lg">
                  <ol className="list-decimal list-inside space-y-1">
                    {editedReview.references.map((ref, index) => (
                      <li key={index} className="text-sm text-gray-700 dark:text-slate-300">{ref}</li>
                    ))}
                  </ol>
                </div>
              </section>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <FileText className="h-12 w-12 text-gray-400 dark:text-slate-500 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-slate-100 mb-2">
              Ready to Generate Literature Review
            </h3>
            <p className="text-gray-600 dark:text-slate-400">
              Configure your review settings and select papers to generate an AI-powered literature review.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

export default LiteratureReviewGenerator
