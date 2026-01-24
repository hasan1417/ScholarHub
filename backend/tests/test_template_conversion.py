"""
Comprehensive tests for LaTeX Template Conversion System

Tests the following tools:
- list_available_templates
- apply_template

Run with: python -m pytest tests/test_template_conversion.py -v
Or standalone: python tests/test_template_conversion.py
"""
import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.constants.paper_templates import CONFERENCE_TEMPLATES, ConferenceTemplate
from app.services.smart_agent_service_v2 import SmartAgentServiceV2, EDITOR_TOOLS, SYSTEM_PROMPT


# ============================================================================
# SAMPLE LATEX DOCUMENTS FOR TESTING
# ============================================================================

SAMPLE_GENERIC_DOCUMENT = r"""
\documentclass{article}
\usepackage{graphicx}
\usepackage{amsmath}

\title{A Study on Machine Learning for Natural Language Processing}
\author{John Smith \and Jane Doe}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
This paper presents a novel approach to natural language processing using deep learning techniques. We demonstrate improved performance on several benchmark datasets.
\end{abstract}

\section{Introduction}
Natural language processing has seen tremendous advances in recent years. Our work builds upon these foundations to propose new methods.

\section{Related Work}
Previous studies have explored various approaches to this problem. Smith et al. (2020) proposed a transformer-based method. Jones et al. (2021) introduced attention mechanisms.

\section{Methods}
We propose a hybrid architecture combining CNNs and transformers. Our model consists of three main components:
\begin{itemize}
    \item Feature extraction layer
    \item Attention mechanism
    \item Classification head
\end{itemize}

\section{Results}
Our experiments show significant improvements over baseline methods. Table 1 summarizes the results.

\section{Conclusion}
We have demonstrated the effectiveness of our approach. Future work will explore additional architectures.

\bibliographystyle{plain}
\bibliography{references}

\end{document}
"""

SAMPLE_ACL_DOCUMENT = r"""
\documentclass[11pt,a4paper]{article}
\usepackage[hyperref]{acl2023}
\usepackage{times}
\usepackage{latexsym}
\usepackage{graphicx}
\aclfinalcopy

\title{Neural Machine Translation with Attention}

\author{Alice Johnson \\
  MIT \\
  \texttt{alice@mit.edu} \And
  Bob Wilson \\
  Stanford \\
  \texttt{bob@stanford.edu}}

\begin{document}
\maketitle

\begin{abstract}
We present a novel attention mechanism for neural machine translation that achieves state-of-the-art results on WMT benchmarks.
\end{abstract}

\section{Introduction}
Machine translation has evolved significantly with neural approaches.

\section{Related Work}
Transformer models \citep{vaswani2017} revolutionized NMT.

\section{Method}
Our approach introduces sparse attention patterns.

\section{Experiments}
We evaluate on WMT14 English-German and English-French.

\section{Results}
Our method achieves 32.5 BLEU on En-De.

\section{Conclusion}
We have shown improved translation quality.

\section{Limitations}
Our model requires significant computational resources.

\bibliography{anthology}

\end{document}
"""

SAMPLE_IEEE_DOCUMENT = r"""
\documentclass[conference]{IEEEtran}
\usepackage{cite}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{graphicx}

\begin{document}

\title{Deep Learning for Image Classification}

\author{\IEEEauthorblockN{Michael Chen}
\IEEEauthorblockA{\textit{Computer Science} \\
\textit{UC Berkeley}\\
Berkeley, USA \\
mchen@berkeley.edu}}

\maketitle

\begin{abstract}
This paper presents a convolutional neural network architecture for image classification.
\end{abstract}

\section{Introduction}
Image classification is a fundamental computer vision task.

\section{Related Work}
ResNet \cite{resnet} introduced residual connections.

\section{Methodology}
We propose a novel block structure.

\section{Results}
Our model achieves 95.2\% accuracy on CIFAR-10.

\section{Conclusion}
We demonstrated improved image classification performance.

\bibliographystyle{IEEEtran}
\bibliography{refs}

\end{document}
"""


# ============================================================================
# TEST FUNCTIONS
# ============================================================================

