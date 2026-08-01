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


@dataclass(frozen=True)
class FilePatch:
    path: str
    patch: str
    role_rank: int
    changed_symbols: tuple[str, ...]


@dataclass(frozen=True)
class FileLesson:
    path: str
    body: str
    code_slices: tuple[str, ...]


@dataclass(frozen=True)
class LocalizedLesson:
    pre_walkthrough: str
    files: tuple[FileLesson, ...]
    post_walkthrough: str


PATCH_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.MULTILINE)
PYTHON_SYMBOL = re.compile(r"^\+\s*(?:async\s+)?(?:def|class)\s+(\w+)", re.MULTILINE)
TEST_SYMBOL = re.compile(r"^\+def\s+(test_\w+)", re.MULTILINE)
FILE_MARKER = re.compile(r"<!-- journey-file: ([^\n]+) -->")
CODE_FENCE = re.compile(
    r"^##### (?:Key code|关键代码)\s*\n+```[^\n]*\n(.*?)\n```",
    re.MULTILINE | re.DOTALL,
)

REQUIRED_HEADINGS = {
    False: (
        "### Goal",
        "### Deliverable files",
        "### The problem at this point",
        "### Failure preview",
        "### Basic concepts",
        "### Why this mechanism is necessary",
        "### Runtime mental model",
        "### File-by-file walkthrough",
        "### Verification evidence",
        "### Durable takeaways",
        "### Explain it in your own words",
        "### Textbook",
    ),
    True: (
        "### 目标",
        "### 交付文件",
        "### 当前遇到的问题",
        "### 先看会坏在哪里",
        "### 基本概念",
        "### 为什么需要这个机制",
        "### 运行时心智模型",
        "### 逐文件走读",
        "### 验证证据",
        "### 需要真正记住的内容",
        "### 用自己的话讲清楚",
        "### 教材",
    ),
}


def role_rank(path: str) -> int:
    if path in {
        "src/minis3/errors.py",
        "src/minis3/model.py",
        "src/minis3/multipart.py",
        "src/minis3/conditional.py",
        "src/minis3/lifecycle.py",
    }:
        return 0
    if path == "src/minis3/bucket.py":
        return 1
    if path.startswith("src/minis3/storage/"):
        return 2
    if path == "src/minis3/listing.py":
        return 3
    if path == "src/minis3/store.py":
        return 4
    if path == "src/minis3/__init__.py":
        return 5
    if path.startswith("tests/"):
        return 6
    return 7


def split_file_patches(patch: str) -> list[FilePatch]:
    matches = list(PATCH_HEADER.finditer(patch))
    if not matches and patch:
        raise ValueError("stage patch has no diff --git headers")
    result: list[FilePatch] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(patch)
        file_patch = patch[match.start():end]
        path = match.group(2)
        result.append(
            FilePatch(
                path=path,
                patch=file_patch,
                role_rank=role_rank(path),
                changed_symbols=tuple(dict.fromkeys(PYTHON_SYMBOL.findall(file_patch))),
            )
        )
    return result


def order_file_patches(file_patches: list[FilePatch]) -> list[FilePatch]:
    return sorted(file_patches, key=lambda item: item.role_rank)


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


def _heading_positions(body: str, headings: tuple[str, ...], *, label: str) -> None:
    positions: list[int] = []
    for heading in headings:
        occurrences = [match.start() for match in re.finditer(rf"^{re.escape(heading)}$", body, re.MULTILINE)]
        if len(occurrences) != 1:
            raise ValueError(f"{label}: expected one {heading!r}, found {len(occurrences)}")
        positions.append(occurrences[0])
    if positions != sorted(positions):
        raise ValueError(f"{label}: required lesson headings are out of order")


def _post_patch_text(file_patch: FilePatch) -> str:
    """Return changed-hunk after-state text for authored slice validation."""

    lines: list[str] = []
    inside_hunk = False
    for line in file_patch.patch.splitlines():
        if line.startswith("@@"):
            inside_hunk = True
            continue
        if not inside_hunk or line.startswith("\\ No newline"):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:].rstrip())
        elif line.startswith(" "):
            lines.append(line[1:].rstrip())
    return "\n".join(lines)


def _normalize_slice(code: str) -> str:
    lines = [line.rstrip() for line in code.strip("\n").splitlines()]
    if not lines:
        return ""
    indent = min((len(line) - len(line.lstrip()) for line in lines if line.strip()), default=0)
    return "\n".join(line[indent:] if line.strip() else "" for line in lines)


def _slice_in_patch(code: str, after_text: str) -> bool:
    wanted = _normalize_slice(code)
    wanted_lines = wanted.splitlines()
    source_lines = after_text.splitlines()
    for start in range(len(source_lines) - len(wanted_lines) + 1):
        window = "\n".join(source_lines[start:start + len(wanted_lines)])
        if _normalize_slice(window) == wanted:
            return True
    return False


