"""Install CircuitPython libraries on the device.

Reads Adafruit bundle modules from:
  - [tool.esp_remote.circuitpython] dependencies in pyproject.toml
  - any adafruit-circuitpython-* entries in [project] dependencies

Host-only packages (Blinka, FastAPI, mpremote, etc.) are skipped. Firmware
imports are checked so missing bundle modules are reported before upload.

Usage:
    poetry run circup-install
    poetry run circup-install --check
    poetry run circup-install --serial
    poetry run circup-install --serial --port /dev/ttyACM1
"""

import argparse
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

from scripts.circuitpython_deps import (
    firmware_missing_bundle_modules,
    print_dependency_report,
    resolve_bundle_modules,
)
from scripts.device_files import LIB_SRC, REPO_ROOT
from scripts.web_workflow_http import auth_header, check_workflow, mkdir_remote, put_bytes

PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
SETTINGS_PATH = REPO_ROOT / "settings.toml"
FIRMWARE_DIR = LIB_SRC / "firmware"

BUNDLE_CACHE_DIR = Path.home() / ".local" / "share" / "circup"


def _load_toml(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _find_bundle(cp_major: int = 10) -> Path:
    candidates = sorted(
        BUNDLE_CACHE_DIR.glob(f"adafruit-circuitpython-bundle-{cp_major}*mpy.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    candidates = sorted(
        BUNDLE_CACHE_DIR.glob("adafruit-circuitpython-bundle-*mpy.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    raise FileNotFoundError(
        f"No Adafruit CircuitPython bundle found in {BUNDLE_CACHE_DIR}.\n"
        "Run: poetry run circup --path /dev/ttyACM0 install adafruit_bus_device\n"
        "(once, to prime the cache — any adafruit-circuitpython-* package works)"
    )


def _extract_lib_entries(zf: zipfile.ZipFile, module_name: str) -> list[str]:
    names = zf.namelist()
    entries = [n for n in names if f"/lib/{module_name}/" in n and not n.endswith("/")]
    if entries:
        return entries
    return [
        n
        for n in names
        if n.endswith(f"/lib/{module_name}.mpy") or n.endswith(f"/lib/{module_name}.py")
    ]


def _remote_path(zip_entry: str) -> str:
    idx = zip_entry.find("/lib/")
    return "lib/" + zip_entry[idx + len("/lib/") :]


def install_wifi(
    host: str,
    password: str,
    module_names: list[str],
    bundle_path: Path,
    *,
    workflow_port: int = 80,
) -> int:
    auth = auth_header(password)
    print(f"\nBundle  : {bundle_path.name}")
    print(f"Host    : {host}:{workflow_port}")
    print()

    try:
        check_workflow(host, password, workflow_port)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not module_names:
        print("Nothing to upload — firmware uses built-in modules only.")
        return 0

    uploaded = 0
    skipped = 0

    with zipfile.ZipFile(bundle_path) as zf:
        for module_name in module_names:
            entries = _extract_lib_entries(zf, module_name)
            if not entries:
                print(f"  [WARN] {module_name} — not found in bundle")
                skipped += 1
                continue

            for entry in entries:
                remote = _remote_path(entry)
                parts = remote.split("/")
                for depth in range(2, len(parts)):
                    mkdir_remote(host, "/".join(parts[:depth]), auth, port=workflow_port)
                put_bytes(host, remote, zf.read(entry), auth, port=workflow_port)
                print(f"  uploaded  {remote}")
                uploaded += 1

    print(f"\nDone — {uploaded} file(s) uploaded, {skipped} skipped.")
    if skipped:
        return 1
    return 0


def install_serial(port: str, module_names: list[str], bundle_path: Path) -> int:
    print(f"\nBundle  : {bundle_path.name}")
    print(f"Port    : {port}")
    print()

    if not module_names:
        print("Nothing to upload — firmware uses built-in modules only.")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        extracted = 0
        skipped = 0

        with zipfile.ZipFile(bundle_path) as zf:
            for module_name in module_names:
                entries = _extract_lib_entries(zf, module_name)
                if not entries:
                    print(f"  [WARN] {module_name} — not found in bundle")
                    skipped += 1
                    continue
                for entry in entries:
                    rel = _remote_path(entry)
                    dest = tmp_path / rel[len("lib/") :]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(entry))
                    extracted += 1
                print(f"  extracted {module_name}  ({len(entries)} file(s))")

        dirs_to_create: list[str] = []
        for fn in sorted(tmp_path.rglob("*")):
            if fn.is_file():
                rel = fn.relative_to(tmp_path)
                for depth in range(1, len(rel.parts)):
                    d = "lib/" + "/".join(rel.parts[:depth])
                    if d not in dirs_to_create and d != "lib":
                        dirs_to_create.append(d)

        print(f"\nUploading {extracted} file(s) via mpremote ...")

        file_entries = sorted(fn for fn in tmp_path.rglob("*") if fn.is_file())

        mkdir_lines = ["import os"]
        for d in dirs_to_create:
            mkdir_lines += [
                "try:",
                f"    os.mkdir('/{d}')",
                "except OSError:",
                "    pass",
            ]
        for fn in file_entries:
            rel = fn.relative_to(tmp_path)
            dest_path = "/lib/" + "/".join(rel.parts)
            mkdir_lines.append(f"open('{dest_path}','wb').close()")
        mkdir_code = "\n".join(mkdir_lines) + "\n"

        chain: list[str] = ["mpremote", "connect", port, "+", "exec", mkdir_code]
        for fn in file_entries:
            rel = fn.relative_to(tmp_path)
            chain += ["+", "cp", "-f", str(fn), ":lib/" + "/".join(rel.parts)]

        result = subprocess.run(chain)
        if result.returncode != 0:
            print("Error: mpremote upload failed", file=sys.stderr)
            return 1

    print(f"\nDone — {extracted} file(s) uploaded, {skipped} skipped.")
    if skipped:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Install CircuitPython libraries on device.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print dependency report only; exit 1 if firmware needs undeclared libs",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Install even when firmware imports undeclared bundle modules",
    )
    parser.add_argument(
        "--serial",
        action="store_true",
        help="Install via USB-serial using mpremote",
    )
    parser.add_argument(
        "--port",
        metavar="PORT",
        default="/dev/ttyACM0",
        help="Serial port for --serial mode (default: /dev/ttyACM0)",
    )
    args = parser.parse_args()

    if not PYPROJECT_PATH.exists():
        print(f"Error: {PYPROJECT_PATH} not found", file=sys.stderr)
        return 1

    if not FIRMWARE_DIR.is_dir():
        print(f"Error: {FIRMWARE_DIR} not found", file=sys.stderr)
        return 1

    print()
    module_names = print_dependency_report(PYPROJECT_PATH, FIRMWARE_DIR)
    print()

    missing = firmware_missing_bundle_modules(PYPROJECT_PATH, FIRMWARE_DIR)
    if missing and not args.allow_missing:
        print(
            "Aborting: firmware imports bundle modules that are not declared.\n"
            "Add adafruit-circuitpython-* packages under [tool.esp_remote.circuitpython]\n"
            "in pyproject.toml, or pass --allow-missing to skip this check.",
            file=sys.stderr,
        )
        return 1

    if args.check:
        return 1 if missing else 0

    if not module_names:
        return 0

    try:
        bundle_path = _find_bundle()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.serial:
        return install_serial(args.port, module_names, bundle_path)

    if not SETTINGS_PATH.exists():
        print(
            f"Error: {SETTINGS_PATH} not found — copy settings.toml.example",
            file=sys.stderr,
        )
        return 1
    settings = _load_toml(SETTINGS_PATH)
    host = settings.get("ESP32_IP", "").strip()
    if not host:
        print("Error: ESP32_IP not set in settings.toml", file=sys.stderr)
        return 1
    password = settings.get("CIRCUITPY_WEB_API_PASSWORD", "").strip()
    try:
        workflow_port = int(settings.get("CIRCUITPY_WEB_API_PORT", 80))
    except (TypeError, ValueError):
        workflow_port = 80

    return install_wifi(
        host, password, module_names, bundle_path, workflow_port=workflow_port
    )


if __name__ == "__main__":
    sys.exit(main())
