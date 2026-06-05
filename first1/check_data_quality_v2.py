# -*- coding: utf-8 -*-
"""
训练数据质量检查脚本 v2（增强版）
在阿里云服务器上运行: python3 check_data_quality_v2.py

增强功能：
  1. 近重复检测（N-gram Jaccard 相似度 + MinHash）
  2. 按任务类型分别统计质量
  3. 回复内容质量评分（词汇多样性、信息密度）
  4. 种子多样性追踪
  5. 生成 HTML 可视化报告
  6. 输出过滤后的数据子集
"""

import json
import hashlib
import re
import os
import sys
import math
from collections import Counter, defaultdict
from datetime import datetime

# ====== 配置 ======
DATA_FILE = "/root/train_scenarios_v2.2.jsonl"
OUTPUT_DIR = "/root/data_quality_report"
MIN_RESPONSE_LENGTH = 5       # 低于此长度视为低信息量
SHINGLE_SIZE = 3              # 近重复检测的 shingle 大小
NEAR_DUP_THRESHOLD = 0.85     # Jaccard 相似度阈值
SAMPLE_CHECK = 100000         # 近重复检测的采样数（数据太大时会很慢）

# ====== 任务类型识别模式 ======
TASK_PATTERNS = [
    ("情绪分析", ["判断.*情绪", "正面.*负面.*中性", "sentiment"]),
    ("相关性打分", ["评估.*相关性", "打分.*0-10", "相关性.*评分", "relevance"]),
    ("新闻分类", ["分类", "归类", "category"]),
    ("摘要生成", ["一句话总结", "不超过.*字", "摘要"]),
    ("投资影响", ["投资影响", ".*个月.*影响", "impact"]),
    ("深度分析", ["详细分析", "深度分析", "全面分析", "分析报告"]),
    ("投资建议", ["投资建议", "买入.*卖出.*持有", "操作建议"]),
    ("风险提示", ["风险", "风险提示", "注意.*风险"]),
    ("行业对比", ["对比", "比较.*行业", "行业.*差异"]),
    ("技术分析", ["技术面", "K线", "均线", "MACD", "RSI"]),
    ("宏观解读", ["宏观", "政策解读", "经济数据"]),
    ("多股对比", ["对比.*股票", "比较.*公司", "选股"]),
    ("数据解读", ["解读.*数据", "财报解读", "指标分析"]),
    ("问答对话", ["问.*答", "对话", "讨论"]),
    ("事件影响链", ["影响.*链", "传导.*路径", "连锁反应"]),
]


def identify_task(instruction: str) -> str:
    """根据 instruction 识别任务类型"""
    for task_name, patterns in TASK_PATTERNS:
        for p in patterns:
            if re.search(p, instruction, re.IGNORECASE):
                return task_name
    return "其他"


def load_data():
    data = []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                data.append(json.loads(line.strip()))
            except:
                continue
    return data


# ==================== 1. 精确重复检测 ====================

def check_exact_duplicates(data):
    seen = set()
    duplicates = 0
    for item in data:
        key = json.dumps(item["conversations"], sort_keys=True, ensure_ascii=False)
        h = hashlib.md5(key.encode()).hexdigest()
        if h in seen:
            duplicates += 1
        else:
            seen.add(h)
    return len(data), duplicates, len(seen)


# ==================== 2. 近重复检测（N-gram Jaccard） ====================

def shingle(text: str, k: int) -> set:
    """将文本转为 k-shingle 集合"""
    text = re.sub(r'\s+', '', text.lower())  # 去空白、小写
    if len(text) < k:
        return {text}
    return {text[i:i+k] for i in range(len(text) - k + 1)}


