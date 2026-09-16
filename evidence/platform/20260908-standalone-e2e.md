# vCluster Standalone + Minima end-to-end evidence

Run date: 2026-09-08 UTC  
Host: `spark-5385` (`aarch64`, Ubuntu 24.04.4 LTS)  
Scope: one self-managed vCluster Standalone Control Plane Cluster on the DGX Spark, with the control-plane host joined as its only worker. The Minima router and model backends remained host-managed.

## Protected baseline

- LAN SSH succeeded through `<SPARK_LAN_IP>`.
- Tailscale SSH succeeded through `<SPARK_TAILSCALE_IP>`.
- The Minima router listened on `0.0.0.0:8000`.
- `GET /v1/models` returned `gemma4-31b-it` and `qwen3.6-27b`, each with `max_model_len: 32768`.
- `vcluster` and `kubelet` were inactive; system `containerd` and Docker were active.
- Docker's existing `docker-model-runner` container was running.

## Installed versions and reviewed host integration

```text
$ vcluster --version
vcluster version 0.36.0
```

The machine already had containerd and Docker sharing `/run/containerd/containerd.sock`. The final Standalone configuration therefore disabled containerd management, selected that CRI socket, and used a `preJoinCommands` hook to start the preserved runtime after the Standalone node-reset phase. Host swap remained enabled; kubelet was configured with `failSwapOn: false` and `NoSwap` for Pods.

## First attempt and corrections

The initial control plane started, but no Node appeared. The join log showed that the node-reset phase stopped the existing containerd, followed by:

```text
[ERROR CRI]: could not connect to the container runtime ...
dial unix /var/run/containerd/containerd.sock: connect: no such file or directory
```

After adding `preJoinCommands: [systemctl start containerd]` and restarting only `vcluster.service`, the node joined successfully.

UFW then blocked Pod-to-host traffic from `cni0`. Kernel logs showed packets from `10.244.0.x` denied on ports 8443 and 8000. Three source- and interface-scoped rules were added for:

- Pod CIDR to the Standalone API (`8443/tcp`)
- Pod CIDR to the Minima router (`8000/tcp`)
- Konnectivity agent to kubelet logs (`10250/tcp`)

The first client Pods exposed one manifest issue: `curlimages/curl:8.12.1` declares the named user `curl_user`, so Kubernetes could not prove `runAsNonRoot`. The image's actual identity was verified as UID 101 and GID 102, and both Jobs were pinned to those numeric values.

## Cluster result

```text
$ kubectl get nodes -o wide
NAME         STATUS   ROLES                  AGE   VERSION   INTERNAL-IP      EXTERNAL-IP   OS-IMAGE             KERNEL-VERSION               CONTAINER-RUNTIME
spark-5385   Ready    control-plane,master   40s   v1.36.0   <SPARK_LAN_IP>   <none>        Ubuntu 24.04.4 LTS   6.17.0-1018-nvidia (arm64)   containerd://2.2.1
```

The final system workload check showed:

```text
NAMESPACE            NAME                                      READY   STATUS
kube-flannel         kube-flannel-ds-lqvrp                     1/1     Running
kube-system          coredns-df8c87f55-fvbxg                   1/1     Running
kube-system          konnectivity-agent-599bbdf4c8-tqs7d       1/1     Running
kube-system          kube-proxy-dmgtm                          1/1     Running
local-path-storage   local-path-provisioner-6d484fd799-w66sg   1/1     Running
```

## First successful client run

Both Jobs completed concurrently:

```text
NAMESPACE    NAME        STATUS     COMPLETIONS   DURATION
team-gemma   ask-gemma   Complete   1/1           4s
team-qwen    ask-qwen    Complete   1/1           3s
```

Their raw response content was:

```text
qwen3.6-27b hello from team-qwen
gemma4-31b-it hello from team-gemma
```

## Delete-and-recreate result

The complete manifest was deleted, including both namespaces, and applied again. The second run also completed:

```text
job.batch/ask-gemma condition met
job.batch/ask-qwen condition met

NAMESPACE    NAME        STATUS     COMPLETIONS   DURATION
team-gemma   ask-gemma   Complete   1/1           5s
team-qwen    ask-qwen    Complete   1/1           4s
```

Parsed Job logs from the second run:

```text
qwen3.6-27b hello from team-qwen {'prompt_tokens': 21, 'total_tokens': 27, 'completion_tokens': 6, 'prompt_tokens_details': None}
gemma4-31b-it hello from team-gemma {'prompt_tokens': 23, 'total_tokens': 30, 'completion_tokens': 7, 'prompt_tokens_details': None}
```

## Final coexistence checks

All protected and newly installed services were active:

```text
ssh        active
tailscaled active
vcluster   active
kubelet    active
containerd active
docker     active

vllm-qwen  active
vllm-gemma active
model-router active
```

The Minima router still returned both models with 32,768-token context limits. Fresh SSH and model-API checks succeeded independently through both LAN and Tailscale. Docker still reported its pre-existing `docker-model-runner` container as `Up 2 days`.

Memory after the run:

```text
               total        used        free      shared  buff/cache   available
Mem:           121Gi       100Gi       2.3Gi       459Mi        20Gi        21Gi
Swap:           15Gi       2.9Gi        13Gi
```

## Final live recheck

At `2026-09-08T07:13:29Z`, a fresh read-only SSH check confirmed that the node was still `Ready`, both recreated Jobs were still `Complete`, and their logs still returned:

```text
qwen3.6-27b hello from team-qwen
gemma4-31b-it hello from team-gemma
```

The `vllm-qwen`, `vllm-gemma`, and `model-router` user services all reported `active`. The live `/v1/models` response still listed `gemma4-31b-it` and `qwen3.6-27b`, each with `max_model_len=32768`.

## Claim boundary

This run proves coexistence and reproducible HTTP client execution inside a single-node vCluster Standalone Control Plane Cluster. The two namespaces are not separate tenant clusters, the models remain host-managed, no GPU scheduling was exercised, vCluster Platform was not installed, and vMetal did not provision the Spark.
