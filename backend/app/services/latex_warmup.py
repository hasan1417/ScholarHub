import asyncio
import os
import textwrap
import tempfile
from pathlib import Path
from shutil import which

WARMUP_SOURCE = textwrap.dedent(
    r"""
    \documentclass{article}
    \usepackage{amsmath}
    \usepackage{amsfonts}
    \usepackage{amssymb}
    \usepackage{graphicx}
    \usepackage{hyperref}
    \usepackage{geometry}
    \geometry{margin=1in}

    \begin{document}
    \title{ScholarHub Warmup Document}
    \author{Automation}
    \date{\today}
    \maketitle

    This is a short warmup document used to prime the \texttt{tectonic} cache.

    \section{Introduction}
    Consider the famous identity:
    \[
      e^{i\pi} + 1 = 0.
    \]

    We also include a figure placeholder to force graphics packages to load:

    \begin{figure}[h]
      \centering
      \fbox{\rule{0pt}{2in} \rule{2in}{0pt}}
      \caption{Placeholder graphic}
    \end{figure}

    \section{Hyperlinks}
    Visit \href{https://scholarhub.local}{ScholarHub} for collaborative research authoring.

    \end{document}
    """
).strip()


async def _run_tectonic(tex_dir: Path, tex_filename: str) -> int:
    exe = which("tectonic")
    if not exe:
        print("[latex-warmup] Skipping warmup: tectonic not found in PATH")
        return 0

    # -Z continue-on-errors: continue past recoverable errors such as the
    # "dehypht-x-2022-03-16.pat: Bad \patterns" hyphenation-cache mismatch.
    process = await asyncio.create_subprocess_exec(
        exe,
        "-Z",
        "continue-on-errors",
        tex_filename,
        "--outdir",
        str(tex_dir),
        "--keep-logs",
        "--chatter",
        "minimal",
        cwd=str(tex_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=os.environ.copy(),
    )

    assert process.stdout is not None
    async for raw_line in process.stdout:
        line = raw_line.decode(errors="ignore").rstrip()
        if line:
            print(f"[latex-warmup] {line}")

    return await process.wait()


async def warmup_latex_cache() -> None:
    exe = which("tectonic")
    if not exe:
        print("[latex-warmup] Tectonic not installed; warmup skipped")
        return

    with tempfile.TemporaryDirectory(prefix="latex-warmup-") as tmpdir:
        tmp_path = Path(tmpdir)
        tex_path = tmp_path / "main.tex"
        tex_path.write_text(WARMUP_SOURCE, encoding="utf-8")

        print("[latex-warmup] Running tectonic warmup pass…")
        try:
            exit_code = await _run_tectonic(tmp_path, tex_path.name)
            if exit_code == 0:
                print("[latex-warmup] Warmup completed successfully")
            else:
                print(f"[latex-warmup] Warmup finished with exit code {exit_code}")
        except Exception as exc:
            print(f"[latex-warmup] Warmup failed: {exc}")
