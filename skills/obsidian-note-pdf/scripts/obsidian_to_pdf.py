#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert an Obsidian Markdown note to an A4 PDF with Pandoc + LuaLaTeX."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
SKIP_DIRS = {".git", ".obsidian", ".trash", "node_modules", "__pycache__"}
WIKI_LINK_RE = re.compile(r"(?<!!)\[\[([^\]\n]+)\]\]")
IMAGE_RE = re.compile(r"!\[\[([^\]\n]+)\]\]")
SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")


class ConversionError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="把 Obsidian Markdown 笔记转换为 A4 PDF（图片、高亮、双链、公式、书签）。"
    )
    p.add_argument("source", help="Markdown 源文件")
    p.add_argument("-o", "--output", help="输出 PDF；默认与源文件同目录、同名")
    p.add_argument("--vault", help="Obsidian 库根目录；默认向上查找 .obsidian")
    p.add_argument("--profile", help="可选 JSON 配置，用于标题、页眉和个别格式修复")
    p.add_argument("--title")
    p.add_argument("--subtitle")
    p.add_argument("--byline")
    p.add_argument("--note")
    p.add_argument("--header-left")
    p.add_argument("--header-right")
    p.add_argument("--build-dir", help="指定构建目录（保留中间文件）")
    p.add_argument("--keep", action="store_true", help="保留临时构建目录")
    p.add_argument("--force", action="store_true", help="覆盖已存在的输出 PDF")
    p.add_argument("--no-table-widths", action="store_true", help="不按内容重分配表格列宽")
    p.add_argument("--max-image-width-cm", type=float, default=16.1)
    return p.parse_args()


