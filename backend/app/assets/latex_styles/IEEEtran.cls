% IEEEtran.cls - Compatible IEEE style for ScholarHub
% Simplified version based on IEEE formatting guidelines

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{IEEEtran}[2024/01/01 IEEE Transaction Compatible Style]

% Options
\DeclareOption{conference}{\def\ieee@conference{}}
\DeclareOption{journal}{\def\ieee@journal{}}
\DeclareOption{technote}{\def\ieee@technote{}}
\DeclareOption{letterpaper}{}
\DeclareOption{a4paper}{\PassOptionsToClass{a4paper}{article}}
\DeclareOption{10pt}{\PassOptionsToClass{10pt}{article}}
\DeclareOption{11pt}{\PassOptionsToClass{11pt}{article}}
\DeclareOption{12pt}{\PassOptionsToClass{12pt}{article}}
\DeclareOption{onecolumn}{\def\ieee@onecolumn{}}
\DeclareOption{twocolumn}{}
\DeclareOption{draft}{\PassOptionsToClass{draft}{article}}
\DeclareOption{final}{\PassOptionsToClass{final}{article}}
\DeclareOption*{\PackageWarning{IEEEtran}{Unknown option '\CurrentOption'}}

\ExecuteOptions{letterpaper,10pt,twocolumn,final}
\ProcessOptions\relax

% Base class
\LoadClass[twocolumn]{article}

% Required packages
\RequirePackage[margin=0.75in,top=0.75in,bottom=1in,columnsep=0.25in]{geometry}
\RequirePackage{times}
\RequirePackage{mathptmx}
\RequirePackage{fancyhdr}
\RequirePackage{graphicx}
\RequirePackage{amsmath}
\RequirePackage{array}
\RequirePackage{caption}

% Caption setup for IEEE style
\captionsetup{font=footnotesize,labelfont=bf,labelsep=period}
\captionsetup[table]{position=top}

% Page style
\pagestyle{plain}

% IEEE author block commands
\newcounter{IEEE@author@count}
\newcommand{\IEEEauthorblockN}[1]{%
  \stepcounter{IEEE@author@count}%
  {\large\bfseries #1}\\%
}
\newcommand{\IEEEauthorblockA}[1]{%
  {\normalsize\itshape #1}\\[0.5em]%
}

% Simple author and affiliation storage
\def\@IEEEauthors{}
\renewcommand{\author}[1]{\def\@IEEEauthors{#1}}

% Title formatting
\def\@maketitle{%
  \newpage
  \null
  \vskip 1em%
  \begin{center}%
    {\LARGE\bfseries \@title \par}%
    \vskip 1.5em%
    {\large \@IEEEauthors \par}%
    \vskip 1em%
  \end{center}%
  \par
  \vskip 1.5em%
}

% Abstract formatting - IEEE style
\renewenvironment{abstract}{%
  \small
  \begin{center}%
    {\bfseries\textit{Abstract}---\ignorespaces}%
  \end{center}%
  \itshape
  \par
}{%
  \par
  \vskip 1em%
}

% Keywords command
\newcommand{\IEEEkeywords}[1]{%
  \par\vskip 0.5em%
  \noindent\textbf{\textit{Index Terms}---}#1%
  \par\vskip 1em%
}
\let\keywords\IEEEkeywords

% Section formatting - IEEE uses Roman numerals
\renewcommand\thesection{\Roman{section}}
\renewcommand\thesubsection{\Alph{subsection}}

\renewcommand\section{\@startsection {section}{1}{\z@}%
  {-3.5ex \@plus -1ex \@minus -.2ex}%
  {2.3ex \@plus.2ex}%
  {\normalfont\large\bfseries\centering}}

\renewcommand\subsection{\@startsection{subsection}{2}{\z@}%
  {-3.25ex\@plus -1ex \@minus -.2ex}%
  {1.5ex \@plus .2ex}%
  {\normalfont\normalsize\itshape}}

\renewcommand\subsubsection{\@startsection{subsubsection}{3}{\z@}%
  {-3.25ex\@plus -1ex \@minus -.2ex}%
  {1.5ex \@plus .2ex}%
  {\normalfont\normalsize\itshape}}

% IEEE proof environment
\newenvironment{IEEEproof}[1][Proof]{%
  \par\noindent\textit{#1:}\ \ignorespaces
}{%
  \hfill$\blacksquare$\par
}

% IEEE itemize/enumerate adjustments
\setlength{\IEEElabelindent}{0pt}
\newlength{\IEEElabelindent}

% IEEE biography - simplified
\newenvironment{IEEEbiography}[2][]{%
  \par\vskip 1em%
  \noindent\textbf{#2}%
  \if\relax#1\relax\else\ \includegraphics[width=1in]{#1}\fi%
  \ %
}{\par}

\newenvironment{IEEEbiographynophoto}[1]{%
  \par\vskip 1em%
  \noindent\textbf{#1}\ %
}{\par}

% Acknowledgment
\newcommand{\IEEEtriggeratref}[1]{}
\newcommand{\IEEEpeerreviewmaketitle}{\maketitle}

% PARstart for drop caps (simplified - just bold first letter)
\newcommand{\IEEEPARstart}[2]{\noindent\textbf{#1}#2}

% Bibliography style
\bibliographystyle{IEEEtran}

\endinput
