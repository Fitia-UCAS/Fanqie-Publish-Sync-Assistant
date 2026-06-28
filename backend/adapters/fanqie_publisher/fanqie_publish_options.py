from __future__ import annotations

from dataclasses import dataclass, field

from backend.adapters.fanqie_web.models import ScheduledPublishSlot
from backend.shared.app.app_runtime_defaults import DEFAULT_CHAPTER_MANAGE_URL


@dataclass(slots=True)
class ChapterPublishOptions:
    chapter_manage_url: str = DEFAULT_CHAPTER_MANAGE_URL
    use_ai: bool = False
    verify_after_publish: bool = True
    debug_screenshots: bool = True
    failure_screenshots: bool = True
    git_tracking: bool = True
    clean_before_run: bool = True
    headless: bool = False
    auth_state_path: str = ""
    schedule_slots: dict[int, ScheduledPublishSlot] = field(default_factory=dict)

    def schedule_for(self, chapter_no: int) -> ScheduledPublishSlot | None:
        return self.schedule_slots.get(chapter_no)


def make_chapter_publish_options(
    *,
    chapter_manage_url: str = DEFAULT_CHAPTER_MANAGE_URL,
    use_ai: bool = False,
    verify_after_publish: bool = True,
    debug_screenshots: bool = True,
    failure_screenshots: bool = True,
    git_tracking: bool = True,
    clean_before_run: bool = True,
    headless: bool = False,
    auth_state_path: str = "",
    schedule_slots: dict[int, ScheduledPublishSlot] | None = None,
) -> ChapterPublishOptions:
    return ChapterPublishOptions(
        chapter_manage_url=chapter_manage_url,
        use_ai=use_ai,
        verify_after_publish=verify_after_publish,
        debug_screenshots=debug_screenshots,
        failure_screenshots=failure_screenshots,
        git_tracking=git_tracking,
        clean_before_run=clean_before_run,
        headless=headless,
        auth_state_path=auth_state_path,
        schedule_slots=dict(schedule_slots or {}),
    )
