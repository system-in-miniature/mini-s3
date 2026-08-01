# Agent 带教

当你希望在终端里由 Codex 互动带完一个 MiniS3 Stage 时使用此模式。命令会准备
干净的 Stage N-1 基线，在工作区安装 `AGENTS.md`，并把当前 Stage 的 agent-only
资料放到 `.journey/`。

## 1. 准备一个 Stage

在 MiniS3 仓库中运行：

```bash
python journey/tools/build_journey.py agent N
```

把 `N` 换成 1 到 15，例如：

```bash
python journey/tools/build_journey.py agent 3
```

默认学习仓库是 `../MiniS3-journey-workspace`。如果工作区已经存在，命令会先询问
是否覆盖；只有确定要替换当前 Stage 进度时才加 `--yes`。

## 2. 打开 CLI Agent

```bash
cd ../MiniS3-journey-workspace
codex
```

然后发送：

```text
开始 Stage NN
```

把 `NN` 换成准备命令打印的两位 Stage 编号，例如 `开始 Stage 03`。

## 3. 继续与验收

Agent 会读取 `AGENTS.md` 和 `.journey/stage.md`，先用低负担问答快速判断当前理解，
再分小段实现并带你走读实际代码。如果某个问题没有帮助，可以直接说“给我答案”或
“继续”。

结束时，Agent 会运行 `.journey/check-command.txt` 中的精确命令，同时检查累计测试
和 canonical Stage parity。

如果要指定其他工作区：

```bash
python journey/tools/build_journey.py agent 3 --workspace /absolute/path/to/workspace
```