def parse_localized_lesson(
    body: str,
    *,
    card_number: int,
    chinese: bool,
    file_patches: list[FilePatch],
) -> LocalizedLesson:
    language = "zh" if chinese else "en"
    label = f"stage-{card_number:02d} {language}"
    headings = REQUIRED_HEADINGS[chinese]
    _heading_positions(body, headings, label=label)

    walkthrough_heading = "### 逐文件走读" if chinese else "### File-by-file walkthrough"
    verification_heading = "### 验证证据" if chinese else "### Verification evidence"
    walkthrough_start = body.index(walkthrough_heading) + len(walkthrough_heading)
    verification_start = body.index(verification_heading, walkthrough_start)
    walkthrough = body[walkthrough_start:verification_start].strip()
    markers = list(FILE_MARKER.finditer(walkthrough))
    if not markers:
        raise ValueError(f"{label}: no journey-file sections")

    patch_by_path = {item.path: item for item in file_patches}
    files: list[FileLesson] = []
    for index, marker in enumerate(markers):
        path = marker.group(1).strip()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(walkthrough)
        file_body = walkthrough[marker.end():end].strip()
        expected_heading = f"#### `{path}`"
        if not file_body.startswith(expected_heading):
            raise ValueError(f"{label} {path}: marker must be followed by {expected_heading}")
        if path not in patch_by_path:
            raise ValueError(f"{label} {path}: file is absent from stage.patch")

        slices = tuple(_normalize_slice(match) for match in CODE_FENCE.findall(file_body))
        after_text = _post_patch_text(patch_by_path[path])
        for code in slices:
            if len([line for line in code.splitlines() if line.strip()]) > 15:
                raise ValueError(f"{label} {path}: key code must contain at most 15 nonblank lines")
            if code and not _slice_in_patch(code, after_text):
                raise ValueError(f"{label} {path}: key code does not match stage.patch")
        files.append(FileLesson(path=path, body=file_body, code_slices=slices))

    paths = [item.path for item in files]
    if len(paths) != len(set(paths)):
        raise ValueError(f"{label}: duplicate journey-file section")
    expected_paths = {item.path for item in file_patches}
    actual_paths = set(paths)
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        raise ValueError(f"{label}: walkthrough coverage mismatch; missing={missing}, extra={extra}")

    return LocalizedLesson(
        pre_walkthrough=body[:walkthrough_start].rstrip(),
        files=tuple(files),
        post_walkthrough=body[verification_start:].strip(),
    )


def _render_diff(file_patch: FilePatch, *, chinese: bool) -> str:
    label = "文件差异：" if chinese else "File diff: "
    lines = [f'??? note "{label}{file_patch.path}"', "    ```diff"]
    lines.extend(
        f"    {clean}" if (clean := line.rstrip()) else ""
        for line in file_patch.patch.splitlines()
    )
    lines.append("    ```")
    return "\n".join(lines)


def _collapse_deliverables(prelude: str, *, chinese: bool) -> str:
    heading = "### 交付文件" if chinese else "### Deliverable files"
    label = "交付文件" if chinese else "Deliverable files"
    heading_start = prelude.index(heading)
    content_start = heading_start + len(heading)
    next_heading = prelude.index("\n### ", content_start)
    items = prelude[content_start:next_heading].strip()
    indented = "\n".join(f"    {line}" if line else "" for line in items.splitlines())
    collapsed = f'??? note "{label}"\n{indented}\n\n'
    return prelude[:heading_start] + collapsed + prelude[next_heading + 1:]


def render_card(card: Card, *, chinese: bool) -> str:
    title = card.chinese_title if chinese else card.english_title
    body = card.chinese if chinese else card.english
    file_patches = split_file_patches(card.patch)
    lesson = parse_localized_lesson(
        body,
        card_number=card.number,
        chinese=chinese,
        file_patches=file_patches,
    )
    patch_by_path = {item.path: item for item in file_patches}
    file_sections = [
        f"{item.body}\n\n{_render_diff(patch_by_path[item.path], chinese=chinese)}"
        for item in lesson.files
    ]
    link_label = "在 GitHub 查看阶段差异" if chinese else "Compare this stage on GitHub"
    checkout = (
        f"完成后可运行 `git checkout stage-{card.number:02d}` 对照你的结果。"
        if chinese
        else f"After finishing, use `git checkout stage-{card.number:02d}` to compare your result."
    )
    patch_link = f"{REPO_URL}/blob/main/journey/stages/{card.number:02d}-{card.slug}/stage.patch"
    return (
        f"# Stage {card.number:02d} · {title}\n\n"
        f"{_collapse_deliverables(lesson.pre_walkthrough, chinese=chinese)}\n\n"
        + "\n\n".join(file_sections)
        + f"\n\n{lesson.post_walkthrough}\n\n"
        f"[{link_label}]({compare_link(card.number)})\n\n"
        f"{checkout}\n\n"
        f"[Complete reference patch / 完整参考补丁]({patch_link})\n"
    )


def render_index(cards: list[Card], *, chinese: bool) -> str:
    if chinese:
        lines = [
            "# 自主重建",
            "",
            "每个 Stage 都是一节可独立浏览的完整课：先理解当前问题、基本概念与必要性，再逐文件读懂关键语句，最后用验证证据和自己的话完成理解闭环。",
            "",
            "这是三种学习模式中的浏览器自主学习路径。按主题学习请进入[机制教程](../tutorial/index.md)；需要 CLI 互动请查看 [Agent 带教使用教程](../agent-guided.md)。",
            "",
            "如果希望在编辑器里聚焦当前增量，运行 `python journey/tools/build_journey.py study N`，再打开 `../MiniS3-journey-workspace`。",
            "",
            "| Stage | 主题 | 新增测试 | 教材章节 |",
            "|---:|---|---:|---:|",
        ]
    else:
        lines = [
            "# Self-Guided Rebuild",
            "",
            "Each Stage is a complete independent-browser lesson: understand the current problem, concepts, and necessity; read each changed file and its critical statements; then close with evidence and your own explanation.",
            "",
            "This is the browser-based path among MiniS3's three learning modes. Use the [Mechanism Tutorial](../tutorial/index.md) for topic-oriented study, or the [Agent-Guided usage guide](../agent-guided.md) for interactive CLI teaching.",
            "",
            "For an editor-focused diff, run `python journey/tools/build_journey.py study N` and open `../MiniS3-journey-workspace`.",
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
