from __future__ import annotations

from datetime import datetime, timedelta

from playwright.sync_api import Page

from backend.fanqie_web.browser_session import save_debug

def set_scheduled_publish_date(page: Page, *, date_increment_days: int) -> str:
    if not find_scheduled_date_field(page):
        save_debug(page, "schedule_publish_date_input_not_found", force=True)
        raise RuntimeError("检测到每日提交字数上限，但未能定位“定时发布”的日期输入框。")

    scheduled_date = _add_days_to_today(max(0, date_increment_days))
    fill_scheduled_date_field(page, scheduled_date=scheduled_date)
    choose_scheduled_date(page, scheduled_date=scheduled_date)
    force_scheduled_date_value(page, scheduled_date=scheduled_date)
    page.wait_for_timeout(400)
    return scheduled_date


def _add_days_to_today(days: int) -> str:
    return (datetime.now() + timedelta(days=max(0, days))).strftime("%Y-%m-%d")



def find_scheduled_date_field(page: Page) -> bool:
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


def read_scheduled_date_field(page: Page) -> str | None:
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


def fill_scheduled_date_field(page: Page, *, scheduled_date: str) -> None:
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


def choose_scheduled_date(page: Page, *, scheduled_date: str) -> bool:
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


def force_scheduled_date_value(page: Page, *, scheduled_date: str) -> bool:
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
