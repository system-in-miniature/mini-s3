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


PATCH_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.MULTILINE)
PYTHON_SYMBOL = re.compile(r"^\+\s*(?:async\s+)?(?:def|class)\s+(\w+)", re.MULTILINE)


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


def split_lesson(body: str, *, chinese: bool) -> tuple[str, str, str]:
    mechanism_heading = "### 机制走读" if chinese else "### Mechanism walkthrough"
    checks_heading = "### 自查" if chinese else "### Self-check"
    mechanism_start = body.index(mechanism_heading)
    checks_start = body.index(checks_heading, mechanism_start)
    return (
        body[:mechanism_start].rstrip(),
        body[mechanism_start:checks_start].strip(),
        body[checks_start:].strip(),
    )


def file_role(path: str, *, chinese: bool) -> str:
    roles = {
        "tests/": ("Executable proof of the stage behavior.", "本阶段行为的可执行证明。"),
        "src/minis3/__init__.py": ("Supported public package surface.", "受支持的包级公开接口。"),
        "src/minis3/errors.py": ("Shared domain failure vocabulary.", "共享的领域失败词汇。"),
        "src/minis3/model.py": ("Immutable values carried through the system.", "贯穿系统的不可变领域值。"),
        "src/minis3/bucket.py": ("Aggregate that owns per-bucket state transitions.", "拥有 Bucket 内部状态迁移的聚合。"),
        "src/minis3/storage/atomic.py": ("Reusable write/fsync/rename durability primitive.", "可复用的 write/fsync/rename 持久性原语。"),
        "src/minis3/storage/disk.py": ("Disk layout, publication, and recovery owner.", "磁盘布局、发布与恢复的所有者。"),
        "src/minis3/storage/__init__.py": ("Storage adapter boundary exports.", "存储适配器边界导出。"),
        "src/minis3/listing.py": ("Read-side projection and pagination logic.", "读取侧投影与分页逻辑。"),
        "src/minis3/store.py": ("Application service coordinating domain and persistence.", "协调领域逻辑与持久化的应用服务。"),
        "src/minis3/multipart.py": ("Multipart values and completion rules.", "Multipart 领域值与完成规则。"),
        "src/minis3/conditional.py": ("ETag precondition matching rules.", "ETag 前置条件匹配规则。"),
        "src/minis3/lifecycle.py": ("Pure lifecycle expiration policy.", "纯生命周期过期策略。"),
        "README.md": ("Journey workspace orientation.", "Journey 工作区入口说明。"),
        "pyproject.toml": ("Install and test configuration.", "安装与测试配置。"),
        "uv.lock": ("Reproducible dependency lock.", "可复现依赖锁。"),
    }
    key = "tests/" if path.startswith("tests/") else path
    english, translated = roles.get(
        key,
        ("Supporting project wiring for this stage.", "本阶段所需的项目支撑接线。"),
    )
    return translated if chinese else english


def file_flow(path: str, *, chinese: bool) -> str:
    if path.startswith("tests/"):
        pair = (
            "Calls the learner-visible boundary and records the expected state or failure; start here only when verifying the mechanism.",
            "调用学习者可见边界并记录预期状态或失败；验证机制时再从这里进入。",
        )
    elif path in {"src/minis3/errors.py", "src/minis3/model.py"}:
        pair = (
            "Constructed by bucket/service code and returned upward without owning I/O; inspect field values when state is correct but results look wrong.",
            "由 Bucket/服务代码构造并向上返回，不拥有 I/O；状态正确但结果异常时检查这些字段。",
        )
    elif path == "src/minis3/bucket.py":
        pair = (
            "Called by `MiniS3`; turns one command plus the current record into the next in-memory history.",
            "由 `MiniS3` 调用；把一次命令和当前记录转换为下一份内存历史。",
        )
    elif path.startswith("src/minis3/storage/"):
        pair = (
            "Called after a domain mutation; turns in-memory state into durable artifacts and reconstructs it on startup.",
            "在领域变更后调用；把内存状态变成持久 Artifact，并在启动时重建。",
        )
    elif path == "src/minis3/listing.py":
        pair = (
            "Called by the service read path; converts stored histories into sorted, paginated response values without mutation.",
            "由服务读取路径调用；把存储历史转换成排序、分页的响应值，不修改状态。",
        )
    elif path in {"src/minis3/multipart.py", "src/minis3/conditional.py", "src/minis3/lifecycle.py"}:
        pair = (
            "Called by `MiniS3` as a policy function; receives explicit values and returns a decision for the service to apply.",
            "由 `MiniS3` 作为策略函数调用；接收显式值并返回由服务执行的决策。",
        )
    elif path == "src/minis3/store.py":
        pair = (
            "Receives public calls, owns locking and orchestration, then delegates to domain, projection, and storage boundaries.",
            "接收公开调用，拥有加锁与编排，再委托给领域、投影和存储边界。",
        )
    elif path == "src/minis3/__init__.py":
        pair = (
            "Reached by user imports; wiring errors appear as missing names before any runtime flow starts.",
            "由用户导入触达；接线错误会在运行时流程开始前表现为名称缺失。",
        )
    else:
        pair = (
            "Supports installation or orientation rather than the runtime data path; debug it when imports, builds, or commands fail before execution.",
            "支撑安装或入口说明，不属于运行时数据流；导入、构建或命令执行前失败时从这里排查。",
        )
    return pair[1] if chinese else pair[0]


