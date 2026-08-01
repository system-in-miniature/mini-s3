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

    def test_authored_file_sections_bind_exactly_to_patch_paths(self) -> None:
        for card in self.cards:
            expected = {
                item.path for item in render_pages.split_file_patches(card.patch)
            }
            for chinese, body in ((False, card.english), (True, card.chinese)):
                with self.subTest(stage=card.number, chinese=chinese):
                    lesson = render_pages.parse_localized_lesson(
                        body,
                        card_number=card.number,
                        chinese=chinese,
                        file_patches=render_pages.split_file_patches(card.patch),
                    )
                    paths = [item.path for item in lesson.files]
                    self.assertEqual(set(paths), expected)
                    self.assertEqual(len(paths), len(set(paths)))

    def test_required_explanation_precedes_files_and_verification_follows(self) -> None:
        headings = (
            (
                False,
                "### The problem at this point",
                "### Failure preview",
                "### Basic concepts",
                "### Why this mechanism is necessary",
                "### Runtime mental model",
                "### File-by-file walkthrough",
                "### Verification evidence",
                "### Durable takeaways",
            ),
            (
                True,
                "### 当前遇到的问题",
                "### 先看会坏在哪里",
                "### 基本概念",
                "### 为什么需要这个机制",
                "### 运行时心智模型",
                "### 逐文件走读",
                "### 验证证据",
                "### 需要真正记住的内容",
            ),
        )
        for card in self.cards:
            for chinese, *ordered in headings:
                body = card.chinese if chinese else card.english
                with self.subTest(stage=card.number, chinese=chinese):
                    positions = [body.index(heading) for heading in ordered]
                    self.assertEqual(positions, sorted(positions))

    def test_key_code_must_be_short_and_match_its_file_patch(self) -> None:
        file_patch = render_pages.FilePatch(
            path="src/minis3/example.py",
            patch=(
                "diff --git a/src/minis3/example.py b/src/minis3/example.py\n"
                "new file mode 100644\n"
                "--- /dev/null\n"
                "+++ b/src/minis3/example.py\n"
                "@@ -0,0 +1,2 @@\n"
                "+def answer() -> int:\n"
                "+    return 42\n"
            ),
            role_rank=0,
            changed_symbols=("answer",),
        )
        valid = """### Goal

### Deliverable files

### The problem at this point

Problem.

### Failure preview

One failing behavior.

### Basic concepts

Concepts.

### Why this mechanism is necessary

Necessity.

### Runtime mental model

Flow.

### File-by-file walkthrough

<!-- journey-file: src/minis3/example.py -->
#### `src/minis3/example.py`

##### Key code

```python
def answer() -> int:
    return 42
```

### Verification evidence

Evidence.

### Durable takeaways

Takeaway.

### Explain it in your own words

Summary.

### Textbook

Book.
"""
        lesson = render_pages.parse_localized_lesson(
            valid,
            card_number=99,
            chinese=False,
            file_patches=[file_patch],
        )
        self.assertEqual(lesson.files[0].code_slices, ("def answer() -> int:\n    return 42",))

        missing = valid.replace("return 42", "return 41")
        with self.assertRaisesRegex(ValueError, "stage-99.*src/minis3/example.py"):
            render_pages.parse_localized_lesson(
                missing,
                card_number=99,
                chinese=False,
                file_patches=[file_patch],
            )

        long_slice = "\n".join(f"line_{index}" for index in range(16))
        too_long = valid.replace(
            "def answer() -> int:\n    return 42",
            long_slice,
        )
        with self.assertRaisesRegex(ValueError, "at most 15"):
            render_pages.parse_localized_lesson(
                too_long,
                card_number=99,
                chinese=False,
                file_patches=[file_patch],
            )

    def test_stage_page_has_one_localized_walkthrough_per_changed_file(self) -> None:
        expectations = (
            (False, "### File-by-file walkthrough", "File diff: "),
            (True, "### 逐文件走读", "文件差异："),
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

    def test_deliverable_file_lists_are_collapsed_in_browser_pages(self) -> None:
        english = render_pages.render_card(self.stage_one, chinese=False)
        chinese = render_pages.render_card(self.stage_one, chinese=True)

        self.assertIn('### Deliverable files\n\n??? note "Show deliverable files"', english)
        self.assertIn('### 交付文件\n\n??? note "展开交付文件"', chinese)
        self.assertIn("    - `src/minis3/model.py`", english)
        self.assertIn("    - `src/minis3/model.py`", chinese)

    def test_all_stages_have_bilingual_authored_teaching_content(self) -> None:
        self.assertEqual(len(self.cards), 15)
        for card in self.cards:
            with self.subTest(stage=card.number, language="en"):
                self.assertIn("### Basic concepts", card.english)
                self.assertIn("### Why this mechanism is necessary", card.english)
                self.assertIn("##### Statement understanding", card.english)
            with self.subTest(stage=card.number, language="zh"):
                self.assertIn("### 基本概念", card.chinese)
                self.assertIn("### 为什么需要这个机制", card.chinese)
                self.assertIn("##### 关键语句理解", card.chinese)

    def test_every_implementation_stage_adds_executable_evidence(self) -> None:
        for card in self.cards[:-1]:
            with self.subTest(stage=card.number):
                paths = [item.path for item in render_pages.split_file_patches(card.patch)]
                self.assertTrue(
                    any(path.startswith("tests/") for path in paths),
                    f"stage-{card.number:02d} changes behavior without stage-owned tests",
                )

    def test_pages_close_with_verification_takeaways_and_learner_explanation(self) -> None:
        expectations = (
            (
                False,
                "### Verification evidence",
                "### Durable takeaways",
                "### Explain it in your own words",
            ),
            (True, "### 验证证据", "### 需要真正记住的内容", "### 用自己的话讲清楚"),
        )
        for card in self.cards:
            for chinese, verification, takeaways, explanation in expectations:
                with self.subTest(stage=card.number, chinese=chinese):
                    page = render_pages.render_card(card, chinese=chinese)
                    self.assertIn(verification, page)
                    self.assertIn(takeaways, page)
                    self.assertIn(explanation, page)
                    self.assertLess(page.index(verification), page.index(takeaways))
                    self.assertLess(page.index(takeaways), page.index(explanation))
                    self.assertNotIn("do not copy the patch first", page.lower())
                    self.assertNotIn("不要先复制补丁", page)

    def test_all_stage_pages_cover_every_canonical_file_once(self) -> None:
        for card in self.cards:
            expected_paths = [item.path for item in render_pages.split_file_patches(card.patch)]
            for chinese, label in ((False, "File diff: "), (True, "文件差异：")):
                with self.subTest(stage=card.number, chinese=chinese):
                    page = render_pages.render_card(card, chinese=chinese)
                    self.assertEqual(page.count(label), len(expected_paths))
                    for path in expected_paths:
                        self.assertEqual(page.count(f"{label}{path}"), 1)

    def test_rendered_pages_do_not_use_generic_teaching_boilerplate(self) -> None:
        forbidden = (
            "Supporting project wiring for this stage.",
            "本阶段所需的项目支撑接线。",
            "Which test would fail first",
            "如果绕过新边界，哪个测试会最先失败",
        )
        for card in self.cards:
            for chinese in (False, True):
                page = render_pages.render_card(card, chinese=chinese)
                for phrase in forbidden:
                    self.assertNotIn(phrase, page)


if __name__ == "__main__":
    unittest.main()
