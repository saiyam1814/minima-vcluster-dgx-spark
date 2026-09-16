# Two tenant clusters on the DGX Spark, one per team

Run date: 2026-09-16 UTC
Host: `spark-5385` (`aarch64`, Ubuntu 24.04.4 LTS)
vCluster CLI on the Spark: `0.36.0`
Scope: the vCluster Standalone instance installed on 8 September is used as the **control plane cluster**. Two tenant clusters, `team-qwen` and `team-gemma`, are deployed into it. Each team's workload runs inside its own tenant cluster and calls the host-managed Minima router. This replaces the namespace-per-team shape from the 8 September run.

## Starting state

The 8 September environment was still intact after 7d23h:

```text
NAME         STATUS   ROLES                  AGE     VERSION   INTERNAL-IP      CONTAINER-RUNTIME
spark-5385   Ready    control-plane,master   7d23h   v1.36.0   <SPARK_LAN_IP>   containerd://2.2.1
```

Both models were live behind the router, and the default StorageClass `local-path` was available. Host memory before the run: 18 GiB available of 121 GiB, with the two models resident.

The old namespace-shaped run was deleted first:

```text
namespace "team-qwen" deleted
namespace "team-gemma" deleted
```

## Creating the two tenant clusters

```bash
export KUBECONFIG=/var/lib/vcluster/kubeconfig.yaml
vcluster create team-qwen  --namespace team-qwen  --add=false --connect=false
vcluster create team-gemma --namespace team-gemma --add=false --connect=false
```

Wall time for the CLI call: 14.0 s for the first (includes a one-time Helm download), 2.7 s for the second. Both control planes reached `Ready` within roughly 55 seconds of the first command.

```text
   NAME     | NAMESPACE  | STATUS  | VERSION | AGE
------------+------------+---------+---------+------
 team-gemma | team-gemma | Running | 0.36.0  | 52s
 team-qwen  | team-qwen  | Running | 0.36.0  | 55s
```

Host memory after both control planes were running: 17 GiB available, so the pair cost roughly 1 GiB.

## Isolation evidence

This is the result the namespace run could not produce. From inside `team-qwen`:

```text
$ vcluster connect team-qwen --namespace team-qwen -- kubectl get ns
NAME              STATUS   AGE
default           Active   34s
kube-node-lease   Active   34s
kube-public       Active   34s
kube-system        Active   34s
```

From inside `team-gemma`, the identical four namespaces. Neither team can see the other's namespace, and neither sees `kube-flannel` or `local-path-storage` from the control plane cluster.

Each tenant cluster presents its own node object, with its own internal address:

```text
team-qwen  : spark-5385  Ready  v1.36.0  10.104.23.9    Fake Kubernetes Image
team-gemma : spark-5385  Ready  v1.36.0  10.97.29.108   Fake Kubernetes Image
```

## Host endpoint reachability probe

The synthetic node above raised the question of whether `status.hostIP` still resolves to the real machine inside a tenant cluster. A probe Job in `team-qwen` answered it:

```text
status.hostIP = <SPARK_LAN_IP>
--- try hostIP ---
hostIP http=200
--- try real LAN ip ---
lan http=200
```

`status.hostIP` returns the Spark's real LAN address, not the synthetic node address, because pod status is synced back from the real pod on the control plane cluster. The team workload manifests therefore needed no change when moving from a namespace to a tenant cluster.

## Both teams' workloads

Applied inside each tenant cluster, with no namespace field in either manifest:

```text
team-qwen  : ask-qwen    Complete   1/1   3s
team-gemma : ask-gemma   Complete   1/1   3s
```

Parsed responses, read from inside each team's own cluster:

```text
qwen3.6-27b   'hello from team-qwen'    prompt=21 completion=6 total=27
gemma4-31b-it 'hello from team-gemma'   prompt=23 completion=7 total=30
```

On the control plane cluster the same objects appear under vCluster's name translation, all scheduled on the single Spark node, each tenant with its own CoreDNS:

```text
NAMESPACE    NAME                                                 STATUS      IP             NODE
team-gemma   ask-gemma-ljbrx-x-default-x-team-gemma               Completed   10.244.0.117   spark-5385
team-gemma   coredns-df8c87f55-lr22n-x-kube-system-x-team-gemma   Running     10.244.0.114   spark-5385
team-gemma   team-gemma-0                                         Running     10.244.0.112   spark-5385
team-qwen    ask-qwen-sn7wh-x-default-x-team-qwen                 Completed   10.244.0.116   spark-5385
team-qwen    coredns-df8c87f55-n67jt-x-kube-system-x-team-qwen    Running     10.244.0.113   spark-5385
team-qwen    team-qwen-0                                          Running     10.244.0.111   spark-5385
```

## Destroy and rebuild one team, leave the other running

```bash
vcluster delete team-qwen --namespace team-qwen
```

Completed in 23.7 s. Immediately afterwards:

```text
   NAME     | NAMESPACE  | STATUS  | VERSION | AGE
------------+------------+---------+---------+--------
 team-gemma | team-gemma | Running | 0.36.0  | 3m47s

$ vcluster connect team-gemma ... -- kubectl get jobs
NAME        STATUS     COMPLETIONS   DURATION   AGE
ask-gemma   Complete   1/1           3s         71s
```

`team-gemma` was unaffected. Recreating `team-qwen` took 3.1 s for the CLI call, and the same workload file produced the same answer:

```text
ask-qwen   Complete   1/1   3s
qwen3.6-27b 'hello from team-qwen'   prompt=21 completion=6 total=27
```

## Final coexistence checks

```text
gemma4-31b-it max_model_len=32768
qwen3.6-27b   max_model_len=32768

live completion through the router: "Qwen on Spark is ready"

ssh active | tailscaled active | vcluster active | kubelet active | containerd active | docker active
docker-model-runner  Up 17 hours
```

The Minima model processes run under the `minima-setup` user manager, so `systemctl --user` as another user reports them inactive; their liveness is confirmed by the API responses and by the running `VLLM::EngineCore` processes owned by `minima-setup`.

Host memory at the end: 16 GiB available of 121 GiB.

## Claim boundary

This run proves that two teams each get their own Kubernetes API on one GPU host, that workloads inside those tenant clusters reach a shared host-managed model endpoint, and that one team's entire cluster can be destroyed and rebuilt in under half a minute without disturbing the other team or the models.

It does not prove hardware isolation between the teams. Both tenant clusters share one node, one GPU, and one kernel. Per-tenant hardware isolation needs private GPU nodes, and untrusted tenant code needs vNode on top. No GPU scheduling was exercised, vCluster Platform was not installed, and vMetal did not provision the Spark.
