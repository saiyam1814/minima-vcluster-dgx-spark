#!/usr/bin/env python3
"""Run Qwen and Gemma simultaneously through the live Minima router."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import statistics
import time

from minima_stream_benchmark import stream_once


MODELS = ("qwen3.6-27b", "gemma4-31b-it")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--batches", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    batches = []
    for _ in range(args.batches):
        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                model: executor.submit(
                    stream_once,
                    args.base_url,
                    model,
                    args.max_tokens,
                    args.timeout,
                )
                for model in MODELS
            }
            requests = {model: future.result() for model, future in futures.items()}
        wall_seconds = time.perf_counter() - started
        output_tokens = sum(
            request.get("completion_tokens") or 0 for request in requests.values()
        )
        batches.append(
            {
                "wall_seconds": round(wall_seconds, 4),
                "output_tokens": output_tokens,
                "aggregate_output_tokens_per_second": round(
                    output_tokens / wall_seconds, 2
                ),
                "requests": requests,
            }
        )

    rates = [batch["aggregate_output_tokens_per_second"] for batch in batches]
    output = {
        "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "test": "simultaneous Qwen and Gemma streaming inference",
        "endpoint": "redacted-private-spark-endpoint",
        "method": {
            "batches": args.batches,
            "requests_per_batch": 2,
            "models": list(MODELS),
            "max_tokens_per_request": args.max_tokens,
            "warning": "Minima-only co-residency profile; not a reference-vLLM comparison.",
        },
        "batches": batches,
        "summary": {
            "successful_batches": sum(
                all(request.get("ok") for request in batch["requests"].values())
                for batch in batches
            ),
            "aggregate_output_tokens_per_second_median": round(
                statistics.median(rates), 2
            ),
            "aggregate_output_tokens_per_second_min": round(min(rates), 2),
            "aggregate_output_tokens_per_second_max": round(max(rates), 2),
        },
    }
    print(json.dumps(output, indent=2))
    return 0 if output["summary"]["successful_batches"] == args.batches else 1


if __name__ == "__main__":
    raise SystemExit(main())
