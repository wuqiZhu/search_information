#!/usr/bin/env python3
"""
场景生成器 v3.2 —— 内存安全 + 密钥安全 + 逻辑健壮
分块去重 / 分批请求 / 多模式种子提取 / 条件推理输出
"""
import json, os, time, random, threading, gc
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

API_KEYS = [
    "tp-c5uwgsuqzwfb6y997zqoutaxf1tl75b4ucbtwypya0vhkx99",
    "tp-cq3xrll333q4dpzejr9hw2nittorca8fdfox3ev60a8boxin",
    "tp-c14havddv668cnmffufilxydum6plsusqzoxigsc9dmobfl8",
    "tp-cz1tm0cz7o5tehygq0be60pmkdfnbhcakvqnkddnvn8ske8o",
]
API_URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
MODEL = "mimo-v2.5-pro"
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "train_scenarios_v3.2.jsonl")
TARGET_SAMPLES = 5_000_000
MAX_WORKERS = 8
CHUNK_SIZE = 100_000

_key_lock = threading.Lock()
_key_index = 0

def get_api_key():
    global _key_index
    with _key_lock:
        key = API_KEYS[_key_index % len(API_KEYS)]
        _key_index += 1
        return key

ALL_CATEGORIES = [
    "03-政策福利", "04-行业动态", "05-长期杠杆",
    "06-嵌入式Linux", "07-BSP开发", "08-设备驱动",
    "09-RISC-V", "10-IoT", "其他"
]

CATEGORY_SEEDS = {
    "政策利好": ["降准", "减税", "补贴", "新基建", "自贸区", "碳中和政策", "数据要素", "东数西算", "注册制改革", "专精特新"],
    "政策利空": ["反垄断", "行业整顿", "加税", "环保限产", "安全审查", "出口管制", "数据安全法", "教培双减", "平台经济监管"],
    "行业景气": ["AI大模型", "智能驾驶", "光伏", "储能", "半导体", "CXO", "创新药", "机器人", "低空经济", "商业航天"],
    "公司事件": ["业绩暴增", "大额合同", "回购", "增持", "IPO", "并购重组", "暴雷", "财务造假", "ST退市", "股权激励"],
    "国际市场": ["美联储加息", "中美关系", "油价波动", "汇率变动", "新兴市场", "全球供应链", "地缘冲突", "大宗商品", "美股财报", "港股通"],
    "资金面": ["北向资金", "两融余额", "ETF流入", "公募发行", "量化交易", "雪球产品", "GJD入场", "险资入市", "外资流向", "南下资金"],
    "情绪与舆论": ["涨停潮", "跌停潮", "恐慌指数", "散户入场", "大V唱多", "机构调研", "龙虎榜", "微博热搜", "雪球热帖", "抖音荐股"]
}


def call_mimo(prompt, max_tokens=800, temperature=0.8):
    key = get_api_key()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    for attempt in range(5):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=90)
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"  429限流，等待{wait}秒...", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            choices = resp.json().get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "") or ""
                reasoning = msg.get("reasoning_content", "") or ""
                text = content.strip() if content.strip() else reasoning.strip()
                if text:
                    return text
            return None
        except requests.exceptions.Timeout:
            print(f"  超时，重试{attempt+1}/5", flush=True)
            time.sleep(5)
        except Exception as e:
            print(f"  API错误: {e}", flush=True)
            time.sleep(3 * (attempt + 1))
    return None


def parse_json_array(text):
    if not text:
        return []
    try:
        start = text.find('[')
        end = text.rfind(']') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except:
        pass
    results = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx] not in '{[':
            idx += 1
        if idx >= len(text):
            break
        try:
            obj, end_idx = decoder.raw_decode(text, idx)
            results.append(obj)
            idx = end_idx
        except:
            idx += 1
    return results


def generate_seeds():
    all_seeds = []
    for category, keywords in CATEGORY_SEEDS.items():
        kw_list = "、".join(keywords)
        cat_seeds = []
        attempts = 0
        while len(cat_seeds) < 300 and attempts < 10:
            prompt = f"""针对"{category}"，围绕关键词{kw_list}，生成50个高度具体的财经新闻标题。
要求：像真实新闻，包含具体公司名/数据/日期，风格多变。
直接输出JSON数组：[{{"title":"..."}}, ...]"""
            resp = call_mimo(prompt, max_tokens=2500, temperature=0.9)
            titles = [t.get("title", "") for t in parse_json_array(resp) if t.get("title")]
            cat_seeds.extend(titles)
            attempts += 1
        all_seeds.extend(cat_seeds[:300])
        print(f"  {category} -> {len(cat_seeds)} 个种子", flush=True)
    return all_seeds


def generate_titles(seed, count=50):
    prompt = f"""基于以下种子，生成{count}条角度各异的财经新闻标题。
直接输出JSON数组：[{{"title":"..."}}, ...]
种子：{seed}"""
    resp = call_mimo(prompt, max_tokens=2500, temperature=0.9)
    return [t.get("title", "") for t in parse_json_array(resp) if t.get("title")]


def annotate_batch(titles):
    title_list = "\n".join([f"{i+1}. {t}" for i, t in enumerate(titles)])
    cats = "、".join(ALL_CATEGORIES)
    prompt = f"""深度分析以下{len(titles)}条新闻，逐条输出JSON数组：
[{{"title":"原标题","sentiment":"positive|negative|neutral","sentiment_score":0.0-1.0,"relevance_score":0-10,"category":"{cats}","summary":"摘要30字以内","impact":"投资影响50字以内","reasoning":"推理过程100字以内"}},...]
{title_list}"""
    resp = call_mimo(prompt, max_tokens=3000, temperature=0.1)
    return parse_json_array(resp)


