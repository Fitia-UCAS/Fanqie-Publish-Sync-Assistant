from __future__ import annotations

from playwright.sync_api import Locator, Page

from backend.fanqie_web.browser_session import save_debug
from backend.fanqie_web.form_fields import editor_body_counter_confirms
from backend.novel.text_cleaning import normalize_text


def _wait_for_editable_ready(page: Page, loc: Locator, *, timeout_ms: int = 8000) -> None:
    try:
        loc.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        pass
    try:
        loc.evaluate(
            """el => new Promise(resolve => {
                const started = Date.now();
                const ready = () => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const editable = el.isContentEditable ||
                        el.getAttribute('contenteditable') === 'true' ||
                        String(el.className || '').toLowerCase().includes('prosemirror') ||
                        String(el.className || '').toLowerCase().includes('ql-editor') ||
                        el.getAttribute('role') === 'textbox';
                    return editable && rect.width > 0 && rect.height > 0 &&
                        style.visibility !== 'hidden' && style.display !== 'none' &&
                        !el.hasAttribute('disabled') && el.getAttribute('aria-disabled') !== 'true';
                };
                const tick = () => {
                    if (ready() || Date.now() - started > 7500) {
                        resolve(true);
                        return;
                    }
                    requestAnimationFrame(tick);
                };
                tick();
            })"""
        )
    except Exception:
        pass
    try:
        loc.evaluate("el => { el.scrollIntoView({block: 'center', inline: 'nearest'}); el.focus(); }")
    except Exception:
        pass
    page.wait_for_timeout(300)


def _editable_text(loc: Locator) -> str:
    try:
        value = loc.evaluate("el => el.innerText || el.textContent || ''")
        return str(value or "")
    except Exception:
        return ""


def _text_was_written(loc: Locator, text: str) -> bool:
    expected = normalize_text(text)
    current = normalize_text(_editable_text(loc))
    if not expected:
        return True
    if len(expected) < 80:
        return current == expected or expected in current

    return len(current) >= max(80, int(len(expected) * 0.65)) and expected[:40] in current and expected[-40:] in current


def _fill_editable_by_paste(page: Page, loc: Locator, text: str) -> bool:
    save_debug(page, "body_fill_paste_before")
    try:
        loc.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
    except Exception:
        pass
    try:
        loc.click(timeout=5000, force=True)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.evaluate("text => navigator.clipboard && navigator.clipboard.writeText(text)", text)
        page.keyboard.press("Control+V")
        page.wait_for_timeout(450)

        page.keyboard.press("End")
        page.keyboard.press("Space")
        page.wait_for_timeout(120)
        page.keyboard.press("Backspace")
        page.wait_for_timeout(350)
        ok = _text_was_written(loc, text) or editor_body_counter_confirms(page, text)
        save_debug(page, "body_fill_paste_success" if ok else "body_fill_paste_failed")
        return ok
    except Exception:
        save_debug(page, "body_fill_paste_exception")
        return False


def _fill_editable_by_dom(page: Page, loc: Locator, text: str) -> bool:
    save_debug(page, "body_fill_dom_before")
    try:
        loc.evaluate(
            """(el, text) => {
                el.scrollIntoView({block: 'center', inline: 'nearest'});
                el.focus();
                const parts = String(text || '').replace(/\r\n?/g, '\n').split(/\n{2,}/);
                const esc = (s) => s
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;');
                el.innerHTML = parts.map(part => {
                    const lines = part.split('\n').map(esc).join('<br>');
                    return `<p>${lines || '<br>'}</p>`;
                }).join('');
                const range = document.createRange();
                range.selectNodeContents(el);
                range.collapse(false);
                const selection = window.getSelection && window.getSelection();
                if (selection) {
                    selection.removeAllRanges();
                    selection.addRange(range);
                }
                for (const type of ['beforeinput', 'input']) {
                    try {
                        el.dispatchEvent(new InputEvent(type, {bubbles: true, cancelable: true, inputType: 'insertText', data: text}));
                    } catch (_) {
                        el.dispatchEvent(new Event(type, {bubbles: true, cancelable: true}));
                    }
                }
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.blur();
                el.focus();
            }""",
            text,
        )
        page.wait_for_timeout(350)
        try:
            loc.click(timeout=3000, force=True)
            page.keyboard.press("End")
            page.keyboard.press("Space")
            page.wait_for_timeout(120)
            page.keyboard.press("Backspace")
        except Exception:
            pass
        page.wait_for_timeout(350)
        ok = _text_was_written(loc, text) or editor_body_counter_confirms(page, text)
        save_debug(page, "body_fill_dom_success" if ok else "body_fill_dom_failed")
        return ok
    except Exception:
        save_debug(page, "body_fill_dom_exception")
        return False


def _fill_editable_by_keyboard(page: Page, loc: Locator, text: str) -> bool:
    save_debug(page, "body_fill_keyboard_before")
    try:
        loc.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})")
    except Exception:
        pass
    try:
        loc.click(timeout=5000, force=True)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.insert_text(text)
        page.wait_for_timeout(350)
        ok = _text_was_written(loc, text) or editor_body_counter_confirms(page, text)
        save_debug(page, "body_fill_keyboard_success" if ok else "body_fill_keyboard_failed")
        return ok
    except Exception:
        save_debug(page, "body_fill_keyboard_exception")
        return False


def fill_locator(page: Page, loc: Locator, text: str) -> None:
    try:
        tag = str(loc.evaluate("el => (el.tagName || '').toLowerCase()"))
    except Exception:
        tag = ""
    try:
        is_editable = bool(
            loc.evaluate(
                """el => el.isContentEditable || el.getAttribute('contenteditable') === 'true' ||
                        String(el.className || '').toLowerCase().includes('prosemirror') ||
                        String(el.className || '').toLowerCase().includes('ql-editor')"""
            )
        )
    except Exception:
        is_editable = False

    if tag in {"input", "textarea"}:
        save_debug(page, "input_fill_before")
        try:
            loc.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass
        try:
            loc.fill(text, timeout=30000)
            save_debug(page, "input_fill_success")
            return
        except Exception:
            pass
        try:
            loc.evaluate(
                """(el, text) => {
                    el.focus();
                    el.value = text;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }""",
                text,
            )
            save_debug(page, "input_fill_js_success")
            return
        except Exception:
            pass

    if is_editable:
        for attempt in range(2):
            _wait_for_editable_ready(page, loc)
            if _fill_editable_by_paste(page, loc, text):
                return
            if _fill_editable_by_dom(page, loc, text):
                return
            if _fill_editable_by_keyboard(page, loc, text):
                return
            if attempt == 0:
                page.wait_for_timeout(900)
                try:
                    loc.evaluate("el => { el.blur(); el.focus(); }")
                except Exception:
                    pass
        save_debug(page, "body_fill_all_methods_failed", force=True)
        raise RuntimeError("正文编辑器写入失败：页面未接收到正文内容。")

    try:
        loc.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass
    try:
        loc.click(timeout=5000, force=True)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.insert_text(text)
        return
    except Exception:
        pass

    loc.evaluate(
        """(el, text) => {
            el.focus();
            if ('value' in el) {
                el.value = text;
            } else {
                el.innerText = text;
                el.textContent = text;
            }
            el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: text}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
        text,
    )