def load_profile(path: str | None) -> dict:
    if not path:
        return {}
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise ConversionError(f"配置文件不存在：{p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConversionError(f"配置文件 JSON 格式错误：{exc}") from exc
    if not isinstance(data, dict):
        raise ConversionError("配置文件顶层必须是 JSON 对象")
    return data


def find_vault(source: Path, explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.is_dir():
            raise ConversionError(f"Obsidian 库目录不存在：{root}")
        return root
    for parent in [source.parent, *source.parent.parents]:
        if (parent / ".obsidian").is_dir():
            return parent
    return source.parent


def build_asset_index(vault: Path) -> tuple[dict[str, list[Path]], dict[str, list[Path]]]:
    images: dict[str, list[Path]] = {}
    notes: dict[str, list[Path]] = {}
    for dirpath, dirnames, filenames in os.walk(vault):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            ext = p.suffix.lower()
            if ext in IMAGE_EXTS:
                images.setdefault(name, []).append(p)
            elif ext == ".md":
                notes.setdefault(name, []).append(p)
    return images, notes


def resolve_image(name: str, source: Path, vault: Path, index: dict[str, list[Path]]) -> Path:
    raw = Path(name).expanduser()
    candidates = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.extend([source.parent / raw, vault / raw])
    for p in candidates:
        if p.is_file():
            return p.resolve()
    hits = index.get(raw.name, [])
    if hits:
        return hits[0].resolve()
    raise ConversionError(f"找不到图片附件：{name}")


def obsidian_uri(path: Path) -> str:
    return "obsidian://open?path=" + urllib.parse.quote(path.resolve().as_posix(), safe="")


def resolve_note(target: str, source: Path, vault: Path, index: dict[str, list[Path]]) -> Path | None:
    target = target.split("#", 1)[0].strip()
    if not target:
        return None
    name = target if target.lower().endswith(".md") else target + ".md"
    raw = Path(name).expanduser()
    candidates = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.extend([source.parent / raw, vault / raw])
    for p in candidates:
        if p.is_file():
            return p.resolve()
    hits = index.get(raw.name, [])
    return hits[0].resolve() if hits else None


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if not line or line[0].isspace() or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip().strip("\"'")
        if value:
            meta[key.strip().lower()] = value
    return meta, text[m.end():]


def tidy_blank_lines(text: str) -> str:
    lines = text.split("\n")

    # Headings must be separated from the preceding paragraph.
    out: list[str] = []
    for line in lines:
        if re.match(r"^#{1,6} ", line) and out and out[-1].strip():
            out.append("")
        out.append(line)
    lines = out

    # Blockquotes and list continuations likewise need a separating blank line.
    out = []
    for line in lines:
        if (line.lstrip().startswith(">")
                and out and out[-1].strip()
                and not out[-1].lstrip().startswith(">")):
            out.append("")
        out.append(line)
    lines = out

    out = []
    for line in lines:
        if (line[:1].isspace() and line.strip()
                and out and re.match(r"^\s*(?:[-*+]|\d+\.)\s+", out[-1])):
            out.append("")
        out.append(line)
    return "\n".join(out)


def split_cells(row: str) -> list[str]:
    s = row.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells, buf, escaped = [], [], False
    for ch in s:
        if ch == "|" and not escaped:
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        escaped = (ch == "\\" and not escaped)
    cells.append("".join(buf).strip())
    return cells


def display_weight(s: str) -> int:
    s = re.sub(r"\\[A-Za-z]+", "x", s)
    s = re.sub(r"[${}\\^_]", "", s)
    return sum(2 if ord(ch) > 127 else 1 for ch in s)


def rebalance_table(block: list[str]) -> tuple[list[str], list[float]]:
    if len(block) < 2 or not SEP_RE.match(block[1]):
        return block, []
    header, sep = split_cells(block[0]), split_cells(block[1])
    if len(header) != len(sep):
        return block, []
    rows = [split_cells(r) for r in block[2:]]
    if any(len(r) != len(sep) for r in rows):
        return block, []

    maxlen = []
    for col in range(len(sep)):
        vals = [header[col]] + [r[col] for r in rows]
        maxlen.append(max(display_weight(v) for v in vals))
    raw = [(m + 7) ** 0.82 for m in maxlen]
    props = [min(max(r / sum(raw), 0.12), 0.60) for r in raw]
    total = sum(props)
    props = [p / total for p in props]

    new_header = []
    for cell in header:
        cell = cell.strip()
        if cell and not (cell.startswith("**") and cell.endswith("**")):
            cell = f"**{cell}**"
        new_header.append(cell)

    new_sep = []
    for spec, p in zip(sep, props):
        left, right = spec.startswith(":"), spec.endswith(":")
        n = max(3, round(p * 76))
        new_sep.append((":" if left else "") + "-" * n + (":" if right else ""))
    return [
        "| " + " | ".join(new_header) + " |",
        "| " + " | ".join(new_sep) + " |",
        *block[2:],
    ], props


def rebalance_tables(text: str, enabled: bool) -> tuple[str, list[str]]:
    if not enabled:
        return text, []
    lines = text.split("\n")
    widths: list[str] = []
    i = 0
    while i < len(lines):
        if (lines[i].lstrip().startswith("|")
                and i + 1 < len(lines) and SEP_RE.match(lines[i + 1])):
            j = i + 2
            while j < len(lines) and lines[j].strip() and "|" in lines[j]:
                j += 1
            new_block, props = rebalance_table(lines[i:j])
            if props:
                widths.append(f"line {i + 1}: " + ", ".join(f"{p:.2f}" for p in props))
                lines[i:j] = new_block
            i = j
        else:
            i += 1
    return "\n".join(lines), widths


def tex_escape(s: str) -> str:
    repl = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(repl.get(ch, ch) for ch in s)


def write_meta(path: Path, values: dict[str, str]) -> None:
    lines = [
        r"\def\DocTitle{" + tex_escape(values["title"]) + "}",
        r"\def\DocSubtitle{" + tex_escape(values["subtitle"]) + "}",
        r"\def\DocByline{" + tex_escape(values["byline"]) + "}",
        r"\def\DocNote{" + tex_escape(values["note"]) + "}",
        r"\def\DocHeaderLeft{" + tex_escape(values["header_left"]) + "}",
        r"\def\DocHeaderRight{" + tex_escape(values["header_right"]) + "}",
        r"\def\DocAuthor{" + tex_escape(values["author"]) + "}",
        r"\def\DocSubject{" + tex_escape(values["subject"]) + "}",
        r"\def\DocKeywords{" + tex_escape(values["keywords"]) + "}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def title_block(values: dict[str, str]) -> str:
    body = [
        r"\thispagestyle{plain}",
        r"\begin{center}",
        r"{\sffamily\bfseries\fontsize{24}{30}\selectfont \DocTitle}\\[7pt]",
    ]
    if values["subtitle"]:
        body.append(r"{\sffamily\large \DocSubtitle}\\[10pt]")
    if values["byline"]:
        body.append(r"{\small \DocByline}\\[2pt]")
    if values["note"]:
        body.append(r"{\small \DocNote}")
    body += [
        r"\end{center}",
        r"\vspace{0.7em}",
        r"\noindent{\color{rulegray}\rule{\linewidth}{0.55pt}}",
        r"\vspace{0.8em}",
    ]
    return "\n\n```{=latex}\n" + "\n".join(body) + "\n```\n\n"


def convert_wiki_text(raw: str, source: Path, vault: Path, notes: dict[str, list[Path]],
                       warnings: list[str]) -> str:
    target, _, alias = raw.partition("|")
    target = target.strip()
    display = alias.strip() if alias.strip() else target.split("#", 1)[0].removesuffix(".md")
    p = resolve_note(target, source, vault, notes)
    if p:
        return f"[{display}]({obsidian_uri(p)})"
    warnings.append(f"双链目标未找到，按纯文本保留：[[{raw}]]")
    return display


def image_block(parts: list[str], image_no: int, suffix: str, width_cm: float) -> str:
    width = r"\linewidth"
    if len(parts) > 1:
        spec = parts[-1].strip()
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:px)?", spec)
        if m:
            width = f"width={min(float(m.group(1)) * 2.54 / 96.0, width_cm):.2f}cm"
        elif re.fullmatch(r"\d+(?:\.\d+)?%", spec):
            width = f"width={float(spec[:-1]) / 100:.3f}\\linewidth"
    if width == r"\linewidth":
        width = r"width=\linewidth"
    return (
        "\n\n```{=latex}\n"
        "\\begin{center}\n"
        f"\\includegraphics[{width},height=0.70\\textheight,keepaspectratio]"
        f"{{figures/fig-{image_no:02d}{suffix}}}\n"
        "\\end{center}\n"
        "```\n\n"
    )


def preprocess(
    text: str,
    source: Path,
    vault: Path,
    images: dict[str, list[Path]],
    notes: dict[str, list[Path]],
    profile: dict,
    build: Path,
    max_width_cm: float,
) -> tuple[str, list[str], list[str], dict[str, str], str | None]:
    warnings: list[str] = []
    repairs = profile.get("repairs", [])
    for item in repairs:
        if isinstance(item, dict):
            old, new = item.get("old", ""), item.get("new", "")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            old, new = item
        else:
            warnings.append(f"忽略无法识别的 repairs 项：{item!r}")
            continue
        if not old:
            continue
        count = text.count(old)
        if count == 0:
            warnings.append(f"配置中的格式修复未命中：{old[:60]!r}")
            continue
        text = text.replace(old, new)

    meta, text = parse_frontmatter(text)
    text = re.sub(r"\n?<!--\s*DOCUMENT_COMPLETE\s*-->\s*$", "\n", text)
    text = re.sub(
        r"\\mathrm\{([^{}]*[\u3400-\u9fff][^{}]*)\}",
        lambda m: r"\text{" + m.group(1) + "}",
        text,
    )
    text = re.sub(
        r"\\tag\{([^{}]*[\u3400-\u9fff][^{}]*)\}",
        lambda m: r"\tag{\text{" + m.group(1) + "}}",
        text,
    )

    first_h1 = re.search(r"^#\s+(.+)$", text, re.M)
    inferred_title = re.sub(r"[*_`]", "", first_h1.group(1)).strip() if first_h1 else source.stem
    title = str(profile.get("title") or meta.get("title") or inferred_title)
    if first_h1 and title == re.sub(r"[*_`]", "", first_h1.group(1)).strip():
        text = re.sub(r"^#\s+.*\n?", "", text, count=1, flags=re.M)

    values = {
        "title": title,
        "subtitle": str(profile.get("subtitle") or meta.get("subtitle") or ""),
        "byline": str(profile.get("byline") or meta.get("author") or ""),
        "note": str(profile.get("note") or ""),
        "header_left": str(profile.get("header_left") or title),
        "header_right": str(profile.get("header_right") or ""),
        "author": str(profile.get("author") or meta.get("author") or "个人笔记"),
        "subject": str(profile.get("subject") or title),
        "keywords": str(profile.get("keywords") or "Obsidian, Markdown, 笔记"),
    }

    # Leading lines that contain only wiki links become a related-notes note.
    lines = text.split("\n")
    lead_links, i = [], 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    while i < len(lines):
        m = re.fullmatch(r"\s*\[\[([^\]\n]+)\]\]\s*", lines[i])
        if not m:
            break
        lead_links.append(m.group(1))
        i += 1
    related = None
    if lead_links:
        rendered = [convert_wiki_text(x, source, vault, notes, warnings) for x in lead_links]
        related = "> **关联笔记**　" + "　·　".join(rendered)
        lines = lines[i:]

    # Images are copied into the build directory so LaTeX never sees spaces or
    # non-ASCII paths.  Non-image ![[...]] embeds become ordinary links.
    build_fig = build / "figures"
    build_fig.mkdir(parents=True, exist_ok=True)
    counters = {"n": 0}

    def export_image(src: Path, stem: Path) -> str:
        ext = src.suffix.lower()
        if ext in {".png", ".jpg", ".jpeg"}:
            shutil.copy2(src, stem.with_suffix(ext))
            return ext
        try:
            from PIL import Image
        except ImportError as exc:
            raise ConversionError(
                f"{src.name} 不是 PNG/JPEG，且未安装 Pillow，无法转换。"
            ) from exc
        dst = stem.with_suffix(".png")
        with Image.open(src) as im:
            if im.mode in ("RGBA", "LA") or "transparency" in im.info:
                im.convert("RGBA").save(dst, "PNG")
            else:
                im.convert("RGB").save(dst, "PNG")
        return ".png"

    def image_repl(match: re.Match[str]) -> str:
        parts = match.group(1).split("|")
        name = parts[0].strip()
        if Path(name).suffix.lower() not in IMAGE_EXTS:
            return convert_wiki_text("|".join(parts), source, vault, notes, warnings)
        p = resolve_image(name, source, vault, images)
        counters["n"] += 1
        n = counters["n"]
        suffix = export_image(p, build_fig / f"fig-{n:02d}")
        return image_block(parts, n, suffix, max_width_cm)

    text = "\n".join(lines)
    text = IMAGE_RE.sub(image_repl, text)
    text = WIKI_LINK_RE.sub(
        lambda m: convert_wiki_text(m.group(1), source, vault, notes, warnings), text
    )

    text = tidy_blank_lines(text)
    text, table_widths = rebalance_tables(text, not bool(profile.get("no_table_widths")))

    unbalanced = [
        i + 1 for i, line in enumerate(text.splitlines()) if line.count("==") % 2
    ]
    if unbalanced:
        warnings.append(
            "检测到未配对的高亮标记 `==`，行号：" + ", ".join(map(str, unbalanced[:8]))
        )

    if re.search(r"^```mermaid\b", text, re.M):
        warnings.append("检测到 Mermaid 图：当前版本不会渲染，PDF 中将保留为代码块。")
    if re.search(r"^>\s*\[!", text, re.M):
        warnings.append("检测到 Obsidian callout：当前按普通引用块排版。")

    text = text.strip() + "\n"
    body = title_block(values) + (related + "\n\n" if related else "") + text
    return body, warnings, table_widths, values, related


def shift_heading_level(text: str) -> int:
    levels = [len(m.group(1)) for m in re.finditer(r"^(#{1,6})\s+", text, re.M)]
    if not levels:
        return 0
    return 1 - min(levels)


def run(cmd: list[str], cwd: Path, log: Path) -> None:
    proc = subprocess.run(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    log.write_text(proc.stdout or "", encoding="utf-8")
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout or "").splitlines()[-35:])
        raise ConversionError(f"命令失败（退出码 {proc.returncode}）：{' '.join(cmd)}\n{tail}")


def pdf_summary(pdf: Path) -> str:
    lines = [f"输出：{pdf}", f"大小：{pdf.stat().st_size / 1024 / 1024:.2f} MB"]
    if shutil.which("pdfinfo"):
        try:
            out = subprocess.check_output(
                ["pdfinfo", str(pdf)], text=True, encoding="utf-8", errors="replace"
            )
            pages = re.search(r"^Pages:\s+(\d+)", out, re.M)
            size = re.search(r"^Page size:\s+(.+)$", out, re.M)
            if pages:
                lines.append(f"页数：{pages.group(1)}")
            if size:
                lines.append(f"页面：{size.group(1).strip()}")
        except Exception:
            pass
    if shutil.which("pdfimages"):
        try:
            out = subprocess.check_output(
                ["pdfimages", "-list", str(pdf)], text=True, encoding="utf-8", errors="replace"
            )
            lines.append(f"图片：{sum(1 for x in out.splitlines() if re.match(r'^\s*\d+', x))} 张")
        except Exception:
            pass
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    source = Path(args.source).expanduser().resolve()
    if not source.is_file():
        print(f"源文件不存在：{source}", file=sys.stderr)
        return 2
    profile = load_profile(args.profile)
    for key in ("title", "subtitle", "byline", "note", "header_left", "header_right"):
        value = getattr(args, key)
        if value is not None:
            profile[key] = value
    if args.no_table_widths:
        profile["no_table_widths"] = True

    vault = find_vault(source, args.vault)
    images, notes = build_asset_index(vault)

    build = Path(args.build_dir).resolve() if args.build_dir else Path(
        tempfile.mkdtemp(prefix="obsidian-pdf-")
    )
    build.mkdir(parents=True, exist_ok=True)
    keep = args.keep or bool(args.build_dir)
    try:
        raw = source.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        body, warnings, widths, values, _ = preprocess(
            raw, source, vault, images, notes, profile, build, args.max_image_width_cm
        )
        (build / "note.md").write_text(body, encoding="utf-8")
        write_meta(build / "meta.tex", values)

        assets = Path(__file__).resolve().parent.parent / "assets"
        shift = shift_heading_level(body)
        pandoc = shutil.which("pandoc")
        lualatex = shutil.which("lualatex")
        if not pandoc:
            raise ConversionError("未找到 pandoc")
        if not lualatex:
            raise ConversionError("未找到 lualatex（需要 TeX Live）")

        cmd = [
            pandoc, "note.md", "-f", "markdown+mark", "-t", "latex", "-s",
            "--lua-filter", str(assets / "mark.lua"),
            "--include-in-header", str(assets / "header.tex"),
            "--include-in-header", "meta.tex",
            "-V", "documentclass=ctexart",
            "-V", "classoption=UTF8",
            "-V", "classoption=fontset=none",
            "-V", "fontsize=12pt",
            "--shift-heading-level-by", str(shift),
            "-o", "note.tex",
        ]
        run(cmd, build, build / "pandoc.log")

        tex_path = build / "note.tex"
        tex = tex_path.read_text(encoding="utf-8")
        if "hidelinks," in tex:
            tex = tex.replace(
                "hidelinks,",
                "colorlinks=true,\n  linkcolor=sectionblue,\n"
                "  urlcolor=linkblue,\n  citecolor=sectionblue,",
            )
            tex_path.write_text(tex, encoding="utf-8")
        else:
            warnings.append("未找到 Pandoc 的 hidelinks 标记，PDF 链接可能为黑色。")

        for n in (1, 2):
            run(
                [lualatex, "-interaction=nonstopmode", "-halt-on-error", "note.tex"],
                build, build / f"lualatex-{n}.log",
            )

        out = Path(args.output).expanduser().resolve() if args.output else source.with_suffix(".pdf")
        if out.exists() and not args.force:
            raise ConversionError(f"输出已存在（加 --force 覆盖）：{out}")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(build / "note.pdf", out)

        print(pdf_summary(out))
        print(f"图片：{len(list((build / 'figures').glob('*')))} 个附件已嵌入")
        if warnings:
            print("\n注意：", file=sys.stderr)
            for w in warnings:
                print(f"- {w}", file=sys.stderr)
        if keep:
            print(f"构建目录：{build}")
        return 0
    except ConversionError as exc:
        print(f"转换失败：{exc}", file=sys.stderr)
        if keep:
            print(f"构建目录：{build}", file=sys.stderr)
        return 1
    finally:
        if not keep:
            shutil.rmtree(build, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
