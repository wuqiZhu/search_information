# coding=utf-8
"""
AI 训练数据缓冲池

被动收集每次 AI API 调用的输入输出对，用于后续模型微调/训练。
纯旁路收集，不改变现有逻辑，不增加主流程延迟，零风险。

自动导出：每收集满 AUTO_EXPORT_THRESHOLD 条后，自动打包为训练格式。

数据格式（JSONL，按天分文件）：
  {"timestamp": "...", "prompt": "...", "response": "...", "model": "...", "system_prompt": "..."}

导出格式（ShareGPT，用于 LLaMAFactory / ONNX 训练）：
  {"instruction": "...", "output": "..."}

存放位置：
  data/training_buffer/buffer_YYYY-MM-DD.jsonl        # 原始缓冲
  data/training_buffer/exported/train_*.jsonl          # 导出训练数据
"""

import json
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path

# 满多少条自动导出
AUTO_EXPORT_THRESHOLD = 500


class TrainingBuffer:
    """训练数据缓冲池（线程安全）"""

    def __init__(self, buffer_dir: str = None, auto_export: bool = True):
        if buffer_dir is None:
            # Docker 环境优先使用挂载卷
            docker_output = Path("/app/output")
            if docker_output.exists():
                buffer_dir = docker_output / "training_buffer"
            else:
                base = Path(__file__).resolve().parent.parent.parent.parent  # TrendRadar/
                buffer_dir = base / "data" / "training_buffer"
        self.buffer_dir = Path(buffer_dir)
        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir = self.buffer_dir / "exported"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._auto_export = auto_export

    def save(self, prompt: str, response: str, metadata: dict = None) -> str:
        """
        保存一次 API 调用记录到当天缓冲文件。

        达到阈值时自动触发导出。

        Returns:
            写入的文件路径
        """
        today = datetime.now().strftime("%Y-%m-%d")
        filepath = self.buffer_dir / f"buffer_{today}.jsonl"

        record = {
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt,
            "response": response,
        }
        if metadata:
            for k, v in metadata.items():
                if k not in record:
                    record[k] = v

        with self._lock:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            # 自动导出检查
            if self._auto_export:
                self._check_and_export_locked(filepath, today)

        return str(filepath)

    def _check_and_export_locked(self, filepath: Path, today: str):
        """检查是否需要导出（调用方已持有锁）"""
        try:
            count = self._count_lines(filepath)
            if count >= AUTO_EXPORT_THRESHOLD:
                exported_path = self.export_dir / f"train_{today}.jsonl"
                if exported_path.exists():
                    # 已导出过，不再重复导出
                    return
                self._export_to_training_format_locked(filepath, exported_path)
                print(f"[TrainingBuffer] 自动导出 {count} 条训练数据 → {exported_path}")
        except Exception:
            pass

    def _count_lines(self, filepath: Path) -> int:
        if not filepath.exists():
            return 0
        with open(filepath, "r", encoding="utf-8") as f:
            return sum(1 for _ in f)

    def _export_to_training_format_locked(self, src: Path, dst: Path):
        """
        将原始缓冲数据导出为 ShareGPT 格式（instruction → output）。

        ShareGPT 格式：
          {"instruction": "...", "output": "..."}
        """
        with open(src, "r", encoding="utf-8") as f_in, \
             open(dst, "w", encoding="utf-8") as f_out:
            for line in f_in:
                try:
                    record = json.loads(line)
                    # 提取 instruction：精简 user_prompt 为合理长度
                    prompt = record.get("prompt", "")
                    # 提取 output
                    response = record.get("response", "")
                    if not prompt or not response:
                        continue
                    train_record = {
                        "instruction": prompt[:2000],
                        "output": response,
                        "model": record.get("model", ""),
                        "source": record.get("mode", "unknown"),
                    }
                    f_out.write(json.dumps(train_record, ensure_ascii=False) + "\n")
                except (json.JSONDecodeError, KeyError):
                    continue

        # 源文件标注已导出（重命名添加 .exported 标记）
        src.rename(src.with_name(src.name + ".exported"))

    # ---- 查询接口 ----

    def get_today_count(self) -> int:
        """获取今天已收集的记录数"""
        today = datetime.now().strftime("%Y-%m-%d")
        filepath = self.buffer_dir / f"buffer_{today}.jsonl"
        if not filepath.exists():
            return 0
        with self._lock:
            return self._count_lines(filepath)

    def get_total_count(self) -> int:
        """获取所有缓冲文件的总记录数（未导出的）"""
        total = 0
        for f in self.buffer_dir.glob("buffer_*.jsonl"):
            if ".exported" not in f.name:
                with open(f, "r", encoding="utf-8") as fh:
                    total += sum(1 for _ in fh)
        return total

    def get_exported_count(self) -> int:
        """获取已导出的总记录数"""
        total = 0
        for f in self.export_dir.glob("train_*.jsonl"):
            with open(f, "r", encoding="utf-8") as fh:
                total += sum(1 for _ in fh)
        return total

    def get_stats(self) -> dict:
        """获取缓冲池统计信息"""
        return {
            "buffer_dir": str(self.buffer_dir),
            "export_dir": str(self.export_dir),
            "today_unexported": self.get_today_count(),
            "total_unexported": self.get_total_count(),
            "total_exported": self.get_exported_count(),
            "auto_export_threshold": AUTO_EXPORT_THRESHOLD,
        }


# 全局单例（懒加载）
_buffer_instance = None
_buffer_lock = threading.Lock()


def get_buffer(buffer_dir: str = None) -> TrainingBuffer:
    """获取全局 TrainingBuffer 单例"""
    global _buffer_instance
    if _buffer_instance is None:
        with _buffer_lock:
            if _buffer_instance is None:
                _buffer_instance = TrainingBuffer(buffer_dir)
    return _buffer_instance


def save_to_buffer(prompt: str, response: str, metadata: dict = None) -> str:
    """
    便捷函数：保存到缓冲池（一次调用）。

    用法:
        from trendradar.ai.training_buffer import save_to_buffer
        save_to_buffer(prompt, response, {"model": "mimo-v2.5-pro"})
    """
    return get_buffer().save(prompt, response, metadata)
