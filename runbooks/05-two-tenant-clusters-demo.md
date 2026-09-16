# Two tenant clusters on the Spark, one per team

Status: **executed successfully on 16 September 2026.** Captured output is in [`evidence/platform/20260916-two-tenant-clusters.md`](../evidence/platform/20260916-two-tenant-clusters.md). One correction from the run: `status.hostIP` does resolve to the Spark's real LAN address inside a tenant cluster, so the ConfigMap fallback described in Step 3 was not needed.

This replaces the namespace-per-team shape used in the 8 September run. Namespaces are what vCluster exists to replace, so a vCluster article should not use them to represent teams. Here each team gets a real tenant cluster with its own Kubernetes API, and both teams' workloads call the same host-managed Minima endpoint.

## Why this shape

The [Standalone documentation](https://www.vcluster.com/docs/vcluster/deploy/control-plane/binary/basics) states it directly: to use vCluster Standalone as a control plane cluster for tenant clusters, point your kubectl context at the Standalone instance. So the cluster already installed on the Spark on 8 September does not need to be rebuilt. It becomes the control plane cluster, and two tenant clusters are deployed into it.

```text
DGX Spark, one Linux host
├── Minima model plane, host-managed
│     └── OpenAI-compatible router :8000
│           ├── qwen3.6-27b    :8867
│           └── gemma4-31b-it  :8868
└── vCluster Standalone instance  ← acts as the CONTROL PLANE CLUSTER
      ├── tenant cluster: team-qwen   (own API server, own kubeconfig)
      └── tenant cluster: team-gemma  (own API server, own kubeconfig)
```

Each team's pods still run on the Spark, because the Spark is the only node. What changes is the boundary the team is handed: a Kubernetes API of their own rather than a namespace inside someone else's cluster.

## Preconditions

Confirm all of these before starting:

- the Standalone node is `Ready` (`kubectl get nodes` against `/var/lib/vcluster/kubeconfig.yaml`);
- the three UFW rules from [runbook 04](04-single-node-standalone-demo.md) are still present;
- `GET /v1/models` on the Spark returns both `qwen3.6-27b` and `gemma4-31b-it`;
- `local-path-provisioner` is `Running`, since each tenant control plane claims a PVC;
- at least 4 GiB of host memory is free beyond what the two models hold.

Record the free memory before and after. Two virtual control planes are small, but the Spark runs close to full with both models resident.

## Where to run the commands

Run on the Spark. The Standalone API advertises the Spark's LAN address, so a Mac on a different network cannot reach it over Tailscale without extra routing. Install the CLI on the Spark:

```bash
curl -L -o vcluster \
  "https://github.com/loft-sh/vcluster/releases/download/v0.36.1/vcluster-linux-arm64"
sudo install -c -m 0755 vcluster /usr/local/bin && rm -f vcluster
vcluster --version
```

Point the CLI at the Standalone instance. This is the step that makes it the control plane cluster:

```bash
export KUBECONFIG=/var/lib/vcluster/kubeconfig.yaml
kubectl config current-context
kubectl get nodes -o wide
```

## Step 1: Create the two tenant clusters

`--add=false` keeps the CLI from trying to register with a vCluster Platform, which is not installed here.

```bash
vcluster create team-qwen  --namespace team-qwen  --add=false --connect=false
vcluster create team-gemma --namespace team-gemma --add=false --connect=false

vcluster list
```

Expect two entries in `Running`. Capture that output.

On the control plane cluster, each tenant's virtual control plane appears as a pod in its own namespace:

```bash
kubectl get pods -A | grep -E 'team-qwen|team-gemma'
```

## Step 2: Prove the boundary is a cluster, not a namespace

This is the evidence the previous run could not produce. From inside `team-qwen`:

```bash
vcluster connect team-qwen --namespace team-qwen -- kubectl get namespaces
vcluster connect team-qwen --namespace team-qwen -- kubectl get nodes
```

Record both. The namespace list should contain the tenant cluster's own namespaces and **not** `team-gemma`. The node list is the tenant's own view of its capacity.

Repeat for `team-gemma`. If either team can enumerate the other's objects, stop and record that before going further, because the article's central claim depends on this output.

## Step 3: Each team deploys its own workload

The manifests carry no namespace. They land in each team's own cluster.

```bash
vcluster connect team-qwen  --namespace team-qwen \
  -- kubectl apply -f /tmp/team-qwen-workload.yaml
vcluster connect team-gemma --namespace team-gemma \
  -- kubectl apply -f /tmp/team-gemma-workload.yaml

vcluster connect team-qwen  --namespace team-qwen \
  -- kubectl wait --for=condition=complete job/ask-qwen --timeout=300s
vcluster connect team-gemma --namespace team-gemma \
  -- kubectl wait --for=condition=complete job/ask-gemma --timeout=300s
```

Capture the logs from inside each tenant cluster:

```bash
vcluster connect team-qwen  --namespace team-qwen  -- kubectl logs job/ask-qwen
vcluster connect team-gemma --namespace team-gemma -- kubectl logs job/ask-gemma
```

**Resolved on 16 September.** A probe Job inside `team-qwen` returned `status.hostIP = <SPARK_LAN_IP>`, the Spark's real LAN address, and both that address and the hostIP path returned HTTP 200 from the router. Pod status is synced back from the real pod, so the synthetic node address in the tenant's node object does not leak into `status.hostIP`. No ConfigMap fallback was needed and the workload manifests were unchanged.

## Step 4: Delete and recreate

Same test as before, one level up. Delete the workloads inside each tenant cluster and reapply:

```bash
vcluster connect team-qwen --namespace team-qwen \
  -- kubectl delete -f /tmp/team-qwen-workload.yaml --wait=true
vcluster connect team-qwen --namespace team-qwen \
  -- kubectl apply -f /tmp/team-qwen-workload.yaml
```

Then delete and recreate an entire tenant cluster, which the namespace version could not demonstrate at all:

```bash
vcluster delete team-qwen --namespace team-qwen
vcluster create team-qwen --namespace team-qwen --add=false --connect=false
vcluster connect team-qwen --namespace team-qwen \
  -- kubectl apply -f /tmp/team-qwen-workload.yaml
```

Confirm `team-gemma` stayed `Running` and its Job stayed `Complete` throughout. A team's cluster being disposable without touching the neighbour is the strongest single result available from this hardware.

## Step 5: Confirm the model plane is untouched

Repeat the final checks from runbook 04:

```bash
# Minima runs under the minima-setup user manager, so systemctl --user as
# another user reports inactive. Check the API instead.
curl -fsS http://127.0.0.1:8000/v1/models | python3 -m json.tool
systemctl is-active ssh tailscaled vcluster kubelet containerd docker
free -h
```

Both models still listed, both context limits still 32768, both services `active`, and SSH still working over LAN and Tailscale.

## What this run proved and did not prove

It proved that two teams each get their own Kubernetes API on one GPU host, that their workloads reach a shared host-managed model endpoint, and that one team's cluster can be destroyed and rebuilt without disturbing the other.

It did not prove hardware isolation between the teams. Both tenant clusters share one node, one GPU, and one kernel. Hard isolation needs private GPU nodes per tenant, and untrusted code needs vNode on top. Say that plainly in the article rather than letting the tenant-cluster boundary imply more than it delivers.

## Evidence to capture

Save raw output under `evidence/platform/` with a UTC-stamped filename:

- `vcluster list` after creation
- the namespace and node listing from inside each tenant cluster, which is the isolation evidence
- both Jobs' completion status and logs, from inside the tenant clusters
- the delete-and-recreate output, including the full tenant cluster rebuild
- the final model, service, and memory checks

Scrub the LAN address and the Tailscale address from anything destined for a public repository.
