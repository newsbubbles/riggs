"""Headless bpy analysis / validation of a mesh + (optional) rig.

Run via: blender --background --factory-startup --python analyze.py -- '{"file": "..."}'

Emits a JSON report between RIGGS_RESULT_BEGIN / RIGGS_RESULT_END so the
cross-platform runner can parse it. This is the seed of the `validate_rig`
tool: every check returns a discrete, structured fact an LLM can branch on,
no vision required.
"""
import json
import os
import sys

import bpy
import bmesh

RESULT_BEGIN = "RIGGS_RESULT_BEGIN"
RESULT_END = "RIGGS_RESULT_END"
WEIGHT_TOL = 1e-3
ISLAND_VERT_CAP = 300_000  # skip island flood-fill above this to stay fast


def get_args():
    argv = sys.argv
    if "--" in argv:
        raw = argv[argv.index("--") + 1]
        return json.loads(raw)
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


def naming_style(bone_names):
    lowered = [b.lower() for b in bone_names]
    if any(n.startswith("mixamorig") for n in lowered):
        return "mixamo"
    if any(n in ("pelvis", "spine_01", "upperarm_l", "thigh_l") for n in lowered):
        return "ue_mannequin"
    if any(n in ("hips", "leftarm", "leftupleg", "spine1") for n in lowered):
        return "humanik_like"
    return "unknown"


def count_islands(mesh_obj):
    me = mesh_obj.data
    if len(me.vertices) > ISLAND_VERT_CAP:
        return None  # skipped for performance
    bm = bmesh.new()
    bm.from_mesh(me)
    parent = list(range(len(bm.verts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    bm.verts.ensure_lookup_table()
    for e in bm.edges:
        a, b = e.verts[0].index, e.verts[1].index
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    islands = len({find(i) for i in range(len(bm.verts))})
    bm.free()
    return islands


def analyze_armature(arm_obj):
    bones = arm_obj.data.bones
    names = [b.name for b in bones]
    roots = [b.name for b in bones if b.parent is None]
    deform = [b.name for b in bones if b.use_deform]
    ik_bones = [n for n in names if n.lower().startswith("ik_")]
    zero_len = []
    for b in bones:
        if (b.head_local - b.tail_local).length < 1e-5:
            zero_len.append(b.name)
    return {
        "name": arm_obj.name,
        "bone_count": len(bones),
        "root_bones": roots,
        "single_root": len(roots) == 1,
        "deform_bone_count": len(deform),
        "ik_bones": ik_bones,
        "has_ik_bones": len(ik_bones) > 0,
        "naming_style": naming_style(names),
        "zero_length_bones": zero_len,
        "unique_names": len(names) == len(set(names)),
        "sample_bones": names[:40],
    }


def analyze_mesh(mesh_obj, armature_bone_names):
    me = mesh_obj.data
    nverts = len(me.vertices)
    ntris = sum(len(p.vertices) - 2 for p in me.polygons)
    dims = mesh_obj.dimensions
    vgroups = [vg.name for vg in mesh_obj.vertex_groups]

    unweighted = 0
    not_normalized = 0
    max_influences = 0
    weighted_any = 0
    for v in me.vertices:
        nz = [g for g in v.groups if g.weight > 1e-6]
        max_influences = max(max_influences, len(nz))
        total = sum(g.weight for g in nz)
        if total <= 1e-6:
            unweighted += 1
        else:
            weighted_any += 1
            if abs(total - 1.0) > WEIGHT_TOL:
                not_normalized += 1

    # vertex-group <-> deform-bone correspondence
    vg_set = set(vgroups)
    bone_set = set(armature_bone_names)
    groups_without_bone = sorted(vg_set - bone_set) if bone_set else []
    deform_bones_without_group = sorted(bone_set - vg_set) if bone_set else []

    # crude scale sanity: a humanoid in meters ~1.5-2.2; in cm ~150-220
    longest = max(dims)
    if longest < 0.01:
        scale_guess = "tiny (sub-cm, likely wrong)"
    elif longest <= 3.0:
        scale_guess = "meters (Blender native; multiply x100 for UE cm)"
    elif longest <= 300.0:
        scale_guess = "centimeters (UE-ready)"
    else:
        scale_guess = "very large (check units)"

    return {
        "name": mesh_obj.name,
        "vertices": nverts,
        "triangles": ntris,
        "dimensions_m": [round(d, 4) for d in dims],
        "longest_axis": round(longest, 4),
        "scale_guess": scale_guess,
        "islands": count_islands(mesh_obj),
        "vertex_group_count": len(vgroups),
        "unweighted_vertices": unweighted,
        "weighted_vertices": weighted_any,
        "vertices_not_normalized": not_normalized,
        "max_influences_per_vertex": max_influences,
        "groups_without_matching_bone": groups_without_bone[:30],
        "deform_bones_without_group": deform_bones_without_group[:30],
    }


def main():
    args = get_args()
    path = args.get("file")
    result = {"ok": False, "file": path}
    try:
        reset_scene()
        import_file(path)

        armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]

        arm_reports = [analyze_armature(a) for a in armatures]
        all_bone_names = [b.name for a in armatures for b in a.data.bones]
        mesh_reports = [analyze_mesh(m, all_bone_names) for m in meshes]

        result.update(
            {
                "ok": True,
                "object_count": len(bpy.data.objects),
                "armature_count": len(armatures),
                "mesh_count": len(meshes),
                "armatures": arm_reports,
                "meshes": mesh_reports,
                "is_rigged": len(armatures) > 0
                and any(m["vertex_group_count"] > 0 for m in mesh_reports),
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
