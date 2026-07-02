from __future__ import annotations

import json

PLOT_SUMMARY_OUTPUT_SCHEMA = """
单章输出必须是 JSON 对象，不要 Markdown，不要解释。字段固定如下：
- chapter_summary: string，写入《当前剧情.md》的最终段落，必须是“第x章，……”格式。
- chapter_title: string，只保留章节名本身，不要包含“第x章”。例如标题“第12章 我牢顾终于会飞了”只写“我牢顾终于会飞了”。
- chapter_context: object，包含 time、locations、characters。无法明确时 time 写“未明确”，locations/characters 可为空数组，不要硬编。
- event_chain: object，包含 cause、process、result。无法明确时写“未明确”或“需结合前后文确认”，不要脑补。
- key_events: string[]，只写真正改变剧情状态的事件短句，不写泛泛关键词。
- conflicts: string[]，本章主要冲突、矛盾、对立、危机或压力源。
- highlights: string[]，网文爽点、笑点、反转点、打脸点、系统奖励点、信息差点等。
- emotional_beats: string[]，本章主要情绪点，例如震惊、憋屈、愤怒、爽感、尴尬、暧昧、期待、危机感。
- character_updates: string[]，人物关系、立场、认知、境界、状态、动机的变化。
- story_threads: object[]，后续需要记住的剧情线、伏笔、承诺、威胁、信息差、任务、关系线。每项建议包含 type、content、status、needs_followup。
- chapter_hook: object，章末钩子或本章追读点，建议包含 type、content、strength、normal_cliffhanger。没有明确钩子时 content 写“无明确章末钩子”。
- unclear_fields: string[]，信息不足但不是错误的字段说明，例如“本章未明确具体时间，需结合前后文确认”。
- corrections: string[]，已有当前剧情中需要修正的地方。
- warnings: string[]，只记录真实问题：正文疑似缺失、乱码、章号断裂、标题与正文明显不匹配、跨章边界无法判断等。
""".strip()


