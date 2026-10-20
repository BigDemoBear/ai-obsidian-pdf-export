# 让 AI 导出 Obsidian 笔记为 PDF

AI Obsidian PDF Export：把笔记交给 AI，由 AI 完成转换、查看输出并说明问题。保留图片、双链、跨行高亮、LaTeX 公式、表格、中文粗斜体与 PDF 书签。

安装技能后，在对话中指定笔记路径和导出要求，由 AI 调用转换脚本并检查页面。

## 如何交给 AI

将 `skills/obsidian-note-pdf/` 完整目录安装到当前 AI 宿主的技能目录，重新打开会话后确认技能可见。

> 使用 $obsidian-note-pdf，把我指定的 Obsidian 笔记导出成 A4 PDF，保留图片、高亮、公式和表格，不修改原笔记。检查 PDF 的图片、宽表和公式所在页，说明未完成项。

AI 宿主需要具备文件访问、本地命令执行和 PDF 页面查看能力。

## 环境与使用说明

完整安装条件、字体要求、手动命令和限制见 [技能 README](skills/obsidian-note-pdf/README.md)，AI 执行流程见 [SKILL.md](skills/obsidian-note-pdf/SKILL.md)。

转换需要 Python、Pandoc 和 LuaLaTeX，PDF 检查使用 Poppler，非 PNG/JPEG 图片转换可选 Pillow。排版使用 Windows 常见字体，具体名称见技能 README。

通用配置示例见 [note-profile.json](skills/obsidian-note-pdf/examples/note-profile.json)。不需要配置时可省略 `--profile`。Mermaid 按代码块输出，其他笔记嵌入转为链接，callout 按普通引用排版。

## 公开分享前

Obsidian 双链使用本机路径，适合在原笔记库所在电脑中打开。对外分享 PDF 时检查链接、作者与页眉；构建目录用于保存转换过程中的正文和附件。

## 许可

本项目采用 [MIT](LICENSE)，外部依赖与许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

检索关键词：AI agent skill, Codex skill, Obsidian to PDF, Markdown PDF, Pandoc, LuaLaTeX, Chinese typography；AI 导出、Obsidian 笔记、中文 PDF、高亮、公式。
