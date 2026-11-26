#!/usr/bin/env python3
"""
TankMix for the RadioMaster T8L - local app: install the tank mix into any
ExpressLRS 3.5.0+ source tree, edit it, build the firmware and flash it to
the T8L's internal module over WiFi, all from the browser (English/Portuguese).

Why the T8L only: it is the one ELRS radio here with no screen for a mixer
and no tank mix in the ELRS web UI, so the mix has to live in the TX module.

Start it with the launcher for your system (TankMix.bat on Windows,
TankMix.command on macOS, tankmix.sh on Linux) or directly:
    python tankmix_config.py [ExpressLRS folder]
The browser opens http://127.0.0.1:8765 .

What a build runs (equivalent to a local ExpressLRS Configurator build):
  1. pio run -e Unified_ESP8285_2400_TX_via_WIFI        (in <ExpressLRS>/src)
     with -DRegulatory_Domain_ISM_2400 passed through PLATFORMIO_BUILD_FLAGS
  2. python python/UnifiedConfiguration.py --target radiomaster.tx_2400.t8l
     --options <options from the build + UID of your binding phrase>
  3. HTTP POST of firmware.bin.gz to http://10.0.0.1/update   (radio in WiFi mode)

Requirements: Python 3.8+, PlatformIO, Git. The page checks them on start.
The binding phrase is never written to disk or passed on a command line, and
its UID is hidden in the log. Listens on 127.0.0.1 only; every API call needs
a per-run random token.
"""

import argparse
import gzip
import hashlib
import json
import locale
import os
import re
import secrets
import shutil
import struct
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import tankmix_patch

TOOL_VERSION = "1.0.0"
PIO_ENV = "Unified_ESP8285_2400_TX_via_WIFI"
HW_TARGET = "radiomaster.tx_2400.t8l"
BUILD_FLAGS = "-DRegulatory_Domain_ISM_2400"
DEFAULT_RADIO = "10.0.0.1"
ELRS_GIT = "https://github.com/ExpressLRS/ExpressLRS.git"
HERE = Path(__file__).resolve().parent
HTML_FILE = HERE / "tankmix_config.html"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
REQUIRED_DEFINES = ["THR_IN", "STR_IN", "LEFT_OUT", "RIGHT_OUT", "SW_CH", "WEAPON_CH",
                    "STEER_PCT", "OUT_DB", "CENTER_DB",
                    "INV_LEFT", "INV_RIGHT", "INV_THR", "INV_STEER"]


# ---------------------------------------------------------------- helpers

def phrase_uid(phrase):
    """Same as generateUID() in src/python/binary_configurator.py."""
    parts = [int(p) if p.isdigit() else -1 for p in phrase.split(",")]
    if 4 <= len(parts) <= 6 and all(0 <= p < 256 for p in parts):
        return bytes([0] * (6 - len(parts)) + parts)
    return hashlib.md5(('-DMY_BINDING_PHRASE="' + phrase + '"').encode()).digest()[0:6]


def firmware_end(f):
    """Same as findFirmwareEnd() in src/python/UnifiedConfiguration.py."""
    f.seek(0, 0)
    magic, segments, _, _, _ = struct.unpack("<BBBBI", f.read(8))
    if magic != 0xE9:
        return None
    is8285 = False
    if segments == 2:
        f.seek(0x1000, 0)
        magic, segments, _, _, _ = struct.unpack("<BBBBI", f.read(8))
        is8285 = True
    else:
        f.seek(24, 0)
    for _ in range(segments):
        _, size = struct.unpack("<II", f.read(8))
        f.seek(size, 1)
    pos = (f.tell() + 16) & ~15
    return pos if is8285 else pos + 32


def read_options(path):
    """Options JSON appended after the image: product[128] device[16] options[512]."""
    with open(path, "rb") as f:
        end = firmware_end(f)
        if end is None:
            return None
        f.seek(end + 128 + 16)
        raw = f.read(512).split(b"\0", 1)[0]
    try:
        return json.loads(raw.decode() or "{}")
    except ValueError:
        return None


