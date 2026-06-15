# Getting a riggs character into UE5 (validated 2026-06-13)

Tested with `Guard_UE.fbx` in the datastorm UE5 project (UE 5.6-era, Interchange importer).
Goal: rigged model (no baked anim) plays the Mannequin's built-in animations.

## What works / what we learned
- **Import is clean.** Interchange import, set **Offset Uniform Scale = 100** (FBX is meters, UE is cm).
  The *"invalid bind poses → rebind using time zero pose"* warning is BENIGN (our T-pose is the frame-0
  rest). Guard comes in upright at correct scale.
- **Direct bind to the project's `SK_Mannequin` FAILS** with *"Failed to merge bones... inserting a bone
  between nodes."* Cause: `canonicalize_ue5.py` adds a `root` bone above `pelvis`, but datastorm's
  `SK_Mannequin` has `pelvis` at the top (no separate `root`). UE also then offers to merge/modify the
  SHARED Manny/Quinn skeleton — **decline that** (don't mutate the project's Mannequin just to import a guard).
- **Correct path = own skeleton + IK Retargeter** (this is riggs' canonical+retarget design anyway):
  import with **Skeleton = None** → Guard gets `Guard_UE_Skeleton`, Mannequin untouched.
- **IK Rig auto-mapping is perfect.** +Add → Animation → Retargeting → IK Rig on `Guard_UE`; set Preview
  Mesh = Guard_UE; right-click `pelvis` → **Set Pelvis** (this version's "Set Retarget Root"); toolbar
  **Auto Create Retarget Chains** → all chains (Spine×3, Neck, Head, clavicle/arm/fingers, legs) map
  because every bone is Mannequin-named. Log: "ready to run on Guard_UE."

## Remaining step (the easy one)
4. **+Add → Animation → Retargeting → IK Retargeter.** Source IK Rig = the Mannequin's (e.g.
   `IK_Mannequin` / `IK_UE5_Mannequin` from the Game Animation Sample). Target IK Rig = `IK_Guard_UE`.
5. Open it → two characters appear. Pick a Manny clip in the Asset Browser → Guard performs it.
6. **Export Selected Animations** → retargeted AnimSequences on the Guard skeleton (or use the
   `Retarget Pose From Mesh` anim node at runtime). The 3-spine Guard vs 5-spine UE5 Manny is handled
   by the Spine chain automatically.

## UPDATE (2026-06-13, UE 5.7.4): direct bind imports + plays, but MANGLES the anim — RETRACTED
Ran `cloud/ue/ue_scripts/import_and_test.py` headless. It imports, binds to `UE4_Mannequin_Skeleton`,
and the JSON reports anims "playing" with motion (sampled `thigh_l`: Idle 4.6 / Walk 20.0 / Run 37.0).
I briefly concluded direct-bind made the retargeter unnecessary. **WRONG — visual QA killed it.**
On screen the ref pose is clean and upright, but the instant a Mannequin anim/blendspace drives the
rig it collapses face-down and splayed (bbox flips 95x46x183 standing -> 95x229x231 prone).

Root cause (confirmed in code): `canonicalize_ue5.py` only **renames** Mixamo bones to Mannequin
names; it never re-orients them, and exports with `primary_bone_axis="Y"` (Mixamo convention). So the
skeleton is Mannequin-NAMED but Mixamo-ORIENTED. A Mannequin AnimSequence stores local rotations
relative to the Mannequin's bone axes; applied to Mixamo-oriented bones, every bone rotates around the
wrong axis -> abomination. Ref pose looks fine because no rotation is applied. The `import_and_test`
JSON can't catch this: `thigh_l_moved_deg` proves the bone moved, not that it moved correctly. This is
exactly the render-QA-as-final-gate case the architecture calls out.

Lesson: `import_and_test.py`'s direct-bind is a STRUCTURAL smoke test only (does it import, do names
line up, does a bone move). It is NOT proof the animation is correct. Never ship on it without an
eyes-on / rendered playback check. TODO: extend the harness to bake one retargeted frame and compare
bone WORLD positions against the source to catch orientation mismatch numerically.

**Correct path = the IK Retargeter below** (this is what the canonicalize naming was always FOR:
auto-characterization maps the chains instantly). Import Skeleton=None -> own skeleton -> IK Rig ->
IK Retargeter (Manny source -> Guard target) -> batch-bake the stock anims onto the Guard. The
retargeter resolves the orientation (and any T-pose-vs-A-pose base-pose) gap in pose space.

## Optional: enable a TRUE direct bind (no retargeter)
Re-export the Guard WITHOUT the extra `root` bone (so `pelvis` is top, matching this project's
`SK_Mannequin`), and add the 8 twist bones (`{upperarm,lowerarm,thigh,calf}_twist_01_{l,r}`) at
identity so the skeleton is an exact Mannequin superset. Then "Import with Skeleton = SK_Mannequin"
merges and the Guard plays Mannequin anims with zero retargeting. The retargeter path is more robust
and engine-idiomatic, so it's the default; this is only if you want literal skeleton-sharing.
(Superseded in practice by the 2026-06-13 UPDATE above: the legacy importer already does the merge.)
