"""Retarget a Kimodo SOMA BVH onto the riggs Mixamo rig, bake, export, preview.

Both skeletons are T-pose but have different per-bone axes, so a naive world-space
copy of rotations twists. We transfer each source bone's world-space rotation DELTA
(relative to its own rest) onto the target bone's rest orientation, per frame, and
bake to keyframes. Hips also get (scaled) root translation.

Args JSON: {"target": Guard_mia.fbx, "bvh": clip.bvh, "output": out.fbx,
            "out_dir": preview dir, "name": "walk", "preview_frames": 4}
"""
import json
import os
import sys

import bpy
from mathutils import Matrix, Vector

RESULT_BEGIN = "RIGGS_RESULT_BEGIN"
RESULT_END = "RIGGS_RESULT_END"
P = "mixamorig:"

# Target is always our Mixamo rig (mixamorig: bones). Each source preset maps a
# SOURCE bone name -> Mixamo target bone name (without the prefix). Pick with
# args["source"] in {"soma","mixamo","mannequin"} (default "soma").

def _mixamo_bones():
    names = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head"]
    for s in ("Left", "Right"):
        names += [f"{s}Shoulder", f"{s}Arm", f"{s}ForeArm", f"{s}Hand",
                  f"{s}UpLeg", f"{s}Leg", f"{s}Foot", f"{s}ToeBase"]
        for f in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
            names += [f"{s}Hand{f}{n}" for n in (1, 2, 3)]
    return names


def _soma_map():
    m = {"Hips": "Hips", "Spine1": "Spine", "Spine2": "Spine1", "Chest": "Spine2",
         "Neck1": "Neck", "Head": "Head"}
    for s in ("Left", "Right"):
        m[f"{s}Leg"] = f"{s}UpLeg"; m[f"{s}Shin"] = f"{s}Leg"
        m[f"{s}Foot"] = f"{s}Foot"; m[f"{s}ToeBase"] = f"{s}ToeBase"
        m[f"{s}Shoulder"] = f"{s}Shoulder"; m[f"{s}Arm"] = f"{s}Arm"
        m[f"{s}ForeArm"] = f"{s}ForeArm"; m[f"{s}Hand"] = f"{s}Hand"
        for f in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
            for n in (1, 2, 3):
                m[f"{s}Hand{f}{n}"] = f"{s}Hand{f}{n}"
    return m


def _mixamo_map():  # source is already a Mixamo skeleton -> identity (handles rest-pose diffs)
    return {f"mixamorig:{b}": b for b in _mixamo_bones()}


def _mannequin_map():  # UE4 Mannequin / SK_Mannequin (3 spine) -> Mixamo
    m = {"pelvis": "Hips", "spine_01": "Spine", "spine_02": "Spine1", "spine_03": "Spine2",
         "neck_01": "Neck", "head": "Head"}
    for u, s in (("l", "Left"), ("r", "Right")):
        m[f"clavicle_{u}"] = f"{s}Shoulder"; m[f"upperarm_{u}"] = f"{s}Arm"
        m[f"lowerarm_{u}"] = f"{s}ForeArm"; m[f"hand_{u}"] = f"{s}Hand"
        m[f"thigh_{u}"] = f"{s}UpLeg"; m[f"calf_{u}"] = f"{s}Leg"
        m[f"foot_{u}"] = f"{s}Foot"; m[f"ball_{u}"] = f"{s}ToeBase"
        for uf, mf in (("thumb", "Thumb"), ("index", "Index"), ("middle", "Middle"),
                       ("ring", "Ring"), ("pinky", "Pinky")):
            for n in (1, 2, 3):
                m[f"{uf}_0{n}_{u}"] = f"{s}Hand{mf}{n}"
    return m


SOURCE_MAPS = {"soma": _soma_map(), "mixamo": _mixamo_map(), "mannequin": _mannequin_map()}
SRC_HIP = {"soma": "Hips", "mixamo": "mixamorig:Hips", "mannequin": "pelvis"}


def get_args():
    argv = sys.argv
    return json.loads(argv[argv.index("--") + 1]) if "--" in argv else {}


