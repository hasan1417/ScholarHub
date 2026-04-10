from fastapi import APIRouter, Depends, HTTPException, status, Response, Query
from app.core.config import settings
from starlette.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
import asyncio
import hashlib
import io
import json
import logging
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)
from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.research_paper import ResearchPaper
from sqlalchemy.orm import Session
from app.services.compilation_version_manager import compilation_version_manager
from app.services.subscription_service import SubscriptionService, get_model_credit_cost
from app.services.submission_builder import (
    get_venue_configs,
    get_venue_config,
    validate_for_venue,
    build_submission_package,
    _generate_bibtex,
    VENUE_CONFIGS,
)
from app.models.paper_member import PaperMember
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.api.utils.openrouter_access import resolve_openrouter_key_for_user, resolve_openrouter_key_for_project
from openai import AsyncOpenAI

router = APIRouter()


ARTIFACT_ROOT = Path(os.getenv("LATEX_ARTIFACT_ROOT", Path("uploads") / "latex_cache")).resolve()
ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)

# Directory containing bundled LaTeX style files for conference templates
LATEX_STYLES_DIR = Path(__file__).parent.parent.parent / "assets" / "latex_styles"


def _copy_style_files(target_dir: Path) -> None:
    """Copy bundled LaTeX style files to the compilation directory."""
    if not LATEX_STYLES_DIR.exists():
        return
    try:
        for style_file in LATEX_STYLES_DIR.glob("*"):
            if style_file.suffix in (".sty", ".bst"):
                shutil.copy2(style_file, target_dir / style_file.name)
    except Exception as e:
        logger.warning("Failed to copy style files to %s: %s", target_dir, e)


class CompileRequest(BaseModel):
    latex_source: str
    paper_id: Optional[str] = None
    engine: Optional[str] = "pdflatex"
    job_label: Optional[str] = None
    include_bibtex: Optional[bool] = True
    latex_files: Optional[Dict[str, str]] = None  # Multi-file: {"intro.tex": "...", ...}

    @field_validator("paper_id")
    @classmethod
    def validate_paper_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            from uuid import UUID

            UUID(v)
        return v


class FixErrorsRequest(BaseModel):
    latex_source: str = Field(..., max_length=500000)
    error_log: str = Field(..., max_length=50000)
    paper_id: Optional[str] = None
    project_id: Optional[str] = None


_ENGINE_VERSION = "texlive-pdflatex-v1"


def _sha256(text: str, extra_files: Optional[Dict[str, str]] = None, paper_id: Optional[str] = None) -> str:
    h = hashlib.sha256()
    h.update(_ENGINE_VERSION.encode("utf-8"))
    h.update(text.encode("utf-8", errors="ignore"))
    if extra_files:
        for name in sorted(extra_files.keys()):
            h.update(name.encode("utf-8", errors="ignore"))
            h.update(extra_files[name].encode("utf-8", errors="ignore"))
    # Include bundled style file mtimes so cache invalidates when they change
    if LATEX_STYLES_DIR.exists():
        for f in sorted(LATEX_STYLES_DIR.iterdir(), key=lambda p: p.name):
            if f.suffix in ('.sty', '.bst'):
                h.update(f.name.encode("utf-8"))
                h.update(str(f.stat().st_mtime_ns).encode("utf-8"))
    # Include user-uploaded support file mtimes
    if paper_id:
        support_dir = Path("uploads") / "papers" / paper_id / "support"
        if support_dir.exists():
            for f in sorted(support_dir.iterdir(), key=lambda p: p.name):
                if f.suffix in ('.cls', '.sty', '.bst', '.bib', '.def', '.fd'):
                    h.update(f.name.encode("utf-8"))
                    h.update(str(f.stat().st_mtime_ns).encode("utf-8"))
    return h.hexdigest()


def _artifact_paths(content_hash: str) -> Dict[str, Path]:
    out_dir = ARTIFACT_ROOT / content_hash
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "dir": out_dir,
        "tex": out_dir / "main.tex",
        # latexmk outputs <input_basename>.pdf; we use main.tex → main.pdf
        "pdf": out_dir / "main.pdf",
        "log": out_dir / "compile.log",
    }


def _parse_latex_errors(log_lines: list[str]) -> list[dict]:
    """Parse LaTeX log lines for structured errors with line numbers.

    Scans for lines starting with `!` (LaTeX error indicator) and looks
    ahead for `l.NNN` patterns to extract line numbers and context.
    """
    errors: list[dict] = []
    i = 0
    while i < len(log_lines):
        line = log_lines[i]
        if line.startswith('!'):
            message = line[1:].strip()
            err: dict = {"message": message}
            # Look ahead up to 5 lines for `l.NNN` pattern (line number)
            for j in range(i + 1, min(i + 6, len(log_lines))):
                look = log_lines[j]
                m = re.match(r'^l\.(\d+)\s*(.*)', look)
                if m:
                    err["line"] = int(m.group(1))
                    ctx = m.group(2).strip()
                    if ctx:
                        err["context"] = ctx
                    break
            errors.append(err)
        i += 1
    return errors


_UNICODE_ESCAPE_RE = re.compile(r'\\u([0-9a-fA-F]{4})(?![0-9a-fA-F])')


def _decode_unicode_escapes(source: str) -> str:
    r"""Convert \uXXXX escape sequences to actual UTF-8 characters.

    AI models sometimes emit Python/JS-style unicode escapes (e.g. \u0641)
    instead of real UTF-8 Arabic characters.  LaTeX doesn't understand these,
    so we decode them before compilation.  LaTeX commands that happen to start
    with ``\u`` (like \usepackage, \underline) are left untouched because the
    4 hex digits are followed by more letters, making them part of a longer
    command name.
    """
    def _replace(m: re.Match) -> str:
        # If the character right after the 4 hex digits is a letter, this is
        # part of a LaTeX command (e.g. \usepackage) — leave it alone.
        end = m.end()
        if end < len(source) and source[end].isalpha():
            return m.group(0)
        return chr(int(m.group(1), 16))
    return _UNICODE_ESCAPE_RE.sub(_replace, source)


_ARABIC_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
_INPUTENC_RE = re.compile(r'\\usepackage\[.*?\]\{inputenc\}')
_FONTENC_RE = re.compile(r'\\usepackage\[.*?\]\{fontenc\}')


