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

# SOMA (BVH joint) -> Mixamo (without prefix)
MAP = {
    "Hips": "Hips",
    "Spine1": "Spine", "Spine2": "Spine1", "Chest": "Spine2",
    "Neck1": "Neck", "Head": "Head",
    "LeftLeg": "LeftUpLeg", "LeftShin": "LeftLeg", "LeftFoot": "LeftFoot", "LeftToeBase": "LeftToeBase",
    "RightLeg": "RightUpLeg", "RightShin": "RightLeg", "RightFoot": "RightFoot", "RightToeBase": "RightToeBase",
}
for s in ("Left", "Right"):
    MAP[f"{s}Shoulder"] = f"{s}Shoulder"
    MAP[f"{s}Arm"] = f"{s}Arm"
    MAP[f"{s}ForeArm"] = f"{s}ForeArm"
    MAP[f"{s}Hand"] = f"{s}Hand"
    for f in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
        for n in (1, 2, 3):
            MAP[f"{s}Hand{f}{n}"] = f"{s}Hand{f}{n}"


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

        # resolve mapped pairs that exist in both rigs
        pairs = []
        for sj, mj in MAP.items():
            sb = src.pose.bones.get(sj)
            tb = tgt.pose.bones.get(P + mj) or tgt.pose.bones.get(mj)
            if sb and tb:
                pairs.append((sb, tb))
        pairs.sort(key=lambda st: depth(st[1]))  # parents first

        s_hip = src.pose.bones.get("Hips")
        t_hip = tgt.pose.bones.get(P + "Hips") or tgt.pose.bones.get("Hips")

        # Align the source armature's WORLD frame to the target's (BVH and FBX import with
        # different up/forward axes). Use the hips rest orientation as the global correction.
        s_hips_w = (src.matrix_world @ s_hip.bone.matrix_local).to_3x3()
        t_hips_w = (tgt.matrix_world @ t_hip.bone.matrix_local).to_3x3()
        align = (t_hips_w @ s_hips_w.inverted()).to_4x4()
        src.matrix_world = align @ src.matrix_world
        bpy.context.view_layer.update()

        # rest world rotations (3x3), captured after alignment
        s_rest = {sb.name: (src.matrix_world @ sb.bone.matrix_local).to_3x3() for sb, _ in pairs}
        t_rest = {tb.name: (tgt.matrix_world @ tb.bone.matrix_local).to_3x3() for _, tb in pairs}
        tw_inv = tgt.matrix_world.inverted()

        bpy.context.view_layer.objects.active = tgt
        bpy.ops.object.mode_set(mode="POSE")
        for _, tb in pairs:
            tb.rotation_mode = "QUATERNION"

        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            for sb, tb in pairs:
                s_cur = (src.matrix_world @ sb.matrix).to_3x3()
                d_w = s_cur @ s_rest[sb.name].inverted()        # source world-space delta from rest
                desired_w = (d_w @ t_rest[tb.name]).to_4x4()    # target's desired WORLD rotation
                cur_w = tgt.matrix_world @ tb.matrix            # keep the bone's current world position
                desired_w.translation = cur_w.translation
                tb.matrix = tw_inv @ desired_w                  # convert WORLD -> armature space
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
