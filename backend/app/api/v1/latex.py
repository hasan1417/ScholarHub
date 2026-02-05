from fastapi import APIRouter, Depends, HTTPException, status, Response, Query
from app.core.config import settings
from starlette.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, Set
import asyncio
import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
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


def _sha256(text: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8", errors="ignore"))
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
    content_hash = _sha256(effective_source)
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to prepare source: {e}")

    cached = await asyncio.to_thread(paths["pdf"].exists)
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
    content_hash = _sha256(effective_source)
    paths = _artifact_paths(content_hash)

    # Always write the .tex
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

        # Cache hit
        cached = (await asyncio.to_thread(paths["pdf"].exists)) and not copied_bib
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
            final = {"type": "final", "pdf_url": f"/api/v1/latex/artifacts/{content_hash}/main.pdf", "hash": content_hash, "elapsed": round(time.time()-t0,2), "buildId": build_id, "errorCount": 0, "commitId": commit_id}
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
            except Exception:
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
                for i in range(2):
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
                    except Exception:
                        pass

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
                final = {
                    "type": "final",
                    "pdf_url": f"/api/v1/latex/artifacts/{content_hash}/main.pdf",
                    "hash": content_hash,
                    "elapsed": elapsed,
                    "buildId": build_id,
                    "errorCount": error_count,
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
