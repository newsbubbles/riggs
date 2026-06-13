#!/usr/bin/env bash
# Provision Make-It-Animatable on a stock RunPod pytorch (py3.11) pod.
# Idempotent: safe to re-run. Mirrors the MIA Dockerfile so no registry/build
# is needed — works with only a RunPod API key.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

echo ">> system deps"
apt-get update -qq
apt-get install -y --no-install-recommends \
    git git-lfs wget ca-certificates \
    libgl1 libglib2.0-0 libxrender1 libxi6 libxxf86vm1 libxfixes3 libsm6 \
    libxkbcommon0 libxext6 libdbus-1-3 libxrandr2 libxinerama1 libxcursor1 >/dev/null
git lfs install

cd /opt
if [ ! -d Make-It-Animatable ]; then
    echo ">> clone MIA"
    git clone --recursive --single-branch https://github.com/jasongzy/Make-It-Animatable.git
fi
cd Make-It-Animatable

echo ">> python deps (pins torch 2.1.2+cu121; downgrades base torch)"
export PIP_DEFAULT_TIMEOUT=300
pip install --retries 10 -r requirements.txt runpod

if [ ! -d output/best/new ]; then
    echo ">> model weights"
    GIT_LFS_SKIP_SMUDGE=1 git clone https://huggingface.co/jasongzy/Make-It-Animatable /tmp/hf
    git -C /tmp/hf lfs pull -I 'output/best/new'
    mkdir -p output/best && cp -r /tmp/hf/output/best/new output/best/
    git -C /tmp/hf lfs pull -I 'data' && cp -r /tmp/hf/data/* data/ 2>/dev/null || true
    rm -rf /tmp/hf
fi

# MIA loads data/Mixamo/bones.fbx at import time (the Mixamo skeleton template).
# That dataset is GATED, so an HF token is required (set HF_TOKEN; accept terms at
# https://huggingface.co/datasets/jasongzy/Mixamo). We fetch only the one file.
# MIA imports BOTH bones.fbx and bones_vroid.fbx at module load (the Mixamo
# skeleton templates). That dataset is GATED: set HF_TOKEN/HF_ACCESS_TOKEN and
# accept terms at https://huggingface.co/datasets/jasongzy/Mixamo. Use the stable
# python API (the huggingface-cli download syntax changed in hub 1.x).
HF_TOK="${HF_TOKEN:-${HF_ACCESS_TOKEN:-}}"
if [ ! -f data/Mixamo/bones.fbx ] || [ ! -f data/Mixamo/bones_vroid.fbx ]; then
    echo ">> Mixamo bone templates (gated, needs HF token)"
    if [ -z "$HF_TOK" ]; then
        echo "ERROR: HF token not set and bone templates missing — MIA cannot import."
        exit 3
    fi
    pip install -q -U huggingface_hub
    python - "$HF_TOK" <<'PY'
import sys
from huggingface_hub import hf_hub_download
tok = sys.argv[1]
for fn in ("bones.fbx", "bones_vroid.fbx"):
    p = hf_hub_download(repo_id="jasongzy/Mixamo", filename=fn, repo_type="dataset",
                        local_dir="data/Mixamo", token=tok)
    print("got", p)
PY
fi

if [ ! -f util/FBX2glTF ]; then
    echo ">> FBX2glTF"
    wget -q https://github.com/facebookincubator/FBX2glTF/releases/download/v0.9.7/FBX2glTF-linux-x64 -O util/FBX2glTF
    chmod +x util/FBX2glTF
fi

echo "PROVISION_OK"
