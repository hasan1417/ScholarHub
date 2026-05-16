"""Study 1: Real Empirical Citation Faithfulness Benchmark.

Runs 15 cited-writing prompts through 4 frontier models via OpenRouter, in two
conditions:
  A) UNGROUNDED — model gets prompt only, must invent citations.
  B) GROUNDED   — model gets prompt + a curated 15-paper library and is
                  instructed to cite ONLY from that library.

For every cited paper in the output, performs:
  - Existence check via Semantic Scholar paper search.
  - Library-membership check (against the provided library keys).
  - DOI / arXiv extraction from text and verification.

Outputs CSV with one row per (prompt, model, condition) and a summary JSON
with fabrication, library-faithfulness, and existence rates per model.

Run:
    cd presentation/report/scripts
    python study1_runner.py --runs all

Cost is bounded by the model list and 15 prompts. With 4 models × 2 conditions,
the total is 120 model calls. At typical pricing this is < $5.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


SCRIPT_DIR = Path(__file__).resolve().parent

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SEMANTIC_SCHOLAR_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"

MODELS = [
    {"id": "openai/gpt-5-mini",                "label": "GPT-5 Mini"},
    {"id": "anthropic/claude-haiku-4.5",       "label": "Claude Haiku 4.5"},
    {"id": "google/gemini-3-flash-preview",    "label": "Gemini 3 Flash"},
    {"id": "deepseek/deepseek-r1-0528",        "label": "DeepSeek R1"},
]


# ---------- environment ----------

def load_env():
    candidates = [
        SCRIPT_DIR.parent.parent.parent / ".env",
        SCRIPT_DIR.parent.parent / ".env",
        Path.cwd() / ".env",
    ]
    env_path = next((p for p in candidates if p.exists()), None)
    if env_path is None:
        raise SystemExit(
            "ENV not found. Place .env at the project root with "
            "OPENROUTER_API_KEY (and optionally SEMANTIC_SCHOLAR_API_KEY)."
        )
    out = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip("\"'")
    return out


# ---------- prompt construction ----------

def build_messages(prompt_obj, library, grounded: bool):
    if not grounded:
        sys_msg = (
            "You are an academic writing assistant. Produce concise scholarly prose. "
            "When you cite, write the citation inline as `[Author Year]` and provide a "
            "References block at the end with full bibliographic details (title, authors, "
            "year, venue/journal, DOI or arXiv ID if applicable). "
            "Aim for 3 distinct citations unless otherwise instructed. Do not refuse."
        )
    else:
        lines = ["The user has the following 15 papers in their library. "
                 "When you cite, you MUST cite only from this list. "
                 "Use the citation key in inline form like `[shapiro2011crdt]` and reproduce "
                 "the full reference at the end. Aim for 3 distinct citations.\n\n"
                 "LIBRARY:"]
        for p in library:
            ident = f"DOI:{p['doi']}" if p.get('doi') else f"arXiv:{p.get('arxiv','')}"
            lines.append(
                f"- key={p['key']} | {p['authors']} ({p['year']}). "
                f"\"{p['title']}\". {p['venue']}. {ident}"
            )
        sys_msg = "\n".join(lines)

    user_msg = prompt_obj["prompt"]
    return [
        {"role": "system", "content": sys_msg},
        {"role": "user",   "content": user_msg},
    ]


# ---------- model invocation ----------

async def call_model(client: httpx.AsyncClient, api_key: str, model: str,
                     messages: list, timeout: float = 90.0) -> tuple[str, dict]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://scholarhub.space",
        "X-Title": "ScholarHub Study 1",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 1200,
    }
    t0 = time.perf_counter()
    r = await client.post(OPENROUTER_URL, headers=headers, json=body, timeout=timeout)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    r.raise_for_status()
    data = r.json()
    msg = data["choices"][0]["message"]
    text = msg.get("content") or msg.get("reasoning") or ""
    if not text and msg.get("reasoning_content"):
        text = msg["reasoning_content"]
    usage = data.get("usage", {})
    meta = {
        "elapsed_ms": elapsed_ms,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "model_returned": data.get("model", model),
    }
    return text, meta


# ---------- citation extraction ----------

# Match references in text. We look for a "References" section and parse loose lines.
REF_SECTION_RE = re.compile(r"(?im)^\s*(references|bibliography)\s*[:.]?\s*$")

# Extract DOIs and arXiv IDs from any text.
DOI_RE   = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)\b", re.I)
ARXIV_RE = re.compile(r"\barXiv:?\s*(\d{4}\.\d{4,5})(v\d+)?\b", re.I)

# Inline citation patterns. Captures "[Author 2023]" or "[author2023key]" or
# "(Author, 2023)" forms.
CITE_INLINE_RE = re.compile(
    r"(?:\[([A-Za-z][A-Za-z0-9_\- ]+(?:,?\s*\d{4})?)\]|\(([A-Za-z][^)]{2,60}?,\s*\d{4})\))"
)


def extract_references_block(text: str) -> str:
    """Find the References block at the end of the response (best effort)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if REF_SECTION_RE.match(line):
            return "\n".join(lines[i + 1:]).strip()
    # Fallback: take the last 25 lines if they look list-y (contain DOIs/arXiv)
    tail = "\n".join(lines[-25:])
    if DOI_RE.search(tail) or ARXIV_RE.search(tail):
        return tail
    return ""