def test_conference_templates_structure():
    """Test that CONFERENCE_TEMPLATES has all required fields."""
    print("\n" + "="*60)
    print("TEST: Conference Templates Structure")
    print("="*60)

    required_fields = ['id', 'name', 'description', 'preamble_example',
                       'author_format', 'sections', 'bib_style', 'notes']

    for template_id, template in CONFERENCE_TEMPLATES.items():
        print(f"\nChecking template: {template_id}")
        for field in required_fields:
            assert field in template, f"Missing field '{field}' in template '{template_id}'"
            assert template[field], f"Empty field '{field}' in template '{template_id}'"
            print(f"  ✓ {field}: present")

        # Check that sections is a non-empty list
        assert isinstance(template['sections'], list), f"'sections' should be a list in '{template_id}'"
        assert len(template['sections']) > 0, f"'sections' should not be empty in '{template_id}'"
        print(f"  ✓ sections: {len(template['sections'])} items")

    print(f"\n✓ All {len(CONFERENCE_TEMPLATES)} templates have valid structure")
    return True


def test_editor_tools_include_template_tools():
    """Test that EDITOR_TOOLS includes the new template tools."""
    print("\n" + "="*60)
    print("TEST: Editor Tools Include Template Tools")
    print("="*60)

    tool_names = [tool['function']['name'] for tool in EDITOR_TOOLS]
    print(f"Available tools: {tool_names}")

    assert 'list_available_templates' in tool_names, "Missing 'list_available_templates' tool"
    print("  ✓ list_available_templates: present")

    assert 'apply_template' in tool_names, "Missing 'apply_template' tool"
    print("  ✓ apply_template: present")

    # Check apply_template has correct enum values
    for tool in EDITOR_TOOLS:
        if tool['function']['name'] == 'apply_template':
            params = tool['function']['parameters']
            template_id_prop = params['properties']['template_id']
            expected_enums = ['acl', 'ieee', 'neurips', 'aaai', 'icml', 'generic']
            assert template_id_prop['enum'] == expected_enums, f"Enum mismatch: {template_id_prop['enum']}"
            print(f"  ✓ apply_template enum values: {expected_enums}")

    print("\n✓ All template tools are correctly defined")
    return True


def test_system_prompt_mentions_templates():
    """Test that SYSTEM_PROMPT includes template conversion instructions."""
    print("\n" + "="*60)
    print("TEST: System Prompt Mentions Templates")
    print("="*60)

    checks = [
        ('list_available_templates', 'list_available_templates'),
        ('apply_template', 'apply_template'),
        ('TEMPLATE CONVERSION', 'Template conversion section'),
        ('ACL', 'ACL format mention'),
        ('IEEE', 'IEEE format mention'),
        ('NeurIPS', 'NeurIPS format mention'),
    ]

    for keyword, description in checks:
        assert keyword in SYSTEM_PROMPT, f"System prompt missing: {description}"
        print(f"  ✓ {description}: present")

    print("\n✓ System prompt includes all template-related instructions")
    return True


def test_handle_list_templates():
    """Test the _handle_list_templates method."""
    print("\n" + "="*60)
    print("TEST: Handle List Templates")
    print("="*60)

    service = SmartAgentServiceV2()

    # Collect output
    output = ''.join(service._handle_list_templates())

    print(f"Output length: {len(output)} characters")
    print("\nOutput preview:")
    print("-"*40)
    print(output[:1000] + "..." if len(output) > 1000 else output)
    print("-"*40)

    # Verify all templates are mentioned
    for template_id in CONFERENCE_TEMPLATES.keys():
        assert template_id in output, f"Template '{template_id}' not mentioned in output"
        print(f"  ✓ {template_id}: mentioned")

    # Verify output format
    assert "## Available Conference Templates" in output, "Missing header"
    assert "Convert this to ACL format" in output or "convert" in output.lower(), "Missing usage example"

    print("\n✓ list_available_templates output is correct")
    return True


def test_handle_apply_template_valid():
    """Test _handle_apply_template with valid template IDs."""
    print("\n" + "="*60)
    print("TEST: Handle Apply Template (Valid IDs)")
    print("="*60)

    service = SmartAgentServiceV2()

    for template_id in CONFERENCE_TEMPLATES.keys():
        print(f"\nTesting template: {template_id}")
        output = ''.join(service._handle_apply_template(template_id))

        # Verify output contains expected sections
        template = CONFERENCE_TEMPLATES[template_id]

        assert template['name'] in output, f"Template name not in output"
        print(f"  ✓ Name mentioned: {template['name'][:30]}...")

        assert "```latex" in output, "Missing LaTeX code block"
        print(f"  ✓ LaTeX code block present")

        assert template['bib_style'] in output, "Bibliography style not mentioned"
        print(f"  ✓ Bib style mentioned: {template['bib_style']}")

        # Check at least some sections are listed
        sections_found = sum(1 for s in template['sections'] if s in output)
        assert sections_found > 0, "No sections listed"
        print(f"  ✓ Sections listed: {sections_found}/{len(template['sections'])}")

    print("\n✓ apply_template works for all valid template IDs")
    return True


