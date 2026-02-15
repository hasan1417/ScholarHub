"""Quick evaluation: run paper searches and compare GptRanker vs SimpleRanker."""

import asyncio
import logging
import time
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.paper_discovery_service import PaperDiscoveryService, DiscoveryResult
from app.services.paper_discovery.config import DiscoveryConfig
from app.services.paper_discovery.rankers import GptRanker, SimpleRanker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("eval_ranker")

QUERIES = [
    "transformer architecture for natural language processing",
    "CRISPR gene editing clinical trials",
    "reinforcement learning robotics manipulation",
]


def print_results(label: str, result: DiscoveryResult, elapsed: float):
    papers = result.papers
    print(f"\n{'='*70}")
    print(f"  {label}  ({elapsed:.2f}s, {len(papers)} papers)")
    print(f"{'='*70}")

    # Source distribution
    sources = Counter(p.source for p in papers)
    print(f"\n  Source distribution: {dict(sources)}")

    # Source stats from the run
    for s in result.source_stats:
        print(f"    {s.source:20s}  count={s.count:<4d}  status={s.status:<13s}  {s.elapsed_ms}ms")

    # Top 10 results
    print(f"\n  Top 10 results:")
    for i, p in enumerate(papers[:10], 1):
        title = (p.title or "")[:80]
        print(f"    {i:2d}. [{p.relevance_score:.3f}] ({p.source:18s}) {title}")
        if p.year or p.citations_count:
            print(f"        year={p.year}  citations={p.citations_count or 0}")


async def run_search(query: str, ranker_name: str, use_gpt: bool) -> tuple[DiscoveryResult, float]:
    config = DiscoveryConfig()
    svc = PaperDiscoveryService(config=config)

    if use_gpt:
        from app.core.config import settings
        if not settings.OPENROUTER_API_KEY:
            print(f"  SKIP {ranker_name}: no OPENROUTER_API_KEY")
            return DiscoveryResult(), 0.0
        svc.orchestrator.ranker = GptRanker(config)
    else:
        svc.orchestrator.ranker = SimpleRanker(config)

    try:
        t0 = time.time()
        result = await svc.discover_papers(
            query=query,
            max_results=10,
            fast_mode=True,
        )
        elapsed = time.time() - t0
        return result, elapsed
    finally:
        await svc.close()


async def main():
    for query in QUERIES:
        print(f"\n\n{'#'*70}")
        print(f"  QUERY: {query}")
        print(f"{'#'*70}")

        # Run SimpleRanker
        simple_result, simple_time = await run_search(query, "SimpleRanker", use_gpt=False)
        print_results("SimpleRanker", simple_result, simple_time)

        # Run GptRanker
        gpt_result, gpt_time = await run_search(query, "GptRanker", use_gpt=True)
        print_results("GptRanker (OpenRouter)", gpt_result, gpt_time)

        # Compare overlap and ranking differences
        if simple_result.papers and gpt_result.papers:
            simple_titles = {p.title for p in simple_result.papers}
            gpt_titles = {p.title for p in gpt_result.papers}
            overlap = simple_titles & gpt_titles
            print(f"\n  Overlap: {len(overlap)}/{len(simple_titles)} papers in common")

            # Show reordering for overlapping papers
            if overlap:
                simple_rank = {p.title: i for i, p in enumerate(simple_result.papers, 1)}
                gpt_rank = {p.title: i for i, p in enumerate(gpt_result.papers, 1)}
                print(f"  Rank changes for shared papers:")
                for title in sorted(overlap, key=lambda t: gpt_rank.get(t, 99)):
                    sr = simple_rank.get(title, "?")
                    gr = gpt_rank.get(title, "?")
                    delta = f"({int(sr)-int(gr):+d})" if isinstance(sr, int) and isinstance(gr, int) else ""
                    short = title[:60]
                    print(f"    Simple #{sr} -> GPT #{gr} {delta}  {short}")


if __name__ == "__main__":
    asyncio.run(main())
