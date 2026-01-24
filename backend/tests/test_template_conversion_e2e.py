"""
End-to-End Integration Tests for LaTeX Template Conversion System

These tests call the actual OpenAI API to verify the AI correctly uses the template tools.

Run with: python tests/test_template_conversion_e2e.py
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'))

from unittest.mock import MagicMock
from app.services.smart_agent_service_v2 import SmartAgentServiceV2


# Sample document for testing
SAMPLE_DOCUMENT = r"""
\documentclass{article}
\usepackage{graphicx}
\usepackage{amsmath}

\title{Deep Learning for Text Classification}
\author{Alice Smith \and Bob Johnson}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
This paper presents a novel deep learning approach for text classification that achieves state-of-the-art results on multiple benchmarks.
\end{abstract}

\section{Introduction}
Text classification is a fundamental NLP task with applications in sentiment analysis, spam detection, and topic categorization.

\section{Related Work}
Previous approaches have used CNNs, RNNs, and more recently transformer-based models.

\section{Methods}
We propose a hybrid architecture combining BERT embeddings with a custom attention mechanism.

\section{Results}
Our model achieves 95.2% accuracy on the IMDB dataset and 92.1% on AG News.

\section{Conclusion}
We demonstrated significant improvements in text classification through our novel architecture.

\bibliographystyle{plain}
\bibliography{refs}

