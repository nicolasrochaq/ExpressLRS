#!/usr/bin/env python3
"""Build the TankMix release zip: python tools/tankmix_config/make_release.py [out_dir]"""

import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
VERSION = re.search(r'TOOL_VERSION = "([^"]+)"', (HERE / "tankmix_config.py").read_text()).group(1)

FILES = [  # (source, name in the zip, unix mode)
    (HERE / "tankmix_config.py", "tankmix_config.py", 0o644),
    (HERE / "tankmix_patch.py", "tankmix_patch.py", 0o644),
    (HERE / "tankmix_config.html", "tankmix_config.html", 0o644),
    (HERE / "README.md", "README.md", 0o644),
    (HERE / "TankMix.bat", "TankMix.bat", 0o644),
    (HERE / "TankMix.command", "TankMix.command", 0o755),
    (HERE / "tankmix.sh", "tankmix.sh", 0o755),
    (ROOT / "src" / "include" / "tankmix.h", "tankmix.h", 0o644),   # template for new ELRS trees
    (ROOT / "LICENSE", "LICENSE", 0o644),
]


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist")
    out.mkdir(parents=True, exist_ok=True)
    zpath = out / f"TankMix-v{VERSION}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for src, name, mode in FILES:
            data = src.read_bytes()
            if name.endswith(".bat"):   # cmd.exe needs CRLF
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            elif name.endswith((".sh", ".command", ".py")):
                data = data.replace(b"\r\n", b"\n")
            info = zipfile.ZipInfo(f"TankMix/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    print(zpath)


if __name__ == "__main__":
    main()
