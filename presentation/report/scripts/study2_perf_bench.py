"""Study 2: System Performance Benchmark.

Runs the following measurements against scholarhub.space:
  1. Frontend asset latency (HTML, JS bundle)
  2. Health endpoint latency
  3. External paper search latency (Semantic Scholar direct, no auth)
  4. CRDT round-trip approximation (HEAD against /collab/ WebSocket upgrade)

Run:
    python study2_perf_bench.py --base https://scholarhub.space --runs 30

Output:
    JSON in ./study2_results.json with median, p95, mean, std for each metric.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


SEMANTIC_SCHOLAR = "https://api.semanticscholar.org/graph/v1/paper/search"
QUERIES = [
    "retrieval augmented generation",
    "conflict-free replicated data types",
    "transformer language model",
    "diffusion image generation",
    "federated learning healthcare",
]


async def time_get(client: httpx.AsyncClient, url: str, **kwargs) -> float:
    t0 = time.perf_counter()
    r = await client.get(url, **kwargs)
    r.raise_for_status()
    return (time.perf_counter() - t0) * 1000.0  # ms


async def measure_endpoint(
    client: httpx.AsyncClient, url: str, runs: int, **kwargs
) -> list[float]:
    samples = []
    for _ in range(runs):
        try:
            samples.append(await time_get(client, url, **kwargs))
        except Exception as exc:
            print(f"  error on {url}: {exc!r}")
        await asyncio.sleep(0.2)  # politeness
    return samples


async def measure_semantic_scholar(client: httpx.AsyncClient, runs: int) -> list[float]:
    samples = []
    for i in range(runs):
        q = QUERIES[i % len(QUERIES)]
        try:
            samples.append(
                await time_get(
                    client,
                    SEMANTIC_SCHOLAR,
                    params={"query": q, "limit": 10, "fields": "title,year,authors"},
                )
            )
        except Exception as exc:
            print(f"  error on semantic scholar: {exc!r}")
        await asyncio.sleep(1.0)  # rate limit
    return samples


def percentiles(samples: list[float]) -> dict:
    if not samples:
        return {"n": 0}
    s = sorted(samples)
    return {
        "n": len(s),
        "min": min(s),
        "p50": statistics.median(s),
        "p95": s[int(0.95 * (len(s) - 1))],
        "p99": s[int(0.99 * (len(s) - 1))],
        "max": max(s),
        "mean": statistics.mean(s),
        "std": statistics.stdev(s) if len(s) > 1 else 0.0,
    }


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="https://scholarhub.space")
    p.add_argument("--runs", type=int, default=30)
    p.add_argument("--out", default="study2_results.json")
    args = p.parse_args()

    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        print(f"[1/4] Frontend HTML ({args.runs} runs)...")
        html = await measure_endpoint(client, f"{args.base}/", args.runs)

        print(f"[2/5] Backend health ({args.runs} runs)...")
        health = await measure_endpoint(client, f"{args.base}/health", args.runs)

        print(f"[3/5] Backend health detailed ({args.runs} runs)...")
        healthz = await measure_endpoint(client, f"{args.base}/healthz", args.runs)

        # Semantic Scholar with longer rate limit
        print(f"[4/5] Semantic Scholar direct (5 runs, slower due to rate limit)...")
        ss_samples = []
        for i in range(5):
            q = QUERIES[i % len(QUERIES)]
            try:
                ss_samples.append(
                    await time_get(
                        client,
                        SEMANTIC_SCHOLAR,
                        params={"query": q, "limit": 10, "fields": "title,year,authors"},
                    )
                )
            except Exception as exc:
                print(f"  error semantic: {exc!r}")
            await asyncio.sleep(3.5)  # politeness for unauthenticated tier

        # OpenAlex direct
        print(f"[5/5] OpenAlex direct ({args.runs} runs)...")
        oa_samples = []
        for i in range(args.runs):
            q = QUERIES[i % len(QUERIES)]
            try:
                oa_samples.append(
                    await time_get(
                        client,
                        "https://api.openalex.org/works",
                        params={"search": q, "per-page": 10},
                    )
                )
            except Exception as exc:
                print(f"  error openalex: {exc!r}")
            await asyncio.sleep(0.5)

        # CrossRef direct
        print(f"[+] CrossRef direct ({args.runs} runs)...")
        cr_samples = []
        for i in range(args.runs):
            q = QUERIES[i % len(QUERIES)]
            try:
                cr_samples.append(
                    await time_get(
                        client,
                        "https://api.crossref.org/works",
                        params={"query": q, "rows": 10},
                    )
                )
            except Exception as exc:
                print(f"  error crossref: {exc!r}")
            await asyncio.sleep(0.5)

        # arXiv direct
        print(f"[+] arXiv direct ({args.runs} runs)...")
        ax_samples = []
        for i in range(args.runs):
            q = QUERIES[i % len(QUERIES)]
            try:
                ax_samples.append(
                    await time_get(
                        client,
                        "https://export.arxiv.org/api/query",
                        params={"search_query": f"all:{q}", "max_results": 10},
                    )
                )
            except Exception as exc:
                print(f"  error arxiv: {exc!r}")
            await asyncio.sleep(1.0)

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base": args.base,
        "runs_per_endpoint": args.runs,
        "results_ms": {
            "frontend_html":     percentiles(html),
            "health_endpoint":   percentiles(health),
            "healthz_detailed":  percentiles(healthz),
            "semantic_scholar":  percentiles(ss_samples),
            "openalex":          percentiles(oa_samples),
            "crossref":          percentiles(cr_samples),
            "arxiv":             percentiles(ax_samples),
        },
    }
    Path(args.out).write_text(json.dumps(results, indent=2))
    print(f"\nWrote {args.out}")
    for k, v in results["results_ms"].items():
        if v.get("n"):
            print(f"  {k:18s} n={v['n']:3d}  p50={v['p50']:7.1f}ms  p95={v['p95']:7.1f}ms")


if __name__ == "__main__":
    asyncio.run(main())
