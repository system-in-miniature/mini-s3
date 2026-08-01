#!/usr/bin/env python3
"""Contracts for browser-native per-file Journey lessons."""

from __future__ import annotations

import unittest

from journey.tools import render_pages


class RenderPagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cards = render_pages.load_cards()
        cls.stage_one = cls.cards[0]

    def test_patch_parser_is_lossless_and_display_follows_runtime_roles(self) -> None:
        parsed = render_pages.split_file_patches(self.stage_one.patch)
        self.assertEqual("".join(item.patch for item in parsed), self.stage_one.patch)
        self.assertEqual(len(parsed), self.stage_one.patch.count("diff --git "))

        displayed = render_pages.order_file_patches(parsed)
        paths = [item.path for item in displayed]
        self.assertLess(paths.index("src/minis3/model.py"), paths.index("tests/test_model.py"))
        self.assertLess(paths.index("tests/test_model.py"), paths.index("pyproject.toml"))

    def test_stage_page_has_one_localized_walkthrough_per_changed_file(self) -> None:
        expectations = (
            (False, "### File-by-file diff walkthrough", "File diff: "),
            (True, "### 逐文件 Diff 走读", "文件差异："),
        )
        for chinese, heading, label in expectations:
            with self.subTest(chinese=chinese):
                page = render_pages.render_card(self.stage_one, chinese=chinese)
                self.assertIn(heading, page)
                self.assertEqual(page.count(label), self.stage_one.patch.count("diff --git "))
                self.assertIn(f"{label}src/minis3/model.py", page)
                self.assertIn(f"{label}tests/test_model.py", page)
                self.assertLess(
                    page.index(f"{label}src/minis3/model.py"),
                    page.index(f"{label}tests/test_model.py"),
                )
                self.assertIn("Complete reference patch / 完整参考补丁", page)
                self.assertEqual(page.count("diff --git "), self.stage_one.patch.count("diff --git "))

    def test_all_stages_have_bilingual_mechanism_source_content(self) -> None:
        self.assertEqual(len(self.cards), 15)
        for card in self.cards:
            with self.subTest(stage=card.number, language="en"):
                self.assertIn("### Mechanism walkthrough", card.english)
                self.assertIn("#### Ownership and flow", card.english)
                self.assertIn("#### Failure and debugging", card.english)
            with self.subTest(stage=card.number, language="zh"):
                self.assertIn("### 机制走读", card.chinese)
                self.assertIn("#### 所有权与数据流", card.chinese)
                self.assertIn("#### 失败与排查", card.chinese)

    def test_all_stage_pages_cover_every_canonical_file_once(self) -> None:
        for card in self.cards:
            expected_paths = [item.path for item in render_pages.split_file_patches(card.patch)]
            for chinese, label in ((False, "File diff: "), (True, "文件差异：")):
                with self.subTest(stage=card.number, chinese=chinese):
                    page = render_pages.render_card(card, chinese=chinese)
                    self.assertEqual(page.count(label), len(expected_paths))
                    for path in expected_paths:
                        self.assertEqual(page.count(f"{label}{path}"), 1)


if __name__ == "__main__":
    unittest.main()
