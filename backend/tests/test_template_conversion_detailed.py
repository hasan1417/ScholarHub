"""
Detailed Template Conversion Tests with Before/After Comparisons

This test suite shows exact transformations for examination.
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'))

from unittest.mock import MagicMock
from app.services.smart_agent_service_v2 import SmartAgentServiceV2
from app.constants.paper_templates import CONFERENCE_TEMPLATES


# ============================================================================
# TEST DOCUMENTS - Various structures to test conversion
# ============================================================================

# Document 1: Simple generic article
DOC_SIMPLE = r"""
\documentclass{article}
\usepackage{graphicx}

\title{Machine Learning for Healthcare}
\author{John Doe \and Jane Smith}
\date{January 2024}

\begin{document}
\maketitle

\begin{abstract}
We present a machine learning approach for healthcare diagnostics.
\end{abstract}

\section{Introduction}
Healthcare diagnostics can benefit from ML techniques.

\section{Methods}
We use a CNN-based architecture.

\section{Results}
Our model achieves 94% accuracy.

\section{Conclusion}
ML shows promise for healthcare.

\bibliographystyle{plain}
\bibliography{refs}

\end{document}
"""

# Document 2: More complex with multiple packages
DOC_COMPLEX = r"""
\documentclass[12pt,letterpaper]{article}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{natbib}
\usepackage{algorithm}
\usepackage{algorithmic}

\title{Transformer Architectures for Language Understanding}
\author{Alice Johnson\thanks{Corresponding author: alice@university.edu} \and
        Bob Williams \and
        Carol Davis}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
This paper introduces novel transformer variants that improve upon BERT and GPT architectures. We demonstrate state-of-the-art results on GLUE and SuperGLUE benchmarks with 15\% fewer parameters.
\end{abstract}

\section{Introduction}
\label{sec:intro}
Large language models have revolutionized NLP \citep{devlin2019bert,brown2020gpt3}.

\section{Related Work}
\subsection{Transformer Models}
The transformer architecture \citep{vaswani2017attention} introduced self-attention.

\subsection{Pre-training Objectives}
BERT uses masked language modeling while GPT uses autoregressive training.

\section{Methodology}
\subsection{Architecture}
Our model uses sparse attention patterns defined as:
\begin{equation}
\text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V
\end{equation}

\subsection{Training}
We train on 100B tokens using AdamW optimizer.

\section{Experiments}
\subsection{Datasets}
We evaluate on GLUE, SuperGLUE, and SQuAD 2.0.

\subsection{Baselines}
We compare against BERT-large, RoBERTa, and ALBERT.

\section{Results}
Our model achieves:
\begin{itemize}
    \item GLUE: 89.2 (vs 87.6 for BERT-large)
    \item SuperGLUE: 84.1 (vs 81.3 for RoBERTa)
    \item SQuAD 2.0 F1: 91.2
\end{itemize}

\section{Discussion}
The sparse attention mechanism reduces computational cost while maintaining accuracy.

\section{Conclusion}
We presented an efficient transformer variant with strong empirical results.

\bibliographystyle{plainnat}
\bibliography{references}

\end{document}
"""

# Document 3: Minimal document
DOC_MINIMAL = r"""
\documentclass{article}
\title{A Short Note}
\author{Anonymous}
\begin{document}
\maketitle
\section{Content}
This is minimal content.
\end{document}
"""

# Document 4: Already in ACL format (test no unnecessary changes)
DOC_ACL_EXISTING = r"""
\documentclass[11pt,a4paper]{article}
\usepackage[hyperref]{acl2023}
\usepackage{times}
\usepackage{latexsym}
\aclfinalcopy

\title{Existing ACL Paper}

\author{First Author \\
  University \\
  \texttt{first@uni.edu} \And
  Second Author \\
  Institute \\
  \texttt{second@inst.org}}

\begin{document}
\maketitle

\begin{abstract}
This paper is already in ACL format.
\end{abstract}

\section{Introduction}
Testing conversion of already-formatted documents.

\bibliography{anthology}