def build_plot_system_prompt() -> str:
    example = {
        "chapter_summary": "第12章，顾长渊观看系统广告后获得补偿礼包，依次拿到极品灵石、仙级神通《观命》、神级功法《九转不灭身》和禁忌体质《红鸾劫心体》。他用《观命》确认自己只有原主残留的金丹气机、实际战力很弱，却也看见《九转不灭身》带来的保命希望。与此同时，黑金日记本分化出副本飞向宁昭雪、安妙音等人，使几名关键女主开始获得顾长渊的日记信息，真正改变剧情走向的变故由此开启。",
        "chapter_title": "广告过后，补偿礼包终于到账",
        "chapter_context": {
            "time": "顾长渊在醉仙楼写完首篇日记后",
            "locations": ["醉仙楼天字包间", "识海"],
            "characters": ["顾长渊", "系统", "宁昭雪", "安妙音"],
        },
        "event_chain": {
            "cause": "顾长渊完成首篇生存日记并触发补偿礼包。",
            "process": "系统先播放广告，随后发放极品灵石、《观命》《九转不灭身》和《红鸾劫心体（残）》。",
            "result": "顾长渊确认自己战力很弱但获得保命希望，黑金日记本副本飞向关键人物，信息差开始改变剧情。",
        },
        "key_events": [
            "顾长渊领取首篇日记补偿礼包",
            "顾长渊获得《观命》《九转不灭身》和《红鸾劫心体（残）》",
            "黑金日记本副本飞向宁昭雪、安妙音等关键人物",
        ],
        "conflicts": ["顾长渊想摆烂求生，但系统和原剧情仍在推动他入局"],
        "highlights": ["广告反转成万宝阁神兵带货", "补偿礼包一次性给出高价值功法与神通", "日记副本制造女主信息差"],
        "emotional_beats": ["顾长渊吐槽系统广告", "获得奖励后的兴奋", "变故开启的期待感"],
        "character_updates": [
            "顾长渊确认自己当前实战能力很弱，求生欲进一步增强",
            "宁昭雪、安妙音等人即将通过日记副本获得信息差",
        ],
        "story_threads": [
            {"type": "信息差", "content": "日记副本会让女主们获得顾长渊不知道的未来信息", "status": "新建", "needs_followup": True},
            {"type": "能力线", "content": "《九转不灭身》和《红鸾劫心体（残）》后续可能影响顾长渊保命和关系线", "status": "新建", "needs_followup": True},
        ],
        "chapter_hook": {
            "type": "变故钩",
            "content": "黑金日记本副本飞向多名关键人物，后续将改变她们对顾长渊和原剧情的认知。",
            "strength": "strong",
            "normal_cliffhanger": True,
        },
        "unclear_fields": [],
        "corrections": [],
        "warnings": [],
    }
    batch_example = {
        "chapters": [
            {
                "chapter_index": 12,
                **example,
            }
        ],
        "warnings": [],
    }
    return f"""
你现在是小说剧情梗概整理助手。我会提供小说正文、已有《当前剧情》或单章事实素材，请你根据正文内容补充《当前剧情》中缺失的章节剧情总结。

你的任务：
只总结剧情，不要续写正文，不要扩写情节，不要自行脑补小说正文里没有出现的内容。

核心原则：
1. 当前剧情必须“一章一条”，章序边界清楚。不要把两章内容合并成一章，也不要把下一章内容提前写进当前章。
2. chapter_summary 必须写成“第x章，……”格式的一段话，并且它必须能直接追加进《当前剧情.md》。
3. chapter_title 只写章节标题正文，不要写“第x章”。
4. 每章总结默认控制在 200—300 字左右；目标字数只是参考，不要为了凑字或压字牺牲关键信息。
5. 语言风格要贴合已有《当前剧情》：用第三人称按时间顺序概括剧情，一章一段，语气平实清楚，保留必要的搞笑梗、系统设定和章末钩子，但不要写成正文复述。
6. 只总结剧情，不写读后感，不写评价，不写分析文章，不要写成正文段落。
7. 保留关键人物、事件、冲突、人物动机、关系变化、系统任务、奖励、误会、地点、身份、伏笔、承诺、威胁、约定、道具、功法、境界变化和章节钩子。
8. 网文额外要抓：冲突、爽点/笑点/反转点、情绪点、信息差、期待感、追读点。
9. 可以适当保留原文里的搞笑设定和核心梗，但只概括其剧情作用，不要过度扩写颜文字、吐槽、擦边玩笑或口水互动。
10. 不要加入对白式展开，不要复刻大段原文对白。
11. 不要跨章脑补；如果只能看到单章，就只提取本章事实。若时间、地点、人物、事件起因、经过或结果无法明确，写“未明确”或放入 unclear_fields，不要硬编。人物名、地点名、功法名、势力名必须严格照抄正文，不要同音替换、近形字替换或自行改字。
12. 合并阶段可以参考已有当前剧情和最近章节摘要来补足前后文；仍无法确认时，标注“需结合前后文确认”，不要编造。
13. 章末破折号、省略号、反问句、断句、人物登场、视角切换、未说完的话，优先视为正常章末钩子，写进 chapter_hook；不要写进 warnings。
14. 只有真实异常才写 warnings：正文明显缺失、乱码、章号断裂、文件在非章末位置中断、标题与正文明显不匹配、跨章边界无法判断。
15. 如果发现已有当前剧情里对应章节或前后承接可能有不恰当之处，请写进 corrections；不要擅自重写未提供正文的旧章节。

最终写入《当前剧情》的格式要求：
1. 文件顶部可以保留原有标题，例如：# 《书名》剧情；不要为新增章节重复生成标题。
2. 每章只写一个自然段，段落之间空一行。
3. 每章段落必须以“第x章，”开头，使用中文逗号“，”，不要写成“第x章：”“### 第x章”“- 第x章”。
4. 最终 MD 里只保留 chapter_summary 的内容，不要把结构化字段写进 MD 正文。
5. chapter_summary 不要分点，不要列表，不要表格，不要代码块。
6. chapter_summary 内部不要换行，保持单段文本。

{PLOT_SUMMARY_OUTPUT_SCHEMA}

单章输出示例：
{json.dumps(example, ensure_ascii=False, indent=2)}

批量合并输出也必须是 JSON 对象，不要 Markdown，不要解释。字段固定如下：
- chapters: object[]
- warnings: string[]

其中 chapters 内每个对象包含 chapter_index 以及单章输出的所有字段。

批量输出示例：
{json.dumps(batch_example, ensure_ascii=False, indent=2)}
""".strip()


