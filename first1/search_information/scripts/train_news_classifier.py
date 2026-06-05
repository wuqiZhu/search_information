# -*- coding: utf-8 -*-
"""
新闻分类器训练脚本（DistilBERT → ONNX）

在 AutoDL 或 GPU 机器上运行：
  1. 安装依赖: pip install torch transformers datasets onnx onnxruntime scikit-learn tqdm
  2. 准备数据: (由 prepare_classifier_data.py 生成)
  3. 训练: python3 train_news_classifier.py --data-dir /root/classifier_data

输出:
  - models/news_classifier/model.onnx        (ONNX 模型，~65MB)
  - models/news_classifier/tokenizer_config/ (tokenizer 文件)
  - models/news_classifier/labels.json       (标签映射)

依赖:
  torch, transformers, datasets, onnx, onnxruntime, scikit-learn, tqdm
"""

import json
import os
import sys
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("train_classifier")


def load_data(data_dir: str):
    """加载 JSONL 数据"""
    train_data, val_data, test_data = [], [], []
    for name in ["train", "val", "test"]:
        path = os.path.join(data_dir, f"{name}.jsonl")
        if not os.path.exists(path):
            logger.warning(f"文件不存在: {path}")
            continue
        with open(path, "r", encoding="utf-8") as f:
            items = [json.loads(line) for line in f]
        if name == "train":
            train_data = items
        elif name == "val":
            val_data = items
        else:
            test_data = items
        logger.info(f"  {name}: {len(items)} 条")

    # 加载标签映射
    labels_path = os.path.join(data_dir, "labels.json")
    if os.path.exists(labels_path):
        with open(labels_path, "r") as f:
            label_info = json.load(f)
        labels = label_info["labels"]
        num_labels = label_info["num_labels"]
        logger.info(f"  标签 ({num_labels}): {labels}")
    else:
        labels = sorted(set(item["label"] for item in train_data))
        num_labels = len(labels)
        logger.info(f"  从数据推断标签 ({num_labels}): {labels}")

    label2id = {l: i for i, l in enumerate(labels)}
    id2label = {i: l for l, i in label2id.items()}

    return train_data, val_data, test_data, label2id, id2label


