"""riggs cloud entrypoint — engine-agnostic, baked into every engine image.

Two modes:
  oneshot:  python riggs_entry.py rig --input in.glb --output out.fbx [--opts '{}']
            reads/writes local (mounted) paths. Used for local Docker tests and
            on-demand pods.
  serve:    python riggs_entry.py serve
            starts a RunPod serverless handler. Input mesh arrives base64 (small
            assets) or as a URL; the rigged FBX is returned base64 (or uploaded).

The engine is chosen by the RIGGS_ENGINE env var ('mia' or 'unirig'), set in the
image. Each image bundles exactly one engine, so the import below resolves to the
one installed.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
import time
import urllib.request


def _load_engine():
    engine = os.environ.get("RIGGS_ENGINE", "").lower()
    if engine == "mia":
        import run_mia as impl
    elif engine == "unirig":
        import run_unirig as impl
    else:
        raise RuntimeError(f"RIGGS_ENGINE must be 'mia' or 'unirig', got {engine!r}")
    return engine, impl


def run_oneshot(input_path: str, output_path: str, opts: dict) -> dict:
    engine, impl = _load_engine()
    t0 = time.time()
    result = impl.rig(input_path, output_path, opts)
    result.setdefault("engine", engine)
    result["seconds"] = round(time.time() - t0, 2)
    return result


# ---- serverless ----------------------------------------------------------

def _fetch_input(job_input: dict, workdir: str) -> str:
    fname = job_input.get("filename", "input.glb")
    dst = os.path.join(workdir, fname)
    if job_input.get("mesh_url"):
        urllib.request.urlretrieve(job_input["mesh_url"], dst)
    elif job_input.get("mesh_b64"):
        with open(dst, "wb") as f:
            f.write(base64.b64decode(job_input["mesh_b64"]))
    else:
        raise ValueError("job input needs 'mesh_url' or 'mesh_b64'")
    return dst


def _handler(job):
    job_input = job.get("input", {})
    opts = job_input.get("opts", {}) or {}
    with tempfile.TemporaryDirectory() as workdir:
        in_path = _fetch_input(job_input, workdir)
        out_path = os.path.join(workdir, "rigged.fbx")
        result = run_oneshot(in_path, out_path, opts)
        if not result.get("ok") or not os.path.isfile(out_path):
            return {"error": result.get("error", "rig failed"), "detail": result}
        with open(out_path, "rb") as f:
            data = f.read()
        result["output_b64"] = base64.b64encode(data).decode()
        result["output_filename"] = "rigged.fbx"
        result["output_bytes"] = len(data)
    return result


def serve():
    import runpod  # provided by the image

    runpod.serverless.start({"handler": _handler})


def main():
    ap = argparse.ArgumentParser(prog="riggs_entry")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("rig", help="one-shot rig of a local file")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--opts", default="{}")

    sub.add_parser("serve", help="start RunPod serverless handler")

    args = ap.parse_args()
    if args.cmd == "serve":
        serve()
        return
    result = run_oneshot(args.input, args.output, json.loads(args.opts))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