def jaccard_similarity(set1: set, set2: set) -> float:
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def check_near_duplicates(data, sample_size=SAMPLE_CHECK):
    """检测近重复样本（采样执行，避免 OOM）"""
    if len(data) > sample_size:
        data = data[:sample_size]

    # 只取 assistant 回复做比较
    responses = []
    for item in data:
        for msg in item["conversations"]:
            if msg["from"] == "gpt":
                responses.append(msg["value"])
                break
        else:
            responses.append("")

    # 计算 shingle
    shingles = []
    for r in responses:
        shingles.append(shingle(r, SHINGLE_SIZE))

    # 配对检测（采样后数据量大时仍可能很慢，限制比较次数）
    near_duplicate_pairs = []
    max_compare = min(5000, len(data))  # 最多比较 5000 条
    for i in range(max_compare):
        for j in range(i + 1, max_compare):
            if len(shingles[i]) > 0 and len(shingles[j]) > 0:
                sim = jaccard_similarity(shingles[i], shingles[j])
                if sim >= NEAR_DUP_THRESHOLD:
                    near_duplicate_pairs.append({
                        "idx1": i,
                        "idx2": j,
                        "similarity": round(sim, 4),
                        "resp1_preview": responses[i][:80],
                        "resp2_preview": responses[j][:80],
                    })

    return near_duplicate_pairs


# ==================== 3. 按任务类型统计 ====================

def analyze_by_task(data):
    """按任务类型拆分统计"""
    task_stats = defaultdict(lambda: {
        "count": 0,
        "lengths": [],
        "low_info": 0,
        "vocab_diversity": [],
    })

    for item in data:
        human_msg = ""
        gpt_msg = ""
        for msg in item["conversations"]:
            if msg["from"] == "human":
                human_msg = msg["value"]
            elif msg["from"] == "gpt":
                gpt_msg = msg["value"]

        task = identify_task(human_msg)
        task_stats[task]["count"] += 1
        task_stats[task]["lengths"].append(len(gpt_msg))
        if len(gpt_msg) < MIN_RESPONSE_LENGTH:
            task_stats[task]["low_info"] += 1
        # 词汇多样性（去重字符 / 总字符）
        unique_chars = len(set(gpt_msg))
        total_chars = max(len(gpt_msg), 1)
        task_stats[task]["vocab_diversity"].append(unique_chars / total_chars)

    # 汇总
    summary = {}
    for task, stats in sorted(task_stats.items(), key=lambda x: -x[1]["count"]):
        lengths = stats["lengths"]
        avg_len = sum(lengths) / len(lengths) if lengths else 0
        max_len = max(lengths) if lengths else 0
        min_len = min(lengths) if lengths else 0
        avg_diversity = (sum(stats["vocab_diversity"]) / len(stats["vocab_diversity"])
                         if stats["vocab_diversity"] else 0)

        summary[task] = {
            "count": stats["count"],
            "pct": round(stats["count"] / len(data) * 100, 2),
            "avg_length": round(avg_len, 1),
            "min_length": min_len,
            "max_length": max_len,
            "low_info_pct": round(stats["low_info"] / stats["count"] * 100, 2),
            "vocab_diversity": round(avg_diversity, 4),
        }

    return summary


# ==================== 4. 种子多样性探测 ====================

def detect_seed_patterns(data):
    """检测是否来自少量种子 → 输出多样性低"""
    human_messages = []
    for item in data:
        for msg in item["conversations"]:
            if msg["from"] == "human":
                human_messages.append(msg["value"])
                break

    # 提取指令模板（去掉具体新闻内容后的骨架）
    template_pattern = re.compile(r"^(.*?)[：:]\s*\n(.+)$", re.MULTILINE)
    templates = Counter()
    for msg in human_messages:
        # 提取问题前半部分作为模板签名
        lines = msg.strip().split("\n")
        if lines:
            template_sig = lines[0][:50]  # 取第一行前50字符
            templates[template_sig] += 1

    # 输出 Top-10 指令模板
    top_templates = templates.most_common(15)
    template_entropy = calculate_entropy([t[1] for t in top_templates])

    return {
        "total_templates": len(templates),
        "top15_pct": sum(t[1] for t in top_templates) / len(human_messages) * 100,
        "template_entropy": round(template_entropy, 4),
        "top_templates": [{"prefix": t[0][:60], "count": t[1]} for t in top_templates],
    }


