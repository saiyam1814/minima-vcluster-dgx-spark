# Minima DGX Spark Demo Curls

These are the sanitized public commands for the live dual-model stack. Run them on the Spark so the endpoint remains loopback-only in the article.

```bash
export MINIMA_BASE_URL="http://127.0.0.1:8000/v1"
```

## List models

```bash
curl -fsS "$MINIMA_BASE_URL/models" | python3 -m json.tool
```

## Qwen text

```bash
curl -fsS "$MINIMA_BASE_URL/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3.6-27b",
    "messages": [{"role": "user", "content": "In 2-3 sentences, why does speculative decoding make LLM inference faster?"}],
    "max_tokens": 200,
    "temperature": 0,
    "chat_template_kwargs": {"enable_thinking": false}
  }' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"])'
```

## Gemma text

```bash
curl -fsS "$MINIMA_BASE_URL/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gemma4-31b-it",
    "messages": [{"role": "user", "content": "In 2-3 sentences, why does speculative decoding make LLM inference faster?"}],
    "max_tokens": 200,
    "temperature": 0
  }' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"])'
```

## Gemma image

This public-domain NARA image shows a forklift that fell through a warehouse floor. Wikimedia requires a user-agent header for the download.

```bash
curl -fsSL -A "demo-fetch/1.0" \
  -o warehouse_incident.jpg \
  "https://upload.wikimedia.org/wikipedia/commons/thumb/7/75/FORKLIFT_ACCIDENT_-_NARA_-_17450151.jpg/960px-FORKLIFT_ACCIDENT_-_NARA_-_17450151.jpg"
```

Linux:

```bash
{
  printf '{"model":"gemma4-31b-it","messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,'
  base64 -w0 warehouse_incident.jpg
  printf '"}},{"type":"text","text":"What incident happened in this image?"}]}],"max_tokens":200,"temperature":0}'
} \
  | curl -fsS "$MINIMA_BASE_URL/chat/completions" \
      -H 'Content-Type: application/json' \
      -d @- \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"])'
```

On macOS, replace `base64 -w0 warehouse_incident.jpg` with:

```bash
base64 -i warehouse_incident.jpg
```

Streaming the JSON body through standard input avoids the Linux shell argument-size limit for larger images.

## Gemma visible reasoning

Gemma's chat template defaults thinking off. When enabled, the reasoning parser separates the trace into `message.reasoning` and the answer into `message.content`.

```bash
curl -fsS "$MINIMA_BASE_URL/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gemma4-31b-it",
    "messages": [{"role": "user", "content": "Alice has 3 brothers and 2 sisters. How many sisters does Alice'\''s brother have?"}],
    "max_tokens": 1024,
    "temperature": 0,
    "chat_template_kwargs": {"enable_thinking": true}
  }' \
  | python3 -c 'import json,sys; m=json.load(sys.stdin)["choices"][0]["message"]; print("REASONING:\n", m.get("reasoning"), "\n\nANSWER:\n", m["content"])'
```

The reasoning trace consumes part of `max_tokens`. Do not log or expose chain-of-thought in a production application without a deliberate product and security review.
