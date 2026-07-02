from __future__ import annotations

from playwright.sync_api import Page

from backend.fanqie_web.ui_actions import locator_count_safe

def find_scheduled_time_field(page: Page) -> bool:
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


def fill_scheduled_time_field(page: Page, *, scheduled_time: str) -> None:
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


def choose_scheduled_time(page: Page, *, scheduled_time: str) -> None:
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
            click_time_picker_text(page, text)
        page.wait_for_timeout(250)


def click_time_picker_text(page: Page, text: str) -> bool:
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


def force_scheduled_time_value(page: Page, *, scheduled_time: str) -> bool:
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
