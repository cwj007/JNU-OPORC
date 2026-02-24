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
from Transformers import utils

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-modal Sentiment Analysis Pipeline")
    parser.add_argument("--date", type=str, help="Specify data date (YYYY-MM-DD)")
    parser.add_argument("--platform", type=str, choices=["weibo", "zhihu"], help="Platform (weibo or zhihu). If not specified, processes both.")
    parser.add_argument("--source_type", type=str, default="csv", choices=["csv", "sqlite", "json"], help="Data source type (csv, sqlite or json)")
    parser.add_argument("--output_format", type=str, default="json", help="Output format (json, csv, sqlite). Multiple formats separated by comma.")
    parser.add_argument("--weibo_posts", type=str)
    parser.add_argument("--weibo_comments", type=str)
    parser.add_argument("--json_file", type=str, help="Path to unlabelled JSON data")
    parser.add_argument("--batch_size", type=int, default=16, help="Batch size for VLM inference (Recommended 16+ for text-only)")
    parser.add_argument("--limit", type=int, help="Limit number of items to process")
    parser.add_argument("--process_count", type=int, default=1, help="Total number of parallel processes")
    parser.add_argument("--process_index", type=int, default=0, help="Index of current process (0 to process_count-1)")
    parser.add_argument("--stream", action="store_true", help="Enable streaming mode to process data continuously as it is crawled (SQLite only)")
    parser.add_argument("--stream_interval", type=int, default=60, help="Interval in seconds to check for new data in streaming mode")
    parser.add_argument("--dry_run", action="store_true", help="Load data only, skip VLM processing")
    
    args = parser.parse_args()
    
    # Enforce SQLite for streaming mode
    if args.stream and args.source_type != "sqlite":
        utils.logger.warning("[main.main] Streaming mode enabled. Forcing source_type to 'sqlite'.")
        args.source_type = "sqlite"
    
    # Load data
    utils.logger.info("[main.main] Initializing components...")
    vlm = VLMHandler()
    data_manager = DataManager()
    
    output_formats = args.output_format.split(",")
    exporter = Exporter(LABELED_DATA_FILE, formats=output_formats)
    
    # 获取已存在的数据 ID，用于在加载阶段就进行过滤
    existing_ids = exporter.get_existing_ids()
    utils.logger.info(f"[main.main] 检测到 {len(existing_ids)} 条历史标注记录，加载时将自动跳过。")

    platforms_to_process = [args.platform] if args.platform else ["weibo", "zhihu"]

    while True:
        has_new_data_any = False
        for current_platform in platforms_to_process:
            all_data = []
            analyzer = MultimodalAnalyzer(vlm, platform=current_platform)
            
            utils.logger.info(f"[main.main] >>> 正在检查平台: {current_platform} <<<")

            if current_platform == "weibo":
                if args.source_type == "csv":
                    posts_file = args.weibo_posts or str(WEIBO_POSTS_FILE)
                    comments_file = args.weibo_comments or str(WEIBO_COMMENTS_FILE)
                    
                    if args.date:
                        p, c = get_weibo_files_by_date(args.date)
                        if p.exists() and c.exists():
                            posts_file, comments_file = str(p), str(c)
                        else:
                            utils.logger.error(f"[main.main] Error: No data found for date {args.date} for weibo")
                            continue
                    
                    utils.logger.info(f"[main.main] 正在读取微博 CSV 数据: {Path(posts_file).name} ...")
                    weibo_data = data_manager.load_weibo_data(posts_file, comments_file, existing_ids=existing_ids)
                    all_data.extend(weibo_data)
                    
                elif args.source_type == "sqlite":
                    utils.logger.info(f"[main.main] 正在从 SQLite 读取微博数据 (date={args.date or 'ALL'})...")
                    weibo_data = data_manager.load_weibo_data(source_type="sqlite", date=args.date, existing_ids=existing_ids)
                    all_data.extend(weibo_data)

                elif args.source_type == "json":
                    if not args.json_file:
                         utils.logger.error("Weibo JSON source requires --json_file argument.")
                         continue
                    utils.logger.info(f"[main.main] 正在从 JSON 读取微博数据: {args.json_file}...")
                    weibo_data = data_manager.load_weibo_data(json_file=args.json_file, source_type="json", existing_ids=existing_ids)
                    all_data.extend(weibo_data)

            elif current_platform == "zhihu":
                if args.source_type == "sqlite":
                     utils.logger.info(f"[main.main] 正在从 SQLite 读取知乎数据 (date={args.date or 'ALL'})...")
                     zhihu_data = data_manager.load_zhihu_data(date=args.date, source_type="sqlite", existing_ids=existing_ids)
                     all_data.extend(zhihu_data)
                elif args.source_type == "json":
                     if not args.json_file:
                         utils.logger.error("Zhihu JSON source requires --json_file argument.")
                         continue
                     utils.logger.info(f"[main.main] 正在从 JSON 读取知乎数据: {Path(args.json_file).name}...")
                     zhihu_data = data_manager.load_zhihu_data(json_file=args.json_file, source_type="json", existing_ids=existing_ids)
                     all_data.extend(zhihu_data)
                else:
                     utils.logger.error(f"Unsupported source_type for Zhihu: {args.source_type}")
                     continue

            # Only load generic JSON if not already handled by platform specific loader
            if args.json_file and args.source_type != "json" and current_platform == platforms_to_process[0]:
                utils.logger.info(f"[main.main] 正在读取通用 JSON 数据: {Path(args.json_file).name} ...")
                json_data = data_manager.load_json_data(args.json_file, existing_ids=existing_ids)
                all_data.extend(json_data)

            if not all_data:
                continue

            has_new_data_any = True

            # Apply limit if provided
            if args.limit:
                utils.logger.info(f"[main.main] 限制处理条数: {args.limit}")
                all_data = all_data[:args.limit]

            # 多进程数据切分
            if args.process_count > 1:
                total_items = len(all_data)
                # 使用简单的分片逻辑：每个进程取 [index::count]
                all_data = all_data[args.process_index::args.process_count]
                utils.logger.info(f"[main.main] 多进程模式: 进程 {args.process_index+1}/{args.process_count} 分配了 {len(all_data)}/{total_items} 条数据")

            # 分离文章和评论
            posts = [d for d in all_data if d.get("type") == "post"]
            comments = [d for d in all_data if d.get("type") == "comment"]
            other_data = [d for d in all_data if d.get("type") not in ["post", "comment"]]
            
            # Process and Analyze
            utils.logger.info("="*50)
            utils.logger.info(f"[main.main] 🚀 开始执行 [{current_platform}] 多模态分析流水线")
            if args.dry_run:
                utils.logger.info("[main.main] ⚠️ Dry run enabled. Skipping VLM analysis.")

            if args.process_count > 1:
                utils.logger.info(f"[main.main] 当前进程  : {args.process_index + 1} / {args.process_count}")
            utils.logger.info(f"[main.main] 待处理总量: {len(all_data)} (文章: {len(posts)}, 评论: {len(comments)})")
            utils.logger.info(f"[main.main] 批次大小  : {args.batch_size}")
            utils.logger.info("="*50)
            
            # 核心策略：先处理文章，为评论提供更丰富的视觉背景
            if posts and not args.dry_run:
                utils.logger.info(f"[main.main] [阶段 1/2] 正在优先处理文章数据 (共 {len(posts)} 条)...")
                analyzer.process_batch(
                    posts, 
                    exporter=exporter, 
                    batch_size=args.batch_size, 
                    use_lock=(args.process_count > 1)
                )
            
            # 阶段 2：处理评论和其他数据
            remaining_data = comments + other_data
            if remaining_data and not args.dry_run:
                utils.logger.info(f"[main.main] \n>>> [阶段 2/2] 正在处理评论数据 (共 {len(remaining_data)} 条)...")
                analyzer.process_batch(
                    remaining_data, 
                    exporter=exporter, 
                    batch_size=args.batch_size, 
                    use_lock=(args.process_count > 1)
                )

        if not has_new_data_any:
            if args.stream:
                utils.logger.info(f"[main.main] >>> 所有平台均未发现新数据，等待 {args.stream_interval} 秒后重试...")
                import time
                time.sleep(args.stream_interval)
                existing_ids = exporter.get_existing_ids()
                continue
            else:
                utils.logger.info("[main.main] >>> 未发现需要处理的新数据。所有数据可能均已处理完成。")
                sys.exit(0)
        
        if not args.stream:
            break
        else:
            utils.logger.info(f"[main.main] 所有平台当前批次处理完成，刷新已处理 ID 并等待下一轮 ({args.stream_interval}s)...")
            import time
            time.sleep(args.stream_interval)
            existing_ids = exporter.get_existing_ids()
    
    # 显式关闭导出器，确保异步队列中的数据全部写入磁盘
    exporter.close()
    
    utils.logger.info(f"[main.main] Pipeline completed successfully. Results saved to {LABELED_DATA_FILE}")
