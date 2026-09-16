#!/usr/bin/env python3
"""Send one deterministic request to each live Minima model concurrently."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import time
import urllib.error
import urllib.request


REQUESTS = {
    "qwen3.6-27b": {
        "prompt": "Reply with exactly: Qwen on Spark is ready",
        "max_tokens": 32,
        "extra": {"chat_template_kwargs": {"enable_thinking": False}},
    },
    "gemma4-31b-it": {
        "prompt": "Reply with exactly: Gemma on Spark is ready",
        "max_tokens": 64,
        "extra": {},
    },
}


def complete(base_url: str, model: str, timeout: float) -> dict:
    spec = REQUESTS[model]
    body = {
        "model": model,
        "messages": [{"role": "user", "content": spec["prompt"]}],
        "max_tokens": spec["max_tokens"],
        "temperature": 0,
        **spec["extra"],
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
        elapsed = time.perf_counter() - started
        message = payload["choices"][0]["message"]
        return {
            "model": model,
            "ok": True,
            "elapsed_seconds": round(elapsed, 3),
            "content": message.get("content"),
            "usage": payload.get("usage"),
        }
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
        return {
            "model": model,
            "ok": False,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000/v1",
        help="OpenAI-compatible base URL (default: %(default)s)",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    observed_at = dt.datetime.now(dt.timezone.utc).isoformat()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(complete, args.base_url, model, args.timeout): model
            for model in REQUESTS
        }
        results = [future.result() for future in concurrent.futures.as_completed(futures)]

    results.sort(key=lambda item: item["model"])
    output = {
        "observed_at_utc": observed_at,
        "test": "dual-model deterministic concurrent smoke test",
        "results": results,
    }
    print(json.dumps(output, indent=2))
    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
