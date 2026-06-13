"""Extract a clean, unrigged base mesh from a (possibly badly-rigged) file.

Removes armatures, armature modifiers, and vertex groups; applies transforms;
recenters so the mesh sits with feet at z=0 and is centred on x/y. Exports
Guard_base.glb and .fbx for use as auto-rigger input.

Args JSON: {"file": path, "out_dir": dir, "name": "Guard_base"}
"""
import json
import os
import sys

import bpy
from mathutils import Vector

RESULT_BEGIN = "RIGGS_RESULT_BEGIN"
RESULT_END = "RIGGS_RESULT_END"


def get_args():
    argv = sys.argv
    if "--" in argv:
        return json.loads(argv[argv.index("--") + 1])
    return {}


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


def world_bbox(objs):
    mins = Vector((1e18, 1e18, 1e18))
    maxs = Vector((-1e18, -1e18, -1e18))
    for o in objs:
        for c in o.bound_box:
            wc = o.matrix_world @ Vector(c)
            for i in range(3):
                mins[i] = min(mins[i], wc[i])
                maxs[i] = max(maxs[i], wc[i])
    return mins, maxs


def main():
    args = get_args()
    path = args["file"]
    out_dir = args.get("out_dir", os.path.dirname(path))
    name = args.get("name", "base")
    os.makedirs(out_dir, exist_ok=True)

    result = {"ok": False, "file": path, "written": []}
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        import_file(path)

        # drop armatures and empties
        for o in [o for o in bpy.data.objects if o.type in ("ARMATURE", "EMPTY")]:
            bpy.data.objects.remove(o, do_unlink=True)

        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
        for m in meshes:
            # remove armature modifiers + vertex groups
            for mod in [md for md in m.modifiers if md.type == "ARMATURE"]:
                m.modifiers.remove(mod)
            m.vertex_groups.clear()
            m.parent = None

        # apply transforms
        bpy.ops.object.select_all(action="DESELECT")
        for m in meshes:
            m.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

        # recenter: feet at z=0, centred on x/y
        mins, maxs = world_bbox(meshes)
        center = (mins + maxs) / 2
        offset = Vector((-center.x, -center.y, -mins.z))
        for m in meshes:
            m.location += offset
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.object.select_all(action="DESELECT")
        for m in meshes:
            m.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

        mins, maxs = world_bbox(meshes)
        dims = maxs - mins

        glb = os.path.join(out_dir, f"{name}.glb")
        fbx = os.path.join(out_dir, f"{name}.fbx")
        bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=False)
        bpy.ops.export_scene.fbx(
            filepath=fbx, use_selection=False, add_leaf_bones=False, bake_anim=False
        )

        result.update(
            {
                "ok": True,
                "mesh_count": len(meshes),
                "total_vertices": sum(len(m.data.vertices) for m in meshes),
                "dimensions_m": [round(d, 4) for d in dims],
                "written": [glb, fbx],
            }
        )
    except Exception as e:
        import traceback
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()

    print(RESULT_BEGIN)
    print(json.dumps(result))
    print(RESULT_END)


if __name__ == "__main__":
    main()
