import json
import sqlite3
from pathlib import Path

# Paths
DB_PATH = Path(r'e:\JNU-OPORC\Visualized\cache\hotsearch.db')
TASKS_PATH = Path(r'e:\JNU-OPORC\Visualized\data\scheduler_tasks.json')

def migrate():
    # 1. Get user mapping from DB
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}")
        return
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    users = conn.execute('SELECT id, username FROM users').fetchall()
    username_to_id = {u['username']: str(u['id']) for u in users}
    conn.close()
    
    print(f"User mapping: {username_to_id}")

    # 2. Load tasks
    if not TASKS_PATH.exists():
        print(f"Tasks file not found at {TASKS_PATH}")
        return
        
    with open(TASKS_PATH, 'r', encoding='utf-8') as f:
        tasks = json.load(f)

    # 3. Migrate owners
    changed = False
    for task in tasks:
        owner = task.get('owner')
        if owner in username_to_id:
            new_owner = username_to_id[owner]
            print(f"Migrating task {task['id']}: {owner} -> {new_owner}")
            task['owner'] = new_owner
            # Also update visualized_user_id in crawler_config if it exists and matches
            if 'crawler_config' in task and task['crawler_config'].get('visualized_user_id') == owner:
                task['crawler_config']['visualized_user_id'] = new_owner
            changed = True
        elif owner.isdigit():
            # Already an ID, skip
            pass
        else:
            print(f"Warning: Unknown owner '{owner}' for task {task['id']}")

    # 4. Save tasks
    if changed:
        with open(TASKS_PATH, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
        print("Migration completed successfully.")
    else:
        print("No migration needed.")

if __name__ == "__main__":
    migrate()
