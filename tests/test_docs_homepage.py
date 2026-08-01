import re
import unittest
from pathlib import Path


class DocumentationHomepageTest(unittest.TestCase):
    def test_homepage_is_fully_bilingual(self) -> None:
        homepage = Path("docs/index.md").read_text(encoding="utf-8")
        headings = [line for line in homepage.splitlines() if line.startswith("#")]

        self.assertTrue(headings)
        self.assertTrue(all(" / " in heading for heading in headings))
        self.assertIn("[Chinese edition / 中文版]", homepage)
        self.assertGreaterEqual(len(re.findall(r"[\u4e00-\u9fff]", homepage)), 120)

    def test_repository_readmes_expose_the_three_learning_modes(self) -> None:
        english = Path("README.md").read_text(encoding="utf-8")
        chinese = Path("README.zh-CN.md").read_text(encoding="utf-8")

        self.assertIn("Mechanism Tutorial", english)
        self.assertIn("Self-Guided Rebuild", english)
        self.assertIn("Agent-Guided Rebuild", english)
        self.assertIn("docs/journey/index.md", english)
        self.assertIn("机制教程", chinese)
        self.assertIn("自主重建", chinese)
        self.assertIn("Agent 带教", chinese)
        self.assertIn("docs/zh/journey/index.md", chinese)

    def test_three_learning_modes_and_agent_usage_guides_are_explicit(self) -> None:
        homepage = Path("docs/index.md").read_text(encoding="utf-8")
        navigation = Path("mkdocs.yml").read_text(encoding="utf-8")
        english_agent = Path("docs/agent-guided.md").read_text(encoding="utf-8")
        chinese_agent = Path("docs/zh/agent-guided.md").read_text(encoding="utf-8")

        for name in (
            "Mechanism Tutorial / 机制教程",
            "Self-Guided Rebuild / 自主重建",
            "Agent-Guided Rebuild / Agent 带教",
        ):
            self.assertIn(name, homepage)

        self.assertIn("Mechanism Tutorial:", navigation)
        self.assertIn("Self-Guided Rebuild:", navigation)
        self.assertIn("Agent-Guided Rebuild:", navigation)
        self.assertIn("build_journey.py agent N", english_agent)
        self.assertIn("AGENTS.md", english_agent)
        self.assertIn("开始 Stage NN", chinese_agent)
        self.assertNotIn("### Basic concepts", english_agent)
        self.assertNotIn("### 基本概念", chinese_agent)


if __name__ == "__main__":
    unittest.main()
