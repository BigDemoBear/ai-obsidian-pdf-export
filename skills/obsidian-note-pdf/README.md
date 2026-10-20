# 让 AI 导出 Obsidian 笔记为 PDF

把笔记和目标要求交给 AI，由 AI 调用转换脚本并检查 PDF 的图片、高亮、公式、表格和中文粗斜体。AI 执行入口是 [SKILL.md](SKILL.md)。这是一个 AI 技能，也可手动调用脚本。

## 交给 AI 使用

将完整的 `obsidian-note-pdf` 目录安装到宿主的技能目录，重新打开会话后确认技能可见。

> 使用 $obsidian-note-pdf，把我指定的 Obsidian 笔记导出成 A4 PDF，保留图片、高亮、双链、公式和表格。不要修改原笔记，检查导出后的页面，并说明未完成项。

AI 宿主需要具备文件访问、本地命令执行和 PDF 页面查看能力。

## 运行环境

- 建议 Python 3.10 或更新版本。主要转换逻辑使用标准库；非 PNG/JPEG 图片转换另需 Pillow，可用 `python -m pip install -r requirements.txt` 安装。
- 转换必需 Pandoc 和 LuaLaTeX。Pandoc 必须支持 `markdown+mark`；TeX 环境需有 `ctexart`、`fontspec`、`geometry`、`graphicx`、`longtable`、`fancyhdr`、`titlesec`、`luacolor`、`lua-ul`、`enumitem`、`needspace`、`etoolbox` 及 Pandoc 生成 LaTeX 所需的包。TeX Live 是可选的安装发行版之一。
- PDF 检查使用 Poppler 的 `pdfinfo`、`pdfimages`、`pdftotext`、`pdftoppm`、`pdffonts`。
- 当前排版文件直接指定 Times New Roman、Microsoft YaHei、Consolas、SimSun、SimHei；运行环境须安装这些字体并能被 LuaLaTeX 识别。

## 手动使用

在本技能目录运行，换成实际源文件和笔记库路径；配置可省略：

```powershell
python scripts/obsidian_to_pdf.py "D:\path\note.md" --vault "D:\path\vault" --profile "examples/note-profile.json"
```

默认输出源文件同目录的同名 PDF；已有文件默认拒绝覆盖，确认需要后加 `--force`。其余参数和检查清单见 [SKILL.md](SKILL.md)。

## 输出说明

- Mermaid 保留代码，不渲染为图；callout 按普通引用处理，嵌入其他笔记不展开。
- 双链生成的 Obsidian 链接使用本机绝对路径。对外分享时检查链接、作者、页眉和 PDF 元数据；构建目录包含转换过程中的正文与附件。
- 转换后查看图片、表格、公式及末页，确认排版完整。

## 许可

本技能采用 [MIT](LICENSE)，依赖与许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
