#!/usr/bin/env python3
"""Client-observed streaming benchmark for the live Minima model router.

This does not restart or reconfigure either backend. It measures the service as
handed over: one OpenAI-compatible router with both models resident.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import math
import statistics
import time
import urllib.error
import urllib.request


MODELS = ("qwen3.6-27b", "gemma4-31b-it")
PROMPT = (
    "Explain how a platform team can turn scarce GPU servers into a repeatable "
    "internal product. Write a dense technical answer of at least 250 words. "
    "Continue until the server stops generation; do not finish early."
)


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def request_body(model: str, max_tokens: int) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if model.startswith("qwen"):
        body["chat_template_kwargs"] = {"enable_thinking": False}
    return body


def stream_once(base_url: str, model: str, max_tokens: int, timeout: float) -> dict:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(request_body(model, max_tokens)).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    first_content_at = None
    last_content_at = None
    pieces: list[str] = []
    usage = None
    finish_reason = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload_text = line[5:].strip()
                if payload_text == "[DONE]":
                    break
                payload = json.loads(payload_text)
                if payload.get("usage"):
                    usage = payload["usage"]
                for choice in payload.get("choices", []):
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]
                    content = choice.get("delta", {}).get("content")
                    if content:
                        now = time.perf_counter()
                        if first_content_at is None:
                            first_content_at = now
                        last_content_at = now
                        pieces.append(content)
        finished = time.perf_counter()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "model": model,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_seconds": round(time.perf_counter() - started, 4),
        }

    completion_tokens = (usage or {}).get("completion_tokens")
    prompt_tokens = (usage or {}).get("prompt_tokens")
    total_seconds = finished - started
    ttft_seconds = None if first_content_at is None else first_content_at - started
    decode_seconds = (
        None
        if first_content_at is None or last_content_at is None
        else last_content_at - first_content_at
    )
    decode_tokens_per_second = None
    if completion_tokens and completion_tokens > 1 and decode_seconds and decode_seconds > 0:
        decode_tokens_per_second = (completion_tokens - 1) / decode_seconds
    end_to_end_tokens_per_second = None
    if completion_tokens and total_seconds > 0:
        end_to_end_tokens_per_second = completion_tokens / total_seconds

    content = "".join(pieces)
    return {
        "ok": True,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "finish_reason": finish_reason,
        "ttft_seconds": None if ttft_seconds is None else round(ttft_seconds, 4),
        "decode_seconds": None if decode_seconds is None else round(decode_seconds, 4),
        "total_seconds": round(total_seconds, 4),
        "decode_tokens_per_second": (
            None
            if decode_tokens_per_second is None
            else round(decode_tokens_per_second, 2)
        ),
        "end_to_end_tokens_per_second": (
            None
            if end_to_end_tokens_per_second is None
            else round(end_to_end_tokens_per_second, 2)
        ),
        "content_prefix": content[:120],
        "content_suffix": content[-120:],
    }


def summarize(runs: list[dict]) -> dict:
    valid = [run for run in runs if run.get("ok")]
    fields = (
        "ttft_seconds",
        "decode_tokens_per_second",
        "end_to_end_tokens_per_second",
        "total_seconds",
    )
    summary = {"successful_requests": len(valid), "total_requests": len(runs)}
    for field in fields:
        values = [float(run[field]) for run in valid if run.get(field) is not None]
        summary[field] = {
            "median": round(statistics.median(values), 3),
            "p95": round(percentile(values, 0.95), 3),
            "min": round(min(values), 3),
            "max": round(max(values), 3),
        }
    return summary


def run_concurrent_batch(
    base_url: str,
    model: str,
    max_tokens: int,
    concurrency: int,
    timeout: float,
) -> dict:
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(stream_once, base_url, model, max_tokens, timeout)
            for _ in range(concurrency)
        ]
        runs = [future.result() for future in futures]
    wall_seconds = time.perf_counter() - started
    successful = [run for run in runs if run.get("ok")]
    output_tokens = sum(run.get("completion_tokens") or 0 for run in successful)
    return {
        "concurrency": concurrency,
        "wall_seconds": round(wall_seconds, 4),
        "successful_requests": len(successful),
        "output_tokens": output_tokens,
        "aggregate_output_tokens_per_second": round(output_tokens / wall_seconds, 2),
        "requests": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--serial-runs", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--concurrent-batches", type=int, default=3)
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Omit per-request content and concurrent request records from JSON output",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    result = {
        "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "test": "client-observed Minima streaming inference profile",
        "endpoint": "redacted-private-spark-endpoint",
        "method": {
            "streaming": True,
            "temperature": 0,
            "max_tokens": args.max_tokens,
            "serial_runs": args.serial_runs,
            "concurrency": args.concurrency,
            "concurrent_batches": args.concurrent_batches,
            "decode_rate_formula": "(completion_tokens - 1) / (last_content_byte_time - first_content_byte_time)",
            "ttft_scope": "client-observed request start to first non-empty content event",
            "client_path": ("loopback on the model host" if "127.0.0.1" in args.base_url or "localhost" in args.base_url
                            else "remote client over the network path in --base-url"),
            "warning": "This profiles Minima only; it is not a comparison against reference vLLM.",
        },
        "models": {},
    }

    exit_code = 0
    for model in MODELS:
        warmup = stream_once(args.base_url, model, args.max_tokens, args.timeout)
        serial = [
            stream_once(args.base_url, model, args.max_tokens, args.timeout)
            for _ in range(args.serial_runs)
        ]
        concurrent = [
            run_concurrent_batch(
                args.base_url,
                model,
                args.max_tokens,
                args.concurrency,
                args.timeout,
            )
            for _ in range(args.concurrent_batches)
        ]
        if args.compact:
            for run in [warmup, *serial]:
                run.pop("content_prefix", None)
                run.pop("content_suffix", None)
            for batch in concurrent:
                batch.pop("requests", None)
        aggregate_rates = [
            batch["aggregate_output_tokens_per_second"] for batch in concurrent
        ]
        result["models"][model] = {
            "warmup": warmup,
            "serial_runs": serial,
            "serial_summary": summarize(serial),
            "concurrent_batches": concurrent,
            "concurrent_summary": {
                "aggregate_output_tokens_per_second_median": round(
                    statistics.median(aggregate_rates), 2
                ),
                "aggregate_output_tokens_per_second_min": round(min(aggregate_rates), 2),
                "aggregate_output_tokens_per_second_max": round(max(aggregate_rates), 2),
            },
        }
        if not warmup.get("ok") or not all(run.get("ok") for run in serial):
            exit_code = 1
        if not all(
            batch["successful_requests"] == args.concurrency for batch in concurrent
        ):
            exit_code = 1

    print(json.dumps(result, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
