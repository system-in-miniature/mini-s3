#!/usr/bin/env python3
"""Render Journey task cards and indexes from stage facts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
STAGES_ROOT = ROOT / "journey" / "stages"
REPO_URL = "https://github.com/system-in-miniature/mini-s3"
META = re.compile(
    r"<!-- journey: chapter=(?P<chapter>\d+) tests_added=(?P<tests>\d+) -->"
)


@dataclass(frozen=True)
class Card:
    number: int
    slug: str
    english_title: str
    chinese_title: str
    chapter: int
    tests_added: int
    english: str
    chinese: str
    patch: str


def section(text: str, heading: str, next_heading: str | None) -> str:
    start = text.index(heading) + len(heading)
    end = len(text) if next_heading is None else text.index(next_heading, start)
    return text[start:end].strip()


def load_cards() -> list[Card]:
    cards: list[Card] = []
    for directory in sorted(STAGES_ROOT.iterdir()):
        if not directory.is_dir():
            continue
        number_text, slug = directory.name.split("-", 1)
        goal = (directory / "goal.md").read_text()
        title_line = goal.splitlines()[0]
        title_match = re.fullmatch(r"# Stage \d{2} · (.+) / (.+)", title_line)
        meta_match = META.search(goal)
        if title_match is None or meta_match is None:
            raise ValueError(f"invalid goal metadata: {directory}")
        cards.append(
            Card(
                number=int(number_text),
                slug=slug,
                english_title=title_match.group(1),
                chinese_title=title_match.group(2),
                chapter=int(meta_match["chapter"]),
                tests_added=int(meta_match["tests"]),
                english=section(goal, "## English", "## 中文"),
                chinese=section(goal, "## 中文", None),
                patch=(directory / "stage.patch").read_text(),
            )
        )
    return cards


def compare_link(number: int) -> str:
    if number == 1:
        return f"{REPO_URL}/tree/stage-01"
    return f"{REPO_URL}/compare/stage-{number - 1:02d}...stage-{number:02d}"


def render_card(card: Card, *, chinese: bool) -> str:
    title = card.chinese_title if chinese else card.english_title
    body = card.chinese if chinese else card.english
    link_label = "在 GitHub 查看阶段差异" if chinese else "Compare this stage on GitHub"
    note = "先做后看：stage.patch" if chinese else "Try first, then peek: stage.patch"
    checkout = (
        f"完成后可运行 `git checkout stage-{card.number:02d}` 对照你的结果。"
        if chinese
        else f"After finishing, use `git checkout stage-{card.number:02d}` to compare your result."
    )
    return (
        f"# Stage {card.number:02d} · {title}\n\n"
        f"{body}\n\n"
        f"[{link_label}]({compare_link(card.number)})\n\n"
        f"{checkout}\n\n"
        f'??? note "{note}"\n'
        "    ```diff\n"
        + "".join(f"    {line}\n" for line in card.patch.splitlines())
        + "    ```\n"
    )


def render_index(cards: list[Card], *, chinese: bool) -> str:
    if chinese:
        lines = [
            "# MiniS3 Journey",
            "",
            "从空目录开始，依次完成任务卡；先动手，卡住时再展开补丁。",
            "",
            "| Stage | 主题 | 新增测试 | 教材章节 |",
            "|---:|---|---:|---:|",
        ]
    else:
        lines = [
            "# MiniS3 Journey",
            "",
            "Start from an empty tree and complete each task card in order. Build first; peek at the patch only when stuck.",
            "",
            "| Stage | Topic | New tests | Book chapter |",
            "|---:|---|---:|---:|",
        ]
    for card in cards:
        title = card.chinese_title if chinese else card.english_title
        chapter_link = (
            f"../tutorial/{card.chapter:02d}-"
            + {
                1: "getting-started",
                2: "objects-etag",
                3: "versioning",
                4: "listing",
                5: "crash-atomicity",
                6: "multipart",
                7: "conditional",
                8: "lifecycle",
                9: "methodology",
            }[card.chapter]
            + ".md"
        )
        lines.append(
            f"| [{card.number:02d}](stage-{card.number:02d}.md) | {title} | "
            f"{card.tests_added} | [{card.chapter}]({chapter_link}) |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    cards = load_cards()
    for chinese, output in (
        (False, ROOT / "docs" / "journey"),
        (True, ROOT / "docs" / "zh" / "journey"),
    ):
        output.mkdir(parents=True, exist_ok=True)
        expected = {"index.md"}
        for card in cards:
            name = f"stage-{card.number:02d}.md"
            expected.add(name)
            (output / name).write_text(render_card(card, chinese=chinese))
        (output / "index.md").write_text(render_index(cards, chinese=chinese))
        for stale in output.glob("stage-*.md"):
            if stale.name not in expected:
                stale.unlink()
    print(f"rendered {len(cards)} bilingual Journey stages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
