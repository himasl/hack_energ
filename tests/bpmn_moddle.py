import json
import shutil
import subprocess
from pathlib import Path

CHECK = Path(__file__).parent / "moddle"
AVAILABLE = shutil.which("node") is not None and (CHECK / "node_modules").exists()


def moddle_warnings(xml):
    out = subprocess.run(["node", "check.mjs"], cwd=CHECK, input=xml, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)
