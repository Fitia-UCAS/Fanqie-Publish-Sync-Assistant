from __future__ import annotations

from pathlib import Path

from backend.story_analysis.llm_json import read_json, write_json
from backend.story_analysis.materials import CharacterChapterMeta, CharacterChapterText
from backend.novel.chapters import Chapter
from backend.novel.reader import read_chapters
from backend.novel.text_cleaning import strip_chapter_prefix
from backend.paths import STORY_ANALYSIS_CHAPTER_DIR
from backend.filenames import safe_filename
from backend.text_files import ensure_dir, read_text_auto, write_text


def split_text_file_to_character_project(input_file: str | Path, output_root: str | Path = STORY_ANALYSIS_CHAPTER_DIR) -> Path:
    source_path = Path(str(input_file or "")).expanduser()
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(f"请选择完整小说 TXT 文件：{source_path}")
    novel_name = safe_filename(source_path.stem)
    novel_dir = ensure_dir(Path(output_root) / novel_name)
    chapters = read_chapters(source_path)
    metas: list[CharacterChapterMeta] = []
    lines = read_text_auto(source_path).splitlines()
    line_cursor = 1
    for chapter in chapters:
        file_name = _chapter_file_name(chapter)
        chapter_text = _chapter_full_text(chapter)
        start_line = _find_heading_line(lines, chapter.raw_heading, line_cursor)
        end_line = max(start_line, start_line + len(chapter_text.splitlines()) - 1)
        line_cursor = end_line + 1
        meta = CharacterChapterMeta(
            novel_name=novel_name,
            chapter_index=chapter.number,
            chapter_title=_chapter_display_heading(chapter),
            file_name=file_name,
            source_file=str(source_path),
            start_line=start_line,
            end_line=end_line,
            char_count=len(chapter_text),
        )
        write_text(novel_dir / file_name, chapter_text)
        metas.append(meta)
    write_json(novel_dir / "chapter_index.json", [meta.to_dict() for meta in metas])
    return novel_dir


def load_character_chapter_index(source: str | Path, chapters_root: str | Path = STORY_ANALYSIS_CHAPTER_DIR) -> list[CharacterChapterMeta]:
    novel_dir = resolve_character_project_dir(source, chapters_root)
    index_path = novel_dir / "chapter_index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"未找到章节索引：{index_path}")
    rows = read_json(index_path)
    if not isinstance(rows, list):
        raise ValueError(f"章节索引格式错误：{index_path}")
    return [CharacterChapterMeta(**row) for row in rows]


def load_character_chapter_text(source: str | Path, meta: CharacterChapterMeta, chapters_root: str | Path = STORY_ANALYSIS_CHAPTER_DIR) -> CharacterChapterText:
    novel_dir = resolve_character_project_dir(source, chapters_root)
    return CharacterChapterText(meta=meta, text=read_text_auto(novel_dir / meta.file_name))


def select_character_chapter_metas(
    source: str | Path,
    *,
    chapter: int | None = None,
    start: int | None = None,
    end: int | None = None,
    all_chapters: bool = False,
) -> list[CharacterChapterMeta]:
    prepared = prepare_character_source(source)
    chapters = load_character_chapter_index(prepared)
    if not chapters:
        return []

    if chapter is not None:
        start = chapter
        end = chapter

    if all_chapters:
        start = min(item.chapter_index for item in chapters)
        end = max(item.chapter_index for item in chapters)
    else:
        start = start if start is not None else min(item.chapter_index for item in chapters)
        end = end if end is not None else max(item.chapter_index for item in chapters)

    if start < 1:
        raise ValueError("起始章节不能小于 1")
    if end < start:
        raise ValueError("结束章节不能小于起始章节")

    selected = [item for item in chapters if start <= item.chapter_index <= end]
    if not selected:
        raise ValueError("没有选中章节，请检查章节编号。")
    return selected


def load_selected_character_chapters(
    source: str | Path,
    *,
    chapter: int | None = None,
    start: int | None = None,
    end: int | None = None,
    all_chapters: bool = False,
) -> list[CharacterChapterText]:
    prepared = prepare_character_source(source)
    selected = select_character_chapter_metas(
        prepared,
        chapter=chapter,
        start=start,
        end=end,
        all_chapters=all_chapters,
    )
    return [load_character_chapter_text(prepared, meta) for meta in selected]


def prepare_character_source(source: str | Path) -> str:
    source_path = Path(str(source or "")).expanduser()
    if source_path.exists() and source_path.is_file():
        return str(split_text_file_to_character_project(source_path))
    return str(source)


def resolve_character_project_dir(source: str | Path, chapters_root: str | Path = STORY_ANALYSIS_CHAPTER_DIR) -> Path:
    raw = str(source or "").strip()
    if not raw:
        raise FileNotFoundError("请先选择 TXT 文件或已切分的章节目录。")
    source_path = Path(raw).expanduser()
    if source_path.exists() and source_path.is_dir():
        return source_path
    candidate = Path(chapters_root) / raw
    if candidate.exists() and candidate.is_dir():
        return candidate
    safe_candidate = Path(chapters_root) / safe_filename(raw)
    if safe_candidate.exists() and safe_candidate.is_dir():
        return safe_candidate
    raise FileNotFoundError(f"未找到章节目录：{source}")


def format_character_chapter_table(chapters: list[CharacterChapterMeta], limit: int | None = 80) -> str:
    selected = chapters if limit is None else chapters[:limit]
    rows = ["章节编号 | 行号范围 | 字数 | 标题", "--- | --- | --- | ---"]
    for item in selected:
        rows.append(f"{item.chapter_index} | {item.start_line}-{item.end_line} | {item.char_count} | {item.chapter_title}")
    if limit is not None and len(chapters) > limit:
        rows.append(f"... | ... | ... | 其余 {len(chapters) - limit} 章未显示")
    return "\n".join(rows)



def _chapter_file_name(chapter: Chapter) -> str:
    prefix = f"第{chapter.number:03d}章"
    subtitle = safe_filename(_chapter_subtitle(chapter), fallback="", max_length=48)
    return f"{prefix}_{subtitle}.txt" if subtitle else f"{prefix}.txt"


def _chapter_display_heading(chapter: Chapter) -> str:
    subtitle = _chapter_subtitle(chapter)
    return f"第{chapter.number}章" + (f" {subtitle}" if subtitle else "")


def _chapter_subtitle(chapter: Chapter) -> str:
    title = str(chapter.title or "").strip()
    if not title:
        title = strip_chapter_prefix(str(chapter.raw_heading or ""))
    title = strip_chapter_prefix(title)
    return title.lstrip("：:、.．-_— 　").strip()


def _chapter_full_text(chapter: Chapter) -> str:
    heading = _chapter_display_heading(chapter)
    body = chapter.body.strip()
    return f"{heading}\n\n{body}".strip() + "\n"


def _find_heading_line(lines: list[str], heading: str, start_line: int) -> int:
    heading_text = str(heading or "").strip()
    for index in range(max(0, start_line - 1), len(lines)):
        if lines[index].strip() == heading_text:
            return index + 1
    return max(1, start_line)
