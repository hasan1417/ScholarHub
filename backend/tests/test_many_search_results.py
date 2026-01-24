"""
Test: User asks about many search results without PDFs
"""
import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockChannel:
    def __init__(self):
        self.id = str(uuid4())
        self.name = "Test"
        self.ai_memory = {}


class MockProject:
    def __init__(self):
        self.id = str(uuid4())
        self.created_by = str(uuid4())
        self.title = "AI Research"
        self.idea = "Research"
        self.scope = ""
        self.keywords = "AI"
        self.status = "active"


class MockDB:
    def commit(self): pass
    def rollback(self): pass
    def query(self, *args): return self
    def join(self, *args): return self
    def filter(self, *args): return self
    def first(self): return None
    def all(self): return []
    def count(self): return 0
    def order_by(self, *args): return self
    def limit(self, *args): return self


def test_many_search_results():
    from app.services.ai_service import AIService
    from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

    print("Testing: User asks about 15 search results without PDFs")
    print("=" * 70)

    ai = AIService()
    db = MockDB()
    orch = ToolOrchestrator(ai, db)

    # Create 15 search results (simulating a search)
    search_results = []
    for i in range(15):
        has_pdf = (i % 5 == 0)  # Only every 5th paper has PDF
        search_results.append({
            "title": f"Paper {i+1}: Research on Topic {chr(65+i)}",
            "authors": f"Author {i+1}",
            "year": 2024 - (i % 3),
            "abstract": f"This paper investigates topic {chr(65+i)} using novel methods. We propose an approach that achieves state-of-the-art results on benchmark datasets.",
            "pdf_url": "http://example.com/paper.pdf" if has_pdf else None,
            "is_open_access": has_pdf,
            "source": "semantic_scholar"
        })

    channel = MockChannel()
    project = MockProject()

    print("\nUser: What methodologies do these 15 papers use? Give me details.")
    print("-" * 70)

    result = orch.handle_message(
        project=project,
        channel=channel,
        message="What methodologies do these 15 papers use? I need specific details about their approaches and experimental setups.",
        recent_search_results=search_results,
        conversation_history=[
            {"role": "user", "content": "Search for papers about machine learning"},
            {"role": "assistant", "content": "Found 15 papers about machine learning."},
        ],
        reasoning_mode=False,
    )

    print("AI Response:")
    print(result.get("message", "")[:1500])
    print()
    print(f"Tools called: {result.get('tools_called', [])}")

    response = result.get("message", "").lower()
    keywords = ["abstract", "limited", "high-level", "cannot", "pdf", "ingest", "add to library", "shallow", "only"]

    found_keywords = [k for k in keywords if k in response]

    if found_keywords:
        print(f"\n✓ AI acknowledged limitations (found: {found_keywords})")
    else:
        print("\n⚠ AI may not have acknowledged limitations clearly")

    print()
    print("=" * 70)


if __name__ == "__main__":
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(backend_dir)

    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(backend_dir), ".env"))

    test_many_search_results()
