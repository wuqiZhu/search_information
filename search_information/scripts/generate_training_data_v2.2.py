#!/usr/bin/env python3
"""
场景生成器 v2.2
修复：真实API密钥、种子提取兼容5种格式、净增打印、分类标签补全、种子采样扩大
"""
import json, os, requests, time, random, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

API_KEYS = [
    "tp-czlg508mettka4cw8ovzmnt4tnk7f5avzebx3syqki8i5cpy",
    "tp-c5uwgsuqzwfb6y997zqoutaxf1tl75b4ucbtwypya0vhkx99",
    "tp-cq3xrll333q4dpzejr9hw2nittorca8fdfox3ev60a8boxin",
    "tp-c14havddv668cnmffufilxydum6plsusqzoxigsc9dmobfl8",
]
API_URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
MODEL = "mimo-v2.5-pro"
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "train_scenarios_final.jsonl")
TARGET_SAMPLES = 150000
MAX_WORKERS = 20
_key_lock = threading.Lock()
_key_index = 0

def get_next_key():
    global _key_index
    with _key_lock:
        key = API_KEYS[_key_index % len(API_KEYS)]
        _key_index += 1
        return key

SEEDS_INITIAL = [
    "突发！某光伏龙头Q3净利润暴增340%",
    "震惊！知名基金经理清仓新能源",
    "重磅！央行突然降准0.5个百分点",
    "深夜公告：某芯片公司获国家大基金50亿注资",
    "炸裂！AI概念股批量涨停",
    "工信部等八部门联合印发《新型储能制造业高质量发展行动方案》，明确2027年装机目标",
    "美联储主席鲍威尔在杰克逊霍尔年会发表讲话：降息时机已到，但仍需警惕通胀反复",
    "北向资金连续7日净流入超600亿，创年内最长买入纪录，外资坚定看多中国资产",
    "某医药巨头ADC新药三期临床数据超预期，分析师上调目标价至300元",
    "两市成交额连续第10个交易日破万亿，券商股掀涨停潮",
    "3天涨20%，某低空经济概念股遭交易所问询",
    "5月新能源汽车出口量同比增长180%，比亚迪单月出口破10万辆",
    "某公司回购10亿元股份，占总股本2%，回购价上限较现价溢价40%",
    "茅台提价传闻再起，白酒板块集体异动，五粮液涨超5%",
    "宁德时代发布神行超充电池PLUS，充电10分钟续航800公里",
    "华为宣布开源鸿蒙PC版，信创板块应声大涨，中国软件涨停",
    "特斯拉FSD入华获批，自动驾驶概念股全线爆发，德赛西威封板",
    "某券商发布研报：当前A股估值处于历史低位，建议逢低布局",
    "中证协发布《证券公司数字化转型评估办法》，金融科技投入成硬指标",
    "全球半导体销售额连续8个月同比增长，行业复苏确认",
    "ETF规模突破2万亿，被动投资时代来临，沪深300ETF单日净流入超百亿",
    "某地产龙头预告半年亏损超200亿，债务重组方案仍未落地",
    "美国商务部将12家中国半导体企业列入实体清单，国产替代再提速",
    "国际油价暴跌7%创年内新低，OPEC+减产协议执行存疑",
    "某公司财务造假被证监会顶格处罚，董事长被终身市场禁入",
    "RISC-V架构服务器CPU首次进入运营商集采，平头哥倚天710入围",
    "低代码开发平台赛道融资火热，今年已有7家获亿元级投资",
]

ALL_CATEGORIES = "03-政策福利|04-行业动态|05-长期杠杆|06-嵌入式Linux|07-BSP开发|08-设备驱动|09-RISC-V|10-IoT|其他"


def call_mimo(prompt, max_tokens=500, temperature=0.8):
    api_key = get_next_key()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    for attempt in range(5):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"  429限流，等待{wait}秒...", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "")
                if content and content.strip():
                    return content.strip()
                reasoning = msg.get("reasoning_content", "")
                if reasoning and reasoning.strip():
                    return reasoning.strip()
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
    results = []
    try:
        start = text.find('[')
        end = text.rfind(']') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except:
        pass
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


def generate_titles(seed, count=30):
    prompt = f"""你是财经记者。基于以下新闻种子，生成{count}条不同角度、不同表述风格的新闻标题。
要求：有的短（15字以内），有的长（多信息点）；有的带数字，有的带情绪词（突发/震惊/重磅）；有的提具体公司/股票名称；涵盖正面、负面、中性三种情绪。
输出JSON数组，每项只有title字段：[{{"title": "..."}}, ...]

种子：{seed}"""
    resp = call_mimo(prompt, max_tokens=2000, temperature=0.9)
    parsed = parse_json_array(resp)
    titles = []
    for t in parsed:
        if isinstance(t, dict) and t.get("title"):
            titles.append(t["title"])
        elif isinstance(t, str) and len(t) > 3:
            titles.append(t)
        elif isinstance(t, list):
            for item in t:
                if isinstance(item, dict) and item.get("title"):
                    titles.append(item["title"])
                elif isinstance(item, str) and len(item) > 3:
                    titles.append(item)
    return titles