def calculate_entropy(counts):
    """计算分布的熵（越高越多样）"""
    total = sum(counts)
    if total == 0:
        return 0
    entropy = 0
    for c in counts:
        p = c / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


# ==================== 5. 内容质量评分 ====================

def score_response_quality(gpt_msg: str) -> dict:
    """对一条回复进行质量评分"""
    score = 0
    details = []

    # 1. 长度基础分（最高50分）
    length = len(gpt_msg)
    if length < 5:
        return {"total": 0, "details": {"长度": 0, "词汇": 0, "信息": 0, "结构": 0, "领域词": 0}}
    length_score = min(50, length / 10)  # 500字符以上满分
    details.append(("长度", round(length_score, 1)))

    # 2. 词汇多样性（最高15分）
    unique_chars = len(set(gpt_msg))
    diversity = unique_chars / max(length, 1)
    diversity_score = min(15, diversity * 40)
    details.append(("词汇", round(diversity_score, 1)))

    # 3. 信息密度（最高15分）
    info_markers = ["%", "亿", "万", "元", "增长", "下降", "比", "率",
                    "第", "超", "达", "涨", "跌", "同比", "环比", "百分点"]
    info_count = sum(1 for m in info_markers if m in gpt_msg)
    info_score = min(15, info_count * 3)
    details.append(("信息", round(info_score, 1)))

    # 4. 结构完整性（最高10分）
    structural_markers = ["首先", "其次", "最后", "第一", "第二", "第",
                          "总体", "综合", "综上", "一、", "二、", "1.", "2.",
                          "背景", "分析", "结论", "建议", "风险"]
    struct_count = sum(1 for m in structural_markers if m in gpt_msg)
    struct_score = min(10, struct_count * 2)
    details.append(("结构", round(struct_score, 1)))

    # 5. 领域关键词（最高10分）
    domain_keywords = ["A股", "港股", "美股", "板块", "行业", "个股", "市场",
                       "投资", "风险", "收益", "估值", "PE", "PB", "ROE",
                       "净利润", "营收", "毛利率", "现金流", "负债"]
    domain_count = sum(1 for k in domain_keywords if k in gpt_msg)
    domain_score = min(10, domain_count)
    details.append(("领域词", round(domain_score, 1)))

    total = length_score + diversity_score + info_score + struct_score + domain_score
    return {
        "total": round(total, 1),
        "details": {k: v for k, v in details},
    }


def analyze_quality_distribution(data, sample_size=50000):
    """分析整体回复质量分布"""
    if len(data) > sample_size:
        data = data[:sample_size]

    qualities = []
    for item in data:
        for msg in item["conversations"]:
            if msg["from"] == "gpt":
                quality = score_response_quality(msg["value"])
                qualities.append(quality["total"])
                break

    if not qualities:
        return {"avg": 0, "buckets": {}}

    buckets = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
    for q in qualities:
        if q <= 20:
            buckets["0-20"] += 1
        elif q <= 40:
            buckets["20-40"] += 1
        elif q <= 60:
            buckets["40-60"] += 1
        elif q <= 80:
            buckets["60-80"] += 1
        else:
            buckets["80-100"] += 1

    return {
        "avg_score": round(sum(qualities) / len(qualities), 1),
        "sample_size": len(qualities),
        "distribution": {k: round(v / len(qualities) * 100, 1) for k, v in buckets.items()},
    }


# ==================== 6. 输出过滤后的数据 ====================

def save_filtered_data(data, output_path):
    """去掉低信息量样本，输出清洗后的数据"""
    filtered = []
    removed_count = 0

    for item in data:
        keep = True
        for msg in item["conversations"]:
            if msg["from"] == "gpt" and len(msg["value"]) < MIN_RESPONSE_LENGTH:
                keep = False
                break
        if keep:
            filtered.append(item)
        else:
            removed_count += 1

    with open(output_path, "w", encoding="utf-8") as f:
        for item in filtered:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return len(filtered), removed_count


# ==================== 7. 生成 HTML 报告 ====================

