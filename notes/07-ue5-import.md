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

## Optional: enable a TRUE direct bind (no retargeter)
Re-export the Guard WITHOUT the extra `root` bone (so `pelvis` is top, matching this project's
`SK_Mannequin`), and add the 8 twist bones (`{upperarm,lowerarm,thigh,calf}_twist_01_{l,r}`) at
identity so the skeleton is an exact Mannequin superset. Then "Import with Skeleton = SK_Mannequin"
merges and the Guard plays Mannequin anims with zero retargeting. The retargeter path is more robust
and engine-idiomatic, so it's the default; this is only if you want literal skeleton-sharing.
