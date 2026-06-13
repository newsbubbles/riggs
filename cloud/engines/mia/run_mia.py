"""Headless Make-It-Animatable inference: mesh path -> rigged FBX path.

MIA's pipeline lives in app.py as a Gradio generator `_pipeline`. We load the
models once, drive the generator to completion with no animation file (static
rigged output in the predicted rest pose), then copy `db.anim_path` (the
animatable model MIA exports via its Auto-Rig-Pro fork) to the requested path.

Expected to run inside the MIA image where CWD is the MIA repo root and the
weights live under output/best/new/.
"""
from __future__ import annotations

import os
import shutil
import traceback

_MIA_DIR = os.environ.get("MIA_DIR", "/opt/Make-It-Animatable")

_initialized = False


def _ensure_init():
    global _initialized, app
    if _initialized:
        return
    os.chdir(_MIA_DIR)
    if _MIA_DIR not in os.sys.path:
        os.sys.path.insert(0, _MIA_DIR)
    # gr.Info/gr.Warning are UI toasts that require a live Gradio Blocks context;
    # headless they raise LookupError. No-op them before importing app (which binds
    # them as print_fn). gr.Error stays (it's raised intentionally for real errors).
    import gradio as gr
    gr.Info = lambda *a, **k: None
    gr.Warning = lambda *a, **k: None
    gr.Success = lambda *a, **k: None

    import app as _app  # noqa

    app = _app
    app.init_models()
    # MIA's pipeline stage functions return Gradio-component dicts (e.g. {state: db}).
    # Those component globals only exist when the Gradio UI is built (init_blocks).
    # We run headless and ignore the returns (the real work is the db mutation), so
    # inject harmless placeholders for the referenced globals to avoid NameError.
    for name in ("state", "output_joints_coarse", "output_normed_input", "output_sample",
                 "output_joints", "output_bw", "output_rest_vis", "output_rest_lbs",
                 "output_anim_vis", "output_anim"):
        if not hasattr(app, name):
            setattr(app, name, f"__riggs_{name}")
    _initialized = True


def rig(input_path: str, output_path: str, opts: dict | None = None) -> dict:
    opts = opts or {}
    try:
        _ensure_init()

        # Rigging-only defaults: no animation, keep predicted rest pose.
        # `reset_to_rest`/`rest_pose_type` let the caller force a clean A/T-pose.
        kwargs = dict(
            input_path=input_path,
            is_gs=bool(opts.get("is_gaussian_splat", False)),
            no_fingers=bool(opts.get("no_fingers", False)),
            rest_pose_type=opts.get("rest_pose_type"),  # e.g. "T-pose" / "A-pose" / None
            reset_to_rest=bool(opts.get("reset_to_rest", False)),
            input_normal=bool(opts.get("input_normal", False)),
            bw_fix=bool(opts.get("bw_fix", True)),
            animation_file=opts.get("animation_file"),  # None -> static rigged model
            retarget=bool(opts.get("retarget", True)),
            inplace=bool(opts.get("inplace", True)),
            export_temp=True,
        )

        db = app.DB()
        # _pipeline is a generator yielding Gradio updates; exhaust it.
        for _ in app._pipeline(db=db, **kwargs):
            pass

        produced = getattr(db, "anim_path", None)
        if not produced or not os.path.isfile(produced):
            # fall back to scanning the per-run output dir for an fbx/glb
            out_dir = getattr(db, "output_dir", os.path.join(_MIA_DIR, "output"))
            cand = []
            for root, _, files in os.walk(out_dir):
                for fn in files:
                    if fn.lower().endswith((".fbx", ".glb")):
                        cand.append(os.path.join(root, fn))
            if not cand:
                return {"ok": False, "error": "no rigged output produced",
                        "db_attrs": [a for a in dir(db) if not a.startswith("__")]}
            produced = max(cand, key=os.path.getmtime)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        shutil.copyfile(produced, output_path)
        return {"ok": True, "produced": produced, "output": output_path}
    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}
