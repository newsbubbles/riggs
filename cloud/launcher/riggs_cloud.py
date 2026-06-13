"""riggs-cloud — rig a local mesh on a RunPod serverless endpoint.

The heavy GPU work runs in a riggs engine image (MIA or UniRig) deployed as a
RunPod serverless endpoint. This client base64-encodes the mesh, submits the
job, polls, and writes the rigged FBX back to disk. Pure stdlib.

Usage:
  set RUNPOD_API_KEY=...               (or pass --api-key)
  python riggs_cloud.py rig \
      --endpoint <ENDPOINT_ID> \
      --input  D:/riggs/out/Guard_base.glb \
      --output D:/riggs/out/Guard_mia.fbx \
      [--opts '{"rest_pose_type": "A-pose"}']

For meshes larger than ~8 MB, host the file and pass --mesh-url instead of
embedding it (RunPod payloads are size-limited).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.request

API = "https://api.runpod.ai/v2"


def _post(url: str, key: str, body: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def _get(url: str, key: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def rig(args):
    key = args.api_key or os.environ.get("RUNPOD_API_KEY")
    if not key:
        sys.exit("set RUNPOD_API_KEY or pass --api-key")

    job_input = {"opts": json.loads(args.opts)}
    if args.mesh_url:
        job_input["mesh_url"] = args.mesh_url
        job_input["filename"] = os.path.basename(args.mesh_url)
    else:
        with open(args.input, "rb") as f:
            job_input["mesh_b64"] = base64.b64encode(f.read()).decode()
        job_input["filename"] = os.path.basename(args.input)

    print(f"submitting job to endpoint {args.endpoint} ...")
    submit = _post(f"{API}/{args.endpoint}/run", key, {"input": job_input})
    job_id = submit.get("id")
    if not job_id:
        sys.exit(f"submit failed: {submit}")
    print(f"job {job_id} queued; polling...")

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        st = _get(f"{API}/{args.endpoint}/status/{job_id}", key)
        status = st.get("status")
        if status == "COMPLETED":
            out = st.get("output", {})
            if not out.get("ok") or not out.get("output_b64"):
                sys.exit(f"job completed but no rigged output: {json.dumps(out)[:1000]}")
            with open(args.output, "wb") as f:
                f.write(base64.b64decode(out["output_b64"]))
            secs = out.get("seconds")
            print(f"done in {secs}s -> {args.output} ({out.get('output_bytes')} bytes)")
            return
        if status in ("FAILED", "CANCELLED", "TIMED_OUT"):
            sys.exit(f"job {status}: {json.dumps(st)[:1000]}")
        print(f"  status={status} ...")
        time.sleep(args.poll)
    sys.exit("timed out waiting for job")


def main():
    ap = argparse.ArgumentParser(prog="riggs-cloud")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("rig", help="rig a mesh on a RunPod endpoint")
    p.add_argument("--endpoint", required=True, help="RunPod serverless endpoint id")
    p.add_argument("--input", help="local mesh (glb/fbx/obj)")
    p.add_argument("--mesh-url", help="public URL to the mesh (use for >8MB files)")
    p.add_argument("--output", required=True, help="where to write the rigged FBX")
    p.add_argument("--opts", default="{}", help="engine options as JSON")
    p.add_argument("--api-key", default=None)
    p.add_argument("--poll", type=float, default=5.0, help="poll interval seconds")
    p.add_argument("--timeout", type=float, default=1800.0)
    p.set_defaults(func=rig)

    args = ap.parse_args()
    if not getattr(args, "mesh_url", None) and not getattr(args, "input", None):
        sys.exit("provide --input or --mesh-url")
    args.func(args)


if __name__ == "__main__":
    main()
