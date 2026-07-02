from __future__ import annotations

import threading

from backend.fanqie_web.browser_session import close_context, make_context


def start_login(emit_log):
    emit_log("system", "正在打开自动化浏览器，请在浏览器中登录番茄账号…", "info")
    threading.Thread(target=_login_worker, args=(emit_log,), daemon=True).start()


def _login_worker(emit_log):
    try:
        p, context, page = make_context(headless=False, debug_category="auto_publish")
        page.goto("https://fanqienovel.com/main/writer/login", wait_until="domcontentloaded", timeout=60000)
        emit_log("system", "浏览器已打开，请登录番茄账号，完成后关闭浏览器页面。", "info")
        page.wait_for_event("close")
        close_context(p, context, save_state=True)
        emit_log("system", "登录会话已保存，点击「检测」确认状态。", "success")
    except Exception as exc:
        emit_log("system", f"登录过程异常：{exc}", "error")
