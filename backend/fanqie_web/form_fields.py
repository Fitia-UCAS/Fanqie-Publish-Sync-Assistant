from __future__ import annotations

import re
from typing import Any, Tuple

from playwright.sync_api import Locator, Page

from backend.fanqie_web.text_counts import count_non_whitespace_chars
from backend.fanqie_web.ui_actions import locator_count_safe
from backend.novel.text_cleaning import normalize_novel_body, normalize_text


def all_input_like(page: Page) -> list[Locator]:
    selectors = [
        "input",
        "textarea",
        "[contenteditable='true']",
        "[contenteditable=true]",
        ".ProseMirror",
        ".ql-editor",
        ".DraftEditor-root",
        ".public-DraftEditor-content",
        "[role='textbox']",
    ]
    result: list[Locator] = []
    for sel in selectors:
        loc = page.locator(sel)
        count = locator_count_safe(loc)
        for i in range(count):
            item = loc.nth(i)
            try:
                if item.is_visible():
                    result.append(item)
            except Exception:
                continue
    return result


def element_text_or_value(loc: Locator) -> str:
    try:
        tag = loc.evaluate("el => el.tagName.toLowerCase()")
    except Exception:
        tag = ""
    try:
        if tag in ("input", "textarea"):
            return loc.input_value(timeout=3000)
    except Exception:
        pass
    try:
        value = loc.evaluate(
            """el => {
                if ('value' in el && el.value) return el.value;
                return el.innerText || el.textContent || '';
            }"""
        )
        return value or ""
    except Exception:
        return ""


def reported_body_word_count(page: Page) -> int | None:
    try:
        body = page.locator("body").inner_text(timeout=1000)
    except Exception:
        body = ""
    if not body:
        return None
    compact = re.sub(r"\s+", "", body)
    matches = [int(m.group(1)) for m in re.finditer(r"正文字数[:：]?(\d{1,8})", compact)]
    if not matches:
        matches = [int(m.group(1)) for m in re.finditer(r"正文(?:字数|字数统计)[:：]?(\d{1,8})", compact)]
    if not matches:
        return None
    return max(matches)


def editor_body_counter_confirms(page: Page, text: str) -> bool:
    count = reported_body_word_count(page)
    if count is None:
        return False
    expected = count_non_whitespace_chars(normalize_novel_body(text or ""))
    if expected <= 0:
        return True
    if expected >= 400:
        floor = max(200, int(expected * 0.45))
    elif expected >= 80:
        floor = max(40, int(expected * 0.45))
    else:
        floor = max(1, int(expected * 0.45))
    return count >= floor


def _input_meta(loc: Locator) -> dict:
    try:
        return loc.evaluate(
            """el => {
                const tag = (el.tagName || '').toLowerCase();
                const cls = String(el.className || '').toLowerCase();
                const placeholder = String(el.getAttribute('placeholder') || '').trim();
                const aria = String(el.getAttribute('aria-label') || '').trim();
                const role = String(el.getAttribute('role') || '').trim();
                const type = String(el.getAttribute('type') || '').toLowerCase();
                const contenteditable = el.isContentEditable || el.getAttribute('contenteditable') === 'true';
                const text = ('value' in el && el.value !== undefined) ? el.value : (el.innerText || el.textContent || '');
                const rect = el.getBoundingClientRect();
                const parentText = (el.parentElement && (el.parentElement.innerText || el.parentElement.textContent)) || '';
                const hint = `${placeholder} ${aria} ${cls} ${parentText}`.toLowerCase();
                const editorLike = contenteditable || role === 'textbox' ||
                    cls.includes('prosemirror') || cls.includes('ql-editor') ||
                    cls.includes('drafteditor') || cls.includes('public-drafteditor');
                const bodyHint = hint.includes('正文') || hint.includes('content') || hint.includes('请输入正文') || cls.includes('prosemirror') || cls.includes('ql-editor');
                return {
                    tag, cls, placeholder, aria, role, type, contenteditable,
                    text: String(text || ''), editorLike, bodyHint,
                    width: rect.width || 0, height: rect.height || 0,
                    area: Math.max(0, (rect.width || 0) * (rect.height || 0))
                };
            }"""
        )
    except Exception:
        return {}


def _locator_is(loc: Locator, expected: Locator) -> bool:
    try:
        return bool(loc.evaluate("(el, other) => el === other", expected.element_handle()))
    except Exception:
        return loc is expected


def _looks_like_chapter_no_value(value: str) -> bool:
    value = (value or "").strip()
    return value.isdigit() and len(value) <= 4


