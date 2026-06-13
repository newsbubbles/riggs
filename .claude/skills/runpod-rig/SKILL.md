---
name: runpod-rig
description: Auto-rig a 3D humanoid mesh on a cloud GPU via RunPod, and manage RunPod GPU pods from the CLI. Use when the user wants to rig/skin a character mesh (FBX/GLB/OBJ) using Make-It-Animatable or UniRig but lacks a capable local GPU, or asks to spin up / control / tear down a RunPod GPU pod, list RunPod GPU prices, or run a one-shot GPU batch job that returns a file. Triggers: "rig this on runpod", "rig on a cloud GPU", "spin up a runpod pod", "auto-rig the mesh", "make it animatable on the cloud".
---

# runpod-rig

Rig a humanoid mesh on a rented GPU and pull the rigged FBX back, all from one
CLI command. The heavy ML rigger runs on a RunPod pod; you only need a RunPod
API key. Everything lives in `cloud/runpod/rp.py` in the riggs project (D:/riggs).

**Status: verified working** (MIA on RTX 3090 → 52-bone Mixamo rig, fingers
weighted, posed cleanly in Blender). The fixes found during bring-up are already
baked into `provision_mia.sh` + `cloud/engines/mia/run_mia.py`; see Gotchas below.

## When to use which engine
- **mia** (Make-It-Animatable, default): skeleton + skin weights, Mixamo skeleton,
  Apache-2.0 weights (commercial OK). Runs on any GPU. **Use this for a full rig.**
- **unirig**: all-MIT but the skinning model isn't released yet (skeleton only
  today). Needs sm_75+ (flash_attn). Use only for skeleton experiments / bake-off.

## Prerequisites (check first)
1. `RUNPOD_API_KEY` in `D:/riggs/.env` (already set if this project is configured).
2. `HF_TOKEN` (or `HF_ACCESS_TOKEN`) in `D:/riggs/.env`, read scope. A token is NOT
   enough on its own — you must also click **Agree / Request access** on each gated
   repo once, with the same account the token belongs to, or downloads 403 mid-run:
   - **Rigging (MIA):** https://huggingface.co/datasets/jasongzy/Mixamo — gated
     Mixamo bone templates, loaded at import. Usually granted instantly on agreeing.
   - **Animation (Kimodo):** https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct
     — Kimodo's text encoder. **Meta manual review**, can take minutes to hours; submit
     early. Commercial OK under the Llama 3 Community License.
3. `pip install runpod` (the SDK) and OpenSSH client `ssh`/`scp`/`ssh-keygen` on PATH
   (built into Windows 10+ and Linux).
4. RunPod account has a little credit. A rig run is ~15-25 min on a cheap GPU
   (RTX 3090 ≈ $0.2-0.3/hr), so roughly $0.05-0.15 per character. Use `python rp.py
   stop <id>` to pause billing while keeping a provisioned pod, `resume <id>` to wake it.

## The one command (recommended)
```
cd D:/riggs/cloud/runpod
python rp.py rig --engine mia \
    --input  D:/riggs/out/Guard_base.glb \
    --output D:/riggs/out/Guard_mia.fbx \
    --gpu "NVIDIA GeForce RTX 3090"
```
This creates a pod, uploads the riggs code, provisions the engine (first boot
installs deps + downloads weights, ~10-15 min), rigs the mesh, downloads the FBX,
and **terminates the pod**. Add `--keep` to leave the pod up for debugging or
repeat runs (then `python rp.py down <id>` when done).

`--opts` passes engine options as JSON, e.g. MIA: `--opts '{"rest_pose_type":"A-pose"}'`.

## Lifecycle commands (for manual control)
```
python rp.py gpus                       # list GPU types sorted by price
python rp.py up --gpu "NVIDIA GeForce RTX 3090"   # create pod, print ssh
python rp.py status <pod_id>            # state + connection
python rp.py exec <pod_id> -- nvidia-smi
python rp.py push <pod_id> local.glb /opt/riggs/in.glb
python rp.py pull <pod_id> /opt/riggs/rigged.fbx out.fbx
python rp.py down <pod_id>              # TERMINATE (stops billing)
```

## How it works (so you can debug)
- SSH: `rp.py` keeps an ed25519 keypair in `cloud/runpod/.ssh` and passes the
  public key to the pod via the `PUBLIC_KEY` env var, so no dashboard SSH-key
  step is needed. The pod image must run sshd — use a RunPod pytorch base image
  (the default `runpod/pytorch:...py3.11...` does).
- Provisioning: `provision_<engine>.sh` runs on the pod (mirrors the engine
  Dockerfile) so no registry/image build is required.
- The rig itself runs `riggs_entry.py rig`, which calls `run_<engine>.py`.

## Troubleshooting
- **"pod not SSH-ready"**: GPU may be unavailable in that region; try another
  `--gpu` or `--cloud COMMUNITY`. Check `python rp.py status <id>`.
- **provisioning failed**: re-run with `--keep`, then
  `python rp.py exec <id> -- bash /opt/riggs/provision_mia.sh` to see the error.
  Common cause: HF LFS rate limit (retry) or a deps conflict.
- **rig failed**: ssh in (`--keep`), `cd /opt/riggs`, run the rig manually; check
  `run_mia.py` output retrieval (`db.anim_path`) on the first real run.
- **ALWAYS terminate** pods you `--keep` — they bill per second while running.

## Gotchas (already handled in the scripts — context if something regresses)
- Run `rp.py` from Git Bash with `MSYS_NO_PATHCONV=1`, or remote `/opt/...` paths get
  rewritten to `C:/Program Files/Git/opt/...`. (PowerShell is unaffected.)
- RunPod `stop` WITHOUT a network volume wipes the container filesystem — a resumed
  pod comes back as the bare base image. Don't use stop to "pause" a provisioned pod;
  keep it running or re-provision (~12 min).
- MIA needs BOTH `bones.fbx` and `bones_vroid.fbx` from the gated Mixamo dataset, fetched
  via `huggingface_hub.hf_hub_download` (the `huggingface-cli download` syntax broke in hub 1.x).
- bpy needs apt libs: `libxkbcommon0 libxext6 libdbus-1-3 libxrandr2 libxinerama1 libxcursor1`.
- Headless MIA: `run_mia.py` no-ops `gr.Info/Warning/Success` and stubs the Gradio UI
  globals (`state`, `output_*`); the rigged file is `db.anim_path`; needs `util/FBX2glTF`.

## Faster path (optional, after first success)
Build + push the engine image to a registry (see `cloud/README.md`), register it
with `runpod.create_container_registry_auth`, and pass `--image <registry/image>`
to skip the ~10-15 min runtime install (weights are baked in).

## Extending
- New engine: add `cloud/engines/<name>/run_<name>.py` (a `rig(input, output, opts)
  -> {ok, output}` function) + `cloud/runpod/provision_<name>.sh`, then
  `--engine <name>`.
