# Single-node vCluster Standalone Control Plane Cluster integration smoke test

> **Status:** Completed successfully on 2026-09-08 UTC. The curated command output is in [the end-to-end evidence record](../evidence/platform/20260908-standalone-e2e.md).

This runbook is the reproducible procedure for the completed test. The blocks labelled **Verified output** are excerpts captured on 2026-09-08. Every other command is an instruction or a health gate; do not treat illustrative or expected output as evidence from a new run.

The procedure installs one self-managed vCluster Standalone instance directly on the DGX Spark and joins the same machine as its only worker. The resulting machine can serve as a Control Plane Cluster, but this test does not create a tenant cluster. The Minima router and both vLLM backends remain host-managed throughout.

The test deliberately uses the pinned vCluster `v0.36.0` release and Kubernetes `v1.36.0`. It does not claim to use the latest available vCluster release.

## What runs where

- **Mac:** SSH, SCP, and independent access checks.
- **DGX Spark shell:** host checks, UFW rules, the Standalone installer, and `kubectl`.
- **Kubernetes:** two short-lived HTTP client Jobs in two namespaces.
- **Spark host:** the Minima router, both Minima vLLM backends, Docker, and the pre-existing containerd service.

The Jobs call the host router through the Kubernetes Node IP. They do not deploy or manage the models.

## Stage 0: protect access and start an evidence record

Do this only while the Mac is on the same LAN as the Spark. Open two LAN SSH sessions and keep both open:

```bash
ssh -o ServerAliveInterval=10 -o ServerAliveCountMax=6 saiyam@<SPARK_LAN_IP>
```

Open a third session through the Spark's Tailscale name or address and keep it open as a separate recovery path:

```bash
ssh -o ServerAliveInterval=10 -o ServerAliveCountMax=6 saiyam@<spark-tailscale-name-or-ip>
```

Run the installation only in the first LAN session. Use the other sessions for health checks. Never proceed when Tailscale is the only working route to the machine.

In the first LAN session, start a timestamped private transcript:

```bash
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
RUN_START=$(date -u '+%Y-%m-%d %H:%M:%S UTC')
EVIDENCE="$HOME/minima-vcluster-lab/$RUN_ID"
export RUN_ID RUN_START EVIDENCE
mkdir -p "$EVIDENCE"
script -q -a "$EVIDENCE/terminal.typescript"
```

Refresh sudo interactively. Do not put the password in a script, environment variable, transcript, or repository:

```bash
sudo -v
```

## Stage 1: record and gate the live baseline

Run these commands on the Spark:

```bash
date -u +%FT%TZ
hostname
uname -a
ip -brief address
ip route
```

Both access services must be active:

```bash
systemctl is-active ssh tailscaled
tailscale status
```

Record the router's model list and confirm that both exact model IDs are present:

```bash
curl --fail-with-body -sS http://127.0.0.1:8000/v1/models \
  | tee "$EVIDENCE/models-before.json" \
  | python3 -m json.tool
```

```bash
curl --fail-with-body -sS http://<SPARK_LAN_IP>:8000/v1/models \
  | python3 -m json.tool
```

The router must listen beyond loopback because the Pods call a Node IP:

```bash
sudo ss -ltnp '( sport = :8000 )'
```

Check the services through their owning account. The Minima units belong to `minima-setup`, not to the `saiyam` user manager:

```bash
sudo -u minima-setup env \
  XDG_RUNTIME_DIR=/run/user/1001 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus \
  systemctl --user is-active vllm-qwen vllm-gemma model-router
```

Record the shared runtime and Docker baseline. Docker already uses `/run/containerd/containerd.sock`, so it must survive the installation:

```bash
systemctl is-active containerd docker
systemctl show containerd -p FragmentPath -p ExecStart -p ActiveEnterTimestamp --no-pager
docker ps --no-trunc | tee "$EVIDENCE/docker-before.txt"
sudo sha256sum /etc/containerd/config.toml /etc/systemd/system/containerd.service \
  | tee "$EVIDENCE/containerd-before.sha256"
```

