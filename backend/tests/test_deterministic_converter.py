"""Tests for deterministic_converter module."""

import pytest

from app.services.deterministic_converter import (
    ConvertResult,
    extract_latex_title,
    deterministic_full_convert,
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


class TestDeterministicFullConvert:
    """Updated from TestDeterministicPreambleConvert for new return type."""

    def test_normal_conversion(self):
        result = deterministic_full_convert(MINIMAL_DOC, "acl")
        assert result.kind == "edits"
        assert "<<<EDIT>>>" in result.edits
        assert "<<<LINES>>>" in result.edits
        assert "1-8" in result.edits  # \maketitle is on line 8
        assert "My Great Paper" in result.edits
        assert "ACL" in result.edits
        assert "Your Paper Title" not in result.edits

    def test_nested_braces_title(self):
        source = r"""\documentclass{article}
\title{A Study on {Deep} Learning}
\author{Jane}
\begin{document}
\maketitle
\section{Intro}
\end{document}
"""
        result = deterministic_full_convert(source, "acl")
        assert result.kind == "edits"
        assert "A Study on {Deep} Learning" in result.edits

    def test_missing_maketitle(self):
        source = r"""\documentclass{article}
\title{Test}
\begin{document}
\section{Intro}
\end{document}
"""
        result = deterministic_full_convert(source, "acl")
        assert result.kind == "fallback"
        assert result.fallback_reason == "missing_maketitle"

    def test_missing_title(self):
        source = r"""\documentclass{article}
\begin{document}
\maketitle
\end{document}
"""
        result = deterministic_full_convert(source, "acl")
        assert result.kind == "fallback"
        assert result.fallback_reason == "missing_title"

    def test_truncated_source(self):
        source = r"""\documentclass{article}
\title{Test}
\begin{document}
\maketitle
\section{Intro}
"""
        result = deterministic_full_convert(source, "acl")
        assert result.kind == "fallback"
        assert result.fallback_reason == "truncated"

    def test_unknown_template(self):
        result = deterministic_full_convert(MINIMAL_DOC, "nonexistent")
        assert result.kind == "fallback"
        assert result.fallback_reason == "unknown_template"


class TestBodyEdits:
    """Tests for body-level edit rules."""

    def test_ieee_keywords_converted(self):
        source = r"""\documentclass[conference]{IEEEtran}
\title{My Paper}
\author{Author}
\begin{document}
\maketitle

\begin{IEEEkeywords}
deep learning, NLP
\end{IEEEkeywords}

\bibliographystyle{IEEEtran}
\end{document}
"""
        result = deterministic_full_convert(source, "acl")
        assert result.kind == "edits"
        assert r"\begin{keywords}" in result.edits
        assert r"\end{keywords}" in result.edits

    def test_bibliographystyle_converted(self):
        source = r"""\documentclass[conference]{IEEEtran}
\title{My Paper}
\author{Author}
\begin{document}
\maketitle

\section{Intro}
Hello.

\bibliographystyle{IEEEtran}
\end{document}
"""
        result = deterministic_full_convert(source, "acl")
        assert result.kind == "edits"
        assert r"\bibliographystyle{plain}" in result.edits

    def test_no_body_constructs(self):
        """When doc has no IEEEkeywords or bibliographystyle, only preamble edit returned."""
        result = deterministic_full_convert(MINIMAL_DOC, "acl")
        assert result.kind == "edits"
        assert "IEEEkeywords" not in result.edits
        assert "bibliographystyle" not in result.edits
        # Should have exactly one edit block (preamble)
        assert result.edits.count("<<<EDIT>>>") == 1

    def test_commented_bibliographystyle_not_modified(self):
        source = r"""\documentclass{article}
\title{My Paper}
\author{Author}
\begin{document}
\maketitle

\section{Intro}
% \bibliographystyle{IEEEtran}
\bibliographystyle{plain}

\end{document}
"""
        result = deterministic_full_convert(source, "acl")
        # The commented line should be skipped, and the active one is already "plain"
        assert "bibliographystyle" not in result.edits or "Update bibliographystyle" not in result.edits

    def test_multiple_bibliographystyle_only_first_active(self):
        source = r"""\documentclass{article}
\title{My Paper}
\author{Author}
\begin{document}
\maketitle

% \bibliographystyle{alpha}
\bibliographystyle{IEEEtran}
\bibliographystyle{unsrt}

\end{document}
"""
        result = deterministic_full_convert(source, "acl")
        assert result.kind == "edits"
        # Only the first active one (IEEEtran) should be edited to plain
        bib_edits = [line for line in result.edits.split("\n") if "bibliographystyle" in line.lower() and "Update" in line]
        assert len(bib_edits) == 1

    def test_noop_when_already_target_format(self):
        """Document already matching target → noop."""
        from app.constants.paper_templates import CONFERENCE_TEMPLATES
        acl_preamble = CONFERENCE_TEMPLATES["acl"]["preamble_example"].replace(
            "Your Paper Title", "My Paper"
        )
        source = acl_preamble + "\n\n\\section{Intro}\nHello.\n\n\\end{document}\n"
        result = deterministic_full_convert(source, "acl")
        assert result.kind == "noop"

    def test_elsevier_fallback(self):
        """Elsevier uses frontmatter, not \\maketitle — intentional fallback."""
        source = r"""\documentclass[preprint,12pt]{elsarticle}
\title{My Paper}
\begin{document}
\begin{frontmatter}
\title{My Paper}
\end{frontmatter}
\section{Intro}
\end{document}
"""
        result = deterministic_full_convert(source, "elsevier")
        assert result.kind == "fallback"
        assert result.fallback_reason == "non_maketitle_family"

    def test_escaped_percent_not_treated_as_comment(self):
        r"""Line with \% before command is still active code."""
        source = r"""\documentclass{article}
\title{My Paper}
\author{Author}
\begin{document}
\maketitle

\section{Results: 50\% improvement}
\bibliographystyle{IEEEtran}

\end{document}
"""
        result = deterministic_full_convert(source, "acl")
        assert result.kind == "edits"
        # The \% on the "Results" line shouldn't affect the bibliographystyle line
        assert r"\bibliographystyle{plain}" in result.edits

    def test_every_fallback_has_reason(self):
        """All fallback paths return non-empty fallback_reason."""
        # unknown_template
        r = deterministic_full_convert(MINIMAL_DOC, "nonexistent")
        assert r.kind == "fallback" and r.fallback_reason == "unknown_template"

        # truncated
        r = deterministic_full_convert(r"\title{T}\maketitle", "acl")
        assert r.kind == "fallback" and r.fallback_reason == "truncated"

        # missing_maketitle
        r = deterministic_full_convert(
            r"\documentclass{article}" + "\n" + r"\title{T}" + "\n" +
            r"\begin{document}" + "\n" + r"\end{document}", "acl"
        )
        assert r.kind == "fallback" and r.fallback_reason == "missing_maketitle"

        # missing_title
        r = deterministic_full_convert(
            r"\documentclass{article}" + "\n" +
            r"\begin{document}" + "\n" + r"\maketitle" + "\n" + r"\end{document}", "acl"
        )
        assert r.kind == "fallback" and r.fallback_reason == "missing_title"

        # non_maketitle_family
        r = deterministic_full_convert(MINIMAL_DOC, "elsevier")
        assert r.kind == "fallback" and r.fallback_reason == "non_maketitle_family"


class TestHardening:
    """Tests for hardening rules: descending order, precise matching, idempotency."""

    def test_edits_in_descending_line_order(self):
        """All edit blocks should be in descending start_line order."""
        source = r"""\documentclass[conference]{IEEEtran}
\title{My Paper}
\author{Author}
\begin{document}
\maketitle

\begin{IEEEkeywords}
deep learning
\end{IEEEkeywords}

\bibliographystyle{IEEEtran}
\end{document}
"""
        result = deterministic_full_convert(source, "acl")
        assert result.kind == "edits"
        # Extract line numbers from <<<LINES>>> blocks
        import re
        line_ranges = re.findall(r"<<<LINES>>>\n(\d+)", result.edits)
        line_nums = [int(x) for x in line_ranges]
        # Should be descending
        assert line_nums == sorted(line_nums, reverse=True), f"Not descending: {line_nums}"

    def test_precise_maketitle_match(self):
        r"""\\maketitlepage should not match \\maketitle."""
        source = r"""\documentclass{article}
\title{Test}
\author{Author}
\begin{document}
\maketitlepage
\maketitle
\section{Intro}
\end{document}
"""
        result = deterministic_full_convert(source, "acl")
        assert result.kind == "edits"
        # \maketitle is on line 6, not line 5 (\maketitlepage)
        assert "1-6" in result.edits
