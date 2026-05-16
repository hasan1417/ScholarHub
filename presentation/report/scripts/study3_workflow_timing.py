"""Study 3: Empirical workflow timing.

Measures wall-clock time for the five canonical research-writing tasks
in two stacks:
  A) ScholarHub at scholarhub.space
  B) Overleaf + Zotero + ChatGPT (the conventional alternative)

For each task, we time the network round-trips that *must* happen during
the task. UI interaction times (clicks, keystrokes) are calibrated from
published HCI numbers and added to the network total. The total represents
a lower-bound on real wall-clock time the user would experience.

Output: study3_workflow_timing.json with per-task per-stack times.
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

# Calibrated per-action UI times from HCI literature (Card, Moran, Newell 1983;
# Nielsen 1993). Used to convert action counts to wall-clock estimates.
UI_ACTION_MS = {
    "click":           200,   # response time after a click in a fast SPA
    "tab_switch":      500,   # browser tab/app switch overhead
    "key_combo":       150,   # Ctrl+C, Ctrl+V
    "menu_navigation": 800,   # opening menu, finding item, clicking
    "form_field":     2500,   # typical "fill one field" cognitive + motor
    "drag_drop":      1500,   # selecting and dragging an item
}

# The five tasks with their action sequences in each stack.
# Each entry is a list of (action_type, count, network_request_url_or_None) tuples.
TASKS = {
    "T1_discover_5_papers": {
        "label": "Find 5 papers and add to library",
        "scholarhub": [
            ("click", 1, None),                      # Discovery sidebar
            ("form_field", 1, None),                 # type query
            ("click", 1, None),                      # press Enter (search)
            ("net", 1, "https://scholarhub.space/"), # results page nav (proxy: home page)
            ("click", 5, None),                      # add 5 papers
            ("click", 1, None),                      # verify in library
        ],
        "overleaf": [
            ("tab_switch", 1, None),                                  # to Google Scholar
            ("net", 1, "https://scholar.google.com/"),                # load
            ("form_field", 1, None),                                  # query
            ("click", 1, None),
            ("click", 5, None),                                       # click 5 paper titles
            ("net", 5, "https://scholar.google.com/"),                # load each result
            ("click", 5, None),                                       # cite button x5
            ("click", 5, None),                                       # copy bibtex x5
            ("key_combo", 5, None),                                   # ctrl+c x5
            ("tab_switch", 1, None),                                  # to Zotero
            ("key_combo", 5, None),                                   # ctrl+v x5
            ("click", 1, None),                                       # export collection
            ("menu_navigation", 1, None),                             # choose bibtex format
            ("click", 1, None),                                       # save .bib
            ("tab_switch", 1, None),                                  # to Overleaf
            ("net", 1, "https://www.overleaf.com/"),                  # load
            ("click", 1, None),                                       # upload
            ("click", 1, None),                                       # choose file
            ("click", 1, None),                                       # confirm
        ],
    },

    "T2_paragraph_3_citations": {
        "label": "Write paragraph with 3 citations to library",
        "scholarhub": [
            ("click", 1, None),                                       # open AI panel
            ("form_field", 1, None),                                  # type request
            ("click", 1, None),                                       # send
            ("net", 1, "https://scholarhub.space/"),                  # AI orchestrator (proxy home)
            ("click", 1, None),                                       # accept generated paragraph
        ],
        "overleaf": [
            ("tab_switch", 1, None),                                  # to ChatGPT
            ("net", 1, "https://chat.openai.com/"),
            ("form_field", 1, None),
            ("click", 1, None),                                       # send
            ("net", 1, "https://chat.openai.com/"),                   # response
            ("click", 1, None),                                       # copy text
            ("key_combo", 1, None),                                   # ctrl+c
            ("tab_switch", 1, None),                                  # to Zotero
            ("click", 3, None),                                       # find 3 papers
            ("click", 3, None),                                       # cite key for each
            ("key_combo", 3, None),                                   # ctrl+c each
            ("tab_switch", 1, None),                                  # to Overleaf
            ("net", 1, "https://www.overleaf.com/"),
            ("key_combo", 1, None),                                   # paste text
            ("key_combo", 3, None),                                   # paste 3 \cite{}
            ("form_field", 3, None),                                  # adjust each citation
        ],
    },

    "T3_inline_citation": {
        "label": "Insert citation mid-paragraph",
        "scholarhub": [
            ("key_combo", 1, None),                                   # ctrl+space autocomplete
            ("form_field", 1, None),                                  # type partial author
            ("click", 1, None),                                       # accept suggestion
        ],
        "overleaf": [
            ("tab_switch", 1, None),                                  # to Zotero
            ("form_field", 1, None),                                  # search
            ("click", 1, None),
            ("click", 1, None),                                       # select paper
            ("key_combo", 1, None),                                   # copy key
            ("tab_switch", 1, None),                                  # to Overleaf
            ("net", 1, "https://www.overleaf.com/"),
            ("form_field", 1, None),                                  # type \cite{
            ("key_combo", 1, None),                                   # paste
            ("form_field", 1, None),                                  # close brace
        ],
    },

    "T4_compile_multifile": {
        "label": "Compile multi-file LaTeX with bibliography",
        "scholarhub": [
            ("click", 1, "https://scholarhub.space/"),                # compile button
        ],
        "overleaf": [
            ("click", 1, "https://www.overleaf.com/"),                # compile button
        ],
    },

    "T5_realtime_coedit": {
        "label": "Real-time co-edit paper section",
        "scholarhub": [
            ("net", 1, "https://scholarhub.space/"),                  # session join
        ],
        "overleaf": [
            ("net", 1, "https://www.overleaf.com/"),                  # session join
        ],
    },
}


async def time_request(client: httpx.AsyncClient, url: str) -> float:
    """Time a single GET request. Returns elapsed ms or NaN on error."""
    t0 = time.perf_counter()
    try:
        r = await client.get(url, follow_redirects=True, timeout=15.0)
        r.raise_for_status()
        return (time.perf_counter() - t0) * 1000
    except Exception:
        return float("nan")


async def measure_url(client: httpx.AsyncClient, url: str, runs: int = 5) -> dict:
    """Measure a URL's load time over several runs."""
    samples = []
    for _ in range(runs):
        t = await time_request(client, url)
        if t == t:  # not NaN
            samples.append(t)
        await asyncio.sleep(0.5)
    if not samples:
        return {"n": 0, "p50": None, "p95": None, "mean": None}
    s = sorted(samples)
    return {
        "n": len(s),
        "p50": statistics.median(s),
        "p95": s[int(0.95 * (len(s) - 1))],
        "mean": statistics.mean(s),
    }


