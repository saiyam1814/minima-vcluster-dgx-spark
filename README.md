# Two Teams, Two Models, One DGX Spark

Manifests and scripts from the vCluster Labs article *Two Teams, Two Models, One DGX Spark: Minima-Optimized Models with vCluster*.

Two [Minima](https://mnma.ai/)-optimized models stay resident on a single NVIDIA DGX Spark behind one OpenAI-compatible router. vCluster Standalone turns that machine into a control plane cluster, and each of two teams gets its own tenant cluster on it. Their workloads call the shared model endpoint.

The article carries the full walkthrough and the captured output. This repository is just the files you need to run it.

## Contents

| Path | What it is |
|---|---|
| `manifests/vcluster-standalone.yaml` | The tested vCluster Standalone configuration |
| `manifests/team-qwen-workload.yaml`, `manifests/team-gemma-workload.yaml` | Each team's workload, applied **inside** that team's own tenant cluster |
| `scripts/minima_stream_benchmark.py` | Streaming time-to-first-token, decode rate, and aggregate throughput |
| `scripts/mixed_model_benchmark.py` | Both models answering at the same time |
| `scripts/dual_model_smoke.py` | Concurrent deterministic smoke test |
| `scripts/gemma_vision_smoke.py` | Multimodal check against a diagram |
| `demo-curls.md` | Sanitized text, vision, and reasoning requests, pure curl |

## Giving each team its own cluster

On a DGX Spark that already serves models and already runs vCluster Standalone:

```bash
export KUBECONFIG=/var/lib/vcluster/kubeconfig.yaml

vcluster create team-qwen  --namespace team-qwen  --add=false
vcluster create team-gemma --namespace team-gemma --add=false
```

Each team then applies its own workload inside its own cluster. The manifests carry no namespace field, which is the point:

```bash
vcluster connect team-qwen --namespace team-qwen \
  -- kubectl apply -f manifests/team-qwen-workload.yaml
vcluster connect team-gemma --namespace team-gemma \
  -- kubectl apply -f manifests/team-gemma-workload.yaml
```

## Benchmarks

Run these from a laptop against the router, not on the Spark:

```bash
export MINIMA_BASE_URL="http://<SPARK_TAILSCALE_IP>:8000/v1"
python3 scripts/minima_stream_benchmark.py \
  --base-url "$MINIMA_BASE_URL" \
  --max-tokens 128 --serial-runs 5 --concurrency 4 --concurrent-batches 3
```

These scripts are ours, not Minima's. They never restart or reconfigure a backend, so they measure the service as handed over. Numbers they produce are client-observed, not vendor specifications, and they are not a comparison against stock vLLM.

## Scope

Two teams each get their own Kubernetes API on one GPU host. They do not get hard tenant isolation: one Spark means both clusters sit on one node, one GPU, and one kernel. Hard tenant isolation needs a node per tenant, which is what Private Nodes are for.

## Notes

Pinned to vCluster `v0.36.0` and Kubernetes `v1.36.0` on Ubuntu 24.04 (arm64, NVIDIA GB10). Private network addresses appear as `<SPARK_LAN_IP>` and `<SPARK_TAILSCALE_IP>`.

## Links

- [vCluster](https://www.vcluster.com/)
- [vCluster Standalone](https://www.vcluster.com/docs/vcluster/deploy/control-plane/binary/basics)
- [Building an inference platform](https://www.vcluster.com/docs/vcluster/introduction/inference-platform)
- [Minima](https://mnma.ai/)
