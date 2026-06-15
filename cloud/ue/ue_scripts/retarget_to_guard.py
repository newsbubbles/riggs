"""Retarget the UE Mannequin's stock anims onto the riggs Guard via an IK Retargeter.

The Guard's skeleton is Mannequin-NAMED but Mixamo-ORIENTED (canonicalize only renames
bones, it doesn't re-orient them), so a DIRECT bind plays Mannequin anims around the wrong
local axes and mangles the mesh. The fix is the IK Retargeter, which retargets in pose space
and is robust to the orientation (and T-pose-vs-A-pose) gap. The Mannequin naming exists
precisely so the chain mapping is trivial.

Run LIVE in an open editor (Cmd box):  py D:/riggs/cloud/ue/ue_scripts/retarget_to_guard.py
Writes a structured result to D:/riggs/out/retarget_result.json.
"""
import json
import os
import unreal

OUT = "D:/riggs/out/retarget_result.json"
FBX = "D:/riggs/examples/Guard_UE.fbx"
DEST = "/Game/RiggsTest"
GUARD_NAME = "SK_GuardRiggs_Own"            # own-skeleton import (keeps the broken bound one separate)
MANNY_MESH = "/Game/Mannequin/Character/Mesh/SK_Mannequin"
ANIMS = [
    "/Game/Mannequin/Animations/ThirdPersonIdle",
    "/Game/Mannequin/Animations/ThirdPersonWalk",
    "/Game/Mannequin/Animations/ThirdPersonRun",
]
# UE4 Mannequin chains; identical bone names on both skeletons => trivial mapping.
CHAINS = [
    ("Spine", "spine_01", "spine_03"),
    ("Neck", "neck_01", "neck_01"),
    ("Head", "head", "head"),
    ("LeftArm", "clavicle_l", "hand_l"),
    ("RightArm", "clavicle_r", "hand_r"),
    ("LeftLeg", "thigh_l", "ball_l"),
    ("RightLeg", "thigh_r", "ball_r"),
    ("Root", "root", "root"),
]

res = {"ok": False, "steps": []}


def log(m):
    res["steps"].append(m)
    unreal.log("RTG: " + m)


def first_attr(obj, names, *args):
    """Call the first method on obj whose name exists (API drifts across UE versions)."""
    for n in names:
        fn = getattr(obj, n, None)
        if callable(fn):
            return fn(*args)
    raise AttributeError("none of %s on %s" % (names, type(obj).__name__))


# Force legacy FBX importer (Interchange's progress UI asserts on Slate when not in a window).
try:
    unreal.SystemLibrary.execute_console_command(None, "Interchange.FeatureFlags.Import.FBX 0")
except Exception as e:
    log("cvar fail: " + str(e))

