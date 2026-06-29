from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import append_jsonl, read_json, read_jsonl, write_json
from backend.adapters.webnovel_writer.webnovel_writer_models import CONTROL_ENTITY_BUCKETS, DEFAULT_STATE, ENTITY_BUCKETS, WriterPaths, WriterProjectMeta, fresh_state, now_iso
from backend.adapters.webnovel_writer.webnovel_writer_markdown import blueprint_markdown_template, entity_markdown_template, parse_blueprint_markdown, parse_entity_markdown
from backend.adapters.webnovel_writer.webnovel_writer_model_router import ensure_model_routes
from backend.adapters.webnovel_writer.webnovel_writer_story_config import default_story_config
from backend.shared.filename.filename_sanitizer import safe_filename
from backend.shared.text_file.text_file_storage import backup_file, ensure_dir, read_text_auto, write_text


def make_project_id(title: str) -> str:
    safe = safe_filename(title or "未命名小说")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{safe}_{stamp}"


class WebnovelWriterStorage:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = ensure_dir(root_dir)

    def project_root(self, project_id: str) -> Path:
        if not project_id:
            raise ValueError("project_id 为空，请先选择小说项目目录。")
        raw = str(project_id).strip()
        candidate = Path(raw).expanduser()
        if candidate.is_absolute() or re.match(r"^[A-Za-z]:[\\/]", raw) or raw.startswith("\\\\"):
            return candidate
        return self.root_dir / safe_filename(raw)

    def paths(self, project_id: str) -> WriterPaths:
        root = self.project_root(project_id)
        return WriterPaths(
            root=str(root),
            meta=str(root / "project.json"),
            settings=str(root / "settings.json"),
            story_config=str(root / "story_config.json"),
            state=str(root / "story_state.json"),
            outlines=str(root / "outlines"),
            volumes=str(root / "volumes"),
            blueprints=str(root / "blueprints"),
            chapters=str(root / "chapters"),
            drafts=str(root / "drafts"),
            rejected=str(root / "rejected"),
            reviews=str(root / "reviews"),
            commits=str(root / "commits"),
            runtime=str(root / "runtime"),
            artifacts=str(root / "artifacts"),
            runs=str(root / "runs"),
            validation=str(root / "validation"),
            indexes=str(root / "indexes"),
            exports=str(root / "exports"),
            control=str(root / "writer_control"),
        )

    def ensure_project_dirs(self, project_id: str) -> WriterPaths:
        paths = self.paths(project_id)
        for value in paths.to_dict().values():
            p = Path(value)
            if p.suffix:
                ensure_dir(p.parent)
            else:
                ensure_dir(p)
        for sub in ["backups", "source_settings", "events", "writer_control/entities", "writer_control/blueprints", "writer_control/reports", "writer_control/context_packs", "writer_control/relations", "writer_control/templates", "writer_control/models", "writer_control/genres"]:
            ensure_dir(Path(paths.root) / sub)
        self._ensure_control_templates(paths)
        self._ensure_reference_init_scaffold(paths)
        try:
            ensure_model_routes(self, project_id)
        except Exception:
            pass
        return paths

    def _ensure_reference_init_scaffold(self, paths: WriterPaths) -> None:
        """Create the human-editable project scaffold promised by the reference projects.

        The upstream webnovel-writer init command creates runtime state, setting/outlining
        folders and an RAG .env example. Keep this as project output only; it is not a
        release-note markdown file and is safe to generate inside user projects.
        """
        root = Path(paths.root)
        setting_dir = ensure_dir(root / "设定集")
        outline_dir = ensure_dir(root / "大纲")
        review_dir = ensure_dir(root / "审查报告")

        env_path = root / ".env.example"
        if not env_path.exists():
            write_text(env_path, """# RAG / semantic recall configuration
# Compatible with OpenAI-style embedding/rerank services. Fill only what you use.

EMBED_BASE_URL=https://api-inference.modelscope.cn/v1
EMBED_MODEL=Qwen/Qwen3-Embedding-8B
EMBED_API_KEY=your_embed_api_key

RERANK_BASE_URL=https://api.jina.ai/v1
RERANK_MODEL=jina-reranker-v3
RERANK_API_KEY=your_rerank_api_key

# Optional generation model environment variables
LLM_PLATFORM=deepseek
DEEPSEEK_API_KEY=your_generation_api_key
DEEPSEEK_MODEL_NAME=deepseek-chat
""")

        setting_templates = {
            "世界观.md": "# 世界观\n\n## 核心规则\n- \n\n## 不可违反\n- \n",
            "力量体系.md": "# 力量体系\n\n## 等级/境界\n- \n\n## 代价与限制\n- \n",
            "主角卡.md": "# 主角卡\n\n- 姓名：\n- 目标：\n- 弱点：\n- 金手指：\n",
            "反派设计.md": "# 反派设计\n\n## 核心反派\n- 名称：\n- 目标：\n- 与主角冲突：\n",
        }
        for name, content in setting_templates.items():
            path = setting_dir / name
            if not path.exists():
                write_text(path, content)

        outline_templates = {
            "总纲.md": "# 总纲\n\n## 一句话故事\n\n## 主线目标\n\n## 分卷规划\n- 第1卷：\n",
            "爽点规划.md": "# 爽点规划\n\n## 核心爽点循环\n- 压迫 → 破局 → 反转 → 收益\n\n## 章末钩子库\n- \n",
            "时间线.md": "# 时间线\n\n| 章节 | 时间 | 事件 | 影响 |\n|---|---|---|---|\n",
        }
        for name, content in outline_templates.items():
            path = outline_dir / name
            if not path.exists():
                write_text(path, content)

        keep = review_dir / ".gitkeep"
        if not keep.exists():
            write_text(keep, "")

    def _ensure_control_templates(self, paths: WriterPaths) -> None:
        control = Path(paths.control)
        readme = control / "README.md"
        if not readme.exists():
            write_text(readme, """# writer_control

这里是网文项目的后端控制目录。建议编辑 Markdown，JSON 由后端同步生成。

- entities/*.md：人类编辑入口，角色、地点、势力、物品、伏笔、冲突等资料。
- entities/*.json：机器缓存；可读，不建议手改。
- blueprints/chapter_0001.md：章节蓝图编辑入口。
- blueprints/chapter_0001.json：蓝图缓存；由 Markdown 同步生成。
- context_packs/：写章前上下文包。
- reports/：全书体检与同步报告。

运行 `python -m backend.adapters.webnovel_writer.webnovel_writer_cli sync --project <项目目录>` 会把 Markdown 编译成 JSON。
""")
        template_dir = control / "templates"
        if not (template_dir / "ENTITY_TEMPLATE.md").exists():
            write_text(template_dir / "ENTITY_TEMPLATE.md", entity_markdown_template("characters"))
        if not (template_dir / "BLUEPRINT_TEMPLATE.md").exists():
            write_text(template_dir / "BLUEPRINT_TEMPLATE.md", blueprint_markdown_template(1))
        for bucket in CONTROL_ENTITY_BUCKETS:
            json_path = control / "entities" / f"{bucket}.json"
            md_path = control / "entities" / f"{bucket}.md"
            if not md_path.exists():
                write_text(md_path, entity_markdown_template(bucket))
            if not json_path.exists():
                write_json(json_path, {})
        bp_md = control / "blueprints" / "chapter_0001.md"
        bp_json = control / "blueprints" / "chapter_0001.json"
        if not bp_md.exists():
            write_text(bp_md, blueprint_markdown_template(1))
        if not bp_json.exists():
            write_json(bp_json, {
                "chapter_no": 1,
                "title": "章节标题",
                "goal": "",
                "pov": "",
                "main_scene": "",
                "required_characters": [],
                "required_locations": [],
                "required_factions": [],
                "must_cover_nodes": [],
                "forbidden_zones": [],
                "conflict": "",
                "payoff_or_emotion": "",
                "ending_hook": "",
                "fact_writeback_notes": []
            })

    def create_or_update_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_path = str(payload.get("storyConfigPath") or payload.get("story_config_path") or "").strip()
        novel_file = str(payload.get("novelFilePath") or payload.get("novel_file") or "").strip()
        project_path = str(payload.get("projectPath") or payload.get("project_path") or "").strip()
        title = str(payload.get("title") or "").strip()
        if not title:
            title = self._infer_title_from_source(source_path)
        if not title and novel_file:
            title = Path(novel_file).stem
        title = title or "未命名小说"

        project_id = str(payload.get("projectId") or payload.get("project_id") or "").strip()
        if project_path:
            project_id = project_path
        elif not project_id and novel_file:
            project_id = str(Path(novel_file).expanduser().parent)
        elif not project_id:
            project_id = make_project_id(title)

        paths = self.ensure_project_dirs(project_id)
        old = read_json(paths.meta, {}) or {}

        novel_path = Path(novel_file).expanduser() if novel_file else None
        if novel_path:
            ensure_dir(novel_path.parent)
            if not novel_path.exists():
                write_text(novel_path, "")

        story_cfg_path = Path(paths.story_config)
        story_cfg = read_json(story_cfg_path, None) if story_cfg_path.exists() else None
        if not isinstance(story_cfg, dict):
            story_cfg = default_story_config()
        story_cfg = self._merge_story_config_defaults(story_cfg)
        existing_profile = story_cfg.get("story_profile", {}) if isinstance(story_cfg, dict) else {}
        should_import_source = bool(source_path) and (not story_cfg_path.exists() or str(existing_profile.get("source_setting_file") or "") != source_path)
        imported_cfg = self._story_config_from_source(source_path, title) if should_import_source else None
        if imported_cfg:
            story_cfg = self._merge_story_config_defaults(imported_cfg)
            try:
                source = Path(source_path).expanduser()
                if source.exists() and source.is_file():
                    raw_dir = ensure_dir(Path(paths.root) / "source_settings")
                    write_text(raw_dir / source.name, read_text_auto(source))
            except Exception:
                pass

        story_profile = story_cfg.setdefault("story_profile", {})
        if title and not story_profile.get("title"):
            story_profile["title"] = title
        if novel_path:
            story_cfg.setdefault("source_files", {})["novel_txt"] = str(novel_path)

        meta = WriterProjectMeta(
            project_id=project_id,
            title=title or str(story_profile.get("title") or old.get("title") or "未命名小说"),
            genre=str(payload.get("genre") or old.get("genre") or story_profile.get("genre") or "").strip(),
            premise=str(payload.get("premise") or old.get("premise") or story_profile.get("premise") or "").strip(),
            target_audience=str(payload.get("targetAudience") or payload.get("target_audience") or old.get("target_audience") or story_profile.get("target_audience") or "").strip(),
            style_brief=str(payload.get("styleBrief") or payload.get("style_brief") or old.get("style_brief") or story_profile.get("style_brief") or "").strip(),
            project_path=str(Path(paths.root)),
            novel_file=str(novel_path) if novel_path else str(old.get("novel_file") or ""),
            story_config_source=source_path or str(old.get("story_config_source") or ""),
            created_at=str(old.get("created_at") or now_iso()),
            updated_at=now_iso(),
        )
        write_json(paths.meta, meta.to_dict())
        if not Path(paths.state).exists():
            write_json(paths.state, fresh_state())
        else:
            self.save_state(project_id, self.load_state(project_id))
        write_json(story_cfg_path, story_cfg)
        self.import_novel_file_if_empty(project_id)
        self.rebuild_chapter_index(project_id)
        self.sync_novel_file(project_id)
        return {"meta": meta.to_dict(), "paths": paths.to_dict()}

    def _merge_story_config_defaults(self, cfg: dict[str, Any]) -> dict[str, Any]:
        base = default_story_config()

        def merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
            for k, v in src.items():
                if isinstance(v, dict) and isinstance(dst.get(k), dict):
                    merge(dst[k], v)
                else:
                    dst[k] = v
            return dst

        return merge(base, cfg if isinstance(cfg, dict) else {})

    def _infer_title_from_source(self, source_path: str) -> str:
        if not source_path:
            return ""
        source = Path(source_path).expanduser()
        if not source.exists() or not source.is_file():
            return ""
        try:
            if source.suffix.lower() == ".json":
                data = json.loads(read_text_auto(source))
                if isinstance(data, dict):
                    profile = data.get("story_profile") if isinstance(data.get("story_profile"), dict) else {}
                    return str(profile.get("title") or data.get("title") or "").strip()
            raw = read_text_auto(source)
            for pattern in (r"^#\s*[《<]?([^》>\n#]+)[》>]?(?:\s*设定)?\s*$", r"^##\s*书名\s*\n+\s*[《<]?([^》>\n]+)[》>]?"):
                match = re.search(pattern, raw, re.M)
                if match:
                    title = match.group(1).strip()
                    title = re.sub(r"设定$", "", title).strip(" ：:《》<>")
                    if title:
                        return title
            return source.stem
        except Exception:
            return source.stem

    def _story_config_from_source(self, source_path: str, title: str) -> dict[str, Any] | None:
        if not source_path:
            return None
        source = Path(source_path).expanduser()
        if not source.exists() or not source.is_file():
            return None
        suffix = source.suffix.lower()
        if suffix == ".json":
            try:
                data = json.loads(read_text_auto(source))
                if isinstance(data, dict):
                    return data
            except Exception:
                return None
        if suffix in {".md", ".txt"}:
            raw = read_text_auto(source)
            cfg = default_story_config()
            profile = cfg.setdefault("story_profile", {})
            profile["title"] = title or profile.get("title") or source.stem
            profile["source_setting_file"] = str(source)
            profile["raw_setting_markdown"] = raw
            cfg.setdefault("source_files", {})["story_setting"] = str(source)
            self._extract_profile_from_markdown(raw, profile)
            return cfg
        return None

    def _extract_profile_from_markdown(self, raw: str, profile: dict[str, Any]) -> None:
        mapping = {
            "题材": "genre",
            "类型": "genre",
            "核心创意": "premise",
            "简介": "premise",
            "目标读者": "target_audience",
            "文风": "style_brief",
            "世界概要": "world_summary",
            "世界观": "world_summary",
            "核心钩子": "core_hook",
            "第一卷目标": "first_volume_goal",
        }
        for cn, key in mapping.items():
            match = re.search(rf"(?:^|\n)#+\s*{re.escape(cn)}\s*\n+([\s\S]*?)(?=\n#+\s|\Z)", raw)
            if match and not profile.get(key):
                profile[key] = match.group(1).strip()[:3000]

    def list_projects(self) -> list[dict[str, Any]]:
        rows = []
        if not self.root_dir.exists():
            return []
        for root in sorted(self.root_dir.iterdir(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
            if not root.is_dir():
                continue
            meta_path = root / "project.json"
            if not meta_path.exists():
                continue
            meta = read_json(meta_path, {}) or {}
            rows.append({
                "projectId": meta.get("project_id") or root.name,
                "title": meta.get("title") or root.name,
                "genre": meta.get("genre") or "",
                "updatedAt": meta.get("updated_at") or "",
                "path": str(root),
            })
        return rows

    def load_project(self, project_id: str) -> dict[str, Any]:
        paths = self.ensure_project_dirs(project_id)
        meta = read_json(paths.meta, {}) or {}
        state = self.load_state(project_id)
        return {
            "meta": meta,
            "state": state,
            "storyConfig": self.load_story_config(project_id),
            "paths": paths.to_dict(),
            "chapters": self.list_chapters(project_id),
            "blueprints": self.list_blueprints(project_id),
            "recallIndex": self.index_summary(project_id),
        }

    def load_meta(self, project_id: str) -> dict[str, Any]:
        return read_json(self.paths(project_id).meta, {}) or {}

    def load_state(self, project_id: str) -> dict[str, Any]:
        state = read_json(self.paths(project_id).state, None)
        if not isinstance(state, dict):
            state = fresh_state()
        merged = json.loads(json.dumps(DEFAULT_STATE, ensure_ascii=False))
        merged.update(state)
        for key, default in DEFAULT_STATE.items():
            if isinstance(default, dict) and not isinstance(merged.get(key), dict):
                merged[key] = {}
            elif isinstance(default, list) and not isinstance(merged.get(key), list):
                merged[key] = []
        if "project_clock" not in merged or not isinstance(merged["project_clock"], dict):
            merged["project_clock"] = {"created_at": now_iso(), "updated_at": now_iso()}
        return merged

    def save_state(self, project_id: str, state: dict[str, Any]) -> Path:
        state = dict(state or {})
        clock = state.setdefault("project_clock", {})
        clock.setdefault("created_at", now_iso())
        clock["updated_at"] = now_iso()
        return write_json(self.paths(project_id).state, state)

    def load_story_config(self, project_id: str) -> dict[str, Any]:
        cfg = read_json(self.paths(project_id).story_config, None)
        return self._merge_story_config_defaults(cfg if isinstance(cfg, dict) else {})

    def save_outline(self, project_id: str, filename: str, text: str) -> Path:
        paths = self.ensure_project_dirs(project_id)
        return write_text(Path(paths.outlines) / f"{safe_filename(filename)}.md", str(text or ""))

    def latest_outline_text(self, project_id: str) -> str:
        root = Path(self.paths(project_id).outlines)
        if not root.exists():
            return ""
        files = sorted(root.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        return read_text_auto(files[0]) if files else ""

    def save_blueprint(self, project_id: str, chapter_no: int, text: str) -> Path:
        paths = self.ensure_project_dirs(project_id)
        return write_text(Path(paths.blueprints) / f"第{chapter_no:04d}章_蓝图.md", str(text or ""))

    def save_blueprint_json(self, project_id: str, chapter_no: int, data: dict[str, Any]) -> Path:
        paths = self.ensure_project_dirs(project_id)
        return write_json(Path(paths.blueprints) / f"第{chapter_no:04d}章_蓝图.json", data)

    def load_blueprint(self, project_id: str, chapter_no: int) -> str:
        path = Path(self.paths(project_id).blueprints) / f"第{chapter_no:04d}章_蓝图.md"
        return read_text_auto(path) if path.exists() else ""

    def load_blueprint_json(self, project_id: str, chapter_no: int) -> dict[str, Any]:
        path = Path(self.paths(project_id).blueprints) / f"第{chapter_no:04d}章_蓝图.json"
        data = read_json(path, {})
        return data if isinstance(data, dict) else {}

    def save_chapter(self, project_id: str, chapter_no: int, title: str, text: str) -> Path:
        paths = self.ensure_project_dirs(project_id)
        clean_title = safe_filename(title or f"第{chapter_no}章")
        folder = Path(paths.chapters)
        # Avoid two files for the same chapter after title changes.
        for old in folder.glob(f"第{chapter_no:04d}章_*.txt"):
            if old.exists():
                backup_dir = Path(paths.root) / "backups" / "chapters"
                try:
                    backup_file(old, backup_dir)
                except Exception:
                    pass
                old.unlink(missing_ok=True)
        chapter_path = write_text(folder / f"第{chapter_no:04d}章_{clean_title}.txt", str(text or "").strip() + "\n")
        self.rebuild_chapter_index(project_id)
        self.sync_novel_file(project_id)
        return chapter_path

    def load_chapter(self, project_id: str, chapter_no: int) -> tuple[Path | None, str]:
        candidates = sorted(Path(self.paths(project_id).chapters).glob(f"第{chapter_no:04d}章_*.txt"))
        if not candidates:
            return None, ""
        path = candidates[0]
        return path, read_text_auto(path)

    def save_review(self, project_id: str, chapter_no: int, review: dict[str, Any]) -> Path:
        return write_json(Path(self.paths(project_id).reviews) / f"第{chapter_no:04d}章_review.json", review)

    def save_commit(self, project_id: str, chapter_no: int, commit: dict[str, Any]) -> Path:
        path = write_json(Path(self.paths(project_id).commits) / f"第{chapter_no:04d}章_commit.json", commit)
        self.append_event(project_id, "chapter_committed", commit)
        return path

    def save_draft(self, project_id: str, chapter_no: int, title: str, text: str, *, rejected: bool = False) -> Path:
        paths = self.ensure_project_dirs(project_id)
        clean_title = safe_filename(title or f"第{chapter_no}章")
        folder = Path(paths.rejected if rejected else paths.drafts)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S") if rejected else "latest"
        return write_text(folder / f"第{chapter_no:04d}章_{clean_title}_{stamp}.txt", str(text or "").strip() + "\n")

    def save_artifact(self, project_id: str, chapter_no: int, name: str, data: Any) -> Path:
        paths = self.ensure_project_dirs(project_id)
        folder = Path(paths.artifacts) / f"第{chapter_no:04d}章"
        return write_json(folder / f"{safe_filename(name)}.json", data)

    def save_runtime_text(self, project_id: str, chapter_no: int, name: str, text: str) -> Path:
        paths = self.ensure_project_dirs(project_id)
        folder = Path(paths.runtime) / f"第{chapter_no:04d}章"
        return write_text(folder / f"{safe_filename(name)}.md", str(text or ""))

    def save_run(self, project_id: str, chapter_no: int, data: dict[str, Any]) -> Path:
        paths = self.ensure_project_dirs(project_id)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return write_json(Path(paths.runs) / f"第{chapter_no:04d}章_{stamp}.json", data)

    def save_validation(self, project_id: str, name: str, data: dict[str, Any]) -> Path:
        paths = self.ensure_project_dirs(project_id)
        return write_json(Path(paths.validation) / f"{safe_filename(name)}.json", data)

    def append_event(self, project_id: str, event_type: str, payload: dict[str, Any]) -> Path:
        paths = self.ensure_project_dirs(project_id)
        event_path = Path(paths.root) / "events" / "event_log.jsonl"
        events = read_jsonl(event_path)
        prev_fingerprint = ""
        if events and isinstance(events[-1], dict):
            prev_fingerprint = str(events[-1].get("fingerprint") or "")
        event = {
            "event_id": self._event_id(event_type, payload),
            "type": event_type,
            "at": now_iso(),
            "prev_fingerprint": prev_fingerprint,
            "payload": payload,
        }
        event["fingerprint"] = _event_chain_fingerprint(prev_fingerprint, event)
        return append_jsonl(event_path, event)

    def read_events(self, project_id: str) -> list[Any]:
        return read_jsonl(Path(self.paths(project_id).root) / "events" / "event_log.jsonl")

    def sync_control_files(self, project_id: str) -> dict[str, Any]:
        """Compile writer_control Markdown/JSON into machine state.

        Markdown is the human source. JSON files under writer_control are caches.
        A sync manifest tracks which entities/blueprints were last managed by this
        folder, so deleting an entry from Markdown no longer leaves stale machine
        state behind.
        """
        paths = self.ensure_project_dirs(project_id)
        state = self.load_state(project_id)
        root = Path(paths.root)
        control = Path(paths.control)
        issues: list[dict[str, Any]] = []
        changed = False
        parsed_markdown: list[str] = []
        generated: list[str] = []
        manifest_path = control / ".sync_manifest.json"
        old_manifest = read_json(manifest_path, {}) or {}
        old_entity_manifest = old_manifest.get("entities") if isinstance(old_manifest.get("entities"), dict) else {}
        old_blueprints = {int(x) for x in (old_manifest.get("blueprints") or []) if str(x).isdigit()}
        new_manifest: dict[str, Any] = {"schema_version": 2, "synced_at": now_iso(), "entities": {}, "blueprints": []}

        for bucket in CONTROL_ENTITY_BUCKETS:
            md_path = control / "entities" / f"{bucket}.md"
            json_path = control / "entities" / f"{bucket}.json"
            source_path: Path = json_path
            data: Any = None
            mapping: dict[str, Any] | None = None

            if md_path.exists():
                source_path = md_path
                try:
                    mapping, md_issues = parse_entity_markdown(read_text_auto(md_path), bucket)
                    for item in md_issues:
                        item.setdefault("path", str(md_path))
                        issues.append(item)
                    write_json(json_path, mapping)
                    parsed_markdown.append(str(md_path))
                    generated.append(str(json_path))
                    data = mapping
                except Exception as exc:
                    issues.append({"level": "error", "type": "control_markdown", "path": str(md_path), "message": f"Markdown 解析失败：{exc}"})
                    data = read_json(json_path, None)
            else:
                data = read_json(json_path, None)

            if data is None:
                data = {}
                write_json(json_path, data)
                generated.append(str(json_path))
            mapping = _normalise_entity_map(data, bucket)
            if mapping is None:
                issues.append({"level": "error", "type": "control_json", "path": str(json_path), "message": f"{json_path.name} 必须是对象或对象数组。"})
                continue

            current = state.setdefault(bucket, {})
            if not isinstance(current, dict):
                current = {}
                state[bucket] = current
            old_bucket = old_entity_manifest.get(bucket) if isinstance(old_entity_manifest, dict) else {}
            old_names = set(old_bucket.get("names") or old_bucket or []) if isinstance(old_bucket, (dict, list)) else set()
            new_names = set(mapping.keys())
            for stale_name in sorted(old_names - new_names):
                stale = current.get(stale_name)
                if isinstance(stale, dict) and (stale.get("_control_managed") or stale_name in old_names):
                    del current[stale_name]
                    changed = True

            rel_source = str(source_path.relative_to(root)) if source_path.is_relative_to(root) else str(source_path)
            for name, value in mapping.items():
                if not isinstance(value, dict):
                    value = {"status": value}
                before = dict(current.get(name) or {}) if isinstance(current.get(name), dict) else {}
                merged = dict(before)
                merged.update(value)
                merged.setdefault("name", name)
                merged["_control_managed"] = True
                merged["_control_source"] = rel_source
                before_cmp = dict(before)
                merged_cmp = dict(merged)
                before_cmp.pop("_control_synced_at", None)
                merged_cmp.pop("_control_synced_at", None)
                if before_cmp != merged_cmp:
                    merged["_control_synced_at"] = now_iso()
                    current[name] = merged
                    changed = True
                elif name not in current:
                    current[name] = merged
                    changed = True
            new_manifest["entities"][bucket] = {"source": rel_source, "names": sorted(new_names)}

        parsed_blueprints: set[int] = set()
        for md_path in sorted((control / "blueprints").glob("chapter_*.md")):
            try:
                data, md_issues = parse_blueprint_markdown(read_text_auto(md_path))
                for item in md_issues:
                    item.setdefault("path", str(md_path))
                    issues.append(item)
                chapter_no = _chapter_no_from_control_file(md_path, data)
                if not chapter_no:
                    issues.append({"level": "warning", "type": "blueprint_markdown", "path": str(md_path), "message": "蓝图 Markdown 无法识别章号。"})
                    continue
                data["chapter_no"] = chapter_no
                data["_control_managed"] = True
                data["_control_source"] = str(md_path.relative_to(root)) if md_path.is_relative_to(root) else str(md_path)
                json_path = control / "blueprints" / f"chapter_{chapter_no:04d}.json"
                write_json(json_path, data)
                self.save_blueprint_json(project_id, chapter_no, data)
                self.save_blueprint(project_id, chapter_no, read_text_auto(md_path))
                parsed_blueprints.add(chapter_no)
                parsed_markdown.append(str(md_path))
                generated.extend([str(json_path), str(Path(paths.blueprints) / f"第{chapter_no:04d}章_蓝图.json")])
                changed = True
            except Exception as exc:
                issues.append({"level": "error", "type": "blueprint_markdown", "path": str(md_path), "message": f"Markdown 解析失败：{exc}"})

        for json_path in sorted((control / "blueprints").glob("chapter_*.json")):
            data = read_json(json_path, None)
            if not isinstance(data, dict):
                issues.append({"level": "error", "type": "control_json", "path": str(json_path), "message": "蓝图必须是 JSON object。"})
                continue
            chapter_no = _chapter_no_from_control_file(json_path, data)
            if not chapter_no:
                issues.append({"level": "warning", "type": "blueprint_name", "path": str(json_path), "message": "蓝图文件名或 chapter_no 无法识别。"})
                continue
            if chapter_no in parsed_blueprints:
                continue
            data["chapter_no"] = chapter_no
            data["_control_managed"] = True
            data.setdefault("_control_source", str(json_path.relative_to(root)) if json_path.is_relative_to(root) else str(json_path))
            self.save_blueprint_json(project_id, chapter_no, data)
            md_path = control / "blueprints" / f"chapter_{chapter_no:04d}.md"
            if not md_path.exists():
                md = _blueprint_to_markdown(data)
                write_text(md_path, md)
                self.save_blueprint(project_id, chapter_no, md)
                generated.append(str(md_path))
            parsed_blueprints.add(chapter_no)
            changed = True

        for stale_no in sorted(old_blueprints - parsed_blueprints):
            for stale in [
                control / "blueprints" / f"chapter_{stale_no:04d}.json",
                Path(paths.blueprints) / f"第{stale_no:04d}章_蓝图.json",
                Path(paths.blueprints) / f"第{stale_no:04d}章_蓝图.md",
            ]:
                if stale.exists():
                    backup_file(stale, Path(paths.root) / "backups" / "writer_control_removed")
                    stale.unlink(missing_ok=True)
                    changed = True

        new_manifest["blueprints"] = sorted(parsed_blueprints)
        if changed:
            self.save_state(project_id, state)
        relation_path = self.save_relation_index(project_id)
        report = {
            "ok": not any(i.get("level") == "error" for i in issues),
            "synced_at": now_iso(),
            "issues": issues,
            "parsedMarkdown": parsed_markdown,
            "generated": sorted(set(generated)),
            "removedManagedEntities": {bucket: sorted(set((old_entity_manifest.get(bucket) or {}).get("names") or []) - set((new_manifest["entities"].get(bucket) or {}).get("names") or [])) for bucket in CONTROL_ENTITY_BUCKETS if isinstance(old_entity_manifest.get(bucket), dict)},
            "removedManagedBlueprints": sorted(old_blueprints - parsed_blueprints),
            "relationIndex": str(relation_path),
            "manifest": str(manifest_path),
        }
        write_json(manifest_path, new_manifest)
        write_json(control / "reports" / "last_control_sync.json", report)
        write_text(control / "reports" / "last_control_sync.md", _control_sync_markdown(report))
        return report

    def refresh_markdown_templates(self, project_id: str, *, force: bool = False) -> dict[str, Any]:
        paths = self.ensure_project_dirs(project_id)
        control = Path(paths.control)
        created: list[str] = []
        for bucket in CONTROL_ENTITY_BUCKETS:
            path = control / "entities" / f"{bucket}.md"
            if force or not path.exists():
                write_text(path, entity_markdown_template(bucket))
                created.append(str(path))
        bp = control / "blueprints" / "chapter_0001.md"
        if force or not bp.exists():
            write_text(bp, blueprint_markdown_template(1))
            created.append(str(bp))
        write_text(control / "templates" / "ENTITY_TEMPLATE.md", entity_markdown_template("characters"))
        write_text(control / "templates" / "BLUEPRINT_TEMPLATE.md", blueprint_markdown_template(1))
        return {"ok": True, "created": created, "templateDir": str(control / "templates")}

    def save_relation_index(self, project_id: str) -> Path:
        state = self.load_state(project_id)
        rows = build_relation_rows(state)
        path = Path(self.paths(project_id).control) / "relations" / "entity_relations.json"
        return write_json(path, {"schema_version": 1, "updated_at": now_iso(), "count": len(rows), "relations": rows})

    def list_rejected(self, project_id: str) -> list[dict[str, Any]]:
        root = Path(self.paths(project_id).rejected)
        if not root.exists():
            return []
        rows = []
        for path in sorted(root.glob("第*.txt"), key=lambda p: p.stat().st_mtime, reverse=True):
            match = re.match(r"第(\d+)章_(.+?)_\d{8}_\d{6}\.txt$", path.name)
            rows.append({"chapterNo": int(match.group(1)) if match else 0, "title": match.group(2) if match else path.stem, "path": str(path), "size": path.stat().st_size, "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")})
        return rows

    def save_context_pack(self, project_id: str, chapter_no: int, markdown: str, data: dict[str, Any]) -> tuple[Path, Path]:
        paths = self.ensure_project_dirs(project_id)
        folder = Path(paths.control) / "context_packs"
        md = write_text(folder / f"chapter_{chapter_no:04d}_context.md", markdown)
        js = write_json(folder / f"chapter_{chapter_no:04d}_context.json", data)
        return md, js

    def list_chapters(self, project_id: str) -> list[dict[str, Any]]:
        root = Path(self.paths(project_id).chapters)
        if not root.exists():
            return []
        rows = []
        for path in sorted(root.glob("第*.txt")):
            match = re.match(r"第(\d+)章_(.+)\.txt$", path.name)
            if not match:
                continue
            rows.append({"chapterNo": int(match.group(1)), "title": match.group(2), "path": str(path), "size": path.stat().st_size})
        return rows

    def list_blueprints(self, project_id: str) -> list[dict[str, Any]]:
        root = Path(self.paths(project_id).blueprints)
        if not root.exists():
            return []
        rows = []
        for path in sorted(root.glob("第*章_蓝图.md")):
            match = re.match(r"第(\d+)章_蓝图\.md$", path.name)
            if match:
                rows.append({"chapterNo": int(match.group(1)), "path": str(path)})
        return rows

    def import_novel_file_if_empty(self, project_id: str) -> int:
        meta = self.load_meta(project_id)
        novel_file = str(meta.get("novel_file") or "").strip()
        if not novel_file or self.list_chapters(project_id):
            return 0
        p = Path(novel_file).expanduser()
        if not p.exists() or not p.is_file():
            return 0
        text = read_text_auto(p)
        chapters = _split_chapters(text)
        count = 0
        for no, title, body in chapters:
            if body.strip():
                self.save_chapter(project_id, no, title or f"第{no}章", body)
                count += 1
        return count

    def sync_novel_file(self, project_id: str) -> Path | None:
        meta = self.load_meta(project_id)
        novel_file = str(meta.get("novel_file") or "").strip()
        if not novel_file:
            return None
        output = Path(novel_file).expanduser()
        ensure_dir(output.parent)
        chapters = []
        for row in self.list_chapters(project_id):
            path = Path(row["path"])
            body = read_text_auto(path).strip()
            if not body:
                continue
            header = f"第{row['chapterNo']}章 {row.get('title') or ''}".strip()
            if re.match(r"^第\s*\d+\s*章", body):
                chapters.append(body)
            else:
                chapters.append(f"{header}\n\n{body}")
        existing = read_text_auto(output) if output.exists() else ""
        text = ("\n\n".join(chapters).strip() + "\n") if chapters else existing
        write_text(output, text)
        return output

    def export_txt(self, project_id: str) -> Path:
        paths = self.ensure_project_dirs(project_id)
        meta = self.load_meta(project_id)
        title = safe_filename(str(meta.get("title") or project_id))
        self.sync_novel_file(project_id)
        chapters = []
        for row in self.list_chapters(project_id):
            path = Path(row["path"])
            text = read_text_auto(path).strip()
            header = f"第{row['chapterNo']}章 {row.get('title') or ''}".strip()
            if re.match(r"^第\s*\d+\s*章", text):
                chapters.append(text)
            else:
                chapters.append(f"{header}\n\n{text}")
        output = Path(paths.exports) / f"{title}_全书导出.txt"
        write_text(output, "\n\n".join(chapters).strip() + "\n")
        return output

    def recent_chapter_summaries(self, project_id: str, count: int = 6) -> list[dict[str, str]]:
        state = self.load_state(project_id)
        summaries = state.get("chapter_summaries") or {}
        titles = state.get("chapter_titles") or {}
        rows = []
        for key in sorted(summaries, key=lambda x: int(x) if str(x).isdigit() else 0)[-max(0, count):]:
            rows.append({"chapter_no": str(key), "title": str(titles.get(str(key)) or ""), "summary": str(summaries.get(key) or "")})
        return rows

    def rebuild_chapter_index(self, project_id: str) -> Path:
        paths = self.ensure_project_dirs(project_id)
        docs = []
        for row in self.list_chapters(project_id):
            p = Path(row["path"])
            text = read_text_auto(p)
            tokens = _tokenize_cn(text)
            docs.append({
                "chapter_no": row["chapterNo"],
                "title": row.get("title") or "",
                "path": str(p),
                "length": len(tokens),
                "terms": dict(Counter(tokens)),
                "snippet": _first_nonempty(text, 360),
                "sha256": hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest(),
            })
        df = Counter()
        for doc in docs:
            df.update(doc["terms"].keys())
        index = {"schema_version": 1, "updated_at": now_iso(), "doc_count": len(docs), "df": dict(df), "docs": docs}
        return write_json(Path(paths.indexes) / "chapter_index.json", index)

    def index_summary(self, project_id: str) -> dict[str, Any]:
        data = read_json(Path(self.paths(project_id).indexes) / "chapter_index.json", {}) or {}
        return {"docCount": data.get("doc_count") or 0, "updatedAt": data.get("updated_at") or ""}

    def recall(self, project_id: str, query: str, *, top_k: int = 6, exclude_chapter: int | None = None) -> list[dict[str, Any]]:
        index_path = Path(self.paths(project_id).indexes) / "chapter_index.json"
        data = read_json(index_path, {}) or {}
        if not data.get("docs"):
            self.rebuild_chapter_index(project_id)
            data = read_json(index_path, {}) or {}
        docs = data.get("docs") or []
        if not docs:
            return []
        q_terms = Counter(_tokenize_cn(query))
        if not q_terms:
            return []
        n_docs = max(1, int(data.get("doc_count") or len(docs)))
        df = data.get("df") or {}
        avg_len = sum(max(1, int(doc.get("length") or 1)) for doc in docs) / max(1, len(docs))
        rows = []
        for doc in docs:
            if exclude_chapter and int(doc.get("chapter_no") or 0) == exclude_chapter:
                continue
            terms = doc.get("terms") or {}
            length = max(1, int(doc.get("length") or 1))
            score = 0.0
            for term, qf in q_terms.items():
                tf = float(terms.get(term) or 0)
                if tf <= 0:
                    continue
                idf = math.log(1 + (n_docs - float(df.get(term, 0)) + 0.5) / (float(df.get(term, 0)) + 0.5))
                score += idf * tf * 2.2 / (tf + 1.2 * (1 - 0.75 + 0.75 * length / max(1, avg_len))) * qf
            if score > 0:
                rows.append({
                    "chapter_no": doc.get("chapter_no"),
                    "title": doc.get("title") or "",
                    "score": round(score, 4),
                    "snippet": doc.get("snippet") or "",
                    "path": doc.get("path") or "",
                })
        rows.sort(key=lambda r: r["score"], reverse=True)
        return rows[: max(0, top_k)]

    def rebuild_state_from_commits(self, project_id: str) -> Path:
        state = fresh_state()
        root = Path(self.paths(project_id).commits)
        for path in sorted(root.glob("第*章_commit.json")):
            commit = read_json(path, {}) or {}
            if commit.get("status") == "accepted":
                self.apply_commit_to_state(state, commit)
        return self.save_state(project_id, state)

    def apply_commit_to_state(self, state: dict[str, Any], commit: dict[str, Any]) -> dict[str, Any]:
        chapter_no = int(commit.get("chapter_no") or 0)
        for key, prefix in [("characters", "char"), ("locations", "loc"), ("factions", "fac"), ("items", "item"), ("foreshadows", "foresh"), ("conflicts", "conf")]:
            state.setdefault(key, {})
            incoming = commit.get(key) or {}
            if isinstance(incoming, dict):
                for name, value in incoming.items():
                    current = state[key].get(name, {}) if isinstance(state[key].get(name, {}), dict) else {}
                    value_dict = value if isinstance(value, dict) else {"status": value}
                    entity = _merge_entity(prefix, str(name), current, value_dict, chapter_no)
                    state[key][name] = entity
                    state.setdefault("entity_mentions", []).append({"chapter_no": chapter_no, "type": key, "name": str(name), "id": entity.get("id")})
        for key in ["secrets", "pledges", "deadlines"]:
            incoming = commit.get(key) or {}
            if isinstance(incoming, dict):
                state.setdefault(key, {}).update(incoming)
        if isinstance(commit.get("timeline"), list):
            state.setdefault("timeline", []).extend(commit["timeline"])
        if isinstance(commit.get("milestones"), list):
            state.setdefault("milestones", []).extend(commit["milestones"])
        if chapter_no:
            state.setdefault("chapter_summaries", {})[str(chapter_no)] = commit.get("summary") or ""
            state.setdefault("chapter_titles", {})[str(chapter_no)] = commit.get("chapter_title") or ""
            state.setdefault("chapter_status", {})[str(chapter_no)] = "committed"
            state["latest_chapter"] = max(int(state.get("latest_chapter") or 0), chapter_no)
            state["last_commit_id"] = commit.get("commit_id") or state.get("last_commit_id") or ""
        state["foreshadow_debts"] = {
            name: item for name, item in (state.get("foreshadows") or {}).items()
            if isinstance(item, dict) and str(item.get("status") or "") not in {"回收", "已回收", "resolved", "closed", "payoff"}
        }
        state["conflict_progress"] = {name: item.get("progress") if isinstance(item, dict) else item for name, item in (state.get("conflicts") or {}).items()}
        clock = state.setdefault("project_clock", {})
        clock.setdefault("created_at", now_iso())
        clock["updated_at"] = now_iso()
        return state

    def _event_id(self, event_type: str, payload: dict[str, Any]) -> str:
        raw = json.dumps({"type": event_type, "payload": payload, "at": now_iso()}, ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _event_chain_fingerprint(prev_fingerprint: str, event: dict[str, Any]) -> str:
    payload = dict(event)
    payload.pop("fingerprint", None)
    raw = json.dumps({"prev": prev_fingerprint or "", "event": payload}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _merge_entity(prefix: str, name: str, current: dict[str, Any], incoming: dict[str, Any], chapter_no: int) -> dict[str, Any]:
    entity = dict(current or {})
    entity.setdefault("id", f"{prefix}_{_slug(name)}")
    entity.setdefault("name", name)
    entity.setdefault("aliases", [])
    entity.setdefault("first_seen_chapter", chapter_no)
    entity["last_seen_chapter"] = chapter_no
    history = entity.setdefault("history", [])
    if isinstance(history, list):
        history.append({"chapter_no": chapter_no, "changes": incoming})
        if len(history) > 120:
            del history[:-120]
    for k, v in incoming.items():
        if k == "history":
            continue
        entity[k] = v
    return entity


def _slug(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", value.strip()).strip("_")
    return text[:48] or "entity"


def _split_chapters(text: str) -> list[tuple[int, str, str]]:
    pattern = re.compile(r"(?m)^\s*第\s*([0-9０-９一二三四五六七八九十百千万零〇两]+)\s*章\s*([^\n]*)")
    matches = list(pattern.finditer(text or ""))
    rows: list[tuple[int, str, str]] = []
    for i, m in enumerate(matches):
        no = _cn_int(m.group(1)) or (i + 1)
        title = (m.group(2) or "").strip(" ：:、\t") or f"第{no}章"
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        rows.append((no, title, body))
    if not rows and text.strip():
        rows.append((1, "第1章", text.strip()))
    return rows


def _cn_int(value: str) -> int:
    s = str(value).translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if s.isdigit():
        return int(s)
    nums = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    total = section = number = 0
    for ch in s:
        if ch in nums:
            number = nums[ch]
        elif ch in units:
            unit = units[ch]
            if unit == 10000:
                section = (section + number) * unit
                total += section
                section = number = 0
            else:
                section += (number or 1) * unit
                number = 0
    return total + section + number


def _tokenize_cn(text: str) -> list[str]:
    text = re.sub(r"\s+", "", str(text or ""))
    tokens: list[str] = []
    # Chinese bi/tri-grams work decently for local recall without external deps.
    cn = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    for seg in cn:
        for n in (2, 3):
            tokens.extend(seg[i : i + n] for i in range(0, max(0, len(seg) - n + 1)))
    tokens.extend(re.findall(r"[A-Za-z0-9_]{2,}", text.lower()))
    return tokens[:50000]


def _first_nonempty(text: str, limit: int) -> str:
    for line in str(text or "").splitlines():
        line = line.strip()
        if line:
            return line[:limit]
    return str(text or "").strip()[:limit]



def _normalise_entity_map(data: Any, bucket: str) -> dict[str, Any] | None:
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        out: dict[str, Any] = {}
        for idx, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                return None
            name = str(item.get("name") or item.get("title") or item.get("id") or f"{bucket}_{idx}").strip()
            out[name] = item
        return out
    return None


def _chapter_no_from_control_file(path: Path, data: dict[str, Any]) -> int:
    value = data.get("chapter_no") or data.get("chapterNo")
    if value:
        try:
            return int(value)
        except Exception:
            pass
    match = re.search(r"chapter_(\d+)", path.stem)
    return int(match.group(1)) if match else 0


def _blueprint_to_markdown(data: dict[str, Any]) -> str:
    lines = [f"# 第{data.get('chapter_no') or data.get('chapterNo') or ''}章 {data.get('title') or ''}".strip(), ""]
    for key, title in [("goal", "目标"), ("pov", "视角"), ("main_scene", "主要场景"), ("conflict", "冲突"), ("payoff_or_emotion", "爽点/情绪回报"), ("ending_hook", "章末钩子")]:
        value = data.get(key) or ""
        if value:
            lines += [f"## {title}", str(value), ""]
    for key, title in [("must_cover_nodes", "必达节点"), ("forbidden_zones", "禁区"), ("fact_writeback_notes", "事实回写提示")]:
        value = data.get(key) or []
        if isinstance(value, list) and value:
            lines.append(f"## {title}")
            lines.extend(f"- {item}" for item in value)
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_relation_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(src_type: str, src: str, rel: str, dst_type: str, dst: str, note: str = "") -> None:
        if src and dst:
            rows.append({"sourceType": src_type, "source": src, "relation": rel, "targetType": dst_type, "target": dst, "note": note})

    for name, item in (state.get("characters") or {}).items():
        if isinstance(item, dict):
            add("character", str(name), "located_at", "location", str(item.get("location") or ""))
            for rel in item.get("relations") or []:
                if isinstance(rel, dict):
                    add("character", str(name), str(rel.get("type") or "related_to"), "character", str(rel.get("target") or rel.get("name") or ""), str(rel.get("note") or ""))
                else:
                    add("character", str(name), "related_to", "character", str(rel))
    for name, item in (state.get("factions") or {}).items():
        if isinstance(item, dict):
            for member in item.get("members") or []:
                add("faction", str(name), "has_member", "character", str(member))
    for name, item in (state.get("items") or {}).items():
        if isinstance(item, dict):
            add("item", str(name), "owned_by", "character", str(item.get("owner") or ""))
    for name, item in (state.get("foreshadows") or {}).items():
        if isinstance(item, dict):
            for key in ["characters", "related_characters", "involved_characters"]:
                for value in item.get(key) or []:
                    add("foreshadow", str(name), "involves", "character", str(value))
    for name, item in (state.get("conflicts") or {}).items():
        if isinstance(item, dict):
            for value in item.get("characters") or item.get("participants") or []:
                add("conflict", str(name), "involves", "character", str(value))
            for value in item.get("factions") or []:
                add("conflict", str(name), "involves", "faction", str(value))
    return rows


def _control_sync_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# writer_control 同步报告",
        "",
        f"- 时间：{report.get('synced_at')}",
        f"- 状态：{'通过' if report.get('ok') else '有错误'}",
        f"- Markdown：{len(report.get('parsedMarkdown') or [])}",
        f"- 生成文件：{len(report.get('generated') or [])}",
        "",
    ]
    issues = report.get("issues") or []
    lines += ["## 问题", ""]
    if not issues:
        lines.append("暂无。")
    for item in issues:
        path = f" `{item.get('path')}`" if item.get("path") else ""
        lines.append(f"- [{item.get('level', 'info')}] {item.get('type', '')}{path}: {item.get('message', '')}")
    removed_entities = report.get("removedManagedEntities") or {}
    removed_blueprints = report.get("removedManagedBlueprints") or []
    lines += ["", "## 已移除的受控缓存", ""]
    if not removed_entities and not removed_blueprints:
        lines.append("暂无。")
    for bucket, names in removed_entities.items():
        if names:
            lines.append(f"- {bucket}: {', '.join(map(str, names))}")
    if removed_blueprints:
        lines.append("- blueprints: " + ", ".join(f"第{x}章" for x in removed_blueprints))
    lines += ["", "## 生成文件", ""]
    for path in (report.get("generated") or [])[:80]:
        lines.append(f"- `{path}`")
    return "\n".join(lines).rstrip() + "\n"
