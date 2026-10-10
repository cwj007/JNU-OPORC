import sys
import os
from pathlib import Path

# 确保项目根目录在 sys.path 中
ROOT_DIR = Path(__file__).parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

def run_db_indexing():
    """运行数据库性能索引管理脚本"""
    print("=== 1. 正在管理数据库性能索引 ===")
    try:
        from Visualized.scripts.check_perf_indices import enable_wal, add_indices, HOTSEARCH_DB_PATH, TRANSFORMERS_DB_PATH, MEDIA_CRAWLER_DB_PATH
        for db in [HOTSEARCH_DB_PATH, TRANSFORMERS_DB_PATH, MEDIA_CRAWLER_DB_PATH]:
            enable_wal(db)
        add_indices()
    except ImportError as e:
        print(f"导入索引脚本失败: {e}")
    except Exception as e:
        print(f"执行性能索引管理失败: {e}")

def run_init_db():
    """初始化数据库结构、FTS 全文搜索和触发器"""
    print("\n=== 2. 正在初始化数据库结构与 FTS 全文搜索 ===")
    try:
        from Visualized.api.database import init_db
        init_db()
        print("数据库结构与 FTS 初始化完成。")
    except ImportError as e:
        print(f"导入数据库初始化模块失败: {e}")
    except Exception as e:
        print(f"执行数据库初始化失败: {e}")

def check_ignore_status():
    """检查代码索引忽略配置状态"""
    print("\n=== 3. 正在检查代码索引管理配置 (.ignore) ===")
    ignore_file = ROOT_DIR / ".trae" / ".ignore"
    if ignore_file.exists():
        print(f"找到索引忽略配置文件: {ignore_file}")
        # 简单读取行数作为状态反馈
        with open(ignore_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            print(f"当前配置行数: {len(lines)}")
    else:
        print("未找到 .trae/.ignore 文件，建议检查配置。")

def main():
    print("="*50)
    print("项目索引管理与维护工具 (Maintenance Tool)")
    print("="*50)
    
    # 1. 管理数据库索引
    run_db_indexing()
    
    # 2. 初始化/验证 FTS 和表结构
    run_init_db()
    
    # 3. 检查代码索引配置
    check_ignore_status()
    
    print("\n" + "="*50)
    print("所有索引管理任务执行完毕。")
    print("="*50)

if __name__ == "__main__":
    main()
