from fastapi import APIRouter, Depends, HTTPException, status, Response, Query
from app.core.config import settings
from starlette.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, Set
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
from app.models.reference import Reference
from app.models.research_paper import ResearchPaper
from sqlalchemy.orm import Session
from app.services.compilation_version_manager import compilation_version_manager

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
            if style_file.suffix in (".sty", ".bst", ".cls"):
                shutil.copy2(style_file, target_dir / style_file.name)
    except Exception as e:
        logger.warning("Failed to copy style files to %s: %s", target_dir, e)


class CompileRequest(BaseModel):
    latex_source: str
    paper_id: Optional[str] = None
    engine: Optional[str] = "tectonic"
    job_label: Optional[str] = None
    include_bibtex: Optional[bool] = True
    latex_files: Optional[Dict[str, str]] = None  # Multi-file: {"intro.tex": "...", ...}


def _sha256(text: str, extra_files: Optional[Dict[str, str]] = None) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8", errors="ignore"))
    if extra_files:
        for name in sorted(extra_files.keys()):
            h.update(name.encode("utf-8", errors="ignore"))
            h.update(extra_files[name].encode("utf-8", errors="ignore"))
    return h.hexdigest()


def _artifact_paths(content_hash: str) -> Dict[str, Path]:
    out_dir = ARTIFACT_ROOT / content_hash
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "dir": out_dir,
        "tex": out_dir / "main.tex",
        # Tectonic outputs <input_basename>.pdf; we use main.tex → main.pdf
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
    """Ensure the document body is not completely empty to keep tectonic happy."""
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