try:
    atools = unreal.AssetToolsHelpers.get_asset_tools()

    # When launched via GUI -ExecCmds at startup, make sure the asset registry has
    # finished its initial scan before we load/create assets.
    try:
        unreal.AssetRegistryHelpers.get_asset_registry().wait_for_completion()
    except Exception as e:
        log("registry wait skipped: " + str(e)[:80])

    # --- 1. import the Guard on its OWN skeleton (Skeleton = None) ---
    opts = unreal.FbxImportUI()
    opts.set_editor_property("import_mesh", True)
    opts.set_editor_property("import_as_skeletal", True)
    opts.set_editor_property("import_animations", False)
    opts.set_editor_property("import_materials", False)
    opts.set_editor_property("import_textures", False)
    opts.set_editor_property("create_physics_asset", False)
    opts.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    smid = opts.get_editor_property("skeletal_mesh_import_data")
    # The Blender FBX export already writes cm (UnitScaleFactor), so UE reads this
    # FBX at ~184cm with scale=1.0. Importing at 100 makes the Guard ~194 METERS,
    # which is what wrecked the retarget. Scale must be 1.0 for the own-skeleton import.
    smid.set_editor_property("import_uniform_scale", 1.0)
    smid.set_editor_property("convert_scene", True)
    smid.set_editor_property("use_t0_as_ref_pose", True)

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", FBX)
    task.set_editor_property("destination_path", DEST)
    task.set_editor_property("destination_name", GUARD_NAME)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    task.set_editor_property("options", opts)
    atools.import_asset_tasks([task])

    guard_mesh = unreal.load_asset("%s/%s" % (DEST, GUARD_NAME))
    if not guard_mesh:
        raise RuntimeError("Guard import produced no asset")
    guard_skel = guard_mesh.get_editor_property("skeleton")
    log("imported Guard own-skel: " + guard_skel.get_path_name())

    manny_mesh = unreal.load_asset(MANNY_MESH)
    if not manny_mesh:
        raise RuntimeError("Mannequin mesh missing: " + MANNY_MESH)

    # --- 2. build an IK Rig for each (same chain names on both) ---
    def make_ik_rig(name, mesh):
        path = "%s/%s" % (DEST, name)
        rig = atools.create_asset(name, DEST, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())
        if rig is None:
            rig = unreal.load_asset(path)
        if rig is None:
            raise RuntimeError("could not create/load IK rig " + path)
        ctrl = first_attr(unreal.IKRigController, ["get_controller", "get_ik_rig_controller"], rig)
        first_attr(ctrl, ["set_skeletal_mesh"], mesh)
        try:
            first_attr(ctrl, ["set_retarget_root", "set_retarget_root_bone"], "pelvis")
        except Exception as e:
            log("%s set root fail: %s" % (name, e))
        added = 0
        for cn, s, e in CHAINS:
            try:
                ctrl.add_retarget_chain(cn, s, e, "None")
                added += 1
            except Exception as ex:
                try:
                    ctrl.add_retarget_chain(unreal.BoneChain(chain_name=cn, start_bone=s, end_bone=e))
                    added += 1
                except Exception as ex2:
                    log("%s chain %s fail: %s" % (name, cn, ex2))
        unreal.EditorAssetLibrary.save_loaded_asset(rig)
        log("%s: %d/%d chains" % (name, added, len(CHAINS)))
        return rig

    guard_rig = make_ik_rig("IK_GuardRiggs", guard_mesh)
    manny_rig = make_ik_rig("IK_MannyUE4", manny_mesh)

    # --- 3. build the IK Retargeter (Manny -> Guard) ---
    rtg_path = "%s/RTG_Manny_to_Guard" % DEST
    rtg = atools.create_asset("RTG_Manny_to_Guard", DEST, unreal.IKRetargeter, unreal.IKRetargetFactory())
    if rtg is None:
        rtg = unreal.load_asset(rtg_path)
    rc = first_attr(unreal.IKRetargeterController, ["get_controller", "get_ik_retargeter_controller"], rtg)
    try:
        rc.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, manny_rig)
        rc.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, guard_rig)
    except Exception as e:
        # older API: set_source_ik_rig / set_target_ik_rig
        first_attr(rc, ["set_source_ik_rig"], manny_rig)
        first_attr(rc, ["set_target_ik_rig"], guard_rig)
        log("used source/target setter fallback (%s)" % e)

    # CRITICAL: map source chains -> target chains. Without this the retargeter has
    # nothing to drive and bakes the rest pose every frame (frozen). Both rigs use
    # identical Mannequin chain names, so EXACT auto-map connects them 1:1.
    mapped = False
    for mt in ("EXACT", "FUZZY"):
        try:
            rc.auto_map_chains(getattr(unreal.AutoMapChainType, mt), True)
            log("auto_map_chains %s ok" % mt)
            mapped = True
            break
        except Exception as e:
            log("auto_map_chains %s failed: %s" % (mt, str(e)[:80]))
    if not mapped:
        log("WARNING: no chain mapping applied")
    try:
        rc.auto_align_all_bones() if hasattr(rc, "auto_align_all_bones") else None
    except Exception:
        pass
    unreal.EditorAssetLibrary.save_loaded_asset(rtg)
    log("retargeter built")

    # --- 4. bake the stock anims onto the Guard ---
    # duplicate_and_retarget wants Array<AssetData>, NOT loaded AnimSequence objects.
    anims = [unreal.EditorAssetLibrary.find_asset_data(a)
             for a in ANIMS if unreal.EditorAssetLibrary.does_asset_exist(a)]
    new_assets = unreal.IKRetargetBatchOperation.duplicate_and_retarget(
        anims, manny_mesh, guard_mesh, rtg, "", "", "Guard_", "", True)
    log("baked %d anims" % len(new_assets or []))

    # --- diagnostics: dump REAL bone transforms to find WHY it deforms (loc + SCALE) ---
    NAMES = ["Guard_ThirdPersonIdle", "Guard_ThirdPersonWalk", "Guard_ThirdPersonRun"]

    def find_anim(nm):
        for p in ("%s/%s" % (DEST, nm), "/Game/%s" % nm):
            if unreal.EditorAssetLibrary.does_asset_exist(p):
                return p, unreal.load_asset(p)
        return None, None

    def xf(anim, bone, frame):
        t = unreal.AnimationLibrary.get_bone_pose_for_frame(anim, bone, frame, True)
        l, s, r = t.translation, t.scale3d, t.rotation.euler()
        return {"loc": [round(l.x, 1), round(l.y, 1), round(l.z, 1)],
                "scale": [round(s.x, 3), round(s.y, 3), round(s.z, 3)],
                "rot": [round(r.x, 1), round(r.y, 1), round(r.z, 1)]}

    checks = []
    for nm in NAMES:
        p, anim = find_anim(nm)
        if not anim:
            checks.append({"anim": nm, "missing": True})
            continue
        ask = anim.get_editor_property("skeleton")
        f = unreal.AnimationLibrary.get_num_frames(anim)
        mid = max(1, f // 2)
        entry = {"anim": p, "frames": f,
                 "on_guard_skel": bool(ask and ask.get_path_name() == guard_skel.get_path_name())}
        for bone in ("root", "pelvis", "thigh_l"):
            try:
                entry[bone] = {"f0": xf(anim, bone, 0), "mid": xf(anim, bone, mid)}
            except Exception as e:
                entry[bone] = "err: " + str(e)[:60]
        # save + relocate into RiggsTest
        try:
            unreal.EditorAssetLibrary.save_loaded_asset(anim)
            if p.startswith("/Game/%s" % nm):
                unreal.EditorAssetLibrary.rename_asset(p, "%s/%s" % (DEST, nm))
        except Exception as e:
            entry["save_err"] = str(e)[:80]
        checks.append(entry)

    # source Mannequin walk, same bones, for a direct ratio comparison
    src = unreal.load_asset("/Game/Mannequin/Animations/ThirdPersonWalk")
    if src:
        try:
            fm = unreal.AnimationLibrary.get_num_frames(src)
            res["manny_walk"] = {b: xf(src, b, max(1, fm // 2)) for b in ("root", "pelvis", "thigh_l")}
        except Exception as e:
            res["manny_err"] = str(e)[:80]

    res["checks"] = checks
    res["ok"] = any(not c.get("missing") for c in checks)
except Exception as e:
    import traceback
    res["error"] = str(e)
    res["traceback"] = traceback.format_exc()

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    json.dump(res, f, indent=2)
unreal.log("RTG_DONE ok=%s -> %s" % (res["ok"], OUT))
