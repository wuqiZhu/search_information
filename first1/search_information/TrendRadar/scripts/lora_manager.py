# -*- coding: utf-8 -*-
"""
LoRA 管理器 — 多 adapter 切换，按任务自动加载/卸载

百器模型第2层（榫卯层），部署于阿里云服务器。

用法:
    from lora_manager import LoraManager
    lm = LoraManager()
    result = lm.infer("relevance_score", {"title": "...", "summary": "..."})
    result = lm.infer("urgency", {"title": "...", "platform": "weibo", "rank_change": "15→3"})
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")
logger = logging.getLogger("lora_manager")

# 默认路径配置
DEFAULT_BASE_MODEL = os.environ.get(
    "LORA_BASE_MODEL", "/root/models/Qwen1.5-1.5B"
)
DEFAULT_ADAPTERS_DIR = os.environ.get(
    "LORA_ADAPTERS_DIR", "/root/models/loras"
)

# adapter 注册表: task_name -> (adapter_dir_name, prompt_template)
ADAPTER_REGISTRY = {
    "relevance_score": {
        "dir": "lora_a_relevance",
        "description": "精细相关评分 (0-10)",
        "input_schema": {"title": str, "summary": str, "category": str},
        "output_schema": {"score": float, "confidence": float},
    },
    "urgency": {
        "dir": "lora_c_urgency",
        "description": "紧急度判断 (高/中/低)",
        "input_schema": {"title": str, "platform": str, "rank_change": str},
        "output_schema": {"level": str, "reason": str},
    },
    "sentiment_fine": {
        "dir": "lora_b_sentiment",
        "description": "细粒度情绪 (positive/neutral/negative + 强度)",
        "input_schema": {"title": str, "summary": str},
        "output_schema": {"label": str, "intensity": float},
    },
}


class LoraManager:
    """
    多 LoRA 切换管理器。

    在基座模型上按任务动态加载/卸载 adapter，推理时自动切换。
    同一时刻只加载一个 adapter 以节省显存。
    """

    def __init__(
        self,
        base_model: str = DEFAULT_BASE_MODEL,
        adapters_dir: str = DEFAULT_ADAPTERS_DIR,
        device: str = "auto",
        load_on_start: Optional[List[str]] = None,
    ):
        self.base_model_path = base_model
        self.adapters_dir = Path(adapters_dir)
        self.device = device
        self._model = None
        self._tokenizer = None
        self._current_task: Optional[str] = None
        self._load_time: float = 0

        logger.info(f"[LoRA] 基座模型: {base_model}")
        logger.info(f"[LoRA] adapter 目录: {adapters_dir}")

        if load_on_start:
            for task in load_on_start:
                self.load_adapter(task)

    # ── 模型加载 ──

    def _load_base(self):
        """加载基座模型（仅首次调用）"""
        if self._model is not None:
            return

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        logger.info(f"[LoRA] 加载基座模型: {self.base_model_path} ...")
        t0 = time.time()

        # 4-bit 量化加载以节省显存；不支持时回退到普通加载
        import torch
        load_kwargs = dict(
            torch_dtype=torch.float16,
            device_map=self.device if self.device != "auto" else "auto",
            trust_remote_code=True,
        )
        try:
            # 先试 4-bit（GPU 环境）
            self._model = AutoModelForCausalLM.from_pretrained(
                self.base_model_path, load_in_4bit=True, **load_kwargs
            )
        except (TypeError, RuntimeError, ImportError):
            logger.warning("[LoRA] 4-bit 加载失败，回退到 float16")
            self._model = AutoModelForCausalLM.from_pretrained(
                self.base_model_path, **load_kwargs
            )
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.base_model_path, trust_remote_code=True
        )
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        elapsed = time.time() - t0
        logger.info(f"[LoRA] 基座加载完成 ({elapsed:.1f}s)")

    def load_adapter(self, task: str) -> bool:
        """
        加载指定任务的 LoRA adapter。

        如果已有其他 adapter 加载，先卸载再加载新的（节省显存）。
        """
        from peft import PeftModel

        if task not in ADAPTER_REGISTRY:
            logger.error(f"[LoRA] 未知任务: {task}，可用: {list(ADAPTER_REGISTRY.keys())}")
            return False

        if self._current_task == task:
            return True

        # 卸载当前 adapter
        if self._current_task is not None:
            self.unload_adapter()

        # 确保基座已加载
        self._load_base()

        # 加载新 adapter
        adapter_path = self.adapters_dir / ADAPTER_REGISTRY[task]["dir"]
        if not adapter_path.exists():
            logger.error(f"[LoRA] adapter 路径不存在: {adapter_path}")
            return False

        t0 = time.time()
        try:
            self._model = PeftModel.from_pretrained(
                self._model, adapter_path, adapter_name=task
            )
            self._model = self._model.merge_and_unload()
            self._model.to(self._model.device)
            self._current_task = task
            elapsed = time.time() - t0
            self._load_time = elapsed
            logger.info(f"[LoRA] ✅ adapter {task} 已加载 ({elapsed:.1f}s)")
            return True
        except Exception as e:
            logger.error(f"[LoRA] ❌ adapter {task} 加载失败: {e}")
            return False

    def unload_adapter(self):
        """卸载当前 adapter，释放显存"""
        if self._current_task is None:
            return

        import gc
        import torch

        task = self._current_task
        try:
            # 恢复到基座（移除 adapter）
            if hasattr(self._model, "merge_and_unload"):
                self._model = self._model.unload()
            self._current_task = None
            gc.collect()
            torch.cuda.empty_cache()
            logger.info(f"[LoRA] adapter {task} 已卸载")
        except Exception as e:
            logger.warning(f"[LoRA] 卸载 adapter 时出错: {e}")

    # ── 推理 ──

    def infer(self, task: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 LoRA 推理。

        Args:
            task: 任务名 (relevance_score / urgency / sentiment_fine)
            input_data: 输入数据（按 ADAPTER_REGISTRY 定义的 schema）

        Returns:
            推理结果 + 元数据
        """
        # 自动加载 adapter
        if self._current_task != task:
            ok = self.load_adapter(task)
            if not ok:
                return {"error": f"adapter {task} 未加载"}

        registry = ADAPTER_REGISTRY[task]

        # 构造 prompt
        prompt = self._build_prompt(task, input_data)

        # 推理
        t0 = time.time()
        try:
            import torch

            inputs = self._tokenizer(prompt, return_tensors="pt", truncation=True)
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=64,
                    temperature=0.1,
                    do_sample=False,
                    pad_token_id=self._tokenizer.pad_token_id,
                )

            raw_output = self._tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            ).strip()

            result = self._parse_output(task, raw_output)
            elapsed = time.time() - t0
            result["_elapsed_ms"] = round(elapsed * 1000, 1)

            logger.info(
                f"[LoRA] {task}: {result.get('score', result.get('level', '?'))} "
                f"({elapsed*1000:.0f}ms)"
            )
            return result

        except Exception as e:
            logger.error(f"[LoRA] 推理失败: {e}")
            return {"error": str(e)}

    def _build_prompt(self, task: str, data: Dict[str, Any]) -> str:
        """按任务构造 prompt"""
        if task == "relevance_score":
            return (
                f"【任务】评估以下新闻与投资关注点的相关程度（0-10分）。\n\n"
                f"标题: {data.get('title', '')}\n"
                f"摘要: {data.get('summary', '')}\n"
                f"分类: {data.get('category', '综合')}\n\n"
                f"请只输出一个JSON，格式: {{\"score\": <0-10>, \"confidence\": <0-1>}}"
            )

        elif task == "urgency":
            return (
                f"【任务】判断该新闻是否需要立即关注。\n\n"
                f"标题: {data.get('title', '')}\n"
                f"平台: {data.get('platform', '')}\n"
                f"排名变化: {data.get('rank_change', '无')}\n\n"
                f"请只输出一个JSON，格式: {{\"level\": \"high|medium|low\", \"reason\": \"...\"}}"
            )

        elif task == "sentiment_fine":
            return (
                f"【任务】分析以下新闻的情绪倾向及强度。\n\n"
                f"标题: {data.get('title', '')}\n"
                f"摘要: {data.get('summary', '')}\n\n"
                f"请只输出一个JSON，格式: {{\"label\": \"positive|neutral|negative\", \"intensity\": <0-1>}}"
            )

        return json.dumps(data, ensure_ascii=False)

    def _parse_output(self, task: str, raw: str) -> Dict[str, Any]:
        """解析模型输出为结构化 JSON"""
        # 尝试直接解析 JSON
        try:
            # 查找第一个 { 到最后一个 }
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start:end + 1])
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass

        # 回退：按关键词提取
        if task == "relevance_score":
            import re
            nums = re.findall(r"[\d.]+", raw)
            score = float(nums[0]) if nums else 5.0
            return {"score": min(10, max(0, score)), "confidence": 0.5}

        elif task == "urgency":
            raw_lower = raw.lower()
            if "high" in raw_lower:
                return {"level": "high", "reason": raw[:100]}
            elif "medium" in raw_lower:
                return {"level": "medium", "reason": raw[:100]}
            else:
                return {"level": "low", "reason": raw[:100]}

        return {"raw": raw}

    def is_available(self, task: Optional[str] = None) -> bool:
        """检查模型/adapter 是否可用"""
        if task:
            return task in ADAPTER_REGISTRY and (
                self.adapters_dir / ADAPTER_REGISTRY[task]["dir"]
            ).exists()
        return self._model is not None

    def list_adapters(self) -> List[Dict[str, Any]]:
        """列出所有注册的 adapter 及其状态"""
        result = []
        for task, info in ADAPTER_REGISTRY.items():
            adapter_path = self.adapters_dir / info["dir"]
            result.append({
                "task": task,
                "description": info["description"],
                "path": str(adapter_path),
                "exists": adapter_path.exists(),
                "loaded": self._current_task == task,
            })
        return result

    @property
    def current_task(self) -> Optional[str]:
        return self._current_task

    @property
    def load_time(self) -> float:
        return self._load_time


# ============================================================
# 便捷函数
# ============================================================

_instance = None


def get_manager(**kwargs) -> LoraManager:
    """全局单例"""
    global _instance
    if _instance is None:
        _instance = LoraManager(**kwargs)
    return _instance


def infer(task: str, data: dict) -> dict:
    """一键推理"""
    return get_manager().infer(task, data)


if __name__ == "__main__":
    # 简单测试
    lm = LoraManager(load_on_start=["relevance_score"])
    r = lm.infer("relevance_score", {
        "title": "台积电CoWoS产能翻倍，先进封装供不应求",
        "summary": "台积电宣布2026年CoWoS产能将翻倍，以满足AI芯片需求",
        "category": "科技",
    })
    print(json.dumps(r, ensure_ascii=False, indent=2))