async def _run_tectonic(out_dir: Path, tex_path: Path):
    """Run tectonic to compile the given tex file into out_dir, stream stderr/stdout."""
    # Determine tectonic availability
    from shutil import which
    exe = which("tectonic")
    if not exe:
        raise FileNotFoundError("tectonic not found in PATH. Install via 'brew install tectonic' or see https://tectonic-typesetting.github.io/")

    # Use subprocess with streaming
    create = asyncio.create_subprocess_exec(
        exe,
        str(tex_path.name),
        "--outdir",
        str(out_dir),
        "--keep-logs",
        "--synctex",
        "--chatter",
        "minimal",
        cwd=str(out_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    proc = await create
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
    content_hash = _sha256(effective_source, request.latex_files)
    paths = _artifact_paths(content_hash)

    # Write source to cache dir (always refresh the tex file for transparency)
    try:
        await asyncio.to_thread(paths["dir"].mkdir, parents=True, exist_ok=True)
        # Copy bundled conference style files (.sty, .bst) for template support
        await asyncio.to_thread(_copy_style_files, paths["dir"])
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
    content_hash = _sha256(effective_source, request.latex_files)
    paths = _artifact_paths(content_hash)

    # Always write the .tex (and extra files if multi-file)
    try:
        await asyncio.to_thread(paths["dir"].mkdir, parents=True, exist_ok=True)
        # Copy bundled conference style files (.sty, .bst) for template support
        await asyncio.to_thread(_copy_style_files, paths["dir"])
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
        if request.latex_files:
            for fname, content in request.latex_files.items():
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
        engine = (request.engine or 'tectonic')
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
                    print(f"[metrics] compile {{'buildId': '{build_id}', 'payload_size': {payload_size}, 'engine': '{engine}', 'status': '{status_str}', 'elapsed': {round(time.time()-t0,2)}, 'errorCount': 0 }}")
                except Exception:
                    pass
            return

        # Compile via tectonic
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

            # stream logs
            async for line in _run_tectonic(paths["dir"], paths["tex"]):
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

            # If bibliography is used, try bibtex + up to two more passes with early stop
            try:
                aux = (paths["dir"] / "main.aux")
                aux_exists = await asyncio.to_thread(aux.exists)
                aux_content = (await asyncio.to_thread(aux.read_text, errors='ignore')) if aux_exists else ''
                need_bib = '\\citation' in aux_content or '\\bibdata' in aux_content
            except Exception as e:
                logger.debug("Failed to check aux for bibliography needs: %s", e)
                need_bib = False

            if need_bib:
                bbl_path = paths["dir"] / "main.bbl"
                bbl_exists = await asyncio.to_thread(bbl_path.exists)
                bbl_before = (await asyncio.to_thread(bbl_path.read_text, errors='ignore')) if bbl_exists else ''
                try:
                    from shutil import which
                    bibtex_exe = which("bibtex")
                    if not bibtex_exe:
                        yield f"data: {json.dumps({'type': 'log', 'line': '[bibtex] bibtex not found in PATH; references may be unresolved'})}\n\n"
                    else:
                        proc2 = await asyncio.create_subprocess_exec(
                            bibtex_exe, "main",
                            cwd=str(paths["dir"]),
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.STDOUT,
                        )
                        assert proc2.stdout is not None
                        while True:
                            l2 = await proc2.stdout.readline()
                            if not l2:
                                break
                            s2 = '[bibtex] ' + l2.decode(errors='ignore').rstrip()
                            logs_buf.append(s2)
                            yield f"data: {json.dumps({'type': 'log', 'line': s2})}\n\n"
                        await proc2.wait()
                        yield f"data: {json.dumps({'type': 'log', 'line': '[bibtex] Completed'})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'log', 'line': f'[bibtex] Failed: {e}'})}\n\n"

                # Up to two more tectonic passes; stop early if main.bbl stabilized
                for _ in range(2):
                    async for line in _run_tectonic(paths["dir"], paths["tex"]):
                        logs_buf.append(line)
                        payload = {"type": "log", "line": line}
                        yield f"data: {json.dumps(payload)}\n\n"
                    try:
                        bbl_check_path = paths["dir"] / "main.bbl"
                        bbl_check_exists = await asyncio.to_thread(bbl_check_path.exists)
                        bbl_now = (await asyncio.to_thread(bbl_check_path.read_text, errors='ignore')) if bbl_check_exists else ''
                        if bbl_now == bbl_before:
                            yield f"data: {json.dumps({'type': 'log', 'line': '[bibtex] Bibliography stabilized; stopping extra passes'})}\n\n"
                            break
                        bbl_before = bbl_now
                    except Exception as e:
                        logger.debug("Failed to check bbl stabilization: %s", e)

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
                    print(f"[metrics] compile {{'buildId': '{build_id}', 'payload_size': {payload_size}, 'engine': '{engine}', 'status': '{status_str}', 'elapsed': {total}, 'exit_code': {exit_code}, 'errorCount': {error_count} }}")
                except Exception:
                    pass

    headers = {
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    }
    return StreamingResponse(event_stream(), media_type='text/event-stream', headers=headers)


# Snapshot materialization removed; LaTeX source must be provided directly


def _make_bibtex_key(title: Optional[str], authors: Optional[list], year: Optional[int]) -> str:
    try:
        last = ''
        if isinstance(authors, list) and authors:
            parts = str(authors[0]).split()
            last = parts[-1].lower() if parts else ''
        yr = str(year or '')
        base = (title or '').strip().lower()
        base = ''.join(ch for ch in base if ch.isalnum() or ch.isspace()).split()
        short = ''.join(base[:3])[:12]
        key = (last + yr + short) or ("ref" + yr)
        return key
    except Exception:
        return "ref"


def _esc(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    # basic brace-safe escaping
    return s.replace('{', '\\{').replace('}', '\\}')


def _to_bibtex_entry(ref: Reference, seen_keys: Optional[Set[str]] = None) -> str:
    key = _make_bibtex_key(ref.title, ref.authors, ref.year)
    # Disambiguate duplicate keys by appending a, b, c, etc.
    if seen_keys is not None:
        original_key = key
        suffix_idx = 0
        while key in seen_keys:
            suffix_idx += 1
            key = original_key + chr(ord('a') + suffix_idx - 1)
        seen_keys.add(key)
    fields = []
    def add(k: str, v: Optional[str]):
        if v:
            fields.append(f"  {k} = {{{_esc(v)}}}")
    has_journal = bool(ref.journal)
    has_authors = bool(ref.authors and len(ref.authors) > 0)
    has_year = ref.year is not None
    # Common fields
    add("title", ref.title)
    if has_authors:
        try:
            add("author", ' and '.join(ref.authors))
        except Exception as e:
            logger.warning("Failed to join authors for reference %s: %s", ref.id, e)
    add("year", str(ref.year) if has_year else None)
    add("doi", ref.doi)
    add("url", ref.url)
    add("journal", ref.journal)
    # Choose entry type: article if journal present; else misc
    entry_type = "article" if has_journal else "misc"
    entry = f"@{entry_type}" + "{" + key + ",\n" + ",\n".join(fields) + "\n}"
    return entry


def _generate_bibtex_for_paper(db: Session, owner_id: Any, paper_id: str) -> str:
    refs = db.query(Reference).filter(Reference.owner_id == owner_id, Reference.paper_id == paper_id).all()
    entries = []
    seen_keys: Set[str] = set()
    for r in refs:
        try:
            entries.append(_to_bibtex_entry(r, seen_keys=seen_keys))
        except Exception as e:
            logger.warning("Failed to generate BibTeX entry for reference %s: %s", r.id, e)
            continue
    return "\n\n".join(entries) if entries else "% Bibliography is empty for this paper."
