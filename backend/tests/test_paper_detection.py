"""
Tests for paper content detection in the OpenRouter orchestrator.

These tests verify the _detect_paper_content method correctly identifies
LaTeX and Markdown paper content while avoiding false positives.
"""

import pytest


class MockOrchestrator:
    """Minimal mock to test _detect_paper_content in isolation."""

    def _detect_paper_content(self, content: str, min_length: int = 0):
        """Detect if content contains paper content (LaTeX or Markdown). Returns format or None."""
        import re
        if not content:
            return None

        # Enforce minimum length to avoid false positives on short snippets
        if min_length > 0 and len(content) < min_length:
            return None

        # Check for LaTeX patterns - require stronger signals
        # Primary indicators (document structure)
        primary_latex = [
            r'\\documentclass',
            r'\\begin\{document\}',
        ]
        # Secondary indicators (content structure)
        secondary_latex = [
            r'\\title\{',
            r'\\section\{',
            r'\\subsection\{',
            r'\\usepackage',
            r'\\author\{',
            r'\\abstract',
            r'\\maketitle',
        ]
        primary_matches = sum(1 for pattern in primary_latex if re.search(pattern, content))
        secondary_matches = sum(1 for pattern in secondary_latex if re.search(pattern, content))

        # Require at least one primary indicator OR 3+ secondary indicators
        if primary_matches >= 1 and secondary_matches >= 1:
            return "latex"
        if secondary_matches >= 3:
            return "latex"

        # Check for Markdown paper patterns (structured academic content)
        markdown_indicators = [
            r'^#\s+.+',  # H1 heading (title)
            r'^##\s+(?:Abstract|Introduction|Background|Methods|Results|Discussion|Conclusion|References)',
            r'^###\s+',  # H3 subsections
            r'\*\*(?:Abstract|Keywords|Author).*?\*\*',  # Bold academic labels
        ]
        markdown_matches = sum(
            1 for pattern in markdown_indicators
            if re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
        )
        # Need title + at least one academic section
        has_title = bool(re.search(r'^#\s+.+', content, re.MULTILINE))
        if has_title and markdown_matches >= 2:
            return "markdown"

        return None


@pytest.fixture
def detector():
    """Create a mock orchestrator for testing detection."""
    return MockOrchestrator()


class TestLaTeXDetection:
    """Tests for LaTeX paper detection."""

    def test_full_latex_document_detected(self, detector):
        """Full LaTeX document with documentclass and begin{document} should be detected."""
        content = r"""
\documentclass{article}
\usepackage{graphicx}
\title{A Study on Machine Learning}
\author{John Doe}
\begin{document}
\maketitle
\section{Introduction}
This paper presents...
\end{document}
"""
        assert detector._detect_paper_content(content) == "latex"

    def test_latex_with_primary_and_secondary(self, detector):
        """LaTeX with one primary (documentclass) and one secondary (section) should be detected."""
        content = r"""
\documentclass{article}
\section{Introduction}
Some content here.
"""
        assert detector._detect_paper_content(content) == "latex"

    def test_latex_three_secondary_no_primary(self, detector):
        """LaTeX with 3+ secondary indicators but no primary should be detected."""
        content = r"""
\title{Research Paper}
\author{Jane Smith}
\section{Methods}
\subsection{Data Collection}
"""
        assert detector._detect_paper_content(content) == "latex"

    def test_false_positive_two_sections_only(self, detector):
        """Just two section/subsection markers should NOT trigger detection (was old threshold)."""
        content = r"""
Here's how to use LaTeX sections:
\section{First Section}
\subsection{A Subsection}
That's it!
"""
        # This should NOT be detected as paper content
        assert detector._detect_paper_content(content) is None

    def test_false_positive_code_snippet(self, detector):
        """Code snippet explaining LaTeX should not be detected as paper."""
        content = r"""
To create a section in LaTeX, use:
\section{Your Section Title}

You can also use \subsection{} for nested sections.
"""
        # Only 2 secondary indicators - should NOT be detected
        assert detector._detect_paper_content(content) is None

    def test_min_length_prevents_short_matches(self, detector):
        """Short content should not match when min_length is specified."""
        short_content = r"\documentclass{article}\section{Test}"

        # Without min_length, should detect
        assert detector._detect_paper_content(short_content) == "latex"

        # With min_length > content length, should NOT detect
        assert detector._detect_paper_content(short_content, min_length=500) is None

    def test_empty_content(self, detector):
        """Empty or None content should return None."""
        assert detector._detect_paper_content("") is None
        assert detector._detect_paper_content(None) is None


