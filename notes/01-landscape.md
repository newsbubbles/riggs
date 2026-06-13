# Auto-rig / auto-skin landscape (2026)

Verified survey from web research. Every tool checked against live docs, not memory.
Source URLs kept inline.

## ML auto-riggers (skeleton + skin from geometry, no human placement)

These are the unlock. They take a mesh and output bones plus skin weights in one shot.

### UniRig (VAST-AI / Tsinghua, SIGGRAPH 2025) — PRIMARY CANDIDATE
- Does **both** skeleton (autoregressive transformer, "Skeleton Tree Tokenization") **and**
  skinning (bone-point cross-attention).
- Input: obj / fbx / glb / vrm. Output: fbx with skeleton + weights baked in.
- License: **MIT** (the only cleanly commercial-OK local option). Verify the HuggingFace
  weight-card license separately from the code license.
- VRAM: 8GB+ for inference. Runs with huge headroom on the 5090, also fine on the 1070.
- Headless: yes, CLI / bash driven, no GUI. No official hosted API (community ComfyUI wrapper exists).
- Quality: trained on Rig-XL + VRoid, handles realistic and anime humanoids, animals, inorganic.
- Caveat to resolve first: confirm the full skeleton+skinning checkpoint is actually published
  on HF (was "coming soon" at README time).
- Skeleton: its own learned topology, not UE5/Mixamo native. Retarget for UE5.
- https://github.com/VAST-AI-Research/UniRig | https://huggingface.co/VAST-AI/UniRig

### Make-It-Animatable (CVPR 2025, jasongzy) — PRIMARY CANDIDATE for humanoids
- Outputs bones + blend weights + pose transforms. Targets the **Mixamo skeleton**, which is
  the single easiest retarget into UE5.
- Sub-1-second inference. Handles arbitrary input poses (not just T-pose), which is rare and useful.
- Works on meshes and Gaussian splats.
- License: **ambiguous** — Apache-2.0 on GitHub vs CC-BY-NC-4.0 on the HF Space. Must resolve the
  actual LICENSE file before any commercial use (datastorm is a sellable game).
- Local Gradio app, scriptable. Small model, 5090 is overkill.
- https://jasongzy.github.io/Make-It-Animatable/ | https://github.com/jasongzy/Make-It-Animatable

### Others
- **RigNet** (2020): does both, but GPLv3 (copyleft, bad for a sellable game), unmaintained,
  legacy CUDA that fights the 5090, and needs the mesh decimated to 1-5k verts. Superseded.
- **MagicArticulate** (ByteDance, CVPR 2025): general-purpose, autoregressive skeleton + diffusion
  skinning. Research-stage. https://github.com/Seed3D/MagicArticulate
- **HumanRig** (Alibaba, CVPR 2025): humanoid-specialized, uniform skeleton topology, built to
  survive messy AI-generated meshes where GNN methods fail. Requires T-pose.
  https://github.com/c8241998/HumanRig
- **Tripo3D / Meshy / Anything World**: cloud REST rigging APIs. Tripo is the same lineage as
  UniRig (Tripo co-authored it). Good as cloud overflow when local fails or the queue is deep.
  Meshy is humanoid-only and caps at 300k faces. All credit-based.
- **Rodin / Hyper3D** (our current mesh gen): mesh + texture only, NO rig. `generate_with_pose`
  forces a T/A pose which eases downstream rigging, but produces no bones. Pair with a rigger.

## Blender / free-tool ecosystem (for the deterministic fallback path)

- **Auto-Rig Pro** ($40): the only tool with native UE5 Mannequin export (6 spine / 2 neck,
  `ik_foot_*` bones, axis match, "Rename for UE"). Its export IS scriptable
  (`bpy.ops.arp.arp_export_fbx_panel`). Its Smart auto-placement and Bind are NOT officially
  scriptable and the Smart step is a viewport-modal operator, so full headless ARP is unverified
  and risky. **Best use: the UE5 export stage, not the rigging stage.**
- **Rigify** (free, built-in): fully headless-capable (no modal ops). Add metarig
  (`armature_human_metarig_add`), set edit-bone head/tail by coordinate, `rigify_generate()`.
  But it has NO feature detection — you must supply joint landmarks yourself (that is our
  geometric detection layer). Not Mannequin-named, needs rename/retarget.
- **AccuRIG** (free) and **Mixamo** (free): best one-click skin quality, but BOTH are GUI-only
  with no API / CLI / headless path. Disqualified from an autonomous pipeline (short of brittle
  computer-use clicking). Mixamo also has no supported API at all.
