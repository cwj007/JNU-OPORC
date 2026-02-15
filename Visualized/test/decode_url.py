
from urllib.parse import unquote

encoded_str = "%E6%83%85%E4%BA%BA%E8%8A%82"
decoded_str = unquote(encoded_str)
print(f"Encoded: {encoded_str}")
print(f"Decoded (top_id): {decoded_str}")
