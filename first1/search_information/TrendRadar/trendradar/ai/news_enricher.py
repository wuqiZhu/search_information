import re
import logging
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}

PLACEHOLDER_IMAGE = "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=financial+news+abstract+blue+gradient&image_size=square"


def extract_article_image(url: str, timeout: int = 10) -> Optional[str]:
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"

        soup = BeautifulSoup(resp.text, "html.parser")

        image = _extract_og_image(soup)
        if image:
            return _resolve_url(url, image)

        image = _extract_twitter_image(soup)
        if image:
            return _resolve_url(url, image)

        image = _extract_first_large_image(soup)
        if image:
            return _resolve_url(url, image)

        return None

    except Exception as e:
        logger.debug(f"图片抓取失败 {url}: {e}")
        return None


def _extract_og_image(soup: BeautifulSoup) -> Optional[str]:
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"].strip()
    return None


def _extract_twitter_image(soup: BeautifulSoup) -> Optional[str]:
    twitter = soup.find("meta", attrs={"name": "twitter:image"})
    if twitter and twitter.get("content"):
        return twitter["content"].strip()

    twitter_src = soup.find("meta", attrs={"property": "twitter:image"})
    if twitter_src and twitter_src.get("content"):
        return twitter_src["content"].strip()
    return None


def _extract_first_large_image(soup: BeautifulSoup) -> Optional[str]:
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if not src:
            continue

        src = src.strip()
        if src.startswith("data:"):
            continue
        if any(x in src.lower() for x in ["logo", "icon", "avatar", "ad", "tracking", "pixel", "1x1"]):
            continue

        width = img.get("width")
        height = img.get("height")
        if width and height:
            try:
                if int(width) < 100 or int(height) < 100:
                    continue
            except (ValueError, TypeError):
                pass

        ext = urlparse(src).path.lower()
        if any(ext.endswith(e) for e in IMAGE_EXTENSIONS):
            return src

        if not any(ext.endswith(e) for e in [".js", ".css", ".ico"]):
            return src

    return None


def _resolve_url(base_url: str, image_url: str) -> str:
    if image_url.startswith("//"):
        return "https:" + image_url
    if image_url.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{image_url}"
    if image_url.startswith("http"):
        return image_url
    return urljoin(base_url, image_url)


def generate_ai_digest(news_items: list, api_key: str, api_endpoint: str = None, model: str = "mimo-v2.5-pro") -> Optional[str]:
    if not news_items:
        return None

    titles_text = "\n".join(
        f"- [{item.get('keyword', '')}] {item.get('title', '')}"
        for item in news_items[:20]
    )

    prompt = f"""你是一个投资信息分析师。请根据以下今日新闻，生成一份简洁的投资日报。

要求：
1. 用3-5个要点总结今日最重要的信息
2. 每个要点包含：核心信息 + 对投资者的影响
3. 最后给出一个总体建议（看多/看空/观望）
4. 使用emoji让内容更生动
5. 总字数控制在300字以内

今日新闻：
{titles_text}

请直接输出日报内容，不要加任何前缀。"""

    try:
        endpoint = api_endpoint or "https://token-plan-cn.xiaomimimo.com/v1"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
            "temperature": 0.7
        }

        resp = requests.post(
            f"{endpoint}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        resp.raise_for_status()
        data = resp.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        reasoning = data.get("choices", [{}])[0].get("message", {}).get("reasoning_content", "")

        result = content.strip() if content.strip() else reasoning.strip()
        return result if result else None

    except Exception as e:
        logger.error(f"AI日报生成失败: {e}")
        return None


def enrich_news_items(news_items: list, max_items: int = 5) -> list:
    enriched = []

    for item in news_items[:max_items]:
        title = item.get("title", "")
        url = item.get("url", "")

        image_url = None
        if url and url.startswith("http"):
            image_url = extract_article_image(url)

        enriched_item = {
            **item,
            "image_url": image_url or PLACEHOLDER_IMAGE,
            "has_real_image": image_url is not None,
        }
        enriched.append(enriched_item)

    for item in news_items[max_items:]:
        enriched.append({
            **item,
            "image_url": PLACEHOLDER_IMAGE,
            "has_real_image": False,
        })

    return enriched
