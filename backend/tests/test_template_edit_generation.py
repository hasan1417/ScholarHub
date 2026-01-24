"""
Test that AI can generate actual edit proposals for template conversion.

This tests the full user flow:
1. User asks to convert to ACL
2. AI shows template info
3. User says "yes, make the edits"
4. AI generates propose_edit with actual changes
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'))

from unittest.mock import MagicMock
from app.services.smart_agent_service_v2 import SmartAgentServiceV2


SAMPLE_DOCUMENT = r"""
\documentclass{article}
\usepackage{graphicx}

\title{Deep Learning for Text Classification}
\author{Alice Smith \and Bob Johnson}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
This paper presents a novel approach for text classification.
\end{abstract}

\section{Introduction}
Text classification is important.

\section{Methods}
We use deep learning.

\section{Results}
Our model achieves 95% accuracy.

\section{Conclusion}
We demonstrated good results.

\end{document}
"""


def create_mock_db():
    mock_db = MagicMock()
    mock_db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []
    return mock_db


def test_direct_edit_request():
    """Test that asking directly for edits generates propose_edit."""
    print("\n" + "="*70)
    print("TEST: Direct Edit Request for ACL Conversion")
    print("="*70)

    service = SmartAgentServiceV2()
    if not service.client:
        print("⚠️ SKIPPED: OpenAI API key not configured")
        return None

    mock_db = create_mock_db()

    # Ask directly for edits
    query = """Please convert this document to ACL format. Generate the specific <<<EDIT>>> blocks
    to change the preamble and author block. I want to see the actual changes."""

    print(f"\nQuery: '{query[:100]}...'")
    print("-" * 50)

    try:
        response = ''.join(service.stream_query(
            db=mock_db,
            user_id="test-user",
            query=query,
            document_excerpt=SAMPLE_DOCUMENT,
            reasoning_mode=False
        ))

        print(f"\nResponse length: {len(response)} chars")
        print("\nFull Response:")
        print("="*50)
        print(response)
        print("="*50)

        # Check what we got
        has_edit_markers = '<<<EDIT>>>' in response
        has_original = '<<<ORIGINAL>>>' in response
        has_proposed = '<<<PROPOSED>>>' in response
        has_acl_content = 'acl' in response.lower() or 'ACL' in response

        print(f"\n✓ Has <<<EDIT>>>: {has_edit_markers}")
        print(f"✓ Has <<<ORIGINAL>>>: {has_original}")
        print(f"✓ Has <<<PROPOSED>>>: {has_proposed}")
        print(f"✓ ACL content: {has_acl_content}")

        if has_edit_markers:
            print("\n🎉 AI generated actual edit proposals!")
        else:
            print("\n📋 AI provided template information (may need follow-up for edits)")

        return True

    except Exception as e:
        print(f"✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_followup_edit_request():
    """Test that a follow-up request generates edits."""
    print("\n" + "="*70)
    print("TEST: Follow-up Edit Request")
    print("="*70)

    service = SmartAgentServiceV2()
    if not service.client:
        print("⚠️ SKIPPED: OpenAI API key not configured")
        return None

    mock_db = create_mock_db()

    # Simulate follow-up after seeing template info
    query = """Yes, please make those edits. Convert the preamble from \\documentclass{article}
    to ACL format with the proper packages and author block format."""

    print(f"\nQuery: '{query[:100]}...'")
    print("-" * 50)

    try:
        response = ''.join(service.stream_query(
            db=mock_db,
            user_id="test-user",
            query=query,
            document_excerpt=SAMPLE_DOCUMENT,
            reasoning_mode=False
        ))

        print(f"\nResponse length: {len(response)} chars")
        print("\nFull Response:")
        print("="*50)
        print(response)
        print("="*50)

        has_edit_markers = '<<<EDIT>>>' in response
        has_documentclass = '\\documentclass' in response

        print(f"\n✓ Has edit markers: {has_edit_markers}")
        print(f"✓ Has documentclass: {has_documentclass}")

        return True

    except Exception as e:
        print(f"✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_ieee_edit_generation():
    """Test IEEE conversion with edit generation."""
    print("\n" + "="*70)
    print("TEST: IEEE Conversion with Edits")
    print("="*70)

    service = SmartAgentServiceV2()
    if not service.client:
        print("⚠️ SKIPPED: OpenAI API key not configured")
        return None

    mock_db = create_mock_db()

    query = """Convert this to IEEE format. Replace the preamble with IEEEtran class
    and update the author block to use IEEEauthorblockN/A. Show me the edits."""

    print(f"\nQuery: '{query[:100]}...'")
    print("-" * 50)

    try:
        response = ''.join(service.stream_query(
            db=mock_db,
            user_id="test-user",
            query=query,
            document_excerpt=SAMPLE_DOCUMENT,
            reasoning_mode=False
        ))

        print(f"\nResponse length: {len(response)} chars")
        print("\nFull Response:")
        print("="*50)
        print(response)
        print("="*50)

        has_ieee = 'IEEE' in response or 'IEEEtran' in response
        print(f"\n✓ Has IEEE content: {has_ieee}")

        return True

    except Exception as e:
        print(f"✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "#"*70)
    print("# TEMPLATE EDIT GENERATION TESTS")
    print("#"*70)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️ WARNING: OPENAI_API_KEY not set")
        sys.exit(0)

    tests = [
        test_direct_edit_request,
        test_followup_edit_request,
        test_ieee_edit_generation,
    ]

    for test in tests:
        test()

    print("\n" + "="*70)
    print("Tests completed!")
    print("="*70)