def find_pio(explicit=None):
    if explicit:
        return explicit
    for name in ("pio", "platformio"):
        p = shutil.which(name)
        if p:
            return p
    home = Path.home() / ".platformio" / "penv"
    for cand in (home / "Scripts" / "pio.exe", home / "bin" / "pio"):
        if cand.exists():
            return str(cand)
    return None


def run_quiet(cmd, timeout=30):
    """Run a command, return (ok, first line of output)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, errors="replace")
        out = (r.stdout or r.stderr or "").strip().splitlines()
        return r.returncode == 0, (out[0] if out else "")
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)


def default_versions_dir():
    docs = Path.home() / "Documents"
    return str((docs if docs.is_dir() else Path.home()) / "ExpressLRS-versions")


def check_requirements(pio_override=None):
    """System check shown at the top of the page. Each item: ok, detail, required."""
    res = {}
    v = sys.version_info
    res["python"] = {"ok": v >= (3, 8), "detail": f"{v.major}.{v.minor}.{v.micro}", "required": True}
    pio = find_pio(pio_override)
    ok, out = run_quiet([pio, "--version"]) if pio else (False, "")
    res["pio"] = {"ok": bool(pio and ok), "detail": out if ok else "", "path": pio, "required": True}
    git = shutil.which("git")
    ok, out = run_quiet([git, "--version"]) if git else (False, "")
    res["git"] = {"ok": bool(git and ok), "detail": out if ok else "", "required": True}
    try:
        urllib.request.urlopen(urllib.request.Request("https://github.com", method="HEAD"), timeout=6)
        res["internet"] = {"ok": True, "detail": "github.com", "required": False}
    except Exception:
        res["internet"] = {"ok": False, "detail": "", "required": False}
    return res


def list_elrs_versions():
    """Release tags of ExpressLRS that support the T8L (>= 3.5.0), newest first."""
    git = shutil.which("git")
    if not git:
        return None
    try:
        r = subprocess.run([git, "ls-remote", "--tags", "--refs", ELRS_GIT], capture_output=True,
                           text=True, timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    tags = set()
    for line in r.stdout.splitlines():
        tag = line.rsplit("/", 1)[-1]
        if re.fullmatch(r"\d+\.\d+\.\d+", tag):
            if tuple(map(int, tag.split("."))) >= tankmix_patch.MIN_VERSION:
                tags.add(tag)
    return sorted(tags, key=lambda t: tuple(map(int, t.split("."))), reverse=True)


# ---------------------------------------------------------------- jobs

class Job:
    """One long task at a time (download / build / flash); the page polls the log."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.kind = None
        self.lines = []
        self.result = None      # None / "ok" / "error"
        self.code = None        # short result code the page translates
        self.secret = None      # string to mask in the log

    def start(self, kind, secret, fn):
        with self.lock:
            if self.running:
                return False
            self.running, self.kind, self.lines = True, kind, []
            self.result = self.code = None
            self.secret = secret or None
        threading.Thread(target=self._run, args=(fn,), daemon=True).start()
        return True

    def log(self, text):
        for line in str(text).splitlines() or [""]:
            line = ANSI.sub("", line).rstrip()
            if self.secret:
                line = line.replace(self.secret, "********")
            with self.lock:
                self.lines.append(line)

    def _run(self, fn):
        try:
            res = fn(self)
            ok, code = res if isinstance(res, tuple) else (res, None)
        except Exception as e:  # report, never crash the server
            self.log(f"ERROR: {e}")
            ok, code = False, "exception"
        with self.lock:
            self.running, self.result, self.code, self.secret = False, "ok" if ok else "error", code, None

    def snapshot(self, since):
        with self.lock:
            return {"running": self.running, "kind": self.kind, "result": self.result, "code": self.code,
                    "lines": self.lines[since:], "next": len(self.lines)}


# ---------------------------------------------------------------- app

