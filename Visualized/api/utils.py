import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr, formatdate, make_msgid
from datetime import datetime
from . import config

import anyio

# 辅助函数：判断是否包含中文
def contains_chinese(text):
    if not text: return False
    return bool(re.search(r'[\u4e00-\u9fa5]', str(text)))

# 辅助函数：判断是否仅为数字或英文
def is_junk_label(text):
    if not text: return True
    s = str(text).strip().lower()
    if s in ['unknown', 'none', 'null', '', '控制']: return True
    # 如果不包含中文，且全是数字/英文/符号，则认为是无效标签
    if not contains_chinese(s):
        return True
    return False

def _send_email_sync(to_email: str, subject: str, content: str, level: str = "info", meta_data: dict = None, rule_name: str = None, username: str = "用户"):
    """同步发送邮件的内部函数"""
    if not config.SMTP_USER or not config.SMTP_PASSWORD:
        print("[Email] Skip sending: SMTP_USER or SMTP_PASSWORD not configured")
        return False

    try:
        # 创建邮件对象
        msg = MIMEMultipart("alternative")
        msg["From"] = formataddr((config.SMTP_FROM_NAME, config.SMTP_USER))
        msg["To"] = to_email
        
        # 优化主题：【舆情预警】[预警等级] 关于“[监测任务]”的舆情通知
        level_map = {
            "red": "红色预警",
            "orange": "橙色预警",
            "yellow": "黄色预警",
            "green": "蓝色预警",
            "high": "红色预警",
            "medium": "橙色预警",
            "low": "蓝色预警"
        }
        level_text = level_map.get(level.lower(), "常规预警")
        task_name = rule_name if rule_name else subject
        msg["Subject"] = Header(f"【舆情预警】[{level_text}] 关于“{task_name}”的舆情通知", "utf-8")
        
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()

        # HTML 内容
        level_colors = {
            "red": "#f5222d",
            "orange": "#fa8c16",
            "yellow": "#fadb14",
            "green": "#52c41a",
            "high": "#f5222d",
            "medium": "#fa8c16",
            "low": "#52c41a"
        }
        color = level_colors.get(level.lower(), "#1890ff")
        
        # 提取 meta_data 信息
        meta = meta_data or {}
        triggered_rule = meta.get('triggered_rule', '达到预设阈值条件')
        heat_summary = meta.get('heat_summary', f"当前已发现相关信息约 {meta.get('count', 'XX')} 条，声量仍在波动中。")
        core_focus = meta.get('core_focus', '用户对该话题的讨论热度持续上升。')
        possible_impact = meta.get('possible_impact', '可能对产品口碑或品牌形象造成一定影响。')
        suggested_actions = meta.get('suggested_actions', [
            "立即核实技术问题详情与影响范围。",
            "准备统一的对外解释或道歉口径。",
            "联系核心传播节点，控制信息扩散。"
        ])
        
        if isinstance(suggested_actions, str):
            suggested_actions = [suggested_actions]

        actions_html = "".join([f"<li>{action}</li>" for action in suggested_actions])

        html_content = f"""
        <html>
        <body style="font-family: 'Microsoft YaHei', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f4f7f9; padding: 20px;">
            <div style="max-width: 650px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <!-- Header -->
                <div style="background-color: {color}; color: white; padding: 30px 20px; text-align: center;">
                    <h1 style="margin: 0; font-size: 24px; letter-spacing: 2px;">舆情预警通知</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9; font-size: 16px;">{datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
                </div>
                
                <!-- Body -->
                <div style="padding: 30px 40px;">
                    <p style="font-size: 16px; font-weight: bold;">尊敬的{username}，您好：</p>
                    <p style="color: #666;">舆情监测系统发现您关注的议题已触发预设预警规则，具体信息如下：</p>
                    
                    <div style="margin: 25px 0; border-left: 4px solid {color}; padding-left: 20px;">
                        <p style="margin: 10px 0;"><strong style="color: #444; width: 80px; display: inline-block;">预警等级：</strong> <span style="color: {color}; font-weight: bold;">[{level_text}]</span></p>
                        <p style="margin: 10px 0;"><strong style="color: #444; width: 80px; display: inline-block;">预警任务：</strong> {task_name}</p>
                        <p style="margin: 10px 0;"><strong style="color: #444; width: 80px; display: inline-block;">触发规则：</strong> {triggered_rule}</p>
                        <p style="margin: 10px 0;"><strong style="color: #444; width: 80px; display: inline-block;">热度摘要：</strong> {heat_summary}</p>
                        <p style="margin: 10px 0;"><strong style="color: #444; width: 80px; display: inline-block;">核心焦点：</strong> {core_focus}</p>
                        <p style="margin: 10px 0;"><strong style="color: #444; width: 80px; display: inline-block;">可能影响：</strong> {possible_impact}</p>
                    </div>
                    
                    <div style="background-color: #fcf8f2; border: 1px solid #faebcc; border-radius: 4px; padding: 20px; margin-bottom: 25px;">
                        <h4 style="margin-top: 0; color: #8a6d3b;">建议措施：</h4>
                        <ul style="margin-bottom: 0; padding-left: 20px; color: #8a6d3b;">
                            {actions_html}
                        </ul>
                    </div>
                    
                    <div style="text-align: center; margin-top: 35px;">
                        <p style="color: #888; font-size: 14px; margin-bottom: 15px;">您可以：</p>
                        <a href="{config.BASE_URL if hasattr(config, 'BASE_URL') else 'http://your-system-url.com'}/warning" 
                           style="background-color: {color}; color: white; padding: 12px 30px; text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block;">
                           登录系统处理预警
                        </a>
                    </div>
                </div>
                
                <!-- Footer -->
                <div style="background-color: #f9f9f9; padding: 20px; text-align: center; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #999; margin: 0;">
                        此邮件由 <strong>舆情监测系统</strong> 自动发送，请勿直接回复。<br>
                        如果您有任何疑问，请联系系统管理员。
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # 添加纯文本和 HTML 部分
        msg.attach(MIMEText(content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        # 发送邮件
        if config.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT, timeout=30)
        else:
            server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT, timeout=30)
            server.starttls()
        
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print(f"[Email] Success: Sent to {to_email}")
        return True
    except Exception as e:
        print(f"[Email] Error sending to {to_email}: {e}")
        return False

async def send_email_notification(to_email: str, subject: str, content: str, level: str = "info", meta_data: dict = None, rule_name: str = None, username: str = "用户"):
    """异步发送邮件通知（在线程池中运行）"""
    return await anyio.to_thread.run_sync(
        _send_email_sync, to_email, subject, content, level, meta_data, rule_name, username
    )

