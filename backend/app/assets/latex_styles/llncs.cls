% llncs.cls - Compatible LNCS (Springer) style for ScholarHub
% Lecture Notes in Computer Science

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{llncs}[2024/01/01 LNCS Compatible Style]

% Options
\DeclareOption{runningheads}{\def\lncs@runningheads{}}
\DeclareOption{a4paper}{\PassOptionsToClass{a4paper}{article}}
\DeclareOption{oribibl}{}
\DeclareOption*{\PackageWarning{llncs}{Unknown option '\CurrentOption'}}

\ProcessOptions\relax

% Base class
\LoadClass[10pt]{article}

% Required packages
\RequirePackage[margin=1in]{geometry}
\RequirePackage{times}
\RequirePackage{mathptmx}
\RequirePackage{fancyhdr}
\RequirePackage{graphicx}
\RequirePackage{amsmath}
\RequirePackage{amssymb}

% Page style
\pagestyle{fancy}
\fancyhf{}
\fancyhead[C]{\small Lecture Notes in Computer Science}
\fancyfoot[C]{\thepage}
\renewcommand{\headrulewidth}{0pt}

% Institute command
\def\institute#1{\def\@institute{#1}}
\def\@institute{}
\def\inst#1{\textsuperscript{#1}}

% Email and URL
\def\email#1{\texttt{#1}}
\def\url#1{\texttt{#1}}

% Running heads
\def\titlerunning#1{\def\@titlerunning{#1}}
\def\@titlerunning{}
\def\authorrunning#1{\def\@authorrunning{#1}}
\def\@authorrunning{}

% Title formatting
\def\@maketitle{%
  \newpage
  \null
  \vskip 2em%
  \begin{center}%
  \let \footnote \thanks
    {\LARGE\bfseries \@title \par}%
    \vskip 1.5em%
    {\large
      \lineskip .5em%
      \begin{tabular}[t]{c}%
        \@author
      \end{tabular}\par}%
    \vskip 0.5em%
    {\small \@institute \par}%
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
    {\bfseries Abstract.\space}%
  \end{center}%
  \quotation
}{\endquotation}

% Keywords
\newcommand{\keywords}[1]{\par\vskip 0.5em\noindent\textbf{Keywords:} #1}

% Acknowledgments
\newenvironment{acknowledgement}{\section*{Acknowledgements}}{}

% Springer theorem environments
\newtheorem{theorem}{Theorem}
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{proposition}[theorem]{Proposition}
\newtheorem{corollary}[theorem]{Corollary}
\newtheorem{definition}{Definition}
\newtheorem{example}{Example}
\newtheorem{remark}{Remark}

\endinput
