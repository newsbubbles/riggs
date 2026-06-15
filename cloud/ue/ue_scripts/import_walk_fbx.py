"""Import the riggs Guard_walk.fbx (mesh + BAKED walk keyframes, Mixamo rig) into UE.

No UE retargeter: the motion is keyframed in the FBX (Kimodo walk retargeted onto the
Guard's Mixamo rig in Blender). UE just reads the keyframes. Scale=1 (FBX is cm),
convert_scene on (Mixamo Y-up -> UE Z-up). Verifies the AnimSequence actually moves.

Headless-safe. Writes D:/riggs/out/walk_import.json.
"""
import json
import os
import unreal

OUT = "D:/riggs/out/walk_import.json"
FBX = "D:/riggs/out/motion/Guard_walk.fbx"
DEST = "/Game/RiggsWalk"
NAME = "SK_GuardWalk"

try:
    unreal.SystemLibrary.execute_console_command(None, "Interchange.FeatureFlags.Import.FBX 0")
except Exception:
    pass

res = {"ok": False, "fbx": FBX}
try:
    o = unreal.FbxImportUI()
    o.set_editor_property("import_mesh", True)
    o.set_editor_property("import_as_skeletal", True)
    o.set_editor_property("import_animations", True)
    o.set_editor_property("import_materials", False)
    o.set_editor_property("import_textures", False)
    o.set_editor_property("create_physics_asset", False)
    o.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    s = o.get_editor_property("skeletal_mesh_import_data")
    s.set_editor_property("import_uniform_scale", 1.0)
    s.set_editor_property("convert_scene", True)
    s.set_editor_property("use_t0_as_ref_pose", False)
    try:
        a = o.get_editor_property("anim_sequence_import_data")
        a.set_editor_property("import_uniform_scale", 1.0)
        a.set_editor_property("convert_scene", True)
    except Exception:
        pass

    t = unreal.AssetImportTask()
    t.set_editor_property("filename", FBX)
    t.set_editor_property("destination_path", DEST)
    t.set_editor_property("destination_name", NAME)
    t.set_editor_property("automated", True)
    t.set_editor_property("replace_existing", True)
    t.set_editor_property("save", True)
    t.set_editor_property("options", o)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])

    # save EVERYTHING the import created (mesh + auto-created Skeleton + AnimSequence).
    # task save=True only persists the primary mesh; the skeleton/anim are separate assets.
    unreal.EditorAssetLibrary.save_directory(DEST, only_if_is_dirty=False, recursive=True)

    mesh = unreal.load_asset("%s/%s" % (DEST, NAME))
    if mesh:
        b = mesh.get_bounds().box_extent
        res["mesh_size_cm"] = [round(b.x * 2, 1), round(b.y * 2, 1), round(b.z * 2, 1)]
        res["tall_cm"] = round(max(b.x, b.y, b.z) * 2, 1)

    # find the imported AnimSequence(s) in DEST
    paths = unreal.EditorAssetLibrary.list_assets(DEST, recursive=True)
    anims = []
    for p in paths:
        ad = unreal.EditorAssetLibrary.find_asset_data(p)
        if ad and ad.asset_class_path.asset_name == "AnimSequence":
            anims.append(p.split(".")[0])
    res["anim_assets"] = anims

    # sample a leg bone across frames to prove real motion
    CANDS = ["mixamorig:LeftUpLeg", "mixamorig:RightUpLeg", "LeftUpLeg",
             "mixamorig_LeftUpLeg", "mixamorig:LeftLeg", "thigh_l", "pelvis", "mixamorig:Hips"]
    checks = []
    for ap in anims:
        anim = unreal.load_asset(ap)
        f = unreal.AnimationLibrary.get_num_frames(anim)
        entry = {"anim": ap, "frames": f}
        moved_any = False
        for bone in CANDS:
            try:
                t0 = unreal.AnimationLibrary.get_bone_pose_for_frame(anim, bone, 0, True)
                t1 = unreal.AnimationLibrary.get_bone_pose_for_frame(anim, bone, max(1, f // 2), True)
                d = t1.rotation.euler() - t0.rotation.euler()
                dmax = round(max(abs(d.x), abs(d.y), abs(d.z)), 1)
                if dmax > 0.5:
                    moved_any = True
                    entry[bone] = "%s deg" % dmax
            except Exception:
                pass
        entry["MOVES"] = moved_any
        checks.append(entry)
    res["anim_checks"] = checks
    res["ok"] = bool(anims) and any(c.get("MOVES") for c in checks)
except Exception as e:
    import traceback
    res["error"] = str(e)
    res["traceback"] = traceback.format_exc()

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    json.dump(res, f, indent=2)
unreal.log("WALK_IMPORT_DONE ok=%s -> %s" % (res["ok"], OUT))
