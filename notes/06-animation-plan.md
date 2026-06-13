# riggs animation: text -> humanoid motion -> UE5/Blender (plan)

Source idea: text_to_motion_humanoid_stack.md. Thesis (agreed): text-to-motion already
exists in open research, but it spits out motion tensors / SMPL / BVH, not production FBX on
a target game rig. The product gap is the BRIDGE: normalize -> retarget -> contact cleanup ->
root-motion -> UE5/Blender export + validation.

## Why this is a natural riggs extension (we already built ~70% of the bridge)

| Animation need (from the doc) | riggs already has it |
|---|---|
| Run the generator on a GPU, agent-driven | `cloud/runpod/rp.py` pod harness + provision pattern + the RigEngine adapter shape |
| A canonical skeleton to target | Mixamo canonical + the Mixamo->UE Mannequin map in `canonicalize_ue5.py` |
| Retarget onto a production rig | the bone map + the headless `blender_runner` + bpy bridge |
| FBX export to UE5 (scale + Y-up handled) | `canonicalize_ue5.py` export settings + the documented UE import gotcha |
| Structured validation | `analyze.py` (extend the same pass/fail idea to motion) |
| Drive it from a Claude agent | the `runpod-rig` skill pattern |

So animation is mostly: add a motion GENERATOR engine + a RETARGET/CLEANUP bpy stage, both
reusing the harness, the canonical skeleton, and the export we already have. The rig riggs
produces is the retarget TARGET, so a character you rigged can be animated end to end in one
project.

## Canonical internal motion format (the spine of the bridge)
One normalized representation everything converts to/from:
```
fps, root_translation[t], root_rotation[t], joint_rotations[t,j], joint_positions[t,j],
contacts[t, foot/hand], skeleton_definition, scale, coordinate_system, metadata
```
Importers/exporters: research .npy/.npz, SMPL/SMPL-X, BVH, FBX (via Blender), GLB.

## LICENSING VERDICT (verified 2026-06-13 — settled before building)
- **MoMask / MDM / T2M-GPT: NOT commercially usable.** Code is MIT/Apache, but all are trained on
  HumanML3D -> AMASS -> SMPL/SMPL-X. AMASS and SMPL licenses explicitly ban "use of the Dataset to
  train ... neural networks ... for commercial use of any kind." The pretrained weights are the
  prohibited artifact. Fine for research/tooling, NOT for shipping in datastorm. (amass.is.tue.mpg.de/license.html,
  smpl.is.tue.mpg.de/modellicense.html)
- **PRIMARY (clean, commercial): NVIDIA Kimodo** (github.com/nv-tlabs/kimodo). Verified: real
  text-to-motion diffusion model, Apache-2.0 code; **SOMA + Unitree-G1 weight variants are NVIDIA
  Open Model License = commercial OK, royalty-free, NVIDIA claims no output ownership**; trained on
  Bones Rigplay (700hr commercially-friendly mocap), NOT AMASS. **AVOID the SMPL-X variant (R&D /
  non-commercial).** ~17GB VRAM (or <3GB with TEXT_ENCODER_DEVICE=cpu). Output: 77-joint SOMA
  skeleton -> retarget SOMA->Mixamo via riggs bridge.
- **TURNKEY FALLBACK: DeepMotion SayMotion API** (commercial license on paid tiers, exports FBX/GLB/BVH).
- **ZERO-RISK CURATED: Mixamo** animations (free for commercial games, we already target the skeleton)
  + Cascadeur (Indie $99/yr) for editing/physics cleanup. Not text-driven, but bulletproof.
- Verify-before-ship: confirm the exact Kimodo SOMA/G1 weight license at download (Open Model, not
  R&D); read SayMotion ToS commercial clause.

## MVP (kinematic, no physics yet) — mirrors how we shipped rigging
```
text prompt
  -> Kimodo (SOMA variant) on a RunPod pod (rp.py, same flow as MIA)   [MotionEngine adapter]
  -> SOMA 77-joint motion (canonical motion format)
  -> Blender: import, retarget SOMA -> riggs' Mixamo rig (new SOMA->Mixamo bone map)
  -> foot-lock + floor + root-motion cleanup
  -> bake action, export UE FBX (reuse canonicalize export + scale/Y-up handling)
  -> validate (frame rate, foot sliding, root motion, no penetration)
  -> UE5
```
Engine choice: **Kimodo-SOMA first** (the only clean, commercial, open text-to-motion model).
SayMotion API as a fallback/comparison behind the same MotionEngine adapter.

## Higher-quality stack (phase 2+): physics realism pass
After kinematic MVP works, route reference motion through PHC / PULSE / ProtoMotions /
MaskedMimic for physically plausible contacts/balance, export back to canonical format,
retarget/export again. This is the real "humanoid animation generator" but much heavier.

## Build phases
1. **MotionEngine harness** — wrap MoMask on a pod (provision_momask.sh), `rp.py motion
   --prompt "..." --out clip.bvh`, normalize to canonical format, save a preview.
2. **Blender retarget bridge** — bpy script: import motion -> map source skeleton to riggs
   Mixamo rig -> retarget -> bake -> export FBX (reuse canonicalize_ue5 export).
3. **Cleanup layer** — foot-contact detection + locking, floor correction, root-drift smoothing.
4. **Physics pass** — PHC/PULSE/ProtoMotions/MaskedMimic (optional upgrade).
5. **Presets + validation** — Mixamo / Rigify / UE Mannequin presets, Blender + UE5 validation.

## Decisions / risks to settle before building
- **Commercial license — RESOLVED (see Licensing Verdict above).** MoMask/MDM/T2M-GPT are out for
  commercial (AMASS/SMPL). Clean path = Kimodo-SOMA (NVIDIA Open Model License). Settled.
- **MVP scope:** kinematic-first (skip physics) to get a working text->FBX path fast, then add
  the physics realism pass. Recommended.
- **Retarget target:** reuse the riggs Mixamo canonical + Mannequin path. Obvious reuse.
- **GPU fit:** these are smaller than the riggers; cheap pods are fine. Same rp.py flow.

## First concrete step
Stand up Kimodo (SOMA variant) on a RunPod pod exactly like we did MIA: `provision_kimodo.sh` +
`cloud/engines/kimodo/run_kimodo.py` (prompt -> SOMA motion), wired into `rp.py motion --prompt`.
Then the Blender SOMA->Mixamo retarget onto the Guard rig is step 2. Use the SOMA Open-Model-License
checkpoint, NOT SMPL-X.