For a clean installation, vCluster and kubelet must not already be active:

```bash
systemctl is-active vcluster kubelet || true
test ! -e /var/lib/vcluster/kubeconfig.yaml
```

Record memory, swap, storage, and the watcher value:

```bash
free -h
swapon --show
df -h /
cat /proc/sys/fs/inotify/max_user_watches | tee "$EVIDENCE/inotify-before.txt"
cat /proc/sys/fs/inotify/max_user_instances
```

**Stop unless every gate passes:**

- fresh SSH connections work over both LAN and Tailscale;
- `ssh`, `tailscaled`, `containerd`, and Docker are active;
- the router returns `qwen3.6-27b` and `gemma4-31b-it` over loopback and the LAN address;
- port `8000` listens on `<SPARK_LAN_IP>` or `0.0.0.0`, not only on `127.0.0.1`;
- all three Minima user services are active;
- Docker's pre-existing containers are healthy;
- no previous vCluster or kubelet is active.

If an unexpected vCluster is present, capture `sudo systemctl status vcluster --no-pager` and stop. Do not reset an unknown installation.

## Stage 2: copy and review the pinned inputs

From a Mac terminal:

```bash
cd /Users/saiyam/git/myblogs/7-days-spark/minima-vcluster-platform-for-ai
scp manifests/vcluster-standalone.yaml saiyam@<SPARK_LAN_IP>:/tmp/vcluster.yaml
scp manifests/team-model-jobs.yaml saiyam@<SPARK_LAN_IP>:/tmp/team-model-jobs.yaml
```

Back on the Spark, inspect and hash exactly what will run:

```bash
sed -n '1,220p' /tmp/vcluster.yaml
sed -n '1,220p' /tmp/team-model-jobs.yaml
sha256sum /tmp/vcluster.yaml /tmp/team-model-jobs.yaml \
  | tee "$EVIDENCE/input-files.sha256"
```

Do not continue unless `vcluster.yaml` contains all of these safeguards:

- `advertiseAddress: <SPARK_LAN_IP>` for this multi-homed host;
- `joinNode.enabled: true` for the one-node lab;
- `joinNode.containerd.enabled: false` so vCluster does not replace the runtime shared with Docker;
- `preJoinCommands: [systemctl start containerd]` because the Standalone node-reset phase stops the existing runtime before the kubeadm join;
- `criSocket: unix:///run/containerd/containerd.sock`;
- kubelet `failSwapOn: false` with `memorySwap.swapBehavior: NoSwap` so host services retain swap but Pods cannot use it;
- Kubernetes image tag `v1.36.0`.

The `preJoinCommands` hook is not cosmetic. During the first attempt on 2026-09-08, the node-reset phase stopped the preserved runtime and kubeadm could not reach its CRI socket. Starting containerd immediately before the join fixed that failure without restarting either model.

## Stage 3: install the narrow host-network rules

The Spark has UFW enabled. The successful run required exactly three inbound rules. Each rule is limited to traffic arriving on `cni0`, sourced from the Pod CIDR, and addressed to the Spark's LAN IP:

```bash
sudo ufw status verbose | tee "$EVIDENCE/ufw-before.txt"
```

```bash
sudo ufw allow in on cni0 from 10.244.0.0/16 to <SPARK_LAN_IP> \
  port 8443 proto tcp comment 'vcluster pods to standalone api'
```

```bash
sudo ufw allow in on cni0 from 10.244.0.0/16 to <SPARK_LAN_IP> \
  port 8000 proto tcp comment 'vcluster pods to minima router'
```

```bash
sudo ufw allow in on cni0 from 10.244.0.0/16 to <SPARK_LAN_IP> \
  port 10250 proto tcp comment 'vcluster agent to kubelet'
```

```bash
sudo ufw status verbose | tee "$EVIDENCE/ufw-after.txt"
```