def generate_html_report(results, output_path):
    """生成可视化 HTML 报告"""
    task = results["task_analysis"]
    domain = results["domain_stats"]
    instruction = results["instruction_stats"]

    # 构建任务类型分布表格行
    task_rows = ""
    for t, s in task.items():
        bar_width = min(s["pct"] * 3, 100)
        task_rows += f"""
        <tr>
            <td>{t}</td>
            <td>{s['count']:,}</td>
            <td>{s['pct']}%</td>
            <td>{s['avg_length']}</td>
            <td>{s['max_length']}</td>
            <td>{s['low_info_pct']}%</td>
            <td>{s['vocab_diversity']}</td>
            <td><div class="bar" style="width:{bar_width}px"></div></td>
        </tr>"""

    domain_rows = ""
    for d, c in sorted(domain.items(), key=lambda x: -x[1]):
        pct = c / results["total"] * 100
        bar_width = min(pct * 3, 100)
        domain_rows += f"""
        <tr>
            <td>{d}</td>
            <td>{c:,}</td>
            <td>{pct:.1f}%</td>
            <td><div class="bar" style="width:{bar_width}px"></div></td>
        </tr>"""

    inst_rows = ""
    for t, c in sorted(instruction.items(), key=lambda x: -x[1]):
        pct = c / results["total"] * 100
        bar_width = min(pct * 2, 100)
        inst_rows += f"""
        <tr>
            <td>{t}</td>
            <td>{c:,}</td>
            <td>{pct:.1f}%</td>
            <td><div class="bar" style="width:{bar_width}px"></div></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>训练数据质量检查报告</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px; background: #f5f5f5; }}
        h1 {{ color: #333; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .card {{ background: white; border-radius: 8px; padding: 20px; margin: 15px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
        .metric .value {{ font-size: 28px; font-weight: bold; color: #1a73e8; }}
        .metric .label {{ font-size: 14px; color: #666; }}
        .pass {{ color: #0d8a3f; }}
        .warn {{ color: #e67e22; }}
        .fail {{ color: #d32f2f; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #eee; font-size: 14px; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        .bar {{ height: 16px; background: #1a73e8; border-radius: 3px; }}
        .bar.warn {{ background: #e67e22; }}
        .bar.fail {{ background: #d32f2f; }}
        .summary-box {{ background: #e8f0fe; border-left: 4px solid #1a73e8; padding: 15px; margin: 15px 0; border-radius: 4px; }}
        .timestamp {{ color: #999; font-size: 12px; }}
    </style>
</head>
<body>
<div class="container">
    <h1>📊 训练数据质量检查报告</h1>
    <p class="timestamp">生成时间: {results['timestamp']}</p>

    <div class="card">
        <h2>📈 概览</h2>
        <div class="metric"><span class="value">{results['total']:,}</span><div class="label">总样本</div></div>
        <div class="metric"><span class="value">{results['duplicates']:,}</span><div class="label">重复</div></div>
        <div class="metric"><span class="value">{results['unique']:,}</span><div class="label">去重后</div></div>
        <div class="metric">
            <span class="value {'pass' if results['dup_rate'] < 10 else 'fail'}">{results['dup_rate']:.2f}%</span>
            <div class="label">重复率 {'✅' if results['dup_rate'] < 10 else '❌'}</div>
        </div>
        <div class="metric">
            <span class="value">{results['avg_length']}</span>
            <div class="label">平均回复长度(字符) {'⚠️ 太短!' if results['avg_length'] < 200 else '✅'}</div>
        </div>
        <div class="metric">
            <span class="value">{results['low_info_pct']:.1f}%</span>
            <div class="label">低信息量占比 {'⚠️ 偏高!' if results['low_info_pct'] > 10 else '✅'}</div>
        </div>
    </div>

    <div class="card">
        <h2>📐 长度分布</h2>
        <table>
            <tr><th>区间</th><th>数量</th><th>占比</th><th></th></tr>
            {''.join(f'<tr><td>{b}</td><td>{c:,}</td><td>{results["length_dist"][b]}%</td><td><div class="bar {"fail" if b in ["0-50","51-100"] else "warn" if b == "101-200" else "pass"}" style="width:{min(results["length_dist"][b]*2,100)}px"></div></td></tr>' for b, c in sorted(results['length_dist_raw'].items()))}
        </table>
        <p>最长: {results['max_length']} 字符 | 最短: {results['min_length']} 字符</p>
    </div>

    <div class="card">
        <h2>🎯 按任务类型分析</h2>
        <table>
            <tr><th>任务类型</th><th>数量</th><th>占比</th><th>平均长度</th><th>最大长度</th><th>低信息%</th><th>词汇多样性</th><th></th></tr>
            {task_rows}
        </table>
    </div>

    <div class="card">
        <h2>🏢 领域覆盖</h2>
        <table>
            <tr><th>领域</th><th>命中数</th><th>占比</th><th></th></tr>
            {domain_rows}
        </table>
    </div>

    <div class="card">
        <h2>📋 指令类型分布</h2>
        <table>
            <tr><th>类型</th><th>数量</th><th>占比</th><th></th></tr>
            {inst_rows}
        </table>
    </div>

    <div class="card">
        <h2>💡 内容质量评分</h2>
        <p>平均分: <strong>{results['quality_score']['avg_score']}</strong> / 100（采样{results['quality_score']['sample_size']:,}条）</p>
        <table>
            <tr><th>评分区间</th><th>占比</th><th></th></tr>
            {''.join(f'<tr><td>{b}</td><td>{v}%</td><td><div class="bar {"fail" if b in ["0-20","20-40"] else "warn" if b == "40-60" else "pass"}" style="width:{min(v*2,100)}px"></div></td></tr>' for b, v in sorted(results['quality_score']['distribution'].items()))}
        </table>
    </div>

    <div class="card">
        <h2>🔄 种子/模板多样性</h2>
        <div class="metric"><span class="value">{results['seed_diversity']['total_templates']}</span><div class="label">指令模板种类</div></div>
        <div class="metric"><span class="value">{results['seed_diversity']['template_entropy']}</span><div class="label">模板熵</div></div>
        <table>
            <tr><th>Top 指令模板</th><th>出现次数</th></tr>
            {''.join(f'<tr><td><code>{t["prefix"]}...</code></td><td>{t["count"]:,}</td></tr>' for t in results['seed_diversity']['top_templates'][:8])}
        </table>
    </div>

    <div class="card">
        <h2>⚠️ 建议</h2>
        <ul>
            {''.join(f'<li>{sug}</li>' for sug in results['suggestions'])}
        </ul>
    </div>
</div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"HTML 报告已保存: {output_path}")


# ==================== 8. 主流程 ====================

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("训练数据质量检查报告 v2（增强版）")
    print("=" * 60)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n[1/8] 加载数据...")
    data = load_data()
    total = len(data)
    print(f"总样本数: {total:,}")

    print(f"\n[2/8] 精确重复检测...")
    _, duplicates, unique = check_exact_duplicates(data)
    dup_rate = duplicates / total * 100 if total > 0 else 0
    print(f"重复: {duplicates:,} | 去重后: {unique:,} | 重复率: {dup_rate:.2f}%")

    print(f"\n[3/8] 近重复检测（采样 {min(SAMPLE_CHECK, total):,} 条）...")
    near_dups = check_near_duplicates(data)
    print(f"近重复对: {len(near_dups)} 对")
    if near_dups:
        for nd in near_dups[:3]:
            print(f"  相似度 {nd['similarity']}: {nd['resp1_preview'][:50]} <-> {nd['resp2_preview'][:50]}")

    print(f"\n[4/8] 长度分布分析...")
    lengths = []
    low_info_count = 0
    for item in data:
        for msg in item["conversations"]:
            if msg["from"] == "gpt":
                l = len(msg["value"])
                lengths.append(l)
                if l < MIN_RESPONSE_LENGTH:
                    low_info_count += 1
                break

    avg_length = sum(lengths) / len(lengths) if lengths else 0
    max_length = max(lengths) if lengths else 0
    min_length = min(lengths) if lengths else 0
    low_info_pct = low_info_count / total * 100 if total > 0 else 0

    len_buckets = {"0-50": 0, "51-100": 0, "101-200": 0, "201-500": 0, "500-1000": 0, "1000+": 0}
    for l in lengths:
        if l <= 50:
            len_buckets["0-50"] += 1
        elif l <= 100:
            len_buckets["51-100"] += 1
        elif l <= 200:
            len_buckets["101-200"] += 1
        elif l <= 500:
            len_buckets["201-500"] += 1
        elif l <= 1000:
            len_buckets["500-1000"] += 1
        else:
            len_buckets["1000+"] += 1

    print(f"平均长度: {avg_length:.1f} 字符")
    print(f"最短: {min_length} | 最长: {max_length}")
    print(f"低信息量: {low_info_count:,} ({low_info_pct:.2f}%)")
    print("分布:")
    for bucket, count in len_buckets.items():
        pct = count / total * 100
        marker = "⚠️ " if pct > 20 and bucket in ["0-50", "51-100"] else "  "
        print(f"  {marker}{bucket}: {count:,} ({pct:.1f}%)")

    print(f"\n[5/8] 按任务类型分析...")
    task_analysis = analyze_by_task(data)
    print(f"任务类型数: {len(task_analysis)}")
    for task, stats in task_analysis.items():
        marker = "⚠️" if stats["avg_length"] < 100 else "✅"
        print(f"  {marker} {task}: {stats['count']:,}条 | 平均{stats['avg_length']}字符 | 最大{stats['max_length']} | 低信息 {stats['low_info_pct']}%")

    print(f"\n[6/8] 领域覆盖分析（增强版）...")
    # 增强版领域检测
    domain_data = [
        ("A股", ["A股", "上证", "深证", "创业板", "科创板", "沪深", "沪指", "深成指", "北交所"]),
        ("港股", ["港股", "恒生", "港交所", "香港", "南下", "H股", "腾讯控股", "港币"]),
        ("美股", ["美股", "纳斯达克", "道琼斯", "标普", "特斯拉", "苹果", "亚马逊", "英伟达", "美元"]),
        ("宏观", ["央行", "GDP", "CPI", "PMI", "降准", "降息", "利率", "通胀", "货币政策", "财政政策", "美联储"]),
        ("行业", ["板块", "行业", "赛道", "产业链", "新能源", "半导体", "医药", "消费", "金融"]),
        ("个股", ["公司", "财报", "营收", "利润", "涨停", "跌停", "市值"]),
        ("基金/ETF", ["基金", "ETF", "净值", "申购", "赎回"]),
        ("商品/期货", ["商品", "期货", "原油", "黄金", "铜", "铁矿石"]),
        ("外汇", ["汇率", "人民币", "美元", "外汇", "离岸"]),
    ]

    domain_counter = Counter()
    domain_items = defaultdict(list)
    for item in data:
        human_msg = ""
        for msg in item["conversations"]:
            if msg["from"] == "human":
                human_msg = msg["value"]
                break

        for domain, keywords in domain_data:
            if any(kw in human_msg for kw in keywords):
                domain_counter[domain] += 1
                domain_items[domain].append(item)
                break

    domain_stats = dict(domain_counter.most_common())
    for d, c in domain_stats.items():
        pct = c / total * 100
        print(f"  {d}: {c:,} ({pct:.1f}%)")

    print(f"\n[7/8] 指令多样性...")
    instruction_stats = {}
    for item in data:
        human_msg = ""
        for msg in item["conversations"]:
            if msg["from"] == "human":
                human_msg = msg["value"]
                break
        task = identify_task(human_msg)
        instruction_stats[task] = instruction_stats.get(task, 0) + 1

    print(f"任务类型数: {len(instruction_stats)}")
    total_entropy = calculate_entropy(list(instruction_stats.values()))
    print(f"分布熵: {total_entropy:.4f} (越高越多样)")
    for t, c in sorted(instruction_stats.items(), key=lambda x: -x[1]):
        pct = c / total * 100
        print(f"  {t}: {c:,} ({pct:.1f}%)")

    print(f"\n[8/8] 种子多样性 + 内容质量评分...")
    seed_diversity = detect_seed_patterns(data)
    print(f"指令模板种类: {seed_diversity['total_templates']}")
    print(f"Top15模板占比: {seed_diversity['top15_pct']:.1f}%")
    print(f"模板熵: {seed_diversity['template_entropy']}")

    quality_score = analyze_quality_distribution(data)
    print(f"内容质量平均分: {quality_score['avg_score']} / 100")
    for bucket, pct in quality_score["distribution"].items():
        print(f"  {bucket}: {pct}%")

    # ====== 生成建议 ======
    suggestions = []
    if avg_length < 200:
        suggestions.append(f"🔴 回复过短（平均{avg_length:.0f}字符）。建议生成更多长文本数据（500-2000字符/条）")
    if low_info_pct > 10:
        suggestions.append(f"🟡 低信息量占比 {low_info_pct:.1f}%。建议过滤掉回复<{MIN_RESPONSE_LENGTH}字符的样本")
    if near_dups:
        suggestions.append(f"🟡 发现 {len(near_dups)} 对近重复样本。建议做语义去重或增加生成多样性")
    if seed_diversity["total_templates"] < 10:
        suggestions.append(f"🔴 指令模板只有 {seed_diversity['total_templates']} 种。建议扩展到 15-20 种不同类型的指令")
    hk_pct = domain_stats.get("港股", 0) / total * 100
    if hk_pct < 1:
        suggestions.append(f"🔴 港股覆盖率极低 ({hk_pct:.1f}%)。建议专门生成港股分析数据")
    macro_pct = domain_stats.get("宏观", 0) / total * 100
    if macro_pct < 3:
        suggestions.append(f"🟡 宏观覆盖率偏低 ({macro_pct:.1f}%)。建议补充宏观政策解读数据")
    if task_analysis.get("深度分析", {}).get("count", 0) < 1000:
        suggestions.append("🟡 缺少深度分析类任务。建议增加「详细分析」「全面分析」「分析报告」类型的数据")

    print("\n" + "=" * 60)
    print("建议:")
    for s in suggestions:
        print(f"  {s}")

    # ====== 保存过滤后的数据 ======
    print(f"\n保存过滤后的数据...")
    filtered_path = os.path.join(OUTPUT_DIR, "train_data_filtered.jsonl")
    filtered_count, removed_count = save_filtered_data(data, filtered_path)
    print(f"过滤后: {filtered_count:,} 条 (移除 {removed_count:,} 条低信息量)")
    print(f"输出: {filtered_path}")

    # ====== 生成 HTML 报告 ======
    results = {
        "timestamp": timestamp,
        "total": total,
        "duplicates": duplicates,
        "unique": unique,
        "dup_rate": round(dup_rate, 2),
        "avg_length": round(avg_length, 1),
        "max_length": max_length,
        "min_length": min_length,
        "low_info_count": low_info_count,
        "low_info_pct": round(low_info_pct, 2),
        "length_dist": {k: round(v / total * 100, 1) for k, v in len_buckets.items()},
        "length_dist_raw": len_buckets,
        "near_duplicates": len(near_dups),
        "task_analysis": task_analysis,
        "domain_stats": domain_stats,
        "instruction_stats": instruction_stats,
        "seed_diversity": seed_diversity,
        "quality_score": quality_score,
        "suggestions": suggestions,
    }

    html_path = os.path.join(OUTPUT_DIR, "data_quality_report.html")
    generate_html_report(results, html_path)

    # 同时保存 JSON 摘要
    summary = {k: v for k, v in results.items() if k != "task_analysis"}
    summary_path = os.path.join(OUTPUT_DIR, "data_quality_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"报告完成！所有输出在: {OUTPUT_DIR}")
    print(f"  📄 HTML 报告: {html_path}")
    print(f"  📄 JSON 摘要: {summary_path}")
    print(f"  📄 过滤后数据: {filtered_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