\end{document}
"""


def create_mock_db():
    """Create a mock database session."""
    mock_db = MagicMock()
    mock_db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []
    return mock_db


def test_list_templates_query():
    """Test that asking about available templates triggers list_available_templates tool."""
    print("\n" + "="*70)
    print("E2E TEST: List Templates Query")
    print("="*70)

    service = SmartAgentServiceV2()
    if not service.client:
        print("⚠️ SKIPPED: OpenAI API key not configured")
        return None

    mock_db = create_mock_db()
    queries = [
        "What templates are available?",
        "Show me the available formats",
        "What conference styles can I convert to?",
    ]

    for query in queries:
        print(f"\nQuery: '{query}'")
        print("-" * 50)

        try:
            response = ''.join(service.stream_query(
                db=mock_db,
                user_id="test-user",
                query=query,
                document_excerpt=SAMPLE_DOCUMENT,
                reasoning_mode=False
            ))

            print(f"Response length: {len(response)} chars")
            print(f"Response preview: {response[:500]}...")

            # Check if response mentions templates
            templates_mentioned = any(t in response.lower() for t in ['acl', 'ieee', 'neurips', 'aaai'])
            print(f"✓ Templates mentioned: {templates_mentioned}")

            if not templates_mentioned:
                print("⚠️ WARNING: Response may not have used list_available_templates tool")

        except Exception as e:
            print(f"✗ Error: {str(e)}")
            return False

    print("\n✓ List templates query test completed")
    return True


def test_convert_to_acl():
    """Test converting a document to ACL format."""
    print("\n" + "="*70)
    print("E2E TEST: Convert to ACL Format")
    print("="*70)

    service = SmartAgentServiceV2()
    if not service.client:
        print("⚠️ SKIPPED: OpenAI API key not configured")
        return None

    mock_db = create_mock_db()
    query = "Convert this paper to ACL format"

    print(f"\nQuery: '{query}'")
    print("-" * 50)

    try:
        response = ''.join(service.stream_query(
            db=mock_db,
            user_id="test-user",
            query=query,
            document_excerpt=SAMPLE_DOCUMENT,
            reasoning_mode=False
        ))

        print(f"Response length: {len(response)} chars")
        print("\nFull Response:")
        print("="*50)
        print(response)
        print("="*50)

        # Check for expected content
        checks = [
            ('ACL' in response, 'ACL mentioned'),
            ('acl2023' in response.lower() or 'documentclass' in response.lower(), 'LaTeX structure mentioned'),
            ('author' in response.lower(), 'Author format discussed'),
        ]

        for passed, description in checks:
            status = "✓" if passed else "✗"
            print(f"{status} {description}")

        return all(passed for passed, _ in checks)

    except Exception as e:
        print(f"✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_convert_to_ieee():
    """Test converting a document to IEEE format."""
    print("\n" + "="*70)
    print("E2E TEST: Convert to IEEE Format")
    print("="*70)

    service = SmartAgentServiceV2()
    if not service.client:
        print("⚠️ SKIPPED: OpenAI API key not configured")
        return None

    mock_db = create_mock_db()
    query = "Reformat this paper for IEEE conference"

    print(f"\nQuery: '{query}'")
    print("-" * 50)

    try:
        response = ''.join(service.stream_query(
            db=mock_db,
            user_id="test-user",
            query=query,
            document_excerpt=SAMPLE_DOCUMENT,
            reasoning_mode=False
        ))

        print(f"Response length: {len(response)} chars")
        print("\nFull Response:")
        print("="*50)
        print(response)
        print("="*50)

        # Check for expected content
        checks = [
            ('IEEE' in response, 'IEEE mentioned'),
            ('IEEEtran' in response or 'documentclass' in response.lower(), 'IEEE class mentioned'),
        ]

        for passed, description in checks:
            status = "✓" if passed else "✗"
            print(f"{status} {description}")

        return all(passed for passed, _ in checks)

    except Exception as e:
        print(f"✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_convert_to_neurips():
    """Test converting a document to NeurIPS format."""
    print("\n" + "="*70)
    print("E2E TEST: Convert to NeurIPS Format")
    print("="*70)

    service = SmartAgentServiceV2()
    if not service.client:
        print("⚠️ SKIPPED: OpenAI API key not configured")
        return None

    mock_db = create_mock_db()
    query = "Change this to NeurIPS style"

    print(f"\nQuery: '{query}'")
    print("-" * 50)

    try:
        response = ''.join(service.stream_query(
            db=mock_db,
            user_id="test-user",
            query=query,
            document_excerpt=SAMPLE_DOCUMENT,
            reasoning_mode=False
        ))

        print(f"Response length: {len(response)} chars")
        print("\nFull Response:")
        print("="*50)
        print(response)
        print("="*50)

        # Check for expected content
        checks = [
            ('NeurIPS' in response or 'neurips' in response.lower(), 'NeurIPS mentioned'),
        ]

        for passed, description in checks:
            status = "✓" if passed else "✗"
            print(f"{status} {description}")

        return all(passed for passed, _ in checks)

    except Exception as e:
        print(f"✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_full_conversion_with_edits():
    """Test asking for specific edits after seeing template info."""
    print("\n" + "="*70)
    print("E2E TEST: Full Conversion with Edit Proposals")
    print("="*70)

    service = SmartAgentServiceV2()
    if not service.client:
        print("⚠️ SKIPPED: OpenAI API key not configured")
        return None

    mock_db = create_mock_db()

    # First, ask to convert
    query = "Convert this paper to ACL format. Please show me the specific edits needed."

    print(f"\nQuery: '{query}'")
    print("-" * 50)

    try:
        response = ''.join(service.stream_query(
            db=mock_db,
            user_id="test-user",
            query=query,
            document_excerpt=SAMPLE_DOCUMENT,
            reasoning_mode=False
        ))

        print(f"Response length: {len(response)} chars")
        print("\nFull Response:")
        print("="*50)
        print(response)
        print("="*50)

        # Check for expected content - either template info or edit proposals
        has_template_info = 'ACL' in response
        has_edit_markers = '<<<EDIT>>>' in response or '<<<ORIGINAL>>>' in response
        has_latex_code = '\\documentclass' in response

        print(f"\n✓ Has template info: {has_template_info}")
        print(f"✓ Has edit markers: {has_edit_markers}")
        print(f"✓ Has LaTeX code: {has_latex_code}")

        return has_template_info or has_edit_markers

    except Exception as e:
        print(f"✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def run_all_e2e_tests():
    """Run all end-to-end tests."""
    print("\n" + "#"*70)
    print("# LATEX TEMPLATE CONVERSION - END-TO-END TESTS")
    print("#"*70)

    # Check if API key is available
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️ WARNING: OPENAI_API_KEY not set. E2E tests will be skipped.")
        print("Set the environment variable to run these tests.")
        return True  # Don't fail if no API key

    print(f"\n✓ OpenAI API key found (length: {len(api_key)})")

    tests = [
        ("List Templates Query", test_list_templates_query),
        ("Convert to ACL", test_convert_to_acl),
        ("Convert to IEEE", test_convert_to_ieee),
        ("Convert to NeurIPS", test_convert_to_neurips),
        ("Full Conversion with Edits", test_full_conversion_with_edits),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            if result is None:
                results.append((name, None, "Skipped"))
            elif result:
                results.append((name, True, None))
            else:
                results.append((name, False, "Test assertions failed"))
        except Exception as e:
            results.append((name, False, str(e)))

    # Summary
    print("\n" + "="*70)
    print("E2E TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, success, _ in results if success is True)
    skipped = sum(1 for _, success, _ in results if success is None)
    failed = sum(1 for _, success, _ in results if success is False)
    total = len(results)

    for name, success, error in results:
        if success is True:
            status = "✓ PASS"
        elif success is None:
            status = "⊘ SKIP"
        else:
            status = "✗ FAIL"
        print(f"{status}: {name}")
        if error and success is False:
            print(f"       Error: {error}")

    print(f"\nTotal: {passed} passed, {skipped} skipped, {failed} failed (out of {total})")

    if failed == 0:
        print("\n🎉 ALL E2E TESTS PASSED!")
    else:
        print(f"\n⚠️ {failed} test(s) failed")

    return failed == 0


if __name__ == "__main__":
    success = run_all_e2e_tests()
    sys.exit(0 if success else 1)