def _inject_arabic_support(source: str) -> str:
    """Auto-detect Arabic text/RTL commands and inject bidi+fontspec packages."""
    has_arabic = (
        bool(_ARABIC_RE.search(source))
        or r'\RL{' in source
        or r'\begin{Arabic}' in source
    )
    if not has_arabic:
        return source

    # Already has RTL support
    if r'\usepackage{bidi}' in source or r'\usepackage{polyglossia}' in source:
        return source

    # fontspec conflicts with inputenc/fontenc — remove them
    source = _INPUTENC_RE.sub(r'% \g<0>  % disabled for fontspec/bidi', source)
    source = _FONTENC_RE.sub(r'% \g<0>  % disabled for fontspec/bidi', source)

    # Build injection block
    lines = []
    if r'\usepackage{fontspec}' not in source:
        lines.append(r'\usepackage{fontspec}')
    lines.append(r'\usepackage{bidi}')
    if r'\arabicfont' not in source:
        lines.append(r'\newfontfamily\arabicfont[Script=Arabic]{Amiri}')
    # Make \RL automatically use the Arabic font so glyphs actually render
    lines.append(r'\let\origRL\RL')
    lines.append(r'\renewcommand{\RL}[1]{{\arabicfont\origRL{#1}}}')
    inject = '\n'.join(lines) + '\n'

    # Insert just before \begin{document}
    idx = source.find(r'\begin{document}')
    if idx != -1:
        return source[:idx] + inject + source[idx:]
    logger.warning("Arabic text detected but no \\begin{document} found; skipping RTL injection")
    return source


def _ensure_body_content(source: str) -> str:
    """Ensure the document body is not completely empty to keep the compiler happy."""
    try:
        lower = source.lower()
        begin_token = "\\begin{document}"
        start = lower.find(begin_token)
        if start != -1 and _document_body_empty(source):
            insertion_point = start + len(begin_token)
            return f"{source[:insertion_point]}\n\\mbox{{}}%\n{source[insertion_point:]}"
    except Exception as e:
        logger.warning("Failed to ensure body content: %s", e)
    return source


def _document_body_empty(source: str) -> bool:
    try:
        lower = source.lower()
        begin_token = "\\begin{document}"
        end_token = "\\end{document}"
        start = lower.find(begin_token)
        end = lower.find(end_token, start + len(begin_token)) if start != -1 else -1
        if start != -1 and end != -1:
            body = source[start + len(begin_token):end]
            cleaned_lines = []
            for raw_line in body.splitlines():
                stripped = raw_line.split('%', 1)[0]
                cleaned_lines.append(stripped)
            cleaned = ''.join(cleaned_lines).strip()
            return len(cleaned) == 0
    except Exception as e:
        logger.warning("Failed to check if document body is empty: %s", e)
    return False


def _needs_xelatex(source: str) -> bool:
    """Check if the document requires XeLaTeX (Arabic/RTL, fontspec, etc.)."""
    has_arabic = (
        bool(_ARABIC_RE.search(source))
        or r'\RL{' in source
        or r'\begin{Arabic}' in source
    )
    has_fontspec = (
        r'\usepackage{fontspec}' in source
        or r'\usepackage{polyglossia}' in source
    )
    return has_arabic or has_fontspec


