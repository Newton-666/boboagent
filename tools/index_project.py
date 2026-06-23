"""Codebase indexer — scan project structure and store in memory.

After indexing, LLM can locate functions/classes instantly without grep_code.
"""

import os
import re
from pathlib import Path
from typing import Optional

TOOL_NAME = "index_project"

# Directories to skip
SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    "dist", "build", ".next", "coverage", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "projects",
}

# File extensions to index
INDEX_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".go", ".rs", ".sh",
    ".c", ".h", ".cpp", ".hpp", ".java",
    ".rb", ".swift", ".kt",
}

# ── Helpers ──

def _extract_summary(content: str, lang: str) -> str:
    """Extract module-level docstring or first comment block as summary."""
    lines = content.split("\n")
    # Skip shebang and encoding
    start = 0
    for i, line in enumerate(lines[:5]):
        stripped = line.strip()
        if stripped.startswith("#!") or stripped.startswith("# -*-"):
            start = i + 1
            continue
        break
    # Python docstring
    if lang == "py":
        for line in lines[start:start + 20]:
            stripped = line.strip()
            m = re.match(r'^["\']{3}(.*)', stripped)
            if m:
                desc = m.group(1).strip()
                return desc[:120] if desc else ""
        return ""
    # JS/TS /** */ or // comments at top
    if lang in ("js", "ts"):
        desc_lines = []
        in_block = False
        for line in lines[start:start + 15]:
            s = line.strip()
            if s.startswith("/**"):
                in_block = True
                desc_lines.append(s.strip("/*").strip())
            elif in_block and "*/" in s:
                desc_lines.append(s.replace("*/", "").strip())
                break
            elif in_block:
                desc_lines.append(s.strip("*").strip())
            elif s.startswith("//"):
                desc_lines.append(s[2:].strip())
        return " ".join(desc_lines)[:120] if desc_lines else ""
    # C/C++ /** */ or // at top
    if lang in ("c", "cpp", "h"):
        desc_lines = []
        in_block = False
        for line in lines[start:start + 15]:
            s = line.strip()
            if s.startswith("/**") or s.startswith("/*"):
                in_block = True
                desc_lines.append(s.strip("/*").strip())
            elif in_block and "*/" in s:
                desc_lines.append(s.replace("*/", "").strip())
                break
            elif in_block:
                desc_lines.append(s.strip("*").strip())
            elif s.startswith("//") and not desc_lines:
                desc_lines.append(s[2:].strip())
            elif desc_lines and not s.startswith("//"):
                break
        return " ".join(desc_lines)[:120] if desc_lines else ""
    # # comments at top (Go, Ruby, Shell)
    desc_lines = []
    for line in lines[start:start + 10]:
        s = line.strip()
        if s.startswith("#") and not s.startswith("#!"):
            desc_lines.append(s[1:].strip())
        elif desc_lines and not s.startswith("#"):
            break
    return " ".join(desc_lines)[:120] if desc_lines else ""


def _extract_imports(content: str, ext: str) -> list[str]:
    """Extract import/require/include statements from a file."""
    imports = []
    for line in content.split("\n"):
        s = line.strip()
        # Python
        if ext == ".py":
            m = re.match(r"^(?:from\s+(\S+)\s+)?import\s+(\S+)", s)
            if m:
                module = m.group(1) or m.group(2)
                imports.append(module)
        # JS/TS
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            m = re.match(r"^(?:import|require)\s.*?['\"](.+?)['\"]", s)
            if m:
                imports.append(m.group(1))
        # Go
        elif ext == ".go":
            m = re.match(r'^import\s+["\'](.+?)["\']', s)
            if m:
                imports.append(m.group(1))
        # C/C++
        elif ext in (".c", ".h", ".cpp", ".hpp"):
            m = re.match(r'^#include\s+[<"](.+?)[>"]', s)
            if m:
                imports.append(m.group(1))
        # Java
        elif ext == ".java":
            m = re.match(r"^import\s+([\w.]+)", s)
            if m:
                imports.append(m.group(1))
        # Rust
        elif ext == ".rs":
            m = re.match(r"^(?:use|extern crate)\s+([\w:]+)", s)
            if m:
                imports.append(m.group(1))
    return imports[:20]  # max 20 imports per file


