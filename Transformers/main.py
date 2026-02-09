import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from Transformers.config import WEIBO_POSTS_FILE, WEIBO_COMMENTS_FILE, LABELED_DATA_FILE, get_weibo_files_by_date, get_available_dates
from Transformers.models.vlm_handler import VLMHandler
from Transformers.processors.data_manager import DataManager
from Transformers.processors.multimodal_analyzer import MultimodalAnalyzer
from Transformers.processors.exporter import Exporter

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-modal Sentiment Analysis Pipeline")
    parser.add_argument("--date", type=str, help="Specify data date (YYYY-MM-DD)")
    parser.add_argument("--weibo_posts", type=str)
    parser.add_argument("--weibo_comments", type=str)
    parser.add_argument("--json_file", type=str, help="Path to unlabelled JSON data")
    parser.add_argument("--limit", type=int, help="Limit number of items to process")
    
    args = parser.parse_args()
    
    # Determine which files to load
    posts_file = args.weibo_posts or str(WEIBO_POSTS_FILE)
    comments_file = args.weibo_comments or str(WEIBO_COMMENTS_FILE)
    
    if args.date:
        p, c = get_weibo_files_by_date(args.date)
        if p.exists() and c.exists():
            posts_file, comments_file = str(p), str(c)
        else:
            print(f"Error: No data found for date {args.date}")
            sys.exit(1)

    # Load data
    print("Initializing components...")
    vlm = VLMHandler()
    analyzer = MultimodalAnalyzer(vlm)
    data_manager = DataManager()
    exporter = Exporter(LABELED_DATA_FILE)

    all_data = []
    if posts_file and comments_file:
        print(f"Loading Weibo data from {posts_file}...")
        weibo_data = data_manager.load_weibo_data(posts_file, comments_file)
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
