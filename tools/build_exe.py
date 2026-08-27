"""Build the Windows EXE locally.

Usage (from the repo root, venv active):

    python tools/build_exe.py

Requires: pyinstaller installed in the venv.
Output: dist/brymenble-tc-bridge.exe
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    spec = ROOT / "brymenble-tc-bridge.spec"
    if not spec.exists():
        print(f"missing spec: {spec}", file=sys.stderr)
        return 1
    cmd = [sys.executable, "-m", "PyInstaller", str(spec), "--noconfirm", "--clean"]
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())