# ── Extractors ──────────────────────────────────────────────────────────

def _extract_python(content: str) -> list[str]:
    """Extract function and class signatures from Python."""
    items = []
    for line in content.split("\n"):
        line = line.strip()
        # Class definition
        m = re.match(r"^class\s+(\w+)\s*(\(.*\))?\s*:", line)
        if m:
            bases = m.group(2) or ""
            items.append(f"class {m.group(1)}{bases}")
            continue
        # Function definition (including async)
        m = re.match(r"^(async\s+)?def\s+(\w+)\s*\((.*?)\)\s*(->.*)?\s*:", line)
        if m:
            name = m.group(2)
            params = m.group(3)[:80]
            async_prefix = "async " if m.group(1) else ""
            items.append(f"{async_prefix}def {name}({params})")
            continue
    return items


def _extract_javascript(content: str) -> list[str]:
    """Extract function/class signatures from JS/TS."""
    items = []
    for line in content.split("\n"):
        line = line.strip()
        # class
        if re.match(r"^(export\s+)?class\s+\w+", line):
            name = re.search(r"class\s+(\w+)", line).group(1)
            items.append(f"class {name}")
            continue
        # function
        m = re.match(r"^(export\s+)?(async\s+)?function\s+(\w+)\s*\((.*?)\)", line)
        if m:
            name = m.group(3)
            params = m.group(4)[:80] if m.group(4) else ""
            async_prefix = "async " if m.group(2) else ""
            items.append(f"{async_prefix}function {name}({params})")
            continue
        # arrow function assigned to const
        m = re.match(r"^(export\s+)?const\s+(\w+)\s*=\s*(async\s*)?\(.*\)\s*=>", line)
        if m:
            name = m.group(2)
            items.append(f"const {name} = (...) =>")
            continue
    return items


def _extract_go(content: str) -> list[str]:
    """Extract function and type signatures from Go."""
    items = []
    for line in content.split("\n"):
        line = line.strip()
        m = re.match(r"^func\s+(\(.*?\)\s+)?(\w+)\s*\((.*?)\)", line)
        if m:
            receiver = m.group(1) or ""
            name = m.group(2)
            params = m.group(3)[:80] if m.group(3) else ""
            items.append(f"func {receiver.strip()}{name}({params})")
            continue
        m = re.match(r"^type\s+(\w+)\s+(struct|interface)", line)
        if m:
            items.append(f"type {m.group(1)} {m.group(2)}")
            continue
    return items


def _extract_rust(content: str) -> list[str]:
    """Extract function and struct signatures from Rust."""
    items = []
    for line in content.split("\n"):
        line = line.strip()
        m = re.match(r"^(pub\s+)?(async\s+)?fn\s+(\w+)\s*[<(](.*)", line)
        if m:
            name = m.group(3)
            rest = m.group(4)[:80] if m.group(4) else ""
            items.append(f"fn {name}({rest}")
            continue
        m = re.match(r"^(pub\s+)?(struct|enum|trait|impl)\s+(\w+)", line)
        if m:
            items.append(f"{m.group(2)} {m.group(3)}")
            continue
    return items


def _extract_c(content: str) -> list[str]:
    """Extract function and struct signatures from C/C++."""
    items = []
    for line in content.split("\n"):
        s = line.strip()
        # function declaration/definition
        m = re.match(r"^(static\s+|inline\s+|virtual\s+)?.*?\s+(\w+)\s*\(([^)]*)\)\s*{?", s)
        if m and m.group(2) not in ("if", "else", "for", "while", "switch", "return", "sizeof"):
            name = m.group(2)
            params = m.group(3)[:60]
            prefix = m.group(1) or ""
            items.append(f"{prefix}fn {name}({params})")
            continue
        # struct/class/enum
        m = re.match(r"^(typedef\s+)?(struct|class|enum|union)\s+(\w+)", s)
        if m:
            items.append(f"{m.group(2)} {m.group(3)}")
            continue
        # #define MACRO
        m = re.match(r"^#define\s+(\w+)(?:\(.*\))?", s)
        if m:
            items.append(f"#define {m.group(1)}")
            continue
    return items


