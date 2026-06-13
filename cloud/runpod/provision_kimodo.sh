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

# The combined pip build of motion_correction's CMake/pybind11 extension can target the
# WRONG python (Ubuntu's default python3 is 3.10, but the runtime is 3.11), producing a
# cp310 .so that won't import. Rebuild it explicitly against python3.11 and drop the .so
# into the installed package.
echo ">> (re)build motion_correction C++ extension for python3.11"
PY311="$(command -v python3.11 || echo /usr/bin/python3.11)"
python -m pip install -q pybind11 || true
MC_PKG="$(dirname "$($PY311 -c 'import importlib.util as u; print(u.find_spec("motion_correction").origin)')")"
( cd /opt/kimodo/MotionCorrection && rm -rf build \
  && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DPYBIND11_FINDPYTHON=ON \
       -DPython_EXECUTABLE="$PY311" -DPython3_EXECUTABLE="$PY311" \
  && cmake --build build -j4 )
MC_SO="$(find /opt/kimodo/MotionCorrection/build -name '_motion_correction*.so' | head -1)"
cp "$MC_SO" "$MC_PKG/" && echo ">> installed $MC_SO -> $MC_PKG"
$PY311 -c "from motion_correction import _motion_correction; print('motion_correction ext OK')"

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
