# Two Teams, Two Models, One DGX Spark

Companion repository for the vCluster Labs article *Two Teams, Two Models, One DGX Spark: Minima-Optimized Models with vCluster*.

Two [Minima](https://mnma.ai/)-optimized models stay resident on a single NVIDIA DGX Spark behind one OpenAI-compatible router. vCluster Standalone turns that same machine into a control plane cluster, and each of two teams gets its own tenant cluster on it. Their workloads call the shared model endpoint, one team's entire cluster is destroyed and rebuilt, and the models keep serving throughout.

Everything here was run on the actual machine. Every number in the article traces to a file in `evidence/`.

## What is in here

| Path | What it is |
|---|---|
| `runbooks/04-single-node-standalone-demo.md` | Installing vCluster Standalone next to already-running model services |
| `runbooks/05-two-tenant-clusters-demo.md` | Creating one tenant cluster per team on that Standalone instance |
| `manifests/vcluster-standalone.yaml` | The tested Standalone configuration |
| `manifests/team-qwen-workload.yaml`, `manifests/team-gemma-workload.yaml` | Each team's workload, applied **inside** that team's own tenant cluster |
| `scripts/minima_stream_benchmark.py` | The streaming benchmark behind the article's tables |
| `scripts/dual_model_smoke.py`, `mixed_model_benchmark.py`, `gemma_vision_smoke.py` | Smoke tests and contention profile |
| `demo-curls.md` | Sanitized text, vision, and reasoning requests, pure curl |
| `evidence/platform/` | Captured command output from the run |
| `evidence/inference/` | Raw per-request JSON behind the performance tables |
| `diagrams/` | Article diagrams as SVG and PNG |

## Quick start

The runbooks assume a DGX Spark that is already serving models and already has a vCluster Standalone instance installed. From there, giving each team its own cluster is two commands:

```bash
export KUBECONFIG=/var/lib/vcluster/kubeconfig.yaml
vcluster create team-qwen  --namespace team-qwen  --add=false
vcluster create team-gemma --namespace team-gemma --add=false
```

Then each team applies its own workload inside its own cluster:

```bash
vcluster connect team-qwen --namespace team-qwen \
  -- kubectl apply -f manifests/team-qwen-workload.yaml
```

`runbooks/05-two-tenant-clusters-demo.md` has the full sequence, including the isolation checks and the destroy-and-rebuild test.

## What the results do and do not show

The run shows two teams each holding their own Kubernetes API on one GPU host, with no visibility into each other, both reaching a shared host-managed model endpoint, and one team's cluster being destroyed and rebuilt in well under a minute without disturbing the other.

It does not show hard tenant isolation between the teams. There is one Spark, so both clusters sit on one node, one GPU, and one kernel. Hard tenant isolation needs a node per tenant, which is what Private Nodes are for. GPU scheduling, vCluster Platform, and vMetal were not exercised.

## Versions

Pinned to vCluster `v0.36.0` and Kubernetes `v1.36.0` on Ubuntu 24.04 (arm64, NVIDIA GB10).

## Redaction

Private network addresses appear as `<SPARK_LAN_IP>` and `<SPARK_TAILSCALE_IP>`. Credentials, kubeconfigs, join tokens, model files, and Minima implementation details that have not been cleared for publication are not in this repository.

## Links

- [vCluster](https://www.vcluster.com/)
- [vCluster Standalone](https://www.vcluster.com/docs/vcluster/deploy/control-plane/binary/basics)
- [Building an inference platform](https://www.vcluster.com/docs/vcluster/introduction/inference-platform)
- [For AI Clouds, Hard Tenant Isolation Is Not Optional](https://www.vcluster.com/blog/ai-clouds-hard-tenant-isolation-not-optional)
- [Minima](https://mnma.ai/)
