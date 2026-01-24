% acmart.cls - Compatible ACM style for ScholarHub
% ACM Master Article Template (for CHI, SIGCHI, etc.)

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{acmart}[2024/01/01 ACM Compatible Style]

% Format options
\DeclareOption{sigchi}{\def\acm@format{sigchi}}
\DeclareOption{sigconf}{\def\acm@format{sigconf}}
\DeclareOption{sigplan}{\def\acm@format{sigplan}}
\DeclareOption{acmsmall}{\def\acm@format{acmsmall}}
\DeclareOption{acmlarge}{\def\acm@format{acmlarge}}
\DeclareOption{acmtog}{\def\acm@format{acmtog}}
\DeclareOption{manuscript}{\def\acm@format{manuscript}}
\DeclareOption{screen}{}
\DeclareOption{review}{}
\DeclareOption{anonymous}{\def\acm@anonymous{}}
\DeclareOption{authorversion}{}
\DeclareOption{nonacm}{}
\DeclareOption{acmthm}{}
\DeclareOption{timestamp}{}
\DeclareOption*{\PackageWarning{acmart}{Unknown option '\CurrentOption'}}

\ExecuteOptions{sigconf}
\ProcessOptions\relax

% Base class
\LoadClass[10pt,twocolumn]{article}

% Required packages
\RequirePackage[margin=0.75in]{geometry}
\RequirePackage{times}
\RequirePackage{mathptmx}
\RequirePackage{fancyhdr}
\RequirePackage{graphicx}
\RequirePackage{amsmath}
\RequirePackage{amssymb}
\RequirePackage{natbib}
\RequirePackage{xcolor}
\RequirePackage{caption}

% Caption setup
\captionsetup{font=small,labelfont=bf}

% ACM colors
\definecolor{acmblue}{RGB}{0,0,128}

% Page style
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small ACM Conference}
\fancyhead[R]{\small\thepage}
\fancyfoot{}
\renewcommand{\headrulewidth}{0.4pt}

% ACM metadata commands
\def\acmConference#1#2#3{\def\@acmConference{#1}\def\@acmDate{#2}\def\@acmLocation{#3}}
\def\@acmConference{Conference}\def\@acmDate{Date}\def\@acmLocation{Location}
\def\acmYear#1{\def\@acmYear{#1}}
\def\@acmYear{2024}
\def\acmDOI#1{\def\@acmDOI{#1}}
\def\@acmDOI{}
\def\acmISBN#1{\def\@acmISBN{#1}}
\def\@acmISBN{}
\def\acmPrice#1{\def\@acmPrice{#1}}
\def\@acmPrice{}
\def\copyrightyear#1{\def\@copyrightyear{#1}}
\def\@copyrightyear{2024}
\def\setcopyright#1{}
\def\acmJournal#1{\def\@acmJournal{#1}}
\def\@acmJournal{}
\def\acmVolume#1{\def\@acmVolume{#1}}
\def\@acmVolume{}
\def\acmNumber#1{\def\@acmNumber{#1}}
\def\@acmNumber{}
\def\acmArticle#1{\def\@acmArticle{#1}}
\def\@acmArticle{}
\def\acmMonth#1{\def\@acmMonth{#1}}
\def\@acmMonth{}
\def\acmSubmissionID#1{}
\def\received#1{}

% Author handling
\newcounter{acm@author}
\def\author#1{%
  \stepcounter{acm@author}%
  \g@addto@macro\@author{#1\\}%
}
\def\authornote#1{}
\def\authornotemark[#1]{}
\def\affiliation#1{\g@addto@macro\@affiliation{#1\\}}
\def\@affiliation{}
\def\email#1{\texttt{#1}}
\def\orcid#1{}
\def\institution#1{#1}
\def\department#1{#1}
\def\streetaddress#1{#1}
\def\city#1{#1}
\def\state#1{#1}
\def\country#1{#1}
\def\postcode#1{#1}
\def\additionalaffiliation#1{}

% Title note
\def\titlenote#1{}
\def\subtitle#1{\def\@subtitle{#1}}
\def\@subtitle{}

% Title formatting
\def\@maketitle{%
  \newpage
  \null
  \vskip 1em%
  \begin{center}%
  \let \footnote \thanks
    {\LARGE\bfseries \@title \par}%
    \ifx\@subtitle\empty\else
      \vskip 0.5em%
      {\large \@subtitle \par}%
    \fi
    \vskip 1.5em%
    {\large \@author}%
    \vskip 0.5em%
    {\small \@affiliation}%
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
    {\bfseries ABSTRACT}%
  \end{center}%
  \quotation
}{\endquotation}

% CCS Concepts
\def\ccsdesc[#1]#2{\par\noindent\textbf{CCS Concepts:} \textbullet\ #2}
\newcommand{\keywords}[1]{\par\vskip 0.5em\noindent\textbf{Keywords:} #1\par\vskip 1em}

% ACM reference format
\def\acmBadgeL#1#2{}
\def\acmBadgeR#1#2{}

% teaser figure
\newenvironment{teaserfigure}{\begin{figure*}}{\end{figure*}}

% Acknowledgments
\newenvironment{acks}{\section*{Acknowledgments}}{}

% Print-only and screen-only
\newcommand{\printonly}[1]{#1}
\newcommand{\screenonly}[1]{}

% Description for accessibility
\newcommand{\Description}[1]{}

\endinput