def build_plot_user_prompt(
    *,
    plot_notes: str,
    recent_summaries: str,
    chapter_heading: str,
    chapter_text: str,
    target_words: int = 260,
) -> str:
    safe_words = max(80, min(int(target_words or 260), 500))
    return f"""
下面是此前已经整理好的《当前剧情》。它只用于校对前后承接，不要重新总结整本，也不要改写未提供正文的旧章节。

【已有当前剧情】
{plot_notes or "（暂无，从当前章开始建立。）"}

【最近章节摘要】
{recent_summaries or "（暂无。）"}

请只处理下面这一章：

【当前章节标题】
{chapter_heading}

【当前章节正文】
{chapter_text}

请输出当前章的结构化总结。

要求：
1. chapter_summary 必须保持“第x章，……”格式，使用中文逗号“，”。
2. chapter_title 只保留标题正文，不要包含“第x章”。
3. chapter_summary 必须是一段可以直接写入《当前剧情.md》的最终段落。
4. 只总结这一章的剧情，不要续写，不要扩写，不要脑补。
5. 用第三人称按时间顺序概括剧情，保留关键人物、事件、冲突、人物变化、伏笔和章节钩子。
6. 同时提取 chapter_context、event_chain、conflicts、highlights、emotional_beats、story_threads、chapter_hook。人物名、地点名、功法名、势力名必须严格照抄正文，不要把正文中的名字改成近似字。
7. 时间、地点、人物、起因、经过、结果无法明确时，写“未明确”或放进 unclear_fields，不要硬编。
8. 章末断句、省略号、破折号、反问句或人物登场若属于追读设计，写进 chapter_hook，并将 normal_cliffhanger 设为 true，不要写进 warnings。
9. 可以保留核心搞笑梗、系统设定和关键吐槽，但不要写成正文段落，不要加入对白式展开。
10. chapter_summary 建议控制在 {safe_words} 字左右；信息密度优先，宁可准确，也不要为了短而丢关键伏笔。
11. 不要输出“### 第x章”“第x章：”“- 第x章”这类格式。
12. 不要在 chapter_summary 里分点、列表、表格或换行。
13. 如果发现已有当前剧情与本章承接存在不恰当之处，请写进 corrections。
14. 只有正文疑似不完整、章节标题和内容明显不匹配，或无法判断章号/边界时，才写进 warnings。
""".strip()


def build_plot_fact_prompt(
    *,
    chapter_heading: str,
    chapter_text: str,
    target_words: int = 260,
) -> str:
    safe_words = max(80, min(int(target_words or 260), 500))
    return f"""
请只阅读下面这一章正文，提取“本章事实素材”。

注意：
1. 你现在没有完整前文，只能基于本章正文提取事实，不要脑补前后剧情。
2. chapter_summary 必须写成“第x章，……”格式，使用中文逗号“，”。
3. chapter_title 只保留标题正文，不要包含“第x章”。
4. chapter_summary 必须是一段可以直接写入《当前剧情.md》的最终段落。
5. 只总结剧情，不要续写正文，不要扩写情节，不要自行添加正文里没有的信息。
6. 用第三人称按时间顺序概括剧情，保留关键人物、事件、冲突、人物变化、伏笔和章末钩子。
7. 同时提取 chapter_context、event_chain、conflicts、highlights、emotional_beats、character_updates、story_threads、chapter_hook。人物名、地点名、功法名、势力名必须严格照抄正文，不要把正文中的名字改成近似字。
8. 时间、地点、人物、事件起因、经过或结果无法从本章明确提取时，不要硬编；写“未明确”或在 unclear_fields 说明“需结合前后文确认”。
9. 章末断句、省略号、破折号、反问句、视角切换、人物登场、未说完的话，默认当作正常 chapter_hook，不要当作问题。
10. 可以适当保留原文里的搞笑设定、系统设定和核心梗，但不要写成正文段落，不要加入对白式展开。
11. 不要输出“### 第x章”“第x章：”“- 第x章”这类格式。
12. 不要在 chapter_summary 里分点、列表、表格或换行。
13. 这个结果后续会再按章序合并进《当前剧情》，所以要尽量保留会影响后续的关键信息。
14. chapter_summary 建议控制在 {safe_words} 字左右；目标字数只是参考，不能为了压字丢掉关键剧情。

【当前章节标题】
{chapter_heading}

【当前章节正文】
{chapter_text}

请输出单章 JSON 对象，不要 Markdown，不要解释。
""".strip()


