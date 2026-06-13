"""UE-side probe: confirm headless Python works and the Mannequin assets exist."""
import json
import unreal

res = {"ok": True, "engine": unreal.SystemLibrary.get_engine_version()}
paths = [
    "/Game/Mannequin/Character/Mesh/UE4_Mannequin_Skeleton",
    "/Game/Mannequin/Character/Mesh/SK_Mannequin",
    "/Game/Mannequin/Animations/ThirdPersonRun",
    "/Game/Mannequin/Animations/ThirdPersonWalk",
    "/Game/Mannequin/Animations/ThirdPersonIdle",
]
res["assets"] = {p: unreal.EditorAssetLibrary.does_asset_exist(p) for p in paths}

print("RIGGS_RESULT_BEGIN")
print(json.dumps(res))
print("RIGGS_RESULT_END")
