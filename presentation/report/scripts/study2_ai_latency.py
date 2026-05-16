"""Study 2 supplement: AI orchestrator latency through OpenRouter.

Measures end-to-end response latency for what ScholarHub does internally:
issue a chat completion request through OpenRouter to one of the supported
models. We measure both first-token latency (using streaming) and full
response latency for a fixed prompt.

This is the most realistic public-facing measurement of ScholarHub's AI
orchestrator latency without authenticated access to the production
/projects/.../discussion-or/.../assistant endpoint.

Output: study2_ai_latency.json
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


SCRIPT_DIR = Path(__file__).resolve().parent
ENV_PATH   = Path("/Users/hassan/Desktop/Coding/MX/Final Project/ScholarHub/.env")

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    {"id": "openai/gpt-5-mini",                "label": "GPT-5 Mini"},
    {"id": "anthropic/claude-haiku-4.5",       "label": "Claude Haiku 4.5"},
    {"id": "google/gemini-3-flash-preview",    "label": "Gemini 3 Flash"},
    {"id": "deepseek/deepseek-r1-0528",        "label": "DeepSeek R1"},
]

# Realistic prompt: short question that an AI orchestrator might receive
PROMPT = "Briefly explain the difference between operational transformation and CRDTs in one paragraph."
SYSTEM = ("You are a research-writing assistant. Produce concise scholarly responses "
          "of one paragraph, under 200 words.")


def load_key() -> str:
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("missing OPENROUTER_API_KEY")


async def measure_full(client: httpx.AsyncClient, key: str, model: str) -> tuple[float, int, int]:
    """Time non-streaming request. Returns (elapsed_ms, prompt_tokens, completion_tokens)."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": PROMPT},
        ],
        "max_tokens": 250,
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://scholarhub.space",
        "X-Title": "ScholarHub Study 2",
        "Content-Type": "application/json",
    }
    t0 = time.perf_counter()
    r = await client.post(OPENROUTER, headers=headers, json=body, timeout=120.0)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    r.raise_for_status()
    d = r.json()
    usage = d.get("usage", {})
    return elapsed_ms, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


async def measure_streaming(client: httpx.AsyncClient, key: str, model: str) -> dict:
    """Time streaming request. Capture first-token latency and full-response latency."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": PROMPT},
        ],
        "max_tokens": 250,
        "temperature": 0.3,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://scholarhub.space",
        "X-Title": "ScholarHub Study 2",
        "Content-Type": "application/json",
    }
    t0 = time.perf_counter()
    first_token_ms = None
    last_chunk_ms = None
    bytes_received = 0
    async with client.stream("POST", OPENROUTER, headers=headers, json=body, timeout=120.0) as r:
        r.raise_for_status()
        async for chunk in r.aiter_text():
            if first_token_ms is None and chunk.strip():
                first_token_ms = (time.perf_counter() - t0) * 1000
            last_chunk_ms = (time.perf_counter() - t0) * 1000
            bytes_received += len(chunk)
    return {
        "first_token_ms": first_token_ms or last_chunk_ms or 0,
        "full_response_ms": last_chunk_ms or 0,
        "bytes": bytes_received,
    }


def stats(samples: list[float]) -> dict:
    if not samples:
        return {"n": 0}
    s = sorted(samples)
    return {
        "n": len(s),
        "p50": statistics.median(s),
        "p95": s[int(0.95 * (len(s) - 1))],
        "min": min(s),
        "max": max(s),
        "mean": statistics.mean(s),
        "std": statistics.stdev(s) if len(s) > 1 else 0.0,
    }


async def main():
    key = load_key()
    runs = 5
    timeout = httpx.Timeout(120.0, connect=15.0)
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_chars": len(PROMPT),
        "runs_per_model": runs,
        "by_model": {},
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        for m in MODELS:
            print(f"\n{m['label']:22s} ...")
            full_times = []
            first_tokens = []
            full_streams = []
            for i in range(runs):
                try:
                    print(f"  full run {i+1}/{runs}", end=" ")
                    e, pt, ct = await measure_full(client, key, m["id"])
                    full_times.append(e)
                    print(f"=> {e:.0f}ms")
                    await asyncio.sleep(1.0)
                except Exception as exc:
                    print(f"  FULL ERR: {type(exc).__name__}")
                try:
                    print(f"  stream run {i+1}/{runs}", end=" ")
                    s = await measure_streaming(client, key, m["id"])
                    first_tokens.append(s["first_token_ms"])
                    full_streams.append(s["full_response_ms"])
                    print(f"=> first={s['first_token_ms']:.0f}ms full={s['full_response_ms']:.0f}ms")
                    await asyncio.sleep(1.0)
                except Exception as exc:
                    print(f"  STREAM ERR: {type(exc).__name__}")

            results["by_model"][m["id"]] = {
                "label": m["label"],
                "full_response_ms":  stats(full_times),
                "first_token_ms":    stats(first_tokens),
                "stream_full_ms":    stats(full_streams),
            }

    out = SCRIPT_DIR / "study2_ai_latency.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out}")
    print(f"\n{'Model':22s} {'FullP50':>10s} {'FullP95':>10s} {'FirstP50':>10s} {'StrP50':>10s}")
    for mid, d in results["by_model"].items():
        f = d["full_response_ms"]
        ft = d["first_token_ms"]
        sf = d["stream_full_ms"]
        print(f"{d['label']:22s} {f.get('p50',0):>9.0f}  {f.get('p95',0):>9.0f}  "
              f"{ft.get('p50',0):>9.0f}  {sf.get('p50',0):>9.0f}")


if __name__ == "__main__":
    asyncio.run(main())
