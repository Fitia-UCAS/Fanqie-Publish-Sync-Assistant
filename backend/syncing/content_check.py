from __future__ import annotations

from typing import Callable

from backend.syncing.local_source import Chapter
from backend.syncing.plan import SyncPlan, SyncedChapter
from backend.fanqie_web.submission import complete_sync_submission
from backend.fanqie_web.list_counts import verify_single_chapter_count
from backend.fanqie_web.browser_session import save_debug


def confirm_same_content_if_needed(
    page,
    *,
    chapter_no: int,
    options: SyncPlan,
    local: Chapter,
    log: Callable[[str], None],
) -> SyncedChapter | None:
    if not options.is_publish_to_remote:
        return None
    log("编辑页内容已与本地一致，继续执行发布确认。")
    complete_sync_submission(page, use_ai=options.use_ai, log=log)
    save_debug(page, "after_sync_submit_same_content")
    if options.verify_after_publish:
        verify_single_chapter_count(
            page,
            chapter_no=chapter_no,
            chapter_manage_url=options.chapter_manage_url,
            local=local,
            action_name="同步",
            log=log,
        )
    msg = "完成：编辑页内容已一致，并已发布确认。"
    log(msg)
    return SyncedChapter(ok=True, changed=False, published=True, message=msg)