def _extract_java(content: str) -> list[str]:
    """Extract class, method, interface signatures from Java."""
    items = []
    for line in content.split("\n"):
        s = line.strip()
        # class/interface/enum/@interface
        m = re.match(r"^(public\s+|private\s+|protected\s+)?(abstract\s+|final\s+)?(class|interface|enum|@interface)\s+(\w+)", s)
        if m:
            items.append(f"{m.group(2) or ''}{m.group(3)} {m.group(4)}")
            continue
        # method
        m = re.match(r"^(public\s+|private\s+|protected\s+|static\s+|final\s+|abstract\s+|synchronized\s+)*\s*[\w<>[\],\s]+\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+\S+)?\s*{?", s)
        if m and m.group(2) not in ("if", "else", "for", "while", "switch", "return", "catch"):
            name = m.group(2)
            params = m.group(3)[:60]
            items.append(f"method {name}({params})")
            continue
    return items


def _extract_ruby(content: str) -> list[str]:
    """Extract method and class signatures from Ruby."""
    items = []
    for line in content.split("\n"):
        s = line.strip()
        m = re.match(r"^(class|module)\s+([\w:]+)", s)
        if m:
            items.append(f"{m.group(1)} {m.group(2)}")
            continue
        m = re.match(r"^def\s+(self\.)?(\w+[\?!]?)\s*(\(.*?\))?", s)
        if m:
            prefix = "self." if m.group(1) else ""
            name = m.group(2)
            params = m.group(3) or "()"
            items.append(f"def {prefix}{name}{params}")
            continue
    return items


def _extract_swift(content: str) -> list[str]:
    """Extract class and function signatures from Swift."""
    items = []
    for line in content.split("\n"):
        s = line.strip()
        m = re.match(r"^(public\s+|private\s+|internal\s+|open\s+)?(class|struct|enum|protocol|extension)\s+(\w+)", s)
        if m:
            items.append(f"{m.group(2)} {m.group(3)}")
            continue
        m = re.match(r"^(public\s+|private\s+|internal\s+|open\s+|static\s+)?func\s+(\w+)\s*\(([^)]*)\)", s)
        if m:
            items.append(f"func {m.group(2)}({m.group(3)[:60]})")
            continue
    return items


def _extract_kotlin(content: str) -> list[str]:
    """Extract class and function signatures from Kotlin."""
    items = []
    for line in content.split("\n"):
        s = line.strip()
        m = re.match(r"^(data\s+|sealed\s+|open\s+)?(class|interface|object|enum class|data class)\s+(\w+)", s)
        if m:
            items.append(f"{m.group(2)} {m.group(3)}")
            continue
        m = re.match(r"^(fun|suspend fun)\s+(\w+)\s*\(([^)]*)\)", s)
        if m:
            items.append(f"{m.group(1)} {m.group(2)}({m.group(3)[:60]})")
            continue
    return items


def _extract_shell(content: str) -> list[str]:
    """Extract function definitions from shell scripts."""
    items = []
    for line in content.split("\n"):
        s = line.strip()
        m = re.match(r"^function\s+(\w+)\s*{", s)
        if m:
            items.append(f"function {m.group(1)}")
            continue
        m = re.match(r"^(\w+)\s*\(\s*\)\s*{", s)
        if m and m.group(1) not in ("if", "then", "else", "fi", "esac", "do", "done"):
            items.append(f"function {m.group(1)}")
            continue
    return items