These rules do not expose the three ports on arbitrary interfaces or to arbitrary source networks. Do not replace them with broad `allow 8000`, `allow 8443`, or `allow 10250` rules.

Raise the watcher limit temporarily and verify it:

```bash
sudo sysctl fs.inotify.max_user_watches=524288
cat /proc/sys/fs/inotify/max_user_watches
```

Host swap remains enabled. Do not run `swapoff -a` while the two memory-heavy Minima backends are resident.

## Stage 4: install pinned vCluster Standalone v0.36.0

Download the pinned installer and ARM64 Standalone binary as files rather than piping a moving response directly to a root shell:

```bash
curl -fL --proto '=https' --tlsv1.2 \
  -o /tmp/install-standalone-v0.36.0.sh \
  https://github.com/loft-sh/vcluster/releases/download/v0.36.0/install-standalone.sh
```

```bash
curl -fL --proto '=https' --tlsv1.2 \
  -o /tmp/vcluster-linux-arm64-standalone-v0.36.0 \
  https://github.com/loft-sh/vcluster/releases/download/v0.36.0/vcluster-linux-arm64-standalone
```

Verify the immutable v0.36.0 release-asset digests:

```bash
echo 'a64283f42b30296e16912cb67b205b8d55eac77aada2680b6217f5a713da04a9  /tmp/install-standalone-v0.36.0.sh' \
  | sha256sum -c -
```

```bash
echo 'b3e8e3e2971a3bbfc6a7d43867a534b09d68338d9567533de73eef021c02ad1e  /tmp/vcluster-linux-arm64-standalone-v0.36.0' \
  | sha256sum -c -
```

Install the reviewed configuration:

```bash
sudo install -d -m 0755 /etc/vcluster
sudo install -m 0644 /tmp/vcluster.yaml /etc/vcluster/vcluster.yaml
chmod 0755 /tmp/install-standalone-v0.36.0.sh \
  /tmp/vcluster-linux-arm64-standalone-v0.36.0
```

Run the verified installer in the first LAN session and capture its exit code:

```bash
set -o pipefail
sudo /bin/sh /tmp/install-standalone-v0.36.0.sh \
  --vcluster-name spark-ai \
  --config /etc/vcluster/vcluster.yaml \
  --binary /tmp/vcluster-linux-arm64-standalone-v0.36.0 \
  --skip-download 2>&1 | tee "$EVIDENCE/install.log"
INSTALL_RC=${PIPESTATUS[0]}
echo "INSTALL_RC=$INSTALL_RC"
```

Stop if `INSTALL_RC` is not `0`. Keep every SSH session open and follow the failure-capture section below.

The joined control-plane node is appropriate for this smoke test, but it shares the machine with control-plane processes and credentials. A production design uses dedicated workers.

## Stage 5: recheck every protected host service

Before running any Kubernetes workload:

```bash
systemctl is-active ssh tailscaled vcluster kubelet containerd docker
```

```bash
sudo -u minima-setup env \
  XDG_RUNTIME_DIR=/run/user/1001 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus \
  systemctl --user is-active vllm-qwen vllm-gemma model-router
```

```bash
curl --fail-with-body -sS http://127.0.0.1:8000/v1/models \
  | tee "$EVIDENCE/models-after-install.json" \
  | python3 -m json.tool
docker ps --no-trunc | tee "$EVIDENCE/docker-after-install.txt"
```

Open one new LAN SSH connection and one new Tailscale SSH connection from the Mac. Stop if either route fails, a model disappears, or Docker loses its pre-existing container.

## Stage 6: verify the single-node cluster

Wait for the actual node, then capture the cluster state:

```bash
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml \
  wait --for=condition=Ready node --all --timeout=5m
```

```bash
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml version -o yaml \
  | tee "$EVIDENCE/kubectl-version.yaml"
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml get nodes -o wide \
  | tee "$EVIDENCE/nodes.txt"
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml get pods -A -o wide \
  | tee "$EVIDENCE/pods-before-jobs.txt"
```

