"""读取本地文件内容（支持文件和目录）"""

import os
from pathlib import Path
from core.file_safety import safe_read_check

TOOL_NAME = "read_local_file"

# 读取目录时每个文件最多显示的行数
DIR_PREVIEW_LINES = 30


def _read_single_file(filepath: str, max_chars: int = 40000,
                      offset: int = 0, limit: int | None = None) -> str:
    """读取单个文件内容

    Args:
        filepath: 文件路径
        max_chars: 最大返回字符数（默认 40000）
        offset: 从第几行开始读（0 表示开头）
        limit: 最多读几行（None 表示全部）
    """
    path = Path(filepath).expanduser()

    if not path.exists():
        return f"错误: 文件不存在: {filepath}"

    ext = path.suffix.lower()

    try:
        if ext == '.pdf':
            try:
                import pypdf
                reader = pypdf.PdfReader(str(path))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
                return f"{filepath}\n\n{text[:max_chars]}" + (f"\n... (共 {len(text)} 字符)" if len(text) > max_chars else "")
            except ImportError:
                return "错误: 请安装 pypdf: pip install pypdf"
        elif ext in ['.docx', '.doc']:
            try:
                import docx
                doc = docx.Document(str(path))
                text = "\n".join(p.text for p in doc.paragraphs)
                return f"{filepath}\n\n{text[:max_chars]}" + (f"\n... (共 {len(text)} 字符)" if len(text) > max_chars else "")
            except ImportError:
                return "错误: 请安装 python-docx: pip install python-docx"
        elif ext in ['.pptx', '.ppt']:
            try:
                from pptx import Presentation
                prs = Presentation(str(path))
                text_parts = []
                for slide in prs.slides:
                    for shape in slide.shapes:
                        if hasattr(shape, "text") and shape.text.strip():
                            text_parts.append(shape.text)
                text = "\n".join(text_parts)
                return f"{filepath}\n\n{text[:max_chars]}" + (f"\n... (共 {len(text)} 字符)" if len(text) > max_chars else "")
            except ImportError:
                return "错误: 请安装 python-pptx: pip install python-pptx"
        elif ext in ['.xlsx', '.xls']:
            try:
                import openpyxl
                wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
                text_parts = []
                for sheet_name in wb.sheetnames:
                    ws = wb[sheet_name]
                    rows = []
                    for row in ws.iter_rows(values_only=True):
                        row_text = " | ".join(str(c) for c in row if c is not None)
                        if row_text.strip():
                            rows.append(row_text)
                    if rows:
                        text_parts.append(f"[{sheet_name}]\n" + "\n".join(rows[:50]))
                        if len(rows) > 50:
                            text_parts.append(f"... (共 {len(rows)} 行)")
                wb.close()
                text = "\n\n".join(text_parts)
                return f"{filepath}\n\n{text[:max_chars]}" + (f"\n... (共 {len(text)} 字符)" if len(text) > max_chars else "")
            except ImportError:
                return "错误: 请安装 openpyxl: pip install openpyxl"
        elif ext in ['.md', '.txt', '.py', '.json', '.yaml', '.yml', '.html', '.css', '.js', '.sh']:
            content = path.read_text(encoding='utf-8')
        else:
            content = path.read_text(encoding='utf-8', errors='ignore')

        # ── 分页：offset + limit ──
        if offset > 0 or limit is not None:
            lines = content.split('\n')
            total_lines = len(lines)
            start = offset
            end = (start + limit) if limit is not None else total_lines
            selected = lines[start:end]
            content = '\n'.join(selected)
            if offset > 0 or limit is not None:
                header = f"[行 {start+1}-{min(end, total_lines)} / 共 {total_lines} 行]\n"
                content = header + content

        if len(content) > max_chars:
            content = content[:max_chars] + f"\n... (内容已截断，共 {len(content)} 字符)"

        return f"{filepath}\n\n{content}"
    except Exception as e:
        return f"错误: 读取失败: {str(e)}"


def _read_directory(dirpath: str) -> str:
    """读取目录结构，返回每个文件的摘要"""
    path = Path(dirpath).expanduser()

    if not path.exists():
        return f"错误: 目录不存在: {dirpath}"
    if not path.is_dir():
        return _read_single_file(dirpath)

    result = []
    result.append(f"目录: {dirpath}")
    result.append("")

    # 收集所有文件
    files = []
    for f in sorted(path.iterdir()):
        if f.name.startswith('.'):
            continue
        if f.is_file():
            size = f.stat().st_size
            files.append((f.name, size, f))

    result.append(f"共 {len(files)} 个文件")
    result.append("")

    for name, size, fpath in files:
        size_str = f"{size}B" if size < 1024 else f"{size/1024:.1f}KB"
        result.append(f"  {name} ({size_str})")

        # 读取前几行作为预览
        try:
            ext = fpath.suffix.lower()
            if ext in ['.md', '.txt', '.py', '.json', '.yaml', '.yml', '.html', '.css', '.js', '.sh']:
                lines = fpath.read_text(encoding='utf-8', errors='ignore').split('\n')
                preview_lines = lines[:DIR_PREVIEW_LINES]
                for line in preview_lines:
                    if line.strip():
                        result.append(f"    {line[:100]}")
                if len(lines) > DIR_PREVIEW_LINES:
                    result.append(f"    ... (共 {len(lines)} 行)")
        except Exception:
            pass
        result.append("")

    return '\n'.join(result)


def execute(filepath: str, max_chars: int = 40000,
            offset: int = 0, limit: int = None) -> str:
    """读取本地文件或目录内容

    Args:
        filepath: 文件或目录路径
        max_chars: 最大返回字符数（默认 40000）
        offset: 从第几行开始读（默认 0 = 开头）。用于大文件分页读取
        limit: 最多读取的行数（默认 None = 全部）。配合 offset 实现分页
    """
    path = Path(filepath).expanduser()

    if not path.exists():
        return f"错误: 路径不存在: {filepath}"

    # 安全: 二进制文件检测
    if path.is_file():
        warning = safe_read_check(str(path))
        if warning:
            return warning

    if path.is_dir():
        return _read_directory(filepath)
    else:
        return _read_single_file(filepath, max_chars, offset, limit)


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "读取本地文件或目录内容（默认上限 40000 字符）。支持 .md, .txt, .py, .pdf, .docx 等。大文件可用 offset+limit 分页读取，防止撑爆上下文。目录返回结构预览。",
        "parameters": {"type": "object", "properties": {
            "filepath": {"type": "string", "description": "要读取的文件绝对路径"},
            "max_chars": {"type": "integer", "description": "最大返回字符数，超出的内容截断"},
            "offset": {"type": "integer", "description": "从第几行开始读（0=开头），大文件分页用"},
            "limit": {"type": "integer", "description": "最多读取行数，配合 offset 分页"}
        }, "required": ["filepath"]}
    }
}
def register(reg): reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
