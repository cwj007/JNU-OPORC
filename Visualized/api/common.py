import re

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

def parse_keyword_expr(keyword_str: str, mode: str, table_alias: str = None, column_name: str = None) -> tuple:
    """
    Parses complex keyword expressions supporting '&' (AND), '|' (OR), and newline (OR group).
    Returns (sql_clause, params_list).
    """
    if not keyword_str:
        return "", []

    prefix = f"{table_alias}." if table_alias else ""
    
    def build_condition(term):
        term_wild = f"%{term}%"
        if mode == "simple" and column_name:
             return f"({prefix}{column_name} LIKE ?)", [term_wild]
        elif mode == "title":
            # For title mode, also check top_name if we have an alias (implies content table)
            if table_alias:
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
