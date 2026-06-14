"""工具执行 — 并行调度、错误分析、密钥脱敏、自动 diff、自动运行、文件回滚"""

import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


class ToolRunnerMixin:
    """为 Engine 提供工具执行、结果加工能力。"""

    MAX_TOOL_RESULT_LENGTH = 40000
    _file_checkpoints: dict[str, str] = {}  # path -> content before write

    SECRET_PATTERNS = [
        re.compile(r'(sk-|sk-ant-)[a-zA-Z0-9_\-]{20,}'),
        re.compile(r'(ghp_|gho_|ghu_|ghs_|ghf_)[a-zA-Z0-9_\-]{20,}'),
        re.compile(r'AKIA[0-9A-Z]{16}'),
        re.compile(r'-----BEGIN\s+(RSA|DSA|EC|OPENSSH|PGP)\s+PRIVATE\s+KEY-----'),
        re.compile(r'(_KEY|_SECRET|_TOKEN|_PASSWORD|_API_KEY)\s*=\s*.{8,}', re.IGNORECASE),
        re.compile(r'Bearer\s+[a-zA-Z0-9_\-\.]{20,}'),
        re.compile(r'(password|passwd|pwd)\s*[:=]\s*["\']?.{6,}["\']?', re.IGNORECASE),
    ]

    def _redact_secrets(self, text: str) -> str:
        for pattern in self.SECRET_PATTERNS:
            text = pattern.sub('[REDACTED]', text)
        return text

    def _format_final_output(self, content: str) -> str:
        if not content:
            return content
        lines = content.split('\n')
        seen = set()
        unique_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                unique_lines.append(line)
            elif not stripped:
                unique_lines.append(line)
        return '\n'.join(unique_lines)

    def _execute_tool_loop(self, tool_calls: list) -> list:
        from core.tool_executor import execute_tool as _execute_tool
        from tools import TOOLS_SCHEMA

        # 工具失败时的替代建议
        _TOOL_FALLBACKS = {
            "web_search": "web_fetch(url), open_url(url)",
            "web_fetch": "web_search(query), open_url(url)",
            "search_obsidian": "read_local_file(path), list_directory(path)",
            "notion_search": "notion_read_page(page_id)",
            "read_local_file": "list_directory(path), execute_terminal('cat /path')",
            "execute_terminal": "代码执行可以通过 code_execution 工具",
            "notion_create_page": "file_writer(path), write_obsidian(path)",
            "search_emails": "read_email_content(email_id)",
        }

        # Build a quick lookup: tool_name -> description + params
        _schema_map = {}
        for t in TOOLS_SCHEMA:
            fn = t.get("function", t)
            name = fn.get("name", "")
            if name:
                params = fn.get("parameters", {}).get("properties", {})
                required = fn.get("parameters", {}).get("required", [])
                desc = fn.get("description", "")
                _schema_map[name] = {"description": desc, "properties": params, "required": required}

        # 拦截 restore_checkpoint 工具，由 engine 自身处理
        self._notify("thinking", {"phase": "executing_tools", "message": f"准备执行 {len(tool_calls)} 个工具"})
        tool_results = []

        # Phase 1: 确认检查（必须顺序执行）
        prepared = []
        for tc in tool_calls:
            tool_name = tc.get("function", {}).get("name", "")
            if tool_name == "restore_checkpoint":
                self._handle_restore_checkpoint(tc, tool_results)
                continue
            if tool_name == "cross_search":
                self._handle_cross_search(tc, tool_results)
                continue
            args_str = tc.get("function", {}).get("arguments", "{}")
            try:
                tool_args = json.loads(args_str)
            except Exception:
                tool_args = {}
                # 架构化错误：告诉 LLM 正确的参数格式
                schema = _schema_map.get(tool_name, {})
                props = schema.get("properties", {})
                if props:
                    hints = []
                    for pname, pinfo in props.items():
                        ptype = pinfo.get("type", "string")
                        desc = pinfo.get("description", "")
                        hints.append(f"  {pname} ({ptype}): {desc}")
                    required = schema.get("required", [])
                    req_hint = f"必需参数: {', '.join(required)}" if required else ""
                    tool_results.append({
                        "tool_call_id": tc.get("id", ""),
                        "role": "tool",
                        "content": (
                            f"错误: 工具 '{tool_name}' 参数格式错误\n"
                            f"LLM 传入了无效 JSON: {args_str[:100]}\n"
                            f"正确格式:\n" + "\n".join(hints) +
                            (f"\n{req_hint}" if req_hint else "")
                        )
                    })
                    self._record_message("tool_result", result="参数解析失败")
                    continue
            self._record_message("tool_call", tool_name=tool_name, args=tool_args)
            is_high_risk, reason = self._is_high_risk_tool(tool_name, tool_args)
            if is_high_risk:
                self._notify("confirm_request", {"tool_name": tool_name, "tool_args": tool_args, "reason": reason})
                confirmed = self._confirm(tool_name, tool_args, reason)
                if not confirmed:
                    self._notify("tool_cancelled", {"name": tool_name, "args": tool_args, "reason": "用户取消"})
                    tool_results.append({"tool_call_id": tc.get("id", ""), "role": "tool", "content": f"操作已取消: {reason}"})
                    continue
            prepared.append((tc, tool_name, tool_args))

        if not prepared:
            return tool_results

        # Phase 2: 并行执行
        self._notify("thinking", {"phase": "executing", "message": f"并行执行 {len(prepared)} 个工具"})
        executor = ThreadPoolExecutor(max_workers=len(prepared))
        future_map = {}
        for tc, tool_name, tool_args in prepared:
            # 生成人类可读的工具上下文
            context = tool_name
            if isinstance(tool_args, dict):
                if "query" in tool_args:
                    context = f"搜索: {tool_args['query'][:60]}"
                elif "command" in tool_args:
                    context = f"终端: {tool_args['command'][:60]}"
                elif "filepath" in tool_args:
                    context = f"读取: {tool_args['filepath'][:60]}"
                elif "path" in tool_args:
                    context = f"文件: {tool_args['path'][:60]}"
                elif "url" in tool_args:
                    context = f"打开: {tool_args['url'][:60]}"
                elif "filename" in tool_args:
                    context = f"笔记: {tool_args['filename'][:60]}"
                elif "keyword" in tool_args:
                    context = f"搜索: {tool_args['keyword'][:60]}"
                elif "content" in tool_args:
                    content_preview = tool_args["content"][:40].replace("\n", " ")
                    context = f"写入: {content_preview}"
            # 文件写入前创建检查点（允许回滚）
            if tool_name == "file_writer" and isinstance(tool_args, dict):
                path = tool_args.get("path", "")
                if path and os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf-8") as _f:
                            self._file_checkpoints[path] = _f.read()
                    except Exception:
                        pass
            self._notify("tool_call", {"name": tool_name, "args": tool_args, "context": context, "status": "start"})
            future = executor.submit(_execute_tool, tool_name, tool_args)
            future_map[future] = (tc, tool_name, tool_args)
        executor.shutdown(wait=False)

        # Phase 3: 收集结果
        for future in as_completed(future_map):
            tc, tool_name, tool_args = future_map[future]
            start_time = time.time()
            try:
                result = future.result(timeout=30)
            except Exception as e:
                error_detail = str(e)
                schema = _schema_map.get(tool_name, {})
                props = schema.get("properties", {})
                hint = ""
                if props:
                    hints = []
                    for pname, pinfo in props.items():
                        ptype = pinfo.get("type", "string")
                        hints.append(f"  {pname}:{ptype}={tool_args.get(pname, '?')}")
                    hint = "\\n参数: " + ", ".join(hints[:5])
                alt_hints = _TOOL_FALLBACKS.get(tool_name, "")
                result = f"错误: 工具 '{tool_name}' 执行异常: {error_detail[:200]}{hint}"
                if alt_hints:
                    result += f"\\n可尝试: {alt_hints}"
            duration = time.time() - start_time

            is_error = result.startswith("错误")
            if is_error:
                self._tool_failures[tool_name] = self._tool_failures.get(tool_name, 0) + 1
            else:
                self._tool_failures[tool_name] = 0

            if self._tool_failures.get(tool_name, 0) >= 2:
                result = f"错误: 工具 '{tool_name}' 持续失败，请尝试其他方法（不要再次使用此工具）"

            result = self._redact_secrets(result)

            # 错误结构化
            if tool_name == "execute_terminal" and result.startswith("错误"):
                for line in result.split("\n"):
                    m = re.search(r'File "([^"]+)", line (\d+)', line)
                    if m:
                        filepath, lineno = m.group(1), m.group(2)
                        error_type = "错误"
                        for et in ["SyntaxError", "TypeError", "ValueError", "ImportError",
                                    "ModuleNotFoundError", "NameError", "AttributeError",
                                    "IndexError", "KeyError", "FileNotFoundError"]:
                            if et in line:
                                error_type = et
                                break
                        result = f"[{error_type}] {filepath}:{lineno}\n{result[:self.MAX_TOOL_RESULT_LENGTH]}"
                        break

            # Git diff 捕获
            if tool_name in ("file_writer", "code_execution") and not result.startswith("错误"):
                try:
                    cwd = os.getcwd()
                    diff = subprocess.run(
                        ["git", "diff"], capture_output=True, text=True, cwd=cwd, timeout=3
                    )
                    if diff.returncode == 0 and diff.stdout.strip():
                        self._pending_diff = diff.stdout.strip()
                except Exception:
                    pass

            # 自动运行
            if tool_name == "file_writer" and not result.startswith("错误"):
                filepath = tool_args.get("path", "") if isinstance(tool_args, dict) else ""
                if filepath.endswith(".py"):
                    try:
                        cwd = os.getcwd()
                        run_result = subprocess.run(
                            ["python3", filepath], capture_output=True, text=True, cwd=cwd, timeout=10
                        )
                        parts = []
                        if run_result.stdout.strip():
                            parts.append(f"输出:\n{run_result.stdout.strip()[:1000]}")
                        if run_result.stderr.strip():
                            parts.append(f"错误:\n{run_result.stderr.strip()[:1000]}")
                        if parts:
                            result += "\n\n[自动运行结果]\n" + "\n".join(parts)
                        else:
                            result += "\n\n[自动运行] 执行成功（无输出）"
                    except subprocess.TimeoutExpired:
                        result += "\n\n[自动运行] 执行超时（>10秒）"
                    except Exception:
                        pass

            self._notify("tool_result", {
                "name": tool_name, "args": tool_args, "result": result[:200],
                "duration": duration, "success": not result.startswith("错误")
            })
            tool_results.append({
                "tool_call_id": tc.get("id", ""), "role": "tool",
                "content": result[:self.MAX_TOOL_RESULT_LENGTH]
            })
            self._record_message("tool_result", result=result[:200])

        return tool_results

    def _restore_checkpoint(self, path: str = "") -> str:
        """从检查点恢复文件内容。path 为空时列出所有检查点。"""
        if not path:
            if not self._file_checkpoints:
                return "ℹ️ 当前没有可回滚的文件检查点"
            lines = ["📋 可回滚的文件:"]
            for p in self._file_checkpoints:
                size = len(self._file_checkpoints[p])
                lines.append(f"  {p} ({size} 字符)")
            return "\n".join(lines)
        if path not in self._file_checkpoints:
            return f"❌ 没有找到 '{path}' 的检查点"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._file_checkpoints[path])
            del self._file_checkpoints[path]
            return f"✅ 已回滚: {path}"
        except Exception as e:
            return f"❌ 回滚失败: {str(e)}"

    def _handle_restore_checkpoint(self, tc: dict, tool_results: list):
        """Handle restore_checkpoint tool inline (needs engine context).
        Supports: file checkpoint restore, trash restore, trash listing."""
        import os
        args_str = tc.get("function", {}).get("arguments", "{}")
        try:
            tool_args = json.loads(args_str)
        except Exception:
            tool_args = {}
        path = tool_args.get("path", "")

        # Trash operations
        if path == "__list_trash__":
            from tools.obsidian_tools import _list_trash
            items = _list_trash()
            if not items:
                result = "回收站为空"
            else:
                lines = ["回收站中的文件:"]
                for i, name in enumerate(items[:20], 1):
                    lines.append(f"  {i}. {name}")
                result = "\n".join(lines)
        elif path and path.startswith("trash:"):
            trash_name = path.split(":", 1)[1]
            trash_dir = os.path.expanduser("~/.bobo/trash")
            trash_path = os.path.join(trash_dir, trash_name)
            if not os.path.exists(trash_path):
                result = f"回收站中未找到: {trash_name}"
            else:
                # Try to restore to original location (extract from backup name)
                vault = os.environ.get("OBSIDIAN_VAULT", "")
                base_name = trash_name.rsplit("_", 1)[0]  # remove timestamp
                restore_path = os.path.join(vault, base_name) if vault else os.path.join(os.getcwd(), base_name)
                if os.path.exists(restore_path):
                    result = f"文件已存在: {restore_path}，请先删除旧文件再恢复"
                else:
                    import shutil
                    os.makedirs(os.path.dirname(restore_path) or ".", exist_ok=True)
                    shutil.move(trash_path, restore_path)
                    result = f"✅ 已从回收站恢复: {trash_name}"
        else:
            # Normal checkpoint restore
            result = self._restore_checkpoint(path)

        self._notify("restore_checkpoint", {"name": "restore_checkpoint", "args": tool_args, "result": result[:200], "duration": 0, "success": True})
        tool_results.append({"tool_call_id": tc.get("id", ""), "role": "tool", "content": result[:self.MAX_TOOL_RESULT_LENGTH]})
        self._record_message("tool_result", result=result[:200])

    def _handle_cross_search(self, tc: dict, tool_results: list):
        """Search Obsidian + Notion + email for the same query."""
        args_str = tc.get("function", {}).get("arguments", "{}")
        try:
            tool_args = json.loads(args_str)
        except Exception:
            tool_args = {}
        query = tool_args.get("query", "")
        if not query:
            result = "请输入搜索关键词"
            self._notify("tool_result", {"name": "cross_search", "args": tool_args, "result": result, "duration": 0, "success": False})
            tool_results.append({"tool_call_id": tc.get("id", ""), "role": "tool", "content": result})
            return

        self._notify("thinking", {"phase": "cross_search", "message": f"搜索 '{query}' 跨平台..."})
        parts = []

        # Obsidian
        try:
            from tools.obsidian_tools import search_obsidian_notes
            obsidian_result = search_obsidian_notes(query)
            if "没有找到" not in obsidian_result:
                parts.append(f"[Obsidian]\n{obsidian_result}")
        except Exception:
            pass

        # Notion (only if configured)
        import os
        if os.environ.get("NOTION_API_KEY", ""):
            try:
                from tools.notion_search import execute as notion_search
                notion_result = notion_search(query)
                if "没有找到" not in notion_result and "Notion 未配置" not in notion_result:
                    parts.append(f"[Notion]\n{notion_result}")
            except Exception:
                pass

        # Email (only if configured)
        if os.path.exists(os.path.expanduser("~/.bobo/mail.json")):
            try:
                from tools.search_emails import execute as email_search
                email_result = email_search(query)
                if email_result and "没有找到" not in email_result:
                    parts.append(f"[邮件]\n{email_result}")
            except Exception:
                pass

        if not parts:
            result = f"在已配置的平台中都没有找到包含 '{query}' 的内容"
        else:
            result = f"跨平台搜索 '{query}':\n\n" + "\n\n".join(parts)

        self._notify("tool_result", {"name": "cross_search", "args": tool_args, "result": result[:200], "duration": 0, "success": True})
        tool_results.append({"tool_call_id": tc.get("id", ""), "role": "tool", "content": result[:self.MAX_TOOL_RESULT_LENGTH]})
        self._record_message("tool_result", result=result[:200])
