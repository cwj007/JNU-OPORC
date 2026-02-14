import requests
platforms = ['baidu', 'douyin', 'bilibili', 'hupu', 'thepaper', 'toutiao']
for p in platforms:
    try:
        resp = requests.get(f'https://api.uapis.cn/api/hotlist?type={p}', timeout=10)
        data = resp.json()
        items = data.get('data') or data.get('list') or []
        print(f"{p}: {len(items)} items")
        for i in items[:3]:
            print(f"  {i.get('title') or i.get('word')}")
    except Exception as e:
        print(f"{p}: Error {e}")
