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
        "preamble_example": r"""\documentclass[11pt,a4paper,twocolumn]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{times}
\usepackage{latexsym}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{geometry}
\geometry{a4paper, margin=0.75in}
\usepackage{natbib}
\usepackage{authblk}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Affiliation One \\ \texttt{email1@domain.com}}
\affil[2]{Affiliation Two \\ \texttt{email2@domain.com}}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Affiliation \\ \texttt{email}}",
        "sections": ["Abstract", "Introduction", "Related Work", "Method", "Experiments", "Results", "Discussion", "Conclusion", "Limitations", "Ethics Statement"],
        "bib_style": "plainnat",
        "notes": "ACL-style two-column format. Max 8 pages + unlimited references. Uses natbib for citations (\\citep{} and \\citet{})."
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
        "preamble_example": r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{hyperref}
\usepackage{url}
\usepackage{booktabs}
\usepackage{amsfonts}
\usepackage{amsmath}
\usepackage{nicefrac}
\usepackage{microtype}
\usepackage{graphicx}
\usepackage{geometry}
\geometry{letterpaper, margin=1in}
\usepackage{authblk}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Department, University \\ \texttt{email1@domain.com}}
\affil[2]{Department, University \\ \texttt{email2@domain.com}}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Department, University \\ \texttt{email}}",
        "sections": ["Abstract", "Introduction", "Related Work", "Method", "Experiments", "Results", "Conclusion", "Broader Impact"],
        "bib_style": "plain",
        "notes": "NeurIPS-style single-column format. 9-page limit for main content + unlimited appendix/references."
    },
    "aaai": {
        "id": "aaai",
        "name": "AAAI Conference on Artificial Intelligence",
        "description": "Two-column format for AAAI conferences",
        "preamble_example": r"""\documentclass[letterpaper,twocolumn]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{times}
