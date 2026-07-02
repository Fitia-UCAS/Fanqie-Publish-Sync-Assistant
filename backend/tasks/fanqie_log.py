from __future__ import annotations


from datetime import datetime
from pathlib import Path
import re

from backend.tasks.callbacks import TaskCallbacks
from backend.paths import task_log_file


_OPERATION_LABELS = {
    "compare": "检查差异",
    "check": "检查差异",
    "save": "保存草稿",
    "publish": "正式发布",
    "push": "同步到平台",
    "pull": "从平台拉取",
}


class FanqieLog:
    def __init__(self, *, callbacks: TaskCallbacks, task_kind: str, operation: str, start: int, end: int, total: int) -> None:
        self.callbacks = callbacks
        self.total = total
        self.current_chapter = 0
        self.current_index = 0
        self._index_announced = False
        self._final_verify_announced = False
        self._last_console_message = ""
        self.path = self._make_log_path(task_kind=task_kind, operation=operation, start=start, end=end)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            f"任务：{task_kind}\n操作：{operation}\n范围：第 {start} 章到第 {end} 章\n开始：{datetime.now():%Y-%m-%d %H:%M:%S}\n\n",
            encoding="utf-8",
        )

    def emit_start(self, operation: str, start: int, end: int) -> None:
        label = _OPERATION_LABELS.get(operation, operation)
        self.callbacks.emit_log(f"准备执行：{label}｜第 {start} 章到第 {end} 章")
        self.callbacks.emit_progress(0, max(1, self.total))

    def log(self, message: str) -> None:
        text = str(message or "").strip()
        if not text:
            return
        self._write_detail(text)
        summary = self._to_console_summary(text)
        if summary:
            level, summary_text = summary
            if summary_text == self._last_console_message:
                return
            self._last_console_message = summary_text
            self.callbacks.emit_log(summary_text, level)

    def finish(self, ok_count: int, processed_count: int) -> None:
        self._write_detail(f"任务结束：成功 {ok_count}/{self.total}。")
        self.callbacks.emit_progress(min(processed_count, self.total), max(1, self.total))

    def _write_detail(self, message: str) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(f"[{datetime.now():%H:%M:%S}] {message}\n")

    def _emit_stage_progress(self, fraction: float) -> None:

        if not self.current_index or not self.total:
            return
        base = max(0, self.current_index - 1)
        value = min(float(self.total), base + max(0.0, min(float(fraction), 0.98)))
        self.callbacks.emit_progress(value, self.total)

    def _to_console_summary(self, message: str) -> tuple[str, str] | None:
        if message.startswith("后台批量处理："):
            parsed = self._parse_chapter_progress(message)
            if parsed:
                chapter_no, index, total = parsed
                self.current_chapter = chapter_no
                self.current_index = index
                self.callbacks.emit_progress(index - 1, total)
                return "info", f"第 {chapter_no} 章（{index}/{total}）：处理中..."
            return "info", message

        if "检测到未登录" in message:
            return "warning", "检测到未登录，请先在 Edge 里完成番茄后台登录。"

        if message.startswith("正在建立章节入口索引"):
            return "info", "正在建立章节索引..."
        if message.startswith("章节入口索引完成") or message.startswith("章节入口索引：已缓存"):
            if not self._index_announced:
                self._index_announced = True
                return "success", "章节索引已建立。"
            return None
        if message.startswith("章节入口索引部分完成"):
            return "warning", "部分章节未建立索引，将自动降级定位。"
        if message.startswith("章节入口索引建立失败"):
            return "warning", "章节索引失败，已降级为常规定位。"

        if message.startswith("准备自动新建番茄后台"):
            self._emit_stage_progress(0.12)
            return "info", self._chapter_message("正在新建章节...")
        if message.startswith("番茄已打开新的章节编辑标签页"):
            self._emit_stage_progress(0.24)
            return "info", self._chapter_message("已打开编辑页。")
        if message.startswith("正在填写章节序号"):
            self._emit_stage_progress(0.36)
            return "info", self._chapter_message("正在填写章节号...")
        if message.startswith("正文写入未刷新"):
            self._emit_stage_progress(0.48)
            return "warning", self._chapter_message("正文未刷新，正在重试...")
        if message.startswith("正在覆盖标题和完整正文") or message.startswith("正在用本地正文完整覆盖"):
            self._emit_stage_progress(0.50)
            return "info", self._chapter_message("正在写入标题和正文...")
        if message.startswith("正在保存"):
            self._emit_stage_progress(0.66)
            return "info", self._chapter_message("正在保存...")
        if message.startswith("正在点击下一步"):
            self._emit_stage_progress(0.78)
            return "info", self._chapter_message("正在进入发布确认...")
        if message.startswith("检测到内容检测方式弹窗"):
            self._emit_stage_progress(0.82)
            return "info", self._chapter_message("已选择仅基础检测...")
        if message.startswith("正在确认发布"):
            self._emit_stage_progress(0.90)
            return "info", self._chapter_message("正在确认发布...")
        if message.startswith("发布确认流程完成"):
            self._emit_stage_progress(0.96)
            return "success", self._chapter_message("发布确认完成。")

        if message.startswith("完成："):
            if self.current_index:
                self.callbacks.emit_progress(self.current_index, self.total)
            return "success", self._chapter_message("完成。")

        if message.startswith("失败："):
            return "error", self._short_failure(message)

        if message.startswith("正在进行最终章节列表校验") or message.startswith("最终列表校验"):
            if not self._final_verify_announced:
                self._final_verify_announced = True
                self.callbacks.emit_progress(max(0, self.total - 0.05), self.total)
                return "info", "正在最终校验发布结果..."
            return None
        if message.startswith("最终章节列表校验通过"):
            self.callbacks.emit_progress(self.total, self.total)
            return "success", "最终校验通过。"


        noisy_prefixes = (
            "准备执行：",
            "缺章处理：",
            "正文校准",
            "本地：",
            "番茄：",
            "Diff：",
            "Git：",
            "Git追踪目录：",
            "编辑页内容",
            "经检测，",
            "新建前校验：",
            "未找到目标章节",
            "新建章节：",
            "编辑页遮罩",
            "检测到错别字",
            "启动时已清理",
            "启动清理",
            "正在选择“是否使用AI",
            "正在读取章节列表字数",
            "章节列表字数读取完成",
            "列表校验通过",
        )
        if message.startswith(noisy_prefixes):
            return None

        if "Timeout" in message or "Target page" in message or "Error" in message:
            return "warning", self._truncate(message, 160)
        return None

    def _chapter_message(self, suffix: str) -> str:
        if self.current_chapter:
            return f"第 {self.current_chapter} 章：{suffix}"
        return suffix

    def _short_failure(self, message: str) -> str:
        first_line = message.splitlines()[0]
        first_line = self._truncate(first_line, 170)
        return f"{first_line}（详情见日志）"

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        text = " ".join(str(text).split())
        return text if len(text) <= max_len else text[: max_len - 1] + "…"

    @staticmethod
    def _parse_chapter_progress(message: str) -> tuple[int, int, int] | None:
        match = re.search(r"第\s*(\d+)\s*章.*?（\s*(\d+)\s*/\s*(\d+)\s*）", message)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2)), int(match.group(3))

    @staticmethod
    def _make_log_path(*, task_kind: str, operation: str, start: int, end: int) -> Path:
        if task_kind == "auto_publish":
            return task_log_file("auto_publish")
        return task_log_file("chapter_sync")


