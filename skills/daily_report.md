# 技能：生成日报

## 触发场景
用户说"生成日报"、"今天做了什么"、"帮我写日报"

## 工作流步骤
1. 获取当前日期：`get_current_time(format="date")`
2. 搜索今天的日历事件：`list_calendar_events()`
3. 搜索今天的笔记：`search_obsidian("今日总结")`
4. 查看今天的邮件：`read_recent(limit=5)`
5. 整合信息，生成日报笔记：`write_obsidian("日报_{日期}.md", 内容)`

## 输出格式
- 今天的日期
- 完成的日程
- 新邮件摘要
- 笔记记录
- 明日计划
