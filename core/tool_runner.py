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
        in_code_block = False
        for line in lines:
            stripped = line.strip()
            # 代码围栏内的行不参与去重，原样保留（代码里合法的重复行不能删）
            if stripped.startswith('```'):
                in_code_block = not in_code_block
                unique_lines.append(line)
                continue
            if in_code_block:
                unique_lines.append(line)
                continue
            if stripped and stripped not in seen:
                seen.add(stripped)
                unique_lines.append(line)
            elif not stripped:
                unique_lines.append(line)
        return '\n'.join(unique_lines)

    def _execute_tool_loop(self, tool_calls: list) -> list:
        from core.tool_executor import execute_tool as _execute_tool
        from tools import TOOLS_SCHEMA

        # 工具失败时的替代建议：告诉 LLM 具体下一步做什么
        _TOOL_FALLBACKS = {
            # Web 类
            "web_search": "网络搜索失败 → 尝试 web_fetch(url) 直接抓取已知网页，或 open_url(url) 打开浏览器",
            "web_fetch": "网页抓取失败 → 尝试 web_search(query) 搜索相同内容，或 web_extract(url) 提取纯文本",
            "web_extract": "提取失败 → 尝试 web_fetch(url) 重新抓取，或直接用浏览器 open_url(url)",
            "open_url": "打开失败 → 尝试 web_fetch(url) 获取页面内容",
            # 文件/代码类
            "read_local_file": "读取失败 → 检查路径，用 list_directory(path) 查看目录，或用 execute_terminal 的 cat 命令",
            "list_directory": "列目录失败 → 用 execute_terminal('ls -la /path') 查看，或 read_local_file 逐个读取",
            "file_operation": "文件操作失败 → 用 execute_terminal 的 cp/mv/rm 命令替代",
            "search_code": "代码搜索失败 → 用 grep_code(pattern) 正则搜索，或用 execute_terminal('grep -r pattern path')",
            "execute_terminal": "终端命令失败 → 检查命令语法，用 code_execution 执行脚本，或拆分为多个简单命令",
            "file_operation": "文件写入失败 → 用 execute_terminal('cat > file') 写入，或检查目录权限",
            "edit_file": "编辑失败 → old_string 与文件内容不完全一致（含缩进/空格），用 read_local_file 重新读取确认",
            "grep_code": "搜索无结果 → 放宽正则表达式，或改用 file_types 不过滤先看全部文件，或用 list_directory 确定文件位置",
            "run_tests": "测试失败 → 查看失败详情，用 grep_code 定位问题代码，用 edit_file 修复后重新 run_tests",
            # Obsidian 类
            "search_obsidian": "搜索无结果 → 用 grep_code 搜索本地文件，或用 list_directory 浏览 vault",
            "read_obsidian": "读取失败 → 用 read_local_file(path) 直接读取文件",
            "write_obsidian": "写入失败 → 用 file_operation(action='write', path=...) 或 execute_terminal('cat > file') 写入",
            "append_obsidian": "追加失败 → 用 read_obsidian 读取原内容，合并后用 write_obsidian 回写",
            "classify_note": "分类失败 → 手动用 batch_move_notes 移动到目标文件夹",
            # Notion 类
            "notion_search": "Notion 搜索失败 → 检查 Notion API Key 是否已配置，或用 notion_read_page(page_id) 直接读取",
            "notion_read_page": "Notion 读取失败 → 检查 page_id 是否正确，或用 notion_search(query) 重新搜索",
            "notion_create_page": "Notion 创建失败 → 用 write_obsidian(path) 保存到本地，或检查 Notion 权限",
            "notion_append": "Notion 追加失败 → 用 notion_read_page 读取后用 notion_create_page 重建",
            # Email 类
            "search_emails": "邮件搜索失败 → 检查 ~/.bobo/mail.json 是否配置，或用 read_email_content(id) 直接读取",
            "read_email_content": "邮件读取失败 → 用 search_emails 重新搜索，或检查邮箱配置",
            # GitHub 类
            "git_status": "Git 状态失败 → 用 execute_terminal('git status') 查看",
            "github_create_repo": "创建仓库失败 → 用 execute_terminal('gh repo create') 替代，或检查 GitHub token",
            "github_create_pr": "创建 PR 失败 → 用 execute_terminal('gh pr create') 替代",
            # macOS 类
            "send_notification": "通知失败 → 用 execute_terminal('osascript -e display notification') 替代",
            "set_reminder": "提醒失败 → 用 create_calendar_event 或 execute_terminal 创建",
            # API 类
            "api_call": "API 调用失败 → 检查 api_register 的配置是否正确，端点路径和认证方式是否匹配",
            "api_register": "API 注册失败 → 确认 base_url 可访问，auth_key 有效，endpoints JSON 格式正确",
            # 通用
            "code_execution": "代码执行失败 → 查看错误详情修复代码，或用 execute_terminal 逐行调试",
            "save_memory": "保存失败 → 内容可能已达上限（100K 字符），用 search_memory 查看已有的，delete_entry 删除旧的",
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
            if tool_name in ("file_writer", "file_operation") and isinstance(tool_args, dict):
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
                # 根据异常类型给出更有用的提示
                if "Timeout" in type(e).__name__ or "timeout" in error_detail.lower():
                    error_type_hint = "（超时，可重试一次或增加超时时间）"
                elif "Connection" in type(e).__name__ or "connect" in error_detail.lower():
                    error_type_hint = "（网络连接失败，检查网络后重试）"
                else:
                    error_type_hint = ""

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
                result = f"错误: 工具 '{tool_name}' 执行失败{error_type_hint}: {error_detail[:200]}{hint}"
                if alt_hints:
                    result += f"\\n→ {alt_hints}"
            duration = time.time() - start_time

            is_error = result.startswith("错误")
            if is_error:
                self._tool_failures[tool_name] = self._tool_failures.get(tool_name, 0) + 1
            else:
                self._tool_failures[tool_name] = 0

            if self._tool_failures.get(tool_name, 0) >= 2:
                alt = _TOOL_FALLBACKS.get(tool_name, "")
                if alt:
                    result = f"⚠️ 工具 '{tool_name}' 已连续失败 2 次，请停止使用此工具。\n{alt}"
                else:
                    result = f"⚠️ 工具 '{tool_name}' 已连续失败 2 次，请考虑完全不同的方法来解决用户的问题，而非继续用此工具"

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

            # 终端执行记录 — 发射到桌面端
            if tool_name == "execute_terminal" and hasattr(self, '_notify'):
                cmd = ""
                if isinstance(tool_args, dict):
                    cmd = tool_args.get("command", "") or tool_args.get("cmd", "") or str(tool_args)[:80]
                self._notify("terminal.output", {
                    "command": str(cmd)[:200],
                    "output": str(result)[:2000],
                    "duration": 0,
                })

            # Git diff 捕获
            if tool_name in ("file_writer", "code_execution", "edit_file", "write_obsidian", "append_obsidian") and not result.startswith("错误"):
                try:
                    cwd = os.getcwd()
                    diff = subprocess.run(
                        ["git", "diff"], capture_output=True, text=True, cwd=cwd, timeout=3
                    )
                    diff_text = ""
                    if diff.returncode == 0 and diff.stdout.strip():
                        self._pending_diff = diff.stdout.strip()
                        diff_text = diff.stdout.strip()[:3000]
                    # 通知桌面端：文件已修改
                    if hasattr(self, '_notify'):
                        fpath = ""
                        if isinstance(tool_args, dict):
                            fpath = tool_args.get("file_path", "") or tool_args.get("path", "") or ""
                        if not fpath and tool_name in ("write_obsidian", "append_obsidian"):
                            fpath = tool_args.get("filename", "") or tool_args.get("filepath", "") or tool_args.get("title", "")
                        self._notify("notes.changed", {
                            "file": fpath,
                            "diff": diff_text,
                            "tool": tool_name,
                        })
                except Exception:
                    pass

            # 自动运行
            if tool_name in ("file_writer", "file_operation") and not result.startswith("错误"):
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
                "name": tool_name, "args": tool_args,
                "result": result[:8000],
                "result_truncated": len(result) > 8000,
                "duration": duration, "success": not result.startswith("错误")
            })
            tool_results.append({
                "tool_call_id": tc.get("id", ""), "role": "tool",
                "content": result[:self.MAX_TOOL_RESULT_LENGTH]
            })
            self._record_message("tool_result", result=result[:200])

        # ── Loop detection: warn LLM if same tool+args called 3+ times ──
        for tc, tool_name, tool_args in prepared:
            args_key = str(sorted(tool_args.items())) if tool_args else "{}"
            self._recent_tool_calls.append((tool_name, args_key))
        if len(self._recent_tool_calls) > 20:
            self._recent_tool_calls = self._recent_tool_calls[-20:]

        from collections import Counter
        recent = self._recent_tool_calls[-10:]
        for (name, args), count in Counter(recent).items():
            if count >= 3:
                warning = (
                    f"[防循环] '{name}' 已重复调用 {count} 次（相同参数）。\n"
                    f"请停止。若文件截断，用 offset+limit 分页继续。否则基于已有信息继续或报告用户。"
                )
                tool_results.append({
                    "tool_call_id": "system-loop-detector", "role": "tool",
                    "content": warning
                })
                break

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
        """Search Obsidian + Notion + email, return unified time-sorted timeline."""
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
        import os as _os

        items = []  # [{platform, title, date, detail}]

        # ── Obsidian ──
        try:
            from tools.obsidian_tools import OBSIDIAN_VAULT, BLOCKED_FOLDERS
            vault = OBSIDIAN_VAULT
            if vault and _os.path.exists(vault):
                from tools.obsidian_tools import search_obsidian_notes
                obsidian_result = search_obsidian_notes(query)
                if "没有找到" not in obsidian_result and "📝" in obsidian_result:
                    # 解析文件路径，获取修改时间
                    for line in obsidian_result.split("\n"):
                        line = line.strip()
                        if line.startswith("- "):
                            rel_path = line[2:]
                            abs_path = _os.path.join(vault, rel_path)
                            try:
                                mtime = _os.path.getmtime(abs_path)
                                date_str = time.strftime("%m-%d %H:%M", time.localtime(mtime))
                                items.append({
                                    "platform": "Obsidian",
                                    "title": rel_path.replace(".md", ""),
                                    "date": mtime,
                                    "date_str": date_str,
                                    "detail": rel_path,
                                })
                            except Exception:
                                pass
        except Exception:
            pass

        # ── Notion ──
        if _os.environ.get("NOTION_API_KEY", ""):
            try:
                import requests as _req
                api_key = _os.environ.get("NOTION_API_KEY", "")
                resp = _req.post(
                    "https://api.notion.com/v1/search",
                    json={"query": query, "page_size": 10},
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Notion-Version": "2022-06-28",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    for page in resp.json().get("results", []):
                        title = "未命名"
                        for prop in page.get("properties", {}).values():
                            if prop.get("type") == "title":
                                parts = prop.get("title", [])
                                if parts:
                                    title = "".join(t.get("plain_text", "") for t in parts)
                                break
                        edited = page.get("last_edited_time", "")
                        try:
                            from datetime import datetime as _dt
                            dt = _dt.fromisoformat(edited.replace("Z", "+00:00"))
                            ts = dt.timestamp()
                            date_str = dt.strftime("%m-%d %H:%M")
                        except Exception:
                            ts = 0
                            date_str = ""
                        items.append({
                            "platform": "Notion",
                            "title": title,
                            "date": ts,
                            "date_str": date_str,
                            "detail": page.get("url", ""),
                        })
            except Exception:
                pass

        # ── Email ──
        if _os.path.exists(_os.path.expanduser("~/.bobo/mail.json")):
            try:
                from tools.email_module import EmailModule
                mail = EmailModule()
                if mail.enabled:
                    email_results = mail.search_emails(query)
                    if isinstance(email_results, list):
                        for em in email_results:
                            subject = em.get("subject", "无主题")
                            date_str = em.get("date", "")
                            ts = 0
                            try:
                                from email.utils import parsedate_to_datetime
                                ts = parsedate_to_datetime(date_str).timestamp()
                            except Exception:
                                pass
                            items.append({
                                "platform": "Email",
                                "title": subject,
                                "date": ts,
                                "date_str": date_str[:10] if date_str else "",
                                "detail": em.get("from", ""),
                            })
                    elif isinstance(email_results, str) and "未找到" not in email_results:
                        # 解析文本格式的邮件结果
                        for line in email_results.split("\n"):
                            line = line.strip()
                            if line and not line.startswith("📭") and not line.startswith("📧"):
                                items.append({
                                    "platform": "Email",
                                    "title": line[:80],
                                    "date": 0,
                                    "date_str": "",
                                    "detail": "",
                                })
            except Exception:
                pass

        # ── 合并、去重、排序 ──
        if not items:
            result = f"在已配置的平台中都没有找到包含 '{query}' 的内容"
        else:
            # 去重：标题相似度 > 80% 视为重复，保留日期最新的
            unique = []
            seen_titles = []
            items.sort(key=lambda x: x.get("date", 0), reverse=True)
            for item in items:
                title_lower = item["title"].lower()
                is_dup = False
                for seen in seen_titles:
                    if title_lower in seen or seen in title_lower:
                        is_dup = True
                        break
                    # 简单相似度：共用词比例
                    words = set(title_lower.split())
                    seen_words = set(seen.split())
                    if words and seen_words:
                        overlap = len(words & seen_words) / min(len(words), len(seen_words))
                        if overlap > 0.7:
                            is_dup = True
                            break
                if not is_dup:
                    seen_titles.append(title_lower)
                    unique.append(item)

            # 排序：有日期的在前，无日期的在后
            dated = [i for i in unique if i["date"] > 0]
            undated = [i for i in unique if i["date"] == 0]
            dated.sort(key=lambda x: x["date"], reverse=True)

            lines = [f"跨平台搜索 '{query}' — 找到 {len(unique)} 条结果，按时间排列:\n"]
            for item in dated + undated:
                platform_icon = {"Obsidian": "📝", "Notion": "📋", "Email": "📧"}.get(item["platform"], "📄")
                date_part = f" {item['date_str']}" if item["date_str"] else ""
                detail_part = f" — {item['detail'][:50]}" if item["detail"] else ""
                lines.append(f"  {platform_icon}{date_part}  {item['title']}{detail_part}")

            # 平台覆盖摘要
            platforms_found = list(set(i["platform"] for i in unique))
            lines.append(f"\n来源: {', '.join(platforms_found)} （共 {len(unique)} 条）")

            result = "\n".join(lines)

        self._notify("tool_result", {"name": "cross_search", "args": tool_args, "result": result[:200], "duration": 0, "success": True})
        tool_results.append({"tool_call_id": tc.get("id", ""), "role": "tool", "content": result[:self.MAX_TOOL_RESULT_LENGTH]})
        self._record_message("tool_result", result=result[:200])
