import argparse
import math
import os
import sys
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # Ensure app package is importable when run directly

from app.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.research_paper import ResearchPaper  # noqa: E402


LOREM = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. "
    "Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. "
    "Cras elementum ultrices diam. Maecenas ligula massa, varius a, semper congue, euismod non, mi. "
    "Proin porttitor, orci nec nonummy molestie, enim est eleifend mi, non fermentum diam nisl sit amet erat. "
    "Duis semper. Duis arcu massa, scelerisque vitae, consequat in, pretium a, enim. "
    "Pellentesque congue. Ut in risus volutpat libero pharetra tempor. Cras vestibulum bibendum augue. "
    "Praesent egestas leo in pede. Praesent blandit odio eu enim. Pellentesque sed dui ut augue blandit sodales. "
    "Vestibulum ante ipsum primis in faucibus orci luctus et ultrices posuere cubilia Curae; Aliquam nibh. "
    "Mauris ac mauris sed pede pellentesque fermentum. Maecenas adipiscing ante non diam sodales hendrerit."
)


def make_paragraph(text: str) -> Dict[str, Any]:
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": text}],
    }


def make_heading(text: str, level: int) -> Dict[str, Any]:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def build_tiptap_doc(title: str, approx_pages: int = 3) -> Dict[str, Any]:
    # Heuristic: ~600 words per page in typical article layout
    target_words = max(approx_pages, 1) * 600
    sections = [
        (1, title),
        (2, "Abstract"),
        (0, "This paper is a sample rich text document generated for testing. It contains enough content to approximately span the requested number of pages when converted to LaTeX and compiled to PDF. The content is intentionally generic and should be replaced with your actual research text."),
        (2, "1. Introduction"),
        (0, LOREM),
        (0, LOREM),
        (2, "2. Background"),
        (0, LOREM),
        (2, "3. Method"),
        (0, LOREM),
        (2, "4. Results"),
        (0, LOREM),
        (2, "5. Discussion"),
        (0, LOREM),
        (2, "6. Conclusion"),
        (0, "This concludes the sample paper. Replace this content with your own sections, figures, tables, and citations as needed."),
    ]

    content: List[Dict[str, Any]] = []
    total_words = 0
    for level_or_para, text in sections:
        if level_or_para > 0:
            content.append(make_heading(text, level_or_para))
        else:
            content.append(make_paragraph(text))
            total_words += len(text.split())

    # Add additional paragraphs until we reach target words
    while total_words < target_words:
        content.append(make_paragraph(LOREM))
        total_words += len(LOREM.split())

    return {"type": "doc", "content": content, "authoring_mode": "rich"}


def tiptap_to_basic_html(doc: Dict[str, Any]) -> str:
    # Minimal HTML for preview; the editor primarily uses content_json
    parts: List[str] = []
    for node in doc.get("content", []) or []:
        t = node.get("type")
        if t == "heading":
            level = int(node.get("attrs", {}).get("level", 1))
            txt = "".join(c.get("text", "") for c in (node.get("content") or []) if c.get("type") == "text")
            level = max(1, min(level, 6))
            parts.append(f"<h{level}>{txt}</h{level}>")
        elif t == "paragraph":
            txt = "".join(c.get("text", "") for c in (node.get("content") or []) if c.get("type") == "text")
            parts.append(f"<p>{txt}</p>")
    return "\n".join(parts)


def create_sample_paper(db: Session, owner: User, title: str, pages: int, is_public: bool = False) -> ResearchPaper:
    doc = build_tiptap_doc(title, pages)
    html = tiptap_to_basic_html(doc)
    paper = ResearchPaper(
        title=title,
        abstract="Sample abstract for a generated rich mode paper.",
        content=html,
        content_json=doc,
        status="draft",
        paper_type="research",
        owner_id=owner.id,
        is_public=is_public,
        keywords=["sample", "rich", "generated"],
        references="",
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)
    return paper


def main():
    parser = argparse.ArgumentParser(description="Create a sample rich mode paper with approx N pages.")
    parser.add_argument("--owner-email", type=str, help="Owner user email", required=False)
    parser.add_argument("--owner-id", type=str, help="Owner user ID (UUID)", required=False)
    parser.add_argument("--title", type=str, default="Sample 3-Page Rich Paper", help="Paper title")
    parser.add_argument("--pages", type=int, default=3, help="Approximate number of pages of content")
    parser.add_argument("--public", action="store_true", help="Create as public paper")
    args = parser.parse_args()

    if not args.owner_email and not args.owner_id:
        print("Error: provide --owner-email or --owner-id", file=sys.stderr)
        sys.exit(2)

    db: Session = SessionLocal()
    try:
        owner: Optional[User] = None
        if args.owner_email:
            owner = db.query(User).filter(User.email == args.owner_email).first()
        elif args.owner_id:
            owner = db.query(User).filter(User.id == args.owner_id).first()
        if not owner:
            print("Error: owner not found", file=sys.stderr)
            sys.exit(1)

        paper = create_sample_paper(db, owner, args.title.strip(), max(args.pages, 1), args.public)
        print("Created paper:")
        print(f"  id: {paper.id}")
        print(f"  title: {paper.title}")
        print(f"  owner: {owner.email}")
        print(f"  content_json: authoring_mode={paper.content_json.get('authoring_mode')}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

