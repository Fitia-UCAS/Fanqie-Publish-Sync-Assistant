from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable
from playwright.sync_api import Page

from backend.adapters.fanqie_web.page_actions.chapter_page_interactions import locator_count_safe
from backend.adapters.fanqie_web.browser.browser_session import save_debug

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
DEFAULT_SCHEDULED_PUBLISH_TIME = "10:00"


def daily_submit_limit_visible(page: Page) -> bool:
    try:
        body = page.locator("body").inner_text(timeout=800)
    except Exception:
        body = ""
    compact = "".join(body.split())
    if any(keyword in compact for keyword in DAILY_SUBMIT_LIMIT_KEYWORDS):
        return True
    return ("每日上限" in compact or "本日" in compact) and ("提交字数" in compact or "投稿字数" in compact)


def ensure_scheduled_publish_at_10(
    page: Page,
    *,
    scheduled_time: str = DEFAULT_SCHEDULED_PUBLISH_TIME,
    date_increment_days: int = 0,
    log: Callable[[str], None] = print,
) -> str:
    save_debug(page, "schedule_publish_before")

    if not _ensure_scheduled_publish_switch_on(page):
        save_debug(page, "schedule_publish_toggle_failed", force=True)
        raise RuntimeError("检测到每日提交字数上限，但未能打开“定时发布”开关。")
    page.wait_for_timeout(600)
    save_debug(page, "schedule_publish_toggle_on")

    scheduled_date = _set_scheduled_publish_date(page, date_increment_days=date_increment_days)
    log(f"检测到提交字数超过每日上限，自动改为定时发布，发布日期设为 {scheduled_date}，发布时间设为 {scheduled_time}。")
    save_debug(page, "schedule_publish_date_set")

    if not _mark_scheduled_publish_time_target(page):
        save_debug(page, "schedule_publish_time_input_not_found", force=True)
        raise RuntimeError("检测到每日提交字数上限，但未能定位“定时发布”的时间输入框。")

    _click_and_fill_scheduled_publish_time(page, scheduled_time=scheduled_time)
    _choose_time_picker_value(page, scheduled_time=scheduled_time)
    _force_scheduled_publish_time_value(page, scheduled_time=scheduled_time)
    page.wait_for_timeout(400)
    save_debug(page, "schedule_publish_time_set")
    return scheduled_date



def ensure_scheduled_publish(
    page: Page,
    *,
    scheduled_date: str,
    scheduled_time: str,
    log: Callable[[str], None] = print,
) -> str:
    save_debug(page, "schedule_publish_manual_before")
    if not _ensure_scheduled_publish_switch_on(page):
        save_debug(page, "schedule_publish_manual_toggle_failed", force=True)
        raise RuntimeError("未能打开“定时发布”开关。")
    if not _mark_scheduled_publish_date_target(page):
        save_debug(page, "schedule_publish_manual_date_input_not_found", force=True)
        raise RuntimeError("未能定位“定时发布”的日期输入框。")
    _click_and_fill_scheduled_publish_date(page, scheduled_date=scheduled_date)
    _choose_date_picker_value(page, scheduled_date=scheduled_date)
    _force_scheduled_publish_date_value(page, scheduled_date=scheduled_date)
    if not _mark_scheduled_publish_time_target(page):
        save_debug(page, "schedule_publish_manual_time_input_not_found", force=True)
        raise RuntimeError("未能定位“定时发布”的时间输入框。")
    _click_and_fill_scheduled_publish_time(page, scheduled_time=scheduled_time)
    _choose_time_picker_value(page, scheduled_time=scheduled_time)
    _force_scheduled_publish_time_value(page, scheduled_time=scheduled_time)
    save_debug(page, "schedule_publish_manual_set")
    log(f"已设置定时发布：{scheduled_date} {scheduled_time}。")
    return scheduled_date

