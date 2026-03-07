import re

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union

# Try to import PLATFORM_MAP from Transformers.config
try:
    from Transformers.config import PLATFORM_MAP
except ImportError:
    # Fallback if import fails
    PLATFORM_MAP = {
        "weibo": "微博",
        "zhihu": "知乎",
        "toutiao": "头条",
        "douyin": "抖音",
        "kuaishou": "快手",
        "bilibili": "B站",
        "xiaohongshu": "小红书"
    }

def parse_keyword_expr(keyword_str: str, mode: str, table_alias: str = None, column_name: str = None, use_fts: bool = False, check_top_name_column: bool = False) -> tuple:
    """
    Parses complex keyword expressions supporting '&' (AND), '|' (OR), and newline (OR group).
    Returns (sql_clause, params_list).
    
    Args:
        keyword_str: The raw keyword expression string
        mode: 'full', 'title', 'content', 'comment', or 'simple'
        table_alias: SQL table alias (e.g. 'c')
        column_name: Used for 'simple' mode
        use_fts: If True, uses FTS5 MATCH syntax for better performance
        check_top_name_column: If True, checks for a 'top_name' column in the table_alias directly
    """
    if not keyword_str:
        return "", []

    prefix = f"{table_alias}." if table_alias else ""
    
    def build_condition(term):
        term_wild = f"%{term}%"
        
        # FTS5 optimization: If use_fts is enabled and mode is suitable
        if use_fts and mode in ["full", "title", "content", "comment"]:
            if mode == "title":
                fts_query = f'title:"{term}"'
                if table_alias:
                    # Title search with FTS + fallback for top_name
                    if check_top_name_column:
                        return f"({prefix}rowid IN (SELECT rowid FROM content_fts WHERE {fts_query}) OR IFNULL({prefix}top_name, '') LIKE ?)", [term_wild]
                    return f"({prefix}rowid IN (SELECT rowid FROM content_fts WHERE {fts_query}) OR EXISTS (SELECT 1 FROM top_topics tt WHERE tt.top_id = {prefix}top_id AND tt.top_name LIKE ?))", [term_wild]
                return f"({prefix}rowid IN (SELECT rowid FROM content_fts WHERE {fts_query}))", []
            elif mode == "content":
                fts_query = f'content:"{term}"'
                return f"({prefix}rowid IN (SELECT rowid FROM content_fts WHERE {fts_query}))", []
            elif mode == "comment":
                fts_query = f'"{term}"'
                outer_ref = f"{prefix}note_id" if table_alias else "note_id"
                return f"EXISTS (SELECT 1 FROM comments cm_sub WHERE cm_sub.note_id = {outer_ref} AND cm_sub.rowid IN (SELECT rowid FROM comments_fts WHERE comments_fts MATCH ?))", [fts_query]
            else: # full
                fts_query = f'"{term}"'
                outer_ref = f"{prefix}note_id" if table_alias else "note_id"
                if table_alias:
                    if check_top_name_column:
                        return f"({prefix}rowid IN (SELECT rowid FROM content_fts WHERE content_fts MATCH ?) OR EXISTS (SELECT 1 FROM comments cm_sub WHERE cm_sub.note_id = {outer_ref} AND cm_sub.rowid IN (SELECT rowid FROM comments_fts WHERE comments_fts MATCH ?)) OR IFNULL({prefix}top_name, '') LIKE ?)", [fts_query, fts_query, term_wild]
                    return f"({prefix}rowid IN (SELECT rowid FROM content_fts WHERE content_fts MATCH ?) OR EXISTS (SELECT 1 FROM comments cm_sub WHERE cm_sub.note_id = {outer_ref} AND cm_sub.rowid IN (SELECT rowid FROM comments_fts WHERE comments_fts MATCH ?)) OR EXISTS (SELECT 1 FROM top_topics tt WHERE tt.top_id = {prefix}top_id AND tt.top_name LIKE ?))", [fts_query, fts_query, term_wild]
                return f"({prefix}rowid IN (SELECT rowid FROM content_fts WHERE content_fts MATCH ?) OR EXISTS (SELECT 1 FROM comments cm_sub WHERE cm_sub.note_id = {outer_ref} AND cm_sub.rowid IN (SELECT rowid FROM comments_fts WHERE comments_fts MATCH ?)))", [fts_query, fts_query]

        # Fallback to standard LIKE
        if mode == "simple" and column_name:
             return f"({prefix}{column_name} LIKE ?)", [term_wild]
        elif mode == "title":
            # For title mode, also check top_name if we have an alias (implies content table)
            if table_alias:
                # If check_top_name_column is true, only match against the pre-computed top_name column
                # This ensures the search range matches the displayed text (usually truncated to 20 chars)
                if check_top_name_column:
                    return f"(IFNULL({prefix}top_name, '') LIKE ?)", [term_wild]
                # Fallback to checking title and related top_topics table
                return f"({prefix}title LIKE ? OR EXISTS (SELECT 1 FROM top_topics tt WHERE tt.top_id = {prefix}top_id AND tt.top_name LIKE ?))", [term_wild, term_wild]
            return f"({prefix}title LIKE ?)", [term_wild]
        elif mode == "content":
            return f"({prefix}content LIKE ?)", [term_wild]
        elif mode == "comment":
            # For comment mode, we need to handle the subquery
            outer_ref = f"{prefix}note_id" if table_alias else "note_id"
            return f"EXISTS (SELECT 1 FROM comments cm_sub WHERE cm_sub.note_id = {outer_ref} AND cm_sub.content LIKE ?)", [term_wild]
        else: # full
            outer_ref = f"{prefix}note_id" if table_alias else "note_id"
            # 检查 title, content, 以及评论，以及 top_name (如果可能)
            if table_alias:
                # If check_top_name_column is true, only match against the pre-computed top_name column for the title part
                if check_top_name_column:
                    return f"({prefix}title LIKE ? OR {prefix}content LIKE ? OR EXISTS (SELECT 1 FROM comments cm_sub WHERE cm_sub.note_id = {outer_ref} AND cm_sub.content LIKE ?) OR IFNULL({prefix}top_name, '') LIKE ?)", [term_wild, term_wild, term_wild, term_wild]
                return f"({prefix}title LIKE ? OR {prefix}content LIKE ? OR EXISTS (SELECT 1 FROM comments cm_sub WHERE cm_sub.note_id = {outer_ref} AND cm_sub.content LIKE ?) OR EXISTS (SELECT 1 FROM top_topics tt WHERE tt.top_id = {prefix}top_id AND tt.top_name LIKE ?))", [term_wild, term_wild, term_wild, term_wild]
            return f"({prefix}title LIKE ? OR {prefix}content LIKE ? OR EXISTS (SELECT 1 FROM comments cm_sub WHERE cm_sub.note_id = {outer_ref} AND cm_sub.content LIKE ?))", [term_wild, term_wild, term_wild]

    groups = str(keyword_str).split('\n')
    group_clauses = []
    all_params = []
    
    for group in groups:
        if not group.strip(): continue
        # First, split by | for explicit OR
        explicit_or_terms = group.split('|')
        or_clauses = []
        for e_term in explicit_or_terms:
            if not e_term.strip(): continue
            
            # Within each term, we might have space-separated words which also mean OR
            # But we must preserve & groups
            # Let's normalize & by removing spaces around it
            normalized_term = re.sub(r'\s*&\s*', '&', e_term.strip())
            
            # Now split by space to get OR terms
            space_or_terms = normalized_term.split()
            
            for term in space_or_terms:
                if not term.strip(): continue
                # Split by & for AND
                and_terms = term.split('&')
                and_clauses = []
                for subterm in and_terms:
                    subterm = subterm.strip()
                    if not subterm: continue
                    clause, params = build_condition(subterm)
                    and_clauses.append(clause)
                    all_params.extend(params)
                
                if and_clauses:
                    if len(and_clauses) > 1:
                        or_clauses.append("(" + " AND ".join(and_clauses) + ")")
                    else:
                        or_clauses.append(and_clauses[0])
                    
        if or_clauses:
            if len(or_clauses) > 1:
                group_clauses.append("(" + " OR ".join(or_clauses) + ")")
            else:
                group_clauses.append(or_clauses[0])
                
    if not group_clauses:
        return "", []
        
    final_sql = "(" + " OR ".join(group_clauses) + ")"
    return final_sql, all_params

