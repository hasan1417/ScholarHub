import os
import json
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.research_paper import ResearchPaper
from app.models.reference import Reference


router = APIRouter()


class ConvertRequest(BaseModel):
    paper_id: str
    target: str = "latex"  # currently only 'latex' supported
    model: Optional[str] = None  # optional override (AI strategy only)
    create_copy: bool = True     # always copy; true by default
    strategy: str = "strict"     # 'strict' (deterministic) or 'ai'


class ConvertResponse(BaseModel):
    new_paper_id: str
    title: str
    mode: str
    report: Dict[str, Any]


def _extract_counts_from_tiptap(doc: Any) -> Dict[str, int]:
    counts = {"paragraphs": 0, "headings": 0, "lists": 0, "tables": 0, "codeblocks": 0}
    try:
        def walk(node: Any):
            if not isinstance(node, dict):
                return
            t = node.get("type")
            if t == "paragraph":
                counts["paragraphs"] += 1
            elif t == "heading":
                counts["headings"] += 1
            elif t in ("bulletList", "orderedList"):
                counts["lists"] += 1
            elif t in ("table",):
                counts["tables"] += 1
            elif t in ("codeBlock", "codeBlockComponent", "code_block"):
                counts["codeblocks"] += 1
            for c in node.get("content", []) or []:
                walk(c)
        walk(doc)
    except Exception:
        pass
    return counts


def _tiptap_to_markdown(doc: Any) -> str:
    """Best-effort TipTap JSON → Markdown for model context. Not exhaustive."""
    lines: List[str] = []

    def text_of(n: Dict[str, Any]) -> str:
        if n.get("type") == "text":
            s = n.get("text", "")
            marks = n.get("marks", []) or []
            for m in marks:
                mt = m.get("type")
                if mt == "bold":
                    s = f"**{s}**"
                elif mt == "italic":
                    s = f"*{s}*"
                elif mt == "code":
                    s = f"`{s}`"
                elif mt == "underline":
                    s = s  # ignore underline in MD
            return s
        # Recurse content to flatten inline
        if isinstance(n, dict):
            return "".join(text_of(c) for c in (n.get("content") or []))
        return ""

    def walk(n: Any, list_prefix: Optional[str] = None):
        if not isinstance(n, dict):
            return
        t = n.get("type")
        if t == "heading":
            level = int(n.get("attrs", {}).get("level", 1))
            level = max(1, min(level, 6))
            content = "".join(text_of(c) for c in (n.get("content") or []))
            lines.append("#" * level + f" {content}")
            lines.append("")
        elif t == "paragraph":
            content = "".join(text_of(c) for c in (n.get("content") or []))
            if content.strip():
                if list_prefix is not None:
                    lines.append(f"{list_prefix} {content}")
                else:
                    lines.append(content)
            lines.append("")
        elif t == "bulletList":
            for item in (n.get("content") or []):
                walk(item, list_prefix="-")
        elif t == "orderedList":
            idx = 1
            for item in (n.get("content") or []):
                walk(item, list_prefix=f"{idx}.")
                idx += 1
        elif t == "listItem":
            for c in (n.get("content") or []):
                walk(c, list_prefix=list_prefix)
        elif t == "codeBlock":
            lang = n.get("attrs", {}).get("language") or ""
            content = "".join(text_of(c) for c in (n.get("content") or []))
            lines.append(f"```{lang}\n{content}\n```")
            lines.append("")
        elif t == "blockquote":
            inner = []
            for c in (n.get("content") or []):
                # simple: collect paragraph texts
                inner.append("".join(text_of(cc) for cc in (c.get("content") or [])))
            for l in "\n".join(inner).splitlines():
                lines.append("> " + l)
            lines.append("")
        elif t in ("table", "tableRow", "tableCell", "tableHeader"):
            # Minimal: render table as GitHub MD when possible
            # We'll convert rows to pipes; header guessed from first row
            # This is best-effort; model will refine.
            pass
        else:
            for c in (n.get("content") or []):
                walk(c, list_prefix=list_prefix)

    try:
        walk(doc)
    except Exception:
        return ""
    return "\n".join(lines).strip()


