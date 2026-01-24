"""Paper templates for AI-generated paper creation and conference formats."""

from typing import TypedDict, List, Optional


class PaperTemplate(TypedDict):
    id: str
    label: str
    description: str
    sections: List[str]
    richTemplate: str
    latexTemplate: str


class ConferenceTemplate(TypedDict):
    id: str
    name: str
    description: str
    preamble_example: str
    author_format: str
    sections: List[str]
    bib_style: str
    notes: str


# Conference/journal templates for format conversion
CONFERENCE_TEMPLATES: dict[str, ConferenceTemplate] = {
    "acl": {
        "id": "acl",
        "name": "ACL (Association for Computational Linguistics)",
        "description": "Two-column format for ACL, EMNLP, NAACL, and related NLP conferences",
        "preamble_example": r"""\documentclass[11pt,a4paper]{article}
\usepackage[hyperref]{acl2023}
\usepackage{times}
\usepackage{latexsym}
\usepackage{graphicx}
\usepackage{amsmath}
\aclfinalcopy

\title{Your Paper Title}

\author{First Author \\
  Affiliation / Address line 1 \\
  \texttt{email@domain.com} \And
  Second Author \\
  Affiliation / Address line 1 \\
  \texttt{email@domain.com}}

\begin{document}
\maketitle""",
        "author_format": r"\author{Name1 \\ Affiliation \\ \texttt{email} \And Name2 \\ Affiliation \\ \texttt{email}}",
        "sections": ["Abstract", "Introduction", "Related Work", "Method", "Experiments", "Results", "Discussion", "Conclusion", "Limitations", "Ethics Statement"],
        "bib_style": "acl_natbib",
        "notes": "Two-column format, uses \\And for multiple authors, natbib citations with \\citep{} and \\citet{}. Max 8 pages + unlimited references. Requires acl2023.sty."
    },
    "ieee": {
        "id": "ieee",
        "name": "IEEE Conference",
        "description": "Standard IEEE conference two-column format",
        "preamble_example": r"""\documentclass[conference]{IEEEtran}
\usepackage{cite}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{algorithmic}
\usepackage{graphicx}
\usepackage{textcomp}
\usepackage{xcolor}

\begin{document}

\title{Your Paper Title}

\author{\IEEEauthorblockN{First Author}
\IEEEauthorblockA{\textit{Department} \\
\textit{University}\\
City, Country \\
email@domain.com}
\and
\IEEEauthorblockN{Second Author}
\IEEEauthorblockA{\textit{Department} \\
\textit{University}\\
City, Country \\
email@domain.com}}

\maketitle""",
        "author_format": r"\author{\IEEEauthorblockN{Name}\IEEEauthorblockA{\textit{Dept} \\ \textit{Univ} \\ email}}",
        "sections": ["Abstract", "Introduction", "Related Work", "Methodology", "Experimental Setup", "Results", "Discussion", "Conclusion"],
        "bib_style": "IEEEtran",
        "notes": "Two-column format, uses IEEEauthorblockN/A for authors, numeric citations with \\cite{}. Uses IEEEtran document class."
    },
    "neurips": {
        "id": "neurips",
        "name": "NeurIPS (Neural Information Processing Systems)",
        "description": "Single-column format for NeurIPS machine learning conference",
        "preamble_example": r"""\documentclass{article}
\usepackage[final]{neurips_2024}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{hyperref}
\usepackage{url}
\usepackage{booktabs}
\usepackage{amsfonts}
\usepackage{nicefrac}
\usepackage{microtype}
\usepackage{graphicx}

\title{Your Paper Title}

\author{
  First Author \\
  Department \\
  University \\
  \texttt{email@domain.com} \\
  \And
  Second Author \\
  Department \\
  University \\
  \texttt{email@domain.com}
}

\begin{document}
\maketitle""",
        "author_format": r"\author{Name \\ Department \\ University \\ \texttt{email}}",
        "sections": ["Abstract", "Introduction", "Related Work", "Method", "Experiments", "Results", "Conclusion", "Broader Impact"],
        "bib_style": "plain",
        "notes": "Single-column format, simple author format with \\And separator, 9-page limit for main content + unlimited appendix/references. Requires neurips_2024.sty."
    },
    "aaai": {
        "id": "aaai",
        "name": "AAAI Conference on Artificial Intelligence",
        "description": "Two-column format for AAAI conferences",
        "preamble_example": r"""\documentclass[letterpaper]{article}
\usepackage{aaai24}
\usepackage{times}
\usepackage{helvet}
\usepackage{courier}
\usepackage[hyphens]{url}
\usepackage{graphicx}
\urlstyle{rm}
\usepackage{natbib}
\usepackage{caption}
\frenchspacing
\setlength{\pdfpagewidth}{8.5in}
\setlength{\pdfpageheight}{11in}

\title{Your Paper Title}
\author{
    First Author\textsuperscript{\rm 1},
    Second Author\textsuperscript{\rm 2}
}
\affiliations{
    \textsuperscript{\rm 1}University One\\
    \textsuperscript{\rm 2}University Two\\
    first@email.com, second@email.com
}

\begin{document}
\maketitle""",
        "author_format": r"\author{Name1\textsuperscript{\rm 1}, Name2\textsuperscript{\rm 2}} with separate \affiliations{}",
        "sections": ["Abstract", "Introduction", "Related Work", "Approach", "Experiments", "Results", "Conclusion"],
        "bib_style": "aaai24",
        "notes": "Two-column format, uses superscript numbers with separate \\affiliations{} block, 7-page limit + 1 page references. Requires aaai24.sty."
    },
    "icml": {
        "id": "icml",
        "name": "ICML (International Conference on Machine Learning)",
        "description": "Two-column format for ICML machine learning conference",
        "preamble_example": r"""\documentclass{article}
\usepackage{icml2024}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{mathtools}
\usepackage{amsthm}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{hyperref}
\usepackage{url}
\usepackage{booktabs}
\usepackage{graphicx}

\icmltitlerunning{Short Title for Header}

\begin{document}

\twocolumn[
\icmltitle{Your Full Paper Title}

\icmlsetsymbol{equal}{*}

\begin{icmlauthorlist}
\icmlauthor{First Author}{univ1}
\icmlauthor{Second Author}{univ2}
\end{icmlauthorlist}

\icmlaffiliation{univ1}{Department, University One, City, Country}
\icmlaffiliation{univ2}{Department, University Two, City, Country}

\icmlcorrespondingauthor{First Author}{email@domain.com}

\icmlkeywords{Machine Learning, ICML}

\vskip 0.3in
]

\printAffiliationsAndNotice{}""",
        "author_format": r"\begin{icmlauthorlist}\icmlauthor{Name}{affil}\end{icmlauthorlist} with \icmlaffiliation{}",
        "sections": ["Abstract", "Introduction", "Related Work", "Preliminaries", "Method", "Experiments", "Results", "Conclusion"],
        "bib_style": "icml2024",
        "notes": "Two-column format, uses icmlauthorlist environment, 8-page limit + unlimited references/appendix. Requires icml2024.sty."
    },
    "generic": {
        "id": "generic",
        "name": "Generic Article",
        "description": "Simple single-column article format, universally compatible",
        "preamble_example": r"""\documentclass[12pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{natbib}

\title{Your Paper Title}
\author{First Author\thanks{email@domain.com} \and Second Author}
\date{\today}

\begin{document}
\maketitle""",
        "author_format": r"\author{Name1\thanks{email} \and Name2}",
        "sections": ["Abstract", "Introduction", "Methods", "Results", "Discussion", "Conclusion"],
        "bib_style": "plain",
        "notes": "Single-column format, simple \\author{} with \\and separator, no page limits. Works with standard LaTeX installation."
    },
}


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
