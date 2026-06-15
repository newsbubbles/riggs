"""Open the riggs Guard in the UE editor, walking.

Run via the GUI editor (not -Cmd): set the Guard as the preview mesh for the
ThirdPersonWalk anim so Persona auto-loops the walk ON THE GUARD, then open both
the walk anim (to watch it move) and the skeletal mesh editor (to check the
ref-pose deform). Does not save shared assets (preview mesh is session-only).

Launch: UnrealEditor.exe <uproject> -ExecCmds=py D:/riggs/cloud/ue/ue_scripts/open_guard.py
"""
import unreal

GUARD = "/Game/RiggsTest/SK_GuardRiggs"
WALK = "/Game/Mannequin/Animations/ThirdPersonWalk"

guard = unreal.load_asset(GUARD)
walk = unreal.load_asset(WALK)
aes = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem)

notes = []


def tryset(obj, prop, val, label):
    try:
        obj.set_editor_property(prop, val)
        notes.append("set " + label)
        return True
    except Exception as e:
        notes.append("skip " + label + ": " + str(e)[:80])
        return False


if walk and guard:
    # Prefer anim-level preview mesh (only affects this anim's editor view).
    if not any(tryset(walk, p, guard, "walk." + p) for p in ("preview_skeletal_mesh", "preview_mesh")):
        # Fallback: skeleton-level preview mesh, session only (not saved).
        try:
            skel = guard.get_editor_property("skeleton")
            for p in ("preview_skeletal_mesh", "preview_mesh"):
                if tryset(skel, p, guard, "skeleton." + p):
                    break
        except Exception as e:
            notes.append("no skel: " + str(e)[:80])

# Open the walk anim (Persona auto-loops it) and the Guard mesh editor.
if walk:
    aes.open_editor_for_assets([walk])
if guard:
    aes.open_editor_for_assets([guard])

unreal.log("RIGGS_OPEN_GUARD: " + (" | ".join(notes) if notes else "opened"))