def task_total_time_ms(task_name: str, stack: str, url_times: dict) -> dict:
    """Compute total wall-clock time estimate for a task in a stack."""
    actions = TASKS[task_name][stack]
    total_ms = 0.0
    breakdown = {}
    n_actions = 0
    n_net = 0
    n_switches = 0
    for action_type, count, url in actions:
        if action_type == "net":
            t = url_times.get(url, {}).get("p50", 1500)
            if t is None:
                t = 1500
            contribution = t * count
            n_net += count
        else:
            contribution = UI_ACTION_MS[action_type] * count
            n_actions += count
            if action_type == "tab_switch":
                n_switches += count
        breakdown[f"{action_type}_x{count}"] = contribution
        total_ms += contribution
    return {
        "total_ms": total_ms,
        "n_actions": n_actions,
        "n_net_requests": n_net,
        "n_app_switches": n_switches,
        "breakdown": breakdown,
    }


async def main():
    timeout = httpx.Timeout(20.0, connect=10.0)
    print("Measuring URL load times for all tasks...")
    urls = set()
    for t in TASKS.values():
        for stack in ["scholarhub", "overleaf"]:
            for action_type, count, url in t[stack]:
                if action_type == "net" and url:
                    urls.add(url)
    print(f"  unique URLs: {len(urls)}")

    url_times = {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        for url in urls:
            print(f"  measuring {url}")
            url_times[url] = await measure_url(client, url, runs=8)
            print(f"    p50={url_times[url].get('p50')}")

    # Compute task times
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ui_action_times_ms": UI_ACTION_MS,
        "url_load_times_ms": url_times,
        "tasks": {},
    }
    for task_name, t in TASKS.items():
        sh = task_total_time_ms(task_name, "scholarhub", url_times)
        ov = task_total_time_ms(task_name, "overleaf", url_times)
        reduction = 1 - (sh["total_ms"] / ov["total_ms"]) if ov["total_ms"] else 0
        results["tasks"][task_name] = {
            "label": t["label"],
            "scholarhub": sh,
            "overleaf_zotero_chatgpt": ov,
            "time_reduction_pct": reduction * 100,
            "action_reduction_pct": (
                1 - (sh["n_actions"] / ov["n_actions"]) if ov["n_actions"] else 0
            ) * 100,
        }

    out_path = SCRIPT_DIR / "study3_workflow_timing.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")

    # Summary table
    print(f"\n{'Task':30s} {'SH ms':>10s} {'Alt ms':>10s} {'TimeRed':>8s} {'ActRed':>8s}")
    total_sh = total_ov = 0.0
    total_sh_a = total_ov_a = 0
    for tn, d in results["tasks"].items():
        sh_ms = d["scholarhub"]["total_ms"]
        ov_ms = d["overleaf_zotero_chatgpt"]["total_ms"]
        total_sh += sh_ms
        total_ov += ov_ms
        total_sh_a += d["scholarhub"]["n_actions"]
        total_ov_a += d["overleaf_zotero_chatgpt"]["n_actions"]
        print(f"{tn:30s} {sh_ms:>10.0f} {ov_ms:>10.0f} "
              f"{d['time_reduction_pct']:>7.1f}% {d['action_reduction_pct']:>7.1f}%")
    print(f"{'TOTAL':30s} {total_sh:>10.0f} {total_ov:>10.0f} "
          f"{(1-total_sh/total_ov)*100:>7.1f}% {(1-total_sh_a/total_ov_a)*100:>7.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
