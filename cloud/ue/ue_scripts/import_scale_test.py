"""Import the riggs Guard FBX as its OWN skeleton several ways and measure the result.

The own-skeleton import comes in tiny + 90deg-rotated (Mixamo meters/Y-up). This sweeps
UE import options (scale / convert_scene / convert_scene_unit / force_front_x_axis) and
reports each variant's resulting mesh full-size in cm, so we can see which combo (if any)
lands at ~183cm tall and upright (Z is the tall axis). If none do, the Blender export needs
the fix instead.

Headless-safe (legacy importer; no Slate). Writes D:/riggs/out/scale_test.json.
"""
import json
import os
import unreal

OUT = "D:/riggs/out/scale_test.json"
FBX = "D:/riggs/examples/Guard_UE.fbx"
DEST = "/Game/ScaleTest"

try:
    unreal.SystemLibrary.execute_console_command(None, "Interchange.FeatureFlags.Import.FBX 0")
except Exception:
    pass

atools = unreal.AssetToolsHelpers.get_asset_tools()

VARIANTS = [
    {"name": "A_s100_conv",    "scale": 100.0, "convert": True,  "front_x": False, "unit": False},
    {"name": "B_s100_noconv",  "scale": 100.0, "convert": False, "front_x": False, "unit": False},
    {"name": "C_s1_conv",      "scale": 1.0,   "convert": True,  "front_x": False, "unit": False},
    {"name": "D_s100_unit",    "scale": 100.0, "convert": True,  "front_x": False, "unit": True},
    {"name": "E_s100_frontx",  "scale": 100.0, "convert": True,  "front_x": True,  "unit": False},
    {"name": "F_s1_unit",      "scale": 1.0,   "convert": True,  "front_x": False, "unit": True},
]

res = {"variants": []}


def build_opts(v):
    o = unreal.FbxImportUI()
    o.set_editor_property("import_mesh", True)
    o.set_editor_property("import_as_skeletal", True)
    o.set_editor_property("import_animations", False)
    o.set_editor_property("import_materials", False)
    o.set_editor_property("import_textures", False)
    o.set_editor_property("create_physics_asset", False)
    o.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    s = o.get_editor_property("skeletal_mesh_import_data")
    s.set_editor_property("import_uniform_scale", v["scale"])
    s.set_editor_property("convert_scene", v["convert"])
    try:
        s.set_editor_property("force_front_x_axis", v["front_x"])
    except Exception:
        pass
    try:
        s.set_editor_property("convert_scene_unit", v["unit"])
    except Exception:
        pass
    s.set_editor_property("use_t0_as_ref_pose", True)
    return o


for v in VARIANTS:
    rec = {"variant": v["name"], "opts": v}
    try:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", FBX)
        t.set_editor_property("destination_path", DEST)
        t.set_editor_property("destination_name", "SK_" + v["name"])
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", False)
        t.set_editor_property("options", build_opts(v))
        atools.import_asset_tasks([t])
        m = unreal.load_asset("%s/SK_%s" % (DEST, v["name"]))
        if not m:
            rec["error"] = "no asset"
        else:
            try:
                b = m.get_bounds()
                e = b.box_extent
                rec["full_size_cm"] = [round(e.x * 2, 1), round(e.y * 2, 1), round(e.z * 2, 1)]
                rec["tall_axis"] = ["X", "Y", "Z"][[e.x, e.y, e.z].index(max(e.x, e.y, e.z))]
                rec["tall_cm"] = round(max(e.x, e.y, e.z) * 2, 1)
            except Exception as ex:
                rec["bounds_err"] = str(ex)[:80]
    except Exception as ex:
        rec["error"] = str(ex)[:140]
    res["variants"].append(rec)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    json.dump(res, f, indent=2)
unreal.log("SCALE_TEST_DONE -> " + OUT)
