import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from xml.etree import ElementTree

import requests
import yaml

logger = logging.getLogger(__name__)

RSS_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_rss_feeds() -> list:
    try:
        with open(RSS_CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        rss_source = config.get("analyzer", {}).get("rss_source", "")
        if rss_source and Path(rss_source).exists():
            logger.info("从外部项目读取 RSS 源: %s", rss_source)
            try:
                with open(rss_source, "r", encoding="utf-8") as f:
                    external_config = yaml.safe_load(f)
                external_feeds = external_config.get("rss", {}).get("feeds", [])
                if external_feeds:
                    logger.info("从外部项目加载 %d 个 RSS 源", len(external_feeds))
                    return external_feeds
            except Exception as e:
                logger.warning("读取外部 RSS 配置失败，回退到本地: %s", e)

        return config.get("analyzer", {}).get("rss", {}).get("feeds", [])
    except Exception as e:
        logger.error("加载 RSS 配置失败: %s", e)
        return []


def fetch_feed(feed_url: str, timeout: int = 15) -> list:
    try:
        resp = requests.get(feed_url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (compatible; AnalyzerBot/1.0)"
        })
        resp.raise_for_status()
        return _parse_feed(resp.text)
    except Exception as e:
        logger.error("获取 RSS 失败: %s - %s", feed_url, e)
        return []


def _parse_feed(xml_text: str) -> list:
    items = []
    try:
        root = ElementTree.fromstring(xml_text)

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            link_el = entry.find("atom:link", ns)
            summary_el = entry.find("atom:summary", ns)
            content_el = entry.find("atom:content", ns)
            updated_el = entry.find("atom:updated", ns)

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.get("href", "") if link_el is not None else ""
            summary = ""
            if summary_el is not None and summary_el.text:
                summary = summary_el.text.strip()
            elif content_el is not None and content_el.text:
                summary = content_el.text.strip()
            published = updated_el.text.strip() if updated_el is not None and updated_el.text else ""

            if title and link:
                items.append({
                    "title": title,
                    "url": link,
                    "summary": summary[:1000],
                    "published": published,
                    "content_hash": hashlib.md5(link.encode()).hexdigest(),
                })

        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            summary = desc_el.text.strip()[:1000] if desc_el is not None and desc_el.text else ""
            published = pub_el.text.strip() if pub_el is not None and pub_el.text else ""

            if title and link:
                items.append({
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "published": published,
                    "content_hash": hashlib.md5(link.encode()).hexdigest(),
                })

    except ElementTree.ParseError as e:
        logger.error("XML 解析失败: %s", e)

    return items


def fetch_all_feeds() -> list:
    feeds = load_rss_feeds()
    if not feeds:
        logger.warning("未配置 RSS 订阅源")
        return []

    all_items = []
    for feed in feeds:
        url = feed.get("url", "")
        name = feed.get("name", url)
        logger.info("获取 RSS: %s", name)
        items = fetch_feed(url)
        for item in items:
            item["source_name"] = name
        all_items.extend(items)
        logger.info("  获取 %d 条", len(items))

    seen = set()
    unique = []
    for item in all_items:
        if item["content_hash"] not in seen:
            seen.add(item["content_hash"])
            unique.append(item)

    logger.info("RSS 共获取 %d 条（去重后）", len(unique))
    return unique


def save_feed_items(items: list, output_dir: str) -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = Path(output_dir) / f"rss_{ts}.json"

    import json
    filepath.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("RSS 数据已保存: %s", filepath)
    return str(filepath)
