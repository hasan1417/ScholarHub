% elsarticle.cls - Compatible Elsevier style for ScholarHub
% Elsevier journal articles

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{elsarticle}[2024/01/01 Elsevier Compatible Style]

% Options
\DeclareOption{preprint}{\def\els@preprint{}}
\DeclareOption{review}{\def\els@review{}}
\DeclareOption{1p}{\def\els@onep{}}
\DeclareOption{3p}{\def\els@threep{}}
\DeclareOption{5p}{\def\els@fivep{}}
\DeclareOption{authoryear}{\def\els@authoryear{}}
\DeclareOption{number}{\def\els@number{}}
\DeclareOption{sort&compress}{}
\DeclareOption{longtitle}{}
\DeclareOption*{\PackageWarning{elsarticle}{Unknown option '\CurrentOption'}}

\ExecuteOptions{preprint,authoryear}
\ProcessOptions\relax

% Base class
\LoadClass[11pt]{article}

% Required packages
\RequirePackage[margin=1in]{geometry}
\RequirePackage{times}
\RequirePackage{fancyhdr}
\RequirePackage{graphicx}
\RequirePackage{amsmath}
\RequirePackage{amssymb}
\RequirePackage{natbib}
\RequirePackage{lineno}

% Page style
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small\@journalname}
\fancyhead[R]{\small\thepage}
\fancyfoot{}
\renewcommand{\headrulewidth}{0.4pt}

% Journal name
\def\journalname#1{\def\@journalname{#1}}
\def\@journalname{Journal Name}

% Elsevier frontmatter environment
\newenvironment{frontmatter}{%
  \global\@topnum\z@
  \@afterindentfalse
  \@afterheading
}{}

% Author and affiliation
\newcounter{els@author}
\renewcommand{\author}[2][]{%
  \stepcounter{els@author}%
  \ifx\\#1\\%
    \g@addto@macro\@author{#2\quad}%
  \else%
    \g@addto@macro\@author{#2\textsuperscript{#1}\quad}%
  \fi%
}
\newcommand{\ead}[1]{\def\@ead{#1}}
\def\@ead{}

\newcommand{\address}[2][]{%
  \ifx\\#1\\%
    \g@addto@macro\@address{#2\\}%
  \else%
    \g@addto@macro\@address{\textsuperscript{#1}#2\\}%
  \fi%
}
\def\@address{}

\def\cortext[#1]#2{}
\def\fntext[#1]#2{}
\def\tnotetext[#1]#2{}

% Title formatting
\def\@maketitle{%
  \newpage
  \null
  \vskip 2em%
  \begin{center}%
  \let \footnote \thanks
    {\LARGE\bfseries \@title \par}%
    \vskip 1.5em%
    {\large \@author \par}%
    \vskip 0.5em%
    {\small \@address \par}%
    \vskip 1em%
  \end{center}%
  \par
  \vskip 1.5em}

% Section formatting
\renewcommand\section{\@startsection {section}{1}{\z@}%
  {-3.5ex \@plus -1ex \@minus -.2ex}%
  {2.3ex \@plus.2ex}%
  {\normalfont\large\bfseries}}

\renewcommand\subsection{\@startsection{subsection}{2}{\z@}%
  {-3.25ex\@plus -1ex \@minus -.2ex}%
  {1.5ex \@plus .2ex}%
  {\normalfont\normalsize\bfseries}}

% Abstract
\renewenvironment{abstract}{%
  \small
  \begin{center}%
    {\bfseries Abstract}%
  \end{center}%
  \begin{quotation}
}{%
  \end{quotation}
}

% Keywords
\def\keyword#1{\def\@keyword{#1}}
\def\@keyword{}
\newcommand{\keywords}[1]{\par\vskip 0.5em\noindent\textit{Keywords:} #1\par\vskip 1em}

% Highlights environment
\newenvironment{highlights}{%
  \par\vskip 1em%
  \noindent\textbf{Highlights}%
  \begin{itemize}
}{\end{itemize}}

% Graphical abstract
\newenvironment{graphicalabstract}{}{}

\endinput
