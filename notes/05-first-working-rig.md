# First working rig (2026-06-13)

The Guard mesh, auto-rigged end to end through the cloud pipeline, posed cleanly in
Blender. Finger bones that were completely unweighted/dead in yesterday's broken rig
now articulate individually with smooth mesh deformation around the knuckles. Verified
interactively in Pose Mode (the classic middle-finger test pose).

This is the proof the project hinged on: a generated mesh became a properly boned,
properly weighted, poseable humanoid with NO manual bone placement and NO vision-guessing.

## The path that worked
1. extract_base.py -> clean unrigged Guard_base.glb
2. rp.py: spin RTX 3090 RunPod pod, provision Make-It-Animatable, rig, pull Guard_mia.fbx
3. MIA reposed mesh+skeleton to a consistent T-pose rest -> 52-bone Mixamo rig, fingers
   weighted, 0 unweighted verts, max 4 influences. Fixed the A-pose-mesh-vs-T-pose-skeleton
   mismatch at the source (it reads geometry instead of assuming a pose).
4. analyze.py validated, render.py (bone overlay) confirmed bones follow the arms.
5. Imported into live Blender via the MCP, Pose Mode, posed fingers -> clean deformation.

## What made the difference vs yesterday
- Stopped trying to make a vision model place bones. Let an ML auto-rigger read the
  geometry. The LLM orchestrates + validates with discrete checks.
- Cloud GPU sidestepped the local Pascal/flash_attn/Linux walls.

## Remaining polish (local, no GPU)
- normalize weights (8245 verts slightly off 1.0)
- rename Mixamo -> UE5 Mannequin + add ik_ bones, export UE5 FBX
- broader pose / deformation stress test