async def _run_latexmk(out_dir: Path, tex_path: Path, use_xelatex: bool = False):
    """Run latexmk to compile the given tex file, streaming output lines."""
    from shutil import which
    exe = which("latexmk")
    if not exe:
        raise FileNotFoundError("latexmk not found in PATH. Install via 'apt-get install latexmk texlive-latex-base'")

    engine_flag = "-xelatex" if use_xelatex else "-pdf"
    cmd = [
        exe,
        engine_flag,
        "-interaction=nonstopmode",
        "-synctex=1",
        "-file-line-error",
        f"-outdir={str(out_dir)}",
        str(tex_path.name),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(out_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            yield line.decode(errors="ignore").rstrip("\n")
    finally:
        await proc.wait()


@router.post("/latex/compile")
async def compile_latex(request: CompileRequest, current_user: User = Depends(get_current_user), save_version: bool = Query(False), db: Session = Depends(get_db)):
    if not request.latex_source or len(request.latex_source.strip()) < 5:
        if not request.paper_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="latex_source is empty")
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == request.paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        fallback = ''
        if paper.content_json and isinstance(paper.content_json, dict):
            fallback = paper.content_json.get('latex_source') or paper.content or ''
        else:
            fallback = paper.content or ''
        if not fallback or len(fallback.strip()) < 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="latex_source is empty")
        request.latex_source = fallback

    if _document_body_empty(request.latex_source):
        return {
            "buildId": request.job_label or f"empty-{int(time.time()*1000)}",
            "success": False,
            "serverElapsed": 0.0,
            "errorCount": 1,
            "pdf_url": None,
            "commitId": None,
            "message": "Document has no content to compile."
        }

    effective_source = _ensure_body_content(request.latex_source)
    effective_source = _decode_unicode_escapes(effective_source)
    effective_source = _inject_arabic_support(effective_source)
    content_hash = _sha256(effective_source, request.latex_files, request.paper_id)
    paths = _artifact_paths(content_hash)

    # Write source to cache dir (always refresh the tex file for transparency)
    try:
        await asyncio.to_thread(paths["dir"].mkdir, parents=True, exist_ok=True)
        # Copy bundled conference style files (.sty, .bst) for template support
        await asyncio.to_thread(_copy_style_files, paths["dir"])
        # Copy user-uploaded support files (.cls, .sty, .bst, etc.)
        paper_id = request.paper_id
        if paper_id:
            def _copy_support_files_sync():
                support_src = Path("uploads") / "papers" / paper_id / "support"
                if support_src.exists():
                    for f in support_src.iterdir():
                        if f.suffix in ('.cls', '.sty', '.bst', '.bib', '.def', '.fd'):
                            shutil.copy2(f, paths["dir"] / f.name)
            await asyncio.to_thread(_copy_support_files_sync)
        # Clear cached aux/bbl files to force fresh bibliography build
        def _clear_aux_files():
            for ext in [".aux", ".bbl", ".blg"]:
                cached_file = paths["dir"] / f"main{ext}"
                if cached_file.exists():
                    cached_file.unlink()
        await asyncio.to_thread(_clear_aux_files)
        await asyncio.to_thread(paths["tex"].write_text, effective_source, encoding="utf-8")
        # Write additional multi-file sources
        if request.latex_files:
            for fname, content in request.latex_files.items():
                safe_name = Path(fname).name
                if not safe_name.endswith('.tex') or safe_name == 'main.tex':
                    continue
                target_path = paths["dir"] / safe_name
                if not target_path.resolve().is_relative_to(paths["dir"].resolve()):
                    continue
                await asyncio.to_thread(target_path.write_text, content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to prepare source: {e}")

    synctex_check = paths["dir"] / "main.synctex.gz"
    cached = (
        (await asyncio.to_thread(paths["pdf"].exists))
        and (await asyncio.to_thread(synctex_check.exists))
    )
    commit_id = None
    # If cached and save_version requested, save a compiled version commit
    if cached and save_version and request.paper_id:
      try:
        logs = ''
        try:
            log_exists = await asyncio.to_thread(paths["log"].exists)
            logs = (await asyncio.to_thread(paths["log"].read_text, encoding='utf-8', errors='ignore')) if log_exists else ''
        except Exception as e:
            logger.warning("Failed to read compile log for version save: %s", e)
            logs = ''
        pdf_url = f"/api/v1/latex/artifacts/{content_hash}/main.pdf"
        commit = compilation_version_manager.saveCompiledVersion(request.paper_id, current_user.id, request.latex_source, pdf_url, logs)
        if commit:
            commit_id = str(commit.id)
      except Exception as e:
        logger.warning("Failed to save compiled version (cache hit, non-stream): %s", e)
        commit_id = None

    build_id = request.job_label or f"{content_hash}-{int(time.time()*1000)}"
    resp = {
        "buildId": build_id,
        "success": bool(cached),
        "serverElapsed": 0.0,
        "errorCount": 0,
        "pdf_url": f"/api/v1/latex/artifacts/{content_hash}/main.pdf" if cached else None,
        "commitId": commit_id,
    }
    return resp


def _unwrap_latex_command(source: str, cmd: str) -> str:
    r"""Remove \cmd{...} wrappers, keeping brace contents. Handles nested braces."""
    result: list[str] = []
    i = 0
    prefix = cmd + '{'
    plen = len(prefix)
    while i < len(source):
        if source[i:i + plen] == prefix:
            i += plen
            depth = 1
            start = i
            while i < len(source) and depth > 0:
                if source[i] == '{':
                    depth += 1
                elif source[i] == '}':
                    depth -= 1
                if depth > 0:
                    i += 1
            result.append(source[start:i])
            i += 1  # skip closing }
        else:
            result.append(source[i])
            i += 1
    return ''.join(result)


_XELATEX_LINE_PATTERNS = (
    r'\usepackage{fontspec}',
    r'\usepackage{bidi}',
    r'\usepackage{polyglossia}',
    r'\newfontfamily',
    r'\let\origRL',
    r'\renewcommand{\RL}',
    r'\setmainlanguage',
    r'\setotherlanguage',
)


def _strip_xelatex_for_pandoc(source: str) -> str:
    r"""Strip XeLaTeX-specific Arabic/RTL commands for pandoc compatibility.

    Pandoc handles raw UTF-8 Arabic text natively in DOCX but chokes on
    fontspec/bidi packages and \RL{} commands.  Remove these wrappers while
    preserving the Arabic text content.
    """
    # Unwrap \RL{...} → contents
    source = _unwrap_latex_command(source, r'\RL')
    # Unwrap \begin{Arabic}...\end{Arabic} → contents
    source = source.replace(r'\begin{Arabic}', '').replace(r'\end{Arabic}', '')

    # Remove XeLaTeX-specific package/command lines; restore commented-out
    # inputenc/fontenc that _inject_arabic_support may have disabled.
    lines = source.split('\n')
    filtered: list[str] = []
    for line in lines:
        stripped = line.strip()
        # Restore lines commented out by _inject_arabic_support
        if stripped.startswith('%') and 'disabled for fontspec' in stripped:
            restored = stripped.lstrip('% ').split('%')[0].strip()
            if restored:
                filtered.append(restored)
            continue
        if any(pat in stripped for pat in _XELATEX_LINE_PATTERNS):
            continue
        filtered.append(line)
    return '\n'.join(filtered)


class ExportDocxRequest(BaseModel):
    latex_source: str
    paper_id: Optional[str] = None
    include_bibtex: Optional[bool] = True
    latex_files: Optional[Dict[str, str]] = None


@router.post("/latex/export-docx")
async def export_docx(request: ExportDocxRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Convert LaTeX source to DOCX via pandoc."""
    if request.paper_id:
        try:
            uuid.UUID(request.paper_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid paper_id")
    # Validate / fallback source
    if not request.latex_source or len(request.latex_source.strip()) < 5:
        if not request.paper_id:
            raise HTTPException(status_code=400, detail="latex_source is empty")
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == request.paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        fallback = ''
        if paper.content_json and isinstance(paper.content_json, dict):
            fallback = paper.content_json.get('latex_source') or paper.content or ''
        else:
            fallback = paper.content or ''
        if not fallback or len(fallback.strip()) < 5:
            raise HTTPException(status_code=400, detail="latex_source is empty")
        request.latex_source = fallback

    effective_source = _decode_unicode_escapes(request.latex_source)
    effective_source = _strip_xelatex_for_pandoc(effective_source)
    effective_source = _ensure_body_content(effective_source)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "main.tex").write_text(effective_source, encoding="utf-8")

        # Write extra .tex files
        if request.latex_files:
            for fname, content in request.latex_files.items():
                safe_name = Path(fname).name
                if not safe_name.endswith('.tex') or safe_name == 'main.tex':
                    continue
                (tmp / safe_name).write_text(content, encoding="utf-8")

        # Copy figures
        if request.paper_id:
            figures_src = Path("uploads") / "papers" / request.paper_id / "figures"
            if figures_src.exists():
                shutil.copytree(figures_src, tmp / "figures")

        # Copy or generate .bib
        if request.paper_id:
            paper_dir = Path("uploads") / "papers" / request.paper_id
            copied_bib = False
            if paper_dir.exists():
                for bib_file in paper_dir.glob("*.bib"):
                    shutil.copy2(bib_file, tmp / bib_file.name)
                    copied_bib = True
            if not copied_bib and request.include_bibtex:
                try:
                    bib = _generate_bibtex_for_paper(db, current_user.id, request.paper_id)
                    (tmp / "main.bib").write_text(bib, encoding="utf-8")
                except Exception as e:
                    logger.warning("Failed to generate bibtex for DOCX export: %s", e)

        _copy_style_files(tmp)

        # Run pandoc
        proc = await asyncio.create_subprocess_exec(
            "pandoc", "main.tex", "-o", "output.docx",
            cwd=str(tmp),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            raise HTTPException(status_code=504, detail="DOCX conversion timed out")

        if proc.returncode != 0:
            err_msg = stderr.decode(errors="ignore")[:500] if stderr else "unknown error"
            raise HTTPException(status_code=500, detail=f"Pandoc conversion failed: {err_msg}")

        docx_path = tmp / "output.docx"
        if not docx_path.exists():
            raise HTTPException(status_code=500, detail="Pandoc did not produce output.docx")

        docx_bytes = docx_path.read_bytes()

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=paper.docx"},
    )


class ExportSourceZipRequest(BaseModel):
    latex_source: str
    paper_id: Optional[str] = None
    include_bibtex: Optional[bool] = True
    latex_files: Optional[Dict[str, str]] = None


@router.post("/latex/export-source-zip")
async def export_source_zip(request: ExportSourceZipRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Package all project source files into a downloadable ZIP archive."""
    if request.paper_id:
        try:
            uuid.UUID(request.paper_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid paper_id")
    # Validate / fallback source
    if not request.latex_source or len(request.latex_source.strip()) < 5:
        if not request.paper_id:
            raise HTTPException(status_code=400, detail="latex_source is empty")
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == request.paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        fallback = ''
        if paper.content_json and isinstance(paper.content_json, dict):
            fallback = paper.content_json.get('latex_source') or paper.content or ''
        else:
            fallback = paper.content or ''
        if not fallback or len(fallback.strip()) < 5:
            raise HTTPException(status_code=400, detail="latex_source is empty")
        request.latex_source = fallback

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "main.tex").write_text(request.latex_source, encoding="utf-8")

        # Write extra .tex files
        if request.latex_files:
            for fname, content in request.latex_files.items():
                safe_name = Path(fname).name
                if not safe_name.endswith('.tex') or safe_name == 'main.tex':
                    continue
                (tmp / safe_name).write_text(content, encoding="utf-8")

        # Copy figures
        if request.paper_id:
            figures_src = Path("uploads") / "papers" / request.paper_id / "figures"
            if figures_src.exists():
                shutil.copytree(figures_src, tmp / "figures")

        # Copy or generate .bib
        if request.paper_id:
            paper_dir = Path("uploads") / "papers" / request.paper_id
            copied_bib = False
            if paper_dir.exists():
                for bib_file in paper_dir.glob("*.bib"):
                    shutil.copy2(bib_file, tmp / bib_file.name)
                    copied_bib = True
            if not copied_bib and request.include_bibtex:
                try:
                    bib = _generate_bibtex_for_paper(db, current_user.id, request.paper_id)
                    (tmp / "main.bib").write_text(bib, encoding="utf-8")
                except Exception as e:
                    logger.warning("Failed to generate bibtex for source ZIP export: %s", e)

        _copy_style_files(tmp)

        # Create ZIP in memory
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(tmpdir):
                for file in files:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, tmpdir)
                    zf.write(abs_path, rel_path)
        zip_bytes = buf.getvalue()

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=paper-source.zip"},
    )


