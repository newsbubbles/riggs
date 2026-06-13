# UniRig rigging image (MIT code + MIT weights).
# Needs an sm_75+ GPU (flash_attn) -> cloud only, not the local Pascal 1080.
# Uses a -devel CUDA base so nvcc can build flash_attn + spconv.
#
# Build (needs a CUDA-capable builder or buildx with the right base):
#   docker build -t ghcr.io/<you>/riggs-unirig:latest -f cloud/engines/unirig/Dockerfile .
#
# NOTE: UniRig's skinning checkpoint is "coming soon"; today this yields a
# skeleton-only rig. Pass opts {"skin": true} once the checkpoint releases.
FROM nvidia/cuda:12.1.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    RIGGS_ENGINE=unirig \
    UNIRIG_DIR=/opt/UniRig \
    TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9;9.0"

RUN apt-get update && apt-get install -y --no-install-recommends \
        git git-lfs wget ca-certificates build-essential ninja-build \
        python3.11 python3.11-dev python3-pip \
        libgl1 libglib2.0-0 libxrender1 libxi6 libxxf86vm1 libxfixes3 libsm6 \
    && rm -rf /var/lib/apt/lists/* \
    && git lfs install \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && python -m pip install --upgrade pip

WORKDIR /opt
RUN git clone https://github.com/VAST-AI-Research/UniRig.git
WORKDIR /opt/UniRig

# torch first, then UniRig deps. spconv + pyg ops + flash_attn (compiled here).
RUN python -m pip install torch==2.4.0 torchvision --index-url https://download.pytorch.org/whl/cu121 \
    && python -m pip install -r requirements.txt \
    && python -m pip install spconv-cu121 \
    && python -m pip install torch_scatter torch_cluster -f https://data.pyg.org/whl/torch-2.4.0+cu121.html --no-cache-dir \
    && python -m pip install numpy==1.26.4 runpod

# model weights (skeleton model; skinning model not yet released)
RUN GIT_LFS_SKIP_SMUDGE=1 git clone https://huggingface.co/VAST-AI/UniRig /tmp/hf \
    && git -C /tmp/hf lfs pull \
    && mkdir -p checkpoints && cp -r /tmp/hf/* checkpoints/ 2>/dev/null || true \
    && rm -rf /tmp/hf

COPY cloud/riggs_entry.py /opt/riggs/riggs_entry.py
COPY cloud/engines/unirig/run_unirig.py /opt/riggs/run_unirig.py
ENV PYTHONPATH=/opt/riggs:/opt/UniRig

WORKDIR /opt/riggs
ENTRYPOINT ["python", "riggs_entry.py"]
CMD ["serve"]
