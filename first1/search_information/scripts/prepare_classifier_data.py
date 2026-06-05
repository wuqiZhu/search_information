# -*- coding: utf-8 -*-
"""
训练数据准备脚本——从 v2.2 合成数据中提取情绪分类训练集

在阿里云服务器上运行（无需 torch/transformers），产出：
  - train.jsonl     (训练集，约26万条)
  - val.jsonl       (验证集，约3.2万条)
  - test.jsonl      (测试集，约3.2万条)

用法:
  python3 prepare_classifier_data.py \
    --input /root/train_scenarios_v2.2.jsonl \
    --output /root/classifier_data \
    --task sentiment

支持的 task:
  - sentiment: 3分类 (positive/negative/neutral)
  - relevance: 相关性打分 (0-10 → 相关/不相关 二分类)
  - category:  9分类
"""

import json
import os
import random
import sys
from collections import Counter


def parse_v2_2_line(line: str) -> dict:
    """解析 v2.2 格式的一行"""
    record = json.loads(line)
    conv = record.get("conversations", [])
    if len(conv) < 2:
        return None
    human_msg = conv[0].get("value", "").strip()
    gpt_msg = conv[1].get("value", "").strip()
    return {"instruction": human_msg, "response": gpt_msg}


def extract_sentiment(record: dict) -> dict:
    """
    从情感分析任务中提取样本。
    human格式: "判断新闻情绪：正面、负面、中性。\n新闻：{title}"
    gpt格式: "positive" / "negative" / "neutral"
    """
    instruction = record["instruction"]
    response = record["response"]

    # 只处理情感分析任务
    if "判断新闻情绪" not in instruction:
        return None

    # 提取新闻标题：从"新闻："之后取内容
    title = ""
    if "新闻：" in instruction:
        title = instruction.split("新闻：", 1)[1].strip()
    elif "内容：" in instruction:
        title = instruction.split("内容：", 1)[1].strip()
    if not title:
        title = instruction

    # 标准化标签
    label_map = {
        "positive": "positive", "正面": "positive",
        "negative": "negative", "负面": "negative",
        "neutral": "neutral", "中性": "neutral",
    }
    label = label_map.get(response.strip().lower(), None)
    if label is None:
        return None

    label_id = {"positive": 2, "neutral": 1, "negative": 0}
    return {
        "text": title,
        "label": label,
        "label_id": label_id[label],
        "source": "v2.2_synthetic"
    }


def extract_relevance(record: dict) -> dict:
    """
    从相关性评分任务中提取样本 → 二分类（相关/不相关）
    """
    instruction = record["instruction"]
    response = record["response"]

    if "相关性" not in instruction and "打分" not in instruction:
        return None

    title = ""
    if "内容：" in instruction:
        title = instruction.split("内容：", 1)[1].strip()
    elif "新闻：" in instruction:
        title = instruction.split("新闻：", 1)[1].strip()
    if not title:
        title = instruction

    try:
        score = float(response.strip())
    except ValueError:
        return None

    label = "relevant" if score >= 5 else "irrelevant"
    return {
        "text": title,
        "label": label,
        "score": score,
        "label_id": 1 if score >= 5 else 0,
        "source": "v2.2_synthetic"
    }


def extract_category(record: dict) -> dict:
    """
    从新闻分类任务中提取样本。
    """
    instruction = record["instruction"]
    response = record["response"]

    if "分类" not in instruction:
        return None

    title = ""
    if "新闻：" in instruction:
        title = instruction.split("新闻：", 1)[1].strip()
    elif "内容：" in instruction:
        title = instruction.split("内容：", 1)[1].strip()
    if not title:
        title = instruction

    category = response.strip().split("-", 1)[-1] if "-" in response else response.strip()
    return {
        "text": title,
        "label": category,
        "source": "v2.2_synthetic"
    }


def prepare_dataset(input_path: str, output_dir: str, task: str = "sentiment",
                    train_ratio: float = 0.8, val_ratio: float = 0.1,
                    max_samples: int = None):
    """
    准备分类器训练数据集。

    Args:
        input_path: v2.2 JSONL 文件路径
        output_dir: 输出目录
        task: 任务类型 (sentiment/relevance/category)
        train_ratio: 训练集比例
        val_ratio: 验证集比例
        max_samples: 最大样本数（用于快速测试）
    """
    os.makedirs(output_dir, exist_ok=True)

    extractors = {
        "sentiment": extract_sentiment,
        "relevance": extract_relevance,
        "category": extract_category,
    }
    extractor = extractors.get(task)
    if not extractor:
        print(f"不支持的任务: {task}，可选: {list(extractors.keys())}")
        sys.exit(1)

    print(f"读取数据: {input_path}")
    print(f"任务类型: {task}")
    print(f"输出目录: {output_dir}")

    samples = []
    label_counts = Counter()
    line_count = 0

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line_count += 1
            if line_count % 200000 == 0:
                print(f"  已处理 {line_count} 行，找到 {len(samples)} 个有效样本")

            record = parse_v2_2_line(line)
            if not record:
                continue

            sample = extractor(record)
            if sample:
                samples.append(sample)
                label_counts[sample["label"]] += 1

            if max_samples and len(samples) >= max_samples:
                break

    print(f"\n处理完成:")
    print(f"  总行数: {line_count}")
    print(f"  有效样本: {len(samples)}")
    print(f"  标签分布: {dict(label_counts)}")

    # 打乱
    random.shuffle(samples)

    # 划分
    n = len(samples)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)
    train = samples[:n_train]
    val = samples[n_train:n_train + n_val]
    test = samples[n_train + n_val:]

    print(f"\n数据集划分:")
    print(f"  训练集: {len(train)} 条")
    print(f"  验证集: {len(val)} 条")
    print(f"  测试集: {len(test)} 条")

    # 保存
    for name, data in [("train", train), ("val", val), ("test", test)]:
        path = os.path.join(output_dir, f"{name}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"  已保存: {path}")

    # 保存标签映射
    labels = sorted(set(s["label"] for s in samples))
    label_map_path = os.path.join(output_dir, "labels.json")
    with open(label_map_path, "w", encoding="utf-8") as f:
        json.dump({
            "task": task,
            "labels": labels,
            "num_labels": len(labels),
            "label_id_map": {label: i for i, label in enumerate(labels)},
            "samples": {"train": len(train), "val": len(val), "test": len(test)},
        }, f, ensure_ascii=False, indent=2)
    print(f"  标签映射: {label_map_path}")

    print("\n✅ 数据准备完成!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="分类器训练数据准备")
    parser.add_argument("--input", default="/root/train_scenarios_v2.2.jsonl",
                        help="v2.2 JSONL 文件路径")
    parser.add_argument("--output", default="/root/classifier_data",
                        help="输出目录")
    parser.add_argument("--task", default="sentiment",
                        choices=["sentiment", "relevance", "category"],
                        help="任务类型")
    parser.add_argument("--max-samples", type=int, default=None,
                        help="最大样本数（测试用）")
    args = parser.parse_args()
    prepare_dataset(args.input, args.output, args.task, max_samples=args.max_samples)