\usepackage{helvet}
\usepackage{courier}
\usepackage[hyphens]{url}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{natbib}
\usepackage{caption}
\usepackage{geometry}
\geometry{letterpaper, margin=0.75in}
\usepackage{authblk}
\frenchspacing

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{University One, first@email.com}
\affil[2]{University Two, second@email.com}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{University, email}",
        "sections": ["Abstract", "Introduction", "Related Work", "Approach", "Experiments", "Results", "Conclusion"],
        "bib_style": "plainnat",
        "notes": "AAAI-style two-column format. 7-page limit + 1 page references."
    },
    "icml": {
        "id": "icml",
        "name": "ICML (International Conference on Machine Learning)",
        "description": "Two-column format for ICML machine learning conference",
        "preamble_example": r"""\documentclass[10pt,twocolumn]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{mathtools}
\usepackage{amsthm}
\usepackage{hyperref}
\usepackage{url}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{geometry}
\geometry{letterpaper, margin=0.75in}
\usepackage{authblk}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Department, University One, City, Country \\ \texttt{email1@domain.com}}
\affil[2]{Department, University Two, City, Country \\ \texttt{email2@domain.com}}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Department, University, City, Country \\ \texttt{email}}",
        "sections": ["Abstract", "Introduction", "Related Work", "Preliminaries", "Method", "Experiments", "Results", "Conclusion"],
        "bib_style": "plain",
        "notes": "ICML-style two-column format. 8-page limit + unlimited references/appendix."
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
    "cvpr": {
        "id": "cvpr",
        "name": "CVPR (Computer Vision and Pattern Recognition)",
        "description": "Two-column format for CVPR computer vision conference",
        "preamble_example": r"""\documentclass[10pt,twocolumn,letterpaper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{times}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{geometry}
\geometry{letterpaper, margin=0.75in}
\usepackage{authblk}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Institution One \\ {\small\texttt{first@email.com}}}
\affil[2]{Institution Two \\ {\small\texttt{second@email.com}}}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Institution \\ \texttt{email}}",
        "sections": ["Abstract", "Introduction", "Related Work", "Method", "Experiments", "Results", "Conclusion"],
        "bib_style": "ieee",
        "notes": "CVPR-style two-column format. 8-page limit + unlimited references."
    },
    "iccv": {
        "id": "iccv",
        "name": "ICCV (International Conference on Computer Vision)",
        "description": "Two-column format for ICCV computer vision conference",
        "preamble_example": r"""\documentclass[10pt,twocolumn,letterpaper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{times}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{geometry}
\geometry{letterpaper, margin=0.75in}
\usepackage{authblk}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Institution One \\ {\small\texttt{first@email.com}}}
\affil[2]{Institution Two \\ {\small\texttt{second@email.com}}}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Institution \\ \texttt{email}}",
        "sections": ["Abstract", "Introduction", "Related Work", "Method", "Experiments", "Results", "Conclusion"],
        "bib_style": "ieee",
        "notes": "ICCV-style two-column format. 8-page limit + 2 pages refs."
    },
    "eccv": {
        "id": "eccv",
        "name": "ECCV (European Conference on Computer Vision)",
        "description": "Single-column LNCS-style format for ECCV",
        "preamble_example": r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{geometry}
\geometry{a4paper, margin=1in}
\usepackage{authblk}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Institution One}
\affil[2]{Institution Two}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Institution}",
        "sections": ["Abstract", "Introduction", "Related Work", "Method", "Experiments", "Conclusion"],
        "bib_style": "plain",
        "notes": "ECCV-style single-column format (LNCS-like). 14-page limit + refs."
    },
    "iclr": {
        "id": "iclr",
        "name": "ICLR (International Conference on Learning Representations)",
        "description": "Single-column format for ICLR machine learning conference",
        "preamble_example": r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{times}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{hyperref}
\usepackage{url}
\usepackage{geometry}
\geometry{letterpaper, margin=1in}
\usepackage{authblk}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Department, University \\ \texttt{first@email.com}}
\affil[2]{Department, University \\ \texttt{second@email.com}}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Dept, Univ \\ \texttt{email}}",
        "sections": ["Abstract", "Introduction", "Related Work", "Method", "Experiments", "Results", "Conclusion", "Reproducibility Statement"],
        "bib_style": "plain",
        "notes": "ICLR-style single-column format. 9-page limit + unlimited appendix/refs."
    },
    "jmlr": {
        "id": "jmlr",
        "name": "JMLR (Journal of Machine Learning Research)",
        "description": "Single-column format for JMLR journal",
        "preamble_example": r"""\documentclass[twoside,11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{geometry}
\geometry{letterpaper, margin=1in}
\usepackage{authblk}
\usepackage{fancyhdr}
\pagestyle{fancy}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Department, University \\ \texttt{first@email.com}}
\affil[2]{Department, University \\ \texttt{second@email.com}}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Dept, Univ \\ \texttt{email}}",
        "sections": ["Abstract", "Introduction", "Related Work", "Problem Setup", "Method", "Theoretical Analysis", "Experiments", "Conclusion"],
        "bib_style": "plainnat",
        "notes": "JMLR-style single-column journal format. No page limit."
    },
    "ijcai": {
        "id": "ijcai",
        "name": "IJCAI (International Joint Conference on AI)",
        "description": "Two-column format for IJCAI conference",
        "preamble_example": r"""\documentclass[10pt,twocolumn]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{times}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{geometry}
\geometry{letterpaper, margin=0.75in}
\usepackage{authblk}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Institution One \\ first@email.com}
\affil[2]{Institution Two \\ second@email.com}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Institution \\ email}",
        "sections": ["Abstract", "Introduction", "Related Work", "Background", "Approach", "Experiments", "Conclusion"],
        "bib_style": "plain",
        "notes": "IJCAI-style two-column format. 7-page limit + 2 pages refs."
    },
    "kdd": {
        "id": "kdd",
        "name": "KDD (ACM SIGKDD)",
        "description": "ACM two-column format for KDD data mining conference",
        "preamble_example": r"""\documentclass[10pt,twocolumn]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{geometry}
\geometry{letterpaper, margin=0.75in}
\usepackage{authblk}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{University One, City, Country \\ first@email.com}
\affil[2]{University Two, City, Country \\ second@email.com}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Univ, City, Country \\ email}",
        "sections": ["Abstract", "Introduction", "Related Work", "Problem Definition", "Methodology", "Experiments", "Results", "Conclusion"],
        "bib_style": "plain",
        "notes": "KDD-style ACM two-column format. 9-page limit + refs."
    },
    "lncs": {
        "id": "lncs",
        "name": "LNCS (Springer Lecture Notes)",
        "description": "Single-column Springer LNCS format for conference proceedings",
        "preamble_example": r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{geometry}
\geometry{a4paper, margin=1in}
\usepackage{authblk}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Institution One, City, Country \\ \texttt{first@email.com}}
\affil[2]{Institution Two, City, Country \\ \texttt{second@email.com}}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Institution, City, Country \\ \texttt{email}}",
        "sections": ["Abstract", "Introduction", "Related Work", "Approach", "Evaluation", "Conclusion"],
        "bib_style": "plain",
        "notes": "LNCS-style single-column format. Typically 12-16 pages."
    },
    "elsevier": {
        "id": "elsevier",
        "name": "Elsevier Journal",
        "description": "Single-column format for Elsevier journals",
        "preamble_example": r"""\documentclass[preprint,12pt]{elsarticle}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{lineno}

\journal{Journal Name}

\begin{document}

\begin{frontmatter}

\title{Your Paper Title}

\author[inst1]{First Author}
\ead{first@email.com}
\author[inst2]{Second Author}
\ead{second@email.com}

\address[inst1]{Institution One, City, Country}
\address[inst2]{Institution Two, City, Country}

\begin{abstract}
Your abstract here.
\end{abstract}

\begin{keyword}
keyword1 \sep keyword2 \sep keyword3
\end{keyword}

\end{frontmatter}""",
        "author_format": r"\author[label]{Name} \ead{email} \address[label]{Institution}",
        "sections": ["Abstract", "Introduction", "Materials and Methods", "Results", "Discussion", "Conclusion"],
        "bib_style": "elsarticle-num",
        "notes": "Single-column preprint format. Uses elsarticle.cls. Use frontmatter environment for title/authors."
    },
    "nature": {
        "id": "nature",
        "name": "Nature",
        "description": "Format for Nature journal submissions",
        "preamble_example": r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{geometry}
\geometry{a4paper, margin=1in}
\usepackage{lineno}
\usepackage{setspace}
\onehalfspacing

\title{Your Paper Title}

\author{First Author$^{1}$ \& Second Author$^{2}$\\[1ex]
\small $^{1}$Institution One, City, Country\\
\small $^{2}$Institution Two, City, Country}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author{Name$^{1}$ \& Name$^{2}$} with numbered affiliations below",
        "sections": ["Abstract", "Introduction", "Results", "Discussion", "Methods", "References"],
        "bib_style": "unsrtnat",
        "notes": "Nature-style single-column format. Methods section at end. Very concise abstract (<150 words). Line numbers recommended for submission."
    },
    "pnas": {
        "id": "pnas",
        "name": "PNAS",
        "description": "Two-column format for PNAS journal",
        "preamble_example": r"""\documentclass[9pt,twocolumn]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{geometry}
\geometry{letterpaper, margin=0.75in}
\usepackage{hyperref}

\title{Your Paper Title}

\author{First Author$^{1}$, Second Author$^{2}$}

\date{}

\begin{document}
\maketitle

\noindent$^{1}$Institution One, City, Country\\
$^{2}$Institution Two, City, Country

""",
        "author_format": r"\author{Name$^{1}$, Name$^{2}$} with affiliations after \maketitle",
        "sections": ["Abstract", "Significance", "Introduction", "Results", "Discussion", "Materials and Methods"],
        "bib_style": "unsrtnat",
        "notes": "PNAS-style two-column format using standard packages. Include Significance statement after abstract. 6-page limit for most articles."
    },
    "acm": {
        "id": "acm",
        "name": "ACM (CHI, SIGCHI, etc.)",
        "description": "ACM format for CHI, SIGCHI, and other ACM conferences",
        "preamble_example": r"""\documentclass[10pt,twocolumn]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{geometry}
\geometry{letterpaper, margin=0.75in}
\usepackage{authblk}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{University One, City, Country \\ first@email.com}
\affil[2]{University Two, City, Country \\ second@email.com}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Univ, City, Country \\ email}",
        "sections": ["Abstract", "Introduction", "Related Work", "System Design", "User Study", "Results", "Discussion", "Conclusion"],
        "bib_style": "plain",
        "notes": "ACM-style two-column format for CHI, SIGCHI, and other ACM conferences."
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
