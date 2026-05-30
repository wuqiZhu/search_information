#!/usr/bin/env python3
import sqlite3
import json
import os
from pathlib import Path

STORAGE_DIR = "/root/projects/data/search_information"
OUTPUT = "/root/projects/search_information/search_information/scripts/train_invest.jsonl"

SYSTEM_PROMPT = """你是一个投资分析助手，专门分析新闻对投资的影响。

分析维度：
1. 情绪分析：positive（利好）/ negative（利空）/ neutral（中性）
2. 情绪分数：1-10（1=极度利空，5=中性，10=极度利好）
3. 相关性分数：1-10（1=完全无关，10=直接相关）
4. 分类：01-宏观政策、02-公司公告、03-行业动态、04-市场数据、05-国际形势、06-科技创新、07-社会民生
5. 摘要：一句话总结核心信息

请用JSON格式输出：{"sentiment":"...","sentiment_score":...,"relevance_score":...,"category":"...","summary":"..."}"""

def export_from_db(db_path, table_name, output_file):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if table_name == "news_items":
        cursor.execute(f"SELECT title, sentiment, sentiment_score, relevance_score, category, summary FROM {table_name} WHERE sentiment IS NOT NULL AND sentiment != ''")
    else:
        cursor.execute(f"SELECT title, sentiment, sentiment_score, relevance_score, category, summary FROM {table_name} WHERE sentiment IS NOT NULL AND sentiment != ''")

    rows = cursor.fetchall()
    conn.close()

    samples = []
    for row in rows:
        title = row["title"]
        answer = json.dumps({
            "sentiment": row["sentiment"],
            "sentiment_score": row["sentiment_score"],
            "relevance_score": row["relevance_score"],
            "category": row["category"],
            "summary": row["summary"]
        }, ensure_ascii=False)

        samples.append({
            "conversations": [
                {"from": "human", "value": f"请分析这条新闻对投资的影响：{title}"},
                {"from": "gpt", "value": answer}
            ]
        })

        samples.append({
            "conversations": [
                {"from": "human", "value": f"这条新闻的相关性如何：{title}"},
                {"from": "gpt", "value": json.dumps({
                    "relevance_score": row["relevance_score"],
                    "category": row["category"]
                }, ensure_ascii=False)}
            ]
        })

    with open(output_file, 'a', encoding='utf-8') as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')

    return len(rows), len(samples)

def main():
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    if os.path.exists(OUTPUT):
        os.remove(OUTPUT)

    total_rows = 0
    total_samples = 0

    for db_file in sorted(Path(STORAGE_DIR, "news").glob("*.db")):
        rows, samples = export_from_db(str(db_file), "news_items", OUTPUT)
        print(f"  {db_file.name}: {rows} 条 → {samples} 个样本")
        total_rows += rows
        total_samples += samples

    for db_file in sorted(Path(STORAGE_DIR, "rss").glob("*.db")):
        rows, samples = export_from_db(str(db_file), "rss_items", OUTPUT)
        print(f"  {db_file.name}: {rows} 条 → {samples} 个样本")
        total_rows += rows
        total_samples += samples

    print(f"\n✅ 导出完成：{total_rows} 条数据 → {total_samples} 个训练样本")
    print(f"   文件：{OUTPUT}")

if __name__ == "__main__":
    main()