def _ensure_scheduled_publish_switch_on(page: Page) -> bool:
    script = r'''
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
        function fieldsVisible() {
            const compact = compactText(document.body);
            return compact.includes('定时发布') && compact.includes('日期') &&
                   compact.includes('时间') && compact.includes('预告关键词');
        }
        function isOn(el) {
            if (!el) return false;
            const cls = String(el.className || '').toLowerCase();
            const aria = String(el.getAttribute('aria-checked') || '').toLowerCase();
            return el.checked === true || aria === 'true' ||
                cls.includes('checked') || cls.includes('on') || cls.includes('open') || cls.includes('active');
        }
        function clickElement(el) {
            if (!el || !visible(el)) return false;
            try {
                el.scrollIntoView({block: 'center', inline: 'center'});
                el.click();
                return true;
            } catch (e) {
                return false;
            }
        }
        if (fieldsVisible()) return true;
        const labelNodes = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        for (let node; (node = walker.nextNode());) {
            if (!node.nodeValue || !node.nodeValue.includes('定时发布')) continue;
            const parent = node.parentElement;
            if (parent && visible(parent)) labelNodes.push(parent);
        }
        const switchSelectors = [
            '[role="switch"]',
            'button[aria-checked]',
            'input[type="checkbox"]',
            '.arco-switch',
            '.semi-switch',
            '.byte-switch',
            '[class*="switch"]',
            '[class*="Switch"]'
        ];
        const candidates = [];
        for (const label of labelNodes) {
            let root = label;
            for (let depth = 0; depth < 6 && root; depth++, root = root.parentElement) {
                for (const selector of switchSelectors) {
                    for (const sw of Array.from(root.querySelectorAll(selector))) {
                        if (!visible(sw)) continue;
                        const rect = sw.getBoundingClientRect();
                        const distance = Math.abs((rect.top + rect.height / 2) - (label.getBoundingClientRect().top + label.getBoundingClientRect().height / 2));
                        candidates.push({el: sw, rect, distance});
                    }
                }
            }
        }
        candidates.sort((a, b) => a.distance - b.distance || b.rect.left - a.rect.left);
        for (const item of candidates) {
            if (isOn(item.el)) return true;
            const clickable = item.el.closest('button, [role="switch"], label, [role="button"]') || item.el;
            if (clickElement(clickable) || clickElement(item.el)) return true;
        }
        for (const label of labelNodes) {
            const rect = label.getBoundingClientRect();
            const points = [
                [rect.right + 44, rect.top + rect.height / 2],
                [rect.right + 70, rect.top + rect.height / 2],
                [rect.right + 95, rect.top + rect.height / 2],
            ];
            for (const [x, y] of points) {
                const target = document.elementFromPoint(x, y);
                const clickable = target && (target.closest('button, [role="switch"], [role="button"], label') || target);
                if (clickElement(clickable)) return true;
            }
        }
        return fieldsVisible();
    }
    '''
    try:
        if page.evaluate(script):
            return True
    except Exception:
        pass
    for _ in range(10):
        try:
            body = page.locator("body").inner_text(timeout=500)
        except Exception:
            body = ""
        compact = "".join(body.split())
        if "定时发布" in compact and "日期" in compact and "时间" in compact and "预告关键词" in compact:
            return True
        page.wait_for_timeout(300)
    return False


def _set_scheduled_publish_date(page: Page, *, date_increment_days: int) -> str:
    if not _mark_scheduled_publish_date_target(page):
        save_debug(page, "schedule_publish_date_input_not_found", force=True)
        raise RuntimeError("检测到每日提交字数上限，但未能定位“定时发布”的日期输入框。")

    scheduled_date = _add_days_to_today(max(0, date_increment_days))
    _click_and_fill_scheduled_publish_date(page, scheduled_date=scheduled_date)
    _choose_date_picker_value(page, scheduled_date=scheduled_date)
    _force_scheduled_publish_date_value(page, scheduled_date=scheduled_date)
    page.wait_for_timeout(400)
    return scheduled_date


def _add_days_to_today(days: int) -> str:
    return (datetime.now() + timedelta(days=max(0, days))).strftime("%Y-%m-%d")


def _add_days_to_iso_date(iso_date: str | None, days: int) -> str:
    source = (iso_date or "").strip()
    try:
        base = datetime.strptime(source, "%Y-%m-%d")
    except Exception:
        base = datetime.now()
    return (base + timedelta(days=max(0, days))).strftime("%Y-%m-%d")