def test_handle_apply_template_invalid():
    """Test _handle_apply_template with invalid template ID."""
    print("\n" + "="*60)
    print("TEST: Handle Apply Template (Invalid ID)")
    print("="*60)

    service = SmartAgentServiceV2()

    output = ''.join(service._handle_apply_template("invalid_template"))

    print(f"Output: {output}")

    assert "Unknown template" in output, "Should indicate unknown template"
    assert "invalid_template" in output, "Should echo the invalid ID"

    print("\n✓ apply_template correctly handles invalid template IDs")
    return True


def test_template_preambles_are_valid_latex():
    """Test that template preambles contain valid LaTeX structure."""
    print("\n" + "="*60)
    print("TEST: Template Preambles Validity")
    print("="*60)

    for template_id, template in CONFERENCE_TEMPLATES.items():
        preamble = template['preamble_example']
        print(f"\nChecking {template_id}:")

        # Basic LaTeX structure checks
        assert r'\documentclass' in preamble, f"{template_id}: Missing \\documentclass"
        print(f"  ✓ Has \\documentclass")

        assert r'\begin{document}' in preamble or template_id == 'icml', f"{template_id}: Missing \\begin{{document}}"
        print(f"  ✓ Has \\begin{{document}} (or ICML special case)")

        assert r'\title{' in preamble or r'\icmltitle{' in preamble, f"{template_id}: Missing title"
        print(f"  ✓ Has title command")

        # Check for balanced braces (simple check)
        open_braces = preamble.count('{')
        close_braces = preamble.count('}')
        # Allow some imbalance since preamble may end mid-document
        assert abs(open_braces - close_braces) < 5, f"{template_id}: Severely unbalanced braces"
        print(f"  ✓ Braces roughly balanced ({open_braces} open, {close_braces} close)")

    print("\n✓ All template preambles have valid LaTeX structure")
    return True


def test_format_tool_response_integration():
    """Test that _format_tool_response correctly routes to template handlers."""
    print("\n" + "="*60)
    print("TEST: Format Tool Response Integration")
    print("="*60)

    service = SmartAgentServiceV2()

    # Test list_available_templates
    print("\nTesting list_available_templates routing:")
    output1 = ''.join(service._format_tool_response('list_available_templates', {}))
    assert "Available Conference Templates" in output1
    print("  ✓ list_available_templates routed correctly")

    # Test apply_template
    print("\nTesting apply_template routing:")
    output2 = ''.join(service._format_tool_response('apply_template', {'template_id': 'acl'}))
    assert "ACL" in output2
    print("  ✓ apply_template routed correctly")

    print("\n✓ Tool response routing works correctly")
    return True


def print_sample_conversion_output():
    """Print sample output for manual inspection."""
    print("\n" + "="*60)
    print("SAMPLE OUTPUT: Converting Generic Document to ACL")
    print("="*60)

    service = SmartAgentServiceV2()

    print("\n--- Original Document (first 500 chars) ---")
    print(SAMPLE_GENERIC_DOCUMENT[:500] + "...")

    print("\n--- Conversion Guidance for ACL ---")
    output = ''.join(service._handle_apply_template('acl'))
    print(output)

    print("\n--- Conversion Guidance for IEEE ---")
    output = ''.join(service._handle_apply_template('ieee'))
    print(output)


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "#"*60)
    print("# LATEX TEMPLATE CONVERSION SYSTEM - TEST SUITE")
    print("#"*60)

    tests = [
        ("Template Structure", test_conference_templates_structure),
        ("Editor Tools", test_editor_tools_include_template_tools),
        ("System Prompt", test_system_prompt_mentions_templates),
        ("List Templates Handler", test_handle_list_templates),
        ("Apply Template (Valid)", test_handle_apply_template_valid),
        ("Apply Template (Invalid)", test_handle_apply_template_invalid),
        ("Preamble Validity", test_template_preambles_are_valid_latex),
        ("Tool Response Integration", test_format_tool_response_integration),
    ]

    results = []
    for name, test_func in tests:
        try:
            test_func()
            results.append((name, True, None))
        except AssertionError as e:
            results.append((name, False, str(e)))
        except Exception as e:
            results.append((name, False, f"Error: {str(e)}"))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    for name, success, error in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {name}")
        if error:
            print(f"       Error: {error}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()

    print("\n")
    print_sample_conversion_output()

    sys.exit(0 if success else 1)
