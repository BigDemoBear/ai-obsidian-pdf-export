---
name: obsidian-note-pdf
description: "将 Obsidian Markdown 笔记导出为 A4 PDF，保留 ![[图片]]、==高亮==、[[双链]]、LaTeX 公式、表格、中文加粗与斜体、PDF 书签。用户要求把 Obsidian 笔记或含 Obsidian 语法的 Markdown 转为 PDF 时使用；不要直接用裸 Pandoc 导出。"
license: "MIT; see LICENSE and THIRD_PARTY_NOTICES.md"
metadata:
  version: "1.0.1"
---

# Obsidian 笔记导出 PDF

把一个 Obsidian 笔记转成可交付的 A4 PDF。核心是单命令脚本，不需要手工复制图片、改 LaTeX 或分步运行 Pandoc。

## 何时使用

- 用户要求把 `.md` 笔记导出为 PDF，且笔记含 `![[...]]`、`==...==`、`[[...]]`、YAML 头、LaTeX 公式或宽表。
- 用户抱怨 PDF 中图片丢失、高亮变成 `==`、双链变成方括号、中文粗体/斜体不明显。
- 不用于 Office 文档转换；`.docx/.pptx/.xlsx` 走 Office 技能。

## 转换方式

脚本先处理 Obsidian 图片嵌入、高亮和双链，再调用 Pandoc 与 LuaLaTeX 排版；宋体通过合成粗体与斜体显示中文强调。

## 快速使用

在技能根目录运行，将源文件和笔记库路径替换为实际路径：

```powershell
python scripts/obsidian_to_pdf.py "D:\path\note.md" `
  --vault "D:\path\vault" `
  --profile "examples/note-profile.json" `
  --force
```

默认输出到源文件同目录、同名 `.pdf`。常用参数：

| 参数 | 用途 |
| --- | --- |
| `--vault` | Obsidian 库根目录；省略时向上查找 `.obsidian` |
| `--profile` | 标题、页眉和个别格式修复的 JSON |
| `-o/--output` | 指定输出 PDF |
| `--title/--subtitle/--byline/--note` | 直接覆盖封面文字 |
| `--header-left/--header-right` | 覆盖页眉 |
| `--build-dir` | 指定并保留构建目录 |
| `--keep` | 保留临时构建目录 |
| `--force` | 覆盖已有 PDF |
| `--no-table-widths` | 关闭按内容重分配表格列宽 |

首次使用先检查依赖：

```powershell
Get-Command pandoc, lualatex, pdfinfo, pdfimages, pdftotext, pdftoppm, pdffonts
```

## 处理流程

1. **解析笔记**：读取 YAML 标题/作者；若没有，使用首个 H1 或文件名。
2. **处理 Obsidian 语法**：
   - `![[image.png|286]]`：在库中查找附件，复制到构建目录，生成等宽图片块；支持 `|数字`、`|数字px`、`|百分比`。
   - 顶部连续的双链：合并成“关联笔记”一行，链接到本机 Obsidian。
   - 正文双链：转为可点击的 `obsidian://open?path=...` 链接。
   - `==...==`：由 Lua 过滤器转成黄/红/蓝跨行高亮。
   - 非图片嵌入、Mermaid、callout：按链接、代码块、普通引用处理并给出警告。
3. **修复 Markdown 结构**：在标题、引用块、列表续段前补空行；中文 `\mathrm{}` 与 `\tag{}` 改用 `\text{}`。
4. **表格**：按内容长度重分配列宽，表头加粗，表格字号缩小，避免宽表溢出。
5. **排版**：Pandoc → `ctexart` LaTeX；LuaLaTeX 编译两遍；宋体合成粗体/斜体；A4、页眉页脚、PDF 书签和元数据。
6. **验收**：用 `pdfinfo`、`pdfimages`、`pdftotext` 和页面渲染抽查。

## 配置文件

没有配置也能用。需要精确控制封面或修复少数“高亮/加粗交叉”的错误标记时，提供 JSON：

```json
{
  "title": "工程学习笔记",
  "subtitle": "方法与示例",
  "byline": "个人笔记",
  "note": "示例配置，请按实际笔记修改",
  "header_left": "工程学习笔记",
  "header_right": "方法与示例",
  "author": "笔记作者",
  "subject": "学习笔记",
  "keywords": "Obsidian, Markdown, PDF",
  "repairs": []
}
```

`repairs` 只用于格式修复，必须逐项写明原文与替换文本，不能用来改写技术内容。修复未命中会在 stderr 报警。

## 验收清单

```powershell
pdfinfo "note.pdf"
pdfimages -list "note.pdf"
pdftotext -layout "note.pdf" "note.txt"
pdftoppm -f 1 -l 1 -singlefile -png -r 120 "note.pdf" "page1"
```

- `Pages` 合理，`Page size` 为 A4。
- `pdfimages` 的图片数与笔记附件数一致。
- 文本中不再出现 `![[`、`[[` 或成对的 `==`。
- 抽查含图页、宽表页、末页；确认中文 **加粗**、*斜体*、高亮和公式可见。
- `pdffonts` 显示字体已嵌入。

## 已知边界

- Mermaid 不渲染，保留为代码块并警告。
- Obsidian callout 当前按普通引用块处理。
- `![[另一篇笔记]]` 按可点击链接处理，不展开嵌入内容。
- 非 PNG/JPEG 图片需要 Pillow 转成 PNG。
- 公式必须能被 Pandoc/LaTeX 解析；复杂 TikZ、Dataview、Canvas 不在范围内。

## 排版与源文件

使用本技能脚本处理 Obsidian 语法；正文保持宋体，中文强调使用合成粗斜体。分页调整保持图像可读、内容完整。格式修复写入 profile 或构建文件，源笔记保持原样。

## 环境与公开分享

安装位置、系统工具和字体要求见 [README.md](README.md)。运行环境应提供排版文件指定的字体。

PDF 内的 `obsidian://open?path=...` 链接使用本机绝对路径。对外分享时检查链接、作者和页眉；构建目录用于保存转换过程中的正文与附件。
