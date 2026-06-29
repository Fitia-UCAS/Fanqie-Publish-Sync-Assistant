from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.service_chapter_formatter import format_chapters
from backend.services.service_chapter_text_parser import parse_chapters, read_chapters
from backend.shared.app.app_paths import get_state_paths
from backend.adapters.webnovel_writer.webnovel_writer_storage import WebnovelWriterStorage
from backend.adapters.webnovel_writer.webnovel_writer_vector_rag_v29 import (
    build_true_vector_rag,
    query_true_vector_rag,
    vector_rag_eval_v29,
    vector_rag_gaps_v29,
)
from backend.adapters.webnovel_writer.webnovel_writer_production_v30 import (
    production_gaps_v30,
    production_optimize_v30,
    production_query_v30,
)


class ChapterParserTest(unittest.TestCase):
    def test_parse_complete_txt_with_emojis(self) -> None:
        text = "第1章 (⌐■_■)五位是来相亲的，谁先介绍自己？\n\n正文一。\n\n第2章 (′?w?)他说的好有道理啊，但我总觉得哪里不对劲\n\n正文二。\n"
        chapters = parse_chapters(text)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0].number, 1)
        self.assertIn("(⌐■_■)", chapters[0].title)
        self.assertIn("正文二", chapters[1].body)

    def test_parse_chinese_chapter_numbers(self) -> None:
        chapters = parse_chapters("第一章 风起\n\nA\n\n第十二章 云动\n\nB\n")
        self.assertEqual([chapter.number for chapter in chapters], [1, 12])

    def test_format_chapters_keeps_titles(self) -> None:
        chapters = parse_chapters("第1章 标题？！\n\nA\n")
        self.assertIn("第1章 标题？！", format_chapters(chapters))


    def test_parse_ignores_body_recap_chapter_reference(self) -> None:
        text = (
            "第980章 偷吃的小瑶瑶，众女陆续返回（额外纪元复盘）\n\n"
            "正文。\n\n"
            "第905章 ，圣爷与主角的再度对话中，讨论到纪元破败保留下来了人族的火种。\n\n"
            "其实再追溯到最开始的第32章，首次提到黑雾。\n\n"
            "第981章 下一章标题\n\n"
            "下一章正文。\n"
        )

        chapters = parse_chapters(text)

        self.assertEqual([chapter.number for chapter in chapters], [980, 981])
        self.assertIn("第905章 ，圣爷与主角", chapters[0].body)


class ProjectStructureTest(unittest.TestCase):
    def test_state_paths_exist(self) -> None:
        paths = get_state_paths()
        self.assertIn("chapter_sync_compare", paths)




class WebnovelWriterTrueVectorRagTest(unittest.TestCase):
    def _make_project(self) -> tuple[WebnovelWriterStorage, str]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        storage = WebnovelWriterStorage(root / "projects")
        project_id = str(root / "book")
        storage.create_or_update_project({"projectPath": project_id, "title": "向量测试", "genre": "玄幻"})
        state = storage.load_state(project_id)
        state.setdefault("characters", {})["林澈"] = {"id": "char_linche", "aliases": ["主角"], "status": "调查旧阵眼"}
        state.setdefault("foreshadows", {})["旧阵眼异常"] = {"id": "foreshadow_old_array", "status": "已埋", "description": "第1章发现阵眼发热"}
        storage.save_state(project_id, state)
        storage.save_chapter(project_id, 1, "旧阵眼", "林澈在青云城旧阵眼前停下，掌心感到灼热。李青留下的信物沾着陌生血迹。")
        storage.save_chapter(project_id, 2, "夜市追踪", "夜市里人声鼎沸，林澈追查血迹来源，却发现青云宗巡夜弟子在遮掩真相。")
        storage.save_chapter(project_id, 3, "山门风波", "山门前，长老宣布试炼提前，所有弟子必须进入烈焰谷。")
        return storage, project_id

    def test_build_uses_non_hash_true_vector_index(self) -> None:
        storage, project_id = self._make_project()
        report = build_true_vector_rag(storage, project_id)
        self.assertTrue(report["ok"])
        provider = report["provider"]
        self.assertNotEqual(provider.get("name"), "local_hash_vector")
        self.assertIn(provider.get("embedding_type"), {"tfidf_sparse", "dense"})
        index_path = Path(report["paths_written"]["index"])
        self.assertTrue(index_path.exists())

    def test_query_reranks_relevant_chapter(self) -> None:
        storage, project_id = self._make_project()
        build_true_vector_rag(storage, project_id)
        result = query_true_vector_rag(storage, project_id, "旧阵眼 发热 血迹", top_k=3)
        self.assertTrue(result["ok"])
        self.assertTrue(result["rerank"])
        self.assertGreaterEqual(len(result["results"]), 1)
        self.assertTrue(any(row.get("source") == "chapter" and row.get("chapter_no") == 1 for row in result["results"]))
        self.assertIn("vector_score", result["results"][0]["scores"])

    def test_gap_and_eval_pass_after_build(self) -> None:
        storage, project_id = self._make_project()
        build_true_vector_rag(storage, project_id)
        gaps = vector_rag_gaps_v29(storage, project_id)
        self.assertTrue(gaps["ok"])
        eval_report = vector_rag_eval_v29(storage, project_id)
        self.assertTrue(eval_report["ok"])
        self.assertEqual(eval_report["passed"], eval_report["case_count"])

    def test_production_v30_acceptance_passes(self) -> None:
        storage, project_id = self._make_project()
        report = production_optimize_v30(storage, project_id, chapter_no=1, query="旧阵眼 血迹", top_k=3)
        self.assertTrue(report["ok"])
        self.assertTrue(report["local_production_acceptance"])
        self.assertTrue(Path(report["paths_written"]["json"]).exists())
        self.assertTrue(any(item["name"] == "query_rerank" and item["ok"] for item in report["acceptance"]))

    def test_production_v30_gaps_pass_after_optimize(self) -> None:
        storage, project_id = self._make_project()
        production_optimize_v30(storage, project_id, chapter_no=1, query="青云宗 巡夜", top_k=3)
        gaps = production_gaps_v30(storage, project_id)
        self.assertTrue(gaps["ok"])
        self.assertEqual(gaps["production_aligned"], gaps["total"])

    def test_production_v30_query_uses_explainable_rerank(self) -> None:
        storage, project_id = self._make_project()
        production_optimize_v30(storage, project_id, chapter_no=1, query="旧阵眼", top_k=3)
        result = production_query_v30(storage, project_id, "旧阵眼 发热", top_k=3)
        self.assertTrue(result["ok"])
        self.assertIn(result["rerank_mode"], {"local_explainable", "external_then_local"})
        self.assertGreaterEqual(len(result["results"]), 1)
        self.assertIn("scores", result["results"][0])


if __name__ == "__main__":
    unittest.main()
