"""Tests for deterministic_converter module."""

import pytest

from app.services.deterministic_converter import (
    extract_latex_title,
    deterministic_preamble_convert,
)


MINIMAL_DOC = r"""\documentclass{article}
\usepackage{graphicx}

\title{My Great Paper}
\author{Jane Doe}

\begin{document}
\maketitle

\section{Introduction}
Hello world.

\end{document}
"""


class TestExtractLatexTitle:
    def test_simple_title(self):
        assert extract_latex_title(MINIMAL_DOC) == "My Great Paper"

    def test_nested_braces(self):
        source = r"\title{A Study on {Deep} Learning}"
        assert extract_latex_title(source) == r"A Study on {Deep} Learning"

    def test_missing_title(self):
        source = r"\documentclass{article}\begin{document}\end{document}"
        assert extract_latex_title(source) is None

    def test_unmatched_braces(self):
        source = r"\title{Broken {"
        assert extract_latex_title(source) is None


class TestDeterministicPreambleConvert:
    def test_normal_conversion(self):
        result = deterministic_preamble_convert(MINIMAL_DOC, "acl")
        assert result is not None
        assert "<<<EDIT>>>" in result
        assert "<<<LINES>>>" in result
        assert "1-8" in result  # \maketitle is on line 8
        assert "My Great Paper" in result
        assert "ACL" in result
        assert "Your Paper Title" not in result

    def test_nested_braces_title(self):
        source = r"""\documentclass{article}
\title{A Study on {Deep} Learning}
\author{Jane}
\begin{document}
\maketitle
\section{Intro}
\end{document}
"""
        result = deterministic_preamble_convert(source, "acl")
        assert result is not None
        assert "A Study on {Deep} Learning" in result

    def test_missing_maketitle(self):
        source = r"""\documentclass{article}
\title{Test}
\begin{document}
\section{Intro}
\end{document}
"""
        result = deterministic_preamble_convert(source, "acl")
        assert result is None

    def test_missing_title(self):
        source = r"""\documentclass{article}
\begin{document}
\maketitle
\end{document}
"""
        result = deterministic_preamble_convert(source, "acl")
        assert result is None

    def test_truncated_source(self):
        source = r"""\documentclass{article}
\title{Test}
\begin{document}
\maketitle
\section{Intro}
"""
        result = deterministic_preamble_convert(source, "acl")
        assert result is None

    def test_unknown_template(self):
        result = deterministic_preamble_convert(MINIMAL_DOC, "nonexistent")
        assert result is None