def _mark_scheduled_publish_date_target(page: Page) -> bool:
    script = r'''
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
        function modalCandidates() {
            return Array.from(document.querySelectorAll('[role="dialog"], .arco-modal-content, .arco-modal, .byte-modal, .byte-modal-content, .semi-modal-content, .semi-modal, div'))
                .filter(visible)
                .map(el => {
                    const rect = el.getBoundingClientRect();
                    const text = compactText(el);
                    const area = rect.width * rect.height;
                    let score = 0;
                    if (text.includes('发布设置')) score += 10;
                    if (text.includes('确认发布')) score += 6;
                    if (text.includes('定时发布')) score += 8;
                    if (text.includes('日期')) score += 8;
                    if (text.includes('时间')) score += 5;
                    if (text.includes('预告关键词')) score += 5;
                    if (rect.width >= 350 && rect.width <= 760 && rect.height >= 250 && rect.height <= 850) score += 3;
                    return {el, rect, text, area, score};
                })
                .filter(x => x.score >= 14)
                .sort((a, b) => b.score - a.score || a.area - b.area);
        }
        function labelCenter(root, text) {
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
            for (let node; (node = walker.nextNode());) {
                if (!node.nodeValue || !node.nodeValue.includes(text)) continue;
                const parent = node.parentElement;
                if (!visible(parent)) continue;
                const rect = parent.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
            }
            return null;
        }
        document.querySelectorAll('[data-fanqie-scheduled-date-input="1"]').forEach(el => el.removeAttribute('data-fanqie-scheduled-date-input'));
        const candidates = modalCandidates();
        const root = candidates.length ? candidates[0].el : document.body;
        const dateLabel = labelCenter(root, '日期');
        const timeLabel = labelCenter(root, '时间');
        const inputs = Array.from(root.querySelectorAll('input, [contenteditable="true"], [role="textbox"], .arco-picker input, .semi-input, .arco-input'))
            .filter(visible)
            .map(el => {
                const rect = el.getBoundingClientRect();
                const value = String(el.value || el.getAttribute('value') || compactText(el) || '');
                let score = 0;
                if (/^\d{4}-\d{2}-\d{2}$/.test(value)) score += 35;
                if (/^\d{1,2}:\d{2}$/.test(value)) score -= 40;
                if (dateLabel) {
                    const y = rect.top + rect.height / 2;
                    score += Math.max(0, 24 - Math.abs(y - dateLabel.y));
                    if (rect.left > dateLabel.x) score += 6;
                }
                if (timeLabel) {
                    const y = rect.top + rect.height / 2;
                    score -= Math.max(0, 20 - Math.abs(y - timeLabel.y));
                }
                if (rect.width >= 120 && rect.width <= 460 && rect.height >= 24 && rect.height <= 56) score += 4;
                return {el, rect, score, value};
            })
            .filter(x => x.score >= 12)
            .sort((a, b) => b.score - a.score || a.rect.top - b.rect.top);
        if (inputs.length) {
            inputs[0].el.setAttribute('data-fanqie-scheduled-date-input', '1');
            return true;
        }
        const rootRect = root.getBoundingClientRect();
        if (dateLabel && rootRect.width > 0) {
            const x = Math.min(rootRect.right - 40, rootRect.left + rootRect.width * 0.72);
            const y = dateLabel.y;
            const target = document.elementFromPoint(x, y);
            const clickable = target && (target.closest('input, [role="textbox"], [contenteditable="true"], .arco-picker, .semi-input, .arco-input, div') || target);
            if (clickable && visible(clickable)) {
                clickable.setAttribute('data-fanqie-scheduled-date-input', '1');
                return true;
            }
        }
        return false;
    }
    '''
    try:
        return bool(page.evaluate(script))
    except Exception:
        return False


