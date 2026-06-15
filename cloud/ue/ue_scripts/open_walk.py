"""Open the imported SK_GuardWalk_Anim in Persona, framed, looping the walk."""
import unreal

aes = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem)
anim = unreal.load_asset("/Game/RiggsWalk/SK_GuardWalk_Anim")
mesh = unreal.load_asset("/Game/RiggsWalk/SK_GuardWalk")
if anim:
    aes.open_editor_for_assets([anim])
elif mesh:
    aes.open_editor_for_assets([mesh])
unreal.log("OPEN_WALK done")
