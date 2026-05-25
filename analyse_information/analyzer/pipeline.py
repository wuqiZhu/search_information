import sys
import json
import logging
import argparse
import time
from pathlib import Path
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv(Path(__file__).parent.parent / ".env")

from analyzer.defuddle.extractor import extract_content, save_raw_content
from analyzer.ai_analyzer import AIAnalyzer
from analyzer.knowledge_builder import KnowledgeBuilder
from analyzer.db import (
    init_db, is_url_processed, save_result, get_stats, get_url_record,
    search_articles, set_feedback, get_feedback_stats, get_user_preferences,
)
from analyzer.rss_fetcher import fetch_all_feeds
from analyzer.digest import generate_daily_digest, generate_weekly_digest

MAX_WORKERS = 3
MAX_RETRIES = 2
RETRY_DELAY = 3


def load_config(config_path: str = None) -> dict:
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(config: dict):
    log_config = config.get("analyzer", {}).get("logging", {})
    log_file = log_config.get("file", "./shared/logs/analyzer.log")
    log_level = log_config.get("level", "INFO")

    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            file_handler,
            logging.StreamHandler(),
        ],
    )


def process_single_url(url: str, config: dict, ai: AIAnalyzer, kb: KnowledgeBuilder, logger, preferences: dict = None) -> dict:
    analyzer_config = config.get("analyzer", {})
    result = {"url": url, "status": "pending"}

    if is_url_processed(url):
        existing = get_url_record(url)
        logger.info("[跳过] URL 已处理过: %s (状态: %s)", url, existing["status"])
        result["status"] = "skipped"
        result["reason"] = f"已处理于 {existing['created_at']}"
        return result

    logger.info("=" * 60)
    logger.info("开始处理: %s", url)

    logger.info("[1/4] 提取内容...")
    raw_data = extract_content(url, timeout=analyzer_config.get("defuddle", {}).get("timeout", 30))
    if not raw_data.get("content"):
        logger.warning("内容提取失败，跳过: %s", url)
        result["status"] = "extract_failed"
        save_result(url, result)
        return result

    raw_path = save_raw_content(raw_data, analyzer_config.get("knowledge_base", {}).get("raw_path", "./knowledge_base/raw"))
    logger.info("原始内容已保存: %s", raw_path)

    logger.info("[2/4] AI 分析 (相关性检查 + 大白话翻译 + 分类)...")
    for attempt in range(MAX_RETRIES + 1):
        try:
            analysis = ai.analyze(raw_data["title"], raw_data["content"], analyzer_config, preferences)
            break
        except Exception as e:
            if attempt < MAX_RETRIES:
                logger.warning("AI 分析失败，%d 秒后重试 (%d/%d): %s", RETRY_DELAY, attempt + 1, MAX_RETRIES, e)
                time.sleep(RETRY_DELAY)
            else:
                logger.error("AI 分析最终失败: %s", e)
                result["status"] = "ai_failed"
                result["reason"] = str(e)
                save_result(url, result)
                return result

    if not analysis["relevant"]:
        logger.info("内容不相关，跳过沉淀: %s (score=%.1f)", raw_data["title"], analysis["score"])
        result["status"] = "not_relevant"
        result["score"] = analysis["score"]
        result["reason"] = analysis["reason"]
        result["title"] = raw_data["title"]
        save_result(url, result)
        return result

    logger.info("相关性评分: %.1f, 分类: %s", analysis["score"], analysis["category"])

    logger.info("[3/4] 保存分析结果...")
    merged = {**raw_data, **analysis}
    kb.save_analyzed(merged)
    kb.save_translated(merged)

    logger.info("[3.5/4] 搜索相关笔记...")
    related_notes = []
    try:
        search_query = raw_data["title"][:30]
        related_notes = search_articles(search_query, limit=5)
        related_notes = [n for n in related_notes if n.get("url") != url and n.get("status") == "success"]
        if related_notes:
            logger.info("找到 %d 篇相关笔记", len(related_notes))
    except Exception as e:
        logger.warning("搜索相关笔记失败: %s", e)

    logger.info("[4/4] 沉淀到 Obsidian 知识库...")
    obsidian_path = kb.save_to_obsidian(merged, related_notes)
    logger.info("知识沉淀完成: %s", obsidian_path)

    result["status"] = "success"
    result["title"] = raw_data["title"]
    result["score"] = analysis["score"]
    result["category"] = analysis["category"]
    result["obsidian_path"] = obsidian_path
    result["translation"] = analysis.get("translation", "")
    save_result(url, result)
    return result


