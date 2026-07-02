from __future__ import annotations


from datetime import datetime
import re

from backend.tasks.callbacks import TaskCallbacks
from backend.paths import task_log_file


class CrawlerLog:
    def __init__(self, callbacks: TaskCallbacks) -> None:
        self.callbacks = callbacks
        self.path = task_log_file("web_crawler")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(f"任务：网页抓取\n开始：{datetime.now():%Y-%m-%d %H:%M:%S}\n\n", encoding="utf-8")
        self.total = 0
        self.current = 0
        self._last_ui = ""

    def log(self, message: str, level: str = "info") -> None:
        text = str(message or "").strip()
        if not text:
            return
        self._write_detail(text)
        summary = self._summary(text, level)
        if not summary:
            return
        ui_level, ui_text = summary
        if ui_text == self._last_ui:
            return
        self._last_ui = ui_text
        self.callbacks.emit_log(ui_text, ui_level)

    def progress(self, current: int, total: int) -> None:
        self.current = max(0, int(current or 0))
        self.total = max(0, int(total or 0))
        self.callbacks.emit_progress(self.current, self.total)
        if self.total > 0:
            self._set_status(f"正在抓取章节：{self.current}/{self.total}", "info")

    def finish(self, ok: bool, message: str) -> None:
        self._write_detail(message)
        if ok and self.total:
            self.callbacks.emit_progress(self.total, self.total)

    def _write_detail(self, message: str) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(f"[{datetime.now():%H:%M:%S}] {message}\n")

    def _set_status(self, message: str, level: str) -> None:
        if message == self._last_ui:
            return
        self._last_ui = message
        self.callbacks.emit_log(message, level)

    def _summary(self, message: str, level: str) -> tuple[str, str] | None:
        if message.startswith("开始：") or message.startswith("开始网页抓取"):
            return "info", "准备网页抓取..."
        if message.startswith("目录：读取") or message.startswith("读取目录："):
            return "info", "正在读取目录..."
        if message.startswith("目录：完成") or message.startswith("目录完成："):
            parsed = re.search(r"共\s*(\d+)\s*章，本次\s*(\d+)\s*章", message)
            if parsed:
                return "success", f"目录读取完成：本次 {parsed.group(2)} 章。"
            return "success", "目录读取完成。"
        if message.startswith("检测：已有 TXT：") or message.startswith("检测到已有 TXT："):
            return "info", self._truncate(message, 80)
        if message.startswith("缺章：") or message.startswith("缺失章节："):
            return None
        if message.startswith("检测：没有已有 TXT") or message.startswith("没有检测到已有 TXT"):
            return "info", self._truncate(message, 80)
        if message.startswith("本地 TXT 已完整"):
            return "success", "本地 TXT 已完整，无需重新抓取。"
        if message.startswith("补抓：开始缺失章节") or message.startswith("开始补抓缺失章节"):
            return "info", "正在补抓缺失章节..."
        if message.startswith("写入：已创建 TXT"):
            return "info", "正在准备写入 TXT..."
        if message.startswith("阶段：第一组参数抓取：") or message.startswith("开始第一组参数抓取"):
            return "info", "正在抓取章节..."
        if message.startswith("抓取：第") or message.startswith("写入：第"):
            return None
        if message.startswith("限流：第"):
            return None
        if message.startswith("失败：第") or message.startswith("补抓失败："):
            return None
        if message.startswith("完成：第") or message.startswith("补抓完成：第"):
            return None
        if message.startswith("进度："):
            return "warning" if "限流：0" not in message and "限流：" in message else "info", self._truncate(message, 80)
        if message.startswith("阶段：第一组参数抓取完成") or message.startswith("第一组参数抓取完成"):
            if "失败" in message:
                return "warning", "第一轮抓取完成，正在补抓失败章节..."
            return "success", "章节抓取完成，正在写出文件..."
        if message.startswith("补抓：上一组") or message.startswith("上一组完成后仍失败"):
            return "warning", "正在补抓失败章节..."
        if message.startswith("限流：") or message.startswith("触发限流保护"):
            return "warning", "触发限流保护，稍后继续..."
        if message.startswith("补抓：第二组参数完成") or message.startswith("补抓：第三组参数完成") or message.startswith("补抓：第四组参数完成"):
            return "info", "补抓阶段完成，正在校验结果..."
        if message.startswith("第二组参数补抓完成") or message.startswith("第三组参数补抓完成") or message.startswith("第四组参数补抓完成"):
            return "info", "补抓阶段完成，正在校验结果..."
        if message.startswith("正在合并并写出 TXT 文件"):
            return "info", "正在合并并写出 TXT 文件..."
        if message.startswith("完成：TXT") or message.startswith("TXT 文件写出完成") or message.startswith("TXT 缺章补齐完成"):
            return "success", "TXT 文件已写出。"
        if message.startswith("失败：仍有") or message.startswith("仍有"):
            return "warning", "抓取完成，但仍有章节失败。"
        if message.startswith("停止：") or message.startswith("已停止"):
            return "warning", self._truncate(message, 80)
        if "失败" in message or level in {"error", "warn", "warning"}:
            return "warning" if level != "error" else "error", self._truncate(message, 80)
        return None

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        text = " ".join(str(text).split())
        return text if len(text) <= max_len else text[: max_len - 1] + "…"