Verify that the Node reports the address the clients will use:

```bash
NODE_IP=$(sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml \
  get node -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
echo "NODE_IP=$NODE_IP"
curl --fail-with-body -sS "http://${NODE_IP}:8000/v1/models" \
  | tee "$EVIDENCE/models-via-node-ip.json" \
  | python3 -m json.tool
```

For this Spark, `NODE_IP` must be `<SPARK_LAN_IP>`. Stop if the node is not `Ready`, the router is unreachable through that IP, or required system Pods are Pending or crashing.

**Verified output from 2026-09-08:**

```text
NAME         STATUS   ROLES                  VERSION   INTERNAL-IP      CONTAINER-RUNTIME
spark-5385   Ready    control-plane,master   v1.36.0   <SPARK_LAN_IP>   containerd://2.2.1
```

The captured healthy system workloads were Flannel, CoreDNS, Konnectivity Agent, kube-proxy, and Local Path Provisioner. Their generated Pod suffixes can change on a new run; do not copy the old names into new evidence.

## Stage 7: run and recreate the two client Jobs

The pinned `curlimages/curl:8.12.1` image declares a named user. Kubernetes cannot use a name from the image to enforce `runAsNonRoot`, so the reviewed manifest supplies the image's verified numeric identity: UID `101` and GID `102`. Both Pods also set `automountServiceAccountToken: false` because they do not call the Kubernetes API.

Start from a clean client state, then apply both Jobs:

```bash
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml \
  delete -f /tmp/team-model-jobs.yaml --ignore-not-found --wait=true
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml \
  apply -f /tmp/team-model-jobs.yaml
```

The Jobs start together. Wait for each completion:

```bash
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml \
  -n team-qwen wait --for=condition=complete job/ask-qwen --timeout=300s
```

```bash
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml \
  -n team-gemma wait --for=condition=complete job/ask-gemma --timeout=300s
```

Capture the raw API responses, not a hand-written approximation:

```bash
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml \
  -n team-qwen logs job/ask-qwen | tee "$EVIDENCE/qwen-job.json"
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml \
  -n team-gemma logs job/ask-gemma | tee "$EVIDENCE/gemma-job.json"
```

```bash
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml get jobs,pods -A -o wide \
  | tee "$EVIDENCE/jobs-pods-final.txt"
```

If a wait fails, capture `get pods -A -o wide`, `describe pod`, logs, and events before changing or deleting anything.

**Verified parsed output from the delete-and-recreate run on 2026-09-08:**

```text
qwen3.6-27b hello from team-qwen {'prompt_tokens': 21, 'total_tokens': 27, 'completion_tokens': 6, 'prompt_tokens_details': None}
gemma4-31b-it hello from team-gemma {'prompt_tokens': 23, 'total_tokens': 30, 'completion_tokens': 7, 'prompt_tokens_details': None}
```

These Jobs prove Kubernetes scheduling, Pod-to-host network reachability, and reproducible client definitions. They do not prove model lifecycle inside Kubernetes, vCluster performance overhead, GPU scheduling, capacity isolation, NetworkPolicy, application authorization, or tenant isolation.

## Stage 8: capture final coexistence evidence

```bash
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml get events -A \
  --sort-by=.lastTimestamp | tee "$EVIDENCE/events-final.txt"
sudo journalctl -u vcluster.service --since "$RUN_START" --no-pager \
  > "$EVIDENCE/vcluster-journal.txt"
```

```bash
curl --fail-with-body -sS http://127.0.0.1:8000/v1/models \
  | tee "$EVIDENCE/models-final.json" \
  | python3 -m json.tool
systemctl is-active ssh tailscaled vcluster kubelet containerd docker \
  | tee "$EVIDENCE/system-services-final.txt"
```

```bash
sudo -u minima-setup env \
  XDG_RUNTIME_DIR=/run/user/1001 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus \
  systemctl --user is-active vllm-qwen vllm-gemma model-router \
  | tee "$EVIDENCE/minima-services-final.txt"
docker ps --no-trunc | tee "$EVIDENCE/docker-final.txt"
free -h | tee "$EVIDENCE/memory-final.txt"
```