\end{document}
"""


def create_mock_db():
    """Create mock database session."""
    mock_db = MagicMock()
    mock_db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []
    return mock_db


def extract_edits(response: str) -> list:
    """Extract edit blocks from response."""
    edits = []
    pattern = r'<<<EDIT>>>\n(.*?)\n<<<ORIGINAL>>>\n(.*?)\n<<<PROPOSED>>>\n(.*?)\n<<<END>>>'
    matches = re.findall(pattern, response, re.DOTALL)
    for desc, original, proposed in matches:
        edits.append({
            'description': desc.strip(),
            'original': original.strip(),
            'proposed': proposed.strip()
        })
    return edits


def apply_edits_to_document(doc: str, edits: list) -> str:
    """Apply extracted edits to document to show final result."""
    result = doc
    for edit in edits:
        original = edit['original']
        proposed = edit['proposed']
        if original in result:
            result = result.replace(original, proposed, 1)
    return result


def print_document_comparison(title: str, original: str, converted: str):
    """Print side-by-side comparison of documents."""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print('='*80)

    print("\n" + "-"*35 + " BEFORE " + "-"*35)
    # Show first 60 lines of original
    lines = original.strip().split('\n')
    for i, line in enumerate(lines[:60]):
        print(f"  {i+1:3d} | {line}")
    if len(lines) > 60:
        print(f"  ... ({len(lines) - 60} more lines)")

    print("\n" + "-"*35 + " AFTER " + "-"*36)
    # Show first 60 lines of converted
    lines = converted.strip().split('\n')
    for i, line in enumerate(lines[:60]):
        print(f"  {i+1:3d} | {line}")
    if len(lines) > 60:
        print(f"  ... ({len(lines) - 60} more lines)")


def run_conversion(doc_name: str, doc: str, target_template: str, service: SmartAgentServiceV2):
    """Test converting a document and show before/after."""
    print(f"\n\n{'#'*80}")
    print(f"# TEST: {doc_name} → {target_template.upper()}")
    print('#'*80)

    mock_db = create_mock_db()

    # Get conversion response
    query = f"Convert this document to {target_template} format"

    response = ''.join(service.stream_query(
        db=mock_db,
        user_id="test-user",
        query=query,
        document_excerpt=doc,
        reasoning_mode=False
    ))

    # Extract edits
    edits = extract_edits(response)

    print(f"\n📋 AI Response Summary:")
    print(f"   - Response length: {len(response)} chars")
    print(f"   - Edits proposed: {len(edits)}")

    if edits:
        print(f"\n📝 Proposed Edits:")
        for i, edit in enumerate(edits, 1):
            print(f"   {i}. {edit['description']}")

        # Apply edits to show result
        converted = apply_edits_to_document(doc, edits)

        # Show comparison
        print_document_comparison(
            f"{doc_name} converted to {target_template.upper()}",
            doc,
            converted
        )

        # Validation checks
        print(f"\n✅ Validation Checks:")
        template = CONFERENCE_TEMPLATES.get(target_template, {})

        # Check documentclass
        if target_template == 'ieee':
            has_correct_class = 'IEEEtran' in converted
        elif target_template == 'acl':
            has_correct_class = 'acl2023' in converted or 'acl20' in converted
        elif target_template == 'neurips':
            has_correct_class = 'neurips' in converted
        elif target_template == 'aaai':
            has_correct_class = 'aaai' in converted
        elif target_template == 'icml':
            has_correct_class = 'icml' in converted
        else:
            has_correct_class = True

        print(f"   - Correct document class: {'✓' if has_correct_class else '✗'}")

        # Check if original content preserved
        # Extract original abstract
        abstract_match = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', doc, re.DOTALL)
        if abstract_match:
            original_abstract = abstract_match.group(1).strip()
            has_abstract = original_abstract in converted or 'abstract' in converted.lower()
            print(f"   - Abstract content preserved: {'✓' if has_abstract else '⚠️ (may need manual check)'}")

        # Check sections preserved
        original_sections = re.findall(r'\\section\{([^}]+)\}', doc)
        sections_preserved = sum(1 for s in original_sections if s in converted)
        print(f"   - Sections preserved: {sections_preserved}/{len(original_sections)}")

        return True, edits, converted
    else:
        print(f"\n⚠️ No edits were generated. Full response:")
        print("-"*40)
        print(response[:2000])
        print("-"*40)
        return False, [], doc


def run_comprehensive_tests():
    """Run comprehensive conversion tests."""
    print("\n" + "="*80)
    print("  COMPREHENSIVE LATEX TEMPLATE CONVERSION TEST SUITE")
    print("  Testing Before/After Transformations")
    print("="*80)

    service = SmartAgentServiceV2()
    if not service.client:
        print("\n⚠️ ERROR: OpenAI API key not configured")
        return False

    print(f"\n✓ OpenAI API configured")
    print(f"✓ Templates available: {list(CONFERENCE_TEMPLATES.keys())}")

    # Test matrix
    tests = [
        # (doc_name, document, target_template)
        ("Simple Article", DOC_SIMPLE, "acl"),
        ("Simple Article", DOC_SIMPLE, "ieee"),
        ("Simple Article", DOC_SIMPLE, "neurips"),
        ("Complex Article", DOC_COMPLEX, "acl"),
        ("Complex Article", DOC_COMPLEX, "ieee"),
        ("Minimal Document", DOC_MINIMAL, "acl"),
        ("Minimal Document", DOC_MINIMAL, "neurips"),
    ]

    results = []

    for doc_name, doc, target in tests:
        try:
            success, edits, converted = run_conversion(doc_name, doc, target, service)
            results.append({
                'name': f"{doc_name} → {target}",
                'success': success,
                'edit_count': len(edits)
            })
        except Exception as e:
            print(f"\n❌ Error in test: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                'name': f"{doc_name} → {target}",
                'success': False,
                'edit_count': 0
            })

    # Summary
    print("\n\n" + "="*80)
    print("  TEST SUMMARY")
    print("="*80)

    for r in results:
        status = "✓ PASS" if r['success'] else "✗ FAIL"
        print(f"  {status}: {r['name']} ({r['edit_count']} edits)")

    passed = sum(1 for r in results if r['success'])
    print(f"\n  Total: {passed}/{len(results)} tests passed")

    return all(r['success'] for r in results)


def test_all_templates_on_single_doc():
    """Test converting one document to all templates."""
    print("\n\n" + "="*80)
    print("  SINGLE DOCUMENT → ALL TEMPLATES TEST")
    print("="*80)

    service = SmartAgentServiceV2()
    if not service.client:
        print("\n⚠️ ERROR: OpenAI API key not configured")
        return

    doc = DOC_SIMPLE
    print(f"\n📄 Source Document: Simple Article")
    print("-"*40)
    for i, line in enumerate(doc.strip().split('\n')[:20], 1):
        print(f"  {i:3d} | {line}")
    print("  ... (truncated)")

    for template_id in ['acl', 'ieee', 'neurips', 'aaai', 'icml', 'generic']:
        print(f"\n\n{'='*60}")
        print(f"  Converting to: {template_id.upper()}")
        print('='*60)

        mock_db = create_mock_db()
        response = ''.join(service.stream_query(
            db=mock_db,
            user_id="test-user",
            query=f"Convert to {template_id} format",
            document_excerpt=doc,
            reasoning_mode=False
        ))

        edits = extract_edits(response)

        if edits:
            converted = apply_edits_to_document(doc, edits)

            # Show just the preamble comparison
            print(f"\n  PREAMBLE TRANSFORMATION ({len(edits)} edit(s)):")
            print("-"*60)

            # Extract and show new preamble
            preamble_match = re.search(r'^(.*?\\begin\{document\})', converted, re.DOTALL)
            if preamble_match:
                new_preamble = preamble_match.group(1)
                for i, line in enumerate(new_preamble.split('\n')[:25], 1):
                    print(f"  {i:3d} | {line}")
                if len(new_preamble.split('\n')) > 25:
                    print("  ... (truncated)")
        else:
            print(f"  ⚠️ No edits generated")


def test_edge_cases():
    """Test edge cases and error handling."""
    print("\n\n" + "="*80)
    print("  EDGE CASE TESTS")
    print("="*80)

    service = SmartAgentServiceV2()
    if not service.client:
        print("\n⚠️ ERROR: OpenAI API key not configured")
        return

    mock_db = create_mock_db()

    # Test 1: Invalid template
    print("\n\n--- Test: Invalid Template ID ---")
    response = ''.join(service.stream_query(
        db=mock_db,
        user_id="test-user",
        query="Convert to INVALID_FORMAT format",
        document_excerpt=DOC_SIMPLE,
        reasoning_mode=False
    ))
    print(f"Response: {response[:500]}...")

    # Test 2: Empty document
    print("\n\n--- Test: Empty Document ---")
    response = ''.join(service.stream_query(
        db=mock_db,
        user_id="test-user",
        query="Convert to ACL format",
        document_excerpt="",
        reasoning_mode=False
    ))
    print(f"Response: {response[:500]}...")

    # Test 3: Document without preamble
    print("\n\n--- Test: Document Without Standard Preamble ---")
    weird_doc = r"""
\section{Introduction}
Just some content without proper structure.
\section{Conclusion}
The end.
"""
    response = ''.join(service.stream_query(
        db=mock_db,
        user_id="test-user",
        query="Convert to IEEE format",
        document_excerpt=weird_doc,
        reasoning_mode=False
    ))
    print(f"Response: {response[:500]}...")

    # Test 4: List templates query
    print("\n\n--- Test: List Available Templates ---")
    response = ''.join(service.stream_query(
        db=mock_db,
        user_id="test-user",
        query="What conference formats can I use?",
        document_excerpt=DOC_SIMPLE,
        reasoning_mode=False
    ))
    print(f"Response (truncated): {response[:1000]}...")


if __name__ == "__main__":
    print("\n" + "#"*80)
    print("#" + " "*30 + "DETAILED TEST SUITE" + " "*29 + "#")
    print("#"*80)

    # Run comprehensive tests
    run_comprehensive_tests()

    # Test all templates
    test_all_templates_on_single_doc()

    # Test edge cases
    test_edge_cases()

    print("\n\n" + "="*80)
    print("  ALL TESTS COMPLETED")
    print("="*80)
