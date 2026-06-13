"""Headless verification render (Workbench, works on Windows + Linux).

Renders a mesh and, optionally, its skeleton drawn as solid bone geometry so an
LLM can see bone-vs-mesh alignment. Uses an orthographic camera for clean
front/side/threeq views. No lights needed (FLAT workbench shading).

Args JSON: {"file": path, "out_dir": dir, "show_bones": bool,
            "views": ["front","side","threeq"], "res": 900, "xray": bool}

Emits the list of written PNG paths in a RIGGS_RESULT block.
"""
import json
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector, Matrix

RESULT_BEGIN = "RIGGS_RESULT_BEGIN"
RESULT_END = "RIGGS_RESULT_END"


def get_args():
    argv = sys.argv
    if "--" in argv:
        return json.loads(argv[argv.index("--") + 1])
    return {}


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise ValueError(f"unsupported extension: {ext}")


def scene_bbox(objs):
    mins = Vector((1e18, 1e18, 1e18))
    maxs = Vector((-1e18, -1e18, -1e18))
    for o in objs:
        for corner in o.bound_box:
            wc = o.matrix_world @ Vector(corner)
            for i in range(3):
                mins[i] = min(mins[i], wc[i])
                maxs[i] = max(maxs[i], wc[i])
    center = (mins + maxs) / 2
    size = maxs - mins
    return center, size


def build_bone_viz(armatures, radius):
    """Create one mesh object of cones along every bone (world space)."""
    bm = bmesh.new()
    z = Vector((0, 0, 1))
    for arm in armatures:
        mw = arm.matrix_world
        for bone in arm.data.bones:
            p0 = mw @ bone.head_local
            p1 = mw @ bone.tail_local
            vec = p1 - p0
            length = vec.length
            if length < 1e-6:
                continue
            ret = bmesh.ops.create_cone(
                bm, cap_ends=True, segments=6, radius1=radius, radius2=radius * 0.25, depth=length
            )
            quat = z.rotation_difference(vec.normalized())
            mat = Matrix.Translation((p0 + p1) / 2) @ quat.to_matrix().to_4x4()
            bmesh.ops.transform(bm, matrix=mat, verts=ret["verts"])
    me = bpy.data.meshes.new("bone_viz")
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("bone_viz", me)
    bpy.context.scene.collection.objects.link(obj)
    obj.color = (1.0, 0.1, 0.1, 1.0)
    return obj


def setup_camera(center, size, view):
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_obj = bpy.data.objects.new("cam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    dist = max(size) * 3 + 1
    if view == "front":  # from -Y looking +Y; frame X (width) x Z (height)
        cam_obj.location = (center.x, center.y - dist, center.z)
        cam_obj.rotation_euler = (math.radians(90), 0, 0)
        cam_data.ortho_scale = max(size.x, size.z) * 1.15
    elif view == "side":  # from +X looking -X; frame Y x Z
        cam_obj.location = (center.x + dist, center.y, center.z)
        cam_obj.rotation_euler = (math.radians(90), 0, math.radians(90))
        cam_data.ortho_scale = max(size.y, size.z) * 1.15
    elif view == "threeq":  # 3/4 front-left
        cam_obj.location = (center.x - dist * 0.7, center.y - dist * 0.7, center.z + size.z * 0.15)
        cam_obj.rotation_euler = (math.radians(78), 0, math.radians(-45))
        cam_data.ortho_scale = max(size) * 1.25
    return cam_obj


def main():
    args = get_args()
    path = args["file"]
    out_dir = args.get("out_dir", os.path.dirname(path))
    views = args.get("views", ["front", "side"])
    show_bones = args.get("show_bones", False)
    res = int(args.get("res", 900))
    xray = args.get("xray", show_bones)
    os.makedirs(out_dir, exist_ok=True)

    result = {"ok": False, "file": path, "written": []}
    try:
        reset_scene()
        import_file(path)

        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
        armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
        center, size = scene_bbox(meshes or bpy.data.objects)

        for m in meshes:
            m.color = (0.55, 0.57, 0.62, 1.0)
        if show_bones and armatures:
            build_bone_viz(armatures, radius=max(size) * 0.006)

        scene = bpy.context.scene
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "FLAT"
        scene.display.shading.color_type = "OBJECT"
        scene.display.shading.show_xray = bool(xray)
        scene.display.shading.xray_alpha = 0.55
        scene.render.film_transparent = False
        scene.render.resolution_x = res
        scene.render.resolution_y = res
        scene.render.image_settings.file_format = "PNG"

        base = os.path.splitext(os.path.basename(path))[0]
        tag = "_rig" if show_bones else ""
        for view in views:
            # remove any prior camera
            for c in [o for o in bpy.data.objects if o.type == "CAMERA"]:
                bpy.data.objects.remove(c, do_unlink=True)
            setup_camera(center, size, view)
            fp = os.path.join(out_dir, f"{base}{tag}_{view}.png")
            scene.render.filepath = fp
            bpy.ops.render.render(write_still=True)
            result["written"].append(fp)

        result["ok"] = True
        result["mesh_count"] = len(meshes)
        result["armature_count"] = len(armatures)
    except Exception as e:
        import traceback
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()

    print(RESULT_BEGIN)
    print(json.dumps(result))
    print(RESULT_END)


if __name__ == "__main__":
    main()