Open fresh SSH connections over LAN and Tailscale one final time. On 2026-09-08, all six system services above and all three Minima services remained active, both models remained listed, and Docker's pre-existing model-runner container remained up.

Leave the transcript shell with:

```bash
exit
```

Keep the full transcript private because it can contain host and network details. The redacted, publishable record is [`evidence/platform/20260908-standalone-e2e.md`](../evidence/platform/20260908-standalone-e2e.md).

## Workload cleanup

To remove only the disposable client layer while retaining the Standalone cluster:

```bash
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml \
  delete -f /tmp/team-model-jobs.yaml --ignore-not-found --wait=true
```

This removes both Jobs and their two namespaces. It does not touch Minima, Docker, Tailscale, containerd, or the Standalone control plane.

## Failure capture and controlled rollback

If installation or node join fails, keep the surviving LAN and Tailscale sessions open and capture evidence before cleanup:

```bash
sudo systemctl status vcluster kubelet containerd docker --no-pager
sudo journalctl -u vcluster.service --since "$RUN_START" --no-pager
sudo kubectl --kubeconfig=/var/lib/vcluster/kubeconfig.yaml get nodes,pods -A -o wide || true
curl --fail-with-body -sS http://127.0.0.1:8000/v1/models | python3 -m json.tool
```

If access and Minima remain healthy but vCluster is repeatedly changing the host, stop only vCluster while investigating:

```bash
sudo systemctl stop vcluster.service
```

Do not stop containerd: Docker uses the same service and socket.

Use the full Standalone reset only after explicitly deciding to retire this lab cluster. The official reset removes vCluster and Kubernetes state, including `/var/lib/vcluster`, `/etc/kubernetes`, `/var/lib/kubelet`, and `/var/lib/etcd`:

```bash
sudo /bin/sh /tmp/install-standalone-v0.36.0.sh --reset-only
sudo systemctl stop kubelet.service || true
sudo systemctl disable kubelet.service || true
```

After a full reset, remove only the three lab-specific UFW rules:

```bash
sudo ufw delete allow in on cni0 from 10.244.0.0/16 to <SPARK_LAN_IP> port 8443 proto tcp
sudo ufw delete allow in on cni0 from 10.244.0.0/16 to <SPARK_LAN_IP> port 8000 proto tcp
sudo ufw delete allow in on cni0 from 10.244.0.0/16 to <SPARK_LAN_IP> port 10250 proto tcp
sudo ufw status verbose
```

Restore the watcher count to the value captured before the run:

```bash
WATCHERS_BEFORE=$(cat "$EVIDENCE/inotify-before.txt")
sudo sysctl "fs.inotify.max_user_watches=${WATCHERS_BEFORE}"
```

Then verify the protected services again:

```bash
systemctl is-active ssh tailscaled containerd docker
sudo -u minima-setup env \
  XDG_RUNTIME_DIR=/run/user/1001 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus \
  systemctl --user is-active vllm-qwen vllm-gemma model-router
curl --fail-with-body -sS http://127.0.0.1:8000/v1/models | python3 -m json.tool
```

The reset script does not restore the old containerd configuration, UFW rules, CNI directories, or every host setting. Do not flush iptables, restore an entire saved firewall ruleset, delete `/etc/containerd`, delete pre-existing CNI directories, stop Docker, stop Tailscale, or reboot as an improvised cleanup. Coordinate any reboot with Minima first.

## Publication boundary

- Do not publish kubeconfigs, full transcripts, Tailscale details, credentials, model paths, or private logs.
- Do not describe the two namespaces as customers or tenant clusters.
- Do not claim vCluster Platform or vMetal was installed.
- Do not claim the models ran inside Kubernetes; only the HTTP clients did.
- Link every published output to the curated evidence record rather than inventing expected output.