class App:
    def __init__(self, pio, template):
        self.src = None
        self.pio = pio
        self.template = template
        self.job = Job()
        self.token = secrets.token_urlsafe(24)

    @property
    def header(self):
        return self.src / "include" / "tankmix.h" if self.src else None

    @property
    def out(self):
        return self.src / ".pio" / "tankmix_out"   # .pio is git-ignored

    def open(self, path):
        """Select an ExpressLRS tree. Returns None or an error code."""
        src = tankmix_patch.resolve_src(path)
        if not src:
            return "not_elrs"
        if not (src / "python" / "UnifiedConfiguration.py").is_file():
            return "too_old"
        self.src = src
        return None

    def info(self):
        d = {"tool_version": TOOL_VERSION, "pio": self.pio, "target": HW_TARGET, "radio": DEFAULT_RADIO,
             "versions_dir": default_versions_dir(), "busy": self.job.running, "src": None}
        if self.src:
            d.update({"src": str(self.src), "header": str(self.header),
                      "mod": tankmix_patch.status(self.src), "firmware": self.firmware_info()})
        return d

    # ---- helpers ----
    def run_cmd(self, job, cmd, env=None, cwd=None, shown=None):
        shown = shown or " ".join(f'"{c}"' if " " in c else c for c in cmd)
        job.log(f"> {shown}")
        e = os.environ.copy()
        e["PYTHONIOENCODING"] = "utf-8"
        e["PYTHONUNBUFFERED"] = "1"
        if env:
            e.update(env)
        # stdin must be a closed pipe, not DEVNULL: on Windows NUL reports isatty() == True,
        # and ExpressLRS 4.x then waits for an interactive hardware choice (EOFError).
        p = subprocess.Popen(cmd, cwd=str(cwd or self.src), env=e, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
        p.stdin.close()
        for raw in p.stdout:
            job.log(raw.decode("utf-8", "replace"))
        return p.wait()

    def config_python(self):
        """Python for UnifiedConfiguration.py. Since 4.x it imports pyserial indirectly
        (external/__init__ -> binary_configurator -> ... -> serial), so prefer PlatformIO's
        own Python, which always has pyserial; else this Python plus a stub module."""
        cands = []
        if self.pio:
            d = Path(self.pio).resolve().parent
            cands += [d / "python.exe", d / "python", d / "python3"]
        cands.append(Path(sys.executable))
        for py in cands:
            if py.is_file() and subprocess.run([str(py), "-c", "import serial"], capture_output=True,
                                               stdin=subprocess.DEVNULL).returncode == 0:
                return str(py), None
        # nobody has pyserial: UnifiedConfiguration never uses it, a stub is enough
        stub = self.out / "pystub"
        (stub / "serial" / "tools").mkdir(parents=True, exist_ok=True)
        (stub / "serial" / "__init__.py").write_text(
            "# stub so ExpressLRS modules import; UnifiedConfiguration never opens a port\n"
            "VERSION = '3.5'\n"
            "class SerialException(Exception): pass\n"
            "class SerialTimeoutException(SerialException): pass\n"
            "class Serial:\n"
            "    def __init__(self, *a, **k): raise SerialException('pyserial not installed')\n")
        (stub / "serial" / "tools" / "__init__.py").write_text("")
        (stub / "serial" / "tools" / "list_ports.py").write_text("def comports(*a, **k):\n    return []\n")
        return sys.executable, {"PYTHONPATH": str(stub)}

    def firmware_info(self):
        gz = self.out / "firmware.bin.gz"
        if gz.exists():
            st = gz.stat()
            hdr = self.header.stat().st_mtime if self.header.exists() else 0
            return {"exists": True, "size": st.st_size, "mtime": st.st_mtime,
                    "newer_than_header": st.st_mtime >= hdr}
        return {"exists": False}

    # ---- download a version ----
    def download(self, version, dest_dir):
        if not re.fullmatch(r"\d+\.\d+\.\d+", version) or \
                tuple(map(int, version.split("."))) < tankmix_patch.MIN_VERSION:
            return False
        dest = Path(dest_dir).expanduser() / version

        def fn(job):
            git = shutil.which("git")
            if not git:
                job.log("Git not found.")
                return False, "no_git"
            if (dest / "src" / "platformio.ini").is_file():
                job.log(f"Already downloaded: {dest}")
            else:
                if dest.exists() and any(dest.iterdir()):
                    job.log(f"{dest} exists and is not an ExpressLRS folder; not touching it.")
                    return False, "dest_busy"
                dest.parent.mkdir(parents=True, exist_ok=True)
                job.log(f"Downloading ExpressLRS {version} to {dest}")
                code = self.run_cmd(job, [git, "clone", "--depth", "1", "--branch", version, ELRS_GIT, str(dest)],
                                    cwd=dest.parent)
                if code != 0:
                    return False, "clone_failed"
            if self.open(dest):
                return False, "not_elrs"
            job.log("")
            ok = tankmix_patch.install(self.src, self.template, log=job.log)
            return ok, None if ok else "install_failed"
        return self.job.start("download", None, fn)

    # ---- build ----
    def build(self, phrase):
        def fn(job):
            if not self.pio:
                job.log("PlatformIO (pio) not found.")
                return False, "no_pio"
            st = tankmix_patch.status(self.src)
            if st["state"] != "installed":
                job.log(st["message"])
                return False, "not_installed"
            job.log(f"Building ExpressLRS {st['version']} for the RadioMaster T8L: {PIO_ENV} in {self.src}")
            code = self.run_cmd(job, [self.pio, "run", "-e", PIO_ENV],
                                env={"PLATFORMIO_BUILD_FLAGS": BUILD_FLAGS})
            if code != 0:
                job.log(f"Build failed (exit {code}). The compiler error is above.")
                return False, "build_failed"
            # 3.x leaves a gzipped firmware.bin; newer versions write firmware.bin.gz instead
            bdir = self.src / ".pio" / "build" / PIO_ENV
            cands = [f for f in (bdir / "firmware.bin", bdir / "firmware.bin.gz") if f.exists()]
            if not cands:
                job.log(f"Build finished but there is no firmware.bin(.gz) in {bdir}.")
                return False, "build_failed"
            built = max(cands, key=lambda f: f.stat().st_mtime)
            self.out.mkdir(parents=True, exist_ok=True)
            for f in ("firmware.bin", "firmware.bin.gz"):
                (self.out / f).unlink(missing_ok=True)
            target_bin = self.out / "firmware.bin"
            with open(built, "rb") as f:
                is_gz = f.read(2) == b"\x1f\x8b"
            if is_gz:
                with gzip.open(built, "rb") as fi, open(target_bin, "wb") as fo:
                    shutil.copyfileobj(fi, fo)
            else:
                shutil.copy2(built, target_bin)

            # Options the build put in the firmware (from user_defines.txt): keep them,
            # only replace the UID with the one from the binding phrase.
            options = read_options(target_bin)
            if options is None:
                job.log("Could not find the options block in the built firmware.")
                return False, "build_failed"
            if phrase:
                options["uid"] = list(phrase_uid(phrase))
            elif "uid" not in options:
                job.log("WARNING: no binding phrase here or in user_defines.txt; the radio will not bind.")
            job.log("")
            job.log(f"Configuring for {HW_TARGET}" + (" with your binding phrase" if phrase else ""))
            py, extra_env = self.config_python()
            script = str(self.src / "python" / "UnifiedConfiguration.py")
            # the UID is as good as the phrase for binding: keep it out of the log
            shown_opts = json.dumps({k: ("[hidden]" if k == "uid" else v) for k, v in options.items()})
            code = self.run_cmd(job, [py, script, "--target", HW_TARGET, "--options", json.dumps(options),
                                      str(target_bin)], env=extra_env,
                                shown=f"{py} UnifiedConfiguration.py --target {HW_TARGET} --options {shown_opts} firmware.bin")
            if code != 0:
                job.log(f"UnifiedConfiguration failed (exit {code}).")
                return False, "build_failed"
            with open(target_bin, "rb") as fi, gzip.open(self.out / "firmware.bin.gz", "wb") as fo:
                shutil.copyfileobj(fi, fo)
            size = (self.out / "firmware.bin.gz").stat().st_size
            job.log("")
            job.log(f"Firmware ready: {self.out / 'firmware.bin.gz'} ({size} bytes)")
            return True
        return self.job.start("build", phrase, fn)

    # ---- flash ----
    def flash(self, address, confirm=False):
        address = address.strip() or DEFAULT_RADIO
        if not re.fullmatch(r"[A-Za-z0-9.\-]+(:\d+)?", address):
            return False, "bad_address"

        def fn(job):
            if confirm:
                url = f"http://{address}/forceupdate?action=confirm"
                job.log(f"Confirming update on {url}")
                return self._report(job, self._http(url, None, None))
            gz = self.out / "firmware.bin.gz"
            if not gz.exists():
                job.log("No firmware built yet.")
                return False, "no_firmware"
            data = gz.read_bytes()
            boundary = uuid.uuid4().hex
            body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"data\"; "
                    f"filename=\"firmware.bin.gz\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
            url = f"http://{address}/update"
            job.log(f"Uploading {len(data)} bytes to {url} ...")
            headers = {"Content-Type": f"multipart/form-data; boundary={boundary}",
                       "X-FileSize": str(len(data))}
            return self._report(job, self._http(url, body, headers))
        return self.job.start("flash", None, fn), None

    @staticmethod
    def _http(url, body, headers):
        req = urllib.request.Request(url, data=body, headers=headers or {},
                                     method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.URLError as e:
            return {"connect_error": str(getattr(e, "reason", e))}
        except (TimeoutError, OSError) as e:
            return {"connect_error": str(e)}

    @staticmethod
    def _report(job, resp):
        if isinstance(resp, dict):
            job.log(f"Could not reach the radio: {resp['connect_error']}")
            return False, "unreachable"
        try:
            j = json.loads(resp)
        except ValueError:
            job.log(f"Unexpected answer from the radio: {resp[:300]}")
            return False, "flash_failed"
        msg = re.sub(r"<br\s*/?>", "\n", j.get("msg", "")).replace("<b>", "").replace("</b>", "")
        status = j.get("status")
        job.log(msg)
        if status == "ok":
            return True
        if status == "mismatch":
            return False, "mismatch"
        return False, "flash_failed"


# ---------------------------------------------------------------- http

def make_handler(app):
    class H(BaseHTTPRequestHandler):
        server_version = "TankMix"

        def log_message(self, fmt, *args):
            pass

        def _send(self, code, body, ctype="application/json"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body)
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _err(self, http, code, detail=""):
            return self._send(http, {"error": code, "detail": detail})

        def _allowed(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def _authed(self):
            return self._allowed() and secrets.compare_digest(
                self.headers.get("X-Token", ""), app.token)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1_000_000:
                raise ValueError("body too large")
            raw = self.rfile.read(n) if n else b""
            return json.loads(raw or b"{}")

        def do_GET(self):
            if not self._allowed():
                return self._err(403, "forbidden")
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                html = HTML_FILE.read_text(encoding="utf-8")
                html = html.replace("__TANKMIX_SERVER_TOKEN__", app.token)
                return self._send(200, html, "text/html; charset=utf-8")
            if not self._authed():
                return self._err(403, "bad_token")
            if path == "/api/info":
                return self._send(200, app.info())
            if path == "/api/check":
                return self._send(200, check_requirements(app.pio))
            if path == "/api/versions":
                v = list_elrs_versions()
                if v is None:
                    return self._err(502, "versions_failed")
                return self._send(200, {"versions": v})
            if path == "/api/header":
                if not app.src or not app.header.is_file():
                    return self._err(404, "not_installed")
                return self._send(200, {"text": app.header.read_bytes().decode("utf-8")})
            if path == "/api/job":
                m = re.search(r"since=(\d+)", self.path)
                snap = app.job.snapshot(int(m.group(1)) if m else 0)
                snap["firmware"] = app.firmware_info() if app.src else {"exists": False}
                return self._send(200, snap)
            return self._err(404, "not_found")

        def do_POST(self):
            if not self._authed():
                return self._err(403, "bad_token")
            try:
                data = self._body()
            except ValueError as e:
                return self._err(400, "bad_request", str(e))
            path = self.path.split("?")[0]
            busy = app.job.running
            if path == "/api/open":
                if busy:
                    return self._err(409, "busy")
                err = app.open(str(data.get("path", "")).strip().strip('"'))
                if err:
                    return self._err(400, err)
                return self._send(200, app.info())
            if path == "/api/download":
                if not app.download(str(data.get("version", "")), str(data.get("dest") or default_versions_dir())):
                    return self._err(409 if busy else 400, "busy" if busy else "bad_version")
                return self._send(200, {"ok": True})
            if not app.src:
                return self._err(409, "no_folder")
            if path == "/api/header":
                text = data.get("text", "")
                missing = [d for d in REQUIRED_DEFINES
                           if not re.search(rf"^\s*#define\s+TANKMIX_{d}\s+-?\d+", text, re.M)]
                if missing:
                    return self._err(400, "bad_header", ", ".join(missing))
                if busy:
                    return self._err(409, "busy")
                if not app.header.is_file():
                    return self._err(409, "not_installed")
                # newline="" keeps the exact line endings the page sent (CRLF stays CRLF)
                with open(app.header, "w", encoding="utf-8", newline="") as f:
                    f.write(text)
                return self._send(200, {"ok": True, "firmware": app.firmware_info()})
            if path == "/api/install":
                if busy:
                    return self._err(409, "busy")
                lines = []
                ok = tankmix_patch.install(app.src, app.template, log=lines.append)
                return self._send(200, {"ok": ok, "log": lines, "info": app.info()})
            if path == "/api/build":
                phrase = str(data.get("phrase", ""))
                if len(phrase) > 128 or "\n" in phrase:
                    return self._err(400, "bad_phrase")
                if not app.build(phrase):
                    return self._err(409, "busy")
                return self._send(200, {"ok": True})
            if path == "/api/flash":
                started, err = app.flash(str(data.get("address", "")), bool(data.get("confirm")))
                if err:
                    return self._err(400, err)
                if not started:
                    return self._err(409, "busy")
                return self._send(200, {"ok": True})
            return self._err(404, "not_found")

    return H


# ---------------------------------------------------------------- main

def console_pt():
    lang = (os.environ.get("LANG") or "") + " " + " ".join(filter(None, locale.getlocale()))
    return "pt" in lang.lower() or "portuguese" in lang.lower()


def main():
    ap = argparse.ArgumentParser(description="TankMix for the RadioMaster T8L: install, edit, build and flash "
                                             "the tank mix on any ExpressLRS 3.5.0+ source tree.")
    ap.add_argument("path", nargs="?", help="ExpressLRS folder (optional; can be chosen in the page)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--pio", help="path to the pio executable (default: search PATH and ~/.platformio)")
    ap.add_argument("--template", default=str(tankmix_patch.DEFAULT_TEMPLATE),
                    help="tankmix.h copied into trees that do not have one yet")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = ap.parse_args()
    pt = console_pt()

    if not HTML_FILE.is_file():
        sys.exit(f"Missing {HTML_FILE}")
    app = App(find_pio(args.pio), Path(args.template))
    if args.path:
        err = app.open(args.path)
        if err:
            sys.exit(("Pasta não é um ExpressLRS 3.5.0+: " if pt else "Not an ExpressLRS 3.5.0+ folder: ") + args.path)

    try:
        srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(app))
    except OSError:
        sys.exit((f"A porta {args.port} está em uso: o TankMix já está aberto? Use --port para outra."
                  if pt else f"Port {args.port} is busy: is TankMix already open? Use --port for another one."))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"TankMix {TOOL_VERSION} - RadioMaster T8L")
    names = {"python": "Python", "pio": "PlatformIO", "git": "Git", "internet": "Internet"}
    for k, r in check_requirements(app.pio).items():
        mark = "OK " if r["ok"] else ("!! " if r["required"] else "-- ")
        miss = ("sem conexão" if pt else "no connection") if k == "internet" else ("não encontrado" if pt else "not found")
        print(f"  {mark}{names[k]:<11}{r['detail'] or miss}")
    print(("  Abra no navegador: " if pt else "  Open in the browser: ") + url)
    print("  Ctrl+C para sair." if pt else "  Press Ctrl+C to quit.")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nFim." if pt else "\nStopped.")


if __name__ == "__main__":
    main()
