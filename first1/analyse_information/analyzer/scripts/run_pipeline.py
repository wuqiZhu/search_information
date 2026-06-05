import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from analyzer.pipeline import load_config, setup_logging, process_batch, process_from_json, init_db, get_stats
import json


def run_single(url: str, workers: int = 1):
    config = load_config()
    setup_logging(config)
    init_db()
    results = process_batch([url], config)
    for r in results:
        print(f"状态: {r['status']}")
        if r.get("category"):
            print(f"分类: {r['category']}")
        if r.get("score"):
            print(f"评分: {r['score']}")


def run_batch(json_file: str, workers: int = 3):
    config = load_config()
    setup_logging(config)
    init_db()
    results = process_from_json(json_file, config)
    success = sum(1 for r in results if r["status"] == "success")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    not_relevant = sum(1 for r in results if r["status"] == "not_relevant")
    failed = sum(1 for r in results if r["status"] in ("extract_failed", "error", "ai_failed"))
    print(f"\n处理完成: 成功 {success}, 跳过 {skipped}, 不相关 {not_relevant}, 失败 {failed}")


def run_stats():
    config = load_config()
    setup_logging(config)
    init_db()
    stats = get_stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python run_pipeline.py <url>           # 处理单个URL")
        print("  python run_pipeline.py --batch <file>  # 批量处理")
        print("  python run_pipeline.py --stats         # 查看统计")
        sys.exit(1)

    if sys.argv[1] == "--stats":
        run_stats()
    elif sys.argv[1] == "--batch" and len(sys.argv) >= 3:
        run_batch(sys.argv[2])
    else:
        run_single(sys.argv[1])