class NewsClassifier:
    """DistilBERT 新闻分类器"""

    def __init__(self, model_name: str = "distilbert-base-multilingual-cased",
                 num_labels: int = 3, max_length: int = 128):
        self.model_name = model_name
        self.num_labels = num_labels
        self.max_length = max_length
        self.tokenizer = None
        self.model = None
        self.device = None

    def prepare(self):
        """加载 tokenizer 和模型"""
        from transformers import (
            AutoTokenizer,
            AutoModelForSequenceClassification,
            TrainingArguments,
            Trainer,
        )

        logger.info(f"加载 tokenizer: {self.model_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)

        logger.info(f"加载模型: {self.model_name} (num_labels={self.num_labels})")
        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name,
            num_labels=self.num_labels,
        )

        import torch
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"设备: {self.device}")

    def tokenize(self, texts):
        """批量 tokenize"""
        return self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )

    def train(self, train_data, val_data, label2id, output_dir: str,
              num_epochs: int = 3, batch_size: int = 64, learning_rate: float = 2e-5):
        """
        训练分类器。

        Args:
            train_data: 训练集
            val_data: 验证集
            label2id: 标签到ID的映射
            output_dir: 模型输出目录
            num_epochs: 训练轮数
            batch_size: 批次大小
            learning_rate: 学习率
        """
        import torch
        from datasets import Dataset
        from transformers import TrainingArguments, Trainer, EarlyStoppingCallback

        # 转换为 HuggingFace Dataset
        def to_dataset(data):
            texts = [item["text"] for item in data]
            labels = [label2id[item["label"]] for item in data]
            encodings = self.tokenizer(texts, truncation=True, padding=True,
                                       max_length=self.max_length)
            return Dataset.from_dict({
                "input_ids": encodings["input_ids"],
                "attention_mask": encodings["attention_mask"],
                "labels": labels,
            })

        train_dataset = to_dataset(train_data)
        val_dataset = to_dataset(val_data)

        logger.info(f"训练集: {len(train_dataset)} 条")
        logger.info(f"验证集: {len(val_dataset)} 条")
        logger.info(f"训练参数: epochs={num_epochs}, batch={batch_size}, lr={learning_rate}")

        output_path = os.path.join(output_dir, "checkpoints")
        training_args = TrainingArguments(
            output_dir=output_path,
            num_train_epochs=num_epochs,
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=batch_size * 2,
            learning_rate=learning_rate,
            warmup_ratio=0.1,
            weight_decay=0.01,
            logging_dir=os.path.join(output_dir, "logs"),
            logging_steps=100,
            eval_strategy="epoch",
            save_strategy="epoch",
            save_total_limit=2,
            load_best_model_at_end=True,
            metric_for_best_model="accuracy",
            greater_is_better=True,
            fp16=torch.cuda.is_available(),
            dataloader_num_workers=2,
            report_to="none",
        )

        def compute_metrics(eval_pred):
            from sklearn.metrics import accuracy_score, f1_score, classification_report
            predictions, labels = eval_pred
            preds = predictions.argmax(-1)
            accuracy = accuracy_score(labels, preds)
            f1 = f1_score(labels, preds, average="weighted")
            return {"accuracy": accuracy, "f1_weighted": f1}

        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            compute_metrics=compute_metrics,
            callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
        )

        # 训练
        logger.info("开始训练...")
        start = time.time()
        trainer.train()
        elapsed = time.time() - start
        logger.info(f"训练完成，耗时 {elapsed:.0f} 秒")

        # 保存 best model
        best_path = os.path.join(output_dir, "best_model")
        trainer.save_model(best_path)
        self.tokenizer.save_pretrained(best_path)
        logger.info(f"最佳模型已保存: {best_path}")

        # 评估
        logger.info("评估验证集...")
        val_metrics = trainer.evaluate(val_dataset)
        logger.info(f"验证集结果: {val_metrics}")

        return trainer, val_metrics

    def evaluate(self, test_data, label2id):
        """测试集评估"""
        from sklearn.metrics import (accuracy_score, f1_score,
                                     classification_report, confusion_matrix)

        import torch
        self.model.eval()
        all_preds = []
        all_labels = []

        batch_size = 64
        for i in range(0, len(test_data), batch_size):
            batch = test_data[i:i + batch_size]
            texts = [item["text"] for item in batch]
            labels = [label2id[item["label"]] for item in batch]

            inputs = self.tokenizer(texts, truncation=True, padding=True,
                                    max_length=self.max_length, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model(**inputs)
                preds = outputs.logits.argmax(-1).cpu().numpy()

            all_preds.extend(preds.tolist())
            all_labels.extend(labels)

        accuracy = accuracy_score(all_labels, all_preds)
        f1 = f1_score(all_labels, all_preds, average="weighted")
        report = classification_report(all_labels, all_preds,
                                       target_names=list(label2id.keys()))
        cm = confusion_matrix(all_labels, all_preds)

        logger.info(f"\n测试集结果:")
        logger.info(f"  Accuracy:  {accuracy:.4f}")
        logger.info(f"  F1 Weighted: {f1:.4f}")
        logger.info(f"\n分类报告:\n{report}")

        return {"accuracy": accuracy, "f1_weighted": f1,
                "classification_report": report,
                "confusion_matrix": cm.tolist()}

    def export_onnx(self, output_dir: str):
        """导出 ONNX 格式 + int8 量化"""
        import torch
        from transformers import AutoConfig

        logger.info("导出 ONNX 模型...")

        # 创建 dummy input（用 max_length 填充，确保动态序列长度）
        dummy_input = self.tokenizer(
            ["测试新闻标题", "另一条稍微长一点的测试新闻标题作为批次输入"],
            return_tensors="pt",
            padding="max_length",
            truncation=True,
            max_length=self.max_length,
        )

        # 导出 ONNX
        onnx_path = os.path.join(output_dir, "model.onnx")

        with torch.no_grad():
            torch.onnx.export(
                self.model.to("cpu"),
                args=(
                    dummy_input["input_ids"],
                    dummy_input["attention_mask"],
                ),
                f=onnx_path,
                input_names=["input_ids", "attention_mask"],
                output_names=["logits"],
                dynamic_axes={
                    "input_ids": {0: "batch_size", 1: "seq_length"},
                    "attention_mask": {0: "batch_size", 1: "seq_length"},
                    # logits shape = (batch_size, num_labels), 只有 batch 是动态的
                    # num_labels 是固定值（3或2），设动态会导致量化时 shape inference 冲突
                    "logits": {0: "batch_size"},
                },
                opset_version=14,
                do_constant_folding=True,
            )
        logger.info(f"ONNX 模型已导出: {onnx_path} ({os.path.getsize(onnx_path) / 1e6:.1f} MB)")

        # 尝试 int8 量化
        try:
            from onnxruntime.quantization import quantize_dynamic, QuantType

            onnx_quant_path = os.path.join(output_dir, "model_quant.onnx")
            quantize_dynamic(
                onnx_path,
                onnx_quant_path,
                weight_type=QuantType.QUInt8,
            )
            quant_size = os.path.getsize(onnx_quant_path) / 1e6
            orig_size = os.path.getsize(onnx_path) / 1e6
            logger.info(f"INT8 量化: {orig_size:.1f}MB → {quant_size:.1f}MB "
                       f"({(1 - quant_size/orig_size)*100:.0f}% 缩减)")
            onnx_path = onnx_quant_path
        except Exception as e:
            logger.warning(f"量化失败 (不影响主模型): {e}")

        return onnx_path

    def save_config(self, output_dir: str, label2id: dict, id2label: dict,
                    metrics: dict = None):
        """保存模型配置"""
        config = {
            "model_type": "distilbert-onnx",
            "model_name": self.model_name,
            "num_labels": self.num_labels,
            "max_length": self.max_length,
            "label2id": label2id,
            "id2label": id2label,
            "metrics": metrics or {},
            "export_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        path = os.path.join(output_dir, "model_config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"配置已保存: {path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="新闻分类器训练")
    parser.add_argument("--data-dir", default="/root/classifier_data",
                        help="数据目录")
    parser.add_argument("--output-dir", default="/root/models/news_classifier",
                        help="模型输出目录")
    parser.add_argument("--model-name", default="distilbert-base-multilingual-cased",
                        help="预训练模型名称")
    parser.add_argument("--epochs", type=int, default=3,
                        help="训练轮数")
    parser.add_argument("--batch-size", type=int, default=64,
                        help="批次大小")
    parser.add_argument("--learning-rate", type=float, default=2e-5,
                        help="学习率")
    parser.add_argument("--max-length", type=int, default=128,
                        help="最大序列长度")
    parser.add_argument("--export-only", action="store_true",
                        help="仅从已有 checkpoint 导出 ONNX")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # 加载数据
    train_data, val_data, test_data, label2id, id2label = load_data(args.data_dir)
    num_labels = len(label2id)

    # 创建分类器
    classifier = NewsClassifier(
        model_name=args.model_name,
        num_labels=num_labels,
        max_length=args.max_length,
    )

    final_metrics = {}

    if args.export_only:
        # 从已有 checkpoint 加载
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        checkpoint_path = os.path.join(args.output_dir, "best_model")
        logger.info(f"从 checkpoint 加载: {checkpoint_path}")
        classifier.tokenizer = AutoTokenizer.from_pretrained(checkpoint_path)
        classifier.model = AutoModelForSequenceClassification.from_pretrained(
            checkpoint_path, num_labels=num_labels
        )
    else:
        # 训练
        classifier.prepare()
        trainer, val_metrics = classifier.train(
            train_data, val_data, label2id,
            output_dir=args.output_dir,
            num_epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
        )
        final_metrics.update({"val_" + k: v for k, v in val_metrics.items()})

        # 测试集评估
        if test_data:
            test_metrics = classifier.evaluate(test_data, label2id)
            final_metrics.update({"test_" + k: v for k, v in test_metrics.items()
                                  if isinstance(v, (int, float))})

    # 导出 ONNX
    onnx_path = classifier.export_onnx(args.output_dir)
    final_metrics["onnx_path"] = onnx_path
    final_metrics["onnx_size_mb"] = round(os.path.getsize(onnx_path) / 1e6, 1)

    # 保存配置
    classifier.save_config(args.output_dir, label2id, id2label, final_metrics)

    logger.info(f"\n{'='*50}")
    logger.info(f"✅ 全部完成!")
    logger.info(f"  模型: {onnx_path}")
    logger.info(f"  配置: {os.path.join(args.output_dir, 'model_config.json')}")
    logger.info(f"{'='*50}")


if __name__ == "__main__":
    import torch  # noqa: ensure available
    main()
