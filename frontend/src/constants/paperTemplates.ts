export type PaperTemplateDefinition = {
  id: string
  label: string
  description: string
  sections: string[]
  richTemplate: string
  latexTemplate: string
}

export const PAPER_TEMPLATES: PaperTemplateDefinition[] = [
  {
    id: 'research',
    label: 'Research Paper',
    description: 'IMRaD structure for reporting experiments and findings.',
    sections: ['Abstract', 'Introduction', 'Methods', 'Results', 'Discussion', 'Conclusion'],
    richTemplate: `# Abstract\n\nSummarize the research question, methodology, and key findings.\n\n# Introduction\n- Background\n- Problem statement\n- Objectives\n\n# Methods\nDescribe your experimental or analytical approach.\n\n# Results\nPresent the findings using tables or figures if needed.\n\n# Discussion\nInterpret the results and relate them to prior work.\n\n# Conclusion\nState the implications and future work.`,
    latexTemplate: `\\documentclass{article}\n\\begin{document}\n\\section{Abstract}\nSummarize the research question, methodology, and key findings.\n\\section{Introduction}\n\\begin{itemize}\n  \\item Background\\item Problem statement\\item Objectives\\end{itemize}\n\\section{Methods}\nDescribe your experimental or analytical approach.\n\\section{Results}\nPresent the findings using tables or figures if needed.\n\\section{Discussion}\nInterpret the results and relate them to prior work.\n\\section{Conclusion}\nState the implications and future work.\n\\end{document}`,
  },
  {
    id: 'review',
    label: 'Literature Review',
    description: 'Compare prior work, identify gaps, and suggest directions.',
    sections: ['Overview', 'Key Themes', 'Gap Analysis', 'Future Work'],
    richTemplate: `# Overview\nOutline the scope and criteria of the review.\n\n# Key Themes\n## Theme 1\nDiscuss representative papers.\n## Theme 2\nDiscuss representative papers.\n\n# Gap Analysis\nHighlight what remains unresolved.\n\n# Future Work\nPropose directions for future studies.`,
    latexTemplate: `\\documentclass{article}\n\\begin{document}\n\\section{Overview}\nOutline the scope and criteria of the review.\n\\section{Key Themes}\n\\subsection{Theme 1}\nDiscuss representative papers.\n\\subsection{Theme 2}\nDiscuss representative papers.\n\\section{Gap Analysis}\nHighlight what remains unresolved.\n\\section{Future Work}\nPropose directions for future studies.\n\\end{document}`,
  },
  {
    id: 'case_study',
    label: 'Case Study',
    description: 'Deep dive into a single scenario or deployment.',
    sections: ['Background', 'Case Description', 'Analysis', 'Lessons Learned'],
    richTemplate: `# Background\nFrame the context and stakeholders.\n\n# Case Description\nDescribe the setting and events chronologically.\n\n# Analysis\nInterpret the decisions and outcomes.\n\n# Lessons Learned\nList actionable insights and recommendations.`,
    latexTemplate: `\\documentclass{article}\n\\begin{document}\n\\section{Background}\nFrame the context and stakeholders.\n\\section{Case Description}\nDescribe the setting and events chronologically.\n\\section{Analysis}\nInterpret the decisions and outcomes.\n\\section{Lessons Learned}\nList actionable insights and recommendations.\n\\end{document}`,
  },
]