def build_plot_merge_prompt(
    *,
    plot_notes: str,
    recent_summaries: str,
    chapter_heading: str,
    chapter_fact: dict,
    target_words: int = 260,
) -> str:
    safe_words = max(80, min(int(target_words or 260), 500))
    return f"""
下面是此前已经整理好的《当前剧情》。请根据它校对前后承接，并把“本章事实素材”合并成最终的当前剧情条目。

【已有当前剧情】
{plot_notes or "（暂无，从当前章开始建立。）"}

【最近章节摘要】
{recent_summaries or "（暂无。）"}

【当前章节标题】
{chapter_heading}

【本章事实素材】
{json.dumps(chapter_fact, ensure_ascii=False, indent=2)}

请输出当前章最终版结构化总结。

要求：
1. chapter_summary 必须保持“第x章，……”格式，使用中文逗号“，”。
2. chapter_title 只保留标题正文，不要包含“第x章”。
3. chapter_summary 必须是一段可以直接写入《当前剧情.md》的最终段落。
4. 只总结当前章剧情，不要续写，不要扩写，不要脑补正文里没有的信息。
5. 用第三人称按时间顺序概括剧情，语言风格贴合已有《当前剧情》。
6. 保留关键人物、事件、冲突、人物变化、伏笔和章节钩子。
7. 可以根据已有当前剧情和最近章节摘要补足本章事实素材里“需结合前后文确认”的字段；如果仍不能确认，保持“未明确”，不要硬编。
8. 可以修正本章事实素材中的措辞、承接、重复和轻微错位，但不要新增正文中没有的信息。
9. 不要把多个章节合并成一条，也不要把下一章内容提前写进当前章。
10. 章末钩子写进 chapter_hook，不要写进 warnings；正常断句、反问、省略号不是问题。
11. 不要输出“### 第x章”“第x章：”“- 第x章”这类格式。
12. 不要在 chapter_summary 里分点、列表、表格或换行。
13. chapter_summary 建议控制在 {safe_words} 字左右；信息密度优先，宁可准确，也不要为了短而丢关键伏笔。
""".strip()


def build_plot_batch_merge_prompt(
    *,
    plot_notes: str,
    chapter_facts: list[dict],
    target_words: int = 260,
) -> str:
    safe_words = max(80, min(int(target_words or 260), 500))
    return f"""
下面是此前已经整理好的《当前剧情》。请根据它，把多个“单章事实素材”快速合并成可预览的当前剧情条目。

重要限制：
1. 必须按章号从小到大输出 chapters。
2. 每章仍然一条，不要把多个章节合并成一条。
3. chapter_summary 必须保持“第x章，……”格式，使用中文逗号“，”。
4. chapter_title 只保留标题正文，不要包含“第x章”。
5. chapter_summary 必须是一段可以直接写入《当前剧情.md》的最终段落。
6. 只总结剧情，不要续写正文，不要扩写情节，不要自行脑补正文里没有出现的内容。
7. 语言风格要贴合已有《当前剧情》：用第三人称按时间顺序概括剧情，一章一段，保留关键人物、事件、冲突、人物变化和章节钩子。
8. 保留并整理 chapter_context、event_chain、conflicts、highlights、emotional_beats、character_updates、story_threads、chapter_hook。
9. 时间、地点、人物、起因、经过、结果无法确认时，允许写“未明确/需结合前后文确认”，不要硬编。
10. 可以适当保留原文里的搞笑设定、系统设定和核心梗，但不要写成正文段落，不要加入对白式展开。
11. 正常章末断句、破折号、省略号、反问句、人物登场属于 chapter_hook，不属于 warnings。
12. 不要输出“### 第x章”“第x章：”“- 第x章”这类格式。
13. 不要在 chapter_summary 里分点、列表、表格或换行。
14. 这是快速预览模式，不要求像逐章串行那样反复校对状态，但仍要尽量修正明显重复、错位、前后矛盾。
15. 每个 chapter_summary 建议控制在 {safe_words} 字左右；目标字数只是参考，不能为了压字丢掉关键剧情。

【已有当前剧情】
{plot_notes or "（暂无，从当前章开始建立。）"}

【单章事实素材列表】
{json.dumps(chapter_facts, ensure_ascii=False, indent=2)}

请输出批量 JSON 对象，格式为：{{"chapters": [ ... ], "warnings": []}}，不要 Markdown，不要解释。
""".strip()
