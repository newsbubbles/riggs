"""Import the riggs Guard FBX into UE bound to the Mannequin skeleton, and verify
(programmatically, no vision) that it can play the engine's stock Mannequin anims.

The proof: if the imported SkeletalMesh binds to the same Skeleton asset the stock
AnimSequences use, UE guarantees those anims play on it. We also sample a moving
bone across the anim to confirm real motion.

Args via RIGGS_UE_ARGS (JSON): {fbx, skeleton, dest, anims:[...], scale}
"""
import json
import os
import unreal

A = json.loads(os.environ.get("RIGGS_UE_ARGS", "{}"))
FBX = A.get("fbx", "D:/riggs/out/Guard_UE.fbx")
SKELETON = A.get("skeleton", "/Game/Mannequin/Character/Mesh/UE4_Mannequin_Skeleton")
DEST = A.get("dest", "/Game/RiggsTest")
NAME = A.get("name", "SK_GuardRiggs")
ANIMS = A.get("anims", [
    "/Game/Mannequin/Animations/ThirdPersonIdle",
    "/Game/Mannequin/Animations/ThirdPersonWalk",
    "/Game/Mannequin/Animations/ThirdPersonRun",
])
SCALE = float(A.get("scale", 100.0))

res = {"ok": False, "fbx": FBX, "target_skeleton": SKELETON}


def build_options(skel):
    opts = unreal.FbxImportUI()
    opts.set_editor_property("import_mesh", True)
    opts.set_editor_property("import_as_skeletal", True)
    opts.set_editor_property("import_animations", False)
    opts.set_editor_property("import_materials", False)
    opts.set_editor_property("import_textures", False)
    opts.set_editor_property("create_physics_asset", False)
    opts.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    if skel:
        opts.set_editor_property("skeleton", skel)
    sk = opts.get_editor_property("skeletal_mesh_import_data")
    sk.set_editor_property("import_uniform_scale", SCALE)
    sk.set_editor_property("convert_scene", True)
    sk.set_editor_property("use_t0_as_ref_pose", True)
    return opts


def do_import(skel, name):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", FBX)
    task.set_editor_property("destination_path", DEST)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    task.set_editor_property("options", build_options(skel))
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    return list(task.get_editor_property("imported_object_paths") or [])


try:
    # 1. try binding directly to the existing Mannequin skeleton
    target_skel = unreal.load_asset(SKELETON)
    bound = True
    try:
        imported = do_import(target_skel, NAME)
    except Exception as e:
        res["bind_error"] = str(e)
        imported = []

    mesh_path = f"{DEST}/{NAME}"
    if not unreal.EditorAssetLibrary.does_asset_exist(mesh_path):
        # fall back: import with its own skeleton (proves mesh imports; retarget would follow)
        bound = False
        imported = do_import(None, NAME)

    mesh = unreal.load_asset(mesh_path)
    res["imported"] = unreal.EditorAssetLibrary.does_asset_exist(mesh_path)
    if mesh:
        msk = mesh.get_editor_property("skeleton")
        res["mesh_skeleton"] = msk.get_path_name() if msk else None
        res["bound_to_mannequin"] = bool(msk and msk.get_path_name().startswith(SKELETON))
        try:
            ref = msk.get_editor_property("bone_tree") if msk else None
            res["skeleton_bone_count"] = len(ref) if ref is not None else None
        except Exception:
            pass

    # 2. verify stock anims are playable (share the skeleton) + sample motion
    playable = []
    for ap in ANIMS:
        if not unreal.EditorAssetLibrary.does_asset_exist(ap):
            continue
        anim = unreal.load_asset(ap)
        ask = anim.get_editor_property("skeleton")
        same = bool(mesh and ask and msk and ask.get_path_name() == msk.get_path_name())
        entry = {"anim": ap, "skeleton_matches_mesh": same}
        try:
            entry["num_frames"] = unreal.AnimationLibrary.get_num_frames(anim)
            entry["length_sec"] = round(unreal.AnimationLibrary.get_sequence_length(anim), 2)
        except Exception as e:
            entry["frames_err"] = str(e)
        # sample a moving bone to prove real motion
        for fn in ("get_bone_pose_for_frame",):
            try:
                f = entry.get("num_frames", 1) or 1
                t0 = unreal.AnimationLibrary.get_bone_pose_for_frame(anim, "thigh_l", 0, True)
                t1 = unreal.AnimationLibrary.get_bone_pose_for_frame(anim, "thigh_l", max(1, f // 2), True)
                d = (t1.rotation.euler() - t0.rotation.euler())
                entry["thigh_l_moved_deg"] = round(max(abs(d.x), abs(d.y), abs(d.z)), 1)
            except Exception as e:
                entry["sample_err"] = str(e)
        playable.append(entry)
    res["anims"] = playable
    res["playable_count"] = sum(1 for a in playable if a.get("skeleton_matches_mesh"))
    res["ok"] = bool(res.get("imported") and res["playable_count"] > 0)
except Exception as e:
    import traceback
    res["error"] = str(e)
    res["traceback"] = traceback.format_exc()

print("RIGGS_RESULT_BEGIN")
print(json.dumps(res))
print("RIGGS_RESULT_END")