def render_file_walkthrough(card: Card, *, chinese: bool) -> str:
    heading = "### 逐文件 Diff 走读" if chinese else "### File-by-file diff walkthrough"
    intro = (
        "按运行时职责阅读，而不是按补丁存储顺序阅读。每个代码块都直接来自 canonical `stage.patch`。"
        if chinese
        else "Read by runtime responsibility, not patch storage order. Every block comes directly from the canonical `stage.patch`."
    )
    label = "文件差异：" if chinese else "File diff: "
    anchors_label = "变化锚点" if chinese else "Changed anchors"
    no_symbols = "配置、导出或文档变化" if chinese else "configuration, export, or documentation change"
    lines = [heading, "", intro, ""]
    for item in order_file_patches(split_file_patches(card.patch)):
        anchors = ", ".join(f"`{name}`" for name in item.changed_symbols) or no_symbols
        lines.extend(
            [
                f"#### `{item.path}`",
                "",
                file_role(item.path, chinese=chinese),
                "",
                file_flow(item.path, chinese=chinese),
                "",
                f"**{anchors_label}:** {anchors}",
                "",
                f'??? note "{label}{item.path}"',
                "    ```diff",
                *[
                    f"    {clean}" if (clean := line.rstrip()) else ""
                    for line in item.patch.splitlines()
                ],
                "    ```",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def render_card(card: Card, *, chinese: bool) -> str:
    title = card.chinese_title if chinese else card.english_title
    body = card.chinese if chinese else card.english
    link_label = "在 GitHub 查看阶段差异" if chinese else "Compare this stage on GitHub"
    checkout = (
        f"完成后可运行 `git checkout stage-{card.number:02d}` 对照你的结果。"
        if chinese
        else f"After finishing, use `git checkout stage-{card.number:02d}` to compare your result."
    )
    patch_link = (
        f"{REPO_URL}/blob/main/journey/stages/"
        f"{card.number:02d}-{card.slug}/stage.patch"
    )
    prelude, mechanism, checks = split_lesson(body, chinese=chinese)
    walkthrough = render_file_walkthrough(card, chinese=chinese)
    return (
        f"# Stage {card.number:02d} · {title}\n\n"
        f"{prelude}\n\n"
        f"{mechanism}\n\n"
        f"{walkthrough}\n\n"
        f"{checks}\n\n"
        f"[{link_label}]({compare_link(card.number)})\n\n"
        f"{checkout}\n\n"
        f"[Complete reference patch / 完整参考补丁]({patch_link})\n"
    )


def render_index(cards: list[Card], *, chinese: bool) -> str:
    if chinese:
        lines = [
            "# MiniS3 Journey",
            "",
            "每个 Stage 都是一节可独立浏览的完整课：先理解 S3 问题与机制，再按运行时职责逐文件阅读 Diff，最后用测试、自查题与面试表达完成闭环。",
            "",
            "如果希望在编辑器里聚焦当前增量，运行 `python journey/tools/build_journey.py study N`，再打开 `../MiniS3-journey-workspace`。Agent 导师可以增强互动，但不是完成课程的前提。",
            "",
            "| Stage | 主题 | 新增测试 | 教材章节 |",
            "|---:|---|---:|---:|",
        ]
    else:
        lines = [
            "# MiniS3 Journey",
            "",
            "Each Stage is a complete independent-browser lesson: understand the S3 problem and mechanism, read every changed file by runtime responsibility, then close with verification, checks, and interview language.",
            "",
            "For an editor-focused diff, run `python journey/tools/build_journey.py study N` and open `../MiniS3-journey-workspace`. An agent tutor adds interaction but is not required to complete the course.",
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
