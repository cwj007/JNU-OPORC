
path = r"e:\JNU-OPORC\MediaCrawler\api\webui\assets\index-DvClRayq.js"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

index = content.find("8080")
if index != -1:
    print(f"Found at {index}")
    print(content[index-50:index+50])
else:
    print("Not found")