def _tiptap_to_latex_strict(doc: Any) -> str:
    """Deterministic TipTap JSON → LaTeX body. Preserves text; no paraphrasing."""
    out: List[str] = []

    def inline_text(n: Dict[str, Any]) -> str:
        if n.get("type") == "text":
            s = n.get("text", "")
            # No stylistic transforms; keep raw except basic escapes
            return s
        if isinstance(n, dict):
            return "".join(inline_text(c) for c in (n.get("content") or []))
        return ""

    def esc(s: str) -> str:
        # Only minimal escaping to avoid compilation issues; do not alter words
        return s.replace("\\", r"\textbackslash{}").replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")

    def walk(n: Any):
        if not isinstance(n, dict):
            return
        t = n.get("type")
        if t == "heading":
            level = int(n.get("attrs", {}).get("level", 1))
            txt = inline_text(n)
            # Map 1..6 to sectioning commands
            cmd = ["section", "subsection", "subsubsection", "paragraph", "subparagraph", "subparagraph"][level-1 if 1 <= level <= 6 else 0]
            out.append(f"\\{cmd}{{{esc(txt)}}}")
            out.append("")
        elif t == "paragraph":
            txt = inline_text(n)
            if txt.strip():
                out.append(esc(txt))
            out.append("")
        elif t == "bulletList":
            out.append("\\begin{itemize}")
            for item in (n.get("content") or []):
                # listItem -> paragraph(s)
                txt = "".join(inline_text(c) for c in (item.get("content") or []))
                out.append("\\item " + esc(txt))
            out.append("\\end{itemize}")
            out.append("")
        elif t == "orderedList":
            out.append("\\begin{enumerate}")
            for item in (n.get("content") or []):
                txt = "".join(inline_text(c) for c in (item.get("content") or []))
                out.append("\\item " + esc(txt))
            out.append("\\end{enumerate}")
            out.append("")
        elif t == "codeBlock":
            content = inline_text(n)
            out.append("\\begin{verbatim}")
            out.append(content)
            out.append("\\end{verbatim}")
            out.append("")
        elif t == "blockquote":
            out.append("\\begin{quote}")
            for c in (n.get("content") or []):
                walk(c)
            out.append("\\end{quote}")
            out.append("")
        else:
            for c in (n.get("content") or []):
                walk(c)

    try:
        walk(doc)
    except Exception:
        return ""
    return "\n".join(out).strip()


