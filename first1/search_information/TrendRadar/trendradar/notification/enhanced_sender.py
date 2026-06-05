import hashlib
import hmac
import base64
import time
import logging
from typing import Optional
from urllib.parse import quote_plus

import requests

from trendradar.ai.news_enricher import enrich_news_items, generate_ai_digest

logger = logging.getLogger(__name__)


def send_enhanced_dingtalk(
    webhook_url: str,
    secret: str,
    news_items: list,
    api_key: str = None,
    api_endpoint: str = None,
    report_type: str = "投资日报",
    max_items: int = 5,
    timeout: int = 30,
) -> bool:
    if not webhook_url:
        logger.warning("钉钉 Webhook URL 未配置")
        return False

    try:
        enriched_items = enrich_news_items(news_items, max_items=max_items)

        ai_digest = None
        if api_key:
            ai_digest = generate_ai_digest(
                news_items,
                api_key=api_key,
                api_endpoint=api_endpoint,
            )

        url = _sign_webhook(webhook_url, secret) if secret else webhook_url

        if ai_digest:
            _send_digest_card(url, ai_digest, report_type, timeout=timeout)
            time.sleep(1)

        _send_feed_card(url, enriched_items, report_type, timeout=timeout)

        logger.info(f"增强通知发送成功：{len(enriched_items)}条新闻")
        return True

    except Exception as e:
        logger.error(f"增强通知发送失败: {e}")
        return False


def _sign_webhook(webhook_url: str, secret: str) -> str:
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    sign = quote_plus(base64.b64encode(hmac_code))
    return f"{webhook_url}&timestamp={timestamp}&sign={sign}"


def _send_digest_card(url: str, digest: str, report_type: str, timeout: int = 30):
    lines = digest.split("\n")
    formatted_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            formatted_lines.append("")
            continue
        if line.startswith("##") or line.startswith("# "):
            line = line.lstrip("#").strip()
            line = f"## {line}"
        formatted_lines.append(line)

    formatted_text = "\n".join(formatted_lines)

    if "通知" not in formatted_text:
        formatted_text = f"**通知**\n\n{formatted_text}"

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": f"📊 {report_type} - AI日报",
            "text": formatted_text,
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        result = resp.json()
        if result.get("errcode") != 0:
            logger.warning(f"钉钉返回错误: {result}")
    except Exception as e:
        logger.error(f"发送AI日报失败: {e}")


def _send_feed_card(url: str, items: list, report_type: str, timeout: int = 30):
    links = []
    for item in items:
        title = item.get("title", "未知标题")
        article_url = item.get("url", "")
        image_url = item.get("image_url", "")
        keyword = item.get("keyword", "")
        source = item.get("source", "")

        if keyword:
            display_title = f"[{keyword}] {title}"
        else:
            display_title = title

        if len(display_title) > 40:
            display_title = display_title[:37] + "..."

        link_item = {
            "title": display_title,
            "messageURL": article_url or "https://github.com/wuqiZhu/search_information",
            "picURL": image_url,
        }
        links.append(link_item)

    if not links:
        logger.warning("没有新闻可发送")
        return

    if links and "通知" not in links[0]["title"]:
        links[0]["title"] = f"通知 | {links[0]['title']}"

    payload = {
        "msgtype": "feedCard",
        "feedCard": {
            "links": links
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        result = resp.json()
        if result.get("errcode") != 0:
            logger.warning(f"钉钉返回错误: {result}")
    except Exception as e:
        logger.error(f"发送feedCard失败: {e}")


def send_enhanced_actioncard(
    url: str,
    title: str,
    text: str,
    button_title: str = "查看详情",
    button_url: str = "https://github.com/wuqiZhu/search_information",
    pic_url: str = None,
    timeout: int = 30,
) -> bool:
    if "通知" not in text:
        text = f"**通知**\n\n{text}"

    payload = {
        "msgtype": "actionCard",
        "actionCard": {
            "title": title,
            "text": text,
            "btnOrientation": "0",
            "singleTitle": button_title,
            "singleURL": button_url,
        },
    }

    if pic_url:
        payload["actionCard"]["picURL"] = pic_url

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        result = resp.json()
        return result.get("errcode") == 0
    except Exception as e:
        logger.error(f"发送ActionCard失败: {e}")
        return False
