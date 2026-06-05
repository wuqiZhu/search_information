# -*- coding: utf-8 -*-
"""
LoRA adapter 训练脚本 — 百器模型第2层

在 AutoDL (RTX 4090) 上运行，训练 LoRA-A（精细相关评分）和 LoRA-C（紧急度判断）。

用法:
  # 训练 LoRA-A（相关评分 0-10）
  python train_lora_heads.py --task relevance_score \
    --data-dir /root/lora_data/relevance \
    --output-dir /root/models/loras/lora_a_relevance

  # 训练 LoRA-C（紧急度判断）
  python train_lora_heads.py --task urgency \
    --data-dir /root/lora_data/urgency \
    --output-dir /root/models/loras/lora_c_urgency

依赖:
  pip install torch transformers peft accelerate datasets
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("train_lora")

TASK_CONFIGS = {
    "relevance_score": {
        "description": "精细相关评分 (0-10)",
        "num_labels": 1,  # regression
        "loss": "mse",
        "max_length": 256,
        "system_prompt": "请评估以下新闻与投资关注点的相关程度（0-10分）。只输出一个数字。",
        "metric": "mae",
    },
    "urgency": {
        "description": "紧急度判断 (高/中/低)",
        "num_labels": 3,
        "loss": "ce",
        "max_length": 256,
        "system_prompt": "请判断该新闻的紧急程度：high（紧急）、medium（关注）、low（常规）。只输出一个词。",
        "metric": "accuracy",
    },
}

DEFAULT_BASE_MODEL = os.environ.get(
    "LORA_BASE_MODEL", "/root/models/Qwen1.5-1.5B"
)


def load_data(data_dir: str, task: str):
    """加载训练/验证数据"""
    train_data, val_data = [], []
    for name in ["train", "val"]:
        path = os.path.join(data_dir, f"{name}.jsonl")
        if not os.path.exists(path):
            logger.warning(f"  文件不存在: {path}")
            continue
        with open(path, encoding="utf-8") as f:
            items = [json.loads(line) for line in f]
        if name == "train":
            train_data = items
        else:
            val_data = items
        logger.info(f"  {name}: {len(items)} 条")

    if not train_data:
        raise ValueError(f"训练数据为空: {data_dir}")

    logger.info(f"  样例: {json.dumps(train_data[0], ensure_ascii=False)[:120]}")
    return train_data, val_data


def train_lora(task: str, data_dir: str, output_dir: str,
               base_model: str = DEFAULT_BASE_MODEL,
               num_epochs: int = 3, batch_size: int = 8,
               lora_r: int = 16, lora_alpha: int = 32,
               learning_rate: float = 2e-4):
    """
    训练 LoRA adapter。

    Args:
        task: 任务名 (relevance_score / urgency)
        data_dir: 训练数据目录（含 train.jsonl / val.jsonl）
        output_dir: adapter 输出路径
        base_model: 基座模型路径
        num_epochs: 训练轮数
        batch_size: 批次大小（RTX 4090 24GB 可到 8）
        lora_r: LoRA rank
        lora_alpha: LoRA alpha
        learning_rate: 学习率
    """
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, TaskType
    from transformers import (
        AutoTokenizer, AutoModelForCausalLM,
        TrainingArguments, Trainer, DataCollatorForSeq2Seq,
    )

    cfg = TASK_CONFIGS[task]
    os.makedirs(output_dir, exist_ok=True)

    logger.info(f"\n{'='*50}")
    logger.info(f"训练 LoRA: {task}")
    logger.info(f"  基座: {base_model}")
    logger.info(f"  数据: {data_dir}")
    logger.info(f"  输出: {output_dir}")
    logger.info(f"  配置: {cfg['description']}")
    logger.info(f"{'='*50}")

    # 1. 加载基座模型
    logger.info("加载基座模型...")
    tokenizer = AutoTokenizer.from_pretrained(
        base_model, trust_remote_code=True
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    # 2. 配置 LoRA
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.1,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 3. 准备数据集
    def format_sample(sample):
        if task == "relevance_score":
            prompt = (
                f"{cfg['system_prompt']}\n\n"
                f"标题: {sample.get('title', '')}\n"
                f"摘要: {sample.get('content', sample.get('summary', ''))}\n"
                f"分类: {sample.get('category', '综合')}\n\n"
                f"评分: "
            )
            target = str(sample.get("score", 5))
        elif task == "urgency":
            prompt = (
                f"{cfg['system_prompt']}\n\n"
                f"标题: {sample.get('title', '')}\n"
                f"平台: {sample.get('platform', '')}\n"
                f"排名变化: {sample.get('rank_change', '无')}\n"
                f"跨平台: {sample.get('cross_platform', 0)} 个平台出现\n\n"
                f"紧急度: "
            )
            target = sample.get("label", "low")

        return {"prompt": prompt, "target": target}

    def tokenize(examples):
        texts = [p + t for p, t in zip(examples["prompt"], examples["target"])]
        encodings = tokenizer(
            texts,
            truncation=True,
            padding=False,
            max_length=cfg["max_length"],
        )
        encodings["labels"] = encodings["input_ids"].copy()
        return encodings

    logger.info("格式化数据...")
    train_samples = [format_sample(s) for s in train_data]
    val_samples = [format_sample(s) for s in val_data] if val_data else []

    train_dataset = Dataset.from_list(train_samples).map(
        tokenize, batched=True, remove_columns=["prompt", "target"]
    )
    val_dataset = (
        Dataset.from_list(val_samples).map(
            tokenize, batched=True, remove_columns=["prompt", "target"]
        )
        if val_samples
        else None
    )

    # 4. 训练
    training_args = TrainingArguments(
        output_dir=os.path.join(output_dir, "checkpoints"),
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size * 2,
        learning_rate=learning_rate,
        warmup_ratio=0.1,
        logging_steps=10,
        eval_strategy="epoch" if val_dataset else "no",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True if val_dataset else False,
        fp16=True,
        report_to="none",
        dataloader_num_workers=2,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        tokenizer=tokenizer,
        data_collator=DataCollatorForSeq2Seq(tokenizer, padding=True),
    )

    logger.info("开始训练...")
    t0 = time.time()
    trainer.train()
    elapsed = time.time() - t0
    logger.info(f"训练完成，耗时 {elapsed:.0f}s ({elapsed/60:.1f}min)")

    # 5. 保存 adapter
    adapter_path = os.path.join(output_dir, "final")
    trainer.save_model(adapter_path)
    tokenizer.save_pretrained(adapter_path)

    # 同时保存一份到标准位置
    final_path = output_dir  # 直接保存到 output_dir
    model.save_pretrained(final_path)
    tokenizer.save_pretrained(final_path)

    # 保存训练配置
    config = {
        "task": task,
        "base_model": base_model,
        "lora_config": {
            "r": lora_r,
            "alpha": lora_alpha,
            "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        },
        "training": {
            "epochs": num_epochs,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "elapsed_seconds": round(elapsed),
        },
        "metrics": {},
    }

    if val_dataset:
        val_metrics = trainer.evaluate()
        config["metrics"]["val"] = val_metrics
        logger.info(f"验证指标: {val_metrics}")

    config_path = os.path.join(output_dir, "training_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    logger.info(f"\n✅ {task} 训练完成!")
    logger.info(f"  adapter: {final_path}")
    logger.info(f"  配置: {config_path}")
    logger.info(f"  大小: {sum(f.stat().st_size for f in Path(final_path).rglob('*') if f.is_file())/1e6:.0f}MB")

    return config


def prepare_relevance_data(input_path: str, output_dir: str):
    """
    从合成数据中提取 LoRA-A 训练集。

    读取 v2.2 格式的 relevance 数据，提取 title/content/score。
    """
    os.makedirs(output_dir, exist_ok=True)
    samples = []

    with open(input_path, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            conv = record.get("conversations", [])
            if len(conv) < 2:
                continue
            human = conv[0].get("value", "")
            gpt = conv[1].get("value", "")

            if "相关性" not in human and "打分" not in human:
                continue

            title = ""
            for sep in ["内容：", "新闻：", "标题："]:
                if sep in human:
                    title = human.split(sep, 1)[1].strip()
                    break
            if not title:
                continue

            try:
                score = float(gpt.strip())
            except ValueError:
                continue

            samples.append({
                "title": title[:200],
                "content": "",
                "category": "综合",
                "score": min(10, max(0, score)),
            })

    logger.info(f"提取了 {len(samples)} 条相关评分数据")

    # 划分
    split = int(len(samples) * 0.9)
    for name, data in [("train", samples[:split]), ("val", samples[split:])]:
        path = os.path.join(output_dir, f"{name}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        logger.info(f"  已保存 {name}: {len(data)} 条 -> {path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LoRA adapter 训练")

    sub = parser.add_subparsers(dest="command", required=True)

    # train 子命令
    train_p = sub.add_parser("train", help="训练 LoRA adapter")
    train_p.add_argument("--task", required=True,
                         choices=list(TASK_CONFIGS.keys()))
    train_p.add_argument("--data-dir", required=True)
    train_p.add_argument("--output-dir", required=True)
    train_p.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    train_p.add_argument("--epochs", type=int, default=3)
    train_p.add_argument("--batch-size", type=int, default=8)
    train_p.add_argument("--lr", type=float, default=2e-4)
    train_p.add_argument("--lora-r", type=int, default=16)
    train_p.add_argument("--lora-alpha", type=int, default=32)

    # prepare 子命令（从v2.2合成数据提取训练集）
    prep_p = sub.add_parser("prepare", help="准备训练数据")
    prep_p.add_argument("--task", required=True,
                        choices=["relevance_score"])
    prep_p.add_argument("--input", required=True)
    prep_p.add_argument("--output-dir", required=True)

    args = parser.parse_args()

    if args.command == "train":
        train_lora(
            task=args.task,
            data_dir=args.data_dir,
            output_dir=args.output_dir,
            base_model=args.base_model,
            num_epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            lora_r=args.lora_r,
            lora_alpha=args.lora_alpha,
        )

    elif args.command == "prepare":
        if args.task == "relevance_score":
            prepare_relevance_data(args.input, args.output_dir)

    # 如果直接运行没有子命令，显示帮助
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
