"""Lint script: Python style, static web paths, and optional HTML lint.

Invoked via ``poetry run lint`` or ``poetry run format``.
"""

import shutil
import subprocess
import sys

from scripts.static_web_check import main as static_web_check_main


def main() -> int:
    """Run all linting tools on src and tests directories."""
    targets = ["src", "tests"]
    failed = False

    print("Running static web checks...")
    if static_web_check_main() != 0:
        failed = True

    print("\nRunning isort...")
    result = subprocess.run(["isort", "--check-only", "--diff", *targets])
    if result.returncode != 0:
        failed = True

    print("\nRunning black...")
    result = subprocess.run(["black", "--check", "--diff", *targets])
    if result.returncode != 0:
        failed = True

    print("\nRunning flake8...")
    result = subprocess.run(["flake8", *targets])
    if result.returncode != 0:
        failed = True

    if shutil.which("djlint"):
        print("\nRunning djlint on static/ ...")
        result = subprocess.run(
            ["djlint", "static", "--check", "--profile", "html", "--extension", "html"],
        )
        if result.returncode != 0:
            failed = True
    else:
        print("\nSkipping djlint (install dev deps: poetry install)")

    if failed:
        print("\nLinting failed. Run 'poetry run format' to auto-fix issues.")
        return 1

    print("\nAll linting checks passed!")
    return 0


def format_code() -> int:
    """Auto-format code with isort and black; HTML with djlint."""
    targets = ["src", "tests"]

    print("Running isort...")
    subprocess.run(["isort", *targets])

    print("\nRunning black...")
    subprocess.run(["black", *targets])

    if shutil.which("djlint"):
        print("\nRunning djlint --reformat on static/ ...")
        subprocess.run(["djlint", "static", "--reformat", "--profile", "html"])

    print("\nFormatting complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
