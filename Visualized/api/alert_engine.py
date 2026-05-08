import traceback
from datetime import datetime, timedelta
import os
import json
from pathlib import Path
from .database import query_db, execute_db, HOTSEARCH_DB_PATH, TRANSFORMERS_DB_PATH
from .risk_assessment import calculate_cri, check_veto_rules, get_dynamic_threshold, determine_level, get_sentiment_score
from .utils import send_email_notification

# 危机识别关键词
CRISIS_KEYWORDS = {
    "politics": ["政治", "政策", "政府", "领土", "外交", "主权", "敏感", "违禁"],
    "law": ["法律", "诉讼", "法院", "判决", "违法", "犯罪", "侵权", "官司", "律师"],
    "ethics": ["伦理", "道德", "歧视", "偏见", "骚扰", "霸凌", "虐待", "造假", "丑闻"]
}

class NotificationService:
    @staticmethod
    async def notify(method: str, title: str, content: str, level: str, reference_id: str = None, meta_data: dict = None, timestamp: str = None, rule_name: str = None, user_id: int = None, rule_id: int = None):
        methods = method.split(',')
        meta_str = json.dumps(meta_data) if meta_data else None
        
        # 确定用于去重的标识符
        # 对于非文章类的阈值告警，使用小时级时间戳防止短时间内重复发送
        log_reference_id = reference_id
        if not log_reference_id:
            log_reference_id = f"threshold_{datetime.now().strftime('%Y%m%d%H')}"

        for m in methods:
            m = m.strip().lower()
            
            # 针对用户特定的告警规则，检查是否已经发送过该类型的通知
            if user_id is not None and rule_id is not None:
                existing_log = await query_db(
                    "SELECT id FROM notifications_log WHERE user_id = ? AND rule_id = ? AND reference_id = ? AND type = ?",
                    (user_id, rule_id, log_reference_id, m),
                    one=True
                )
                if existing_log:
                    print(f"[Skip Notification] Already sent {m} notification for rule {rule_id} and reference {log_reference_id}")
                    continue

            if m == 'system':
                # 系统消息去重（基于 alerts 表，保持向后兼容）
                if reference_id:
                    # 改进去重逻辑：同一篇文章（reference_id）对于同一个用户，在一定时间内（例如24小时）只发送一个预警
                    # 除非是完全不同的标题（为了兼容风险等级变更等情况）
                    # 但对于“单贴高危预警”，我们希望它更严格地去重
                    
                    if user_id is not None:
                        # 检查是否已存在针对该用户的该文章预警
                        # 优先匹配标题完全一致的
                        existing = await query_db(
                            "SELECT id, title FROM alerts WHERE reference_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1", 
                            (reference_id, user_id), 
                            one=True
                        )
                    else:
                        existing = await query_db(
                            "SELECT id, title FROM alerts WHERE reference_id = ? AND user_id IS NULL ORDER BY id DESC LIMIT 1", 
                            (reference_id,), 
                            one=True
                        )
                    
                    if existing:
                        # 如果标题完全一致，或者是“单贴高危预警”且已经存在任何类型的预警，则跳过
                        if existing['title'] == title:
                            print(f"[Skip System Msg] Exact duplicate alert for {reference_id}")
                            continue
                        
                        # 如果当前是“单贴高危预警”，且已经有其他类型的预警了，通常不需要再发
                        if "单贴高危" in title or "单贴高危" in existing['title']:
                            print(f"[Skip System Msg] Redundant article-level alert for {reference_id} (Existing: {existing['title']})")
                            continue
                
                await NotificationService._send_system_msg(title, content, level, reference_id, meta_str, timestamp, rule_name, user_id)
                
                # 记录通知日志
                if user_id is not None and rule_id is not None:
                    await execute_db(
                        "INSERT OR IGNORE INTO notifications_log (user_id, rule_id, reference_id, type) VALUES (?, ?, ?, ?)",
                        (user_id, rule_id, log_reference_id, 'system')
                    )

            elif m == 'email':
                success = await NotificationService._send_email(title, content, level, user_id, meta_data=meta_data, rule_name=rule_name)
                if success and user_id is not None and rule_id is not None:
                    # 获取用户邮箱地址作为 target 记录
                    user_info = await query_db("SELECT email FROM users WHERE id = ?", (user_id,), one=True)
                    target = user_info['email'] if user_info else None
                    await execute_db(
                        "INSERT OR IGNORE INTO notifications_log (user_id, rule_id, reference_id, type, target) VALUES (?, ?, ?, ?, ?)",
                        (user_id, rule_id, log_reference_id, 'email', target)
                    )

    @staticmethod
    async def _send_system_msg(title: str, content: str, level: str, reference_id: str = None, meta_data: str = None, timestamp: str = None, rule_name: str = None, user_id: int = None):
        """发送站内信"""
        # If rule_name is provided, use it as 'type', otherwise default to 'system'
        alert_type = rule_name if rule_name else 'system'
        
        # New field: alerts_time (current detection time)
        alerts_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            if timestamp:
                sql = """
                    INSERT INTO alerts (level, title, content, status, type, reference_id, meta_data, time, alerts_time, user_id) 
                    VALUES (?, ?, ?, 'unread', ?, ?, ?, ?, ?, ?)
                """
                await execute_db(sql, (level, title, content, alert_type, reference_id, meta_data, timestamp, alerts_time, user_id))
            else:
                sql = """
                    INSERT INTO alerts (level, title, content, status, type, reference_id, meta_data, alerts_time, user_id) 
                    VALUES (?, ?, ?, 'unread', ?, ?, ?, ?, ?)
                """
                await execute_db(sql, (level, title, content, alert_type, reference_id, meta_data, alerts_time, user_id))
                
            print(f"[System Notification] {level.upper()}: {title} (Rule: {alert_type}, User: {user_id})")
            return True
        except Exception as e:
            # Fallback for old schema or error
            print(f"Error inserting alert with user_id: {e}")
            return False

    @staticmethod
    async def _send_email(title: str, content: str, level: str, user_id: int = None, meta_data: dict = None, rule_name: str = None):
        """发送邮件"""
        user_info = None
        if user_id is None:
            # 如果没有指定用户，默认发给管理员
            user_info = await query_db("SELECT username, email, email_notify_enabled FROM users WHERE role = 'admin' LIMIT 1", one=True)
        else:
            # 查找指定用户的邮箱设置
            user_info = await query_db("SELECT username, email, email_notify_enabled FROM users WHERE id = ?", (user_id,), one=True)

        if user_info and user_info['email'] and user_info['email_notify_enabled']:
            return await send_email_notification(
                user_info['email'], 
                title, 
                content, 
                level, 
                meta_data=meta_data, 
                rule_name=rule_name,
                username=user_info['username']
            )
        else:
            print(f"[Email Notification Skip] User {user_id if user_id else 'Admin'} has no email or disabled notifications")
            return False

