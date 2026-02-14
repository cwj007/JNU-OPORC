import requests
platforms = ['baidu', 'douyin', 'bilibili', 'hupu', 'thepaper', 'toutiao']
for p in platforms:
    try:
        url = f'https://newsnow.busiyi.world/api/v1/hotsearch/{p}'
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("success"):
            items = data.get("data") or []
            print(f"{p}: {len(items)} items")
            for i in items[:3]:
                print(f"  {i.get('title') or i.get('word')}")
        else:
            print(f"{p}: Failed {data.get('message')}")
    except Exception as e:
        print(f"{p}: Error {e}")
