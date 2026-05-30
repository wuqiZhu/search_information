#!/usr/bin/env python3
"""
历史数据全量标注脚本
读取所有 SQLite 库，用 MiMo API 为每条新闻打标签
支持多线程、断点续跑
"""
import sqlite3
import json
import os
import time
import glob
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")
MIMO_API_URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
MODEL_NAME = "mimo-v2.5-pro"
MAX_RETRIES = 3
BATCH_SIZE = 50
MAX_WORKERS = 10
STORAGE_DIR = "/root/projects/data/search_information"

LABEL_COLS = ['sentiment', 'sentiment_score', 'relevance_score', 'category', 'summary']

SYSTEM_PROMPT = "你是一个金融数据标注专家。只输出JSON，不要额外解释。"
USER_PROMPT_TEMPLATE = """分析以下新闻标题，输出JSON格式：
{{
  "sentiment": "positive|negative|neutral",
  "sentiment_score": 0.0-1.0,
  "relevance_score": 0-10,
  "category": "03-政策福利|04-行业动态|05-长期杠杆|06-嵌入式Linux|07-BSP开发|08-设备驱动|09-RISC-V|10-IoT|其他",
  "summary": "一句话中文摘要，不超过30字"
}}

标题：{title}"""


def call_mimo(prompt, max_tokens=2000):
    headers = {
        "Authorization": f"Bearer {MIMO_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.1
    }
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(MIMO_API_URL, headers=headers, json=payload, timeout=60)
            if resp.status_code == 429:
                wait_time = 30 * (attempt + 1)
                print(f"  [限流] 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            content = msg.get("content", "") or ""
            reasoning = msg.get("reasoning_content", "") or ""
            text = content.strip() if content.strip() else reasoning.strip()
            if text:
                return text
            return None
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                return None
    return None


def analyze_single(title):
    if not title or len(title.strip()) < 5:
        return None
    prompt = USER_PROMPT_TEMPLATE.format(title=title.strip())
    result_text = call_mimo(prompt, max_tokens=2000)
    if not result_text:
        return None
    try:
        return json.loads(result_text)
    except:
        pass
    start = result_text.find('{')
    end = result_text.rfind('}') + 1
    if start >= 0 and end > start:
        try:
            return json.loads(result_text[start:end])
        except:
            pass
    import re
    json_pattern = re.search(r'\{[^{}]*"sentiment"[^{}]*\}', result_text)
    if json_pattern:
        try:
            return json.loads(json_pattern.group())
        except:
            pass
    return None


def add_label_columns(cur, table_name):
    for col in LABEL_COLS:
        try:
            cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} TEXT")
        except:
            pass


def label_database(db_path, table_name, title_col):
    print(f"\n{'='*60}")
    print(f"处理: {db_path} ({table_name})")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    add_label_columns(cur, table_name)
    conn.commit()

    cur.execute(f"SELECT rowid, {title_col} FROM {table_name} WHERE sentiment IS NULL OR sentiment = ''")
    rows = cur.fetchall()
    total = len(rows)
    if total == 0:
        print("  全部已标注")
        conn.close()
        return 0

    print(f"  待标注: {total} 条")
    success = 0
    failed = 0

    def process_one(rowid, title):
        result = analyze_single(title)
        return rowid, result

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_one, rowid, title): rowid for rowid, title in rows}
        for i, future in enumerate(as_completed(futures)):
            rowid, result = future.result()
            if result:
                try:
                    cur.execute(f"""UPDATE {table_name} SET
                        sentiment=?, sentiment_score=?, relevance_score=?, category=?, summary=?
                        WHERE rowid=?""",
                        (result.get('sentiment', ''),
                         result.get('sentiment_score', 0),
                         result.get('relevance_score', 0),
                         result.get('category', ''),
                         result.get('summary', ''),
                         rowid))
                    success += 1
                except:
                    cur.execute(f"UPDATE {table_name} SET sentiment='error' WHERE rowid=?", (rowid,))
                    failed += 1
            else:
                cur.execute(f"UPDATE {table_name} SET sentiment='error' WHERE rowid=?", (rowid,))
                failed += 1

            if (i + 1) % BATCH_SIZE == 0:
                conn.commit()
                print(f"  进度: {i+1}/{total} (成功 {success}, 失败 {failed})")

    conn.commit()
    conn.close()
    print(f"  完成: 成功 {success}/{total}, 失败 {failed}")
    return success


def find_databases():
    dbs = []
    for pattern in ['news/*.db', 'rss/*.db']:
        dbs.extend(glob.glob(os.path.join(STORAGE_DIR, pattern)))
    return sorted(dbs)


def get_table_info(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cur.fetchall()]
    conn.close()

    if 'news_items' in tables:
        return 'news_items', 'title'
    elif 'rss_items' in tables:
        return 'rss_items', 'title'
    return None, None


if __name__ == "__main__":
    if not MIMO_API_KEY:
        print("错误: MIMO_API_KEY 环境变量未设置")
        sys.exit(1)

    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API端点: {MIMO_API_URL}")
    print(f"模型: {MODEL_NAME}")
    print(f"线程数: {MAX_WORKERS}")
    print(f"数据目录: {STORAGE_DIR}")

    dbs = find_databases()
    print(f"找到 {len(dbs)} 个数据库文件")
    for db in dbs:
        print(f"  - {db}")

    total_success = 0
    for db in dbs:
        table_name, title_col = get_table_info(db)
        if table_name:
            cnt = label_database(db, table_name, title_col)
            total_success += cnt
        else:
            print(f"\n跳过 {db}: 未找到匹配的表")

    print(f"\n{'='*60}")
    print(f"全部完成！共成功标注 {total_success} 条")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
