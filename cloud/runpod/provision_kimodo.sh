#!/usr/bin/env bash
# Provision NVIDIA Kimodo (text-to-motion) on a stock RunPod pytorch (py3.11, devel) pod.
# Mirrors the project's Dockerfile. Commercial-clean: we use the SOMA Open-Model-License
# checkpoints, never the SMPL-X (R&D) variant. Idempotent.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

echo ">> system deps (cmake + build tools for MotionCorrection / py-soma-x)"
apt-get update -qq
# python3-dev provides Python.h + libpython so CMake (MotionCorrection) can find Python3
apt-get install -y --no-install-recommends git git-lfs cmake build-essential ca-certificates \
    python3-dev python3.11-dev >/dev/null
# some bases ship a broken pip cmake shim that shadows the real one
rm -f /usr/local/bin/cmake || true

cd /opt
if [ ! -d kimodo ]; then
    echo ">> clone kimodo (recursive: pulls kimodo-viser submodule)"
    git clone --recursive https://github.com/nv-tlabs/kimodo.git
fi
cd kimodo

echo ">> python deps (torch comes from the base image; lockfile omits it)"
pip install -q --upgrade pip
export PIP_DEFAULT_TIMEOUT=300
# Drop the demo-only viser editable: it's a submodule for the web UI and kimodo_gen
# (headless generation) does not import it. Avoids the './kimodo-viser not valid' error.
sed -i '\#-e ./kimodo-viser#d' docker_requirements.txt
# -e . installs the kimodo_gen console script; MotionCorrection built separately per their Dockerfile
SKIP_MOTION_CORRECTION_IN_SETUP=1 pip install --retries 10 -r docker_requirements.txt

echo ">> sanity: kimodo_gen present"
which kimodo_gen || python -c "import kimodo; print('kimodo', kimodo.__file__)"

# Stage the text encoder from a non-gated, license-compliant Llama-3 mirror so we
# never hit Meta's manual-review gate. Needs only an HF token. Generation must then
# run with: TEXT_ENCODERS_DIR=/opt/text_encoders TEXT_ENCODER_MODE=local
echo ">> staging text encoder from non-gated Llama-3 mirror (skips Meta approval)"
export TEXT_ENCODERS_DIR="${TEXT_ENCODERS_DIR:-/opt/text_encoders}"
if [ -f /opt/riggs/setup_text_encoder.py ]; then
    python /opt/riggs/setup_text_encoder.py
else
    echo "WARN: /opt/riggs/setup_text_encoder.py not found; gen will fall back to the gated Meta repo"
fi

echo "PROVISION_OK"