- **Blender automatic weights** (`parent_set type='ARMATURE_AUTO'`, bone heat): scriptable and
  free, but hard-fails on disjoint islands / non-manifold / bad scale, which is exactly what
  arbitrary FBX is. Needs cleanup or a more robust skinner.
- **Voxel / Surface Heat Diffuse Skinning** ($30, or free on GitHub): robust skinner that
  "never fails with bone heat error," handles overlapping body+clothing, skeleton-agnostic.
  Operator name needs verification by introspection; Blender 4.x compat needs checking.
  https://github.com/meshonline/Surface-Heat-Diffuse-Skinning

## UE5 target requirements (verified against Epic docs)

### Two valid strategies, both confirmed
1. Rig directly to the UE5 Mannequin skeleton (exact lowercase `_l/_r` names + `ik_*` bones).
   Zero retarget friction, instant access to Mannequin/Lyra/MetaHuman animation libraries.
2. Rig to a canonical intermediate (Mixamo / HumanIK naming) then UE5 IK Retargeter. UE5.4+
   auto-characterization fuzzy-matches names against templates and adapts chains of different
   bone counts (e.g. 3-spine to 5-spine). A non-Mannequin rig CAN drive Mannequin animations,
   both baked (Export Animations) and at runtime (Retarget Pose From Mesh node).

Strategy 2 generalizes beyond UE5, which matches the stated goal of "a solution for all of them."

### UE5 Mannequin skeleton (Manny/Quinn): 5 spine, 2 neck, twist + metacarpal bones
```
root -> pelvis -> spine_01..05 -> { clavicle_l/r -> upperarm -> (twist) -> lowerarm -> (twist) -> hand -> fingers ; neck_01 -> neck_02 -> head }
pelvis -> thigh_l/r -> (twist) -> calf -> (twist) -> foot -> ball
root -> ik_foot_root -> ik_foot_l/r
root -> ik_hand_root -> ik_hand_gun -> ik_hand_l/r
```
Legacy UE4 Mannequin = 3 spine, 1 neck, single twist, no metacarpals. The 3-vs-5 spine
difference is why UE4 anims look wrong on UE5 without a retargeter. The `ik_*` bones do nothing
on their own (targets for foot IK + weapon attach), sit at identity, but MUST be authored or
foot IK / weapon workflows break later.

### FBX import checklist (must-pass to avoid silent failures)
- FBX 2020.2
- Scale in cm (human ~180 units). Blender defaults to meters, so this is the #1 silent failure (100x off).
- Z-up, X-forward, left-handed. Wrong axis = character imported lying down or rotated 90.
- Single root bone at origin, identity rotation. Multiple roots = import error.
- Unique bone names. Every vertex weighted to >=1 bone. Weights normalized to 1.0.
- Clamp influences to <=8 (ideally 4) for portability. UE5 supports up to 12 via Unlimited Bone Influences.
- Valid bind pose, or import with "Use Time 0 as Reference Pose."
- A-pose recommended over T-pose (matches Mannequin/MetaHuman, fewer shoulder retarget artifacts).
- Export from Blender with `add_leaf_bones=False`, `use_armature_deform_only=True`.

## bpy headless capability summary

Deterministic and headless (the foundation of our tool surface):
- Armature + bone placement by head/tail/roll coordinate, parenting, naming, mirror
  (`symmetrize`, `autoside_names`). 100% data API, no viewport.
- Vertex groups: create, set/read per-vertex weights (`VertexGroup.add/weight`), normalize.
- Data Transfer modifier: copy a known-good rig's weights onto a new mesh deterministically.
- Mesh analysis: `obj.bound_box`, `obj.dimensions`, `mathutils.kdtree.KDTree` (nearest vertex),
  `mathutils.bvhtree.BVHTree` (raycast, closest point). Extremity + symmetry detection is built
  on these, not a builtin but straightforward. **This replaces human landmark-finding.**
- FBX import/export with all the UE5 options.

Needs care:
- Automatic (bone-heat) weights: scriptable but hard-fails, needs error capture + remediation.
- Headless verification render: NOT via screen-screenshot (needs a window) and NOT via Windows
  headless EEVEE. Use `bpy.ops.render.render` with Workbench or Cycles. On Windows this points
  toward running the render under WSL/Linux (matches the darkfloor WSL pattern).

## blender-mcp reality
`ahujasid/blender-mcp` is a thin remote-exec bridge: its power tool is `execute_blender_code`
(arbitrary Python with bpy in scope) talking over a socket to a **GUI** Blender instance. It has
NO rigging-specific tools and is NOT a headless harness. Good for interactive debugging. For the
autonomous pipeline we want the same bpy code run under `blender --background --python` exposed as
proper structured tools, not raw code-exec against a live window.