def annotate_batch(titles):
    title_list = "\n".join([f"{i+1}. {t}" for i, t in enumerate(titles)])
    prompt = f"""你是金融数据标注专家。对以下{len(titles)}条新闻标题，逐条输出JSON数组：
[{{"title":"原标题","sentiment":"positive|negative|neutral","sentiment_score":0.0-1.0,"relevance_score":0-10,"category":"{ALL_CATEGORIES}","summary":"摘要30字以内","impact":"1-3个月投资影响50字以内"}},...]

{title_list}"""
    resp = call_mimo(prompt, max_tokens=2000, temperature=0.1)
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
        samples.append({"conversations": [
            {"from": "human", "value": f"判断新闻情绪：正面、负面、中性。\n新闻：{title}"},
            {"from": "gpt", "value": sentiment}
        ]})
        samples.append({"conversations": [
            {"from": "human", "value": f"评估投资相关性，打分0-10。\n内容：{title}"},
            {"from": "gpt", "value": str(score)}
        ]})
        samples.append({"conversations": [
            {"from": "human", "value": f"将新闻分类：{ALL_CATEGORIES}\n新闻：{title}"},
            {"from": "gpt", "value": category}
        ]})
        samples.append({"conversations": [
            {"from": "human", "value": f"用一句话总结，不超过30字。\n新闻：{title}"},
            {"from": "gpt", "value": summary}
        ]})
        if impact:
            samples.append({"conversations": [
                {"from": "human", "value": f"分析以下新闻对A股相关板块的1-3个月投资影响。\n新闻：{title}"},
                {"from": "gpt", "value": impact}
            ]})
    return samples


def extract_title_from_sample(sample):
    user_msg = sample["conversations"][0]["value"]
    separators = ["\n新闻：", "\n内容：", "\n新闻: ", "\n内容: "]
    for sep in separators:
        if sep in user_msg:
            return user_msg.split(sep, 1)[1].strip()
    lines = user_msg.strip().split("\n")
    if len(lines) > 1:
        return lines[-1].strip()
    return ""


def process_seed(seed):
    print(f"  种子: {seed[:50]}...", flush=True)
    titles = generate_titles(seed, count=30)
    if not titles:
        return []
    all_annotated = []
    for i in range(0, len(titles), 8):
        batch = titles[i:i+8]
        annotated = annotate_batch(batch)
        all_annotated.extend(annotated)
    samples = convert_to_training(all_annotated)
    print(f"    完成 {len(titles)}条新闻 -> {len(samples)}条样本", flush=True)
    return samples


if __name__ == "__main__":
    print(f"场景生成器 v2.2 启动", flush=True)
    print(f"目标: {TARGET_SAMPLES} 条样本 | 并发: {MAX_WORKERS} 线程", flush=True)

    all_samples = []
    if os.path.exists(OUTPUT):
        with open(OUTPUT, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        all_samples.append(json.loads(line))
                    except:
                        pass
        print(f"断点续跑：已加载 {len(all_samples)} 条历史样本", flush=True)

    SEEDS = SEEDS_INITIAL[:]
    round_num = 0
    prev_count = len(all_samples)

    while len(all_samples) < TARGET_SAMPLES:
        round_num += 1
        print(f"\n--- 第 {round_num} 轮（种子: {len(SEEDS)}个） ---", flush=True)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(process_seed, seed): seed for seed in SEEDS}
            for future in as_completed(futures):
                all_samples.extend(future.result())

        seen = set()
        unique = []
        for s in all_samples:
            key = s["conversations"][0]["value"]
            if key not in seen:
                seen.add(key)
                unique.append(s)
        all_samples = unique

        with open(OUTPUT, 'w', encoding='utf-8') as f:
            for s in all_samples:
                f.write(json.dumps(s, ensure_ascii=False) + '\n')

        current = len(all_samples)
        delta = current - prev_count
        prev_count = current
        print(f"本轮净增: {delta} 条 | 累计: {current} 条", flush=True)

        if current >= TARGET_SAMPLES:
            break

        if current > 50:
            random.seed(round_num)
            sample_size = min(200, current)
            candidates = random.sample(all_samples, sample_size)
            new_seeds = []
            for s in candidates:
                title = extract_title_from_sample(s)
                if len(title) > 10:
                    new_seeds.append(title)
            SEEDS = list(set(new_seeds))[:40]
            if not SEEDS:
                SEEDS = SEEDS_INITIAL[:]
            print(f"  下一轮种子: {len(SEEDS)} 个", flush=True)

    all_samples = all_samples[:TARGET_SAMPLES]
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        for s in all_samples:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')

    print(f"\n完成！最终: {len(all_samples)} 条", flush=True)
    print(f"输出: {OUTPUT}", flush=True)
