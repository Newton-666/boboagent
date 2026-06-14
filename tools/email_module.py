#!/usr/bin/env python3
"""
邮箱模块 - 完整版（供 Bobo 调用）
"""

import json
import imaplib
import email
from email.header import decode_header
import os
import re
from collections import Counter
from datetime import datetime, timedelta


class EmailModule:
    def __init__(self):
        self.config = self._load_config()
        self.enabled = self.config is not None
    
    def _load_config(self):
        config_path = os.path.expanduser("~/.bobo/mail.json")
        if not os.path.exists(config_path):
            return None
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception:
            return None
    
    def _connect_imap(self):
        if not self.enabled:
            raise Exception("邮箱未配置")
        mail = imaplib.IMAP4_SSL(self.config["imap_server"], self.config["imap_port"])
        mail.login(self.config["email"], self.config["auth_code"])
        return mail
    
    def read_recent(self, limit=5):
        """读取最近邮件"""
        if not self.enabled:
            return "❌ 邮箱未配置，请在 ~/.bobo/mail.json 中配置"
        
        try:
            mail = self._connect_imap()
            mail.select("INBOX")
            
            result, data = mail.search(None, "ALL")
            email_ids = data[0].split()
            latest_ids = email_ids[-limit:]
            
            emails = []
            for eid in reversed(latest_ids):
                result, msg_data = mail.fetch(eid, "(RFC822)")
                if result == "OK":
                    msg = email.message_from_bytes(msg_data[0][1])
                    
                    subject = decode_header(msg.get("Subject", "无主题"))[0][0]
                    if isinstance(subject, bytes):
                        subject = subject.decode("utf-8", errors="ignore")
                    
                    from_addr = msg.get("From", "未知")
                    
                    emails.append({
                        "subject": subject[:60],
                        "from": from_addr[:50]
                    })
            
            mail.close()
            mail.logout()
            
            if not emails:
                return "📭 收件箱为空"
            
            result = f"📬 最新 {len(emails)} 封邮件:\n"
            for i, e in enumerate(emails, 1):
                result += f"  {i}. {e['subject']}\n     📧 {e['from']}\n"
            return result
            
        except Exception as e:
            return f"❌ 读取失败: {str(e)}"
    
    def read_email_content(self, index=1):
        """读取指定邮件的完整内容"""
        if not self.enabled:
            return "❌ 邮箱未配置"
        
        try:
            mail = self._connect_imap()
            mail.select("INBOX")
            
            result, data = mail.search(None, "ALL")
            email_ids = data[0].split()
            
            if index < 1 or index > len(email_ids):
                return f"❌ 索引超出范围，共有 {len(email_ids)} 封邮件"
            
            target_id = email_ids[-index]
            result, msg_data = mail.fetch(target_id, "(RFC822)")
            
            if result == "OK":
                msg = email.message_from_bytes(msg_data[0][1])
                
                subject = decode_header(msg.get("Subject", "无主题"))[0][0]
                if isinstance(subject, bytes):
                    subject = subject.decode("utf-8", errors="ignore")
                
                from_addr = msg.get("From", "未知")
                date = msg.get("Date", "未知")
                
                # 获取正文
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            break
                else:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                
                mail.close()
                mail.logout()
                
                # 截取前 800 字
                preview = body[:800] + "..." if len(body) > 800 else body
                
                return f"""📧 **{subject}**

📅 日期: {date[:30]}
📧 发件人: {from_addr}

📝 内容:
{preview}

💡 需要我帮你回复或总结这封邮件吗？"""
            
            mail.close()
            mail.logout()
            return "❌ 读取失败"
            
        except Exception as e:
            return f"❌ 读取失败: {str(e)}"
    
    def search_emails(self, keyword: str, limit=10):
        """搜索邮件"""
        if not self.enabled:
            return "❌ 邮箱未配置"
        
        try:
            mail = self._connect_imap()
            mail.select("INBOX")
            
            result, data = mail.search(None, f'BODY "{keyword}"')
            email_ids = data[0].split()
            
            if not email_ids:
                mail.close()
                mail.logout()
                return f"📭 未找到包含「{keyword}」的邮件"
            
            emails = []
            for eid in email_ids[-limit:]:
                result, msg_data = mail.fetch(eid, "(RFC822)")
                if result == "OK":
                    msg = email.message_from_bytes(msg_data[0][1])
                    
                    subject = decode_header(msg.get("Subject", "无主题"))[0][0]
                    if isinstance(subject, bytes):
                        subject = subject.decode("utf-8", errors="ignore")
                    
                    from_addr = msg.get("From", "未知")
                    
                    emails.append({
                        "subject": subject[:60],
                        "from": from_addr[:50]
                    })
            
            mail.close()
            mail.logout()
            
            result = f"🔍 找到 {len(email_ids)} 封包含「{keyword}」的邮件:\n\n"
            for i, e in enumerate(emails, 1):
                result += f"  {i}. {e['subject']}\n     📧 {e['from']}\n\n"
            
            result += "💡 想看哪封邮件的详细内容？告诉我序号，比如「看第一封」"
            return result
            
        except Exception as e:
            return f"❌ 搜索失败: {str(e)}"
    
    def analyze_recent(self, days=7):
        """分析近期邮件"""
        if not self.enabled:
            return "❌ 邮箱未配置"
        
        try:
            mail = self._connect_imap()
            mail.select("INBOX")
            
            date_since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
            result, data = mail.search(None, f'SINCE "{date_since}"')
            email_ids = data[0].split()
            
            domains = []
            for eid in email_ids[-50:]:
                result, msg_data = mail.fetch(eid, "(RFC822)")
                if result == "OK":
                    msg = email.message_from_bytes(msg_data[0][1])
                    from_addr = msg.get("From", "")
                    domain_match = re.search(r'@([\w.-]+)', from_addr)
                    if domain_match:
                        domains.append(domain_match.group(1))
            
            mail.close()
            mail.logout()
            
            if not email_ids:
                return f"📭 最近 {days} 天没有新邮件"
            
            domain_counter = Counter(domains)
            top_domains = domain_counter.most_common(5)
            
            result = f"📊 最近 {days} 天邮件分析:\n"
            result += f"   📬 共收到 {len(email_ids)} 封邮件\n\n"
            result += "📧 发件人域名 Top 5:\n"
            for domain, count in top_domains:
                result += f"     • {domain}: {count} 封\n"
            
            # 分类统计
            edu_count = sum(1 for d in domains if 'edu' in d)
            com_count = sum(1 for d in domains if 'com' in d)
            
            result += f"\n📂 邮件类型:\n"
            result += f"     • 教育机构 (.edu): {edu_count} 封\n"
            result += f"     • 商业机构 (.com): {com_count} 封\n"
            
            return result
            
        except Exception as e:
            return f"❌ 分析失败: {str(e)}"
    
    def health_check(self):
        if not self.enabled:
            return {"status": "disabled", "message": "邮箱未配置"}
        try:
            mail = self._connect_imap()
            mail.select("INBOX")
            mail.close()
            mail.logout()
            return {"status": "healthy", "message": "邮箱连接正常"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


# 供 Bobo 调用的包装函数
def read_recent_tool(limit=5):
    email_mod = EmailModule()
    return email_mod.read_recent(limit)


def read_email_content_tool(index=1):
    email_mod = EmailModule()
    return email_mod.read_email_content(index)


def search_emails_tool(keyword: str):
    email_mod = EmailModule()
    return email_mod.search_emails(keyword)


def analyze_emails_tool(days=7):
    email_mod = EmailModule()
    return email_mod.analyze_recent(days)


if __name__ == "__main__":
    print("=" * 60)
    print("📧 邮箱模块完整测试")
    print("=" * 60)
    
    email_mod = EmailModule()
    
    print("\n1. 健康检查:")
    print(f"   {email_mod.health_check()}")
    
    print("\n2. 搜索邮件测试:")
    print(email_mod.search_emails("Python", 3))
    
    print("\n3. 读取邮件内容测试:")
    print(email_mod.read_email_content(1))
    
    print("\n✅ 测试完成")

# ============================================================
# 邮件隐私处理
# ============================================================

def is_sensitive_email(email_info: dict) -> bool:
    """判断邮件是否敏感（需要用户确认）"""
    sensitive_domains = ['gmail.com', '163.com', 'qq.com', 'outlook.com']
    from_addr = email_info.get('from', '').lower()
    
    # 个人邮箱域名
    for domain in sensitive_domains:
        if domain in from_addr:
            return True
    
    # 敏感关键词
    sensitive_keywords = ['密码', '验证码', '账单', 'invoice', 'password', 'verification']
    subject = email_info.get('subject', '').lower()
    for kw in sensitive_keywords:
        if kw in subject:
            return True
    
    return False


def process_emails_with_privacy(emails):
    """处理邮件，自动处理订阅，敏感邮件询问用户"""
    auto = []
    need_confirm = []
    
    for email in emails:
        if is_sensitive_email(email):
            need_confirm.append(email)
        else:
            auto.append(email)
    
    if need_confirm:
        print(f"\n⚠️ 发现 {len(need_confirm)} 封可能需要确认的邮件：")
        for i, e in enumerate(need_confirm, 1):
            print(f"   {i}. {e.get('from', '未知')}: {e.get('subject', '无主题')}")
        
        print(f"\n   [a] 全部处理")
        print(f"   [n] 全部跳过")
        print(f"   [1,2,3] 处理指定序号")
        choice = input("   请选择: ").strip()
        
        if choice.lower() == 'n':
            return auto
        elif choice.lower() == 'a':
            return auto + need_confirm
        else:
            try:
                indices = [int(x.strip())-1 for x in choice.split(',')]
                selected = [need_confirm[i] for i in indices if 0 <= i < len(need_confirm)]
                return auto + selected
            except Exception:
                return auto
    
    return auto


def register(reg):
    pass
