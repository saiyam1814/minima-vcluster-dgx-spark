# Evidence Contract

Every publishable result needs a raw, timestamped artifact in this directory. Keep proprietary model files, credentials, kubeconfigs, SSH keys, join tokens, and full environment dumps out of the repository.

Recommended layout after the first run:

```text
evidence/
├── environment/
│   ├── spark-host.txt
│   ├── gpu.txt
│   ├── image-digests.txt
│   └── model-and-tokenizer.txt
├── inference/
│   ├── manifest.csv
│   ├── vllm/
│   └── minima/
├── quality/
├── platform/
│   ├── create-to-ready/
│   ├── recovery/
│   └── reassignment/
└── screenshots/
```

Use UTC timestamps and immutable IDs. A useful run ID is:

```text
YYYYMMDDTHHMMSSZ_<arm>_<profile>_c<concurrency>_r<repeat>
```

The inference manifest should contain at least:

```csv
run_id,started_at_utc,arm,model_revision,image_digest,profile,concurrency,input_tokens,requested_output_tokens,completed,failed,wall_seconds,output_tokens,notes
```

Raw per-request JSON or JSONL remains the source of truth. CSV summaries are derived artifacts.

## Redaction check

Before adding a file, scan it for common secret markers:

```bash
grep -RniE 'authorization:|bearer |api[_-]?key|token=|password|private key' evidence/ || true
```

Manually review every match. A clean automated scan is not proof that a file contains no secret.

