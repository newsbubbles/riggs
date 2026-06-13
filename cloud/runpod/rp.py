"""rp.py — full RunPod GPU control from the CLI, for riggs auto-rigging.

Drives the whole lifecycle with only a RUNPOD_API_KEY (read from .env or env):
  gpus                 list GPU types + price
  up                   create a GPU pod (injects an SSH public key), wait, print ssh
  status <id>          show a pod's state + connection
  exec <id> -- <cmd>   run a command on the pod over SSH
  push/pull <id> ...   scp a file to/from the pod
  down <id>            terminate the pod
  rig                  one-shot: up -> provision engine -> rig a mesh -> pull FBX -> down

SSH uses a keypair under cloud/runpod/.ssh, passed to the pod via the PUBLIC_KEY
env var (RunPod base images authorize it on boot — no dashboard step). The pod
image must run an SSH daemon; RunPod's pytorch base images do.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import runpod

HERE = Path(__file__).resolve().parent
SSH_DIR = HERE / ".ssh"
KEY = SSH_DIR / "id_ed25519"
# RunPod base image with python3.11 + sshd + RunPod start script (overridable).
DEFAULT_IMAGE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"


def load_key():
    env = HERE.parent.parent / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        sys.exit("RUNPOD_API_KEY not set (put it in D:/riggs/.env)")
    runpod.api_key = key


def ensure_keypair() -> str:
    SSH_DIR.mkdir(parents=True, exist_ok=True)
    if not KEY.exists():
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(KEY), "-q"], check=True)
    return (KEY.with_suffix(".pub")).read_text().strip()


KNOWN_HOSTS = SSH_DIR / "known_hosts"  # under .ssh (gitignored); avoids the Windows "nul" trap


def _ssh_base(ip: str, port: int) -> list[str]:
    return ["ssh", "-i", str(KEY), "-p", str(port),
            "-o", "StrictHostKeyChecking=no", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
            "-o", "ConnectTimeout=15", f"root@{ip}"]


def pod_conn(pod: dict):
    """Return (ip, tcp_port_for_22) or (None, None) if not ready."""
    rt = pod.get("runtime") or {}
    for p in rt.get("ports") or []:
        if p.get("privatePort") == 22 and p.get("type") == "tcp" and p.get("isIpPublic"):
            return p.get("ip"), p.get("publicPort")
    return None, None


def wait_running(pod_id: str, timeout=600):
    deadline = time.time() + timeout
    while time.time() < deadline:
        pod = runpod.get_pod(pod_id)
        # SDK sometimes wraps in {"pod": {...}}
        pod = pod.get("pod", pod) if isinstance(pod, dict) else pod
        ip, port = pod_conn(pod or {})
        status = (pod or {}).get("desiredStatus")
        if ip and port:
            return pod, ip, port
        print(f"  waiting... status={status}")
        time.sleep(10)
    raise TimeoutError(f"pod {pod_id} not SSH-ready within {timeout}s")


# ---- commands ------------------------------------------------------------

def cmd_gpus(args):
    gpus = runpod.get_gpus()
    rows = []
    for g in gpus:
        gid = g.get("id")
        try:
            d = runpod.get_gpu(gid)
            price = d.get("lowestPrice", {}).get("minimumBidPrice") or d.get("securePrice")
        except Exception:
            price = None
        rows.append((price if price is not None else 9e9, gid, g.get("memoryInGb")))
    rows.sort()
    for price, gid, mem in rows:
        ps = f"${price}/hr" if price < 9e9 else "n/a"
        print(f"{ps:>10}  {mem:>4}GB  {gid}")


def cmd_up(args):
    pub = ensure_keypair()
    print(f"creating pod ({args.gpu}) from {args.image} ...")
    pod = runpod.create_pod(
        name=args.name, image_name=args.image, gpu_type_id=args.gpu,
        cloud_type=args.cloud, support_public_ip=True, start_ssh=True,
        gpu_count=1, container_disk_in_gb=args.disk, volume_in_gb=args.volume,
        ports="22/tcp", env={"PUBLIC_KEY": pub},
    )
    pid = pod["id"]
    print(f"pod id: {pid}  (terminate with: python rp.py down {pid})")
    _, ip, port = wait_running(pid)
    print(f"READY  ssh -i {KEY} -p {port} root@{ip}")
    return pid, ip, port


def cmd_status(args):
    pod = runpod.get_pod(args.pod_id)
    pod = pod.get("pod", pod) if isinstance(pod, dict) else pod
    ip, port = pod_conn(pod or {})
    print(f"status={pod.get('desiredStatus')}  cost/hr={pod.get('costPerHr')}")
    print(f"ssh: {'ready' if ip else 'not ready'}", f"root@{ip}:{port}" if ip else "")


def cmd_down(args):
    runpod.terminate_pod(args.pod_id)
    print(f"terminated {args.pod_id}")


def cmd_stop(args):
    runpod.stop_pod(args.pod_id)
    print(f"stopped {args.pod_id} (GPU billing halted; resume: python rp.py resume {args.pod_id})")


def cmd_resume(args):
    runpod.resume_pod(args.pod_id, 1)
    _, ip, port = wait_running(args.pod_id)
    print(f"READY  ssh -i {KEY} -p {port} root@{ip}")


def cmd_exec(args):
    pod = runpod.get_pod(args.pod_id)
    pod = pod.get("pod", pod) if isinstance(pod, dict) else pod
    ip, port = pod_conn(pod or {})
    if not ip:
        sys.exit("pod not SSH-ready")
    sys.exit(subprocess.run(_ssh_base(ip, port) + [" ".join(args.cmd)]).returncode)


def _scp(ip, port, src, dst):
    return subprocess.run([
        "scp", "-i", str(KEY), "-P", str(port),
        "-o", "StrictHostKeyChecking=no", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
        src, dst,
    ]).returncode


def cmd_push(args):
    pod = runpod.get_pod(args.pod_id); pod = pod.get("pod", pod)
    ip, port = pod_conn(pod or {})
    sys.exit(_scp(ip, port, args.local, f"root@{ip}:{args.remote}"))


def cmd_pull(args):
    pod = runpod.get_pod(args.pod_id); pod = pod.get("pod", pod)
    ip, port = pod_conn(pod or {})
    sys.exit(_scp(ip, port, f"root@{ip}:{args.remote}", args.local))


def cmd_rig(args):
    """Full one-shot rig on a fresh pod."""
    provision = HERE / f"provision_{args.engine}.sh"
    if not provision.is_file():
        sys.exit(f"no provision script for engine {args.engine}: {provision}")
    entry = HERE.parent / "riggs_entry.py"
    runner = HERE.parent / "engines" / args.engine / f"run_{args.engine}.py"

    pid, ip, port = cmd_up(args)
    try:
        ssh = _ssh_base(ip, port)
        print("uploading riggs code + provisioning (first run installs deps, ~10-15 min) ...")
        subprocess.run(ssh + ["mkdir -p /opt/riggs"], check=True)
        for f in (provision, entry, runner):
            if _scp(ip, port, str(f), f"root@{ip}:/opt/riggs/{f.name}"):
                sys.exit(f"failed to upload {f.name}")
        hf = os.environ.get("HF_TOKEN") or os.environ.get("HF_ACCESS_TOKEN") or ""
        rc = subprocess.run(ssh + [f"cd /opt/riggs && HF_TOKEN={hf} bash {provision.name}"]).returncode
        if rc != 0:
            sys.exit("provisioning failed (use --keep and ssh in to debug)")

        remote_in = f"/opt/riggs/input{Path(args.input).suffix}"
        if _scp(ip, port, args.input, f"root@{ip}:{remote_in}"):
            sys.exit("failed to upload mesh")
        print("rigging ...")
        rc = subprocess.run(ssh + [
            f"cd /opt/riggs && RIGGS_ENGINE={args.engine} python riggs_entry.py "
            f"rig --input {remote_in} --output /opt/riggs/rigged.fbx --opts '{args.opts}'"
        ]).returncode
        if rc != 0:
            sys.exit("rig command failed (use --keep and ssh in to debug)")
        if _scp(ip, port, f"root@{ip}:/opt/riggs/rigged.fbx", args.output):
            sys.exit("failed to download rigged FBX")
        print(f"DONE -> {args.output}")
    finally:
        if args.keep:
            print(f"--keep set; pod {pid} left running. Terminate: python rp.py down {pid}")
        else:
            runpod.terminate_pod(pid)
            print(f"terminated {pid}")


def main():
    load_key()
    ap = argparse.ArgumentParser(prog="rp")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("gpus").set_defaults(func=cmd_gpus)

    def add_pod_opts(p):
        p.add_argument("--gpu", default="NVIDIA GeForce RTX 3090")
        p.add_argument("--image", default=DEFAULT_IMAGE)
        p.add_argument("--cloud", default="ALL")
        p.add_argument("--disk", type=int, default=60)
        p.add_argument("--volume", type=int, default=0)
        p.add_argument("--name", default="riggs")

    p = sub.add_parser("up"); add_pod_opts(p); p.set_defaults(func=cmd_up)

    p = sub.add_parser("status"); p.add_argument("pod_id"); p.set_defaults(func=cmd_status)
    p = sub.add_parser("down"); p.add_argument("pod_id"); p.set_defaults(func=cmd_down)
    p = sub.add_parser("stop"); p.add_argument("pod_id"); p.set_defaults(func=cmd_stop)
    p = sub.add_parser("resume"); p.add_argument("pod_id"); p.set_defaults(func=cmd_resume)
    p = sub.add_parser("exec"); p.add_argument("pod_id"); p.add_argument("cmd", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_exec)
    p = sub.add_parser("push"); p.add_argument("pod_id"); p.add_argument("local"); p.add_argument("remote")
    p.set_defaults(func=cmd_push)
    p = sub.add_parser("pull"); p.add_argument("pod_id"); p.add_argument("remote"); p.add_argument("local")
    p.set_defaults(func=cmd_pull)

    p = sub.add_parser("rig"); add_pod_opts(p)
    p.add_argument("--engine", default="mia", choices=["mia", "unirig"])
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--opts", default="{}")
    p.add_argument("--keep", action="store_true", help="don't terminate the pod after")
    p.set_defaults(func=cmd_rig)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
