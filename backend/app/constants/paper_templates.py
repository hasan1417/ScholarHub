"""Paper templates for AI-generated paper creation."""

from typing import TypedDict, List


class PaperTemplate(TypedDict):
    id: str
    label: str
    description: str
    sections: List[str]
    richTemplate: str
    latexTemplate: str


PAPER_TEMPLATES: List[PaperTemplate] = [
    {
        "id": "research",
        "label": "Research Paper",
        "description": "IMRaD structure for reporting experiments and findings.",
        "sections": ["Abstract", "Introduction", "Methods", "Results", "Discussion", "Conclusion"],
        "richTemplate": """# Abstract

Summarize the research question, methodology, and key findings.

# Introduction
- Background
- Problem statement
- Objectives

# Methods
Describe your experimental or analytical approach.

# Results
Present the findings using tables or figures if needed.

# Discussion
Interpret the results and relate them to prior work.

# Conclusion
State the implications and future work.""",
        "latexTemplate": r"""\documentclass{article}
\begin{document}
\section{Abstract}
Summarize the research question, methodology, and key findings.
\section{Introduction}
\begin{itemize}
  \item Background
  \item Problem statement
  \item Objectives
\end{itemize}
\section{Methods}
Describe your experimental or analytical approach.
\section{Results}
Present the findings using tables or figures if needed.
\section{Discussion}
Interpret the results and relate them to prior work.
\section{Conclusion}
State the implications and future work.
\end{document}""",
    },
    {
        "id": "review",
        "label": "Literature Review",
        "description": "Compare prior work, identify gaps, and suggest directions.",
        "sections": ["Overview", "Key Themes", "Gap Analysis", "Future Work"],
        "richTemplate": """# Overview
Outline the scope and criteria of the review.

# Key Themes
## Theme 1
Discuss representative papers.
## Theme 2
Discuss representative papers.

# Gap Analysis
Highlight what remains unresolved.

# Future Work
Propose directions for future studies.""",
        "latexTemplate": r"""\documentclass{article}
\begin{document}
\section{Overview}
Outline the scope and criteria of the review.
\section{Key Themes}
\subsection{Theme 1}
Discuss representative papers.
\subsection{Theme 2}
Discuss representative papers.
\section{Gap Analysis}
Highlight what remains unresolved.
\section{Future Work}
Propose directions for future studies.
\end{document}""",
    },
    {
        "id": "case_study",
        "label": "Case Study",
        "description": "Deep dive into a single scenario or deployment.",
        "sections": ["Background", "Case Description", "Analysis", "Lessons Learned"],
        "richTemplate": """# Background
Frame the context and stakeholders.

# Case Description
Describe the setting and events chronologically.

# Analysis
Interpret the decisions and outcomes.

# Lessons Learned
List actionable insights and recommendations.""",
        "latexTemplate": r"""\documentclass{article}
\begin{document}
\section{Background}
Frame the context and stakeholders.
\section{Case Description}
Describe the setting and events chronologically.
\section{Analysis}
Interpret the decisions and outcomes.
\section{Lessons Learned}
List actionable insights and recommendations.
\end{document}""",
    },
]
