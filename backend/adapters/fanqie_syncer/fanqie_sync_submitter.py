from __future__ import annotations

from playwright.sync_api import Page

from backend.adapters.fanqie_web.models import ScheduledPublishSlot

from backend.adapters.fanqie_web.page_actions.chapter_page_interactions import locator_count_safe
from backend.adapters.fanqie_web.browser.browser_session import save_debug
from backend.adapters.fanqie_web.dialogs.publishing_dialogs import (
    choose_ai_option,
    click_basic_content_check_if_present,
    click_confirm_publish,
    daily_submit_limit_visible,
    ensure_scheduled_publish_at_10,
    ensure_scheduled_publish,
    publish_settings_visible,
)
from backend.adapters.fanqie_web.dialogs.editing_dialogs import click_continue_edit_if_present, click_typo_submit_if_present

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

def click_sync_next_step(page: Page, log=print) -> None:
    log("正在点击下一步...")
    save_debug(page, "sync_next_step_before")


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
                        save_debug(page, "sync_settings_visible_after_basic_check")
                        return
            except Exception:
                raise

            if publish_settings_visible(page):
                save_debug(page, "sync_settings_visible_after_next")
                return

            try:
                if click_continue_edit_if_present(page, log=log, timeout_ms=500):
                    page.wait_for_timeout(800)
                    if publish_settings_visible(page):
                        return
            except Exception:
                pass
            try:
                if click_typo_submit_if_present(page, log=log, timeout_ms=500):
                    page.wait_for_timeout(1000)
                    if publish_settings_visible(page):
                        return
            except Exception:
                pass
            page.wait_for_timeout(500)


        if attempt < 3:
            save_debug(page, f"sync_settings_not_visible_attempt_{attempt}")
            log("未等到提交设置弹窗，重试点击“下一步”...")
            page.wait_for_timeout(1200)

    save_debug(page, "sync_next_step_failed", force=True)
    raise RuntimeError("点击“下一步”后仍未检测到提交设置弹窗，可能被页面校验/保存状态拦截。")

def submit_after_sync_save(page: Page, use_ai: bool = False, log=print, scheduled_slot: ScheduledPublishSlot | None = None) -> None:
    save_debug(page, "sync_submit_flow_start")
    click_sync_next_step(page, log=log)

    confirmed = False
    daily_limit_reschedule_attempts = 0
    for round_no in range(1, 70):
        handled = False

        if click_basic_content_check_if_present(page, log=log, timeout_ms=300):
            handled = True

        if click_continue_edit_if_present(page, log=log, timeout_ms=300):
            handled = True

        if click_typo_submit_if_present(page, log=log, timeout_ms=300):
            handled = True

        if publish_settings_visible(page):
            save_debug(page, f"sync_settings_visible_round_{round_no}")
            if scheduled_slot is not None:
                ensure_scheduled_publish(page, scheduled_date=scheduled_slot.date, scheduled_time=scheduled_slot.time, log=log)
            elif daily_submit_limit_visible(page):
                if daily_limit_reschedule_attempts >= 31:
                    raise RuntimeError("检测到每日提交字数上限，已连续尝试向后顺延 31 次定时发布日期，仍未通过。")
                date_increment_days = daily_limit_reschedule_attempts + 1
                ensure_scheduled_publish_at_10(page, date_increment_days=date_increment_days, log=log)
                daily_limit_reschedule_attempts += 1
            choose_ai_option(page, use_ai=use_ai, log=log)
            click_confirm_publish(page, log=log)
            confirmed = True
            handled = True


        if confirmed and click_typo_submit_if_present(page, log=log, timeout_ms=300):
            handled = True

        if confirmed:
            try:
                body = page.locator("body").inner_text(timeout=800)
            except Exception:
                body = ""
            compact = "".join(body.split())
            blocking = (
                ("发布设置" in compact)
                or ("是否使用AI" in compact)
                or ("确认发布" in compact)
                or ("请选择内容检测方式" in compact)
                or ("仅基础检测" in compact and "全面检测" in compact)
                or ("错别字" in compact and "提交" in compact)
                or ("继续编辑" in compact and "刚刚更新" in compact)
            )
            if not blocking:
                save_debug(page, "sync_submit_flow_done")
                log("同步提交确认流程完成。")
                return

        if not handled:
            page.wait_for_timeout(600)

    save_debug(page, "sync_submit_flow_timeout", force=True)
    raise RuntimeError("同步提交确认流程超时：可能停在内容检测方式、错别字提示、AI 设置或确认发布弹窗。")

