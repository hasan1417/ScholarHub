import React from 'react'
import { Plus, BookOpen, TestTube, Lightbulb, Target, Users } from 'lucide-react'

interface AcademicPaperTemplate {
  id: string
  name: string
  description: string
  icon: React.ReactNode
  structure: string
  category: 'research' | 'review' | 'methodology' | 'case_study'
}

interface AcademicPaperTemplateProps {
  onSelectTemplate: (template: AcademicPaperTemplate) => void
}

const AcademicPaperTemplate: React.FC<AcademicPaperTemplateProps> = ({ onSelectTemplate }) => {
  const templates: AcademicPaperTemplate[] = [
    {
      id: 'research-paper',
      name: 'Research Paper',
      description: 'Standard research paper with introduction, methodology, results, and discussion',
      icon: <TestTube size={24} className="text-blue-600" />,
      structure: `
        <h1>Title</h1>
        <h2>Abstract</h2>
        <p>Brief summary of the research...</p>
        
        <h2>1. Introduction</h2>
        <p>Background and context...</p>
        <p>Research question and objectives...</p>
        
        <h2>2. Literature Review</h2>
        <p>Previous research and findings...</p>
        
        <h2>3. Methodology</h2>
        <p>Research design and methods...</p>
        
        <h2>4. Results</h2>
        <p>Findings and data analysis...</p>
        
        <h2>5. Discussion</h2>
        <p>Interpretation of results...</p>
        
        <h2>6. Conclusion</h2>
        <p>Summary and implications...</p>
        
        <h2>References</h2>
        <p>List of cited sources...</p>
      `,
      category: 'research'
    },
    {
      id: 'literature-review',
      name: 'Literature Review',
      description: 'Comprehensive review of existing research in a specific field',
      icon: <BookOpen size={24} className="text-green-600" />,
      structure: `
        <h1>Title</h1>
        <h2>Abstract</h2>
        <p>Overview of the review...</p>
        
        <h2>1. Introduction</h2>
        <p>Scope and objectives...</p>
        
        <h2>2. Methodology</h2>
        <p>Search strategy and inclusion criteria...</p>
        
        <h2>3. Theoretical Framework</h2>
        <p>Underlying theories and concepts...</p>
        
        <h2>4. Review of Literature</h2>
        <h3>4.1 Theme 1</h3>
        <p>Analysis of first theme...</p>
        <h3>4.2 Theme 2</h3>
        <p>Analysis of second theme...</p>
        
        <h2>5. Synthesis</h2>
        <p>Integration of findings...</p>
        
        <h2>6. Conclusion</h2>
        <p>Summary and future directions...</p>
        
        <h2>References</h2>
        <p>List of reviewed sources...</p>
      `,
      category: 'review'
    },
    {
      id: 'methodology-paper',
      name: 'Methodology Paper',
      description: 'Detailed description of research methods and procedures',
      icon: <Target size={24} className="text-purple-600" />,
      structure: `
        <h1>Title</h1>
        <h2>Abstract</h2>
        <p>Method overview...</p>
        
        <h2>1. Introduction</h2>
        <p>Methodological context...</p>
        
        <h2>2. Method Description</h2>
        <h3>2.1 Participants</h3>
        <p>Sample description...</p>
        <h3>2.2 Materials</h3>
        <p>Instruments and tools...</p>
        <h3>2.3 Procedure</h3>
        <p>Step-by-step process...</p>
        
        <h2>3. Validation</h2>
        <p>Reliability and validity...</p>
        
        <h2>4. Applications</h2>
        <p>Use cases and limitations...</p>
        
        <h2>References</h2>
        <p>Methodological sources...</p>
      `,
      category: 'methodology'
    },
    {
      id: 'case-study',
      name: 'Case Study',
      description: 'In-depth analysis of a specific instance or phenomenon',
      icon: <Users size={24} className="text-orange-600" />,
      structure: `
        <h1>Title</h1>
        <h2>Abstract</h2>
        <p>Case overview...</p>
        
        <h2>1. Introduction</h2>
        <p>Case background and significance...</p>
        
        <h2>2. Case Description</h2>
        <h3>2.1 Context</h3>
        <p>Setting and circumstances...</p>
        <h3>2.2 Participants</h3>
        <p>Key individuals involved...</p>
        <h3>2.3 Timeline</h3>
        <p>Sequence of events...</p>
        
        <h2>3. Analysis</h2>
        <p>Critical examination...</p>
        
        <h2>4. Discussion</h2>
        <p>Implications and lessons...</p>
        
        <h2>5. Conclusion</h2>
        <p>Summary and recommendations...</p>
        
        <h2>References</h2>
        <p>Supporting sources...</p>
      `,
      category: 'case_study'
    }
  ]

  const getCategoryColor = (category: string) => {
    switch (category) {
      case 'research': return 'bg-blue-50 border-blue-200 text-blue-800'
      case 'review': return 'bg-green-50 border-green-200 text-green-800'
      case 'methodology': return 'bg-purple-50 border-purple-200 text-purple-800'
      case 'case_study': return 'bg-orange-50 border-orange-200 text-orange-800'
      default: return 'bg-gray-50 border-gray-200 text-gray-800'
    }
  }

  const getCategoryLabel = (category: string) => {
    switch (category) {
      case 'research': return 'Research'
      case 'review': return 'Literature Review'
      case 'methodology': return 'Methodology'
      case 'case_study': return 'Case Study'
      default: return 'Other'
    }
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Choose a Paper Template</h2>
        <p className="text-gray-600">
          Select a template to get started with your academic paper. Each template includes a structured outline 
          that follows academic writing standards.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {templates.map((template) => (
          <div
            key={template.id}
            className="border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow cursor-pointer group"
            onClick={() => onSelectTemplate(template)}
          >
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0">
                {template.icon}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <h3 className="text-lg font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
                    {template.name}
                  </h3>
                  <span className={`px-2 py-1 text-xs font-medium rounded-full border ${getCategoryColor(template.category)}`}>
                    {getCategoryLabel(template.category)}
                  </span>
                </div>
                <p className="text-gray-600 text-sm mb-4 leading-relaxed">
                  {template.description}
                </p>
                <div className="flex items-center gap-2 text-blue-600 text-sm font-medium group-hover:text-blue-700 transition-colors">
                  <Plus size={16} />
                  <span>Use this template</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-8 p-4 bg-gray-50 rounded-lg">
        <div className="flex items-center gap-2 text-gray-600">
          <Lightbulb size={16} />
          <span className="text-sm">
            <strong>Tip:</strong> You can always modify the template structure after selecting it. 
            These templates are designed to help you get started with proper academic formatting.
          </span>
        </div>
      </div>
    </div>
  )
}

export default AcademicPaperTemplate
