import subprocess
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_content(url: str, timeout: int = 30) -> dict:
    try:
        result = subprocess.run(
            ["npx", "defuddle", url, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
        )

        if result.returncode != 0:
            logger.warning("Defuddle 提取失败，回退到正文提取: %s", result.stderr[:200])
            return _fallback_extract(url)

        data = json.loads(result.stdout)
        return {
            "title": data.get("title", ""),
            "content": data.get("content", ""),
            "url": url,
            "word_count": len(data.get("content", "").split()),
        }
    except subprocess.TimeoutExpired:
        logger.warning("Defuddle 超时，回退到正文提取: %s", url)
        return _fallback_extract(url)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.warning("Defuddle 执行异常 (%s)，回退到正文提取", e)
        return _fallback_extract(url)


def _fallback_extract(url: str) -> dict:
    try:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        html = resp.text

        soup = BeautifulSoup(html, "html.parser")

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
            tag.decompose()

        candidate_selectors = [
            "article", "main", "[role='main']", ".post-content", ".entry-content",
            ".article-body", ".story-body", "#content", ".content",
        ]
        main_content = None
        for selector in candidate_selectors:
            found = soup.select_one(selector)
            if found and len(found.get_text(strip=True)) > 200:
                main_content = found
                break

        if main_content is None:
            body = soup.find("body")
            if body:
                main_content = body
            else:
                main_content = soup

        for tag in main_content.find_all(["nav", "footer", "header", "aside", "form", "button", "input", "select"]):
            tag.decompose()

        paragraphs = []
        for el in main_content.find_all(["h1", "h2", "h3", "h4", "h5", "p", "li", "pre", "code", "blockquote", "table", "td", "th"]):
            text = el.get_text(strip=True)
            if not text or len(text) < 5:
                continue

            if el.name in ("h1", "h2", "h3", "h4", "h5"):
                level = int(el.name[1])
                paragraphs.append(f"\n{'#' * level} {text}\n")
            elif el.name == "li":
                if el.find_parent("ol"):
                    paragraphs.append(f"1. {text}")
                else:
                    paragraphs.append(f"- {text}")
            elif el.name in ("pre", "code"):
                if "\n" in text:
                    paragraphs.append(f"```\n{text}\n```")
                else:
                    paragraphs.append(f"`{text}`")
            elif el.name == "blockquote":
                paragraphs.append(f"> {text}")
            elif el.name in ("table", "td", "th"):
                paragraphs.append(text)
            else:
                paragraphs.append(text)

        content = "\n\n".join(paragraphs)

        if len(content) < 100:
            content = _plain_text_fallback(html)

        content = re.sub(r'\n{3,}', '\n\n', content)

        return {
            "title": title,
            "content": content,
            "url": url,
            "word_count": len(content.split()),
        }
    except Exception as e:
        logger.warning("正文提取失败 (%s)，回退到 plain text", e)
        return _plain_text_extract(url)


def _plain_text_extract(url: str) -> dict:
    try:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        return _plain_text_fallback(resp.text)
    except Exception as e:
        logger.error("plain text 提取也失败: %s", e)
        return {"title": "", "content": "", "url": url, "word_count": 0}


def _plain_text_fallback(html: str) -> dict:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "button"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    content = soup.get_text(separator="\n", strip=True)
    content = re.sub(r'\n{3,}', '\n\n', content)
    return {"title": title, "content": content, "url": "", "word_count": len(content.split())}


def save_raw_content(data: dict, output_dir: str) -> str:
    from datetime import datetime

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in data.get("title", "unknown"))
    safe_name = safe_name[:80]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{safe_name}.md"
    filepath = Path(output_dir) / filename

    md = f"""# {data.get('title', 'Unknown')}

- **来源**: {data.get('url', '')}
- **提取时间**: {datetime.now().isoformat()}
- **字数**: {data.get('word_count', 0)}

---

{data.get('content', '')}
"""
    filepath.write_text(md, encoding="utf-8")
    logger.info("原始内容已保存: %s", filepath)
    return str(filepath)
