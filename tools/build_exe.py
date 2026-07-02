from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


APP_NAME = "番茄发布同步助手"
ROOT_DIR = Path(__file__).resolve().parents[1]
SPEC_NAME = "fanqie-publish-sync.spec"


def run(command: list[str]) -> None:
    print()
    print("$", " ".join(command))
    subprocess.run(command, cwd=ROOT_DIR, check=True)


def remove_build_outputs() -> None:
    for path in (
        ROOT_DIR / "build",
        ROOT_DIR / "dist",
        ROOT_DIR / SPEC_NAME,
        ROOT_DIR / f"{APP_NAME}.spec",
    ):
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def write_spec() -> Path:
    spec_path = ROOT_DIR / SPEC_NAME
    spec_content = """# -*- mode: python ; coding: utf-8 -*-

APP_NAME_FROM_SCRIPT = "__APP_NAME__"

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('frontend', 'frontend'),
        ('logo.png', '.'),
        ('logo.ico', '.'),
    ],
    hiddenimports=[
        'webview.platforms.edgechromium',
        'playwright._impl._driver',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME_FROM_SCRIPT,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['logo.ico'],
)
""".replace("__APP_NAME__", APP_NAME)
    spec_path.write_text(spec_content, encoding="utf-8")
    return spec_path


def install_requirements() -> None:
    requirements = ROOT_DIR / "requirements.txt"
    run([sys.executable, "-m", "pip", "install", "-r", str(requirements)])


def build_executable() -> None:
    spec_path = write_spec()
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(spec_path)])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build fanqie publish sync as a Windows executable.")
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Do not install Python dependencies before building.",
    )
    args = parser.parse_args()

    print("Using Python:", sys.executable)
    print("Project root:", ROOT_DIR)

    remove_build_outputs()

    if not args.skip_install:
        install_requirements()


    build_executable()

    output = ROOT_DIR / "dist" / f"{APP_NAME}.exe"
    print()
    print("Build finished.")
    print("Executable:", output)


if __name__ == "__main__":
    main()
