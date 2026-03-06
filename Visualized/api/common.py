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