_EXTRACTORS = {
    ".py": _extract_python,
    ".js": _extract_javascript,
    ".ts": _extract_javascript,
    ".jsx": _extract_javascript,
    ".tsx": _extract_javascript,
    ".go": _extract_go,
    ".rs": _extract_rust,
    ".sh": _extract_shell,
    ".c": _extract_c,
    ".h": _extract_c,
    ".cpp": _extract_c,
    ".hpp": _extract_c,
    ".java": _extract_java,
    ".rb": _extract_ruby,
    ".swift": _extract_swift,
    ".kt": _extract_kotlin,
}


def execute(path: str = ".", save: bool = True) -> str:
    """Scan project directory and build a structural index.

    Args:
        path: 项目根目录（默认当前目录）
        save: 是否保存到长期记忆（默认 True）
    """
    root = Path(path).expanduser().resolve()
    if not root.exists():
        return f"错误: 目录不存在: {root}"

    # ── Scan ──
    file_count = 0
    total_items = 0
    total_imports = 0
    index_lines = [f"# 项目索引: {root.name}", f"路径: {root}", ""]
    dep_lines = ["", "## 模块依赖", ""]

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden and build directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

        for fname in sorted(filenames):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in INDEX_EXTS:
                continue
            if fname.startswith("."):
                continue

            filepath = os.path.join(dirpath, fname)
            rel = os.path.relpath(filepath, root)

            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(50000)  # first 50K is enough for signatures
            except Exception:
                continue

            extractor = _EXTRACTORS.get(ext)
            if not extractor:
                continue

            lang_map = {".py": "py", ".js": "js", ".ts": "ts", ".jsx": "js", ".tsx": "ts",
                        ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
                        ".go": "go", ".rs": "rs", ".java": "java"}
            lang = lang_map.get(ext, "py")
            summary = _extract_summary(content, lang)
            imports = _extract_imports(content, ext)

            items = extractor(content)
            if not items and not summary:
                continue

            file_count += 1
            total_items += len(items)
            total_imports += len(imports)

            summary_line = f" — {summary}" if summary else ""
            index_lines.append(f"\n## {rel} ({len(items)} symbols){summary_line}")
            for item in items[:50]:  # max 50 per file
                index_lines.append(f"  - {item}")
            if imports:
                dep_lines.append(f"  {rel} → {', '.join(imports[:10])}")

    if file_count == 0:
        return f"在 {root} 下未找到可索引的代码文件"

    index_lines.append(f"\n---")
    index_lines.append(f"总计: {file_count} 个文件, {total_items} 个符号, {total_imports} 个导入")
    if len(dep_lines) > 2:
        index_lines.extend(dep_lines)

    index_text = "\n".join(index_lines)

    # ── Save to memory ──
    saved_msg = ""
    if save:
        try:
            from tools.v5_memory import save_to_knowledge_base
            save_to_knowledge_base(
                f"项目索引 [{root.name}]: {index_text[:80000]}",
                "project_index"
            )
            saved_msg = "\n✅ 已保存到长期记忆，下次对话自动加载"
        except Exception:
            saved_msg = "\n⚠️ 保存到记忆失败（索引仅在本次会话有效）"

    return f"{index_text[:6000]}\n\n... ({file_count} 文件, {total_items} 符号){saved_msg}"


TOOL_FUNC = execute
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "扫描项目目录，提取所有函数、类、接口等代码结构，建立索引。"
            "索引保存到长期记忆，后续对话中无需 grep_code 即可快速定位代码。"
            "支持 Python、JavaScript/TypeScript、Go、Rust。"
            "首次打开项目时使用此工具建立索引。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "项目根目录路径（默认当前工作目录）"
                },
                "save": {
                    "type": "boolean",
                    "description": "是否保存到长期记忆（默认 True）。False 时只返回不保存。"
                }
            },
            "required": []
        }
    }
}


def register(reg):
    reg(TOOL_NAME, TOOL_FUNC, TOOL_SCHEMA)
