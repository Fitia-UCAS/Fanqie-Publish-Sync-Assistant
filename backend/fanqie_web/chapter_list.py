from __future__ import annotations

from playwright.sync_api import Page

from backend.fanqie_web.pagination import click_next_page, click_page_number, get_visible_page_numbers
from backend.fanqie_web.ui_actions import dismiss_popups, ensure_logged_in, goto_chapter_manage, normalize_chapter_no


def scroll_listing_area(page: Page, position: str) -> None:
    script = r"""
    (position) => {
        const targets = [document.scrollingElement || document.documentElement, document.body];
        for (const el of Array.from(document.querySelectorAll('div, section, main'))) {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            if (el.scrollHeight > el.clientHeight + 80) targets.push(el);
        }
        for (const el of targets) {
            if (!el) continue;
            try {
                if (position === 'top') el.scrollTop = 0;
                else if (position === 'middle') el.scrollTop = Math.max(0, (el.scrollHeight - el.clientHeight) / 2);
                else if (position === 'bottom') el.scrollTop = Math.max(0, el.scrollHeight - el.clientHeight);
            } catch (e) {}
        }
    }
    """
    try:
        page.evaluate(script, position)
        page.wait_for_timeout(450)
    except Exception:
        pass

def collect_editor_links_on_current_page(page: Page) -> dict[int, str]:
    script = r"""
    () => {
        function usable(el) {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 &&
                   style.visibility !== 'hidden' && style.display !== 'none';
        }
        function compactText(el) {
            return ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, '').trim();
        }
        function rowScore(el, text) {
            const cls = String(el.className || '').toLowerCase();
            let score = 0;
            if (el.tagName === 'TR') score += 6;
            if (el.getAttribute('role') === 'row') score += 5;
            if (cls.includes('table') && cls.includes('row')) score += 5;
            if (cls.includes('arco-table-tr')) score += 6;
            if (/修改|编辑|查看|章节|发布/.test(text)) score += 2;
            return score;
        }
        function extractFromRow(row) {
            const text = compactText(row);
            if (!text || text.length > 900) return null;
            const chapterMatches = Array.from(text.matchAll(/第\s*([0-9零〇一二两三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟]+)\s*章/g));
            if (!chapterMatches.length) return null;
            const links = Array.from(row.querySelectorAll('a[href]')).filter(usable);
            let link = links.find(a => /modifychapter|chapter|publish/i.test(a.getAttribute('href') || '')) || links[links.length - 1];
            if (!link || !link.href) return null;
            return {rawNo: chapterMatches[0][1], href: link.href, text, score: rowScore(row, text)};
        }
        const roots = Array.from(document.querySelectorAll('tr, .arco-table-tr, [class*="table-row"], [role="row"], li'))
            .filter(usable);
        const looseRoots = Array.from(document.querySelectorAll('a[href*="modifychapter"], a[href*="/publish/"]'))
            .filter(usable)
            .map(a => a.closest('tr, .arco-table-tr, [class*="table-row"], [role="row"], li, div') || a)
            .filter(usable);
        const rows = roots.concat(looseRoots)
            .map(extractFromRow)
            .filter(Boolean)
            .sort((a, b) => b.score - a.score || a.text.length - b.text.length);
        const byNo = new Map();
        for (const item of rows) {
            if (!byNo.has(item.rawNo)) byNo.set(item.rawNo, item);
        }
        return Array.from(byNo.values());
    }
    """
    try:
        items = page.evaluate(script) or []
    except Exception:
        return {}
    result: dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        no = normalize_chapter_no(item.get("rawNo", ""))
        href = str(item.get("href") or "").strip()
        if no and href.startswith(("http://", "https://")):
            result.setdefault(no, href)
    return result

def collect_editor_links_on_current_page_deep(page: Page) -> dict[int, str]:
    result: dict[int, str] = {}

    def merge() -> None:
        for no, href in collect_editor_links_on_current_page(page).items():
            result.setdefault(no, href)

    for pos in ("top", "middle", "bottom"):
        scroll_listing_area(page, pos)
        merge()
    return result