INLINE_AUTHOR_YEAR_RE = re.compile(
    r"\[([A-Z][A-Za-z\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z\-]+|\s+et\s+al\.?)?[\s,]+(?:19|20)\d{2}[a-z]?)\]"
)
# Match library-key citations like [shapiro2011crdt] or [walters2023fabrication]
INLINE_LIBKEY_RE = re.compile(r"\[([a-z][a-z0-9_-]+\d{4}[a-z0-9]+)\]")


def extract_inline_cites(text: str, library_keys: set[str]) -> list[dict]:
    """Extract inline citations: both [Author Year] and library keys [shapiro2011crdt]."""
    seen = set()
    out = []

    # Library keys first (high confidence)
    for m in INLINE_LIBKEY_RE.finditer(text):
        key = m.group(1).strip()
        if key in seen:
            continue
        seen.add(key)
        # Year extraction
        ym = re.search(r"(\d{4})", key)
        year = int(ym.group(1)) if ym else None
        # Author part is everything before the year
        author_part = re.split(r"\d{4}", key)[0]
        is_lib = key in library_keys
        out.append({
            "raw": f"[{key}]",
            "doi": None,
            "arxiv": None,
            "title_guess": None,
            "author": author_part,
            "year": year,
            "library_key": key,
            "source": "inline_libkey",
            "is_library_key": is_lib,
        })

    # Author Year inline cites
    for m in INLINE_AUTHOR_YEAR_RE.finditer(text):
        token = m.group(1).strip()
        if token in seen:
            continue
        seen.add(token)
        ym = re.search(r"((?:19|20)\d{2})", token)
        year = int(ym.group(1)) if ym else None
        author_part = re.sub(r"\s*[,]?\s*(?:19|20)\d{2}[a-z]?", "", token).strip()
        out.append({
            "raw": f"[{token}]",
            "doi": None,
            "arxiv": None,
            "title_guess": None,
            "author": author_part,
            "year": year,
            "source": "inline_author_year",
        })
    return out


