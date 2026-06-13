# riggs cloud — auto-rig on any cloud GPU

Run the ML auto-riggers in Docker on a rented GPU (RunPod, Vast, Lambda, or your
own box), driven by one CLI command. This sidesteps the local blockers: no need
for a modern local GPU, and the container is Linux so headless Blender, bpy, and
flash_attn all just work. Anyone with a few dollars of cloud credit can rig a
mesh.

## Engines

| Engine | Code | Weights | Skeleton | Skin weights | GPU | Commercial use |
|--------|------|---------|----------|--------------|-----|----------------|
| **MIA** (Make-It-Animatable) | MIT | **Apache-2.0** | yes (Mixamo) | **yes** | any CUDA incl. Pascal/1080 | OK (output is yours) |
| **UniRig** | MIT | MIT | yes | *not yet released* | sm_75+ (flash_attn) | OK |

Notes:
- **MIA is the complete, commercially-usable rigger today** (skeleton + skin,
  Apache-2.0 weights). It runs even on the local 1080, so we test it locally
  before paying for cloud.
- **UniRig** is all-MIT but its skinning checkpoint is still "coming soon", so
  right now it yields a skeleton-only rig. It needs an sm_75+ GPU to build/run
  flash_attn, hence cloud-only.
- MIA's pipeline uses a GPLv3 Auto-Rig-Pro fork internally. We never vendor it
  into riggs core; it's pulled inside the engine image only. The rig it produces
  is yours under ARP's own terms.

## Layout
```
cloud/
  riggs_entry.py            engine-agnostic entrypoint (oneshot | serve)
  engines/
    mia/    Dockerfile + run_mia.py
    unirig/ Dockerfile + run_unirig.py
  launcher/
    riggs_cloud.py          local CLI -> RunPod serverless endpoint
```
The same image works two ways: a one-shot `rig` command (local Docker / on-demand
pod) and a RunPod serverless `serve` handler. Both call the same engine wrapper.

## Step 1 — build (from the repo root, D:/riggs)
Docker Desktop must be running.
```
docker build -t ghcr.io/<you>/riggs-mia:latest    -f cloud/engines/mia/Dockerfile .
docker build -t ghcr.io/<you>/riggs-unirig:latest -f cloud/engines/unirig/Dockerfile .
```
The build bakes the model weights into the image (no cold-start download).

## Step 2 — test MIA locally on your own GPU (free)
Docker Desktop passes the 1080 through via WSL2 (`--gpus all`).
```
docker run --gpus all -v "D:/riggs/out:/work" ghcr.io/<you>/riggs-mia:latest \
    rig --input /work/Guard_base.glb --output /work/Guard_mia.fbx
```
Then validate + render the result with the local bpy tools.

## Step 3 — deploy to RunPod serverless
```
docker push ghcr.io/<you>/riggs-mia:latest
```
In the RunPod console (or API): create a Serverless endpoint from the pushed
image, pick a GPU (A40/L4 are cheap; UniRig needs sm_75+), set container disk big
enough for the baked weights. Copy the endpoint id.

## Step 4 — rig from the CLI
```
set RUNPOD_API_KEY=...
python cloud/launcher/riggs_cloud.py rig \
    --endpoint <ENDPOINT_ID> \
    --input  D:/riggs/out/Guard_base.glb \
    --output D:/riggs/out/Guard_mia.fbx \
    --opts '{"rest_pose_type": "A-pose"}'
```

## What's needed to go live (prerequisites)
- [ ] Docker Desktop running (to build / local-test)
- [ ] A registry login: `docker login ghcr.io` (GitHub PAT) or Docker Hub
- [ ] `RUNPOD_API_KEY` + a little RunPod credit (for cloud, not for local test)

## First-run caveats (expected for ML repos)
- MIA's exact output retrieval (`db.anim_path`) is confirmed from app.py but the
  first real run will validate it; `run_mia.py` falls back to scanning the output
  dir for the newest fbx/glb.
- UniRig skin step errors until the checkpoint releases; skeleton + merge work now.
