# Cloud deployment pivot (2026-06-13)

## Why
Local install hit a wall: this dev box is a GTX 1080 (Pascal sm_61) with no nvcc.
- UniRig needs `flash_attn` (sm_75+) and spconv -> won't build/run on Pascal.
- Bleeding-edge torch 2.11 locally has no prebuilt CUDA-extension wheels yet.

Dockerizing on a cloud GPU fixes all of it: rent an sm_75+ box, the container is
Linux so flash_attn/bpy/headless-render all work, one image runs on any provider,
and anyone with a little credit can rig a mesh via one CLI command.

## Licensing ground truth (checked the actual LICENSE files + HF cards)
- **MIA**: code MIT, **weights Apache-2.0** (NOT the CC-BY-NC the research feared).
  Commercially usable for a real game. Caveat: pipeline uses a GPLv3 Auto-Rig-Pro
  fork — handled by pulling engines at runtime, never vendoring into riggs core.
  The output rig is the user's under ARP's own terms.
- **UniRig**: code MIT, **weights MIT**. BUT only the skeleton model is released;
  the skinning-weights model is still "coming soon". So today UniRig = skeleton
  only; you'd weight the mesh yourself until the checkpoint drops.

=> MIA is the complete, commercial-safe rigger right now. UniRig is the all-MIT
target for when its skinning model ships. Build around MIA first; keep UniRig for
the bake-off.

## What was built (D:/riggs/cloud/)
- `riggs_entry.py` — engine-agnostic entrypoint: `rig` (one-shot, mounted paths)
  and `serve` (RunPod serverless handler). Engine chosen by RIGGS_ENGINE env.
- `engines/mia/` Dockerfile (cuda12.1 runtime base, torch 2.1.2+cu121, weights +
  Mixamo data + FBX2glTF baked in) + `run_mia.py` (drives app._pipeline, grabs
  db.anim_path).
- `engines/unirig/` Dockerfile (cuda12.1 devel base for nvcc, builds flash_attn +
  spconv) + `run_unirig.py` (skeleton -> [skin] -> merge).
- `launcher/riggs_cloud.py` — stdlib CLI: base64 mesh -> RunPod endpoint -> poll
  -> write rigged FBX. `--mesh-url` for >8MB.
- All Python syntax-checked; launcher --help works.

## Key property: MIA image runs on the local 1080 too
MIA needs no flash_attn and torch 2.1.2+cu121 supports Pascal, so the MIA image
runs via Docker Desktop WSL2 GPU passthrough on this 1080. We can test it locally
for free before spending on cloud.

## To go live (prerequisites, none done yet)
- Docker Desktop running (currently stopped) — needed to build + local-test.
- Registry login (ghcr.io via GitHub PAT, or Docker Hub) — needed only to push for cloud.
- RUNPOD_API_KEY + credit — needed only for the cloud run, not the local test.

## Next concrete step
Start Docker Desktop, `docker build -t riggs-mia:latest -f cloud/engines/mia/Dockerfile .`,
then `docker run --gpus all -v D:/riggs/out:/work riggs-mia rig --input /work/Guard_base.glb
--output /work/Guard_mia.fbx`. Then validate + render the result; the bones should
finally follow the arms because MIA fits the skeleton to the actual geometry.
