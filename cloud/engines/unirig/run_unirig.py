"""Headless UniRig inference: mesh path -> rigged FBX path.

UniRig's inference is a chain of bash scripts:
  generate_skeleton.sh  (predict skeleton)            [checkpoint available now]
  generate_skin.sh      (predict skin weights)        [checkpoint "coming soon"]
  merge.sh              (merge skeleton/skin onto the original mesh)

Today only the skeleton model is released, so by default we produce a
skeleton-only FBX. When the skinning checkpoint ships, set opts['skin']=True
to run the full skeleton+skin+merge chain.

Runs inside the UniRig image where CWD is the repo root.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import traceback

_UNIRIG_DIR = os.environ.get("UNIRIG_DIR", "/opt/UniRig")


def _sh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=_UNIRIG_DIR, capture_output=True, text=True)


def rig(input_path: str, output_path: str, opts: dict | None = None) -> dict:
    opts = opts or {}
    want_skin = bool(opts.get("skin", False))
    seed = str(opts.get("seed", 12345))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            skel = os.path.join(tmp, "skeleton.fbx")
            logs = {}

            p = _sh(["bash", "launch/inference/generate_skeleton.sh",
                     "--input", input_path, "--output", skel, "--seed", seed])
            logs["skeleton"] = p.stdout[-2000:] + p.stderr[-2000:]
            if p.returncode != 0 or not os.path.isfile(skel):
                return {"ok": False, "error": "skeleton generation failed", "logs": logs}

            source = skel
            if want_skin:
                skin = os.path.join(tmp, "skin.fbx")
                p = _sh(["bash", "launch/inference/generate_skin.sh",
                         "--input", skel, "--output", skin])
                logs["skin"] = p.stdout[-2000:] + p.stderr[-2000:]
                if p.returncode != 0 or not os.path.isfile(skin):
                    return {"ok": False, "error": "skin generation failed "
                            "(the skinning checkpoint may not be released yet)", "logs": logs}
                source = skin

            p = _sh(["bash", "launch/inference/merge.sh",
                     "--source", source, "--target", input_path, "--output", output_path])
            logs["merge"] = p.stdout[-2000:] + p.stderr[-2000:]
            if p.returncode != 0 or not os.path.isfile(output_path):
                # merge may emit glb depending on target ext; try a copy fallback
                if os.path.isfile(source):
                    shutil.copyfile(source, output_path)
                else:
                    return {"ok": False, "error": "merge failed", "logs": logs}

            return {"ok": True, "output": output_path, "skinned": want_skin, "logs": logs}
    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}
