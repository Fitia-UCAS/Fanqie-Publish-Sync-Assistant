from __future__ import annotations

from pathlib import Path

from tests.test_backend_smoke import ChapterParserTest
from backend.services.novel_text.chapter_parser import parse_chapter_blocks
from backend.services.novel_text.text_splitter import NovelSplitOptions, split_novel_text


def _write_novel(path: Path, chapter_numbers: list[int]) -> None:
    parts = ["《测试小说》\n作者：测试\n"]
    for number in chapter_numbers:
        parts.append(f"第{number}章 测试标题{number}\n\n正文{number}\n")
    path.write_text("\n".join(parts), encoding="utf-8")


def test_chapter_count_split_uses_source_name_and_chapter_number_width(tmp_path: Path) -> None:
    source = tmp_path / "测试小说.txt"
    _write_novel(source, [1, 2, 593, 1208])

    result = split_novel_text(
        NovelSplitOptions(
            input_file=source,
            output_dir=tmp_path / "out",
            split_mode="chapter_count",
            chapters_per_file=2,
        )
    )

    assert [item.path.name for item in result.files] == [
        "测试小说_0001-0002.txt",
        "测试小说_0593-1208.txt",
    ]


def test_size_split_uses_source_name_and_part_index(tmp_path: Path) -> None:
    source = tmp_path / "测试小说.txt"
    _write_novel(source, [1, 2, 3])

    result = split_novel_text(
        NovelSplitOptions(
            input_file=source,
            output_dir=tmp_path / "out",
            split_mode="size",
            max_size_mb=0.00001,
        )
    )

    assert [item.path.name for item in result.files] == [
        "测试小说_001.txt",
        "测试小说_002.txt",
        "测试小说_003.txt",
    ]


def test_legacy_split_modes_fall_back_to_chapter_count(tmp_path: Path) -> None:
    source = tmp_path / "测试小说.txt"
    _write_novel(source, [1, 2, 3, 4])

    result = split_novel_text(
        NovelSplitOptions(
            input_file=source,
            output_dir=tmp_path / "out",
            split_mode="line",
            chapters_per_file=2,
        )
    )

    assert result.mode == "chapter_count"
    assert [item.path.name for item in result.files] == ["测试小说_1-2.txt", "测试小说_3-4.txt"]


def test_splitter_chapter_blocks_ignore_backwards_recap_reference() -> None:
    text = (
        "第980章 偷吃的小瑶瑶，众女陆续返回（额外纪元复盘）\n\n"
        "正文。\n\n"
        "第905章 ，圣爷与主角的再度对话中，讨论到纪元破败保留下来了人族的火种。\n\n"
        "其实再追溯到最开始的第32章，首次提到黑雾。\n\n"
        "第981章 下一章标题\n\n"
        "下一章正文。\n"
    )

    chapters = parse_chapter_blocks(text)

    assert [chapter.number for chapter in chapters] == [980, 981]
    assert "第905章 ，圣爷与主角" in chapters[0].body