def parse_date_string(date_str: Optional[str]) -> Optional[str]:
    """
    Robustly parse date strings from frontend.
    Supports YYYY-MM-DD and JS Date.toString() format.
    Returns YYYY-MM-DD format.
    """
    if not date_str:
        return None
    
    # Try YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    
    # Try YYYY-MM-DD HH:MM:SS
    if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', date_str):
        return date_str[:10]
        
    # Try JS Date string: 'Sun Mar 01 2026 00:00:00 GMT+0800 (中国标准时间)'
    # We can use a simpler approach: if it contains a year and month, try to extract it.
    # Or just use dateutil if available, but let's stick to standard library.
    try:
        # Format like: Sun Mar 01 2026 ...
        # We can try parsing it with common JS formats
        # Removing timezone info in parentheses to help strptime
        clean_date = re.sub(r'\s*\(.*?\)', '', date_str)
        # JS dates often look like 'Sun Mar 01 2026 00:00:00 GMT+0800'
        # Let's try to extract YYYY-MM-DD using datetime.strptime
        # Many JS date strings match this:
        formats = [
            "%a %b %d %Y %H:%M:%S GMT%z",
            "%a %b %d %Y %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%fZ", # ISO format
            "%Y-%m-%d %H:%M:%S"
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(clean_date, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
                
        # Last resort: extract YYYY-MM-DD using regex if it's hidden in there
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str)
        if match:
            return match.group(0)
            
        # If it looks like 'Mar 01 2026', we can try to extract year, month, day
        # This is getting complex, but let's handle the most common JS toString() output
        # 'Sun Mar 01 2026 00:00:00 GMT+0800'
        parts = date_str.split()
        if len(parts) >= 4:
            # Mon, Month, Day, Year
            month_map = {
                'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
            }
            if parts[1] in month_map and parts[3].isdigit() and len(parts[3]) == 4:
                year = parts[3]
                month = month_map[parts[1]]
                day = parts[2].zfill(2)
                return f"{year}-{month}-{day}"
    except Exception:
        pass
        
    return date_str # Fallback

async def build_date_filter(days: Any, start_date: Optional[str], end_date: Optional[str], table_alias: str = None, column_name: str = "created_at"):
    """根据 days 或 start_date/end_date 构造 SQL 时间过滤条件"""
    start_date = parse_date_string(start_date)
    end_date = parse_date_string(end_date)
    
    alias = f"{table_alias}." if table_alias else ""
    full_col = f"{alias}{column_name}"
    where_clauses = []
    params = []
    
    if start_date:
        if end_date:
            if start_date == end_date:
                # 单日查询：00:00:00 到 23:59:59
                where_clauses.append(f"{full_col} BETWEEN ? AND ?")
                params.extend([f"{start_date} 00:00:00", f"{start_date} 23:59:59"])
            else:
                # 范围查询
                where_clauses.append(f"{full_col} BETWEEN ? AND ?")
                params.extend([f"{start_date} 00:00:00", f"{end_date} 23:59:59"])
        else:
            # 仅有 start_date: 从该时间开始到现在
            where_clauses.append(f"{full_col} >= ?")
            params.append(start_date)
    else:
        # 统一处理 days 参数，支持字符串和数字
        days_val = str(days) if days is not None else "1"
        
        now = datetime.now()
        if days_val in ["24h", "1"]:
            # 24小时动态窗口：从当前小时往前推 23 小时（补齐到整点）
            start_time = now - timedelta(hours=23)
            start_time_str = start_time.strftime("%Y-%m-%d %H:00:00")
            where_clauses.append(f"{full_col} >= ?")
            params.append(start_time_str)
        elif days_val in ["today", "0"]:
            # 今天：从今天 00:00:00 开始
            start_time_str = now.strftime("%Y-%m-%d 00:00:00")
            where_clauses.append(f"{full_col} >= ?")
            params.append(start_time_str)
        elif days_val in ["yesterday", "-1"]:
            # 昨天：昨天 00:00:00 到 昨天 23:59:59
            yesterday = now - timedelta(days=1)
            yesterday_str = yesterday.strftime("%Y-%m-%d")
            where_clauses.append(f"{full_col} BETWEEN ? AND ?")
            params.extend([f"{yesterday_str} 00:00:00", f"{yesterday_str} 23:59:59"])
        else:
            # 多日：3, 7, 15, 30 等
            try:
                # 兼容 "3d", "7d" 等格式
                if isinstance(days_val, str) and days_val.endswith('d'):
                    d_int = int(days_val[:-1])
                else:
                    d_int = int(days_val)
                
                # 从 N-1 天前的 00:00:00 开始
                start_date_str = (now - timedelta(days=d_int-1)).strftime("%Y-%m-%d") + " 00:00:00"
                where_clauses.append(f"{full_col} >= ?")
                params.append(start_date_str)
            except ValueError:
                # 默认回退到 24h
                start_time = now - timedelta(hours=23)
                start_time_str = start_time.strftime("%Y-%m-%d %H:00:00")
                where_clauses.append(f"{full_col} >= ?")
                params.append(start_time_str)
            
    return where_clauses, params