def convert_to_training(items):
    samples = []
    for item in items:
        title = item.get("title", "").strip()
        if len(title) < 5:
            continue
        sentiment = item.get("sentiment", "neutral")
        score = item.get("relevance_score", 5)
        category = item.get("category", "其他")
        summary = item.get("summary", title[:30])
        impact = item.get("impact", "")
        reasoning = item.get("reasoning", "")

        if reasoning:
            samples.append({"conversations": [
                {"from": "human", "value": f"判断新闻情绪并推理。\n新闻：{title}"},
                {"from": "gpt", "value": f"{sentiment}。理由：{reasoning}"}
            ]})
        else:
            samples.append({"conversations": [
                {"from": "human", "value": f"判断新闻情绪：正面、负面、中性。\n新闻：{title}"},
                {"from": "gpt", "value": sentiment}
            ]})

        if reasoning:
            samples.append({"conversations": [
                {"from": "human", "value": f"评估投资相关性并解释。\n内容：{title}"},
                {"from": "gpt", "value": f"{score}分。{reasoning}"}
            ]})
        else:
            samples.append({"conversations": [
                {"from": "human", "value": f"评估投资相关性，打分0-10。\n内容：{title}"},
                {"from": "gpt", "value": str(score)}
            ]})

        cats = "、".join(ALL_CATEGORIES)
        samples.append({"conversations": [
            {"from": "human", "value": f"新闻分类：{cats}\n新闻：{title}"},
            {"from": "gpt", "value": category}
        ]})

        samples.append({"conversations": [
            {"from": "human", "value": f"一句话总结，不超过30字。\n新闻：{title}"},
            {"from": "gpt", "value": summary}
        ]})

        if impact:
            samples.append({"conversations": [
                {"from": "human", "value": f"分析1-3个月投资影响。\n新闻：{title}"},
                {"from": "gpt", "value": impact}
            ]})
    return samples


def process_seed(seed):
    titles = generate_titles(seed, count=50)
    if not titles:
        return []
    annotated = []
    for i in range(0, len(titles), 8):
        batch = titles[i:i+8]
        annotated.extend(annotate_batch(batch))
    return convert_to_training(annotated)


def extract_title(sample):
    text = sample["conversations"][0]["value"]
    for sep in ["\n新闻：", "\n内容：", "\n新闻: ", "\n内容: "]:
        if sep in text:
            return text.split(sep, 1)[-1].strip()
    lines = text.strip().split("\n")
    if len(lines) > 1:
        return lines[-1].strip()
    return ""


def merge_and_deduplicate(main_file, new_samples):
    if not new_samples:
        return 0
    new_keys = {s["conversations"][0]["value"] for s in new_samples}
    if os.path.exists(main_file):
        with open(main_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    old_key = json.loads(line.strip())["conversations"][0]["value"]
                    new_keys.discard(old_key)
                except:
                    pass
    added = 0
    with open(main_file, 'a', encoding='utf-8') as f:
        for s in new_samples:
            if s["conversations"][0]["value"] in new_keys:
                f.write(json.dumps(s, ensure_ascii=False) + '\n')
                added += 1
    return added


if __name__ == "__main__":
    print("场景生成器 v3.2 启动（内存安全版）", flush=True)
    print(f"目标: {TARGET_SAMPLES} 样本 | 密钥: {len(API_KEYS)}个 | 线程: {MAX_WORKERS}", flush=True)
    print(f"输出: {OUTPUT}", flush=True)

    seeds = generate_seeds()
    print(f"种子总数: {len(seeds)}", flush=True)

    total_samples = 0
    if os.path.exists(OUTPUT):
        with open(OUTPUT, 'r', encoding='utf-8') as f:
            total_samples = sum(1 for _ in f)
    print(f"已有样本: {total_samples}", flush=True)

    round_num = 0
    while total_samples < TARGET_SAMPLES:
        round_num += 1
        print(f"\n--- 第 {round_num} 轮 ---", flush=True)

        new_samples = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(process_seed, s): s for s in seeds}
            for future in as_completed(futures):
                new_samples.extend(future.result())
                if len(new_samples) >= CHUNK_SIZE:
                    added = merge_and_deduplicate(OUTPUT, new_samples)
                    total_samples += added
                    print(f"  分块合并: +{added} | 累计: {total_samples}", flush=True)
                    new_samples.clear()
                    gc.collect()

        if new_samples:
            added = merge_and_deduplicate(OUTPUT, new_samples)
            total_samples += added
            print(f"  最终合并: +{added} | 累计: {total_samples}", flush=True)

        if total_samples >= TARGET_SAMPLES:
            break

        if total_samples > 500:
            with open(OUTPUT, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-1000:]
            recent_samples = [json.loads(line.strip()) for line in lines if line.strip()]
            new_seeds = list({extract_title(s) for s in recent_samples if len(extract_title(s)) > 10})
            if new_seeds:
                seeds = random.sample(new_seeds, min(500, len(new_seeds)))
                print(f"  下一轮种子: {len(seeds)} 个", flush=True)

    print(f"\n完成！总样本: {total_samples}", flush=True)
    print(f"输出: {OUTPUT}", flush=True)
