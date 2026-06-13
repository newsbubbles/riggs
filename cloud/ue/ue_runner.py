"""Headless Unreal Engine runner — the UE analogue of blender_runner.

Drives UnrealEditor-Cmd.exe to run a UE Python script against a .uproject with no
GUI, captures stdout, and extracts a RIGGS_RESULT_BEGIN/END JSON block the script
prints. Args are passed to the UE script via the RIGGS_UE_ARGS env var (JSON).

Usage:
    python ue_runner.py <uproject> <ue_script.py> '<json args>'

Finds the engine from the .uproject's EngineAssociation, or set RIGGS_UE env to the
UnrealEditor-Cmd.exe path.
"""
import json
import os
import re
import subprocess
import sys

RESULT_RE = re.compile(r"RIGGS_RESULT_BEGIN\s*(.*?)\s*RIGGS_RESULT_END", re.S)


def find_editor(uproject):
    if os.environ.get("RIGGS_UE"):
        return os.environ["RIGGS_UE"]
    ver = "5.7"
    try:
        ver = json.load(open(uproject)).get("EngineAssociation", ver)
    except Exception:
        pass
    cand = rf"C:\Program Files\Epic Games\UE_{ver}\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
    if os.path.isfile(cand):
        return cand
    # fall back to any installed UE
    base = r"C:\Program Files\Epic Games"
    if os.path.isdir(base):
        for d in sorted(os.listdir(base), reverse=True):
            p = os.path.join(base, d, "Engine", "Binaries", "Win64", "UnrealEditor-Cmd.exe")
            if os.path.isfile(p):
                return p
    raise FileNotFoundError("UnrealEditor-Cmd.exe not found; set RIGGS_UE")


def run(uproject, script, args=None, timeout=1800):
    editor = find_editor(uproject)
    env = dict(os.environ)
    env["RIGGS_UE_ARGS"] = json.dumps(args or {})
    cmd = [editor, uproject, "-run=pythonscript", f"-script={script}",
           "-unattended", "-nopause", "-nosplash", "-stdout", "-FullStdOutLogOutput"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    m = RESULT_RE.search(out)
    if m:
        # UE prefixes every print line with "[timestamp][ 0]LogPython: " — strip it
        cleaned = "\n".join(
            re.sub(r"^.*?LogPython:\s?", "", ln) for ln in m.group(1).splitlines()
        ).strip()
        try:
            result = json.loads(cleaned)
        except Exception as e:
            result = {"ok": False, "error": f"bad RIGGS_RESULT json: {e}", "raw": cleaned[:2000]}
    else:
        tail = "\n".join(out.splitlines()[-40:])
        result = {"ok": False, "error": "no RIGGS_RESULT block", "returncode": p.returncode, "log_tail": tail}
    result["_returncode"] = p.returncode
    return result


if __name__ == "__main__":
    uproj, scr = sys.argv[1], sys.argv[2]
    a = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
    print(json.dumps(run(uproj, scr, a), indent=2))