async def _pandoc_html_to_latex(html: str) -> Optional[str]:
    """Use pandoc to convert HTML → LaTeX body (no wrap). Returns None if pandoc missing/fails."""
    try:
        from shutil import which
        exe = which("pandoc")
        if not exe:
            return None
        import asyncio
        proc = await asyncio.create_subprocess_exec(
            exe, "-f", "html", "-t", "latex", "--wrap", "none",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin and proc.stdout
        stdout, stderr = await proc.communicate(html.encode("utf-8", errors="ignore"))
        if proc.returncode != 0:
            return None
        return stdout.decode("utf-8", errors="ignore")
    except Exception:
        return None


def _strip_text_from_html(html: str) -> str:
    import re
    # Remove tags, collapse whitespace
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _strip_text_from_latex(tex: str) -> str:
    import re
    s = tex or ""
    # Remove LaTeX commands and braces, keep math content and plain text
    s = re.sub(r"\\[a-zA-Z]+(\[[^\]]*\])?(\{[^}]*\})*", " ", s)
    s = s.replace("{", " ").replace("}", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _wrap_latex_if_needed(title: str, body_tex: str) -> str:
    s = body_tex.strip()
    # If looks like full doc, return as-is
    if "\\documentclass" in s and "\\begin{document}" in s and "\\end{document}" in s:
        return s
    # Else wrap in a minimal article template
    return "\n".join([
        "\\documentclass{article}",
        "\\usepackage{amsmath,amssymb}",
        "",
        f"\\title{{{title}}}",
        "\\author{}",
        "\\date{}",
        "",
        "\\begin{document}",
        "\\maketitle",
        "",
        s,
        "",
        "\\bibliographystyle{plain}",
        "\\bibliography{main}",
        "",
        "\\end{document}",
    ])


def _choose_models(override: Optional[str]) -> List[str]:
    # Preferred order: override -> env -> safe defaults
    candidates: List[str] = []
    if override:
        candidates.append(override)
    env_model = os.getenv("OPENAI_CONVERSION_MODEL")
    if env_model and env_model not in candidates:
        candidates.append(env_model)
    # Safe defaults
    # Prefer gpt-5 if available, then fall back to gpt-4.1 → gpt-4o → gpt-4o-mini
    for m in ["gpt-5", "gpt-4.1", "gpt-4o", "gpt-4o-mini"]:
        if m not in candidates:
            candidates.append(m)
    return candidates


async def _pandoc_latex_to_html(latex: str) -> Optional[str]:
    """Use pandoc to convert LaTeX → HTML. Returns None if pandoc missing/fails."""
    try:
        from shutil import which
        exe = which("pandoc")
        if not exe:
            return None
        import asyncio
        proc = await asyncio.create_subprocess_exec(
            exe, "-f", "latex", "-t", "html", "--wrap", "none",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin and proc.stdout
        stdout, stderr = await proc.communicate(latex.encode("utf-8", errors="ignore"))
        if proc.returncode != 0:
            return None
        return stdout.decode("utf-8", errors="ignore")
    except Exception:
        return None


@router.post("/convert/latex-to-rich", response_model=ConvertResponse)
async def convert_latex_to_rich(req: ConvertRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Fetch source paper and check access
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == req.paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can convert this paper")

    title = paper.title or "Untitled Paper"
    content_json = paper.content_json or {}
    latex_source = content_json.get("latex_source", "") if isinstance(content_json, dict) else ""

    if not latex_source:
        raise HTTPException(status_code=400, detail="Paper has no LaTeX source to convert")

    openai_error: Optional[str] = None
    html_result: Optional[str] = None

    # Strategy: strict (pandoc) or AI
    if req.strategy == "strict":
        # Use pandoc to convert LaTeX → HTML
        html_result = await _pandoc_latex_to_html(latex_source)
        if not html_result:
            # Simple fallback: strip LaTeX commands for plain text
            plain_text = _strip_text_from_latex(latex_source)
            html_result = f"<p>{plain_text}</p>" if plain_text else "<p></p>"
    else:
        # AI strategy
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                models = _choose_models(req.model)
                system = (
                    "Convert the provided LaTeX content to clean HTML with zero paraphrasing. "
                    "Preserve all text verbatim; only convert LaTeX structure to HTML equivalents. "
                    "Remove LaTeX preamble/document wrapper and return only body content."
                )
                user_content = f"Title: {title}\n\nLaTeX Source:\n{latex_source[:20000]}"
                
                last_exc: Optional[Exception] = None
                for m in models:
                    try:
                        resp = client.chat.completions.create(
                            model=m,
                            messages=[
                                {"role": "system", "content": system},
                                {"role": "user", "content": user_content}
                            ],
                            temperature=0,
                            max_tokens=4096,
                        )
                        html_result = (resp.choices[0].message.content or "").strip()
                        if html_result:
                            break
                    except Exception as e:
                        last_exc = e
                        continue
                if html_result is None and last_exc is not None:
                    openai_error = str(last_exc)
            except Exception as e:
                openai_error = str(e)
        else:
            openai_error = "OPENAI_API_KEY not configured"
        
        # Fallback to pandoc
        if not html_result:
            html_result = await _pandoc_latex_to_html(latex_source)
        if not html_result:
            plain_text = _strip_text_from_latex(latex_source)
            html_result = f"<p>{plain_text}</p>" if plain_text else "<p></p>"

    # Fidelity check
    fidelity_ok = True
    try:
        src_text = _strip_text_from_latex(latex_source)
        out_text = _strip_text_from_html(html_result)
        fidelity_ok = (src_text.strip() == out_text.strip())
    except Exception:
        fidelity_ok = False

    # Create new paper as copy in Rich Text mode
    new_title = f"{title} (Rich Text copy)"
    new_paper = ResearchPaper(
        title=new_title,
        abstract=paper.abstract,
        content=html_result,  # Converted HTML content
        content_json={"authoring_mode": "rich"},  # Rich text mode
        status=paper.status,
        paper_type=paper.paper_type,
        owner_id=current_user.id,
        is_public=paper.is_public,
        keywords=paper.keywords,
        references=paper.references,
        year=paper.year,
        doi=paper.doi,
        url=paper.url,
        source=paper.source,
        authors=paper.authors,
        journal=paper.journal,
        description=paper.description,
    )
    db.add(new_paper)
    db.commit()
    db.refresh(new_paper)

    # Duplicate references (same as rich-to-latex)
    try:
        refs = db.query(Reference).filter(Reference.owner_id == current_user.id, Reference.paper_id == paper.id).all()
        for r in refs:
            nr = Reference(
                paper_id=new_paper.id,
                owner_id=current_user.id,
                title=r.title,
                authors=r.authors,
                year=r.year,
                doi=r.doi,
                url=r.url,
                source=r.source,
                journal=r.journal,
                abstract=r.abstract,
                is_open_access=r.is_open_access,
                pdf_url=r.pdf_url,
                status=r.status,
                document_id=r.document_id,
                summary=r.summary,
                key_findings=r.key_findings,
                methodology=r.methodology,
                limitations=r.limitations,
                relevance_score=r.relevance_score,
            )
            db.add(nr)
        db.commit()
        dup_ok = True
    except Exception:
        dup_ok = False

    report: Dict[str, Any] = {
        "latex_length": len(latex_source),
        "html_length": len(html_result),
        "openai_error": openai_error,
        "references_copied": dup_ok,
        "fidelity_ok": fidelity_ok,
    }

    return ConvertResponse(new_paper_id=str(new_paper.id), title=new_title, mode="rich", report=report)


@router.post("/convert/rich-to-latex", response_model=ConvertResponse)
async def convert_rich_to_latex(req: ConvertRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Fetch source paper and check access
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == req.paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.owner_id != current_user.id:
        # Only owner can run conversion-as-copy for now
        raise HTTPException(status_code=403, detail="Only the owner can convert this paper")

    title = paper.title or "Untitled Paper"
    tiptap = paper.content_json or {}
    # Prefer HTML from paper.content (TipTap exported HTML), else build from TipTap
    html = paper.content or ""
    plain_fallback = html

    # Build counts/report baseline
    counts = _extract_counts_from_tiptap(tiptap) if tiptap else {"paragraphs": 0, "headings": 0, "lists": 0, "tables": 0, "codeblocks": 0}
    md = _tiptap_to_markdown(tiptap) if tiptap else (plain_fallback or "")

    openai_error: Optional[str] = None
    body_tex: Optional[str] = None

    # Strategy: strict (default) → Pandoc → deterministic TipTap→LaTeX; AI only if explicitly requested
    if req.strategy == "strict":
        # Prefer HTML→LaTeX via pandoc if available
        body_tex = await _pandoc_html_to_latex(html) if html else None
        if not body_tex:
            # Deterministic TipTap → LaTeX body
            body_tex = _tiptap_to_latex_strict(tiptap) if tiptap else None
        if not body_tex:
            # Last resort: treat plain text as-is
            content_text = md or plain_fallback or ""
            body_tex = content_text.replace("{", "\\{").replace("}", "\\}")
    else:
        # AI strategy
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                models = _choose_models(req.model)
                system = (
                    "Convert the provided content to LaTeX with zero paraphrasing. "
                    "Do not add, remove, or rephrase words or formulas. Preserve text verbatim; only wrap with LaTeX structure."
                )
                user_content = (
                    "Title:\n" + title + "\n\n" +
                    ("HTML (preferred):\n" + html[:20000] + "\n\n" if html else "") +
                    ("TipTap JSON (reference):\n" + json.dumps(tiptap) + "\n\n" if tiptap else "") +
                    ("Markdown (reference):\n" + md[:20000] + "\n\n" if md else "")
                )
                last_exc: Optional[Exception] = None
                for m in models:
                    try:
                        resp = client.chat.completions.create(
                            model=m,
                            messages=[
                                {"role": "system", "content": system},
                                {"role": "user", "content": user_content}
                            ],
                            temperature=0,
                            max_tokens=4096,
                        )
                        body_tex = (resp.choices[0].message.content or "").strip()
                        if body_tex:
                            break
                    except Exception as e:
                        last_exc = e
                        continue
                if body_tex is None and last_exc is not None:
                    openai_error = str(last_exc)
            except Exception as e:
                openai_error = str(e)
        else:
            openai_error = "OPENAI_API_KEY not configured"
        if not body_tex:
            # fallback to strict deterministic
            body_tex = await _pandoc_html_to_latex(html) if html else None
        if not body_tex:
            body_tex = _tiptap_to_latex_strict(tiptap) if tiptap else None
        if not body_tex:
            body_tex = (md or plain_fallback or "").replace("{", "\\{").replace("}", "\\}")

    full_tex = _wrap_latex_if_needed(title, body_tex)

    # Fidelity check: compare normalized text between HTML and LaTeX
    fidelity_ok = True
    try:
        src_text = _strip_text_from_html(html) if html else (md or "")
        out_text = _strip_text_from_latex(full_tex)
        # Allow tiny whitespace diffs only
        fidelity_ok = (src_text == out_text)
    except Exception:
        fidelity_ok = False

    # Create new paper as copy in LaTeX mode
    new_title = f"{title} (LaTeX copy)"
    new_paper = ResearchPaper(
        title=new_title,
        abstract=paper.abstract,
        content=paper.content,  # keep as-is for reference
        content_json={"authoring_mode": "latex", "latex_source": full_tex},
        status=paper.status,
        paper_type=paper.paper_type,
        owner_id=current_user.id,
        is_public=paper.is_public,
        keywords=paper.keywords,
        references=paper.references,
        year=paper.year,
        doi=paper.doi,
        url=paper.url,
        source=paper.source,
        authors=paper.authors,
        journal=paper.journal,
        description=paper.description,
    )
    db.add(new_paper)
    db.commit()
    db.refresh(new_paper)

    # Duplicate references to the new paper (best-effort)
    try:
        refs = db.query(Reference).filter(Reference.owner_id == current_user.id, Reference.paper_id == paper.id).all()
        for r in refs:
            nr = Reference(
                paper_id=new_paper.id,
                owner_id=current_user.id,
                title=r.title,
                authors=r.authors,
                year=r.year,
                doi=r.doi,
                url=r.url,
                source=r.source,
                journal=r.journal,
                abstract=r.abstract,
                is_open_access=r.is_open_access,
                pdf_url=r.pdf_url,
                status=r.status,
                document_id=r.document_id,
                summary=r.summary,
                key_findings=r.key_findings,
                methodology=r.methodology,
                limitations=r.limitations,
                relevance_score=r.relevance_score,
            )
            db.add(nr)
        db.commit()
        dup_ok = True
    except Exception:
        dup_ok = False

    report: Dict[str, Any] = {
        "source_counts": counts,
        "openai_error": openai_error,
        "tex_length": len(full_tex or ""),
        "references_copied": dup_ok,
        "fidelity_ok": fidelity_ok,
    }

    return ConvertResponse(new_paper_id=str(new_paper.id), title=new_title, mode="latex", report=report)
