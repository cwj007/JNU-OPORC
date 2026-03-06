
import json
import os
import sqlite3

cache_file = 'e:/JNU-OPORC/MediaCrawler/browser_data/cookies_cache.json'
db_path = 'e:/JNU-OPORC/Visualized/cache/hotsearch.db'

def fix_cache():
    if not os.path.exists(cache_file):
        print('No cache file')
        return

    with open(cache_file, 'r', encoding='utf-8') as f:
        cache = json.load(f)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    modified = False

    for platform, users in cache.items():
        new_users = {}
        for key, data in users.items():
            v_id = data.get('visualized_user_id')
            # 如果是未知用户，尝试从数据库补全
            if v_id and (data.get('user_id') == 'unknown' or data.get('user_name') == '未知用户'):
                cur.execute('SELECT username FROM users WHERE id = ?', (v_id,))
                row = cur.fetchone()
                if row:
                    sys_username = row[0]
                    if data.get('user_id') == 'unknown' or data.get('user_id').startswith('sys_'):
                        data['user_id'] = v_id
                    if data.get('user_name') == '未知用户':
                        data['user_name'] = sys_username
                    
                    # 更新缓存的 key
                    new_key = f"{data['user_id']}_{v_id}"
                    new_users[new_key] = data
                    modified = True
                    print(f"Fixed entry for visualized_user_id {v_id}: {sys_username}")
                else:
                    new_users[key] = data
            else:
                new_users[key] = data
        cache[platform] = new_users

    conn.close()

    if modified:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=4)
        print('Fixed cookies_cache.json')
    else:
        print('No changes needed')

if __name__ == '__main__':
    fix_cache()
