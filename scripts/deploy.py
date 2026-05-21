"""Run tests, then deploy code to the CircuitPython device.

Transport modes:
  WiFi (default) — Web Workflow HTTP PUT
  Serial (--serial) — mpremote over USB
  USB mass storage (--usb) — CIRCUITPY drive (ESP32-S2/S3)

Usage:
    poetry run deploy
    poetry run deploy --skip-tests
    poetry run deploy --settings
    poetry run deploy --serial --port /dev/ttyACM1
"""

import argparse
import getpass
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from scripts.device_files import (
    LIB_SRC,
    STATIC_DIR,
    device_library_files,
    device_static_files,
)
from scripts.web_workflow_http import (
    auth_header,
    check_workflow,
    mkdir_remote,
    put_file,
)

PACKAGE_NAME = "esp_remote"

REPO_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = REPO_ROOT / "settings.toml"
CODE_PY = REPO_ROOT / "code.py"
BOOT_PY = REPO_ROOT / "boot.py"
_DEFAULT_SERIAL_PORT = "/dev/ttyACM0"

_USB_CANDIDATE_ROOTS = [
    Path("/media") / getpass.getuser() / "CIRCUITPY",
    Path("/media/CIRCUITPY"),
    Path("/Volumes/CIRCUITPY"),
    Path("D:/"),
]