def _looks_like_no_field(meta: dict) -> bool:
    text = " ".join(str(meta.get(key) or "") for key in ("placeholder", "aria", "cls", "type"))
    compact = "".join(text.split()).lower()
    return any(word in compact for word in ("章节序号", "章序号", "章节号", "章号", "序号", "chapterindex", "chapterno", "chapter-no"))


def _looks_like_title_field(meta: dict) -> bool:
    text = " ".join(str(meta.get(key) or "") for key in ("placeholder", "aria", "cls"))
    compact = "".join(text.split()).lower()
    return any(word in compact for word in ("请输入标题", "请输入章节名", "章节名", "主标题", "标题", "chaptertitle", "title"))


def pick_title_and_editor(page: Page) -> Tuple[Locator, Locator]:
    _chapter_no_loc, title_loc, body_loc = pick_chapter_no_title_and_editor(page, require_chapter_no=False)
    return title_loc, body_loc


def pick_chapter_no_title_and_editor(page: Page, *, require_chapter_no: bool = True) -> tuple[Locator | None, Locator, Locator]:
    candidates = all_input_like(page)
    if not candidates:
        raise RuntimeError("未找到任何输入框或正文编辑器。请确认已经进入章节编辑页。")

    scored = []
    for loc in candidates:
        meta = _input_meta(loc)
        txt = str(meta.get("text") or element_text_or_value(loc))
        txt_norm = normalize_text(txt)
        tag = str(meta.get("tag") or "")
        editor_like = bool(meta.get("editorLike")) and tag not in {"input", "textarea"}
        scored.append({
            "length": len(txt_norm),
            "tag": tag,
            "loc": loc,
            "txt_norm": txt_norm,
            "meta": meta,
            "editor_like": editor_like,
        })


    def body_score(item: dict) -> tuple[int, int, int, int, int]:
        meta = item["meta"]
        tag = item["tag"]
        area = int(float(meta.get("area") or 0))
        height = int(float(meta.get("height") or 0))
        body_hint = bool(meta.get("bodyHint"))
        return (
            1 if item["editor_like"] else 0,
            1 if body_hint else 0,
            0 if tag in {"input", "textarea"} else 1,
            area,
            height + item["length"],
        )

    body_item = max(scored, key=body_score)
    body_loc = body_item["loc"]

    non_body = [item for item in scored if not _locator_is(item["loc"], body_loc)]

    def title_score(item: dict) -> tuple[int, int, int]:
        meta = item["meta"]
        tag = item["tag"]
        value = item["txt_norm"]
        if tag not in {"input", "textarea"}:
            return (99, 0, 0)
        if _looks_like_no_field(meta) or _looks_like_chapter_no_value(value):
            return (30, 0, 0)
        if _looks_like_title_field(meta):
            return (0, -item["length"], 0)
        if item["length"] <= 120:
            return (8 if item["length"] == 0 else 4, -item["length"], 0)
        return (60, -item["length"], 0)

    title_items = sorted(non_body, key=title_score)
    title_item = next((item for item in title_items if title_score(item)[0] < 60), None)
    if not title_item:
        raise RuntimeError("找到了正文编辑器，但未能识别标题输入框。")
    title_loc = title_item["loc"]

    chapter_no_loc: Locator | None = None
    if require_chapter_no:
        no_items = []
        for item in non_body:
            if _locator_is(item["loc"], title_loc):
                continue
            meta = item["meta"]
            tag = item["tag"]
            if tag not in {"input", "textarea"}:
                continue
            score = 50
            if _looks_like_no_field(meta):
                score = 0
            elif _looks_like_chapter_no_value(item["txt_norm"]):
                score = 3
            elif item["length"] == 0:
                score = 8
            if score < 50:
                no_items.append((score, item))
        if no_items:
            chapter_no_loc = min(no_items, key=_chapter_no_candidate_score)[1]["loc"]
        else:
            raise RuntimeError("新建章节页已打开，但未能识别章节序号输入框。")

    return chapter_no_loc, title_loc, body_loc


def _chapter_no_candidate_score(pair) -> int:
    return pair[0]


def get_remote_chapter(page: Page) -> tuple[str, str, Locator, Locator]:
    title_loc, body_loc = pick_title_and_editor(page)
    remote_title = element_text_or_value(title_loc).strip()


    remote_body = normalize_novel_body(element_text_or_value(body_loc))
    return remote_title, remote_body, title_loc, body_loc
