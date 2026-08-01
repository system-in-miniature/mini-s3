#!/usr/bin/env python3
"""Contracts for browser-native per-file Journey lessons."""

from __future__ import annotations

from pathlib import Path
import tempfile
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
                "### Mechanism blocks",
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
                "### 机制板块",
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

### Mechanism blocks

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

    def test_stage_page_uses_each_implementation_diff_as_its_separator(self) -> None:
        expectations = (
            (False, "### Mechanism blocks", "File diff: "),
            (True, "### 机制板块", "文件差异："),
        )
        paths = [
            path
            for block in self.stage_one.blocks
            if not block.supporting
            for path in block.files
            if not path.startswith("tests/")
        ]
        for chinese, heading, label in expectations:
            with self.subTest(chinese=chinese):
                page = render_pages.render_card(self.stage_one, chinese=chinese)
                self.assertIn(heading, page)
                mechanism_section = page[page.index(heading):]
                self.assertEqual(mechanism_section.count(label), len(paths))
                for path in paths:
                    self.assertEqual(mechanism_section.count(f'{label}{path}"'), 1)
                self.assertNotIn("View block diff (", mechanism_section)
                self.assertNotIn("查看本板块差异（", mechanism_section)
                self.assertIn("Complete reference patch / 完整参考补丁", page)
                self.assertEqual(page.count("diff --git "), self.stage_one.patch.count("diff --git "))

    def test_test_diff_and_explanation_precede_basic_concepts(self) -> None:
        expectations = (
            (
                False,
                "### Test contract",
                "#### See the failure first",
                '??? note "File diff: tests/test_bucket.py"',
                "This contract exercises the aggregate",
                "### Basic concepts",
                "### Mechanism blocks",
            ),
            (
                True,
                "### 测试契约",
                "#### 先看会坏在哪里",
                '??? note "文件差异：tests/test_bucket.py"',
                "这个契约先单测聚合",
                "### 基本概念",
                "### 机制板块",
            ),
        )
        stage_two = self.cards[1]
        for chinese, contract, failure, drawer, explanation, concepts, mechanisms in expectations:
            with self.subTest(chinese=chinese):
                page = render_pages.render_card(stage_two, chinese=chinese)
                self.assertLess(page.index(contract), page.index(drawer))
                self.assertLess(page.index(contract), page.index(failure))
                self.assertLess(page.index(failure), page.index(drawer))
                self.assertLess(page.index(drawer), page.index(explanation))
                self.assertLess(page.index(explanation), page.index(concepts))
                self.assertLess(page.index(concepts), page.index(mechanisms))
                self.assertEqual(page.count(drawer), 1)
                self.assertNotIn(drawer, page[page.index(mechanisms):])

    def test_authored_test_lessons_are_not_stored_under_mechanism_blocks(self) -> None:
        stage_two = self.cards[1]
        expectations = (
            (stage_two.english, "### Test contract", "### Basic concepts", "### Mechanism blocks", "### Verification evidence"),
            (stage_two.chinese, "### 测试契约", "### 基本概念", "### 机制板块", "### 验证证据"),
        )
        marker = "<!-- journey-file: tests/test_bucket.py -->"
        for body, contract, concepts, mechanisms, verification in expectations:
            with self.subTest(contract=contract):
                test_section = body[body.index(contract):body.index(concepts)]
                mechanism_section = body[body.index(mechanisms):body.index(verification)]
                self.assertIn(marker, test_section)
                self.assertNotIn(marker, mechanism_section)

    def test_failure_preview_uses_test_specific_walkthrough_labels(self) -> None:
        stage_two = self.cards[1]
        expectations = (
            (
                False,
                "#### See the failure first",
                "### Basic concepts",
                (
                    "What this test locks",
                    "How it constructs the counterexample",
                    "Key test statement",
                    "What a failure means",
                ),
                (
                    "What it is and why it appears",
                    "Runtime role",
                    "Key code",
                    "Statement understanding",
                ),
            ),
            (
                True,
                "#### 先看会坏在哪里",
                "### 基本概念",
                ("测试锁定什么", "如何构造反例", "关键测试语句", "失败意味着什么"),
                ("是什么，为什么现在需要", "在运行时做什么", "关键代码", "关键语句理解"),
            ),
        )
        for chinese, start, end, required, forbidden in expectations:
            with self.subTest(chinese=chinese):
                page = render_pages.render_card(stage_two, chinese=chinese)
                preview = page[page.index(start):page.index(end)]
                for label in required:
                    self.assertIn(f"**{label}**", preview)
                for label in forbidden:
                    self.assertNotIn(f"**{label}**", preview)

    def test_core_explanation_follows_its_file_drawer_without_a_path_label(self) -> None:
        expectations = (
            (
                False,
                '??? note "File diff: src/minis3/errors.py"',
                "This file defines protocol-independent domain failures.",
                '??? note "File diff: src/minis3/model.py"',
                "This is the stage's central domain-value file.",
            ),
            (
                True,
                '??? note "文件差异：src/minis3/errors.py"',
                "这里定义与 HTTP 无关的领域错误。",
                '??? note "文件差异：src/minis3/model.py"',
                "这是本阶段的核心领域值文件，",
            ),
        )
        for chinese, first_drawer, first_prose, second_drawer, second_prose in expectations:
            with self.subTest(chinese=chinese):
                page = render_pages.render_card(self.stage_one, chinese=chinese)
                self.assertLess(page.index(first_drawer), page.index(first_prose))
                self.assertLess(page.index(first_prose), page.index(second_drawer))
                self.assertLess(page.index(second_drawer), page.index(second_prose))
                self.assertNotIn("**Explanation:", page)
                self.assertNotIn("**讲解：", page)

    def test_block_layouts_cover_every_patch_file_exactly_once(self) -> None:
        for card in self.cards:
            expected = [item.path for item in render_pages.split_file_patches(card.patch)]
            actual = [*card.failure_files, *(path for block in card.blocks for path in block.files)]
            with self.subTest(stage=card.number):
                self.assertEqual(set(actual), set(expected))
                self.assertEqual(len(actual), len(set(actual)))

    def test_test_files_belong_only_to_failure_preview(self) -> None:
        for card in self.cards:
            expected = {
                item.path
                for item in render_pages.split_file_patches(card.patch)
                if item.path.startswith("tests/")
            }
            mechanism_files = {path for block in card.blocks for path in block.files}
            with self.subTest(stage=card.number):
                self.assertEqual(set(card.failure_files), expected)
                self.assertFalse(mechanism_files & expected)

    def test_test_only_stages_do_not_render_an_empty_mechanism_section(self) -> None:
        for card in (self.cards[6], self.cards[7], self.cards[11]):
            headings = ((False, "### Mechanism blocks"), (True, "### 机制板块"))
            for chinese, heading in headings:
                with self.subTest(stage=card.number, chinese=chinese):
                    page = render_pages.render_card(card, chinese=chinese)
                    self.assertNotIn(heading, page)

    def test_block_layout_rejects_duplicate_file_ownership(self) -> None:
        layout = """
[[blocks]]
id = "first"
title_en = "First"
title_zh = "第一"
summary_en = "First summary."
summary_zh = "第一段说明。"
files = ["src/example.py"]

[[blocks]]
id = "second"
title_en = "Second"
title_zh = "第二"
summary_en = "Second summary."
summary_zh = "第二段说明。"
files = ["src/example.py"]
"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "layout.toml"
            path.write_text(layout)
            with self.assertRaisesRegex(ValueError, "duplicates=.*src/example.py"):
                render_pages.load_block_layouts(
                    path,
                    stage_label="stage-99",
                    patch_paths={"src/example.py"},
                )

    def test_supporting_files_skip_per_file_browser_explanations(self) -> None:
        english = render_pages.render_card(self.stage_one, chinese=False)
        chinese = render_pages.render_card(self.stage_one, chinese=True)

        self.assertIn("#### Object value vocabulary", english)
        self.assertIn("#### Package and tooling scaffold", english)
        self.assertIn("#### 对象值词汇", chinese)
        self.assertIn("#### 包与工具脚手架", chinese)
        self.assertIn("This is the stage's central domain-value file.", english)
        self.assertNotIn("small learner-workspace entry point", english)
        self.assertNotIn("这是小型学习仓库的入口", chinese)
        self.assertIn('??? note "Supporting file diffs (4 files)"', english)
        self.assertIn('??? note "支撑文件差异（4 个文件）"', chinese)
        self.assertNotIn('??? note "File diff: README.md"', english)
        self.assertNotIn('??? note "文件差异：README.md"', chinese)
        for path in ("README.md", "pyproject.toml", "src/minis3/__init__.py", "uv.lock"):
            self.assertEqual(english.count(f"**`{path}`**"), 1)
            self.assertEqual(chinese.count(f"**`{path}`**"), 1)
        for path in (
            "README.md",
            "pyproject.toml",
            "src/minis3/__init__.py",
            "src/minis3/errors.py",
            "src/minis3/model.py",
            "tests/test_model.py",
            "uv.lock",
        ):
            self.assertNotIn(f"#### `{path}`", english)
            self.assertNotIn(f"#### `{path}`", chinese)

    def test_deliverable_file_lists_are_collapsed_in_browser_pages(self) -> None:
        english = render_pages.render_card(self.stage_one, chinese=False)
        chinese = render_pages.render_card(self.stage_one, chinese=True)

        self.assertIn('??? note "Deliverable files"', english)
        self.assertIn('??? note "交付文件"', chinese)
        self.assertNotIn("### Deliverable files", english)
        self.assertNotIn("### 交付文件", chinese)
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
                    self.assertEqual(page.count("diff --git "), len(expected_paths))
                    core_paths = [
                        path
                        for block in card.blocks
                        if not block.supporting
                        for path in block.files
                        if not path.startswith("tests/")
                    ]
                    supporting_paths = [
                        path
                        for block in card.blocks
                        if block.supporting
                        for path in block.files
                    ]
                    test_paths = [path for path in expected_paths if path.startswith("tests/")]
                    for path in core_paths:
                        self.assertEqual(page.count(f'{label}{path}"'), 1)
                    for path in supporting_paths:
                        self.assertEqual(page.count(f"**`{path}`**"), 1)
                    concepts = "### 基本概念" if chinese else "### Basic concepts"
                    for path in test_paths:
                        drawer = f'{label}{path}"'
                        self.assertEqual(page.count(drawer), 1)
                        self.assertLess(page.index(drawer), page.index(concepts))

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
