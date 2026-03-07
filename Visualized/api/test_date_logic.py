import sys
import os
from datetime import datetime, timedelta
import asyncio

# 确保能找到 api 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.common import build_date_filter

async def test_build_date_filter_24h():
    print("Testing build_date_filter for 24h dynamic window...")
    
    # 获取当前时间用于预期值对比
    now = datetime.now()
    expected_start = (now - timedelta(hours=23)).strftime("%Y-%m-%d %H:00:00")
    
    # 调用函数
    where_clauses, params = await build_date_filter(1, None, None, column_name="test_col")
    
    print(f"Where Clauses: {where_clauses}")
    print(f"Params: {params}")
    
    assert len(where_clauses) == 1
    assert "test_col >= ?" in where_clauses[0]
    assert params[0] == expected_start
    print("24h test passed!")

async def test_build_date_filter_range():
    print("\nTesting build_date_filter for date range...")
    start = "2024-01-01"
    end = "2024-01-02"
    
    where_clauses, params = await build_date_filter(0, start, end, column_name="test_col")
    
    print(f"Where Clauses: {where_clauses}")
    print(f"Params: {params}")
    
    assert len(where_clauses) == 1
    assert "test_col BETWEEN ? AND ?" in where_clauses[0]
    assert params[0] == "2024-01-01 00:00:00"
    assert params[1] == "2024-01-02 23:59:59"
    print("Range test passed!")

async def test_build_date_filter_single_day():
    print("\nTesting build_date_filter for single day...")
    day = "2024-01-01"
    
    where_clauses, params = await build_date_filter(0, day, day, column_name="test_col")
    
    print(f"Where Clauses: {where_clauses}")
    print(f"Params: {params}")
    
    assert len(where_clauses) == 1
    assert "test_col BETWEEN ? AND ?" in where_clauses[0]
    assert params[0] == "2024-01-01 00:00:00"
    assert params[1] == "2024-01-01 23:59:59"
    print("Single day test passed!")

if __name__ == "__main__":
    asyncio.run(test_build_date_filter_24h())
    asyncio.run(test_build_date_filter_range())
    asyncio.run(test_build_date_filter_single_day())