class AlertEngine:
    def __init__(self):
        self.rules = []
        self._article_cache = {} # time_window -> articles
        self._comment_cache = {} # note_id -> comments
        self._cri_cache = {} # note_id -> (cri, details)

    async def _get_articles(self, start_time: str, time_window: int):
        """获取文章（带缓存）"""
        cache_key = f"{start_time}_{time_window}"
        if cache_key in self._article_cache:
            return self._article_cache[cache_key]
        
        sql = "SELECT * FROM content WHERE created_at >= ?"
        articles = await query_db(sql, (start_time,))
        results = [dict(a) for a in articles] if articles else []
        self._article_cache[cache_key] = results
        return results

    async def _get_comments(self, note_id: str):
        """获取评论（带缓存）"""
        if note_id in self._comment_cache:
            return self._comment_cache[note_id]
        
        c_sql = "SELECT * FROM comments WHERE note_id = ?"
        comments = await query_db(c_sql, (note_id,))
        results = [dict(c) for c in comments] if comments else []
        self._comment_cache[note_id] = results
        return results

    async def load_rules(self):
        """加载所有启用的预警规则"""
        sql = "SELECT * FROM alert_rules WHERE is_active = 1"
        results = await query_db(sql)
        self.rules = [dict(row) for row in results] if results else []

    async def run_check(self, override_days: int = None):
        """
        执行预警检查
        override_days: 如果提供，强制检查过去 N 天内的文章（覆盖规则配置的 time_window）
        """
        # 每一轮检查清空缓存
        self._article_cache = {}
        self._comment_cache = {}
        self._cri_cache = {}

        await self.load_rules()
        for rule in self.rules:
            try:
                # 复制规则，以免影响原配置
                current_rule = rule.copy()
                if override_days:
                    # 将天数转换为小时
                    current_rule['time_window'] = override_days * 24
                
                if current_rule.get('rule_type') == 'cri_trend':
                    await self._check_cri_rule(current_rule)
                elif current_rule.get('rule_type') == 'article_burst':
                    await self._check_article_burst_rule(current_rule)
                else:
                    await self._check_threshold_rule(current_rule)
            except Exception as e:
                print(f"Error checking rule {rule.get('name')}: {e}")
                traceback.print_exc()

    async def _check_article_burst_rule(self, rule: dict):
        """
        Check for high negative engagement on individual articles
        Logic: Article is Negative (or High Negative Score) AND (Total Comments > X OR Negative Comments > Y)
        """
        config = json.loads(rule.get('config', '{}')) if rule.get('config') else {}
        min_comments = config.get('min_comments', 20)
        min_negative_comments = config.get('min_negative_comments', 10)
        
        # Override time window if set in rule (e.g. from generate_auto_alerts override)
        time_window = rule.get('time_window', 24)
        start_time = (datetime.now() - timedelta(hours=time_window)).strftime("%Y-%m-%d %H:%M:%S")

        # 1. Fetch recent articles (cached)
        articles = await self._get_articles(start_time, time_window)
        
        if not articles:
            return

        for article_dict in articles:
            # 预检：如果该文章已经由该规则发送过通知，则跳过
            note_id = article_dict['note_id']
            user_id = rule.get('user_id')
            rule_id = rule.get('id')
            
            if user_id is not None and rule_id is not None:
                # 检查 notifications_log
                existing = await query_db(
                    "SELECT id FROM notifications_log WHERE user_id = ? AND rule_id = ? AND reference_id = ?",
                    (user_id, rule_id, str(note_id)),
                    one=True
                )
                if existing:
                    continue

            # Check article sentiment first
            sentiment_val = article_dict.get('sentiment', '')
            score = get_sentiment_score(sentiment_val) if get_sentiment_score else 0.5
            
            # If strictly neutral/positive, skip
            is_article_negative = (sentiment_val == '负面') or (score >= 0.6)
            
            if not is_article_negative:
                continue

            # 2. Fetch comments (cached)
            comments_list = await self._get_comments(note_id)
            
            total_comments = len(comments_list)
            
            # 3. Filter negative comments
            negative_comments = []
            for c in comments_list:
                # Use sentiment label or calculate score
                is_negative = False
                c_sentiment = c.get('sentiment', '')
                if c_sentiment == '负面':
                    is_negative = True
                elif get_sentiment_score and get_sentiment_score(c_sentiment) >= 0.6:
                    is_negative = True
                
                if is_negative:
                    negative_comments.append(c)
            
            neg_count = len(negative_comments)
            
            # 4. Check Thresholds
            if total_comments >= min_comments and neg_count >= min_negative_comments:
                # Trigger Alert
                title = f"【单贴高危预警】{article_dict['title'][:20]}..."
                
                article_snippet = article_dict['content'][:200] + "..." if article_dict.get('content') else ""
                stats_info = f" [评论激增: 总{total_comments}/负{neg_count}]"
                content = article_snippet + stats_info
                
                # Use cached CRI if available (with custom config if provided)
                config_str = json.dumps(config, sort_keys=True)
                cri_cache_key = f"{note_id}_{config_str}"
                if cri_cache_key in self._cri_cache:
                    cri, details_cri = self._cri_cache[cri_cache_key]
                else:
                    cri, details_cri = calculate_cri(article_dict, comments_list, config)
                    self._cri_cache[cri_cache_key] = (cri, details_cri)
                
                # Prepare details for frontend
                details = details_cri.copy() if details_cri else {}
                details.update({
                    'article_title': article_dict['title'],
                    'article_content': article_dict.get('content', ''),
                    'article_id': article_dict['note_id'],
                    'total_comments': total_comments,
                    'negative_comments_count': neg_count,
                    'top_negative_comments': [],
                    'alert_type': 'article_burst',
                    'publish_time': article_dict.get('created_at'),
                    'cri': cri
                })
                
                # Sort negative comments by sentiment score
                try:
                    for c in negative_comments:
                        if 'score' not in c:
                            c['score'] = get_sentiment_score(c.get('sentiment', '')) if get_sentiment_score else 0
                    
                    negative_comments.sort(key=lambda x: x.get('score', 0), reverse=True)
                except Exception as e:
                    print(f"Error sorting comments: {e}")
                
                # Format for frontend - Limit to top 50 comments to reduce DB size
                for c in negative_comments[:50]: 
                    details['top_negative_comments'].append({
                        'content': c['content'],
                        'sentiment': c.get('sentiment', '负面'),
                        'score': c.get('score', 0),
                        'created_at': c['created_at']
                    })
                
                await NotificationService.notify(
                    rule['notify_methods'], 
                    title, 
                    content, 
                    "high", # Force high level for burst
                    str(note_id), 
                    details,
                    timestamp=article_dict.get('created_at'),
                    rule_name=rule['name'],
                    user_id=rule.get('user_id'),
                    rule_id=rule.get('id')
                )

    async def _check_cri_rule(self, rule: dict):
        """
        Check Article Comprehensive Risk Index (CRI)
        """
        config = json.loads(rule['config']) if rule.get('config') else {}
        
        # Override time window if requested, else use rule config
        time_window = rule.get('time_window', 24)
        
        # Calculate start time for article scanning
        start_time = (datetime.now() - timedelta(hours=time_window)).strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. Fetch recent articles (cached)
        articles = await self._get_articles(start_time, time_window)
        
        if not articles:
            return

        for article_dict in articles:
            note_id = article_dict['note_id']
            user_id = rule.get('user_id')
            rule_id = rule.get('id')
            
            # 预检：如果该文章已经由该规则发送过通知，则跳过
            if user_id is not None and rule_id is not None:
                existing = await query_db(
                    "SELECT id FROM notifications_log WHERE user_id = ? AND rule_id = ? AND reference_id = ?",
                    (user_id, rule_id, str(note_id)),
                    one=True
                )
                if existing:
                    continue

            # 2. Fetch comments (cached)
            comments_list = await self._get_comments(note_id)
            
            # 3. Calculate CRI (cached by note_id and weights)
            weights = config.get('weights', {})
            custom_keywords = config.get('sensitive_words', {})
            custom_thresholds = config.get('risk_thresholds', {})
            
            weights_str = json.dumps(weights, sort_keys=True)
            # 缓存键也需要包含敏感词和阈值的变化，为了简单起见，如果配置变了就清空缓存
            # 或者将整个 config 序列化作为缓存键的一部分
            config_str = json.dumps(config, sort_keys=True)
            cri_cache_key = f"{note_id}_{config_str}"
            
            if cri_cache_key in self._cri_cache:
                cri, details_cri = self._cri_cache[cri_cache_key]
            else:
                cri, details_cri = calculate_cri(article_dict, comments_list, config)
                self._cri_cache[cri_cache_key] = (cri, details_cri)
            
            # --- Enrich details for frontend display ---
            details = details_cri.copy() if details_cri else {}
            details['article_title'] = article_dict.get('title', '')
            details['article_content'] = article_dict.get('content', '')
            details['article_id'] = article_dict['note_id']
            details['publish_time'] = article_dict['created_at']
            
            # Extract top negative comments for display
            neg_comments_list = []
            for c in comments_list:
                try:
                    if 'score' not in c:
                        c['score'] = get_sentiment_score(c.get('sentiment'))
                    
                    if c['score'] >= 0.6: 
                        neg_comments_list.append({
                            'content': c['content'],
                            'sentiment': c.get('sentiment', '负面'),
                            'score': c['score'],
                            'created_at': c['created_at']
                        })
                except Exception:
                    pass
            
            # Sort by score descending and limit to top 50
            neg_comments_list.sort(key=lambda x: x['score'], reverse=True)
            details['top_negative_comments'] = neg_comments_list[:50]
            
            # 4. Check Veto Rules (Highest Priority)
            veto_triggered, veto_reason, veto_level = check_veto_rules(article_dict, comments_list, details, custom_keywords=custom_keywords)
            
            if veto_triggered:
                title = f"【严重风险预警】{article_dict.get('title', '')[:20]}..."
                # Content now stores the article snippet for direct display in the list
                article_snippet = article_dict.get('content', '')[:200] + "..." if article_dict.get('content') else ""
                stats_info = f" [触发规则: {veto_reason}]"
                content = article_snippet + stats_info
                
                # Add veto info to details
                details['alert_reason'] = veto_reason
                details['alert_type'] = 'veto'
                
                await NotificationService.notify(
                    rule['notify_methods'], 
                    title, 
                    content, 
                    veto_level, # Usually 'red'
                    str(note_id), 
                    details, 
                    timestamp=article_dict.get('created_at'),
                    rule_name=rule['name'],
                    user_id=rule.get('user_id'),
                    rule_id=rule.get('id')
                )
                continue # Skip CRI level check if veto triggered
            
            # 6. Dynamic Threshold Check
            # Get baseline stats (using default for now as we don't have historical stats DB yet)
            mu, sigma = get_dynamic_threshold() 
            level_color, level_desc = determine_level(cri, mu, sigma, custom_thresholds=custom_thresholds)
            
            # Only alert if risk is significant (Yellow/Orange/Red)
            # Green (Normal) is ignored to reduce noise
            if level_color != "green":
                title = f"【综合风险预警-{level_desc}】{article_dict.get('title', '')[:20]}..."
                
                # Content now stores the article snippet for direct display in the list
                article_snippet = article_dict.get('content', '')[:200] + "..." if article_dict.get('content') else ""
                stats_info = f" [CRI: {cri:.2f}/{mu+sigma:.2f} ({level_desc})]"
                content = article_snippet + stats_info
                
                # Add threshold info to details
                details['threshold_mean'] = round(mu, 2)
                details['threshold_stdev'] = round(sigma, 2)
                details['level_desc'] = level_desc
                details['cri_score'] = round(cri, 2)
                details['alert_type'] = 'cri'
                
                await NotificationService.notify(
                    rule['notify_methods'], 
                    title, 
                    content, 
                    level_color, 
                    str(note_id), 
                    details,
                    timestamp=article_dict.get('created_at'),
                    rule_name=rule['name'],
                    user_id=rule.get('user_id'),
                    rule_id=rule.get('id')
                )

    async def _check_threshold_rule(self, rule: dict):
        """检查单条规则是否触发 (Legacy Threshold Logic)"""
        config = json.loads(rule.get('config', '{}')) if rule.get('config') else {}
        custom_keywords = config.get('sensitive_words', {})
        
        time_window = rule['time_window']
        threshold = rule['threshold']
        keyword = rule['keyword']
        sentiment = rule['sentiment']
        is_crisis = rule['is_crisis']
        
        # 计算起始时间
        start_time = (datetime.now() - timedelta(hours=time_window)).strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. 基础条件查询 (情绪 + 关键词 + 时间)
        query = "SELECT COUNT(*) as count FROM content WHERE sentiment = ? AND created_at >= ?"
        params = [sentiment, start_time]
        
        if keyword:
            query += " AND content LIKE ?"
            params.append(f"%{keyword}%")
            
        res = await query_db(query, tuple(params), one=True)
        count = res['count'] if res else 0
        
        triggered = False
        reason = ""
        
        # 阈值触发
        if count >= threshold:
            triggered = True
            # Format time window description
            time_desc = f"{time_window}小时"
            if time_window >= 24:
                days = time_window // 24
                time_desc = f"{days}天"
            if time_window >= 720: # Special case for long history scan
                time_desc = "历史周期"
                
            reason = f"在过去 {time_desc} 内，累计检测到 {count} 条{sentiment}舆情，达到阈值 {threshold}。"
            
        # 2. 危机识别触发 (如果是危机规则)
        if is_crisis:
            # 搜索所有危机关键词
            # 使用自定义关键词或默认关键词
            active_keywords = {}
            for category in ["politics", "law", "ethics"]:
                active_keywords[category] = custom_keywords.get(category, CRISIS_KEYWORDS[category])
            
            all_crisis_kws = [kw for sub in active_keywords.values() for kw in sub]
            crisis_found = False
            found_kws = []
            
            # 这里的查询可能会比较重，实际生产环境建议索引优化或使用全文检索
            for kw in all_crisis_kws:
                crisis_query = "SELECT COUNT(*) as count FROM content WHERE (content LIKE ? OR title LIKE ?) AND created_at >= ?"
                c_res = await query_db(crisis_query, (f"%{kw}%", f"%{kw}%", start_time), one=True)
                if c_res and c_res['count'] > 0:
                    crisis_found = True
                    found_kws.append(kw)
            
            if crisis_found:
                triggered = True
                level = "high"
                title = f"【危机预警】{rule['name']}"
                content = f"检测到涉及敏感领域({', '.join(found_kws)})的内容。触发规则: {rule['name']}。"
                # 尝试查找触发危机词的具体文章
                try:
                    crisis_article_sql = "SELECT title FROM content WHERE (content LIKE ? OR title LIKE ?) AND created_at >= ? LIMIT 1"
                    # Use the first found keyword for title lookup
                    kw = found_kws[0]
                    ca_res = await query_db(crisis_article_sql, (f"%{kw}%", f"%{kw}%", start_time), one=True)
                    if ca_res:
                        ca_res = dict(ca_res)
                        if ca_res.get('title'):
                            title = f"【危机预警】{ca_res['title'][:20]}..."
                            content = f"检测到涉及敏感领域({', '.join(found_kws)})的内容。文章: {ca_res['title']}。触发规则: {rule['name']}。"
                except Exception as e:
                    print(f"Error fetching crisis article title: {e}")
                
                # --- Fetch details for crisis alert ---
                details = {"type": "crisis_list", "keywords": found_kws, "articles": [], "count": count}
                try:
                    # Fetch top 5 crisis articles
                    kw = found_kws[0]
                    # Note: simplified to first keyword for now
                    c_articles_sql = "SELECT * FROM content WHERE (content LIKE ? OR title LIKE ?) AND created_at >= ? ORDER BY created_at DESC LIMIT 5"
                    c_articles = await query_db(c_articles_sql, (f"%{kw}%", f"%{kw}%", start_time))
                    if c_articles:
                        c_articles = [dict(row) for row in c_articles]
                        for art in c_articles:
                            art_info = {
                                "title": art.get('title', ''),
                                "content": art.get('content', '')[:200] + "..." if art.get('content') else "",
                                "note_id": art['note_id'],
                                "created_at": art['created_at'],
                                "comments": []
                            }
                            # Fetch top comments for this article
                            cm_sql = "SELECT * FROM comments WHERE note_id = ? ORDER BY created_at DESC LIMIT 3"
                            cms = await query_db(cm_sql, (art['note_id'],))
                            if cms:
                                cms = [dict(c) for c in cms]
                                for c in cms:
                                    art_info['comments'].append({
                                        "content": c.get('content', ''),
                                        "sentiment": c.get('sentiment', ''),
                                        "created_at": c['created_at']
                                    })
                            details['articles'].append(art_info)
                except Exception as e:
                    print(f"Error fetching crisis details: {e}")

                await NotificationService.notify(
                    rule['notify_methods'], 
                    title, 
                    content, 
                    level, 
                    meta_data=details,
                    rule_name=rule['name'],
                    user_id=rule.get('user_id'),
                    rule_id=rule.get('id')
                )
                return # 危机预警优先处理

        if triggered:
            # New Logic: One alert per article
            try:
                # Fetch ALL matching articles
                article_sql = "SELECT * FROM content WHERE sentiment = ? AND created_at >= ? ORDER BY created_at DESC"
                params = [sentiment, start_time]
                if keyword:
                    article_sql = "SELECT * FROM content WHERE sentiment = ? AND content LIKE ? AND created_at >= ? ORDER BY created_at DESC"
                    params = [sentiment, f"%{keyword}%", start_time]
                
                articles = await query_db(article_sql, tuple(params))
                articles = [dict(row) for row in articles] if articles else []

                for art in articles:
                    # Construct Title
                    art_title = art.get('title', '')
                    if not art_title:
                         art_title = art.get('content', '')[:20].replace('\n', ' ') + "..." if art.get('content') else "无标题内容"
                    
                    # Fetch Comments (needed for Veto/CRI check)
                    cm_sql = "SELECT * FROM comments WHERE note_id = ? ORDER BY created_at DESC LIMIT 50"
                    cms = await query_db(cm_sql, (art['note_id'],))
                    comments_list = [dict(c) for c in cms] if cms else []

                    # Calculate CRI for this article
                    cri, details_cri = calculate_cri(art, comments_list, config)
                    
                    # Check Veto Rules (Highest Priority)
                    veto_triggered, veto_reason, veto_level = check_veto_rules(art, comments_list, custom_keywords=custom_keywords)
                    
                    if veto_triggered:
                        alert_level = veto_level
                        alert_title = f"【严重风险预警】{art_title}"
                        alert_content = f"{art.get('content', '')[:200]}... [触发规则: {veto_reason}]"
                        meta_data = {
                            "type": "veto",
                            "article": {
                                "title": art_title,
                                "content": art.get('content', ''),
                                "note_id": art['note_id'],
                                "created_at": art['created_at'],
                                "comments": []
                            },
                            "alert_reason": veto_reason,
                            "count": count,
                            "cri": cri,
                            "metrics": details_cri
                        }
                    else:
                        alert_title = f"【敏感内容】{art_title}"
                        alert_content = art.get('content', '')[:200] + "..." if art.get('content') else "无内容"
                        alert_level = "medium"
                        
                        meta_data = {
                            "type": "single_article",
                            "article": {
                                "title": art_title,
                                "content": art.get('content', ''),
                                "note_id": art['note_id'],
                                "created_at": art['created_at'],
                                "comments": []
                            },
                            "count": count,
                            "cri": cri,
                            "metrics": details_cri
                        }

                    # Add comments to meta_data
                    for c in comments_list[:20]: # Limit to 20 for display
                         meta_data['article']['comments'].append({
                            "content": c.get('content', ''),
                            "sentiment": c.get('sentiment', ''),
                            "created_at": c['created_at']
                         })

                    # Notify (Idempotent)
                    await NotificationService.notify(
                        rule['notify_methods'], 
                        alert_title, 
                        alert_content, 
                        alert_level, 
                        reference_id=str(art['note_id']), 
                        meta_data=meta_data,
                        timestamp=art['created_at'],
                        rule_name=rule['name'],
                        user_id=rule.get('user_id'),
                        rule_id=rule.get('id')
                    )

            except Exception as e:
                print(f"Error processing individual alerts: {e}")

async def run_alert_engine():
    """便捷启动函数"""
    engine = AlertEngine()
    await engine.run_check()

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_alert_engine())
