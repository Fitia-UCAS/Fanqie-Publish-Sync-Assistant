from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


APP_NAME = "番茄发布同步助手"
ROOT_DIR = Path(__file__).resolve().parents[1]
SPEC_NAME = "fanqie-publish-sync.spec"
FRONTEND_DIR = ROOT_DIR / "frontend"
FRONTEND_BUILD_DIR = ROOT_DIR / "frontend_build"
PERSONAL_VIEWS = {"process", "crawler", "character_notes", "plot_notes"}


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
    if FRONTEND_BUILD_DIR.is_dir():
        shutil.rmtree(FRONTEND_BUILD_DIR)


def strip_personal_from_html(text: str) -> str:
    lines = text.split("\n")
    out = []
    skip_depth = 0
    for line in lines:
        if skip_depth == 0:
            is_personal_section = (
                "<section" in line
                and any(f'data-panel="{v}"' in line for v in PERSONAL_VIEWS)
            )
            is_personal_button = (
                "<button" in line
                and any(f'data-view="{v}"' in line for v in PERSONAL_VIEWS)
            )
            if is_personal_section:
                skip_depth = 1
                skip_depth += line.count("<section") - line.count("</section>")
                continue
            if is_personal_button:
                continue
            out.append(line)
        else:
            skip_depth += line.count("<section") - line.count("</section>")
            if skip_depth <= 0:
                skip_depth = 0
    return "\n".join(out)


def strip_personal_from_css(text: str) -> str:
    result = text
    for view in PERSONAL_VIEWS:
        result = re.sub(
            r',?\s*body\[data-current-view="' + view + r'"\]\s*\.view-panel\[data-panel="' + view + r'"\]',
            "",
            result,
        )
    return result


def strip_personal_from_js(text: str) -> str:
    result = text

    result = re.sub(r"const isPersonalView =.*?;", "", result)
    result = re.sub(
        r"const togglePersonalElements =.*?(?:\n.*?)*?\};", "", result, flags=re.DOTALL
    )

    result = re.sub(
        r"process_novel.*?process_novel_batch.*?novel_splitter.*?clean_text_ads.*?clean_text_breaks.*?",
        "",
        result,
    )
    result = re.sub(
        r"character_notes.*?plot_notes.*?",
        "",
        result,
    )

    result = re.sub(
        r"'process': 'process_novel'.*?",
        "",
        result,
    )

    content_lines = result.split("\n")
    filtered_lines = []
    for line in content_lines:
        stripped = line.strip()
        if "personal" not in stripped.lower() and "togglePersonalElements" not in stripped:
            filtered_lines.append(line)
    return "\n".join(filtered_lines)


def prepare_frontend(exclude_personal: bool) -> Path:
    if not exclude_personal:
        return FRONTEND_DIR
    if FRONTEND_BUILD_DIR.exists():
        shutil.rmtree(FRONTEND_BUILD_DIR)
    shutil.copytree(FRONTEND_DIR, FRONTEND_BUILD_DIR)
    for path in FRONTEND_BUILD_DIR.rglob("*.html"):
        path.write_text(strip_personal_from_html(path.read_text(encoding="utf-8")), encoding="utf-8")
    for path in FRONTEND_BUILD_DIR.rglob("*.css"):
        path.write_text(strip_personal_from_css(path.read_text(encoding="utf-8")), encoding="utf-8")
    for path in FRONTEND_BUILD_DIR.rglob("*.js"):
        path.write_text(strip_personal_from_js(path.read_text(encoding="utf-8")), encoding="utf-8")
    return FRONTEND_BUILD_DIR


def cleanup_frontend_build() -> None:
    if FRONTEND_BUILD_DIR.is_dir():
        shutil.rmtree(FRONTEND_BUILD_DIR)


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


def write_spec(frontend_source: Path) -> Path:
    spec_path = ROOT_DIR / SPEC_NAME
    conda_binaries = find_conda_binaries()
    extra_binaries = repr(conda_binaries) if conda_binaries else "[]"
    spec_content = """# -*- mode: python ; coding: utf-8 -*-

APP_NAME_FROM_SCRIPT = "__APP_NAME__"

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=__CONDA_BINARIES__,
    datas=[
        ('__FRONTEND__', 'frontend'),
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
""".replace("__APP_NAME__", APP_NAME).replace(
        "__FRONTEND__", str(frontend_source.as_posix())
    ).replace(
        "__CONDA_BINARIES__", extra_binaries
    )
    spec_path.write_text(spec_content, encoding="utf-8")
    return spec_path


def install_requirements() -> None:
    requirements = ROOT_DIR / "requirements.txt"
    run([sys.executable, "-m", "pip", "install", "-r", str(requirements)])


def build_executable(frontend_source: Path) -> None:
    spec_path = write_spec(frontend_source)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(spec_path)])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build fanqie publish sync as a Windows executable.")
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Do not install Python dependencies before building.",
    )
    parser.add_argument(
        "--exclude-personal",
        action="store_true",
        help="Exclude personal pages (process, crawler, character_notes, plot_notes) from the build.",
    )
    args = parser.parse_args()

    print("Using Python:", sys.executable)
    print("Project root:", ROOT_DIR)

    remove_build_outputs()
    frontend_source = prepare_frontend(args.exclude_personal)

    if not args.skip_install:
        install_requirements()

    build_executable(frontend_source)
    cleanup_frontend_build()

    output = ROOT_DIR / "dist" / f"{APP_NAME}.exe"
    print()
    print("Build finished.")
    print("Executable:", output)


if __name__ == "__main__":
    main()
