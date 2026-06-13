# Diagnosis: why yesterday's Guard rig failed (2026-06-13)

Ran the new `analyze.py` validator (headless Blender 5.1.2) on the datastorm char files.
This is the first real proof of the riggs premise: every failure showed up as a discrete,
structured fact. No vision needed.

## SK_Mannequin.FBX (reference, known-good) — clean
- 67 bones, `ue_mannequin` naming, all `ik_` bones present, single skeleton.
- 0 unweighted verts, 0 unnormalized, max 3 influences/vertex. Textbook.
- Note: `ik_*` bones correctly have no vertex group. The real `validate_rig` must EXEMPT
  `ik_`/non-deform control bones from the "every bone needs a group" check.
- 4 LODs, ~171 islands (clothing/armor pieces) and it skins fine, so island count alone is
  not the failure cause.

## Guard_Rigged.fbx (yesterday's attempt) — broken, 4 concrete faults
- 60 bones, `ue_mannequin` naming, single root (pelvis), **no ik_ bones**.
- Mesh: 20,918 verts, 1.83 m tall (meters, fine), 44 islands.
- **FAULT 1 — weights not normalized: 18,629 / 20,918 verts (89%) sum != 1.0.** Prime cause of
  bad deformation (ballooning/pinching).
- **FAULT 2 — fingers unweighted:** every `index_*`/`middle_*`/`pinky_*`/`ring_*` bone has NO
  vertex group. Hands have bones but no skin binding -> dead/detached fingers.
- **FAULT 3 — 9 influences/vertex,** over the portable cap of 8 (target 4).
- **FAULT 4 — missing ik_ bones** (`ik_foot_root` chain, `ik_hand_*`). Minor, breaks foot IK /
  weapon attach later.

## Why this matters for riggs
All four are mechanically fixable and, more importantly, mechanically DETECTABLE. This validates
the architecture: turn "does the rig look right" into assertions. It also reveals the repair path.

## Repair opportunity (next test case)
The Guard is mannequin-named, and SK_Mannequin.FBX is the SAME skeleton with correct finger
weights. So a `repair_rig` flow can fix the Guard without re-rigging from scratch:
  1. `normalize_all` weights (fixes FAULT 1)
  2. `limit_total` influences to 4 (fixes FAULT 3)
  3. Data Transfer finger weights from SK_Mannequin LOD0 onto the Guard hands (fixes FAULT 2)
  4. copy `ik_*` bones from SK_Mannequin at identity (fixes FAULT 4)
This is a great first exercise for the deterministic toolset and would give datastorm a working
Guard immediately, before the UniRig bake-off.

## Validator refinements queued
- exempt `ik_`/non-deform bones from the bone<->group check
- add explicit checks: influences > cap, normalization fail count, missing canonical bone set
- treat `single_root` on UE FBX carefully (armature object named "root" + pelvis top bone is normal)
