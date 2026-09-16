#!/usr/bin/env python3
"""Send a local image to the live Gemma model through the Minima router."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import time
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    mime_type = mimetypes.guess_type(args.image.name)[0] or "image/png"
    encoded = base64.b64encode(args.image.read_bytes()).decode("ascii")
    body = {
        "model": "gemma4-31b-it",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Describe the architecture in this diagram. Name the two model "
                            "backends and the client-facing port. Keep the answer under 90 words."
                        ),
                    },
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 160,
    }
    request = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=args.timeout) as response:
        payload = json.load(response)
    output = {
        "model": payload.get("model"),
        "image": args.image.name,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "usage": payload.get("usage"),
        "answer": payload["choices"][0]["message"].get("content"),
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