def collect_chapter_rows_on_current_page(page: Page) -> dict[int, dict[str, Any]]:
    script = r"""
    () => {
        function usable(el) {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 &&
                   style.visibility !== 'hidden' && style.display !== 'none' &&
                   rect.bottom >= 0 && rect.right >= 0 &&
                   rect.top <= window.innerHeight && rect.left <= window.innerWidth;
        }
        function clean(s) { return String(s || '').replace(/\r/g, '').trim(); }
        function compact(s) { return clean(s).replace(/\s+/g, ''); }
        function rowScore(el, text) {
            const cls = String(el.className || '').toLowerCase();
            let score = 0;
            if (el.tagName === 'TR') score += 6;
            if (el.getAttribute('role') === 'row') score += 5;
            if (cls.includes('table') && cls.includes('row')) score += 5;
            if (cls.includes('arco-table-tr')) score += 6;
            if (/第\s*[0-9零〇一二两三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟]+\s*章/.test(text)) score += 8;
            if (/已发布|审核|字数/.test(text)) score += 2;
            return score;
        }
        function extractFromRow(row) {
            const rawText = clean(row.innerText || row.textContent || '');
            const text = compact(rawText);
            if (!text || text.length > 1200) return null;
            const m = text.match(/第\s*([0-9零〇一二两三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟]+)\s*章/);
            if (!m) return null;
            const links = Array.from(row.querySelectorAll('a[href]')).filter(usable);
            const link = links.find(a => /modifychapter|chapter|publish/i.test(a.getAttribute('href') || '')) || links[links.length - 1];
            const href = link && link.href ? link.href : '';
            const lines = rawText.split(/\n+/).map(s => clean(s)).filter(Boolean);
            let title = '';
            let titleIndex = -1;
            for (let i = 0; i < lines.length; i++) {
                if (/第\s*[0-9零〇一二两三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟]+\s*章/.test(lines[i])) {
                    title = lines[i];
                    titleIndex = i;
                    break;
                }
            }
            let wordCount = null;
            for (let i = Math.max(0, titleIndex + 1); i < lines.length; i++) {
                const line = lines[i].replace(/,/g, '').trim();
                if (/^[1-9]\d{2,5}$/.test(line)) {
                    wordCount = Number(line);
                    break;
                }
            }
            if (wordCount === null) {
                const afterTitle = text.slice(m.index + m[0].length);
                const mm = afterTitle.match(/([1-9]\d{2,5})(?:0)?(?:已发布|审核|草稿|20\d{2}-)/);
                if (mm) wordCount = Number(mm[1]);
            }
            return {rawNo: m[1], href, title, wordCount, text, score: rowScore(row, text)};
        }
        const roots = Array.from(document.querySelectorAll('tr, .arco-table-tr, [class*="table-row"], [role="row"], li'))
            .filter(usable);
        const looseRoots = Array.from(document.querySelectorAll('a[href*="modifychapter"], a[href*="/publish/"]'))
            .filter(usable)
            .map(a => a.closest('tr, .arco-table-tr, [class*="table-row"], [role="row"], li, div') || a)
            .filter(usable);
        const rows = roots.concat(looseRoots)
            .map(extractFromRow)
            .filter(Boolean)
            .sort((a, b) => b.score - a.score || a.text.length - b.text.length);
        const byNo = new Map();
        for (const item of rows) {
            if (!byNo.has(item.rawNo)) byNo.set(item.rawNo, item);
        }
        return Array.from(byNo.values());
    }
    """
    try:
        items = page.evaluate(script) or []
    except Exception:
        return {}
    result: dict[int, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        no = normalize_chapter_no(item.get("rawNo", ""))
        if not no:
            continue
        word_count = item.get("wordCount")
        try:
            word_count = int(word_count) if word_count is not None else None
        except Exception:
            word_count = None
        result.setdefault(no, {
            "href": str(item.get("href") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "word_count": word_count,
            "text": str(item.get("text") or "")[:500],
        })
    return result

def collect_chapter_rows_on_current_page_deep(page: Page) -> dict[int, dict[str, Any]]:
    result: dict[int, dict] = {}

    def merge() -> None:
        for no, row in collect_chapter_rows_on_current_page(page).items():
            result.setdefault(no, row)

    for pos in ("top", "middle", "bottom"):
        scroll_listing_area(page, pos)
        merge()
    return result

def build_chapter_row_index(
    page: Page,
    chapter_manage_url: str,
    chapter_numbers: list[int],
    log=print,
) -> dict[int, dict]:

    wanted = {int(no) for no in chapter_numbers if int(no) > 0}
    if not wanted:
        return {}
    log("正在读取章节列表字数，用来确认是否真正发布成功...")
    goto_chapter_manage(page, chapter_manage_url)
    ensure_logged_in(page, chapter_manage_url, log=log)
    dismiss_popups(page)

    found: dict[int, dict] = {}
    visited_pages: set[int] = set()
    stagnant_rounds = 0

    def collect() -> int:
        before = len(found)
        for no, row in collect_chapter_rows_on_current_page_deep(page).items():
            if no in wanted:
                found.setdefault(no, row)
        return len(found) - before

    def finish_if_complete() -> bool:
        if wanted.issubset(found):
            log(f"章节列表字数读取完成：{len(found)}/{len(wanted)}")
            return True
        return False

    collect()
    if finish_if_complete():
        return found

    for _ in range(40):
        progressed = False
        visible_numbers = sorted(get_visible_page_numbers(page))
        for page_no in visible_numbers:
            if page_no in visited_pages:
                continue
            visited_pages.add(page_no)
            if click_page_number(page, page_no):
                dismiss_popups(page)
                collect()
                progressed = True
                if finish_if_complete():
                    return found
        before = len(found)
        if click_next_page(page):
            dismiss_popups(page)
            collect()
            progressed = True
            if len(found) > before:
                stagnant_rounds = 0
            else:
                stagnant_rounds += 1
            if finish_if_complete():
                return found
        elif not progressed:
            stagnant_rounds += 1
        if stagnant_rounds >= 3:
            break
    missing = sorted(wanted - set(found))
    if missing:
        preview = ", ".join(str(no) for no in missing[:20])
        if len(missing) > 20:
            preview += " ..."
        log(f"章节列表字数读取部分完成：{len(found)}/{len(wanted)}；未找到章节：{preview}。")
    return found

def build_chapter_editor_index(
    page: Page,
    chapter_manage_url: str,
    chapter_numbers: list[int],
    log=print,
) -> dict[int, str]:





    wanted = {int(no) for no in chapter_numbers if int(no) > 0}
    if not wanted:
        return {}
    log("正在建立章节入口索引，减少逐章翻页定位...")
    goto_chapter_manage(page, chapter_manage_url)
    ensure_logged_in(page, chapter_manage_url, log=log)
    dismiss_popups(page)

    found: dict[int, str] = {}
    visited_pages: set[int] = set()
    stagnant_rounds = 0

    def collect() -> int:
        before = len(found)
        for no, href in collect_editor_links_on_current_page_deep(page).items():
            if no in wanted:
                found.setdefault(no, href)
        return len(found) - before

    def finish_if_complete() -> bool:
        if wanted.issubset(found):
            log(f"章节入口索引完成：{len(found)}/{len(wanted)}")
            return True
        return False

    collect()
    if finish_if_complete():
        return found


    for _ in range(40):
        progressed = False
        visible_numbers = sorted(get_visible_page_numbers(page))
        for page_no in visible_numbers:
            if page_no in visited_pages:
                continue
            visited_pages.add(page_no)
            if click_page_number(page, page_no):
                dismiss_popups(page)
                added = collect()
                progressed = True
                if added:
                    stagnant_rounds = 0
                if finish_if_complete():
                    return found


        before = len(found)
        if click_next_page(page):
            dismiss_popups(page)
            collect()
            progressed = True
            if len(found) > before:
                stagnant_rounds = 0
            else:
                stagnant_rounds += 1
            if finish_if_complete():
                return found
        elif not progressed:
            stagnant_rounds += 1


        if stagnant_rounds >= 3:
            break

    missing = sorted(wanted - set(found))
    if missing:
        preview = ", ".join(str(no) for no in missing[:20])
        if len(missing) > 20:
            preview += " ..."
        log(f"章节入口索引部分完成：{len(found)}/{len(wanted)}；未索引章节：{preview}。这些章节会自动使用常规定位。")
    else:
        log(f"章节入口索引完成：{len(found)}/{len(wanted)}")
    return found

