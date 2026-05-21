"""Resolve CircuitPython library modules for circup-install from pyproject.toml."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

CP_LIB_PREFIX = "adafruit-circuitpython-"

# Top-level modules provided by CircuitPython firmware (ESP32).
_CP_BUILTIN = frozenset(
    {
        "asyncio",
        "binascii",
        "board",
        "builtins",
        "busio",
        "collections",
        "digitalio",
        "errno",
        "gc",
        "io",
        "json",
        "machine",
        "math",
        "microcontroller",
        "micropython",
        "neopixel",  # often from bundle; listed in overrides when declared
        "os",
        "random",
        "re",
        "socketpool",
        "ssl",
        "storage",
        "struct",
        "supervisor",
        "sys",
        "time",
        "traceback",
        "wifi",
    }
)

# PyPI adafruit-circuitpython-* name → bundle folder name(s) under /lib
_OVERRIDES: dict[str, list[str]] = {
    "adafruit-circuitpython-busdevice": ["adafruit_bus_device"],
    "adafruit-circuitpython-neopixel": ["neopixel"],
    "adafruit-circuitpython-sd": ["adafruit_sdcard"],
}


def _normalize_pypi_name(raw: str) -> str:
    return raw.split()[0].split("(")[0].strip().lower().replace("_", "-")


def _derive_module_name(pkg_name: str) -> str:
    suffix = pkg_name.removeprefix(CP_LIB_PREFIX).replace("-", "_")
    return f"adafruit_{suffix}"


def _pypi_to_bundle_modules(pypi_name: str) -> list[str]:
    if pypi_name in _OVERRIDES:
        return list(_OVERRIDES[pypi_name])
    if pypi_name.startswith(CP_LIB_PREFIX):
        return [_derive_module_name(pypi_name)]
    return []


def _load_pyproject(path: Path) -> dict:
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def declared_pypi_packages(pyproject_path: Path) -> list[str]:
    """All declared CircuitPython PyPI package names (deduplicated, stable order)."""
    data = _load_pyproject(pyproject_path)
    names: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        pkg = _normalize_pypi_name(raw)
        if pkg.startswith(CP_LIB_PREFIX) and pkg not in seen:
            seen.add(pkg)
            names.append(pkg)

    for dep in data.get("project", {}).get("dependencies", []):
        add(str(dep))

    cp_deps = (
        data.get("tool", {})
        .get("esp_remote", {})
        .get("circuitpython", {})
        .get("dependencies", [])
    )
    for dep in cp_deps:
        add(str(dep))

    return names


def resolve_bundle_modules(pyproject_path: Path) -> list[str]:
    """Bundle folder names under /lib to install (deduplicated, sorted)."""
    modules: list[str] = []
    seen: set[str] = set()
    for pypi_name in declared_pypi_packages(pyproject_path):
        for mod in _pypi_to_bundle_modules(pypi_name):
            if mod not in seen:
                seen.add(mod)
                modules.append(mod)
    return sorted(modules)


def host_only_skipped(pyproject_path: Path) -> list[str]:
    """Project dependencies that are not installed on the device."""
    data = _load_pyproject(pyproject_path)
    skipped: list[str] = []
    for dep in data.get("project", {}).get("dependencies", []):
        pkg = _normalize_pypi_name(str(dep))
        if not pkg.startswith(CP_LIB_PREFIX):
            skipped.append(pkg)
    return skipped


def firmware_top_level_imports(firmware_dir: Path) -> set[str]:
    """Top-level modules imported by device firmware (non-recursive scan)."""
    found: set[str] = set()
    pattern = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE)
    for path in sorted(firmware_dir.rglob("*.py")):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            found.add(match.group(1).split(".")[0])
    return found - _CP_BUILTIN - {"esp_remote"}


def firmware_missing_bundle_modules(
    pyproject_path: Path,
    firmware_dir: Path,
) -> list[str]:
    """Firmware imports that look like /lib modules but are not declared for circup."""
    installed = set(resolve_bundle_modules(pyproject_path))
    missing: list[str] = []
    for imp in sorted(firmware_top_level_imports(firmware_dir)):
        if imp in installed:
            continue
        if imp.startswith("adafruit") or imp == "neopixel":
            missing.append(imp)
    return missing


def print_dependency_report(pyproject_path: Path, firmware_dir: Path) -> list[str]:
    """Print a human-readable report; return bundle module names to install."""
    modules = resolve_bundle_modules(pyproject_path)
    skipped = host_only_skipped(pyproject_path)
    fw_imports = sorted(firmware_top_level_imports(firmware_dir))
    missing = firmware_missing_bundle_modules(pyproject_path, firmware_dir)

    print("CircuitPython dependency report")
    print("-" * 40)
    if modules:
        print(f"  Bundle modules to install ({len(modules)}):")
        for mod in modules:
            print(f"    - {mod}")
    else:
        print("  Bundle modules to install: (none declared)")

    if skipped:
        print(f"  Host-only (skipped by circup-install):")
        for pkg in skipped:
            print(f"    - {pkg}")

    if fw_imports:
        print(f"  Firmware imports (expect built-in or bundle above):")
        for imp in fw_imports:
            print(f"    - {imp}")
    else:
        print("  Firmware imports: (only built-in / esp_remote)")

    if missing:
        print("  MISSING — add to pyproject.toml [tool.esp_remote.circuitpython]:")
        for imp in missing:
            print(f"    - {imp}")
    else:
        print("  Firmware/bundle check: OK")

    return modules
