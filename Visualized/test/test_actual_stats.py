
import sqlite3
import datetime

def test_actual_stats():
    conn = sqlite3.connect('Transformers/cache/processed_ids.db')
    conn.row_factory = sqlite3.Row
    
    # Simulate today as 2026-02-25
    # days = 7
    # start_date = 2026-02-19 00:00:00
    start_date_str = "2026-02-19 00:00:00"
    
    # Task 36 params
    task_id = 36
    task_keywords = "苏翊鸣"
    task_platforms = "weibo,zhihu"
    
    # Filter clauses
    keyword_clause = "(title LIKE ? OR content LIKE ? OR EXISTS (SELECT 1 FROM comments cm_sub WHERE cm_sub.note_id = content.note_id AND cm_sub.content LIKE ?))"
    platform_clause = "((source LIKE ? OR source LIKE ?) OR (source LIKE ? OR source LIKE ?))"
    
    full_filter = f"{keyword_clause} AND {platform_clause}"
    task_params = ["%苏翊鸣%", "%苏翊鸣%", "%苏翊鸣%", "%weibo%", "%微博%", "%zhihu%", "%知乎%"]
    
    # Query 1: Article count with date filter
    where_total_art = ["created_at >= ?"]
    params_total_art = [start_date_str]
    where_total_art.append(full_filter)
    params_total_art.extend(task_params)
    
    sql = f"SELECT COUNT(*) as count FROM content WHERE {' AND '.join(where_total_art)}"
    res = conn.execute(sql, params_total_art).fetchone()
    print(f"Article count (days=7, task=36): {res['count']}")
    
    # Query 2: Article count WITHOUT date filter
    where_only_task = [full_filter]
    params_only_task = task_params
    sql_no_date = f"SELECT COUNT(*) as count FROM content WHERE {' AND '.join(where_only_task)}"
    res_no_date = conn.execute(sql_no_date, params_only_task).fetchone()
    print(f"Article count (no date, task=36): {res_no_date['count']}")
    
    # Query 3: Article count with date filter BUT NO task filter
    where_only_date = ["created_at >= ?"]
    params_only_date = ["2026-02-01 00:00:00"] # All of Feb
    sql_date_only = f"SELECT COUNT(*) as count FROM content WHERE {' AND '.join(where_only_date)}"
    res_date_only = conn.execute(sql_date_only, params_only_date).fetchone()
    print(f"Article count (since 2026-02-01, NO task): {res_date_only['count']}")
    
    conn.close()

if __name__ == "__main__":
    test_actual_stats()