@router.get("/latex/artifacts/{content_hash}/{filename}")
async def get_artifact(content_hash: str, filename: str, current_user: User = Depends(get_current_user)):
    paths = _artifact_paths(content_hash)
    target = paths["dir"] / filename
    def _validate_path():
        return target.resolve().is_relative_to(paths["dir"].resolve())
    if not await asyncio.to_thread(_validate_path):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not await asyncio.to_thread(target.exists):
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(str(target))


@router.post("/latex/compile/stream")
async def compile_latex_stream(request: CompileRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db), save_version: bool = Query(False)):
    if not request.latex_source or len(request.latex_source.strip()) < 5:
        if not request.paper_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="latex_source is empty")
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == request.paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        fallback = ''
        if paper.content_json and isinstance(paper.content_json, dict):
            fallback = paper.content_json.get('latex_source') or paper.content or ''
        else:
            fallback = paper.content or ''
        if not fallback or len(fallback.strip()) < 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="latex_source is empty")
        request.latex_source = fallback

    if _document_body_empty(request.latex_source):
        async def empty_stream():
            err = {"type": "error", "message": "Document has no content to compile."}
            yield f"data: {json.dumps(err)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        headers = {
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
        return StreamingResponse(empty_stream(), media_type='text/event-stream', headers=headers)

    effective_source = _ensure_body_content(request.latex_source)
    effective_source = _decode_unicode_escapes(effective_source)
    effective_source = _inject_arabic_support(effective_source)
    content_hash = _sha256(effective_source, request.latex_files, request.paper_id)
    paths = _artifact_paths(content_hash)

    # Always write the .tex (and extra files if multi-file)
    try:
        await asyncio.to_thread(paths["dir"].mkdir, parents=True, exist_ok=True)
        # Copy bundled conference style files (.sty, .bst) for template support
        await asyncio.to_thread(_copy_style_files, paths["dir"])
        # Copy user-uploaded support files (.cls, .sty, .bst, etc.)
        paper_id_stream = request.paper_id
        if paper_id_stream:
            def _copy_support_files_stream():
                support_src = Path("uploads") / "papers" / paper_id_stream / "support"
                if support_src.exists():
                    for f in support_src.iterdir():
                        if f.suffix in ('.cls', '.sty', '.bst', '.bib', '.def', '.fd'):
                            shutil.copy2(f, paths["dir"] / f.name)
            await asyncio.to_thread(_copy_support_files_stream)
        # Clear cached aux/bbl files to force fresh bibliography build
        # This prevents conflicts when switching templates/bib styles
        def _clear_aux_files():
            for ext in [".aux", ".bbl", ".blg"]:
                cached_file = paths["dir"] / f"main{ext}"
                if cached_file.exists():
                    cached_file.unlink()
        await asyncio.to_thread(_clear_aux_files)
        await asyncio.to_thread(paths["tex"].write_text, effective_source, encoding="utf-8")
        # Write additional multi-file sources
        # Use request.latex_files if provided, otherwise fall back to paper.latex_files from DB
        extra_files = request.latex_files
        if not extra_files and request.paper_id:
            try:
                paper_obj = db.query(ResearchPaper).filter(ResearchPaper.id == request.paper_id).first()
                if paper_obj and isinstance(paper_obj.latex_files, dict):
                    extra_files = paper_obj.latex_files
            except Exception:
                pass
        if extra_files:
            for fname, content in extra_files.items():
                # Sanitize filename: only allow .tex files in the compile dir
                safe_name = Path(fname).name
                if not safe_name.endswith('.tex') or safe_name == 'main.tex':
                    continue
                target_path = paths["dir"] / safe_name
                if not target_path.resolve().is_relative_to(paths["dir"].resolve()):
                    continue
                await asyncio.to_thread(target_path.write_text, content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to prepare source: {e}")

    async def event_stream():
        t0 = time.time()
        payload_size = len(request.latex_source or '')
        engine = (request.engine or 'pdflatex')
        status_str = 'unknown'
        exit_code = None
        build_id = request.job_label or f"{content_hash}-{int(time.time()*1000)}"
        error_count = 0
        logs_buf = []

        # Copy figures directory if it exists for this paper (before checking cache)
        copied_bib = False
        if request.paper_id:
            try:
                figures_src = Path("uploads") / "papers" / request.paper_id / "figures"
                def _copy_figures():
                    if figures_src.exists():
                        figures_dst = paths["dir"] / "figures"
                        if figures_dst.exists():
                            shutil.rmtree(figures_dst)
                        shutil.copytree(figures_src, figures_dst)
                await asyncio.to_thread(_copy_figures)
            except Exception as e:
                logger.warning("Failed to copy figures for paper %s: %s", request.paper_id, e)

            # Copy .bib files if they exist for this paper
            try:
                paper_dir = Path("uploads") / "papers" / request.paper_id
                def _copy_bib_files():
                    found = False
                    for bib_file in paper_dir.glob("*.bib"):
                        bib_dst = paths["dir"] / bib_file.name
                        shutil.copy2(bib_file, bib_dst)
                        found = True
                    return found
                copied_bib = await asyncio.to_thread(_copy_bib_files)
            except Exception as e:
                logger.warning("Failed to copy .bib files for paper %s: %s", request.paper_id, e)

        # Cache hit — also require synctex.gz so SyncTeX works
        synctex_path = paths["dir"] / "main.synctex.gz"
        cached = (
            (await asyncio.to_thread(paths["pdf"].exists))
            and (await asyncio.to_thread(synctex_path.exists))
            and not copied_bib
        )
        if cached:
            payload = {"type": "cache", "message": "Cache hit", "hash": content_hash}
            yield f"data: {json.dumps(payload)}\n\n"
            commit_id = None
            if save_version and request.paper_id:
                try:
                    pdf_url = f"/api/v1/latex/artifacts/{content_hash}/main.pdf"
                    logs = ''
                    try:
                        log_exists = await asyncio.to_thread(paths["log"].exists)
                        logs = (await asyncio.to_thread(paths["log"].read_text, encoding='utf-8', errors='ignore')) if log_exists else ''
                    except Exception as e:
                        logger.warning("Failed to read compile log for version save (stream cache hit): %s", e)
                        logs = ''
                    commit = compilation_version_manager.saveCompiledVersion(request.paper_id, current_user.id, request.latex_source, pdf_url, logs)
                    if commit:
                        commit_id = str(commit.id)
                except Exception as e:
                    logger.warning("Failed to save compiled version (stream cache hit): %s", e)
                    commit_id = None
            final = {"type": "final", "pdf_url": f"/api/v1/latex/artifacts/{content_hash}/main.pdf", "hash": content_hash, "elapsed": round(time.time()-t0,2), "buildId": build_id, "errorCount": 0, "errors": [], "commitId": commit_id}
            yield f"data: {json.dumps(final)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            status_str = 'cached'
            if settings.ENABLE_METRICS:
                try:
                    logger.info("[metrics] compile buildId=%s payload_size=%d engine=%s status=%s elapsed=%.2f errorCount=0", build_id, payload_size, engine, status_str, round(time.time()-t0, 2))
                except Exception:
                    pass
            return

        # Compile via latexmk (TeX Live)
        start = time.time()
        try:
            # Optionally write main.bib from user's paper references
            main_bib_path = paths["dir"] / "main.bib"
            main_bib_exists = await asyncio.to_thread(main_bib_path.exists)
            if request.paper_id and ((request.include_bibtex and not copied_bib) or not main_bib_exists):
                try:
                    bib = _generate_bibtex_for_paper(db, current_user.id, request.paper_id)
                    await asyncio.to_thread(main_bib_path.write_text, bib, encoding="utf-8")
                    yield f"data: {json.dumps({'type': 'log', 'line': '[bibtex] Wrote main.bib from paper references'})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'log', 'line': f'[bibtex] Skipped: {e}'})}\n\n"

            # Determine engine: xelatex for Arabic/RTL/fontspec, pdflatex otherwise
            use_xelatex = _needs_xelatex(effective_source)

            # Stream compile logs (latexmk handles bibtex passes automatically)
            async for line in _run_latexmk(paths["dir"], paths["tex"], use_xelatex=use_xelatex):
                try:
                    def _append_log(log_line):
                        with paths["log"].open("a", encoding="utf-8") as lf:
                            lf.write(log_line + "\n")
                    await asyncio.to_thread(_append_log, line)
                except Exception as e:
                    logger.warning("Failed to write compile log: %s", e)
                logs_buf.append(line)
                if 'error' in (line or '').lower():
                    error_count += 1
                payload = {"type": "log", "line": line}
                yield f"data: {json.dumps(payload)}\n\n"

            # Check result
            if await asyncio.to_thread(paths["pdf"].exists):
                elapsed = round(time.time() - start, 2)
                commit_id = None
                if save_version and request.paper_id:
                    try:
                        pdf_url = f"/api/v1/latex/artifacts/{content_hash}/main.pdf"
                        commit = compilation_version_manager.saveCompiledVersion(request.paper_id, current_user.id, request.latex_source, pdf_url, "\n".join(logs_buf[-5000:]))
                        if commit:
                            commit_id = str(commit.id)
                    except Exception as e:
                        logger.warning("Failed to save compiled version (stream compile): %s", e)
                        commit_id = None
                structured_errors = _parse_latex_errors(logs_buf)
                final = {
                    "type": "final",
                    "pdf_url": f"/api/v1/latex/artifacts/{content_hash}/main.pdf",
                    "hash": content_hash,
                    "elapsed": elapsed,
                    "buildId": build_id,
                    "errorCount": error_count,
                    "errors": structured_errors,
                    "commitId": commit_id,
                }
                yield f"data: {json.dumps(final)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                status_str = 'success'
            else:
                err = {"type": "error", "message": "Compilation failed: main.pdf not found"}
                yield f"data: {json.dumps(err)}\n\n"
                status_str = 'error'
                error_count += 1
        except FileNotFoundError as fe:
            err = {"type": "error", "message": str(fe)}
            yield f"data: {json.dumps(err)}\n\n"
            status_str = 'error'
            error_count += 1
        except Exception as e:
            err = {"type": "error", "message": f"Compilation error: {e}"}
            yield f"data: {json.dumps(err)}\n\n"
            status_str = 'error'
            error_count += 1
        finally:
            if settings.ENABLE_METRICS:
                try:
                    total = round(time.time()-t0, 2)
                    logger.info("[metrics] compile buildId=%s payload_size=%d engine=%s status=%s elapsed=%.2f exit_code=%s errorCount=%d", build_id, payload_size, engine, status_str, total, exit_code, error_count)
                except Exception:
                    pass

    headers = {
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    }
    return StreamingResponse(event_stream(), media_type='text/event-stream', headers=headers)


# Snapshot materialization removed; LaTeX source must be provided directly


def _generate_bibtex_for_paper(db: Session, owner_id: Any, paper_id: str) -> str:
    """Thin wrapper around submission_builder._generate_bibtex."""
    return _generate_bibtex(db, owner_id, paper_id)


# ---------------------------------------------------------------------------
# Writing Quality Analyzer
# ---------------------------------------------------------------------------

class WritingAnalysisRequest(BaseModel):
    latex_source: str
    paper_id: Optional[str] = None
    venue: Optional[str] = None  # e.g. "ieee", "acm", "springer", "nature", "arxiv"
    latex_files: Optional[Dict[str, str]] = None


class WritingIssue(BaseModel):
    type: str  # "citation_density", "hedging", "structure", "venue"
    severity: str  # "error", "warning", "info"
    message: str
    line: Optional[int] = None
    suggestion: Optional[str] = None


class WritingAnalysisResponse(BaseModel):
    issues: list[WritingIssue]
    stats: dict
    score: int


# Regex patterns for writing analysis
_SECTION_CMD_RE = re.compile(r'\\(?:section|subsection|subsubsection)\*?\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}')
_CITE_RE = re.compile(r'\\cite[tp]?\*?\{[^}]+\}')
_COMMENT_LINE_RE = re.compile(r'(?<!\\)%.*$', re.MULTILINE)

# Claim indicators that typically require citation support
_CLAIM_INDICATORS = [
    "shows that", "demonstrates", "has been proven", "according to",
    "studies have found", "research indicates", "it is known that",
    "evidence suggests", "has shown", "have shown", "was demonstrated",
    "is well established", "is well known", "previous work",
    "prior research", "existing literature", "has been reported",
    "has been observed", "studies suggest", "recent work",
]

# Hedging: absolute terms and their suggested alternatives
_HEDGING_MAP = {
    "proves": "suggests/demonstrates",
    "definitely": "likely",
    "clearly shows": "indicates",
    "is certain": "appears likely",
    "always": "typically/often",
    "never": "rarely/seldom",
    "undoubtedly": "likely",
    "obviously": "notably",
    "without doubt": "with high confidence",
    "unquestionably": "arguably",
}

# Standard academic sections (normalized lowercase)
_REQUIRED_SECTIONS = [
    ("introduction", {"introduction", "background"}),
    ("related work", {"related work", "literature review", "background"}),
    ("methodology", {"methodology", "methods", "method", "approach", "proposed method", "proposed approach"}),
    ("results", {"results", "experiments", "experimental results", "evaluation"}),
    ("discussion", {"discussion", "analysis"}),
    ("conclusion", {"conclusion", "conclusions", "concluding remarks", "summary"}),
]

# Expected section order (by group index in _REQUIRED_SECTIONS)
_SECTION_ORDER = ["introduction", "related work", "methodology", "results", "discussion", "conclusion"]

# Venue-specific abstract word limits (derived from submission_builder VENUE_CONFIGS)
_VENUE_ABSTRACT_LIMITS: Dict[str, int] = {
    k: v["abstract_max_words"]
    for k, v in VENUE_CONFIGS.items()
    if v.get("abstract_max_words")
}


def _strip_comments(source: str) -> str:
    """Remove LaTeX comments (lines starting with % or inline %)."""
    return _COMMENT_LINE_RE.sub('', source)


def _extract_body(source: str) -> tuple[str, int]:
    """Extract content between \\begin{document} and \\end{document}.

    Returns (body_text, line_offset) where line_offset is the number of
    newlines before the start of the body so that callers can convert
    body-relative line numbers to source-absolute line numbers.
    """
    lower = source.lower()
    begin = lower.find('\\begin{document}')
    end = lower.find('\\end{document}')
    if begin == -1:
        return source, 0
    start = begin + len('\\begin{document}')
    # Count newlines in everything up to (and including) \begin{document} line
    offset = source[:start].count('\n')
    if end == -1:
        return source[start:], offset
    return source[start:end], offset


def _extract_abstract(source: str) -> str:
    """Extract text within \\begin{abstract}...\\end{abstract}."""
    lower = source.lower()
    begin = lower.find('\\begin{abstract}')
    end = lower.find('\\end{abstract}')
    if begin == -1 or end == -1:
        return ""
    start = begin + len('\\begin{abstract}')
    return source[start:end].strip()


def _split_paragraphs(body: str, line_offset: int = 0) -> list[tuple[str, int]]:
    """Split body into paragraphs with approximate line numbers.

    Returns list of (paragraph_text, start_line_number).
    ``line_offset`` is added to every reported line number so that results
    are relative to the full source file, not just the body.
    """
    paragraphs = []
    current_lines: list[str] = []
    current_start = 1
    for i, line in enumerate(body.split('\n'), 1):
        stripped = line.strip()
        # Paragraph break on blank line or section command
        if stripped == '' or _SECTION_CMD_RE.match(stripped):
            if current_lines:
                text = ' '.join(current_lines)
                paragraphs.append((text, current_start + line_offset))
                current_lines = []
            current_start = i + 1
        else:
            if not current_lines:
                current_start = i
            current_lines.append(stripped)
    if current_lines:
        text = ' '.join(current_lines)
        paragraphs.append((text, current_start + line_offset))
    return paragraphs


def _plain_text(text: str) -> str:
    """Very rough LaTeX-to-plain-text for word counting. Strips commands."""
    # Remove \command{...} but keep content inside braces
    t = re.sub(r'\\[a-zA-Z]+\*?\{', '', text)
    t = t.replace('{', '').replace('}', '')
    # Remove remaining backslash commands
    t = re.sub(r'\\[a-zA-Z]+\*?', '', t)
    # Remove special chars
    t = re.sub(r'[~$&^_#]', ' ', t)
    return t


def _total_words(text: str) -> int:
    return len(_plain_text(text).split())


def _analyze_writing(source: str, venue: Optional[str] = None) -> WritingAnalysisResponse:
    """Perform deterministic writing quality analysis on LaTeX source."""
    issues: list[WritingIssue] = []
    clean = _strip_comments(source)
    body, body_line_offset = _extract_body(clean)
    abstract_text = _extract_abstract(clean)

    # --- Stats ---
    total_words = _total_words(body)
    citation_matches = _CITE_RE.findall(clean)
    citation_count = len(citation_matches)
    sections = _SECTION_CMD_RE.findall(clean)
    section_count = len(sections)
    paragraphs = _split_paragraphs(body, body_line_offset)
    para_total_wordss = [_total_words(p[0]) for p in paragraphs]
    avg_paragraph_length = round(sum(para_total_wordss) / max(len(para_total_wordss), 1))
    citations_per_1000 = round(citation_count / max(total_words, 1) * 1000, 1)

    stats = {
        "word_count": total_words,
        "citation_count": citation_count,
        "section_count": section_count,
        "avg_paragraph_length": avg_paragraph_length,
        "citations_per_1000": citations_per_1000,
    }

    # --- Citation Density Check ---
    for para_text, para_line in paragraphs:
        wc = _total_words(para_text)
        if wc <= 50:
            continue
        has_cite = bool(_CITE_RE.search(para_text))
        if has_cite:
            continue
        # Check for claim indicators
        lower_para = para_text.lower()
        for indicator in _CLAIM_INDICATORS:
            if indicator in lower_para:
                issues.append(WritingIssue(
                    type="citation_density",
                    severity="warning",
                    message=f'Paragraph contains claim indicator "{indicator}" but has no \\cite{{}} command.',
                    line=para_line,
                    suggestion="Add a citation to support this claim.",
                ))
                break  # one issue per paragraph

    # --- Hedging Analysis ---
    for i, line in enumerate(body.split('\n'), 1):
        lower_line = line.lower()
        for absolute_term, alternative in _HEDGING_MAP.items():
            if absolute_term in lower_line:
                issues.append(WritingIssue(
                    type="hedging",
                    severity="info",
                    message=f'Absolute term "{absolute_term}" found. Academic writing typically uses hedged language.',
                    line=i + body_line_offset,
                    suggestion=f'Consider using "{alternative}" instead.',
                ))
                break  # one hedging issue per line

    # --- Structure Analysis ---
    section_names_lower = [s.strip().lower() for s in sections]
    found_groups: dict[str, int] = {}  # group_label -> first occurrence index

    for idx, sec_name in enumerate(section_names_lower):
        for group_label, aliases in _REQUIRED_SECTIONS:
            if sec_name in aliases and group_label not in found_groups:
                found_groups[group_label] = idx

    for group_label, _ in _REQUIRED_SECTIONS:
        if group_label not in found_groups:
            issues.append(WritingIssue(
                type="structure",
                severity="warning",
                message=f'Missing standard section: {group_label.title()}.',
                suggestion=f'Consider adding a {group_label.title()} section.',
            ))

    # Check ordering of found sections
    found_order = sorted(found_groups.items(), key=lambda x: x[1])
    expected_order = [g for g in _SECTION_ORDER if g in found_groups]
    actual_order = [g for g, _ in found_order]
    if actual_order != expected_order:
        issues.append(WritingIssue(
            type="structure",
            severity="warning",
            message="Section order does not follow the standard academic structure.",
            suggestion=f"Expected order: {', '.join(g.title() for g in expected_order)}.",
        ))

    # --- Venue Conformance ---
    if venue:
        venue_lower = venue.lower()
        # Abstract length
        if venue_lower in _VENUE_ABSTRACT_LIMITS:
            limit = _VENUE_ABSTRACT_LIMITS[venue_lower]
            if abstract_text:
                abstract_wc = _total_words(abstract_text)
                if abstract_wc > limit:
                    issues.append(WritingIssue(
                        type="venue",
                        severity="warning",
                        message=f"Abstract is {abstract_wc} words, exceeding the {venue.upper()} limit of {limit} words.",
                        suggestion=f"Reduce the abstract to {limit} words or fewer.",
                    ))
            else:
                issues.append(WritingIssue(
                    type="venue",
                    severity="warning",
                    message="No abstract found. Most venues require an abstract.",
                    suggestion="Add a \\begin{{abstract}}...\\end{{abstract}} block.",
                ))

        # Nature: no separate Literature Review, strict word limits
        if venue_lower == "nature":
            for sec_name in section_names_lower:
                if sec_name in {"literature review", "related work"}:
                    issues.append(WritingIssue(
                        type="venue",
                        severity="warning",
                        message=f'Nature-style papers typically do not have a separate "{sec_name.title()}" section.',
                        suggestion="Integrate related work discussion into the Introduction.",
                    ))
            if total_words > 5000:
                issues.append(WritingIssue(
                    type="venue",
                    severity="warning",
                    message=f"Paper is {total_words} words. Nature articles are typically under 5,000 words.",
                    suggestion="Consider condensing the text to meet Nature's word limit.",
                ))

        # IEEE: check for keywords, specific formatting
        if venue_lower == "ieee":
            if "\\begin{IEEEkeywords}" not in clean and "\\begin{keywords}" not in clean:
                issues.append(WritingIssue(
                    type="venue",
                    severity="info",
                    message="IEEE papers typically include a keywords section.",
                    suggestion="Add \\begin{IEEEkeywords}...\\end{IEEEkeywords} after the abstract.",
                ))
            if citations_per_1000 < 5 and total_words > 500:
                issues.append(WritingIssue(
                    type="venue",
                    severity="warning",
                    message=f"Citation density is {citations_per_1000:.1f} per 1000 words. IEEE papers typically have higher density.",
                    suggestion="Consider adding more citations to support technical claims.",
                ))

        # ACM: check for CCS concepts, keywords
        if venue_lower == "acm":
            if "\\begin{CCSXML}" not in clean and "\\ccsdesc" not in clean.lower():
                issues.append(WritingIssue(
                    type="venue",
                    severity="info",
                    message="ACM papers require CCS (Computing Classification System) concepts.",
                    suggestion="Add CCS concepts using \\begin{CCSXML} or \\ccsdesc{} commands.",
                ))
            if "\\keywords" not in clean and "\\begin{keywords}" not in clean:
                issues.append(WritingIssue(
                    type="venue",
                    severity="info",
                    message="ACM papers should include keywords.",
                    suggestion="Add \\keywords{keyword1, keyword2, ...} after the abstract.",
                ))

        # Springer: check for keywords
        if venue_lower == "springer":
            if "\\keywords" not in clean:
                issues.append(WritingIssue(
                    type="venue",
                    severity="info",
                    message="Springer papers typically include keywords.",
                    suggestion="Add \\keywords{keyword1 \\and keyword2} after the abstract.",
                ))

        # arXiv: check for appropriate metadata
        if venue_lower == "arxiv":
            if total_words < 2000:
                issues.append(WritingIssue(
                    type="venue",
                    severity="info",
                    message=f"Paper is {total_words} words. arXiv papers are typically longer for full research contributions.",
                    suggestion="Consider expanding the paper for a more complete presentation.",
                ))

    # --- Score Calculation ---
    score = 100
    citation_penalty = min(sum(1 for i in issues if i.type == "citation_density") * 5, 30)
    hedging_penalty = min(sum(1 for i in issues if i.type == "hedging") * 3, 15)
    structure_penalty = min(sum(1 for i in issues if i.type == "structure") * 10, 30)
    venue_penalty = min(sum(1 for i in issues if i.type == "venue") * 5, 20)
    score = max(0, score - citation_penalty - hedging_penalty - structure_penalty - venue_penalty)

    return WritingAnalysisResponse(issues=issues, stats=stats, score=score)


@router.post("/latex/analyze-writing")
async def analyze_writing(
    request: WritingAnalysisRequest,
    current_user: User = Depends(get_current_user),
):
    """Analyze LaTeX source for writing quality issues."""
    if not request.latex_source or len(request.latex_source.strip()) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="latex_source is too short to analyze.",
        )
    # Merge extra files INTO the document body (before \end{document})
    # so _extract_body() captures them as part of the document content
    combined_source = request.latex_source
    if request.latex_files:
        extra_content = "\n\n".join(
            request.latex_files[fname]
            for fname in sorted(request.latex_files.keys())
        )
        end_doc_idx = combined_source.lower().rfind('\\end{document}')
        if end_doc_idx != -1:
            combined_source = combined_source[:end_doc_idx] + "\n\n" + extra_content + "\n\n" + combined_source[end_doc_idx:]
        else:
            combined_source += "\n\n" + extra_content

    result = _analyze_writing(combined_source, request.venue)
    return result