def process_batch(urls: list, config: dict) -> tuple:
    logger = logging.getLogger("pipeline")
    analyzer_config = config.get("analyzer", {})
    ai = AIAnalyzer(analyzer_config.get("ai", {}))
    kb = KnowledgeBuilder(analyzer_config.get("knowledge_base", {}))

    preferences = get_user_preferences()
    if preferences.get("liked") or preferences.get("disliked"):
        logger.info("已加载用户偏好: %d 条有用, %d 条没用",
                     len(preferences.get("liked", [])), len(preferences.get("disliked", [])))

    skipped = [u for u in urls if is_url_processed(u)]
    new_urls = [u for u in urls if not is_url_processed(u)]

    if skipped:
        logger.info("跳过 %d 个已处理的 URL，剩余 %d 个新 URL", len(skipped), len(new_urls))

    if not new_urls:
        logger.info("所有 URL 均已处理过，无需重复处理")
        return [{"url": u, "status": "skipped", "reason": "已处理过"} for u in urls], ai.token_tracker.summary()

    results = []
    workers = min(MAX_WORKERS, len(new_urls))
    logger.info("并发处理 %d 个 URL，工作线程数: %d", len(new_urls), workers)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(process_single_url, url, config, ai, kb, logger, preferences): url
            for url in new_urls
        }
        for future in as_completed(future_map):
            url = future_map[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error("处理异常: %s - %s", url, e)
                results.append({"url": url, "status": "error", "reason": str(e)})

    for u in skipped:
        existing = get_url_record(u)
        results.append({"url": u, "status": "skipped", "reason": f"已处理于 {existing['created_at']}" if existing else "已处理过"})

    return results, ai.token_tracker.summary()


def process_from_json(json_path: str, config: dict) -> tuple:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    urls = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                urls.append(item)
            elif isinstance(item, dict) and "url" in item:
                urls.append(item["url"])
    elif isinstance(data, dict) and "urls" in data:
        urls = data["urls"]

    return process_batch(urls, config)


def process_rss(config: dict) -> tuple:
    logger = logging.getLogger("pipeline")
    items = fetch_all_feeds()
    if not items:
        logger.info("RSS 无新内容")
        return [], {}

    urls = [item["url"] for item in items]
    logger.info("RSS 共 %d 条，开始处理...", len(urls))
    return process_batch(urls, config)


def process_from_n8n_webhook(data: dict, config: dict) -> dict:
    logger = logging.getLogger("pipeline")
    analyzer_config = config.get("analyzer", {})
    ai = AIAnalyzer(analyzer_config.get("ai", {}))
    kb = KnowledgeBuilder(analyzer_config.get("knowledge_base", {}))

    url = data.get("url", "")
    title = data.get("title", "")
    content = data.get("content", "")

    if content:
        raw_data = {"title": title, "content": content, "url": url, "word_count": len(content.split())}
        save_raw_content(raw_data, analyzer_config.get("knowledge_base", {}).get("raw_path", "./knowledge_base/raw"))

        analysis = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                analysis = ai.analyze(title, content, analyzer_config)
                break
            except Exception as e:
                if attempt < MAX_RETRIES:
                    logger.warning("AI 分析失败，%d 秒后重试 (%d/%d): %s", RETRY_DELAY, attempt + 1, MAX_RETRIES, e)
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error("AI 分析最终失败: %s", e)
                    return {"status": "error", "reason": str(e)}

        if analysis is None:
            return {"status": "error", "reason": "AI 分析返回空结果"}

        if analysis["relevant"]:
            merged = {**raw_data, **analysis}
            kb.save_analyzed(merged)
            kb.save_translated(merged)
            obsidian_path = kb.save_to_obsidian(merged)
            result = {"status": "success", "obsidian_path": obsidian_path, **analysis}
            result["translation"] = analysis.get("translation", "")
            save_result(url, result)
            return result
        result = {"status": "not_relevant", **analysis}
        save_result(url, result)
        return result
    elif url:
        result = process_single_url(url, config, ai, kb, logger)
        return result
    return {"status": "error", "message": "缺少 url 或 content"}


def print_report(results: list, logger, token_stats: dict = None):
    success = sum(1 for r in results if r["status"] == "success")
    not_relevant = sum(1 for r in results if r["status"] == "not_relevant")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] in ("extract_failed", "error", "ai_failed"))

    logger.info("")
    logger.info("=" * 60)
    logger.info("处理报告")
    logger.info("=" * 60)
    logger.info("  总计: %d 篇", len(results))
    logger.info("  ✅ 成功沉淀: %d 篇", success)
    logger.info("  ⏭️  已跳过: %d 篇", skipped)
    logger.info("  ❌ 不相关: %d 篇", not_relevant)
    logger.info("  ⚠️  失败: %d 篇", failed)

    if success > 0:
        logger.info("")
        logger.info("成功沉淀的文章:")
        for r in results:
            if r["status"] == "success":
                logger.info("  📄 [%s] %s (评分: %.1f)", r.get("category", ""), r.get("title", ""), r.get("score", 0))

    if token_stats and token_stats.get("call_count", 0) > 0:
        logger.info("")
        logger.info("Token 用量统计:")
        logger.info("  API 调用次数: %d", token_stats["call_count"])
        logger.info("  输入 Token: %d", token_stats["prompt_tokens"])
        logger.info("  输出 Token: %d", token_stats["completion_tokens"])
        logger.info("  总 Token: %d", token_stats["total_tokens"])
        logger.info("  预估费用: ¥%.4f", token_stats["estimated_cost_yuan"])

    logger.info("=" * 60)


