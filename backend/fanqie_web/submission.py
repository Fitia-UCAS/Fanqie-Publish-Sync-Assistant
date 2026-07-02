from __future__ import annotations

from playwright.sync_api import Page

from backend.fanqie_web.schedule import ScheduledPublishSlot

from backend.fanqie_web.ui_actions import locator_count_safe
from backend.fanqie_web.browser_session import save_debug
from backend.fanqie_web.submission_dialogs import (
    choose_ai_option,
    click_basic_content_check_if_present,
    click_confirm_submit,
    daily_submit_limit_visible,
    publish_settings_visible,
)
from backend.fanqie_web.schedule_picker import ensure_scheduled_publish, ensure_scheduled_publish_at_10
from backend.fanqie_web.edit_dialogs import click_continue_edit_if_present, click_typo_submit_if_present

def _click_next_step_once(page: Page) -> bool:


    try:
        loc = page.get_by_role("button", name="下一步")
        count = locator_count_safe(loc)
        for i in reversed(range(count)):
            item = loc.nth(i)
            try:
                if item.is_visible() and item.is_enabled():
                    item.scroll_into_view_if_needed()
                    item.click(timeout=10000)
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
        function disabled(el) {
            const cls = String(el.className || '').toLowerCase();
            return el.disabled === true ||
                   el.getAttribute('aria-disabled') === 'true' ||
                   el.getAttribute('disabled') !== null ||
                   cls.includes('disabled') || cls.includes('disable');
        }
        function compactText(el) {
            return ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, '').trim();
        }
        const raw = Array.from(document.querySelectorAll('button, [role="button"], a, span, div'))
            .filter(visible)
            .map(el => {
                const clickable = el.closest('button, [role="button"], a') || el;
                const rect = clickable.getBoundingClientRect();
                const tag = clickable.tagName.toLowerCase();
                const cls = String(clickable.className || '').toLowerCase();
                let score = 0;
                if (compactText(el) === '下一步') score += 12;
                if (compactText(clickable) === '下一步') score += 10;
                if (tag === 'button') score += 10;
                if (clickable.getAttribute('role') === 'button') score += 8;
                if (cls.includes('button') || cls.includes('btn')) score += 4;
                if (rect.top > window.innerHeight * 0.45) score += 2;
                if (rect.width >= 50 && rect.width <= 220 && rect.height >= 24 && rect.height <= 70) score += 2;
                return {el, clickable, score, rect};
            })
            .filter(x => x.score >= 18)
            .filter(x => visible(x.clickable) && !disabled(x.clickable))
            .sort((a, b) => b.score - a.score || b.rect.top - a.rect.top || b.rect.left - a.rect.left);
        for (const item of raw) {
            try {
                item.clickable.scrollIntoView({block: 'center', inline: 'center'});
                item.clickable.click();
                return true;
            } catch (e) {
                try {
                    item.el.click();
                    return true;
                } catch (e2) {}
            }
        }
        return false;
    }
    """
    try:
        return bool(page.evaluate(script))
    except Exception:
        return False

def _wait_for_submit_settings(page: Page, *, debug_prefix: str, wait_label: str, log=print) -> None:
    log("正在点击下一步...")
    save_debug(page, f"{debug_prefix}_next_step_before")

    for attempt in range(1, 4):
        if not _click_next_step_once(page):
            if attempt == 3:
                raise RuntimeError("未找到“下一步”按钮。")
            page.wait_for_timeout(1000)
            continue

        for _ in range(80):
            try:
                if click_basic_content_check_if_present(page, log=log, timeout_ms=500):
                    page.wait_for_timeout(1000)
                    if publish_settings_visible(page):
                        save_debug(page, f"{debug_prefix}_settings_visible_after_basic_check")
                        return
            except Exception:
                pass

            if publish_settings_visible(page):
                save_debug(page, f"{debug_prefix}_settings_visible_after_next")
                return

            try:
                if daily_submit_limit_visible(page):
                    save_debug(page, f"{debug_prefix}_daily_limit_after_next", force=True)
                    raise RuntimeError("今日发布章节数已达上限，请明天再试。")
            except RuntimeError:
                raise
            except Exception:
                pass

            try:
                click_typo_submit_if_present(page, log=log, timeout_ms=500)
                click_continue_edit_if_present(page, log=log, timeout_ms=500)
            except Exception:
                pass

            page.wait_for_timeout(500)

        if attempt < 3:
            save_debug(page, f"{debug_prefix}_settings_not_visible_attempt_{attempt}")
            log(f"未等到{wait_label}弹窗，重试点击“下一步”...")
            page.wait_for_timeout(1200)

    save_debug(page, f"{debug_prefix}_next_step_failed", force=True)
    raise RuntimeError(f"点击“下一步”后仍未检测到{wait_label}弹窗，可能被页面校验/保存状态拦截。")


def _complete_submission_after_save(
    page: Page,
    *,
    debug_prefix: str,
    wait_label: str,
    done_message: str,
    timeout_message: str,
    use_ai: bool = False,
    log=print,
    scheduled_slot: ScheduledPublishSlot | None = None,
) -> None:
    save_debug(page, f"{debug_prefix}_submit_flow_start")
    _wait_for_submit_settings(page, debug_prefix=debug_prefix, wait_label=wait_label, log=log)

    confirmed = False
    for round_no in range(1, 8):
        blocking = False

        try:
            if click_basic_content_check_if_present(page, log=log, timeout_ms=1200):
                blocking = True
        except Exception:
            pass

        try:
            if click_typo_submit_if_present(page, log=log, timeout_ms=1200):
                blocking = True
        except Exception:
            pass

        try:
            if click_continue_edit_if_present(page, log=log, timeout_ms=1200):
                blocking = True
        except Exception:
            pass

        if publish_settings_visible(page):
            save_debug(page, f"{debug_prefix}_settings_visible_round_{round_no}")
            if scheduled_slot is not None:
                ensure_scheduled_publish(page, scheduled_date=scheduled_slot.date, scheduled_time=scheduled_slot.time, log=log)
            else:
                ensure_scheduled_publish_at_10(page, log=log)
            choose_ai_option(page, use_ai=use_ai, log=log)
            click_confirm_submit(page, log=log)
            confirmed = True
            blocking = True

        try:
            if daily_submit_limit_visible(page):
                save_debug(page, f"{debug_prefix}_daily_limit", force=True)
                raise RuntimeError("今日发布章节数已达上限，请明天再试。")
        except RuntimeError:
            raise
        except Exception:
            pass

        if confirmed:
            for _ in range(40):
                try:
                    if click_basic_content_check_if_present(page, log=log, timeout_ms=500):
                        blocking = True
                except Exception:
                    pass
                try:
                    if click_typo_submit_if_present(page, log=log, timeout_ms=500):
                        blocking = True
                except Exception:
                    pass
                try:
                    if click_continue_edit_if_present(page, log=log, timeout_ms=500):
                        blocking = True
                except Exception:
                    pass
                if not publish_settings_visible(page) and not content_detection_visible(page):
                    break
                page.wait_for_timeout(500)
            if not blocking:
                save_debug(page, f"{debug_prefix}_submit_flow_done")
                log(done_message)
                return

        if not blocking:
            page.wait_for_timeout(600)

    save_debug(page, f"{debug_prefix}_submit_flow_timeout", force=True)
    raise RuntimeError(timeout_message)


def complete_publish_submission(page: Page, use_ai: bool = False, log=print, scheduled_slot: ScheduledPublishSlot | None = None) -> None:
    _complete_submission_after_save(
        page,
        debug_prefix="publish",
        wait_label="发布设置",
        done_message="发布确认流程完成。",
        timeout_message="发布确认流程超时：可能停在内容检测方式、错别字提示、AI 设置或确认发布弹窗。",
        use_ai=use_ai,
        log=log,
        scheduled_slot=scheduled_slot,
    )


def complete_sync_submission(page: Page, use_ai: bool = False, log=print, scheduled_slot: ScheduledPublishSlot | None = None) -> None:
    _complete_submission_after_save(
        page,
        debug_prefix="sync",
        wait_label="提交设置",
        done_message="同步提交确认流程完成。",
        timeout_message="同步提交确认流程超时：可能停在内容检测方式、错别字提示、AI 设置或确认发布弹窗。",
        use_ai=use_ai,
        log=log,
        scheduled_slot=scheduled_slot,
    )
