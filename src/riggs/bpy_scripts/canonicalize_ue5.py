"""Canonicalize a Mixamo-rigged FBX into a UE Mannequin-named, UE-ready FBX.

Steps (all headless bpy):
  1. import the Mixamo-rigged mesh
  2. normalize vertex weights to sum=1.0 and clamp to <=4 influences
  3. rename bones Mixamo -> UE Mannequin (and the matching vertex groups)
  4. add a `root` bone at origin (parent of pelvis) + the ik_ bones UE expects
  5. scale to centimeters (UE native) if the mesh is in meters
  6. export FBX with UE-correct settings (add_leaf_bones off)

Target naming is the UE4 Mannequin set (3 spine / 1 neck), which matches the
datastorm SK_Mannequin. UE5's IK Retargeter handles the rest via auto-characterization.

Args JSON: {"file": in.fbx, "output": out.fbx}
"""
import json
import os
import sys

import bpy
from mathutils import Vector

RESULT_BEGIN = "RIGGS_RESULT_BEGIN"
RESULT_END = "RIGGS_RESULT_END"
M = "mixamorig:"

# Mixamo -> UE Mannequin bone map
MAP = {
    f"{M}Hips": "pelvis",
    f"{M}Spine": "spine_01", f"{M}Spine1": "spine_02", f"{M}Spine2": "spine_03",
    f"{M}Neck": "neck_01", f"{M}Head": "head",
}
for side, s in (("Left", "_l"), ("Right", "_r")):
    MAP[f"{M}{side}Shoulder"] = f"clavicle{s}"
    MAP[f"{M}{side}Arm"] = f"upperarm{s}"
    MAP[f"{M}{side}ForeArm"] = f"lowerarm{s}"
    MAP[f"{M}{side}Hand"] = f"hand{s}"
    MAP[f"{M}{side}UpLeg"] = f"thigh{s}"
    MAP[f"{M}{side}Leg"] = f"calf{s}"
    MAP[f"{M}{side}Foot"] = f"foot{s}"
    MAP[f"{M}{side}ToeBase"] = f"ball{s}"
    for finger, ue in (("Thumb", "thumb"), ("Index", "index"), ("Middle", "middle"),
                       ("Ring", "ring"), ("Pinky", "pinky")):
        for n in (1, 2, 3):
            MAP[f"{M}{side}Hand{finger}{n}"] = f"{ue}_0{n}{s}"


def get_args():
    argv = sys.argv
    return json.loads(argv[argv.index("--") + 1]) if "--" in argv else {}


def main():
    args = get_args()
    path, out = args["file"], args["output"]
    result = {"ok": False, "file": path, "output": out}
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=path)

        arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]

        # --- 2. normalize + clamp weights ---
        for m in meshes:
            bpy.ops.object.select_all(action="DESELECT")
            m.select_set(True)
            bpy.context.view_layer.objects.active = m
            if m.vertex_groups:
                bpy.ops.object.vertex_group_normalize_all(lock_active=False)
                bpy.ops.object.vertex_group_limit_total(limit=4)
                bpy.ops.object.vertex_group_normalize_all(lock_active=False)

        # --- 3. rename bones + matching vertex groups ---
        renamed = 0
        unmapped = []
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        for eb in arm.data.edit_bones:
            if eb.name in MAP:
                eb.name = MAP[eb.name]
                renamed += 1
            elif eb.name.startswith(M):
                unmapped.append(eb.name)
        bpy.ops.object.mode_set(mode="OBJECT")
        for m in meshes:
            for old, new in MAP.items():
                vg = m.vertex_groups.get(old)
                if vg:
                    vg.name = new

        # --- 4. add root + ik_ bones ---
        bpy.ops.object.mode_set(mode="EDIT")
        ebs = arm.data.edit_bones

        def head_of(name):
            b = ebs.get(name)
            return b.head.copy() if b else Vector((0, 0, 0))

        def mkbone(name, head, tail, parent=None):
            b = ebs.new(name)
            b.head, b.tail = head, tail
            b.use_deform = False
            if parent:
                b.parent = ebs.get(parent)
            return b

        up = Vector((0, 0, 0.1))
        root = mkbone("root", Vector((0, 0, 0)), Vector((0, 0.1, 0)))
        if ebs.get("pelvis"):
            ebs["pelvis"].parent = root
        mkbone("ik_foot_root", Vector((0, 0, 0)), up, "root")
        mkbone("ik_foot_l", head_of("foot_l"), head_of("foot_l") + up, "ik_foot_root")
        mkbone("ik_foot_r", head_of("foot_r"), head_of("foot_r") + up, "ik_foot_root")
        mkbone("ik_hand_root", Vector((0, 0, 0)), up, "root")
        mkbone("ik_hand_gun", head_of("hand_r"), head_of("hand_r") + up, "ik_hand_root")
        mkbone("ik_hand_l", head_of("hand_l"), head_of("hand_l") + up, "ik_hand_gun")
        mkbone("ik_hand_r", head_of("hand_r"), head_of("hand_r") + up, "ik_hand_gun")
        bpy.ops.object.mode_set(mode="OBJECT")

        # --- 5. orientation/scale notes ---
        # Leave the mesh Y-up (Mixamo/MIA native) and in meters. This is a standard
        # FBX: UE's importer converts Y-up -> its Z-up automatically, and you set UE
        # import "Uniform Scale" = 100 (meters -> cm). Don't rotate the rigged mesh in
        # Blender here — baking a rotation across an armature+skin bind is error-prone.
        dim = max(max(m.dimensions) for m in meshes)
        scaled = False

        # --- 6. export UE-ready FBX ---
        bpy.ops.object.select_all(action="DESELECT")
        arm.select_set(True)
        for m in meshes:
            m.select_set(True)
        bpy.context.view_layer.objects.active = arm
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        bpy.ops.export_scene.fbx(
            filepath=out, use_selection=True, object_types={"ARMATURE", "MESH"},
            add_leaf_bones=False, bake_anim=False, mesh_smooth_type="FACE",
            use_armature_deform_only=False, primary_bone_axis="Y", secondary_bone_axis="X",
            apply_scale_options="FBX_SCALE_NONE", global_scale=1.0,
            # default axis (-Z fwd / Y up) -> standard FBX that round-trips and that
            # UE's importer converts to its Z-up automatically. UE import scale = 100.
        )

        result.update({"ok": True, "bones_renamed": renamed, "unmapped_bones": unmapped,
                       "scaled_to_cm": scaled, "final_longest_axis": round(dim * (100 if scaled else 1), 1)})
    except Exception as e:
        import traceback
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()

    print(RESULT_BEGIN)
    print(json.dumps(result))
    print(RESULT_END)


if __name__ == "__main__":
    main()