def process_signals_dir(signals_dir: str, config: dict) -> tuple:
    """从 TrendRadar 信号目录读取 JSON 文件并处理"""
    logger = logging.getLogger("pipeline")
    signals_path = Path(signals_dir)
    
    if not signals_path.exists():
        logger.error("信号目录不存在: %s", signals_dir)
        return [], {}
    
    # 读取所有 JSON 信号文件
    signal_files = list(signals_path.glob("*.json"))
    if not signal_files:
        logger.info("信号目录为空: %s", signals_dir)
        return [], {}
    
    logger.info("从信号目录读取 %d 个文件: %s", len(signal_files), signals_dir)
    
    # 提取 URL
    urls = []
    for sf in signal_files:
        try:
            with open(sf, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "url" in data:
                    urls.append(data["url"])
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "url" in item:
                            urls.append(item["url"])
        except Exception as e:
            logger.warning("读取信号文件失败: %s - %s", sf, e)
    
    if not urls:
        logger.info("未找到有效 URL")
        return [], {}
    
    # 去重
    urls = list(dict.fromkeys(urls))
    logger.info("提取到 %d 个唯一 URL", len(urls))
    
    return process_batch(urls, config)


def main():
    parser = argparse.ArgumentParser(description="信息分析与知识沉淀 Pipeline")
    parser.add_argument("--url", type=str, help="单个 URL")
    parser.add_argument("--urls", nargs="+", help="多个 URL")
    parser.add_argument("--json", type=str, help="从 JSON 文件读取 URL 列表")
    parser.add_argument("--config", type=str, default=None, help="配置文件路径")
    parser.add_argument("--webhook-data", type=str, help="n8n Webhook JSON 数据")
    parser.add_argument("--stats", action="store_true", help="查看历史统计")
    parser.add_argument("--workers", type=int, default=3, help="并发线程数 (默认 3)")

    parser.add_argument("--rss", action="store_true", help="从 RSS 订阅源拉取并处理")
    parser.add_argument("--signals-dir", type=str, help="从 TrendRadar 信号目录读取 JSON 文件")
    parser.add_argument("--search", type=str, help="搜索已沉淀的文章")
    parser.add_argument("--feedback", nargs=2, metavar=("URL", "TAG"), help="标记文章反馈 (URL useful/not_useful)")
    parser.add_argument("--preferences", action="store_true", help="查看用户偏好统计")
    parser.add_argument("--digest", action="store_true", help="生成每日摘要")
    parser.add_argument("--weekly-digest", action="store_true", help="生成每周摘要")

    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config)
    logger = logging.getLogger("pipeline")

    global MAX_WORKERS
    MAX_WORKERS = args.workers

    init_db()

    if args.stats:
        stats = get_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return

    if args.search:
        results = search_articles(args.search)
        if results:
            print(f"找到 {len(results)} 条结果:\n")
            for r in results:
                print(f"  [{r.get('score', 0):.1f}] [{r.get('category', '')}] {r.get('title', '')}")
                print(f"        {r.get('url', '')}")
                if r.get("feedback"):
                    print(f"        反馈: {r['feedback']}")
                print()
        else:
            print(f"未找到与 '{args.search}' 相关的文章")
        return

    if args.feedback:
        url, tag = args.feedback
        if tag not in ("useful", "not_useful"):
            print("反馈标签必须是 useful 或 not_useful")
            return
        success = set_feedback(url, tag)
        if success:
            print(f"已标记: {url} → {tag}")
        else:
            print(f"未找到该 URL: {url}")
        return

    if args.preferences:
        prefs = get_user_preferences()
        fb_stats = get_feedback_stats()
        print("=== 反馈统计 ===")
        print(json.dumps(fb_stats, ensure_ascii=False, indent=2))
        print("\n=== 偏好分类 ===")
        print(json.dumps(prefs["top_categories"], ensure_ascii=False, indent=2))
        if prefs["liked"]:
            print(f"\n最近标记为有用的文章 ({len(prefs['liked'])} 篇):")
            for item in prefs["liked"][:5]:
                print(f"  ✅ [{item['category']}] {item['title']}")
        return

    if args.digest:
        path = generate_daily_digest()
        if path:
            print(f"每日摘要已生成: {path}")
        else:
            print("今日无新文章，跳过摘要生成")
        return

    if args.weekly_digest:
        path = generate_weekly_digest()
        if path:
            print(f"每周摘要已生成: {path}")
        else:
            print("本周无文章，跳过摘要生成")
        return

    logger.info("Pipeline 启动")

    if args.webhook_data:
        data = json.loads(args.webhook_data)
        result = process_from_n8n_webhook(data, config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.signals_dir:
        results, token_stats = process_signals_dir(args.signals_dir, config)
        if results:
            print_report(results, logger, token_stats)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.rss:
        results, token_stats = process_rss(config)
        if results:
            print_report(results, logger, token_stats)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.url:
        results, token_stats = process_batch([args.url], config)
        print_report(results, logger, token_stats)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.urls:
        results, token_stats = process_batch(args.urls, config)
        print_report(results, logger, token_stats)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.json:
        results, token_stats = process_from_json(args.json, config)
        print_report(results, logger, token_stats)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        parser.print_help()

    logger.info("Pipeline 完成")


if __name__ == "__main__":
    main()
