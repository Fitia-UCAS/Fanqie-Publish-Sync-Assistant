from __future__ import annotations

from typing import Callable
from playwright.sync_api import Page

from backend.fanqie_web.ui_actions import locator_count_safe
from backend.fanqie_web.browser_session import save_debug

def publish_settings_visible(page: Page) -> bool:
    try:
        body = page.locator("body").inner_text(timeout=800)
    except Exception:
        body = ""
    compact = "".join(body.split())
    return any(key in compact for key in ["发布设置", "确认发布", "是否使用AI", "是否使用AI生成内容"])



def content_detection_visible(page: Page) -> bool:
    try:
        body = page.locator("body").inner_text(timeout=800)
    except Exception:
        body = ""
    compact = "".join(body.split())
    return (
        "请选择内容检测方式" in compact
        or ("仅基础检测" in compact and "全面检测" in compact)
        or ("基础检测" in compact and "章节剩余次数" in compact)
    )


def click_basic_content_check_if_present(page: Page, log: Callable[[str], None] = print, timeout_ms: int = 3000) -> bool:
    rounds = max(1, timeout_ms // 500)
    for _ in range(rounds):
        if not content_detection_visible(page):
            page.wait_for_timeout(500)
            continue

        log("检测到内容检测方式弹窗，自动选择“仅基础检测”...")
        save_debug(page, "content_check_method_detected")

        for loc in (
            page.get_by_role("button", name="仅基础检测"),
            page.get_by_text("仅基础检测", exact=True),
        ):
            try:
                count = locator_count_safe(loc)
                for i in reversed(range(count)):
                    item = loc.nth(i)
                    try:
                        if item.is_visible() and item.is_enabled():
                            item.scroll_into_view_if_needed()
                            item.click(timeout=5000)
                            save_debug(page, "content_check_basic_clicked")
                            page.wait_for_timeout(1600)
                            return True
                    except Exception:
                        continue
            except Exception:
                pass

        script = r"""
        () => {
            function visible(el) {
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 &&
                       style.visibility !== 'hidden' &&
                       style.display !== 'none' &&
                       rect.bottom >= 0 && rect.right >= 0 &&
                       rect.top <= window.innerHeight && rect.left <= window.innerWidth;
            }
            function compactText(el) {
                return ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, '').trim();
            }
            const roots = Array.from(document.querySelectorAll(
                '[role="dialog"], .arco-modal-content, .arco-modal, .byte-modal, .byte-modal-content, .semi-modal-content, .semi-modal, div'
            ))
                .filter(visible)
                .map(el => {
                    const rect = el.getBoundingClientRect();
                    const text = compactText(el);
                    const area = rect.width * rect.height;
                    let score = 0;
                    if (text.includes('请选择内容检测方式')) score += 12;
                    if (text.includes('仅基础检测')) score += 8;
                    if (text.includes('全面检测')) score += 6;
                    if (rect.width >= 360 && rect.width <= 760 && rect.height >= 180 && rect.height <= 560) score += 4;
                    return {el, rect, text, area, score};
                })
                .filter(x => x.score >= 14)
                .sort((a, b) => b.score - a.score || a.area - b.area);
            const root = roots.length ? roots[0].el : document.body;
            const buttons = Array.from(root.querySelectorAll('button, [role="button"], span, div'))
                .filter(visible)
                .map(el => {
                    const clickable = el.closest('button, [role="button"]') || el;
                    const text = compactText(clickable) || compactText(el);
                    const rect = clickable.getBoundingClientRect();
                    let score = 0;
                    if (text === '仅基础检测') score += 20;
                    if (text.includes('仅基础检测')) score += 12;
                    if (text.includes('全面检测')) score -= 100;
                    if (clickable.tagName.toLowerCase() === 'button') score += 6;
                    if (clickable.getAttribute('role') === 'button') score += 4;
                    if (rect.width >= 70 && rect.width <= 180 && rect.height >= 28 && rect.height <= 70) score += 2;
                    return {el, clickable, text, rect, score};
                })
                .filter(x => x.score >= 12)
                .sort((a, b) => b.score - a.score || a.rect.left - b.rect.left);
            for (const item of buttons) {
                try {
                    item.clickable.scrollIntoView({block: 'center', inline: 'center'});
                    item.clickable.click();
                    return true;
                } catch (e) {
                    try { item.el.click(); return true; } catch (e2) {}
                }
            }
            if (roots.length) {
                const rect = roots[0].rect;
                const points = [
                    [rect.left + rect.width * 0.62, rect.top + rect.height * 0.83],
                    [rect.left + rect.width * 0.58, rect.top + rect.height * 0.83],
                    [rect.left + rect.width * 0.65, rect.top + rect.height * 0.83],
                ];
                for (const [x, y] of points) {
                    const target = document.elementFromPoint(x, y);
                    if (!target) continue;
                    const clickable = target.closest('button, [role="button"]') || target;
                    const text = compactText(clickable);
                    if (text.includes('全面检测')) continue;
                    try {
                        clickable.click();
                        return true;
                    } catch (e) {}
                }
            }
            return false;
        }
        """
        try:
            if page.evaluate(script):
                save_debug(page, "content_check_basic_clicked_js")
                page.wait_for_timeout(1600)
                return True
        except Exception:
            pass

        save_debug(page, "content_check_basic_click_failed", force=True)
        raise RuntimeError("检测到内容检测方式弹窗，但未能点击“仅基础检测”。")
    return False

def choose_ai_option(page: Page, use_ai: bool, log: Callable[[str], None] = print) -> None:
    target_text = "是" if use_ai else "否"
    log(f"正在选择“是否使用AI：{target_text}”...")
    save_debug(page, "publish_settings_choose_ai_before")

    appeared = False
    for _ in range(30):
        try:
            body = page.locator("body").inner_text(timeout=800)
            if ("发布设置" in body) or ("确认发布" in body) or ("是否使用AI" in body):
                appeared = True
                break
        except Exception:
            pass
        page.wait_for_timeout(500)
    if not appeared:
        raise RuntimeError("未检测到发布设置弹窗。")
    script = r"""
    (targetText) => {
        function visible(el) {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 &&
                   style.visibility !== 'hidden' &&
                   style.display !== 'none' &&
                   rect.bottom >= 0 &&
                   rect.right >= 0 &&
                   rect.top <= window.innerHeight &&
                   rect.left <= window.innerWidth;
        }
        function compactText(el) {
            return ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, '').trim();
        }
        function clickAt(x, y) {
            const el = document.elementFromPoint(x, y);
            if (!el) return false;
            const clickable =
                el.closest('label') ||
                el.closest('[role="radio"]') ||
                el.closest('.arco-radio') ||
                el.closest('.byte-radio') ||
                el.closest('.semi-radio') ||
                el.closest('button') ||
                el;
            try {
                clickable.click();
                return true;
            } catch (e) {
                try {
                    el.click();
                    return true;
                } catch (e2) {
                    return false;
                }
            }
        }
        function textRanges(root, exactText) {
            const out = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                const value = (node.nodeValue || '').replace(/\s+/g, '').trim();
                if (value !== exactText) continue;
                const parent = node.parentElement;
                if (!parent || !visible(parent)) continue;
                try {
                    const range = document.createRange();
                    range.selectNodeContents(node);
                    const rect = range.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        out.push({node, parent, rect});
                    }
                } catch (e) {}
            }
            return out;
        }
        function modalCandidates() {
            const selectors = [
                '[role="dialog"]',
                '.arco-modal-content',
                '.arco-modal',
                '.byte-modal',
                '.byte-modal-content',
                '.semi-modal-content',
                '.semi-modal',
                'div'
            ];
            const candidates = Array.from(document.querySelectorAll(selectors.join(',')))
                .filter(visible)
                .map(el => {
                    const rect = el.getBoundingClientRect();
                    const text = compactText(el);
                    const area = rect.width * rect.height;
                    let score = 0;
                    if (text.includes('发布设置')) score += 10;
                    if (text.includes('确认发布')) score += 10;
                    if (text.includes('是否使用AI')) score += 10;
                    if (rect.width >= 350 && rect.width <= 760 && rect.height >= 250 && rect.height <= 700) score += 4;
                    if (rect.left > 100 && rect.top > 80 && rect.right < window.innerWidth - 20 && rect.bottom < window.innerHeight + 20) score += 2;
                    return {el, rect, text, area, score};
                })
                .filter(x => x.score >= 4)
                .sort((a, b) => b.score - a.score || a.area - b.area);
            return candidates;
        }
        const candidates = modalCandidates();
        const root = candidates.length ? candidates[0].el : document.body;
        const rootRect = candidates.length ? candidates[0].rect : document.body.getBoundingClientRect();
        const aiRanges = textRanges(root, '是否使用AI');
        const targetRanges = textRanges(root, targetText);
        let chosen = null;
        if (aiRanges.length && targetRanges.length) {
            const aiY = aiRanges[0].rect.top + aiRanges[0].rect.height / 2;
            let bestDistance = Infinity;
            for (const item of targetRanges) {
                const y = item.rect.top + item.rect.height / 2;
                const distance = Math.abs(y - aiY);
                if (distance < bestDistance) {
                    bestDistance = distance;
                    chosen = item;
                }
            }
            if (bestDistance > 90) {
                chosen = null;
            }
        }
        if (!chosen && targetRanges.length) {
            chosen = targetRanges[targetRanges.length - 1];
        }
        if (chosen) {
            const r = chosen.rect;
            const y = r.top + r.height / 2;
            const points = [
                [r.left - 22, y],
                [r.left - 16, y],
                [r.left + r.width / 2, y],
            ];
            for (const [x, yy] of points) {
                if (clickAt(x, yy)) {
                    return {ok: true, method: 'text-or-radio-click'};
                }
            }
        }
        if (rootRect && rootRect.width > 0 && rootRect.height > 0) {
            const xRatio = targetText === '是' ? 0.32 : 0.50;
            const yRatio = 0.765;
            const x = rootRect.left + rootRect.width * xRatio;
            const y = rootRect.top + rootRect.height * yRatio;
            const points = [
                [x, y],
                [x - 15, y],
                [x + 15, y],
                [x - 25, y],
            ];
            for (const [px, py] of points) {
                if (clickAt(px, py)) {
                    return {ok: true, method: 'modal-coordinate-fallback'};
                }
            }
        }
        return {ok: false, method: 'not-found'};
    }
    """
    result = page.evaluate(script, target_text)
    if not (isinstance(result, dict) and result.get("ok")):

        try:
            loc = page.get_by_text(target_text, exact=True)
            count = locator_count_safe(loc)
            for i in reversed(range(count)):
                item = loc.nth(i)
                if item.is_visible():
                    item.click(timeout=2000)
                    page.wait_for_timeout(800)
                    return
        except Exception:
            pass
        raise RuntimeError(f"未找到“是否使用AI：{target_text}”选项。")
    page.wait_for_timeout(400)
    save_debug(page, "publish_settings_choose_ai_after")

DAILY_SUBMIT_LIMIT_KEYWORDS = (
    "提交字数超出每日上限",
    "提交字数超过每日上限",
    "字数超出每日上限",
    "字数超过每日上限",
    "超过本日提交字数",
    "超出本日提交字数",
    "本日提交的字数",
)
def daily_submit_limit_visible(page: Page) -> bool:
    try:
        body = page.locator("body").inner_text(timeout=800)
    except Exception:
        body = ""
    compact = "".join(body.split())
    if any(keyword in compact for keyword in DAILY_SUBMIT_LIMIT_KEYWORDS):
        return True
    return ("每日上限" in compact or "本日" in compact) and ("提交字数" in compact or "投稿字数" in compact)


def click_confirm_submit(page: Page, log=print) -> None:
    log("正在确认发布...")
    save_debug(page, "publish_confirm_before_click")

    for _ in range(12):
        try:
            loc = page.get_by_text("确认发布", exact=True)
            count = locator_count_safe(loc)
            for i in range(count):
                item = loc.nth(i)
                if item.is_visible():
                    try:
                        item.scroll_into_view_if_needed()
                        item.click(timeout=5000)
                        save_debug(page, "publish_confirm_clicked")
                        page.wait_for_timeout(1200)
                        return
                    except Exception:
                        pass
        except Exception:
            pass
        page.wait_for_timeout(500)

    script = r"""
    () => {
        function visible(el) {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 &&
                   style.visibility !== 'hidden' &&
                   style.display !== 'none' &&
                   rect.bottom >= 0 &&
                   rect.right >= 0 &&
                   rect.top <= window.innerHeight &&
                   rect.left <= window.innerWidth;
        }
        function compactText(el) {
            return ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, '').trim();
        }
        function clickAt(x, y) {
            const el = document.elementFromPoint(x, y);
            if (!el) return false;
            const clickable = el.closest('button') || el;
            try {
                clickable.click();
                return true;
            } catch (e) {
                try {
                    el.click();
                    return true;
                } catch (e2) {
                    return false;
                }
            }
        }
        const candidates = Array.from(document.querySelectorAll('[role="dialog"], .arco-modal-content, .arco-modal, .byte-modal, .byte-modal-content, .semi-modal-content, .semi-modal, div'))
            .filter(visible)
            .map(el => {
                const rect = el.getBoundingClientRect();
                const text = compactText(el);
                const area = rect.width * rect.height;
                let score = 0;
                if (text.includes('发布设置')) score += 10;
                if (text.includes('确认发布')) score += 10;
                if (rect.width >= 350 && rect.width <= 760 && rect.height >= 250 && rect.height <= 700) score += 4;
                return {el, rect, text, area, score};
            })
            .filter(x => x.score >= 4)
            .sort((a, b) => b.score - a.score || a.area - b.area);
        const rect = candidates.length ? candidates[0].rect : null;
        if (!rect) return false;
        const points = [
            [rect.left + rect.width * 0.84, rect.top + rect.height * 0.91],
            [rect.left + rect.width * 0.80, rect.top + rect.height * 0.91],
            [rect.left + rect.width * 0.87, rect.top + rect.height * 0.91],
        ];
        for (const [x, y] of points) {
            if (clickAt(x, y)) return true;
        }
        return false;
    }
    """
    if not page.evaluate(script):
        raise RuntimeError("未找到“确认发布”按钮。")
    save_debug(page, "publish_confirm_clicked_js")
    page.wait_for_timeout(1200)