# ---------------------------------------------------------------------------
# Submission Package Builder
# ---------------------------------------------------------------------------

class SubmissionValidateRequest(BaseModel):
    latex_source: str
    venue: str
    paper_id: Optional[str] = None


class SubmissionBuildRequest(BaseModel):
    latex_source: str
    venue: str
    paper_id: Optional[str] = None
    latex_files: Optional[Dict[str, str]] = None
    include_bibtex: Optional[bool] = True


@router.get("/latex/submission-venues")
async def list_submission_venues(
    current_user: User = Depends(get_current_user),
):
    """Return all available submission venues with their configs."""
    configs = get_venue_configs()
    return {"venues": configs}


@router.post("/latex/validate-submission")
async def validate_submission(
    request: SubmissionValidateRequest,
    current_user: User = Depends(get_current_user),
):
    """Validate LaTeX source against a venue's submission rules."""
    if not request.latex_source or len(request.latex_source.strip()) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="latex_source is too short to validate.",
        )
    cfg = get_venue_config(request.venue)
    if not cfg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown venue: {request.venue}",
        )
    issues = validate_for_venue(request.latex_source, request.venue)
    return {"venue": request.venue, "venue_name": cfg["name"], "issues": issues}


@router.post("/latex/build-submission")
async def build_submission(
    request: SubmissionBuildRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Build a submission-ready ZIP package for a venue."""
    if not request.latex_source or len(request.latex_source.strip()) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="latex_source is too short to package.",
        )
    cfg = get_venue_config(request.venue)
    if not cfg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown venue: {request.venue}",
        )
    if request.paper_id:
        try:
            uuid.UUID(request.paper_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid paper_id")
        # Verify the user owns or has access to this paper
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == request.paper_id).first()
        if not paper:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
        is_owner = str(paper.owner_id) == str(current_user.id)
        is_member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper.id,
            PaperMember.user_id == current_user.id,
        ).first() is not None
        if not is_owner and not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this paper.",
            )

    try:
        zip_bytes = build_submission_package(
            latex_source=request.latex_source,
            venue=request.venue,
            paper_id=request.paper_id,
            extra_files=request.latex_files,
            db=db,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to build submission package: %s", e)
        raise HTTPException(status_code=500, detail="Failed to build submission package.")

    venue_slug = request.venue.lower().replace(" ", "-")
    filename = f"submission-{venue_slug}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/latex/templates")
async def list_templates(
    current_user: User = Depends(get_current_user),
):
    """Return all available conference/journal templates."""
    from app.constants.paper_templates import CONFERENCE_TEMPLATES
    templates = list(CONFERENCE_TEMPLATES.values())
    return {"templates": templates}


# ---------------------------------------------------------------------------
# AI-Powered LaTeX Error Fixer
# ---------------------------------------------------------------------------

_FIX_ERRORS_SYSTEM_PROMPT = """\
You are a LaTeX compilation error fixer. You receive a LaTeX document and its compilation error log.

TASK: Analyze the errors and propose minimal fixes to make the document compile successfully.

RULES:
1. Fix only ERRORS — do NOT fix warnings. Warnings do not prevent PDF generation.
2. If the error log shows only warnings and no errors, respond with: "No compilation errors found. The warnings do not prevent PDF generation."
3. Make MINIMAL changes — only modify what's needed to fix the error
4. NEVER change the document's meaning or content
5. Common fixes: missing packages, unmatched braces, environment mismatches, missing \\end{}, wrong command names, undefined control sequences
6. Do NOT fix undefined citation warnings — these are warnings, not errors
7. For missing packages that cause errors: add the \\usepackage command in the preamble
7. IMPORTANT: The source code is shown with line numbers (e.g., "42: \\usepackage{...}"). In your <<<ANCHOR>>> and <<<PROPOSED>>> output, use the RAW source text WITHOUT the line number prefix. For example, if you see "42: \\usepackage{amsmath}", your ANCHOR should be "\\usepackage{amsmath}" not "42: \\usepackage{amsmath}".

OUTPUT FORMAT — use this EXACT format for each fix:

<<<EDIT>>> [description of the fix]
<<<LINES>>> [startLine]-[endLine]
<<<ANCHOR>>> [first line of original text to match]
<<<PROPOSED>>>
[the fixed text]
<<<END>>>"""


@router.post("/latex/fix-errors")
async def fix_latex_errors(
    request: FixErrorsRequest,
    model: str = Query("openai/gpt-5.4-mini"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream AI-proposed fixes for LaTeX compilation errors."""
    # Resolve OpenRouter API key (project-level if project_id provided)
    project = None
    if request.project_id:
        project = get_project_or_404(db, request.project_id)
        ensure_project_member(db, project, current_user)

    if project:
        discussion_settings = project.discussion_settings or {}
        use_owner_key = bool(discussion_settings.get("use_owner_key_for_team", False))
        resolution = resolve_openrouter_key_for_project(
            db, current_user, project, use_owner_key_for_team=use_owner_key,
        )
    else:
        resolution = resolve_openrouter_key_for_user(db, current_user)

    api_key = resolution.get("api_key")
    if resolution.get("error_status"):
        raise HTTPException(
            status_code=int(resolution["error_status"]),
            detail={
                "error": "no_api_key" if resolution["error_status"] == 402 else "invalid_api_key",
                "message": resolution.get("error_detail") or "OpenRouter API key issue.",
            },
        )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "no_api_key",
                "message": "No API key available. Add your OpenRouter key or upgrade to Pro.",
            },
        )

    credit_cost = get_model_credit_cost(model)
    allowed, current, limit = SubscriptionService.check_feature_limit(
        db, current_user.id, "editor_ai_calls"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "AI usage limit reached",
                "current": current,
                "limit": limit,
                "message": f"You've used {current}/{limit} editor AI credits this month. "
                           "Add your OpenRouter API key in Settings for unlimited usage, "
                           "or upgrade to Pro for more credits.",
            },
        )

    # Build numbered source and user message
    numbered_source = "\n".join(
        f"{i+1}: {line}" for i, line in enumerate(request.latex_source.split("\n"))
    )
    user_message = (
        "## LaTeX Source (with line numbers)\n```\n"
        + numbered_source
        + "\n```\n\n## Compilation Error Log\n```\n"
        + request.error_log
        + "\n```\n\nAnalyze the errors and propose fixes using the <<<EDIT>>> format."
    )

    async def stream_fixes():
        try:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://scholarhub.space",
                    "X-Title": "ScholarHub",
                },
            )

            yield "data: " + json.dumps({"type": "status", "message": "Analyzing errors..."}) + "\n\n"

            stream = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _FIX_ERRORS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=4096,
                temperature=0.2,
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield "data: " + json.dumps({"type": "token", "content": delta.content}) + "\n\n"

            try:
                SubscriptionService.increment_usage(
                    db, current_user.id, "editor_ai_calls", amount=credit_cost
                )
            except Exception as usage_error:
                logger.error(
                    "Failed to increment editor AI usage for user %s: %s",
                    current_user.id,
                    usage_error,
                )

            yield "data: " + json.dumps({"type": "done"}) + "\n\n"

        except Exception:
            logger.exception("LaTeX fix errors failed for user %s", current_user.id)
            yield "data: " + json.dumps({
                "type": "error",
                "message": "Failed to analyze LaTeX errors. Please try again.",
            }) + "\n\n"

    return StreamingResponse(
        stream_fixes(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
