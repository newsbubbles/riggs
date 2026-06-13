# Make-It-Animatable rigging image.
# Runs on any CUDA GPU including Pascal (GTX 1080) -> testable locally via
# Docker Desktop WSL2 GPU passthrough before spending a cent on cloud.
#
# Build:
#   docker build -t ghcr.io/<you>/riggs-mia:latest -f cloud/engines/mia/Dockerfile .
# Local test on your own GPU:
#   docker run --gpus all -v "D:/riggs/out:/work" ghcr.io/<you>/riggs-mia:latest \
#       rig --input /work/Guard_base.glb --output /work/Guard_mia.fbx
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    RIGGS_ENGINE=mia \
    MIA_DIR=/opt/Make-It-Animatable

# system + python 3.11 + libs bpy/trimesh/open3d need even when headless
RUN apt-get update && apt-get install -y --no-install-recommends \
        git git-lfs wget ca-certificates \
        python3.11 python3.11-dev python3-pip \
        libgl1 libglib2.0-0 libxrender1 libxi6 libxxf86vm1 libxfixes3 libsm6 \
        libxkbcommon0 libxext6 libdbus-1-3 libxrandr2 libxinerama1 libxcursor1 \
    && rm -rf /var/lib/apt/lists/* \
    && git lfs install \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && python -m pip install --upgrade pip

WORKDIR /opt
RUN git clone --recursive --single-branch https://github.com/jasongzy/Make-It-Animatable.git
WORKDIR /opt/Make-It-Animatable

# python deps (torch 2.1.2+cu121 etc. — all prebuilt wheels, no compilation)
RUN python -m pip install -r requirements.txt \
    && python -m pip install runpod

# model weights + minimal Mixamo data + FBX2glTF (per MIA README)
RUN GIT_LFS_SKIP_SMUDGE=1 git clone https://huggingface.co/jasongzy/Make-It-Animatable /tmp/hf \
    && git -C /tmp/hf lfs pull -I 'output/best/new' \
    && mkdir -p output/best && cp -r /tmp/hf/output/best/new output/best/ \
    && git -C /tmp/hf lfs pull -I 'data' && cp -r /tmp/hf/data/* data/ 2>/dev/null || true \
    && GIT_LFS_SKIP_SMUDGE=1 git -C data clone https://huggingface.co/datasets/jasongzy/Mixamo \
    && git -C data/Mixamo lfs pull -I 'bones*.fbx,animation' \
    && rm -rf /tmp/hf \
    && wget -q https://github.com/facebookincubator/FBX2glTF/releases/download/v0.9.7/FBX2glTF-linux-x64 -O util/FBX2glTF \
    && chmod +x util/FBX2glTF

# riggs entrypoint + engine wrapper
COPY cloud/riggs_entry.py /opt/riggs/riggs_entry.py
COPY cloud/engines/mia/run_mia.py /opt/riggs/run_mia.py
ENV PYTHONPATH=/opt/riggs:/opt/Make-It-Animatable

WORKDIR /opt/riggs
ENTRYPOINT ["python", "riggs_entry.py"]
CMD ["serve"]
