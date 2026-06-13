# riggs

Auto-rigging and auto-weighting for 3D humanoid characters, built so an LLM can drive the
whole thing from a mesh file to a poseable, UE5-ready rig with almost no human in the loop.

Named after the lethal weapon character.

## Status: working ✅

A generated humanoid mesh goes in, a properly boned, properly weighted, poseable rig comes
out. Verified end to end on the datastorm "ATLAS Guard": clean Mixamo rig (52 bones, fingers
articulated, 0 unweighted vertices, max 4 influences), posed in Blender with smooth
deformation. No manual bone placement, no vision-guessing, no fighting Mixamo's web UI.

## The problem and the insight

Mesh generation is solved (fal.ai Rodin / Hyper3D from a concept image). Articulation was the
wall — and the wall was the *approach*: trying to get a vision model to place bones by looking
at screenshots fights every tool in the stack. The fix:

1. **ML auto-riggers do skeleton + skinning end to end from geometry.** One command, mesh in,
   rigged FBX out. They read the actual mesh instead of assuming a pose, which is why they
   solve the classic "A-pose mesh vs T-pose skeleton" mismatch automatically.
2. **Blender's `bpy` gives deterministic spatial analysis + validation.** The LLM orchestrates
   and verifies with discrete pass/fail checks (every deform bone has a vertex group, no
   unweighted verts, weights sum to 1.0, hierarchy connected, symmetry) — never eyeballing.

Vision is reserved for one optional sanity-check render after the deterministic checks pass.

## Engines

| Engine | License | Skeleton | Skin | GPU | Notes |
|--------|---------|----------|------|-----|-------|
| **MIA** (Make-It-Animatable) | code MIT, weights Apache-2.0 | Mixamo | yes | any CUDA | **default**, commercial OK, proven working |
| **UniRig** | MIT | own topology | not yet released | sm_75+ | skeleton-only today; for the bake-off |

## How it works

```
mesh (glb/fbx/obj)
  -> extract_base.py        clean unrigged base (bpy)
  -> rp.py rig --engine mia  spin a cloud GPU pod, auto-rig, pull rigged FBX
  -> analyze.py / render.py  validate (structured checks) + bone-overlay render
  -> [canonicalize -> UE5 Mannequin + ik_ bones -> export]   (in progress)
```

The heavy ML rigging runs on a rented cloud GPU (cheap, ~$0.10/character), so you don't need
a capable local GPU. One CLI command spins the pod, provisions, rigs, pulls the result, and
tears the pod down.

## Layout
- `src/riggs/blender_runner.py` — cross-platform headless Blender launcher
- `src/riggs/bpy_scripts/` — `analyze.py` (validate_rig), `render.py` (bone-overlay render),
  `extract_base.py` (clean base mesh)
- `cloud/` — Docker images + RunPod control. `cloud/runpod/rp.py` is the GPU control CLI;
  `cloud/runpod/provision_mia.sh` provisions a pod; `cloud/engines/` has the engine wrappers
  and Dockerfiles. See `cloud/README.md`.
- `.claude/skills/runpod-rig/` — reusable skill so any agent can rig on RunPod
- `notes/` — research + architecture + the working-rig writeup (`05-first-working-rig.md`)

## Setup
1. `cp .env.example .env` and fill in `RUNPOD_API_KEY` + `HF_ACCESS_TOKEN`
   (accept terms once at https://huggingface.co/datasets/jasongzy/Mixamo for MIA).
2. `pip install -r requirements.txt`
3. Blender 4.x/5.x installed (the bpy scripts find it automatically; or set `RIGGS_BLENDER`).

## Quick start
```
# rig a mesh on a cloud GPU
cd cloud/runpod
python rp.py rig --engine mia --input ../../out/Guard_base.glb --output ../../out/Guard.fbx

# validate + render locally
cd ../..
python src/riggs/blender_runner.py src/riggs/bpy_scripts/analyze.py '{"file": "out/Guard.fbx"}'
```

## Roadmap
- [x] Auto-rig (skeleton + skin) from a generated mesh, cloud-driven
- [x] Validation + bone-overlay render, reusable RunPod skill
- [ ] Weight normalization pass
- [ ] Canonicalize Mixamo → UE5 Mannequin + `ik_` bones, UE5 FBX export
- [ ] Animation (next)
