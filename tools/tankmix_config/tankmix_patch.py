#!/usr/bin/env python3
"""
tankmix_patch - install the tank mix into any ExpressLRS source tree.

The mod is two small changes, done the same way on every supported version:
  1. src/include/tankmix.h          (copied from a template, e.g. this fork)
  2. src/src/tx_main.cpp:
       #include "tankmix.h"                       after #include "MAVLink.h"
       OtaPackChannelData(&otaPkt, ChannelData,   ->  ..., tankMixApply(ChannelData), ...

Supported: ExpressLRS 3.5.0 and newer (3.5.x, 3.6.x, 4.x, master). The T8L
unified hardware layout needs 3.5.0+, and every version from there on calls
OtaPackChannelData(&otaPkt, ChannelData, ...) once in tx_main.cpp.

Command line:
    python tankmix_patch.py <ExpressLRS folder>             show status
    python tankmix_patch.py <ExpressLRS folder> --install   install the mod
"""

import argparse
import re
import shutil
import subprocess
from pathlib import Path

MIN_VERSION = (3, 5, 0)
INCLUDE_LINE = '#include "tankmix.h"'
CALL_RAW = re.compile(r"OtaPackChannelData\(\s*&otaPkt\s*,\s*ChannelData\s*,")
CALL_MIXED = re.compile(r"OtaPackChannelData\(\s*&otaPkt\s*,\s*tankMixApply\(\s*ChannelData\s*\)\s*,")
_HERE = Path(__file__).resolve().parent
# a tankmix.h next to this script wins (standalone copy of the tool); else this fork's
DEFAULT_TEMPLATE = next((p for p in (_HERE / "tankmix.h",
                                      _HERE.parent.parent / "src" / "include" / "tankmix.h")
                         if p.is_file()), _HERE / "tankmix.h")


def resolve_src(path):
    """Accepts the clone root, its src folder, or src/include/tankmix.h. Returns src or None."""
    p = Path(path).expanduser().resolve()
    if p.name == "tankmix.h" or p.suffix == ".h":
        p = p.parent.parent
    for cand in (p, p / "src"):
        if (cand / "platformio.ini").is_file() and (cand / "src" / "tx_main.cpp").is_file():
            return cand
    return None


def parse_version(text):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def detect_version(src):
    """(version tuple or None, label). Uses git tags; works for Configurator/git clones."""
    try:
        out = subprocess.run(["git", "describe", "--tags", "--always"], cwd=str(src),
                             capture_output=True, text=True, timeout=10)
        label = out.stdout.strip()
        if out.returncode == 0 and label:
            return parse_version(label), label
    except (OSError, subprocess.SubprocessError):
        pass
    tx = (src / "src" / "tx_main.cpp").read_text(encoding="utf-8", errors="replace")
    # no git info: tell 4.x from 3.x by an API that only 4.x has
    return None, "4.x (no git tag)" if "DataDlReceiver" in tx else "unknown (no git tag)"


def read_text(path):
    raw = path.read_bytes()
    return raw.decode("utf-8"), (b"\r\n" in raw)


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def status(src):
    """Describe the mod state of an ExpressLRS tree (all keys always present)."""
    version, label = detect_version(src)
    tx_text, _ = read_text(src / "src" / "tx_main.cpp")
    header = src / "include" / "tankmix.h"
    raw_calls = len(CALL_RAW.findall(tx_text))
    mixed_calls = len(CALL_MIXED.findall(tx_text))
    has_include = INCLUDE_LINE in tx_text
    too_old = version is not None and version < MIN_VERSION

    reason = None
    if has_include and mixed_calls == 1 and raw_calls == 0 and header.is_file():
        state, msg = "installed", "Tank mix is installed."
    elif too_old:
        state, reason = "unsupported", "too_old"
        msg = (f"ExpressLRS {label} is too old: the T8L needs 3.5.0 or newer "
               f"(its hardware layout and the code the mod hooks into).")
    elif raw_calls + mixed_calls != 1:
        state, reason = "unsupported", "hook"
        msg = ("tx_main.cpp does not have exactly one OtaPackChannelData(&otaPkt, ChannelData, ...) "
               f"call (found {raw_calls + mixed_calls}). This version changed that code; the mod "
               "has to be adapted by hand.")
    elif has_include or mixed_calls or header.is_file():
        state, msg = "partial", "Tank mix is partly installed. Install will finish it."
    else:
        state, msg = "missing", "Tank mix is not installed in this ExpressLRS yet."
    return {"state": state, "reason": reason, "calls": raw_calls + mixed_calls,
            "message": msg, "version": label,
            "header": str(header), "header_exists": header.is_file()}


def install(src, template=DEFAULT_TEMPLATE, log=print):
    """Install (or finish installing) the mod. Returns True on success. Idempotent."""
    st = status(src)
    if st["state"] == "unsupported":
        log(st["message"])
        return False
    if st["state"] == "installed":
        log("Already installed, nothing to do.")
        return True

    header = src / "include" / "tankmix.h"
    if not header.is_file():
        template = Path(template)
        if not template.is_file():
            log(f"Template tankmix.h not found: {template}")
            return False
        shutil.copy2(template, header)
        log(f"Copied {template} -> {header}")
    else:
        log(f"Keeping existing {header}")

    tx = src / "src" / "tx_main.cpp"
    text, crlf = read_text(tx)
    nl = "\r\n" if crlf else "\n"
    backup = tx.with_name("tx_main.cpp.before-tankmix")
    if not backup.exists():
        shutil.copy2(tx, backup)
        log(f"Backup: {backup}")

    if INCLUDE_LINE not in text:
        m = re.search(r'^#include\s+"MAVLink\.h"[^\r\n]*\r?\n', text, re.M)
        if not m:  # fall back to after the last #include at the top of the file
            m = list(re.finditer(r'^#include[^\r\n]*\r?\n', text, re.M))[-1]
        text = text[:m.end()] + INCLUDE_LINE + nl + text[m.end():]
        log("tx_main.cpp: added " + INCLUDE_LINE)

    if not CALL_MIXED.search(text):
        text, n = CALL_RAW.subn("OtaPackChannelData(&otaPkt, tankMixApply(ChannelData),", text)
        if n != 1:
            log("Could not patch the OtaPackChannelData call; tx_main.cpp left unchanged.")
            return False
        log("tx_main.cpp: channels now go through tankMixApply() before transmitting")

    write_text(tx, text)
    ok = status(src)["state"] == "installed"
    log("Done." if ok else "Something is still missing, check tx_main.cpp.")
    return ok


def main():
    ap = argparse.ArgumentParser(description="Install the T8L tank mix into an ExpressLRS source tree.")
    ap.add_argument("path", help="ExpressLRS folder (clone root, its src folder, or src/include/tankmix.h)")
    ap.add_argument("--install", action="store_true", help="install the mod")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE), help="tankmix.h to copy if the tree has none")
    args = ap.parse_args()
    src = resolve_src(args.path)
    if not src:
        raise SystemExit(f"{args.path} is not an ExpressLRS folder (no src/platformio.ini and src/src/tx_main.cpp).")
    st = status(src)
    print(f"ExpressLRS {st['version']} at {src}")
    print(st["message"])
    if args.install:
        raise SystemExit(0 if install(src, args.template) else 1)


if __name__ == "__main__":
    main()
