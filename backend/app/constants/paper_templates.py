"""Paper templates for AI-generated paper creation and conference formats."""

from typing import TypedDict, List


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
        "bib_style": "plain",
        "notes": "ACL-style two-column format. Max 8 pages + unlimited references."
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
        "bib_style": "plain",
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
        "bib_style": "plain",
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
        "bib_style": "unsrt",
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
        "bib_style": "unsrt",
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
    "apa": {
        "id": "apa",
        "name": "APA 7th Edition",
        "description": "APA 7th edition style for psychology, education, and social sciences",
        "preamble_example": r"""\documentclass[12pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{times}
\usepackage{geometry}
\geometry{letterpaper, margin=1in}
\usepackage{setspace}
\doublespacing
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{apacite}
\usepackage{authblk}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Department, University One}
\affil[2]{Department, University Two}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Department, University}",
        "sections": ["Abstract", "Introduction", "Literature Review", "Method", "Results", "Discussion", "Conclusion", "References"],
        "bib_style": "apacite",
        "notes": "APA 7th edition double-spaced format. 12pt Times New Roman, 1-inch margins. Uses apacite for author-date citations (\\citeA{} for narrative, \\cite{} for parenthetical)."
    },
    "chicago": {
        "id": "chicago",
        "name": "Chicago/Turabian",
        "description": "Chicago Manual of Style / Turabian format for humanities and social sciences",
        "preamble_example": r"""\documentclass[12pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{geometry}
\geometry{letterpaper, margin=1in}
\usepackage{setspace}
\doublespacing
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{authblk}
\usepackage{endnotes}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Department, University One}
\affil[2]{Department, University Two}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Department, University}",
        "sections": ["Introduction", "Literature Review", "Methodology", "Findings", "Discussion", "Conclusion", "Bibliography"],
        "bib_style": "plain",
        "notes": "Chicago/Turabian double-spaced format. 12pt font, 1-inch margins."
    },
    "plos": {
        "id": "plos",
        "name": "PLOS ONE",
        "description": "Single-column format for PLOS ONE open-access journal",
        "preamble_example": r"""\documentclass[10pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{geometry}
\geometry{a4paper, margin=1in}
\usepackage{lineno}
\linenumbers
\usepackage{hyperref}
\usepackage{authblk}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Department, Institution One, City, Country}
\affil[2]{Department, Institution Two, City, Country}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Department, Institution, City, Country}",
        "sections": ["Abstract", "Introduction", "Materials and Methods", "Results", "Discussion", "Conclusion", "Supporting Information"],
        "bib_style": "plos",
        "notes": "PLOS ONE single-column format with line numbers. No page limits. Open access. Use numbered references in order of appearance."
    },
    "springer-basic": {
        "id": "springer-basic",
        "name": "Springer Basic Journal",
        "description": "Single-column format for Springer journal submissions",
        "preamble_example": r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{geometry}
\geometry{a4paper, margin=1in}
\usepackage{authblk}
\usepackage{lineno}

\title{Your Paper Title}

\author[1]{First Author}
\author[2]{Second Author}
\affil[1]{Department, University One, City, Country \\ \texttt{first@email.com}}
\affil[2]{Department, University Two, City, Country \\ \texttt{second@email.com}}

\date{}

\begin{document}
\maketitle""",
        "author_format": r"\author[1]{Name} \affil[1]{Department, University, City, Country \\ \texttt{email}}",
        "sections": ["Abstract", "Introduction", "Related Work", "Methods", "Results", "Discussion", "Conclusion"],
        "bib_style": "plain",
        "notes": "Springer basic journal single-column format. Distinct from LNCS proceedings format. No strict page limits."
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
    {
        "id": "thesis",
        "label": "Thesis / Dissertation",
        "description": "Full-length thesis with chapters for graduate work.",
        "sections": ["Abstract", "Introduction", "Literature Review", "Methodology", "Results", "Discussion", "Conclusion", "References"],
        "richTemplate": """# Abstract\nSummarize the research objectives, methods, and findings.\n\n# Introduction\nIntroduce the research topic and state the problem.\n\n# Literature Review\nSurvey existing work and identify gaps.\n\n# Methodology\nDescribe the research design and procedures.\n\n# Results\nPresent the findings.\n\n# Discussion\nInterpret results and relate to prior work.\n\n# Conclusion\nSummarize contributions and future directions.\n\n# References""",
        "latexTemplate": r"""\documentclass[12pt]{report}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage[margin=1in]{geometry}

\title{Thesis Title}
\author{Author Name}
\date{\today}

\begin{document}
\maketitle
\tableofcontents

\chapter{Abstract}
% TODO: Add content here.

\chapter{Introduction}
% TODO: Add content here.

\chapter{Literature Review}
% TODO: Add content here.

\chapter{Methodology}
% TODO: Add content here.

\chapter{Results}
% TODO: Add content here.

\chapter{Discussion}
% TODO: Add content here.

\chapter{Conclusion}
% TODO: Add content here.

\bibliographystyle{plain}
\bibliography{references}
\end{document}""",
    },
    {
        "id": "technical_report",
        "label": "Technical Report",
        "description": "Detailed technical documentation of methods and results.",
        "sections": ["Abstract", "Introduction", "Background", "Technical Approach", "Implementation", "Evaluation", "Conclusion"],
        "richTemplate": """# Abstract\nBrief summary of the report.\n\n# Introduction\nState the purpose and scope.\n\n# Background\nProvide context and prior work.\n\n# Technical Approach\nDescribe the methodology in detail.\n\n# Implementation\nExplain the implementation specifics.\n\n# Evaluation\nPresent experiments, benchmarks, or analysis.\n\n# Conclusion\nSummarize findings and next steps.""",
        "latexTemplate": r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage[margin=1in]{geometry}

\title{Technical Report Title}
\author{Author Name}
\date{\today}

\begin{document}
\maketitle

\section{Abstract}
% TODO: Add content here.

\section{Introduction}
% TODO: Add content here.

\section{Background}
% TODO: Add content here.

\section{Technical Approach}
% TODO: Add content here.

\section{Implementation}
% TODO: Add content here.

\section{Evaluation}
% TODO: Add content here.

\section{Conclusion}
% TODO: Add content here.

\bibliographystyle{plain}
\bibliography{references}
\end{document}""",
    },
    {
        "id": "proposal",
        "label": "Research Proposal",
        "description": "Structured proposal for funding or project approval.",
        "sections": ["Abstract", "Introduction", "Problem Statement", "Objectives", "Literature Review", "Methodology", "Timeline", "Expected Outcomes", "Budget", "References"],
        "richTemplate": """# Abstract\nSummarize the proposed research.\n\n# Introduction\nIntroduce the research area and motivation.\n\n# Problem Statement\nDefine the problem to be addressed.\n\n# Objectives\nList specific aims and goals.\n\n# Literature Review\nReview relevant prior work.\n\n# Methodology\nDescribe the planned approach.\n\n# Timeline\nOutline milestones and schedule.\n\n# Expected Outcomes\nDescribe anticipated results and impact.\n\n# Budget\nItemize resource requirements.\n\n# References""",
        "latexTemplate": r"""\documentclass[12pt]{article}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage[margin=1in]{geometry}

\title{Research Proposal Title}
\author{Author Name}
\date{\today}

\begin{document}
\maketitle

\section{Abstract}
% TODO: Add content here.

\section{Introduction}
% TODO: Add content here.

\section{Problem Statement}
% TODO: Add content here.

\section{Objectives}
% TODO: Add content here.

\section{Literature Review}
% TODO: Add content here.

\section{Methodology}
% TODO: Add content here.

\section{Timeline}
% TODO: Add content here.

\section{Expected Outcomes}
% TODO: Add content here.

\section{Budget}
% TODO: Add content here.

\bibliographystyle{plain}
\bibliography{references}
\end{document}""",
    },
    {
        "id": "survey",
        "label": "Survey / SoK Paper",
        "description": "Systematization of knowledge across a research area.",
        "sections": ["Abstract", "Introduction", "Scope & Methodology", "Taxonomy", "Analysis of Approaches", "Open Problems", "Conclusion"],
        "richTemplate": """# Abstract\nSummarize the scope and findings of the survey.\n\n# Introduction\nMotivate the survey and state research questions.\n\n# Scope & Methodology\nDefine inclusion criteria and search strategy.\n\n# Taxonomy\nPresent the classification framework.\n\n# Analysis of Approaches\nCompare and contrast existing methods.\n\n# Open Problems\nIdentify unresolved challenges and gaps.\n\n# Conclusion\nSummarize insights and future directions.""",
        "latexTemplate": r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage[margin=1in]{geometry}

\title{Survey Title}
\author{Author Name}
\date{\today}

\begin{document}
\maketitle

\section{Abstract}
% TODO: Add content here.

\section{Introduction}
% TODO: Add content here.

\section{Scope \& Methodology}
% TODO: Add content here.

\section{Taxonomy}
% TODO: Add content here.

\section{Analysis of Approaches}
% TODO: Add content here.

\section{Open Problems}
% TODO: Add content here.

\section{Conclusion}
% TODO: Add content here.

\bibliographystyle{plain}
\bibliography{references}
\end{document}""",
    },
    {
        "id": "short_paper",
        "label": "Short Paper / Extended Abstract",
        "description": "Compact format for workshops or preliminary results.",
        "sections": ["Abstract", "Introduction", "Approach", "Results", "Conclusion"],
        "richTemplate": """# Abstract\nBriefly state the contribution.\n\n# Introduction\nMotivate the work concisely.\n\n# Approach\nDescribe the method or system.\n\n# Results\nPresent key findings.\n\n# Conclusion\nSummarize and outline future work.""",
        "latexTemplate": r"""\documentclass[10pt,twocolumn]{article}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage[margin=0.75in]{geometry}

\title{Short Paper Title}
\author{Author Name}
\date{}

\begin{document}
\maketitle

\section{Abstract}
% TODO: Add content here.

\section{Introduction}
% TODO: Add content here.

\section{Approach}
% TODO: Add content here.

\section{Results}
% TODO: Add content here.

\section{Conclusion}
% TODO: Add content here.

\bibliographystyle{plain}
\bibliography{references}
\end{document}""",
    },
]
