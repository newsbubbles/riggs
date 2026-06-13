"""Numeric probe for the SOMA->Mixamo retarget. Prints bone world-direction vectors
(source rest vs animated, target rest vs applied) for a couple of bones at one frame,
to pinpoint why motion under-transfers. Mirrors retarget_motion.py's math exactly.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

RESULT_BEGIN = "RIGGS_RESULT_BEGIN"
RESULT_END = "RIGGS_RESULT_END"
P = "mixamorig:"
PROBE = [("LeftArm", "LeftArm"), ("LeftLeg", "LeftUpLeg"), ("LeftShin", "LeftLeg")]


def get_args():
    a = sys.argv
    return json.loads(a[a.index("--") + 1]) if "--" in a else {}


def imp(path):
    e = os.path.splitext(path)[1].lower()
    if e == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif e == ".bvh":
        bpy.ops.import_anim.bvh(filepath=path, use_fps_scale=False, update_scene_fps=True)


def wdir(mat3):
    return (mat3 @ Vector((0, 1, 0))).normalized()  # bone points along its local +Y


def ang(a, b):
    return round(math.degrees(a.angle(b)), 1)


def main():
    args = get_args()
    out = {"ok": False}
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        imp(args["target"])
        tgt = next(o for o in bpy.data.objects if o.type == "ARMATURE")
        before = set(o.name for o in bpy.data.objects)
        imp(args["bvh"])
        src = next(o for o in bpy.data.objects if o.type == "ARMATURE" and o.name not in before)
        scene = bpy.context.scene
        fmid = (scene.frame_start + scene.frame_end) // 2

        s_hip = src.pose.bones["Hips"]; t_hip = tgt.pose.bones.get(P + "Hips") or tgt.pose.bones["Hips"]
        s_hips_w = (src.matrix_world @ s_hip.bone.matrix_local).to_3x3()
        t_hips_w = (tgt.matrix_world @ t_hip.bone.matrix_local).to_3x3()
        align = (t_hips_w @ s_hips_w.inverted()).to_4x4()
        src.matrix_world = align @ src.matrix_world
        bpy.context.view_layer.update()

        rep = {"fmid": fmid, "bones": {}}
        for sj, mj in PROBE:
            sb = src.pose.bones.get(sj); tb = tgt.pose.bones.get(P + mj) or tgt.pose.bones.get(mj)
            if not sb or not tb:
                rep["bones"][sj] = "missing"
                continue
            s_rest = (src.matrix_world @ sb.bone.matrix_local).to_3x3()
            t_rest = (tgt.matrix_world @ tb.bone.matrix_local).to_3x3()
            scene.frame_set(fmid)
            s_cur = (src.matrix_world @ sb.matrix).to_3x3()
            d_w = s_cur @ s_rest.inverted()
            desired = d_w @ t_rest
            rep["bones"][sj] = {
                "src_rest_dir": [round(v, 2) for v in wdir(s_rest)],
                "src_anim_dir": [round(v, 2) for v in wdir(s_cur)],
                "src_moved_deg": ang(wdir(s_rest), wdir(s_cur)),
                "tgt_rest_dir": [round(v, 2) for v in wdir(t_rest)],
                "tgt_desired_dir": [round(v, 2) for v in wdir(desired)],
                "tgt_would_move_deg": ang(wdir(t_rest), wdir(desired)),
            }
        out.update({"ok": True, **rep})
    except Exception as e:
        import traceback
        out["error"] = str(e); out["traceback"] = traceback.format_exc()
    print(RESULT_BEGIN); print(json.dumps(out)); print(RESULT_END)


if __name__ == "__main__":
    main()
