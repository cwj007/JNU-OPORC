import requests
try:
    r = requests.get('http://127.0.0.1:8001/api/hotsearch/all')
    data = r.json()
    platform = data[0]
    items = platform['data']
    if items:
        item = items[0]
        print(f"Platform: {platform['name']}")
        print(f"Item Title: {item['title']}")
        print(f"Trend exists: {'trend' in item}")
        print(f"Trend value: {item.get('trend')}")
    else:
        print("No items found")
except Exception as e:
    print(f"Error: {e}")
