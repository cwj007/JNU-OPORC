import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from Transformers.config import WEIBO_POSTS_FILE, WEIBO_COMMENTS_FILE, LABELED_DATA_FILE
from Transformers.models.vlm_handler import VLMHandler
from Transformers.processors.data_manager import DataManager
from Transformers.processors.multimodal_analyzer import MultimodalAnalyzer
from Transformers.processors.exporter import Exporter

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-modal Sentiment Analysis Pipeline")
    parser.add_argument("--weibo_posts", type=str, default=str(WEIBO_POSTS_FILE))
    parser.add_argument("--weibo_comments", type=str, default=str(WEIBO_COMMENTS_FILE))
    parser.add_argument("--json_file", type=str, help="Path to unlabelled JSON data")
    parser.add_argument("--limit", type=int, help="Limit number of items to process")
    
    args = parser.parse_args()
    
    # Load data
    print("Initializing components...")
    vlm = VLMHandler()
    analyzer = MultimodalAnalyzer(vlm)
    data_manager = DataManager()
    exporter = Exporter(LABELED_DATA_FILE)

    all_data = []
    if args.weibo_posts and args.weibo_comments:
        print(f"Loading Weibo data from {args.weibo_posts}...")
        weibo_data = data_manager.load_weibo_data(args.weibo_posts, args.weibo_comments)
        all_data.extend(weibo_data)

    if args.json_file:
        print(f"Loading JSON data from {args.json_file}...")
        json_data = data_manager.load_json_data(args.json_file)
        all_data.extend(json_data)

    if not all_data:
        print("No data loaded. Please check file paths.")
        sys.exit(1)

    # Apply limit if provided
    if args.limit:
        print(f"Limiting processing to first {args.limit} items.")
        all_data = all_data[:args.limit]

    # Process and Analyze
    print(f"Starting analysis for {len(all_data)} items...")
    if LABELED_DATA_FILE.exists():
        LABELED_DATA_FILE.unlink()
    
    analyzer.process_batch(all_data, exporter=exporter)
    print(f"Pipeline completed successfully. Results saved to {LABELED_DATA_FILE}")
