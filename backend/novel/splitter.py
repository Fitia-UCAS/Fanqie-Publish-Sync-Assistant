from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.novel.source import ChapterBlock, parse_chapter_blocks
from backend.novel.text_cleaning import normalize_chapter_line_breaks
from backend.filenames import safe_filename
from backend.text_files import ensure_dir, read_text_and_encoding, write_text


SPLIT_MODE_LABELS = {
    "chapter_count": "按章节数分割",
    "size": "按大小分割",
}


@dataclass(frozen=True, slots=True)
class SplitPlan:
    input_file: Path
    output_dir: Path
    split_mode: str = "chapter_count"
    chapters_per_file: int = 10
    max_size_mb: float = 5.0
    clean_output: bool = False
    include_prelude: bool = True


@dataclass(frozen=True, slots=True)
class NovelSplitFile:
    path: Path
    label: str
    bytes_size: int
    chapter_count: int = 0
    line_count: int = 0


@dataclass(frozen=True, slots=True)
class SplitReport:
    output_dir: Path
    files: list[NovelSplitFile]
    mode: str
    encoding: str

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(item.bytes_size for item in self.files)


def split_novel_text(options: SplitPlan) -> SplitReport:
    source = Path(options.input_file)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"请选择一个存在的小说 TXT 文件：{source}")

    output_dir = ensure_dir(options.output_dir)
    if options.clean_output:
        _clean_output_txt_files(output_dir)

    text, encoding = read_text_and_encoding(source)
    mode = _normalize_mode(options.split_mode)
    normalized = normalize_chapter_line_breaks(text)
    chapters = _dedupe_adjacent_empty_chapters(parse_chapter_blocks(normalized))
    if not chapters:
        raise RuntimeError("没有识别到章节标题。请确认格式类似：第1章 标题。")
    prelude = normalized[: chapters[0].start].strip() if options.include_prelude else ""
    files = _split_by_chapters(normalized, chapters, prelude, options, output_dir, mode)
    return SplitReport(output_dir=output_dir, files=files, mode=mode, encoding=encoding)


def _normalize_mode(mode: str) -> str:
    normalized = str(mode or "chapter_count").strip()
    if normalized not in SPLIT_MODE_LABELS:
        return "chapter_count"
    return normalized


def _clean_output_txt_files(output_dir: Path) -> None:
    for path in output_dir.glob("*.txt"):
        if path.is_file():
            path.unlink()
    manifest = output_dir / "split_manifest.csv"
    if manifest.exists() and manifest.is_file():
        manifest.unlink()


def _dedupe_adjacent_empty_chapters(chapters: list[ChapterBlock]) -> list[ChapterBlock]:
    deduped: list[ChapterBlock] = []
    for chapter in chapters:
        previous = deduped[-1] if deduped else None
        if previous and previous.number == chapter.number and previous.title == chapter.title and not previous.body.strip():
            deduped[-1] = chapter
            continue
        deduped.append(chapter)
    return deduped


def _split_by_chapters(
    normalized_text: str,
    chapters: list[ChapterBlock],
    prelude: str,
    options: SplitPlan,
    output_dir: Path,
    mode: str,
) -> list[NovelSplitFile]:
    chunks: list[list[ChapterBlock]]
    if mode == "chapter_count":
        per_file = max(1, int(options.chapters_per_file or 10))
        chunks = [chapters[index : index + per_file] for index in range(0, len(chapters), per_file)]
    else:
        chunks = _chapter_chunks_by_size(chapters, max(1, int(float(options.max_size_mb or 5.0) * 1024 * 1024)))

    part_width = max(3, len(str(len(chunks))))
    chapter_width = max(1, len(str(max(chapter.number for chapter in chapters))))
    source_prefix = safe_filename(Path(options.input_file).stem, fallback="novel", max_length=80)
    written: list[NovelSplitFile] = []
    for index, chunk in enumerate(chunks, start=1):
        chunk_text = _chapter_chunk_text(chunk)
        if prelude and index == 1:
            chunk_text = prelude.strip() + "\n\n" + chunk_text
        path = output_dir / _chapter_chunk_filename(
            index,
            chunk,
            mode,
            part_width=part_width,
            chapter_width=chapter_width,
            source_prefix=source_prefix,
        )
        write_text(path, _ensure_trailing_newline(chunk_text))
        written.append(
            NovelSplitFile(
                path=path,
                label=_chapter_chunk_label(chunk),
                bytes_size=path.stat().st_size,
                chapter_count=len(chunk),
                line_count=len(chunk_text.splitlines()),
            )
        )
    _write_manifest(output_dir, written)
    return written


def _chapter_chunks_by_size(chapters: list[ChapterBlock], max_bytes: int) -> list[list[ChapterBlock]]:
    chunks: list[list[ChapterBlock]] = []
    current: list[ChapterBlock] = []
    current_size = 0
    for chapter in chapters:
        chapter_size = len(chapter.text.encode("utf-8"))
        if current and current_size + chapter_size > max_bytes:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(chapter)
        current_size += chapter_size
    if current:
        chunks.append(current)
    return chunks


def _chapter_chunk_text(chapters: list[ChapterBlock]) -> str:
    return "\n".join(chapter.text.strip() for chapter in chapters).strip()


def _chapter_chunk_label(chapters: list[ChapterBlock]) -> str:
    if not chapters:
        return "空分卷"
    first = chapters[0]
    last = chapters[-1]
    if first.number == last.number:
        return first.full_title
    return f"第{first.number}-{last.number}章"


def _chapter_chunk_filename(
    index: int,
    chapters: list[ChapterBlock],
    mode: str,
    *,
    part_width: int,
    chapter_width: int,
    source_prefix: str,
) -> str:
    if mode == "chapter_count" and chapters:
        first = chapters[0].number
        last = chapters[-1].number
        return f"{source_prefix}_{first:0{chapter_width}d}-{last:0{chapter_width}d}.txt"
    return f"{source_prefix}_{index:0{part_width}d}.txt"


def _write_manifest(output_dir: Path, files: list[NovelSplitFile]) -> Path:
    manifest = output_dir / "split_manifest.csv"
    rows = ["index,filename,label,bytes,chapters,lines"]
    for index, item in enumerate(files, start=1):
        rows.append(
            ",".join(
                [
                    str(index),
                    _csv_cell(item.path.name),
                    _csv_cell(item.label),
                    str(item.bytes_size),
                    str(item.chapter_count),
                    str(item.line_count),
                ]
            )
        )
    return write_text(manifest, "\n".join(rows) + "\n")


def _csv_cell(value: str) -> str:
    escaped = str(value or "").replace('"', '""')
    return f'"{escaped}"'


def _ensure_trailing_newline(text: str) -> str:
    return text.rstrip() + "\n"


def default_split_output_dir(input_file: str | Path, output_root: str | Path) -> Path:
    source = Path(input_file)
    root = Path(output_root)
    return root / f"{safe_filename(source.stem, fallback='novel')}_split"


def reset_split_output_dir(output_dir: str | Path) -> None:
    target = Path(output_dir)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
