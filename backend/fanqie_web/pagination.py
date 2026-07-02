from __future__ import annotations

from playwright.sync_api import Page

def click_largest_visible_page_number(page: Page) -> bool:
    script = r"""
    () => {
        const all = Array.from(document.querySelectorAll('button,a,li,span,div'));
        function visible(el) {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 &&
                   style.visibility !== 'hidden' && style.display !== 'none';
        }
        const items = all
            .filter(visible)
            .map(el => {
                const text = (el.innerText || el.textContent || '').trim();
                if (!/^\d+$/.test(text)) return null;
                const n = Number(text);
                const rect = el.getBoundingClientRect();
                return {el, n, top: rect.top, left: rect.left, width: rect.width, height: rect.height};
            })
            .filter(Boolean)
            .filter(x => x.n >= 1 && x.n <= 999 && x.top > window.innerHeight * 0.45 && x.width <= 80 && x.height <= 80);
        if (!items.length) return {clicked: false};
        const maxN = Math.max(...items.map(x => x.n));
        const target = items
            .filter(x => x.n === maxN)
            .sort((a, b) => b.top - a.top || b.left - a.left)[0];
        if (!target) return {clicked: false};
        target.el.scrollIntoView({block: 'center', inline: 'center'});
        target.el.click();
        return {clicked: true, page: maxN};
    }
    """
    try:
        result = page.evaluate(script)
        if result and result.get("clicked"):
            page.wait_for_timeout(2500)
            return True
    except Exception:
        pass
    return False

def get_visible_page_numbers(page: Page) -> list[int]:
    script = r"""
    () => {
        const all = Array.from(document.querySelectorAll('button,a,li,span,div'));
        function visible(el) {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 &&
                   style.visibility !== 'hidden' &&
                   style.display !== 'none';
        }
        const nums = all
            .filter(visible)
            .map(el => {
                const text = (el.innerText || el.textContent || '').trim();
                if (!/^\d+$/.test(text)) return null;
                const n = Number(text);
                const rect = el.getBoundingClientRect();
                return {n, top: rect.top, width: rect.width, height: rect.height};
            })
            .filter(Boolean)
            .filter(x => x.n >= 1 && x.n <= 999 && x.top > window.innerHeight * 0.45 && x.width <= 80 && x.height <= 80)
            .map(x => x.n);
        return Array.from(new Set(nums));
    }
    """
    try:
        nums = page.evaluate(script)
        return sorted([int(x) for x in nums if int(x) > 0], reverse=True)
    except Exception:
        return []

def click_page_number(page: Page, page_no: int) -> bool:
    script = r"""
    (pageNo) => {
        const all = Array.from(document.querySelectorAll('button,a,li,span,div'));
        function visible(el) {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 &&
                   style.visibility !== 'hidden' &&
                   style.display !== 'none';
        }
        const candidates = all
            .filter(visible)
            .map(el => {
                const text = (el.innerText || el.textContent || '').trim();
                if (text !== String(pageNo)) return null;
                const rect = el.getBoundingClientRect();
                return {el, top: rect.top, left: rect.left, width: rect.width, height: rect.height};
            })
            .filter(Boolean)
            .filter(x => x.top > window.innerHeight * 0.45 && x.width <= 80 && x.height <= 80)
            .sort((a, b) => b.top - a.top || b.left - a.left);
        if (!candidates.length) return false;
        const target = candidates[0].el.closest('button,a,li') || candidates[0].el;
        target.click();
        return true;
    }
    """
    try:
        ok = page.evaluate(script, int(page_no))
        if ok:
            page.wait_for_timeout(1800)
            return True
    except Exception:
        pass
    return False

def click_next_page(page: Page) -> bool:
    script = r"""
    () => {
        function visible(el) {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 &&
                   style.visibility !== 'hidden' && style.display !== 'none' &&
                   rect.bottom >= 0 && rect.right >= 0 &&
                   rect.top <= window.innerHeight && rect.left <= window.innerWidth;
        }
        function disabled(el) {
            const cls = String(el.className || '').toLowerCase();
            return el.disabled === true ||
                   el.getAttribute('aria-disabled') === 'true' ||
                   cls.includes('disabled') || cls.includes('disable');
        }
        function text(el) {
            return ((el.innerText || el.textContent || el.getAttribute('aria-label') || '') + '').replace(/\s+/g, '').trim();
        }
        const all = Array.from(document.querySelectorAll('button,a,li,span,div'));
        const candidates = all
            .filter(visible)
            .filter(el => !disabled(el))
            .map(el => {
                const t = text(el);
                const cls = String(el.className || '').toLowerCase();
                const aria = String(el.getAttribute('aria-label') || '').toLowerCase();
                const rect = el.getBoundingClientRect();
                let score = 0;
                if (['下一页', '下页', '>', '›', '»'].includes(t)) score += 8;
                if (aria.includes('next')) score += 8;
                if (cls.includes('pagination') && cls.includes('next')) score += 8;
                if (cls.includes('next')) score += 4;
                if (rect.top > window.innerHeight * 0.45) score += 3;
                if (rect.width <= 100 && rect.height <= 80) score += 2;
                return {el, t, score, top: rect.top, left: rect.left, width: rect.width, height: rect.height};
            })
            .filter(x => x.score >= 10 && x.top > window.innerHeight * 0.45 && x.width <= 120 && x.height <= 90)
            .sort((a, b) => b.score - a.score || b.top - a.top || b.left - a.left);
        if (!candidates.length) return false;
        const target = candidates[0].el.closest('button,a,li') || candidates[0].el;
        target.scrollIntoView({block: 'center', inline: 'center'});
        target.click();
        return true;
    }
    """
    try:
        ok = page.evaluate(script)
        if ok:
            page.wait_for_timeout(1800)
            return True
    except Exception:
        pass
    return False