def load_settings() -> tuple[str, str, int]:
    if not SETTINGS_PATH.exists():
        print(
            f"Error: {SETTINGS_PATH} not found — copy settings.toml.example",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(SETTINGS_PATH, "rb") as f:
        settings = tomllib.load(f)

    host = settings.get("ESP32_IP", "").strip()
    if not host:
        print("Error: ESP32_IP is not set in settings.toml", file=sys.stderr)
        sys.exit(1)

    password = settings.get("CIRCUITPY_WEB_API_PASSWORD", "").strip()
    raw_port = settings.get("CIRCUITPY_WEB_API_PORT", 80)
    try:
        workflow_port = int(raw_port)
    except (TypeError, ValueError):
        workflow_port = 80
    return host, password, workflow_port


def run_lint() -> bool:
    print("=" * 60)
    print("Running lint...")
    print("=" * 60)
    result = subprocess.run(["poetry", "run", "lint"])
    if result.returncode == 0:
        print("\nLint passed.\n")
        return True
    print("\nLint FAILED — aborting deploy.", file=sys.stderr)
    return False


def run_tests() -> bool:
    print("=" * 60)
    print("Running tests...")
    print("=" * 60)
    result = subprocess.run(["pytest", "tests/", "-v", "--tb=short"])
    if result.returncode in (0, 5):
        print("\nTests passed.\n")
        return True
    print("\nTests FAILED — aborting deploy.", file=sys.stderr)
    return False


def deploy_wifi(
    host: str,
    password: str,
    deploy_settings: bool = False,
    *,
    workflow_port: int = 80,
) -> int:
    auth = auth_header(password)
    lib_remote = f"lib/{PACKAGE_NAME}"

    print("=" * 60)
    print(f"Deploying files via WiFi → {host}:{workflow_port}")
    print("(CircuitPython Web Workflow for upload only; terminal stays on WEB_PORT 8080)")
    print("=" * 60)

    print(f"\nChecking Web Workflow on port {workflow_port} ...")
    try:
        check_workflow(host, password, workflow_port)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    print("  Web Workflow OK\n")

    step = 1
    total = 4 if deploy_settings else 3

    print(f"\n[{step}/{total}] Uploading boot.py ...")
    if not BOOT_PY.exists():
        print(f"Error: {BOOT_PY} not found", file=sys.stderr)
        return 1
    put_file(host, "boot.py", BOOT_PY, auth, port=workflow_port)
    print("  uploaded  boot.py")
    step += 1

    if deploy_settings:
        print(f"\n[{step}/{total}] Uploading settings.toml ...")
        if not SETTINGS_PATH.exists():
            print(f"Error: {SETTINGS_PATH} not found", file=sys.stderr)
            return 1
        put_file(host, "settings.toml", SETTINGS_PATH, auth, port=workflow_port)
        print("  uploaded  settings.toml")
        step += 1

    print(f"\n[{step}/{total}] Uploading code.py ...")
    if not CODE_PY.exists():
        print(f"Error: {CODE_PY} not found", file=sys.stderr)
        return 1
    put_file(host, "code.py", CODE_PY, auth, port=workflow_port)
    print("  uploaded  code.py")
    step += 1

    print(f"\n[{step}/{total}] Uploading {PACKAGE_NAME} package ...")
    if not LIB_SRC.exists():
        print(f"Error: {LIB_SRC} not found", file=sys.stderr)
        return 1

    py_files = device_library_files()
    dirs_needed: list[str] = []
    for f in py_files:
        rel = f.relative_to(LIB_SRC)
        parts = rel.parts[:-1]
        for depth in range(len(parts) + 1):
            candidate = lib_remote + "/" + "/".join(parts[:depth])
            if candidate not in dirs_needed:
                dirs_needed.append(candidate)

    for d in dirs_needed:
        mkdir_remote(host, d, auth, port=workflow_port)

    for f in py_files:
        rel = f.relative_to(LIB_SRC)
        remote = lib_remote + "/" + "/".join(rel.parts)
        put_file(host, remote, f, auth, port=workflow_port)
        print(f"  uploaded  {remote}")

    static_files = device_static_files()
    if static_files:
        print(f"\nUploading {len(static_files)} static file(s) ...")
        mkdir_remote(host, "static", auth, port=workflow_port)
        for sf in static_files:
            rel = sf.relative_to(STATIC_DIR)
            remote = "static/" + "/".join(rel.parts)
            parts = remote.split("/")
            for depth in range(2, len(parts)):
                mkdir_remote(host, "/".join(parts[:depth]), auth, port=workflow_port)
            put_file(host, remote, sf, auth, port=workflow_port)
            print(f"  uploaded  {remote}")

    print(
        f"\nDeploy complete — {len(py_files)} library file(s), "
        f"{len(static_files)} static file(s)."
    )
    return 0


def deploy_serial(port: str, deploy_settings: bool = False) -> int:
    print("=" * 60)
    print(f"Deploying via serial → {port}")
    print("=" * 60)

    if not CODE_PY.exists():
        print(f"Error: {CODE_PY} not found", file=sys.stderr)
        return 1
    if not BOOT_PY.exists():
        print(f"Error: {BOOT_PY} not found", file=sys.stderr)
        return 1
    if not LIB_SRC.exists():
        print(f"Error: {LIB_SRC} not found", file=sys.stderr)
        return 1

    py_files = device_library_files()
    lib_remote = f"lib/{PACKAGE_NAME}"
    dirs_to_create: list[str] = [lib_remote]
    for f in py_files:
        rel = f.relative_to(LIB_SRC)
        for depth in range(1, len(rel.parts)):
            d = lib_remote + "/" + "/".join(rel.parts[:depth])
            if d not in dirs_to_create:
                dirs_to_create.append(d)

    print(f"\n[4/4] {PACKAGE_NAME} package")
    print(f"  Creating {len(dirs_to_create)} directories + touching {len(py_files)} files ...")

    mkdir_lines = ["import os"]
    for d in dirs_to_create:
        mkdir_lines += [
            "try:",
            f"    os.mkdir('/{d}')",
            "except OSError:",
            "    pass",
        ]
    for f in py_files:
        rel = f.relative_to(LIB_SRC)
        dest_path = f"/{lib_remote}/" + "/".join(rel.parts)
        mkdir_lines.append(f"open('{dest_path}','wb').close()")
    # Pre-touch root files so mpremote cp -f does not fail when they are missing
    # (fs_exists cannot handle CircuitPython's OSError format for absent paths).
    for root_path in ("/boot.py", "/code.py"):
        mkdir_lines.append(f"open('{root_path}','wb').close()")
    if deploy_settings:
        mkdir_lines.append("open('/settings.toml','wb').close()")

    static_files = device_static_files()
    mkdir_lines += [
        "try:",
        "    os.mkdir('/static')",
        "except OSError:",
        "    pass",
    ]
    for sf in static_files:
        rel = sf.relative_to(STATIC_DIR)
        dest_path = "/static/" + "/".join(rel.parts)
        mkdir_lines.append(f"open('{dest_path}','wb').close()")

    mkdir_code = "\n".join(mkdir_lines) + "\n"

    chain: list[str] = ["mpremote", "connect", port, "+", "exec", mkdir_code]

    if deploy_settings:
        if not SETTINGS_PATH.exists():
            print(f"Error: {SETTINGS_PATH} not found", file=sys.stderr)
            return 1
        chain += ["+", "cp", "-f", str(SETTINGS_PATH), ":settings.toml"]

    chain += ["+", "cp", "-f", str(BOOT_PY), ":boot.py"]
    chain += ["+", "cp", "-f", str(CODE_PY), ":code.py"]

    print(f"  Copying {len(py_files)} library file(s) ...")
    for f in py_files:
        rel = f.relative_to(LIB_SRC)
        chain += ["+", "cp", "-f", str(f), f":{lib_remote}/" + "/".join(rel.parts)]

    for sf in static_files:
        rel = sf.relative_to(STATIC_DIR)
        chain += ["+", "cp", "-f", str(sf), ":static/" + "/".join(rel.parts)]

    result = subprocess.run(chain)
    if result.returncode != 0:
        print("\nError: mpremote file transfer failed.", file=sys.stderr)
        return 1

    print(
        f"\nDeploy complete — {len(py_files)} library, {len(static_files)} static file(s)."
    )
    return 0


def _find_circuitpy() -> Path | None:
    for p in _USB_CANDIDATE_ROOTS:
        if p.is_dir() and (p / "boot_out.txt").exists():
            return p
    return None


def deploy_usb(mount: Path | None, deploy_settings: bool = False) -> int:
    if mount is None:
        mount = _find_circuitpy()

    if mount is None:
        checked = "\n  ".join(str(p) for p in _USB_CANDIDATE_ROOTS)
        print("Error: CIRCUITPY drive not found. Checked:\n  " + checked, file=sys.stderr)
        return 1

    print("=" * 60)
    print(f"Deploying via USB → {mount}")
    print("=" * 60)

    step = 1
    total = 4 if deploy_settings else 3

    print(f"\n[{step}/{total}] Copying boot.py ...")
    shutil.copy2(BOOT_PY, mount / "boot.py")
    step += 1

    if deploy_settings:
        print(f"\n[{step}/{total}] Copying settings.toml ...")
        if not SETTINGS_PATH.exists():
            print(f"Error: {SETTINGS_PATH} not found", file=sys.stderr)
            return 1
        shutil.copy2(SETTINGS_PATH, mount / "settings.toml")
        step += 1

    print(f"\n[{step}/{total}] Copying code.py ...")
    shutil.copy2(CODE_PY, mount / "code.py")
    step += 1

    print(f"\n[{step}/{total}] Copying {PACKAGE_NAME} package ...")
    dest_lib = mount / "lib" / PACKAGE_NAME
    if dest_lib.exists():
        shutil.rmtree(dest_lib)
    dest_lib.mkdir(parents=True)
    for src in device_library_files():
        rel = src.relative_to(LIB_SRC)
        dest = dest_lib / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    py_count = len(device_library_files())
    print(f"  copied  {PACKAGE_NAME}/ → {dest_lib}  ({py_count} files)")

    static_files = device_static_files()
    if static_files:
        dest_static = mount / "static"
        dest_static.mkdir(exist_ok=True)
        for sf in static_files:
            rel = sf.relative_to(STATIC_DIR)
            dest = dest_static / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sf, dest)
        print(f"  copied  static/  ({len(static_files)} files)")

    print(f"\nDeploy complete — eject {mount} safely before unplugging.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Test then deploy to CircuitPython device.")
    parser.add_argument("--skip-tests", action="store_true", help="Deploy without lint/tests")
    parser.add_argument(
        "--settings",
        action="store_true",
        help="Also deploy settings.toml (contains credentials)",
    )
    parser.add_argument("--serial", action="store_true", help="Deploy over USB-serial (mpremote)")
    parser.add_argument(
        "--port",
        metavar="PORT",
        default=_DEFAULT_SERIAL_PORT,
        help=f"Serial port for --serial (default: {_DEFAULT_SERIAL_PORT})",
    )
    parser.add_argument("--usb", action="store_true", help="Deploy over CIRCUITPY mass storage")
    parser.add_argument("--usb-path", metavar="PATH", help="Explicit CIRCUITPY mount path")
    args = parser.parse_args()

    use_serial = args.serial
    use_usb = args.usb or bool(args.usb_path)

    if not args.skip_tests:
        if not run_lint():
            return 1
        if not run_tests():
            return 1

    if use_serial:
        return deploy_serial(args.port, deploy_settings=args.settings)

    if use_usb:
        mount = Path(args.usb_path) if args.usb_path else None
        return deploy_usb(mount, deploy_settings=args.settings)

    host, password, workflow_port = load_settings()
    return deploy_wifi(
        host,
        password,
        deploy_settings=args.settings,
        workflow_port=workflow_port,
    )


if __name__ == "__main__":
    sys.exit(main())
