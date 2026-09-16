# Minima deployment section — owners: David Mayboroda and Sergii Kozyrev

This is the unmistakable partner-owned section for the joint article. Replace
the prompts below with approved public instructions before publication.

## What Minima should supply

1. The supported DGX Spark prerequisites: OS image, driver, CUDA/runtime, disk,
   and memory requirements.
2. The approved model artifact identifiers and immutable revisions or digests.
3. The approved install path:
   - host/systemd commands for reproducing the current handoff, or
   - container image and command, or
   - Helm chart, version, and non-secret values.
4. The router and health/readiness contract, including the public model IDs.
5. The approved commands for start, stop, upgrade, and rollback.
6. Which optimizations may be named publicly for each model.
7. A reference-vLLM benchmark arm, or approval of wording that the published
   numbers profile Minima only and do not prove a speedup.
8. Raw recovery and concurrency artifacts for any Minima-reported claims.

## Current verified public surface

```text
qwen3.6-27b   -> loopback :8867
gemma4-31b-it -> loopback :8868
model router  -> :8000, OpenAI-compatible
```

The article can reproduce client calls and the vCluster integration without
publishing private model files, credentials, tailnet addresses, or proprietary
installation details.
