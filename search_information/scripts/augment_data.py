#!/usr/bin/env python3
import json
import requests
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

INPUT = "/root/projects/search_information/search_information/scripts/train_invest.jsonl"
OUTPUT = "/root/projects/search_information/search_information/scripts/train_invest_augmented.jsonl"
API_KEY = os.getenv("MIMO_API_KEY")
API_URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
MODEL = "mimo-v2.5-pro"

def log(msg):
    print(msg, flush=True)

def augment(sample):
    original = sample["conversations"][0]["value"]
    answer = sample["conversations"][1]["value"]

    prompt = f"""请改写以下问题，保持含义不变但用不同的表述方式。直接输出改写后的问题，不要解释。

原问题：{original}

改写后的问题："""

    for attempt in range(3):
        try:
            resp = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": [
                    {"role": "user", "content": prompt}
                ], "max_tokens": 200, "temperature": 0.8},
                timeout=30
            )
            if resp.status_code == 429:
                time.sleep(30 * (attempt + 1))
                continue
            resp.raise_for_status()
            new_q = resp.json()["choices"][0]["message"]["content"]
            if new_q:
                return {"conversations": [{"from": "human", "value": new_q.strip()}, {"from": "gpt", "value": answer}]}
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return None

def main():
    if not API_KEY:
        log("错误: MIMO_API_KEY 环境变量未设置")
        return

    with open(INPUT) as f:
        data = [json.loads(line) for line in f]

    log(f"原始数据: {len(data)} 条")
    log(f"将生成 {len(data) * 5} 个变体")

    augmented = []
    total = len(data) * 5
    batch_size = 50

    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_futures = []

        with ThreadPoolExecutor(max_workers=10) as ex:
            for i in range(batch_start, batch_end):
                sample_idx = i // 5
                if sample_idx < len(data):
                    batch_futures.append(ex.submit(augment, data[sample_idx]))

            for f in as_completed(batch_futures):
                try:
                    result = f.result()
                    if result:
                        augmented.append(result)
                except:
                    pass

        log(f"进度: {batch_end}/{total} (成功 {len(augmented)})")

    all_data = data + augmented
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        for s in all_data:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')

    log(f"\n✅ 增强完成：{len(data)} → {len(all_data)} 条（含 {len(augmented)} 个变体）")
    log(f"   文件：{OUTPUT}")

if __name__ == "__main__":
    main()