def _read_marked_scheduled_publish_date(page: Page) -> str | None:
    script = r'''
    () => {
        const el = document.querySelector('[data-fanqie-scheduled-date-input="1"]');
        if (!el) return null;
        const value = String(el.value || el.getAttribute('value') || el.innerText || el.textContent || '').trim();
        const match = value.match(/\d{4}-\d{2}-\d{2}/);
        return match ? match[0] : null;
    }
    '''
    try:
        value = page.evaluate(script)
    except Exception:
        value = None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _click_and_fill_scheduled_publish_date(page: Page, *, scheduled_date: str) -> None:
    loc = page.locator('[data-fanqie-scheduled-date-input="1"]').first
    try:
        loc.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass
    try:
        loc.click(timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(250)
    try:
        loc.fill(scheduled_date, timeout=2500)
        page.wait_for_timeout(300)
        return
    except Exception:
        pass
    try:
        page.keyboard.press("Control+A")
        page.keyboard.type(scheduled_date)
        page.wait_for_timeout(300)
    except Exception:
        pass


def _choose_date_picker_value(page: Page, *, scheduled_date: str) -> bool:
    script = r'''
    (scheduledDate) => {
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
        function disabled(el) {
            const cls = String(el.className || '').toLowerCase();
            return el.getAttribute('aria-disabled') === 'true' || el.getAttribute('disabled') !== null ||
                   el.disabled === true || cls.includes('disabled') || cls.includes('disable');
        }
        function compactText(el) {
            return ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, '').trim();
        }
        function clickElement(el) {
            if (!el || !visible(el) || disabled(el)) return false;
            try {
                el.scrollIntoView({block: 'center', inline: 'center'});
                el.click();
                return true;
            } catch (e) {
                return false;
            }
        }
        const parts = scheduledDate.split('-').map(x => parseInt(x, 10));
        if (parts.length !== 3 || parts.some(Number.isNaN)) return false;
        const [year, month, day] = parts;
        const targetDay = String(day);
        const targetDate = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const roots = Array.from(document.querySelectorAll('.arco-picker-container, .arco-trigger-popup, .semi-portal, .semi-popover, .semi-date-picker, .semi-datepicker, [class*="picker-panel"], [class*="date-picker"], [class*="datepicker"]'))
            .filter(visible)
            .map(el => {
                const rect = el.getBoundingClientRect();
                const text = compactText(el);
                let score = 0;
                if (text.includes(String(year))) score += 6;
                if (text.includes(String(month))) score += 3;
                if (text.includes(targetDay)) score += 4;
                if (rect.width >= 180 && rect.width <= 720 && rect.height >= 180 && rect.height <= 720) score += 3;
                return {el, rect, score};
            })
            .filter(x => x.score >= 6)
            .sort((a, b) => b.score - a.score || b.rect.top - a.rect.top);
        if (!roots.length) return false;
        const root = roots[0].el;
        const cells = Array.from(root.querySelectorAll('[title], [aria-label], td, button, [role="button"], div, span'))
            .filter(visible)
            .map(el => {
                const clickable = el.closest('button, [role="button"], td, [class*="cell"], [class*="date"]') || el;
                const rect = clickable.getBoundingClientRect();
                const text = compactText(el) || compactText(clickable);
                const title = String(el.getAttribute('title') || clickable.getAttribute('title') || '');
                const aria = String(el.getAttribute('aria-label') || clickable.getAttribute('aria-label') || '');
                const attrs = `${title} ${aria}`;
                let score = 0;
                if (title.includes(targetDate) || aria.includes(targetDate)) score += 40;
                if (attrs.includes(String(year)) && attrs.includes(String(month)) && attrs.includes(targetDay)) score += 24;
                if (text === targetDay) score += 16;
                if (text.endsWith(targetDay) && text.length <= 4) score += 8;
                if (disabled(clickable) || disabled(el)) score -= 100;
                if (rect.width >= 20 && rect.width <= 80 && rect.height >= 20 && rect.height <= 80) score += 2;
                return {el, clickable, rect, score};
            })
            .filter(x => x.score >= 16)
            .sort((a, b) => b.score - a.score || a.rect.top - b.rect.top || a.rect.left - b.rect.left);
        for (const item of cells) {
            if (clickElement(item.clickable) || clickElement(item.el)) return true;
        }
        return false;
    }
    '''
    try:
        clicked = bool(page.evaluate(script, scheduled_date))
    except Exception:
        clicked = False
    page.wait_for_timeout(250)
    return clicked


def _force_scheduled_publish_date_value(page: Page, *, scheduled_date: str) -> bool:
    script = r'''
    (scheduledDate) => {
        const el = document.querySelector('[data-fanqie-scheduled-date-input="1"]');
        if (!el) return false;
        function fire(target, name) {
            target.dispatchEvent(new Event(name, {bubbles: true, cancelable: true}));
        }
        try {
            if ('value' in el) {
                const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
                if (descriptor && descriptor.set) descriptor.set.call(el, scheduledDate);
                else el.value = scheduledDate;
                el.setAttribute('value', scheduledDate);
                fire(el, 'input');
                fire(el, 'change');
                fire(el, 'blur');
                return true;
            }
            if (el.isContentEditable) {
                el.textContent = scheduledDate;
                fire(el, 'input');
                fire(el, 'change');
                fire(el, 'blur');
                return true;
            }
            el.setAttribute('value', scheduledDate);
            fire(el, 'input');
            fire(el, 'change');
            fire(el, 'blur');
            return true;
        } catch (e) {
            return false;
        }
    }
    '''
    try:
        return bool(page.evaluate(script, scheduled_date))
    except Exception:
        return False


def _mark_scheduled_publish_time_target(page: Page) -> bool:
    script = r'''
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
        function modalCandidates() {
            return Array.from(document.querySelectorAll('[role="dialog"], .arco-modal-content, .arco-modal, .byte-modal, .byte-modal-content, .semi-modal-content, .semi-modal, div'))
                .filter(visible)
                .map(el => {
                    const rect = el.getBoundingClientRect();
                    const text = compactText(el);
                    const area = rect.width * rect.height;
                    let score = 0;
                    if (text.includes('发布设置')) score += 10;
                    if (text.includes('确认发布')) score += 6;
                    if (text.includes('定时发布')) score += 8;
                    if (text.includes('预告关键词')) score += 8;
                    if (rect.width >= 350 && rect.width <= 760 && rect.height >= 250 && rect.height <= 850) score += 3;
                    return {el, rect, text, area, score};
                })
                .filter(x => x.score >= 10)
                .sort((a, b) => b.score - a.score || a.area - b.area);
        }
        function labelCenter(root, text) {
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
            for (let node; (node = walker.nextNode());) {
                if (!node.nodeValue || !node.nodeValue.includes(text)) continue;
                const parent = node.parentElement;
                if (!visible(parent)) continue;
                const rect = parent.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
            }
            return null;
        }
        document.querySelectorAll('[data-fanqie-scheduled-time-input="1"]').forEach(el => el.removeAttribute('data-fanqie-scheduled-time-input'));
        const candidates = modalCandidates();
        const root = candidates.length ? candidates[0].el : document.body;
        const timeLabel = labelCenter(root, '时间');
        const dateLabel = labelCenter(root, '日期');
        const inputs = Array.from(root.querySelectorAll('input, [contenteditable="true"], [role="textbox"], .arco-picker input, .semi-input, .arco-input'))
            .filter(visible)
            .map(el => {
                const rect = el.getBoundingClientRect();
                const value = String(el.value || el.getAttribute('value') || compactText(el) || '');
                let score = 0;
                if (/^\d{1,2}:\d{2}$/.test(value)) score += 30;
                if (/^\d{4}-\d{2}-\d{2}$/.test(value)) score -= 40;
                if (timeLabel) {
                    const y = rect.top + rect.height / 2;
                    score += Math.max(0, 22 - Math.abs(y - timeLabel.y));
                    if (rect.left > timeLabel.x) score += 6;
                }
                if (dateLabel) {
                    const y = rect.top + rect.height / 2;
                    score -= Math.max(0, 18 - Math.abs(y - dateLabel.y));
                }
                if (rect.width >= 90 && rect.width <= 420 && rect.height >= 24 && rect.height <= 56) score += 4;
                return {el, rect, score, value};
            })
            .filter(x => x.score >= 10)
            .sort((a, b) => b.score - a.score || b.rect.top - a.rect.top);
        if (inputs.length) {
            inputs[0].el.setAttribute('data-fanqie-scheduled-time-input', '1');
            return true;
        }
        const rootRect = root.getBoundingClientRect();
        if (timeLabel && rootRect.width > 0) {
            const x = Math.min(rootRect.right - 40, rootRect.left + rootRect.width * 0.72);
            const y = timeLabel.y;
            const target = document.elementFromPoint(x, y);
            const clickable = target && (target.closest('input, [role="textbox"], [contenteditable="true"], .arco-picker, .semi-input, .arco-input, div') || target);
            if (clickable && visible(clickable)) {
                clickable.setAttribute('data-fanqie-scheduled-time-input', '1');
                return true;
            }
        }
        return false;
    }
    '''
    try:
        return bool(page.evaluate(script))
    except Exception:
        return False


def _click_and_fill_scheduled_publish_time(page: Page, *, scheduled_time: str) -> None:
    loc = page.locator('[data-fanqie-scheduled-time-input="1"]').first
    try:
        loc.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass
    try:
        loc.click(timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(300)
    try:
        loc.fill(scheduled_time, timeout=2500)
        page.wait_for_timeout(300)
        return
    except Exception:
        pass
    try:
        page.keyboard.press("Control+A")
        page.keyboard.type(scheduled_time)
        page.wait_for_timeout(300)
    except Exception:
        pass


def _choose_time_picker_value(page: Page, *, scheduled_time: str) -> None:
    hour, minute = scheduled_time.split(":", 1)
    for text in (hour.zfill(2), minute.zfill(2), "确定"):
        clicked = False
        try:
            loc = page.get_by_text(text, exact=True)
            count = locator_count_safe(loc)
            for i in reversed(range(count)):
                item = loc.nth(i)
                try:
                    if item.is_visible():
                        item.scroll_into_view_if_needed(timeout=1500)
                        item.click(timeout=2500)
                        clicked = True
                        break
                except Exception:
                    continue
        except Exception:
            clicked = False
        if not clicked:
            _click_time_picker_text_with_js(page, text)
        page.wait_for_timeout(250)


def _click_time_picker_text_with_js(page: Page, text: str) -> bool:
    script = r'''
    (targetText) => {
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
        function clickAt(x, y) {
            const el = document.elementFromPoint(x, y);
            if (!el) return false;
            const clickable = el.closest('button, [role="button"], li, div, span') || el;
            try {
                clickable.click();
                return true;
            } catch (e) {
                try { el.click(); return true; } catch (e2) { return false; }
            }
        }
        const roots = Array.from(document.querySelectorAll('.arco-picker-container, .arco-trigger-popup, .semi-portal, .semi-popover, [role="dialog"], body'))
            .filter(visible)
            .map(el => {
                const rect = el.getBoundingClientRect();
                const text = compactText(el);
                let score = 0;
                if (text.includes('此刻') || text.includes('确定')) score += 8;
                if (text.includes(targetText)) score += 10;
                if (rect.width >= 120 && rect.width <= 420 && rect.height >= 120 && rect.height <= 520) score += 4;
                return {el, rect, score};
            })
            .filter(x => x.score >= 10)
            .sort((a, b) => b.score - a.score || b.rect.top - a.rect.top);
        const root = roots.length ? roots[0].el : document.body;
        const items = Array.from(root.querySelectorAll('button, [role="button"], li, div, span'))
            .filter(visible)
            .map(el => {
                const rect = el.getBoundingClientRect();
                const text = compactText(el);
                let score = 0;
                if (text === targetText) score += 20;
                if (text.includes(targetText) && targetText === '确定') score += 12;
                if (rect.width >= 20 && rect.width <= 120 && rect.height >= 18 && rect.height <= 60) score += 2;
                return {el, rect, score};
            })
            .filter(x => x.score >= 20)
            .sort((a, b) => b.rect.top - a.rect.top || b.score - a.score);
        for (const item of items) {
            const r = item.rect;
            if (clickAt(r.left + r.width / 2, r.top + r.height / 2)) return true;
        }
        return false;
    }
    '''
    try:
        return bool(page.evaluate(script, text))
    except Exception:
        return False


def _force_scheduled_publish_time_value(page: Page, *, scheduled_time: str) -> bool:
    script = r'''
    (scheduledTime) => {
        const el = document.querySelector('[data-fanqie-scheduled-time-input="1"]');
        if (!el) return false;
        function fire(target, name) {
            target.dispatchEvent(new Event(name, {bubbles: true, cancelable: true}));
        }
        try {
            if ('value' in el) {
                const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
                if (descriptor && descriptor.set) descriptor.set.call(el, scheduledTime);
                else el.value = scheduledTime;
                fire(el, 'input');
                fire(el, 'change');
                fire(el, 'blur');
                return true;
            }
            if (el.isContentEditable) {
                el.textContent = scheduledTime;
                fire(el, 'input');
                fire(el, 'change');
                fire(el, 'blur');
                return true;
            }
            el.setAttribute('value', scheduledTime);
            fire(el, 'input');
            fire(el, 'change');
            fire(el, 'blur');
            return true;
        } catch (e) {
            return false;
        }
    }
    '''
    try:
        return bool(page.evaluate(script, scheduled_time))
    except Exception:
        return False

def click_confirm_publish(page: Page, log=print) -> None:
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