def import_any(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".bvh":
        bpy.ops.import_anim.bvh(filepath=path, use_fps_scale=False, update_scene_fps=True)


def depth(pbone):
    d = 0
    b = pbone.parent
    while b:
        d += 1
        b = b.parent
    return d


def main():
    args = get_args()
    result = {"ok": False, "name": args.get("name")}
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)

        import_any(args["target"])
        tgt = next(o for o in bpy.data.objects if o.type == "ARMATURE")
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]

        before = set(o.name for o in bpy.data.objects)
        import_any(args["bvh"])
        src = next(o for o in bpy.data.objects if o.type == "ARMATURE" and o.name not in before)

        scene = bpy.context.scene
        f0, f1 = scene.frame_start, scene.frame_end

        source = args.get("source", "soma")
        if source not in SOURCE_MAPS:
            raise ValueError(f"source must be one of {list(SOURCE_MAPS)}, got {source!r}")
        amap = SOURCE_MAPS[source]

        # resolve mapped pairs that exist in both rigs
        pairs = []
        for sj, mj in amap.items():
            sb = src.pose.bones.get(sj)
            tb = tgt.pose.bones.get(P + mj) or tgt.pose.bones.get(mj)
            if sb and tb:
                pairs.append((sb, tb))
        pairs.sort(key=lambda st: depth(st[1]))  # parents first
        if not pairs:
            raise RuntimeError(f"no bone pairs matched for source={source!r}; check the source skeleton names")

        s_hip = src.pose.bones.get(SRC_HIP[source])
        t_hip = tgt.pose.bones.get(P + "Hips") or tgt.pose.bones.get("Hips")

        # Align the source armature's WORLD frame to the target's (BVH and FBX import with
        # different up/forward axes). Use the hips rest orientation as the global correction.
        s_hips_w = (src.matrix_world @ s_hip.bone.matrix_local).to_3x3()
        t_hips_w = (tgt.matrix_world @ t_hip.bone.matrix_local).to_3x3()
        align = (t_hips_w @ s_hips_w.inverted()).to_4x4()
        src.matrix_world = align @ src.matrix_world
        bpy.context.view_layer.update()

        # rest world rotations (3x3), captured after alignment
        from mathutils import Matrix
        s_rest = {sb.name: (src.matrix_world @ sb.bone.matrix_local).to_3x3() for sb, _ in pairs}
        t_rest = {tb.name: (tgt.matrix_world @ tb.bone.matrix_local).to_3x3() for _, tb in pairs}

        # nearest mapped target ancestor for each target bone (for analytic local rotation)
        tgt_names = {tb.name for _, tb in pairs}
        parent_of = {}
        for _, tb in pairs:
            a = tb.parent
            while a and a.name not in tgt_names:
                a = a.parent
            parent_of[tb.name] = a.name if a else None

        # clamp to the source animation's real frame range (avoid trailing static frames)
        if src.animation_data and src.animation_data.action:
            a0, a1 = src.animation_data.action.frame_range
            f0, f1 = int(a0), int(a1)
            scene.frame_start, scene.frame_end = f0, f1

        bpy.context.view_layer.objects.active = tgt
        bpy.ops.object.mode_set(mode="POSE")
        for _, tb in pairs:
            tb.rotation_mode = "QUATERNION"
        src_by_tgt = {tb.name: sb for sb, tb in pairs}
        I3 = Matrix.Identity(3)

        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            # desired WORLD rotation per target bone (math only, no Blender state writes)
            r_des = {}
            for sb, tb in pairs:
                d_w = (src.matrix_world @ sb.matrix).to_3x3() @ s_rest[sb.name].inverted()
                r_des[tb.name] = d_w @ t_rest[tb.name]
            # analytic basis: R_basis = R_rest_local^-1 @ R_parent_des^-1 @ R_des  (no staleness)
            for _, tb in pairs:
                par = parent_of[tb.name]
                par_rest = t_rest[par] if par else I3
                par_des = r_des[par] if par else I3
                rest_local = par_rest.inverted() @ t_rest[tb.name]
                basis = rest_local.inverted() @ par_des.inverted() @ r_des[tb.name]
                tb.rotation_quaternion = basis.to_quaternion()
                tb.keyframe_insert("rotation_quaternion", frame=f)

        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.data.objects.remove(src, do_unlink=True)

        # export FBX (Mixamo-named animated rig)
        if args.get("output"):
            bpy.ops.object.select_all(action="DESELECT")
            tgt.select_set(True)
            for m in meshes:
                m.select_set(True)
            bpy.context.view_layer.objects.active = tgt
            bpy.ops.export_scene.fbx(filepath=args["output"], use_selection=True,
                                     add_leaf_bones=False, bake_anim=True,
                                     bake_anim_use_all_bones=True, object_types={"ARMATURE", "MESH"})

        # preview render a few frames (workbench, ortho front)
        written = []
        out_dir = args.get("out_dir")
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            for m in meshes:
                m.color = (0.55, 0.57, 0.62, 1.0)
            scene.render.engine = "BLENDER_WORKBENCH"
            scene.display.shading.light = "FLAT"
            scene.render.resolution_x = scene.render.resolution_y = 640
            scene.render.image_settings.file_format = "PNG"
            # framing
            mins = Vector((1e18,) * 3); maxs = Vector((-1e18,) * 3)
            for o in meshes:
                for c in o.bound_box:
                    w = o.matrix_world @ Vector(c)
                    for i in range(3):
                        mins[i] = min(mins[i], w[i]); maxs[i] = max(maxs[i], w[i])
            center = (mins + maxs) / 2; size = maxs - mins
            cam_d = bpy.data.cameras.new("c"); cam = bpy.data.objects.new("c", cam_d)
            scene.collection.objects.link(cam); scene.camera = cam
            cam_d.type = "ORTHO"; cam_d.ortho_scale = max(size) * 1.3
            import math
            view = args.get("view", "front")
            if view == "side":
                cam.location = (center.x + max(size) * 3, center.y, center.z)
                cam.rotation_euler = (math.radians(90), 0, math.radians(90))
            else:
                cam.location = (center.x, center.y - max(size) * 3, center.z)
                cam.rotation_euler = (math.radians(90), 0, 0)
            n = int(args.get("preview_frames", 4))
            name = args.get("name", "anim")
            for i in range(n):
                fr = int(f0 + (f1 - f0) * (i + 0.5) / n)
                scene.frame_set(fr)
                fp = os.path.join(out_dir, f"{name}_f{fr:03d}.png")
                scene.render.filepath = fp
                bpy.ops.render.render(write_still=True)
                written.append(fp)

        result.update({"ok": True, "frames": [f0, f1], "pairs": len(pairs),
                       "written": written, "output": args.get("output")})
    except Exception as e:
        import traceback
        result["error"] = str(e); result["traceback"] = traceback.format_exc()

    print(RESULT_BEGIN)
    print(json.dumps(result))
    print(RESULT_END)


if __name__ == "__main__":
    main()