class TestMarkdownDetection:
    """Tests for Markdown paper detection."""

    def test_academic_markdown_detected(self, detector):
        """Markdown with title and academic sections should be detected."""
        content = """
# A Comprehensive Study on Neural Networks

## Abstract
This paper presents a novel approach...

## Introduction
Machine learning has revolutionized...

## Methods
We employed the following methodology...
"""
        assert detector._detect_paper_content(content) == "markdown"

    def test_markdown_with_bold_labels(self, detector):
        """Markdown with bold academic labels should be detected."""
        content = """
# Research Paper Title

**Abstract:** This study investigates...

**Keywords:** machine learning, AI, neural networks

## Introduction
The field of artificial intelligence...
"""
        assert detector._detect_paper_content(content) == "markdown"

    def test_false_positive_simple_readme(self, detector):
        """Simple README with H1 but no academic sections should NOT be detected."""
        content = """
# My Project

This is a simple project for demonstration.

## Installation
Run `pip install myproject`

## Usage
Import and use the library.
"""
        # Has title but no academic section names (Abstract, Introduction, etc.)
        assert detector._detect_paper_content(content) is None

    def test_false_positive_no_title(self, detector):
        """Academic sections without H1 title should NOT be detected."""
        content = """
## Abstract
This paper discusses...

## Introduction
We present...
"""
        # No H1 title
        assert detector._detect_paper_content(content) is None


class TestStreamingScenarios:
    """Tests simulating streaming detection scenarios."""

    def test_early_detection_partial_latex(self, detector):
        """Partial LaTeX content during streaming might not have enough signals."""
        # First 200 chars of a paper being streamed
        partial = r"\documentclass{article}\usepackage{graphicx}\usepackage{amsmath}"

        # With min_length=500, should not detect yet
        assert detector._detect_paper_content(partial, min_length=500) is None

        # Without min_length, should detect (has primary + secondary)
        assert detector._detect_paper_content(partial) == "latex"

    def test_full_paper_detected_after_streaming(self, detector):
        """Full paper content should be detected at end of streaming."""
        full_paper = r"""
\documentclass{article}
\usepackage{graphicx}
\usepackage{amsmath}
\title{Machine Learning Applications}
\author{Research Team}
\begin{document}
\maketitle
\section{Introduction}
This paper explores...
\section{Methods}
We used the following approach...
\section{Results}
Our experiments showed...
\section{Conclusion}
In conclusion...
\end{document}
""" + " " * 300  # Pad to ensure > 500 chars

        assert detector._detect_paper_content(full_paper, min_length=500) == "latex"

    def test_non_paper_response_not_detected(self, detector):
        """Regular AI response without LaTeX commands should not trigger detection."""
        response = """
I can help you understand LaTeX! Here are some tips:

1. Use section commands for major sections
2. Use subsection commands for sub-sections
3. Always include a documentclass at the top

Would you like me to create a paper template for you?
"""
        assert detector._detect_paper_content(response) is None
        assert detector._detect_paper_content(response, min_length=500) is None

    def test_response_with_latex_examples_short(self, detector):
        """Short AI response explaining LaTeX commands - min_length helps avoid detection."""
        # This response contains actual LaTeX patterns but is short
        response = r"""
To format your document, use \documentclass{article} at the top,
then \section{Title} for sections.
"""
        # Without min_length, this would detect (has primary + secondary)
        # With min_length=500, it won't detect because content is short
        assert detector._detect_paper_content(response, min_length=500) is None


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_exactly_three_secondary_indicators(self, detector):
        """Exactly 3 secondary indicators should trigger detection."""
        content = r"""
\title{My Paper}
\author{John Doe}
\section{Introduction}
Content here.
"""
        assert detector._detect_paper_content(content) == "latex"

    def test_two_secondary_indicators_no_detection(self, detector):
        """Exactly 2 secondary indicators should NOT trigger detection."""
        content = r"""
\title{My Paper}
\section{Introduction}
Content here.
"""
        assert detector._detect_paper_content(content) is None

    def test_mixed_latex_and_markdown(self, detector):
        """Content with both LaTeX and Markdown should prefer LaTeX if both match."""
        content = r"""
# A Paper Title

\documentclass{article}
\section{Introduction}

## Abstract
Some abstract text.
"""
        # LaTeX check comes first, should return latex
        result = detector._detect_paper_content(content)
        assert result == "latex"

    def test_min_length_boundary(self, detector):
        """Test exact boundary of min_length."""
        content = "x" * 499 + r"\documentclass{article}\section{Test}"

        # Content is now > 500 chars
        assert len(content) > 500
        assert detector._detect_paper_content(content, min_length=500) == "latex"

        # Shorter content
        short = "x" * 450 + r"\documentclass{article}\section{Test}"
        assert detector._detect_paper_content(short, min_length=500) is None
