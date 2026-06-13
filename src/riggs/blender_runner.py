"""Cross-platform launcher for headless Blender bpy scripts.

Finds a Blender executable (Windows or Linux), runs a bpy script under
`blender --background --python <script> -- <json-args>`, and parses a single
JSON result line the script emits between RIGGS_RESULT markers.

Resolution order for the executable:
  1. $RIGGS_BLENDER env var
  2. `blender` on PATH
  3. common install locations per OS (highest version wins)
"""
from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

RESULT_BEGIN = "RIGGS_RESULT_BEGIN"
RESULT_END = "RIGGS_RESULT_END"


def find_blender() -> str:
    env = os.environ.get("RIGGS_BLENDER")
    if env and Path(env).exists():
        return env

    on_path = shutil.which("blender")
    if on_path:
        return on_path

    candidates: list[str] = []
    system = platform.system()
    if system == "Windows":
        for base in (r"C:\Program Files\Blender Foundation", r"C:\Program Files (x86)\Blender Foundation"):
            candidates += glob.glob(os.path.join(base, "Blender *", "blender.exe"))
    elif system == "Linux":
        candidates += [
            "/usr/bin/blender",
            "/usr/local/bin/blender",
            "/snap/bin/blender",
            os.path.expanduser("~/.local/bin/blender"),
        ]
        candidates += glob.glob("/opt/blender*/blender")
    elif system == "Darwin":
        candidates += glob.glob("/Applications/Blender*.app/Contents/MacOS/Blender")

    existing = [c for c in candidates if Path(c).exists()]
    if not existing:
        raise FileNotFoundError(
            "Could not locate a Blender executable. Set $RIGGS_BLENDER to the full path."
        )
    # Highest version string last when sorted; good enough for typical installs.
    existing.sort()
    return existing[-1]


def run_script(script: str, args: dict | None = None, timeout: int = 600) -> dict:
    """Run a bpy script headless and return the parsed JSON result dict.

    The script must print one line of JSON wrapped in RESULT_BEGIN/RESULT_END.
    """
    blender = find_blender()
    script_path = str(Path(script).resolve())
    payload = json.dumps(args or {})

    cmd = [blender, "--background", "--factory-startup", "--python", script_path, "--", payload]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    out = proc.stdout
    if RESULT_BEGIN in out and RESULT_END in out:
        raw = out.split(RESULT_BEGIN, 1)[1].split(RESULT_END, 1)[0].strip()
        result = json.loads(raw)
        result["_returncode"] = proc.returncode
        return result

    return {
        "ok": False,
        "error": "no RIGGS_RESULT block found in Blender output",
        "_returncode": proc.returncode,
        "_stdout_tail": out[-3000:],
        "_stderr_tail": proc.stderr[-3000:],
    }


if __name__ == "__main__":
    # Quick manual use: python blender_runner.py <script.py> '<json-args>'
    script = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(json.dumps(run_script(script, args), indent=2))
