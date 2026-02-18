export type PaperTemplateDefinition = {
  id: string
  label: string
  description: string
  sections: string[]
  richTemplate: string
  latexTemplate: string
}

export interface VenueFormat {
  id: string
  label: string
  description: string
  preamble: string
}

export const VENUE_FORMATS: VenueFormat[] = [
  {
    id: 'generic',
    label: 'Generic',
    description: 'Standard article format',
    preamble: '\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{amsmath,amssymb}\n\\usepackage{graphicx}\n\\usepackage[margin=1in]{geometry}\n\n\\title{%TITLE%}\n\\author{%AUTHOR%}\n\\date{\\today}\n\n\\begin{document}\n\\maketitle',
  },
  {
    id: 'ieee',
    label: 'IEEE',
    description: 'IEEE Conference format',
    preamble: '\\documentclass[conference]{IEEEtran}\n\\usepackage{cite}\n\\usepackage{amsmath,amssymb,amsfonts}\n\\usepackage{graphicx}\n\\usepackage{textcomp}\n\n\\title{%TITLE%}\n\\author{%AUTHOR%}\n\n\\begin{document}\n\\maketitle',
  },
  {
    id: 'acm',
    label: 'ACM',
    description: 'ACM Conference format',
    preamble: '\\documentclass[sigconf]{acmart}\n\n\\title{%TITLE%}\n\\author{%AUTHOR%}\n\n\\begin{document}\n\\maketitle',
  },
  {
    id: 'neurips',
    label: 'NeurIPS',
    description: 'NeurIPS submission format',
    preamble: '\\documentclass{article}\n\\usepackage[final]{neurips_2024}\n\\usepackage[utf8]{inputenc}\n\\usepackage{amsmath,amssymb}\n\n\\title{%TITLE%}\n\\author{%AUTHOR%}\n\n\\begin{document}\n\\maketitle',
  },
  {
    id: 'springer',
    label: 'Springer LNCS',
    description: 'Springer Lecture Notes in Computer Science',
    preamble: '\\documentclass[runningheads]{llncs}\n\\usepackage{graphicx}\n\\usepackage{amsmath,amssymb}\n\n\\title{%TITLE%}\n\\author{%AUTHOR%}\n\n\\begin{document}\n\\maketitle',
  },
  {
    id: 'elsevier',
    label: 'Elsevier',
    description: 'Elsevier journal format',
    preamble: '\\documentclass[preprint,12pt]{elsarticle}\n\\usepackage{amssymb}\n\\usepackage{graphicx}\n\n\\begin{document}\n\\begin{frontmatter}\n\\title{%TITLE%}\n\\author{%AUTHOR%}\n\\end{frontmatter}',
  },
  {
    id: 'apa7',
    label: 'APA 7th Edition',
    description: 'American Psychological Association format',
    preamble: '\\documentclass[man,12pt]{apa7}\n\\usepackage[utf8]{inputenc}\n\\usepackage{amsmath}\n\n\\title{%TITLE%}\n\\authorsnames{%AUTHOR%}\n\n\\begin{document}\n\\maketitle',
  },
]

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
  {
    id: 'thesis',
    label: 'Thesis / Dissertation',
    description: 'Full-length thesis with chapters for graduate work.',
    sections: ['Abstract', 'Introduction', 'Literature Review', 'Methodology', 'Results', 'Discussion', 'Conclusion', 'References'],
    richTemplate: `# Abstract\nSummarize the research objectives, methods, and findings.\n\n# Introduction\nIntroduce the research topic and state the problem.\n\n# Literature Review\nSurvey existing work and identify gaps.\n\n# Methodology\nDescribe the research design and procedures.\n\n# Results\nPresent the findings.\n\n# Discussion\nInterpret results and relate to prior work.\n\n# Conclusion\nSummarize contributions and future directions.\n\n# References`,
    latexTemplate: `\\documentclass[12pt]{report}\n\\usepackage[utf8]{inputenc}\n\\usepackage{amsmath,amssymb}\n\\usepackage{graphicx}\n\\usepackage[margin=1in]{geometry}\n\n\\title{Thesis Title}\n\\author{Author Name}\n\\date{\\today}\n\n\\begin{document}\n\\maketitle\n\\tableofcontents\n\n\\chapter{Abstract}\n% TODO: Add content here.\n\n\\chapter{Introduction}\n% TODO: Add content here.\n\n\\chapter{Literature Review}\n% TODO: Add content here.\n\n\\chapter{Methodology}\n% TODO: Add content here.\n\n\\chapter{Results}\n% TODO: Add content here.\n\n\\chapter{Discussion}\n% TODO: Add content here.\n\n\\chapter{Conclusion}\n% TODO: Add content here.\n\n\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}`,
  },
  {
    id: 'technical_report',
    label: 'Technical Report',
    description: 'Detailed technical documentation of methods and results.',
    sections: ['Abstract', 'Introduction', 'Background', 'Technical Approach', 'Implementation', 'Evaluation', 'Conclusion'],
    richTemplate: `# Abstract\nBrief summary of the report.\n\n# Introduction\nState the purpose and scope.\n\n# Background\nProvide context and prior work.\n\n# Technical Approach\nDescribe the methodology in detail.\n\n# Implementation\nExplain the implementation specifics.\n\n# Evaluation\nPresent experiments, benchmarks, or analysis.\n\n# Conclusion\nSummarize findings and next steps.`,
    latexTemplate: `\\documentclass[11pt]{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{amsmath,amssymb}\n\\usepackage{graphicx}\n\\usepackage[margin=1in]{geometry}\n\n\\title{Technical Report Title}\n\\author{Author Name}\n\\date{\\today}\n\n\\begin{document}\n\\maketitle\n\n\\section{Abstract}\n% TODO: Add content here.\n\n\\section{Introduction}\n% TODO: Add content here.\n\n\\section{Background}\n% TODO: Add content here.\n\n\\section{Technical Approach}\n% TODO: Add content here.\n\n\\section{Implementation}\n% TODO: Add content here.\n\n\\section{Evaluation}\n% TODO: Add content here.\n\n\\section{Conclusion}\n% TODO: Add content here.\n\n\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}`,
  },
  {
    id: 'proposal',
    label: 'Research Proposal',
    description: 'Structured proposal for funding or project approval.',
    sections: ['Abstract', 'Introduction', 'Problem Statement', 'Objectives', 'Literature Review', 'Methodology', 'Timeline', 'Expected Outcomes', 'Budget', 'References'],
    richTemplate: `# Abstract\nSummarize the proposed research.\n\n# Introduction\nIntroduce the research area and motivation.\n\n# Problem Statement\nDefine the problem to be addressed.\n\n# Objectives\nList specific aims and goals.\n\n# Literature Review\nReview relevant prior work.\n\n# Methodology\nDescribe the planned approach.\n\n# Timeline\nOutline milestones and schedule.\n\n# Expected Outcomes\nDescribe anticipated results and impact.\n\n# Budget\nItemize resource requirements.\n\n# References`,
    latexTemplate: `\\documentclass[12pt]{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{amsmath,amssymb}\n\\usepackage{graphicx}\n\\usepackage[margin=1in]{geometry}\n\n\\title{Research Proposal Title}\n\\author{Author Name}\n\\date{\\today}\n\n\\begin{document}\n\\maketitle\n\n\\section{Abstract}\n% TODO: Add content here.\n\n\\section{Introduction}\n% TODO: Add content here.\n\n\\section{Problem Statement}\n% TODO: Add content here.\n\n\\section{Objectives}\n% TODO: Add content here.\n\n\\section{Literature Review}\n% TODO: Add content here.\n\n\\section{Methodology}\n% TODO: Add content here.\n\n\\section{Timeline}\n% TODO: Add content here.\n\n\\section{Expected Outcomes}\n% TODO: Add content here.\n\n\\section{Budget}\n% TODO: Add content here.\n\n\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}`,
  },
  {
    id: 'survey',
    label: 'Survey / SoK Paper',
    description: 'Systematization of knowledge across a research area.',
    sections: ['Abstract', 'Introduction', 'Scope & Methodology', 'Taxonomy', 'Analysis of Approaches', 'Open Problems', 'Conclusion'],
    richTemplate: `# Abstract\nSummarize the scope and findings of the survey.\n\n# Introduction\nMotivate the survey and state research questions.\n\n# Scope & Methodology\nDefine inclusion criteria and search strategy.\n\n# Taxonomy\nPresent the classification framework.\n\n# Analysis of Approaches\nCompare and contrast existing methods.\n\n# Open Problems\nIdentify unresolved challenges and gaps.\n\n# Conclusion\nSummarize insights and future directions.`,
    latexTemplate: `\\documentclass[11pt]{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{amsmath,amssymb}\n\\usepackage{graphicx}\n\\usepackage[margin=1in]{geometry}\n\n\\title{Survey Title}\n\\author{Author Name}\n\\date{\\today}\n\n\\begin{document}\n\\maketitle\n\n\\section{Abstract}\n% TODO: Add content here.\n\n\\section{Introduction}\n% TODO: Add content here.\n\n\\section{Scope \\& Methodology}\n% TODO: Add content here.\n\n\\section{Taxonomy}\n% TODO: Add content here.\n\n\\section{Analysis of Approaches}\n% TODO: Add content here.\n\n\\section{Open Problems}\n% TODO: Add content here.\n\n\\section{Conclusion}\n% TODO: Add content here.\n\n\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}`,
  },
  {
    id: 'short_paper',
    label: 'Short Paper / Extended Abstract',
    description: 'Compact format for workshops or preliminary results.',
    sections: ['Abstract', 'Introduction', 'Approach', 'Results', 'Conclusion'],
    richTemplate: `# Abstract\nBriefly state the contribution.\n\n# Introduction\nMotivate the work concisely.\n\n# Approach\nDescribe the method or system.\n\n# Results\nPresent key findings.\n\n# Conclusion\nSummarize and outline future work.`,
    latexTemplate: `\\documentclass[10pt,twocolumn]{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{amsmath,amssymb}\n\\usepackage{graphicx}\n\\usepackage[margin=0.75in]{geometry}\n\n\\title{Short Paper Title}\n\\author{Author Name}\n\\date{}\n\n\\begin{document}\n\\maketitle\n\n\\section{Abstract}\n% TODO: Add content here.\n\n\\section{Introduction}\n% TODO: Add content here.\n\n\\section{Approach}\n% TODO: Add content here.\n\n\\section{Results}\n% TODO: Add content here.\n\n\\section{Conclusion}\n% TODO: Add content here.\n\n\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}`,
  },
]
