from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "番茄发布与同步助手"
ROOT_DIR = Path(__file__).resolve().parents[1]

SPEC_NAME = "fanqie-publish-sync.spec"
FRONTEND_ROOT = ROOT_DIR / "frontend"
FRONTEND_VARIANTS = {"release", "personal"}
DEFAULT_BUILD_FRONTEND_VARIANT = "release"

RUNTIME_HOOK = ROOT_DIR / "tools" / "_pyinstaller_frontend_variant.py"
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"
OUTPUT_EXE = DIST_DIR / f"{APP_NAME}.exe"


def run(command: list[str]) -> None:
    print()
    print("$", " ".join(command))
    subprocess.run(command, cwd=ROOT_DIR, check=True)


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def remove_previous_executable() -> None:
    """
    删除上一次编译出来的 exe，但不删除 dist/data 这类运行配置数据。
    """
    if OUTPUT_EXE.exists():
        print(f"Removing previous executable: {OUTPUT_EXE}")
        remove_path(OUTPUT_EXE)

    old_onedir_output = DIST_DIR / APP_NAME
    if old_onedir_output.exists():
        print(f"Removing previous onedir output: {old_onedir_output}")
        remove_path(old_onedir_output)


def remove_build_outputs() -> None:
    """
    编译前清理构建产物。

    注意：
    不直接删除整个 dist 目录，避免误删 dist/data 里的用户配置。
    """
    for path in (
        BUILD_DIR,
        ROOT_DIR / SPEC_NAME,
        ROOT_DIR / f"{APP_NAME}.spec",
        RUNTIME_HOOK,
    ):
        remove_path(path)

    remove_previous_executable()


def remove_generated_build_files() -> None:
    """
    编译结束后清理临时生成文件。
    """
    for path in (
        ROOT_DIR / SPEC_NAME,
        ROOT_DIR / f"{APP_NAME}.spec",
        RUNTIME_HOOK,
    ):
        remove_path(path)


def frontend_dir(variant: str) -> Path:
    path = FRONTEND_ROOT / variant

    if variant not in FRONTEND_VARIANTS:
        raise ValueError(f"未知前端版本：{variant}，可选：{', '.join(sorted(FRONTEND_VARIANTS))}")

    if not (path / "index.html").exists():
        raise FileNotFoundError(f"未找到前端入口：{path / 'index.html'}")

    return path


def find_conda_binaries() -> list[tuple[str, str]]:
    python_dir = Path(sys.executable).parent
    candidates = [
        python_dir / "Library" / "bin",
        python_dir.parent / "Library" / "bin",
    ]

    for dll_dir in candidates:
        if dll_dir.is_dir():
            return [(str(dll_dir), ".")]

    return []


def write_runtime_hook(variant: str) -> Path:
    RUNTIME_HOOK.write_text(
        "import os\n"
        f"os.environ.setdefault('FANQIE_FRONTEND_VARIANT', {variant!r})\n",
        encoding="utf-8",
    )
    return RUNTIME_HOOK


def write_spec(variant: str) -> Path:
    source = frontend_dir(variant)
    spec_path = ROOT_DIR / SPEC_NAME
    runtime_hook = write_runtime_hook(variant)
    conda_binaries = find_conda_binaries()

    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

APP_NAME_FROM_SCRIPT = {APP_NAME!r}


a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries={conda_binaries!r},
    datas=[
        ({str(source.as_posix())!r}, {'frontend/' + variant!r}),
        ('logo.png', '.'),
        ('logo.ico', '.'),
    ],
    hiddenimports=[
        'webview.platforms.edgechromium',
        'playwright._impl._driver',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[{str(runtime_hook.as_posix())!r}],
    excludes=[
        'tkinter', 'test', 'unittest', 'pydoc', 'turtle', 'xmlrpc',
    ],
    noarchive=False,
    optimize=1,
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
    upx=False,
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
'''

    spec_path.write_text(spec_content, encoding="utf-8")
    return spec_path


def install_requirements() -> None:
    requirements = ROOT_DIR / "requirements.txt"
    run([sys.executable, "-m", "pip", "install", "-r", str(requirements)])


def build_executable(variant: str) -> None:
    spec_path = write_spec(variant)

    try:
        run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(spec_path)])
    finally:
        remove_generated_build_files()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Fanqie Publish Sync as a Windows windowed executable."
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Do not install Python dependencies before building.",
    )
    parser.add_argument(
        "--frontend",
        choices=sorted(FRONTEND_VARIANTS),
        default=DEFAULT_BUILD_FRONTEND_VARIANT,
        help=f"Choose which frontend variant to package. Default: {DEFAULT_BUILD_FRONTEND_VARIANT}.",
    )

    args = parser.parse_args()

    print("Using Python:", sys.executable)
    print("Project root:", ROOT_DIR)
    print("Frontend variant:", args.frontend)

    remove_build_outputs()
    frontend_dir(args.frontend)

    if not args.skip_install:
        install_requirements()

    build_executable(args.frontend)

    print()
    print("Build finished.")
    print("Executable:", OUTPUT_EXE)


if __name__ == "__main__":
    main()