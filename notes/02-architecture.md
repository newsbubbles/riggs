# riggs architecture (proposed)

## Shape: a funnel with a cheap robust default and a deterministic fallback

```
concept image / mesh
        |
   [ Rodin/Hyper3D ]  (already solved, mesh only)
        |
        v
  ============================  riggs  ============================
  Stage 0  INGEST + NORMALIZE   (bpy, deterministic)
     import fbx/glb, fix scale->cm, axis->Z-up/X-fwd, single root,
     triangulate, merge islands, manifold cleanup, detect T vs A pose
        |
        v
  Stage 1  AUTO-RIG  (two paths, try the robust one first)
     Path A (default):  ML rigger -> skeleton + skin in one shot
        UniRig (MIT, local, 5090)         <- default for license safety
        Make-It-Animatable (Mixamo skel)  <- when humanoid + license cleared
        Tripo3D API                       <- cloud overflow when local fails
     Path B (fallback / full control):  deterministic bpy
        geometric landmark detection (KD-tree/BVH/bbox/symmetry)
        -> build canonical skeleton by coordinate (Rigify metarig or custom)
        -> robust skin (Voxel Heat Diffuse, fallback Data Transfer from ref rig)
        |
        v
  Stage 2  CANONICALIZE + RETARGET PREP
     map whatever skeleton came out -> canonical naming (Mixamo/HumanIK)
     add ik_ bones, optionally rename to UE5 Mannequin
        |
        v
  Stage 3  VALIDATE  (deterministic, the "binary detection per bone")
     structured pass/fail assertions (see below)
     + optional headless Workbench render front/side for LLM vision QA
        |
        v
  Stage 4  EXPORT
     export_ue5_fbx preset (add_leaf_bones=False, deform-only, cm, axis)
     + round-trip re-import sanity check
  =================================================================
        |
        v
  UE5: bind to Mannequin OR set up IK Retargeter (generalizes to any engine)
```

## Why this beats yesterday's approach

Yesterday: vision model tries to place bones on the mesh by looking at screenshots. That fights
the tools (vision is low-bandwidth for spatial placement) and is miserable to verify.

Now: Stage 1 Path A hands the entire skeleton+skin problem to an ML model that was trained for
exactly this. When that is not good enough, Path B uses deterministic geometry (KD-tree, raycast,
bounding box) to find landmarks. In neither path does the LLM eyeball bone positions. The LLM
orchestrates, reads structured validation, and only looks at a render as a last sanity check.

## Stage 3 validation: discrete assertions (this is your per-bone binary detection)

Each returns a clean pass/fail with offending element ids. No vision required.

- every deform bone has a matching vertex group
- no vertex is left unweighted (Epic auto-weights stray verts to root, which deforms badly)
- per-vertex weights sum to 1.0 within tolerance, influences clamped to <=N
- armature hierarchy is fully connected, single root, no cycles
- no zero-length or degenerate bones
- left/right bones are symmetric within tolerance (mirror-coordinate KD query)
- bone count <= 65536, unique names
- scale is cm, up axis correct, single root at origin
- (humanoid expectation) the canonical bone set is present (hips, spine, head, both
  arm/forearm/hand, both upleg/leg/foot) per the HumanIK 15-node minimum

Only after all of these pass do we spend a vision call on a Workbench render to catch the rare
"weights are valid but the elbow bends backward" class of error.

## The LLM-facing tool surface (deterministic-first)

These are the candidate tools. Most are deterministic bpy wrappers run under
`blender --background --python`. The schema design for these is its own task and should go
through the agentic-tooling skill (this whole project is a control surface for an LLM planner).

1. `ingest_mesh(path)` -> normalized scene, reports detected scale/axis/pose, cleanup applied
2. `analyze_mesh_landmarks(obj)` -> bbox, dimensions, symmetry axis, candidate head/hands/feet/spine
   coords (KD-tree + BVH + axis extrema). The "see the mesh without vision" tool.
3. `auto_rig_ml(path, engine)` -> shell out to UniRig / MIA / Tripo, return rigged fbx + report
4. `place_bone(armature, name, head, tail, roll, parent, connect)` -> wraps edit-bone creation
5. `build_skeleton(spec)` -> batch place_bone from a landmark spec, autoside_names + symmetrize
6. `auto_weight(mesh, armature, method)` -> bone-heat / voxel-heat / data-transfer, with failure
   capture and auto-remediation (rescale, clean, island split)
7. `set_vertex_weights / read_vertex_weights` -> deterministic weight edit/inspect + normalize
8. `retarget_to(skeleton_standard)` -> rename/map canonical -> Mixamo / Mannequin, add ik_ bones
9. `validate_rig(mesh, armature)` -> the structured assertion report above
10. `screenshot_pose(armature, angles=[front,side])` -> Workbench render PNGs for vision QA
11. `export_ue5_fbx(path)` -> correct preset + round-trip re-import check

Design principle (from agentic-tooling): the LLM should never need to do continuous spatial
reasoning. Every tool either does the spatial work itself (deterministic geometry / ML) or returns
discrete structured facts the LLM can branch on. Errors carry state so the LLM can remediate
instead of retrying blindly.

## Decisions (LOCKED 2026-06-13)

0. **This is open source + cross-platform.** Must run on both Linux native and Windows. Two
   consequences:
   - Core has **no paid/closed dependency**. Auto-Rig Pro is dropped from the core; the UE5 export
     stage is built from pure `bpy` (`export_scene.fbx` UE5 preset + a bone-rename map). ARP stays
     an optional convenience only.
   - License hygiene: prefer MIT/Apache. RigNet (GPLv3) is out. UniRig (MIT) is the safe core.
     Make-It-Animatable's license (Apache on GitHub vs CC-BY-NC on the HF Space) MUST be resolved
     before it ships as a bundled default; until then it's an optional/bake-off engine.
1. **Runtime**: cross-platform headless. `blender --background --python` runs on both OSes. The
   only Windows-headless gap is EEVEE, so the verification render uses **Workbench or Cycles**
   (both render headless on Windows and Linux). No WSL requirement. blender-mcp is optional, for
   interactive debugging only.
2. **Rig engine**: **bake-off UniRig and Make-It-Animatable** on a shared test set, pick the
   default from real output quality. Both wired as pluggable engine adapters behind one interface.
3. **Skeleton target**: **canonical + retarget**. Rig to a canonical standard (Mixamo/HumanIK
   naming), then UE5 IK Retargeter. Generalizes to any engine. Also emit a renamed-to-Mannequin
   FBX as a convenience export.

## Engine adapter interface (so the bake-off and future engines are pluggable)

```
RigEngine.rig(normalized_mesh_path) -> RigResult { skeleton, weights, source_skeleton_name, report }
```
Adapters: UniRigEngine (local CUDA), MIAEngine (local CUDA), TripoEngine (cloud REST, overflow),
BpyGeometricEngine (deterministic fallback). The bake-off harness runs all available engines on
the test set and scores via validate_rig + a render diff.

## First build milestone (once decisions land)

A vertical slice on ONE test mesh: ingest -> UniRig -> validate -> export -> confirm clean import
in UE5. Prove the spine of the pipeline end to end before broadening to the fallback path,
multiple engines, and the full tool schema.
