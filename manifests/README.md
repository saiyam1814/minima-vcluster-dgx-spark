# Lab manifests

The Standalone and namespace-Job files were applied successfully to the DGX Spark on 2026-09-08 UTC. The resulting environment was one vCluster Standalone instance with the Spark joined as its only node. See the [curated end-to-end evidence](../evidence/platform/20260908-standalone-e2e.md) for captured output.

## `vcluster-standalone.yaml`

The configuration is specific to the tested Spark host:

- pins vCluster's Kubernetes distribution to `v1.36.0` for the pinned vCluster `v0.36.0` run;
- advertises the Spark's LAN address because the host is multi-homed with LAN and Tailscale;
- joins the Standalone control-plane host as the single development worker;
- disables vCluster containerd management and selects `/run/containerd/containerd.sock`, preserving the runtime already shared with Docker;
- starts that preserved containerd in `preJoinCommands` because the Standalone node-reset phase stops it before kubeadm joins the node;
- keeps host swap available to the memory-heavy Minima services while configuring Kubernetes Pods with `NoSwap`.

The joined control-plane node is acceptable for this smoke test. It is not the production topology recommended for untrusted tenant workloads.

## `team-model-jobs.yaml`

The workload manifest creates two namespaces and two short-lived HTTP client Jobs. Each Job:

- discovers the Spark Node IP through the downward API;
- calls the host-managed Minima router on port `8000`;
- disables Kubernetes API token mounting;
- drops Linux capabilities and disallows privilege escalation;
- runs `curlimages/curl:8.12.1` as its verified numeric UID `101` and GID `102`, allowing Kubernetes to enforce `runAsNonRoot` on the ARM64 Spark.

The Minima router and both vLLM backends remain outside Kubernetes. The Jobs demonstrate scheduling, Pod-to-host connectivity, and delete-and-recreate reproducibility; the namespaces are not tenant clusters or customer isolation boundaries.

## Required host rules

UFW blocked Pod-to-host traffic during the first run. The final working setup used three interface-, source-, destination-, port-, and protocol-scoped rules for traffic from `10.244.0.0/16` on `cni0` to `<SPARK_LAN_IP>`:

- `8443/tcp` for the Standalone API;
- `8000/tcp` for the Minima router;
- `10250/tcp` for Konnectivity-to-kubelet log access.

These host rules are intentionally not represented by Kubernetes YAML. Apply the exact commands in the [single-node runbook](../runbooks/04-single-node-standalone-demo.md), and do not replace them with broad port allowances.

## Scope

This phase does not create a tenant cluster, attach a separate private worker, install vCluster Platform, exercise GPU scheduling, or use vMetal. Follow the runbook's access gates and rollback guidance before repeating the installation on an in-use model host.

## `team-qwen-workload.yaml` and `team-gemma-workload.yaml`

**Not yet run.** These replace `team-model-jobs.yaml` for the tenant-cluster shape in [runbook 05](../runbooks/05-two-tenant-clusters-demo.md). Each file is applied *inside* that team's own tenant cluster and therefore carries no namespace. The security context and host-IP discovery are unchanged from the tested Jobs; only the boundary around them changes, from a namespace to a cluster.

`team-model-jobs.yaml` stays in the folder as the record of what was actually run on 8 September. Do not use it as the shape for the article.

## Private addresses

`vcluster-standalone.yaml` and this file both contain the Spark's LAN address. Scrub it before any of this is pushed to a public repository.
