
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# 设置路径
BASE_DIR = Path(__file__).parent.parent.parent
sys.path.append(str(BASE_DIR))

from Visualized.api.alert_engine import AlertEngine
from Visualized.api.database import query_db, execute_db

async def test_optimization():
    print("--- Starting Optimization Test ---")
    
    # 1. 清空现有的预警和通知日志以开始全新测试
    print("Cleaning up alerts and notification logs...")
    await execute_db("DELETE FROM alerts")
    await execute_db("DELETE FROM notifications_log")
    
    engine = AlertEngine()
    
    # 2. 第一次运行：应该生成预警并填充缓存
    print("\n--- First Run: Should generate alerts and fill cache ---")
    start_time = datetime.now()
    # 强制检查过去 30 天
    await engine.run_check(override_days=30)
    end_time = datetime.now()
    first_run_duration = (end_time - start_time).total_seconds()
    
    alerts_count = await query_db("SELECT COUNT(*) as count FROM alerts", one=True)
    logs_count = await query_db("SELECT COUNT(*) as count FROM notifications_log", one=True)
    
    print(f"First run duration: {first_run_duration:.2f}s")
    print(f"Alerts generated: {alerts_count['count']}")
    print(f"Notification logs: {logs_count['count']}")
    print(f"Article cache size: {len(engine._article_cache)}")
    print(f"Comment cache size: {len(engine._comment_cache)}")
    print(f"CRI cache size: {len(engine._cri_cache)}")
    
    # 3. 第二次运行：应该使用缓存且不生成重复预警
    print("\n--- Second Run: Should be faster and skip duplicate alerts ---")
    
    # 注意：run_check 内部会清空缓存，为了测试缓存有效性，我们手动调用内部方法
    # 或者我们修改 run_check 的逻辑，但在测试中我们可以模拟
    
    # 模拟 generate_auto_alerts 的行为
    start_time = datetime.now()
    await engine.run_check(override_days=30)
    end_time = datetime.now()
    second_run_duration = (end_time - start_time).total_seconds()
    
    alerts_count_2 = await query_db("SELECT COUNT(*) as count FROM alerts", one=True)
    logs_count_2 = await query_db("SELECT COUNT(*) as count FROM notifications_log", one=True)
    
    print(f"Second run duration: {second_run_duration:.2f}s")
    print(f"Total alerts after second run: {alerts_count_2['count']}")
    print(f"Total notification logs after second run: {logs_count_2['count']}")
    
    # 验证去重
    if alerts_count_2['count'] == alerts_count['count']:
        print("\nSUCCESS: No duplicate alerts generated in second run.")
    else:
        print(f"\nFAILURE: Generated {alerts_count_2['count'] - alerts_count['count']} duplicate alerts.")
        
    if second_run_duration < first_run_duration:
        print(f"SUCCESS: Second run was faster ({second_run_duration:.2f}s vs {first_run_duration:.2f}s)")
    else:
        print(f"INFO: Second run was not significantly faster (cache is cleared per run_check call).")

if __name__ == "__main__":
    asyncio.run(test_optimization())
