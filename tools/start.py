import importlib.util
import os
import shutil
import sys
from pathlib import Path


PROJECT_DIR_NAME = "fanqie-publish-sync"


def ensure_state_json(project_dir: Path) -> None:
    script_dir = Path(__file__).resolve().parent
    src = script_dir / "state.json"
    dst = project_dir / "data" / "auth" / "fanqie" / "default" / "state.json"

    if not src.exists():
        print("[警告] 启动脚本同级目录下未找到 state.json，跳过复制。")
        return

    if dst.exists():
        print(f"[→] 目标 {dst.relative_to(project_dir.parent)} 已存在。")
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"[✓] state.json 已复制到 {dst.relative_to(project_dir.parent)}")


def load_project_main(project_dir: Path):
    main_py = project_dir / "main.py"
    if not main_py.exists():
        raise FileNotFoundError(f"未找到项目启动文件：{main_py}")

    spec = importlib.util.spec_from_file_location("fanqie_publish_sync_main", main_py)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载项目启动文件：{main_py}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir / PROJECT_DIR_NAME

    if not project_dir.is_dir():
        print(f"[错误] 未找到项目目录：{project_dir}")
        print(f"请确认本脚本和 {PROJECT_DIR_NAME} 文件夹放在同一级目录。")
        sys.exit(1)

    os.chdir(project_dir)

    project_dir_str = str(project_dir)
    if project_dir_str not in sys.path:
        sys.path.insert(0, project_dir_str)

    ensure_state_json(project_dir)

    app_main = load_project_main(project_dir)
    app_main.main()


if __name__ == "__main__":
    main()