def extract_citations(text: str, library_keys: set[str] | None = None) -> list[dict]:
    """Parse the references block AND inline citations into discrete entries."""
    if not text:
        return []
    library_keys = library_keys or set()
    out = []
    seen_keys = set()  # dedupe by (author, year)

    # 1) Parse the References block if present
    block = extract_references_block(text)
    if block:
        chunks = re.split(r"(?m)^\s*(?:\[\d+\]|\d+\.|\*|\-|•)\s*", block)
        chunks = [c.strip() for c in chunks if len(c.strip()) > 20]
        if len(chunks) < 2:
            chunks = [c.strip() for c in re.split(r"\n\s*\n", block) if len(c.strip()) > 20]

        for c in chunks[:8]:
            doi_match = DOI_RE.search(c)
            arxiv_match = ARXIV_RE.search(c)
            doi_id = doi_match.group(1) if doi_match else None
            arxiv_id = arxiv_match.group(1) if arxiv_match else None

            m = re.search(r'"([^"]{15,200})"|“([^”]{15,200})”', c)
            title = m.group(1) if m and m.group(1) else (m.group(2) if m else None)
            if not title:
                cand = re.sub(r"^[^.]*\(\d{4}\)\.?\s*", "", c)
                cand = cand.split(".")[0].strip()
                if len(cand) > 15:
                    title = cand[:200]

            ym = re.search(r"\b(19|20)\d{2}\b", c)
            year = int(ym.group(0)) if ym else None

            am = re.match(r"\s*([A-Z][A-Za-z\-]+)", c)
            author = am.group(1) if am else None

            key = (author, year)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            out.append({
                "raw": c[:300],
                "doi": doi_id,
                "arxiv": arxiv_id,
                "title_guess": title,
                "author": author,
                "year": year,
                "source": "references_block",
            })

    # 2) Add any inline citations we haven't seen
    for inline in extract_inline_cites(text, library_keys):
        # Match by first author surname + year (or library_key)
        if inline.get("library_key"):
            key = ("libkey", inline["library_key"])
        else:
            a = inline.get("author", "")
            first_author = a.split(" ")[0].split(",")[0] if a else None
            key = (first_author, inline["year"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(inline)

    return out[:10]


# ---------- Semantic Scholar verification ----------

async def verify_existence(client: httpx.AsyncClient, ss_key: str | None, cit: dict,
                           sem: asyncio.Semaphore) -> dict:
    """Return a dict with keys: exists (bool), match_method, ss_paper_id, error."""
    headers = {"x-api-key": ss_key} if ss_key else {}
    out: dict = {"exists": False, "match_method": None, "ss_paper_id": None, "error": None}

    # Strategy 1: DOI lookup
    if cit.get("doi"):
        try:
            async with sem:
                r = await client.get(
                    f"https://api.semanticscholar.org/graph/v1/paper/DOI:{cit['doi']}",
                    headers=headers,
                    params={"fields": "title,year,authors"},
                    timeout=15.0,
                )
            if r.status_code == 200:
                d = r.json()
                if d.get("paperId"):
                    out.update(exists=True, match_method="doi", ss_paper_id=d.get("paperId"))
                    return out
            elif r.status_code == 404:
                out["error"] = "doi_not_found"
            else:
                out["error"] = f"doi_status_{r.status_code}"
        except Exception as e:
            out["error"] = f"doi_exc:{type(e).__name__}"

    # Strategy 2: arXiv ID lookup
    if cit.get("arxiv"):
        try:
            async with sem:
                r = await client.get(
                    f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{cit['arxiv']}",
                    headers=headers,
                    params={"fields": "title,year"},
                    timeout=15.0,
                )
            if r.status_code == 200:
                d = r.json()
                if d.get("paperId"):
                    out.update(exists=True, match_method="arxiv", ss_paper_id=d.get("paperId"))
                    return out
        except Exception as e:
            out["error"] = (out["error"] or "") + f";arxiv_exc:{type(e).__name__}"

    # Strategy 3: OpenAlex search (primary - no rate limit issues)
    query = cit.get("title_guess")
    if not query and cit.get("author") and cit.get("year"):
        query = f"{cit['author']} {cit['year']}"

    if query:
        try:
            async with sem:
                r = await client.get(
                    "https://api.openalex.org/works",
                    params={"search": query[:200], "per-page": 5,
                            "select": "id,title,publication_year,authorships,doi"},
                    timeout=15.0,
                )
            if r.status_code == 200:
                hits = r.json().get("results", [])
                if cit.get("title_guess"):
                    target = set(re.findall(r"\w+", cit["title_guess"].lower()))
                    for h in hits:
                        found = set(re.findall(r"\w+", (h.get("title") or "").lower()))
                        if not target or not found:
                            continue
                        j = len(target & found) / max(1, len(target | found))
                        if j > 0.4:
                            out.update(exists=True,
                                       match_method=f"oa_title_jaccard_{j:.2f}",
                                       ss_paper_id=h.get("id"))
                            return out
                    out["error"] = "oa_title_no_match"
                else:
                    target_year = cit.get("year")
                    target_author = (cit.get("author") or "").lower()
                    for h in hits:
                        if target_year and h.get("publication_year") != target_year:
                            if abs((h.get("publication_year") or 0) - target_year) > 1:
                                continue
                        authorships = h.get("authorships") or []
                        for a in authorships:
                            name = ((a.get("author") or {}).get("display_name") or "").lower()
                            if target_author and target_author in name:
                                out.update(exists=True,
                                           match_method="oa_author_year",
                                           ss_paper_id=h.get("id"))
                                return out
                    out["error"] = "oa_author_year_no_match"
            else:
                out["error"] = f"oa_status_{r.status_code}"
        except Exception as e:
            out["error"] = (out["error"] or "") + f";oa_exc:{type(e).__name__}"

    return out


# ---------- runner ----------

async def run_one(client: httpx.AsyncClient, openrouter_key: str, ss_key: str | None,
                  prompt_obj: dict, model: dict, library: list, grounded: bool,
                  ss_sem: asyncio.Semaphore) -> dict:
    msgs = build_messages(prompt_obj, library, grounded)
    try:
        text, meta = await call_model(client, openrouter_key, model["id"], msgs)
    except Exception as e:
        return {
            "prompt_id": prompt_obj["id"], "model_id": model["id"],
            "model_label": model["label"], "grounded": grounded,
            "ok": False, "error": f"{type(e).__name__}:{str(e)[:200]}",
            "citations": [],
        }

    library_keys = {p["key"] for p in library}
    library_dois = {p["doi"].lower() for p in library if p.get("doi")}
    library_arxiv = {p["arxiv"] for p in library if p.get("arxiv")}

    citations = extract_citations(text, library_keys=library_keys)
    verifications = []

    for c in citations:
        in_library = False
        # Library-key citations: trusted by construction (key matches a real paper)
        if c.get("library_key") and c["library_key"] in library_keys:
            in_library = True
            v = {"exists": True, "match_method": "library_key", "ss_paper_id": None, "error": None}
        else:
            # External verification via Semantic Scholar
            v = await verify_existence(client, ss_key, c, ss_sem)
            if c.get("doi") and c["doi"].lower() in library_dois:
                in_library = True
            elif c.get("arxiv") and c["arxiv"] in library_arxiv:
                in_library = True
            elif c.get("title_guess"):
                for p in library:
                    if p["title"][:30].lower() in c["title_guess"].lower():
                        in_library = True
                        break
        verifications.append({**c, **v, "in_library": in_library})

    return {
        "prompt_id": prompt_obj["id"],
        "prompt_topic": prompt_obj.get("topic"),
        "prompt_category": prompt_obj.get("category"),
        "model_id": model["id"],
        "model_label": model["label"],
        "model_returned": meta.get("model_returned"),
        "grounded": grounded,
        "ok": True,
        "elapsed_ms": meta["elapsed_ms"],
        "prompt_tokens": meta["prompt_tokens"],
        "completion_tokens": meta["completion_tokens"],
        "n_citations": len(citations),
        "citations": verifications,
        "raw_text_excerpt": text[:600],
    }


def summarize(results: list[dict]) -> dict:
    """Compute aggregate metrics per (model, grounded) cell.

    Reports both pre-filter (raw model output) and post-filter rates.
    Post-filter simulates ScholarHub's runtime citation filter, which drops
    every citation whose key is not in the project library before the response
    reaches the user. Post-filter fabrication is therefore 0% by construction
    (only in-library citations survive, and in-library papers exist).
    """
    cells = {}
    for r in results:
        if not r.get("ok"):
            continue
        key = (r["model_id"], r["grounded"])
        c = cells.setdefault(key, {
            "model_id": r["model_id"], "model_label": r["model_label"],
            "grounded": r["grounded"],
            "n_responses": 0, "total_citations": 0, "existing": 0,
            "fabricated": 0, "in_library": 0,
            "post_filter_kept": 0, "post_filter_fabricated": 0,
            "total_elapsed_ms": 0.0, "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
        })
        c["n_responses"] += 1
        c["total_elapsed_ms"] += r["elapsed_ms"]
        c["total_prompt_tokens"] += r["prompt_tokens"]
        c["total_completion_tokens"] += r["completion_tokens"]
        for cit in r["citations"]:
            c["total_citations"] += 1
            if cit["exists"]:
                c["existing"] += 1
            else:
                c["fabricated"] += 1
            if cit["in_library"]:
                c["in_library"] += 1
                # Post-filter: only in-library citations survive
                c["post_filter_kept"] += 1
                if not cit["exists"]:
                    c["post_filter_fabricated"] += 1

    summary = []
    for (mid, grounded), c in sorted(cells.items()):
        n = c["total_citations"]
        pf = c["post_filter_kept"]
        summary.append({
            **c,
            "fabrication_rate":          c["fabricated"] / n if n else 0.0,
            "existence_rate":            c["existing"]   / n if n else 0.0,
            "library_faithful":          c["in_library"] / n if n else 0.0,
            "post_filter_fab_rate":      c["post_filter_fabricated"] / pf if pf else 0.0,
            "post_filter_retention":     pf / n if n else 0.0,
            "avg_elapsed_ms":            c["total_elapsed_ms"] / max(1, c["n_responses"]),
        })
    return {"cells": summary, "total_responses": sum(c["n_responses"] for c in cells.values())}


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prompts", default=str(SCRIPT_DIR / "study1_prompts.json"))
    p.add_argument("--library", default=str(SCRIPT_DIR / "study1_library.json"))
    p.add_argument("--out",     default=str(SCRIPT_DIR / "study1_results.json"))
    p.add_argument("--csv",     default=str(SCRIPT_DIR / "study1_results.csv"))
    p.add_argument("--limit",   type=int, default=15, help="max prompts per condition")
    p.add_argument("--ungrounded-only", action="store_true",
                   help="only run ungrounded baseline (faster)")
    p.add_argument("--concurrency", type=int, default=4)
    args = p.parse_args()

    env = load_env()
    openrouter_key = env.get("OPENROUTER_API_KEY")
    ss_key = env.get("SEMANTIC_SCHOLAR_API_KEY")
    if not openrouter_key:
        raise SystemExit("OPENROUTER_API_KEY not in .env")

    prompts_data = json.loads(Path(args.prompts).read_text())
    library_data = json.loads(Path(args.library).read_text())
    prompts = prompts_data["prompts"][: args.limit]
    library = library_data["papers"]
    conditions = [False] if args.ungrounded_only else [False, True]

    print(f"Running {len(prompts)} prompts × {len(MODELS)} models × {len(conditions)} conditions")
    print(f"  = {len(prompts) * len(MODELS) * len(conditions)} model calls")

    timeout = httpx.Timeout(120.0, connect=15.0)
    results = []
    # Throttle SS verification to 1 concurrent request to respect rate limits
    ss_sem = asyncio.Semaphore(1)
    async with httpx.AsyncClient(timeout=timeout) as client:
        sem = asyncio.Semaphore(args.concurrency)

        async def runner(p_obj, m, grounded):
            async with sem:
                r = await run_one(client, openrouter_key, ss_key, p_obj, m,
                                  library, grounded, ss_sem)
                tag = "G" if grounded else "U"
                cit_count = r.get("n_citations", 0)
                fab = sum(1 for c in r.get("citations", []) if not c.get("exists"))
                inlib = sum(1 for c in r.get("citations", []) if c.get("in_library"))
                ok = "ok" if r.get("ok") else f"err:{r.get('error','?')[:40]}"
                print(f"  [{tag}] p{p_obj['id']:02d} {m['label']:18s} cit={cit_count} fab={fab} inlib={inlib} {ok}")
                return r

        tasks = []
        for p_obj in prompts:
            for m in MODELS:
                for grounded in conditions:
                    tasks.append(runner(p_obj, m, grounded))
        results = await asyncio.gather(*tasks, return_exceptions=False)

    # Save raw
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "models": MODELS,
        "n_prompts": len(prompts),
        "conditions": ["ungrounded"] + (["grounded"] if True in conditions else []),
        "library_size": len(library),
        "raw_results": results,
        "summary": summarize(results),
    }
    Path(args.out).write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {args.out}")

    # CSV summary
    with open(args.csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model_id", "model_label", "grounded", "n_responses",
                    "total_citations", "existing", "fabricated", "in_library",
                    "fabrication_rate", "existence_rate", "library_faithful",
                    "post_filter_kept", "post_filter_fabricated",
                    "post_filter_fab_rate", "post_filter_retention",
                    "avg_elapsed_ms"])
        for c in payload["summary"]["cells"]:
            w.writerow([c["model_id"], c["model_label"], c["grounded"],
                        c["n_responses"], c["total_citations"], c["existing"],
                        c["fabricated"], c["in_library"],
                        f"{c['fabrication_rate']:.4f}",
                        f"{c['existence_rate']:.4f}",
                        f"{c['library_faithful']:.4f}",
                        c["post_filter_kept"], c["post_filter_fabricated"],
                        f"{c['post_filter_fab_rate']:.4f}",
                        f"{c['post_filter_retention']:.4f}",
                        f"{c['avg_elapsed_ms']:.0f}"])
    print(f"Wrote {args.csv}")

    # Print summary table
    print("\n=== SUMMARY ===")
    print(f"{'Model':22s} {'Cond':6s} {'N':>4s} {'Cit':>4s} {'Fab%':>6s} {'Exist%':>7s} {'InLib%':>7s} {'PF-Fab%':>8s} {'PF-Keep%':>9s} {'AvgMs':>7s}")
    for c in payload["summary"]["cells"]:
        cond = "GND" if c["grounded"] else "UNG"
        print(f"{c['model_label']:22s} {cond:6s} {c['n_responses']:>4d} {c['total_citations']:>4d} "
              f"{c['fabrication_rate']*100:>5.1f}% {c['existence_rate']*100:>6.1f}% "
              f"{c['library_faithful']*100:>6.1f}% {c['post_filter_fab_rate']*100:>7.1f}% "
              f"{c['post_filter_retention']*100:>8.1f}% {c['avg_elapsed_ms']:>7.0f}")


if __name__ == "__main__":
    asyncio.run(main())
