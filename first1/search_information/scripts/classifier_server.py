# -*- coding: utf-8 -*-
"""
ONNX 多模型分类器服务（哨兵）

支持同时加载多个 ONNX 模型（catetory/sentiment/relevance），
在 CPU 上对新闻进行实时分类。

用法:
  python3 classifier_server.py                          # 启动REST服务
  python3 classifier_server.py --predict sentiment "文本" # 命令行预测
  python3 classifier_server.py --benchmark              # 性能测试

依赖:
  pip install onnxruntime numpy
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

# 模型目录搜索路径（按优先级）
_CANDIDATE_DIRS = [
    Path("/app/models"),                              # Docker 容器
    Path("/root/projects/models"),                    # 宿主机
    Path(__file__).parent.parent / "models",           # 项目内 models/
]

# 默认模型列表
DEFAULT_MODELS = {
    "sentiment": {
        "dir": "sentiment",
        "description": "情绪分类 (positive/neutral/negative)",
        "fallback": None,
    },
    "category": {
        "dir": "category",
        "description": "新闻分类 (科技/政策/综合)",
        "fallback": None,
    },
    "relevance": {
        "dir": "relevance",
        "description": "相关度判定 (relevant/irrelevant)",
        "fallback": None,
    },
}


def _find_models_dir() -> Path:
    """自动检测模型根目录"""
    for d in _CANDIDATE_DIRS:
        if d.exists() and any(d.iterdir()):
            return d
    # 默认使用第一个
    return _CANDIDATE_DIRS[0]


def _find_model_path(model_dir: Path, filename: str) -> Path:
    """搜索模型文件（处理外部分片数据）"""
    candidates = [
        model_dir / filename,
        model_dir / f"{filename}.onnx",
        model_dir / "model.onnx",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


class ONNXClassifier:
    """多模型 ONNX 分类器（CPU推理，~10ms/条）"""

    def __init__(self, models_dir: str = None):
        self.models_dir = Path(models_dir) if models_dir else _find_models_dir()
        self.sessions = {}   # model_name -> onnxruntime session
        self.configs = {}    # model_name -> config dict
        self.tokenizers = {} # model_name -> tokenizer

        print(f"[哨兵] 模型目录: {self.models_dir}")
        self._discover_and_load()

    def _discover_and_load(self):
        """扫描目录，自动发现并加载所有模型"""
        loaded = []
        for model_name, info in DEFAULT_MODELS.items():
            model_dir = self.models_dir / info["dir"]
            config_path = model_dir / "model_config.json"

            # 优先加载 INT8 量化版 (~130MB)，回退到原版 (~518MB+data)
            model_path = model_dir / "model_quant.onnx"
            if not model_path.exists():
                model_path = model_dir / "model.onnx"

            if not model_path.exists():
                print(f"[哨兵]  ⚠️ {model_name}: 模型文件不存在 ({model_path})，跳过")
                continue

            self._load_model(model_name, model_path, config_path)
            loaded.append(model_name)

        if not loaded:
            print("[哨兵]  ⚠️ 未加载任何模型，推理将返回 None")
        else:
            print(f"[哨兵]  ✅ 已加载模型: {', '.join(loaded)}")

    def _load_model(self, name: str, model_path: Path, config_path: Path):
        """加载单个 ONNX 模型"""
        import onnxruntime

        # 加载配置
        config = {}
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)

        self.configs[name] = config

        # 加载 ONNX 会话
        so = onnxruntime.SessionOptions()
        so.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        so.enable_cpu_mem_arena = False
        so.enable_mem_pattern = False
        so.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        session = onnxruntime.InferenceSession(
            str(model_path), so, providers=["CPUExecutionProvider"]
        )

        self.sessions[name] = {
            "session": session,
            "input_name": session.get_inputs()[0].name,
            "mask_name": session.get_inputs()[1].name,
            "labels": config.get("labels", config.get("id2label", {})),
            "num_labels": config.get("num_labels", 3),
        }

        # 加载 tokenizer
        tokenizer_path = self.models_dir / name / "tokenizer.json"
        if tokenizer_path.exists():
            from tokenizers import Tokenizer
            tok = Tokenizer.from_file(str(tokenizer_path))
            max_length = config.get("max_length", 128)
            tok.enable_padding(pad_id=0, pad_token="[PAD]", length=max_length)
            tok.enable_truncation(max_length=max_length)
            self.tokenizers[name] = tok

        model_size = model_path.stat().st_size / 1e6
        labels_info = (
            list(self.sessions[name]["labels"].values())
            if isinstance(self.sessions[name]["labels"], dict)
            else self.sessions[name]["labels"]
        )
        print(f"[哨兵]  ✅ {name}: 已加载 ({model_size:.0f}MB, 标签={labels_info})")

    def _tokenize(self, name: str, texts):
        """使用指定模型的 tokenizer 进行分词"""
        tok = self.tokenizers.get(name)
        if not tok:
            raise RuntimeError(f"{name}: tokenizer 未加载")

        if isinstance(texts, str):
            texts = [texts]

        encoding = tok.encode_batch(texts, add_special_tokens=True)
        input_ids = np.array([e.ids for e in encoding], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encoding], dtype=np.int64)
        return input_ids, attention_mask

    def predict(self, name: str, texts, return_proba=False):
        """
        使用指定模型预测。

        Args:
            name: 模型名称 (sentiment/category/relevance)
            texts: str 或 List[str]
            return_proba: 是否返回概率

        Returns:
            List[Dict] 或单个 Dict
        """
        if name not in self.sessions:
            raise ValueError(f"模型 '{name}' 未加载，可用: {list(self.sessions.keys())}")

        single = isinstance(texts, str)
        if single:
            texts = [texts]

        model = self.sessions[name]
        cfg = self.configs.get(name, {})

        input_ids, attention_mask = self._tokenize(name, texts)

        # ONNX 推理
        outputs = model["session"].run(
            None,
            {model["input_name"]: input_ids, model["mask_name"]: attention_mask},
        )
        logits = outputs[0]

        # softmax
        exp = np.exp(logits - np.max(logits, axis=1, keepdims=True))
        probs = exp / exp.sum(axis=1, keepdims=True)

        # 构建标签映射
        labels = cfg.get("labels", [])
        id2label = cfg.get("id2label", {})

        results = []
        for i in range(len(texts)):
            pred_id = int(np.argmax(probs[i]))
            label = id2label.get(str(pred_id), labels[pred_id] if labels and pred_id < len(labels) else f"class_{pred_id}")

            result = {
                "label": label,
                "label_id": pred_id,
                "score": float(round(probs[i][pred_id], 4)),
            }
            if return_proba:
                all_labels = [id2label.get(str(j), labels[j] if j < len(labels) else f"class_{j}")
                              for j in range(model["num_labels"])]
                result["probabilities"] = {
                    all_labels[j]: float(round(probs[i][j], 4))
                    for j in range(model["num_labels"])
                }
            results.append(result)

        return results[0] if single else results

    def predict_one(self, name: str, text: str) -> dict:
        """单条预测"""
        return self.predict(name, text)

    def is_loaded(self, name: str) -> bool:
        """检查模型是否已加载"""
        return name in self.sessions


# ============================================================
# 全局单例
# ============================================================

_instance = None


def get_classifier(models_dir: str = None):
    global _instance
    if _instance is None:
        _instance = ONNXClassifier(models_dir)
    return _instance


def predict(name: str, text: str):
    """便捷预测"""
    return get_classifier().predict(name, text)


# ============================================================
# CLI
# ============================================================

def benchmark():
    """性能基准测试"""
    test_texts = [
        "A股三大指数今日集体大涨，沪指涨超2%",
        "央行降准释放流动性，利好实体经济",
        "美联储加息预期升温",
        "半导体板块持续走强",
        "新能源补贴政策落地",
        "某科技公司股价暴跌30%",
    ] * 10  # 60条

    clf = get_classifier()
    models = list(clf.sessions.keys())
    print(f"\n📊 性能测试 ({len(test_texts)} 条, 共 {len(models)} 个模型)")
    print("=" * 50)

    for model_name in models:
        try:
            _ = clf.predict(model_name, test_texts[:5])  # 预热

            start = time.time()
            results = clf.predict(model_name, test_texts)
            elapsed = time.time() - start

            avg_ms = elapsed / len(test_texts) * 1000
            throughput = len(test_texts) / elapsed
            print(f"  {model_name:12s}: {avg_ms:.1f}ms/条, {throughput:.0f}条/秒")
        except Exception as e:
            print(f"  {model_name:12s}: ❌ {e}")

    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ONNX 多模型分类器服务 (哨兵)")
    parser.add_argument("--predict", type=str, nargs=2, metavar=("MODEL", "TEXT"),
                        help="预测 (例: --predict sentiment 'A股大涨')")
    parser.add_argument("--predict-file", type=str, metavar="MODEL:FILE",
                        help="批量预测 (例: --predict-file sentiment:/path/to/file.txt)")
    parser.add_argument("--benchmark", action="store_true", help="性能测试")
    parser.add_argument("--port", type=int, default=5080, help="REST服务端口")
    parser.add_argument("--serve", action="store_true", help="启动REST服务")
    parser.add_argument("--models-dir", type=str, default=None, help="模型根目录")

    args = parser.parse_args()

    if args.benchmark:
        return benchmark()

    clf = get_classifier(args.models_dir)
    if not clf.sessions:
        print("[哨兵] ❌ 没有可用的模型，请检查模型目录")
        sys.exit(1)

    if args.predict:
        model_name, text = args.predict
        try:
            result = clf.predict_one(model_name, text)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except ValueError as e:
            print(f"❌ {e}")
            sys.exit(1)
        return

    if args.predict_file:
        model_name, filepath = args.predict_file.split(":", 1)
        with open(filepath, "r", encoding="utf-8") as f:
            texts = [line.strip() for line in f if line.strip()]
        results = clf.predict(model_name, texts)
        for text, result in zip(texts, results):
            print(f"{result['label']:12s} ({result['score']:.2f}) | {text[:50]}")
        return

    if args.serve:
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import urllib.parse

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)

                if parsed.path == "/health":
                    models_status = {k: "ok" for k in clf.sessions.keys()}
                    self._json_response(200, {"status": "ok", "models": models_status})
                    return

                # GET /?model=sentiment&text=xxx
                model_name = params.get("model", ["sentiment"])[0]
                text = params.get("text", [None])[0]

                if not text:
                    self._json_response(400, {"error": "missing text param"})
                    return

                try:
                    result = clf.predict_one(model_name, text)
                    self._json_response(200, result)
                except ValueError as e:
                    self._json_response(400, {"error": str(e)})

            def do_POST(self):
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    self._json_response(400, {"error": "invalid JSON"})
                    return

                texts = data.get("texts", [data.get("text", "")])
                model_name = data.get("model", "sentiment")

                if isinstance(texts, str):
                    texts = [texts]

                try:
                    results = clf.predict(model_name, texts)
                    self._json_response(200, {"results": results})
                except ValueError as e:
                    self._json_response(400, {"error": str(e)})

            def _json_response(self, code, data):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

            def log_message(self, format, *args):
                pass

        print(f"\n🔬 哨兵 REST 服务已启动: http://0.0.0.0:{args.port}")
        print(f"   可用模型: {list(clf.sessions.keys())}")
        print(f"   GET  /?model=sentiment&text=A股大涨")
        print(f"   POST /  {{'model':'sentiment','text':'A股大涨'}}")
        print(f"   GET  /health")
        server = HTTPServer(("0.0.0.0", args.port), Handler)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n服务已停止")
            server.server_close()
        return

    # 默认：测试所有模型
    test_texts = [
        "A股三大指数今日集体大涨，沪指涨超2%",
        "央行降准释放流动性，利好实体经济",
        "美联储加息预期升温",
        "半导体板块持续走强",
        "某科技公司股价暴跌30%",
    ]

    print(f"\n🔬 哨兵多模型测试")
    print("=" * 60)
    for model_name in clf.sessions:
        print(f" [{model_name}]")
        for text in test_texts:
            result = clf.predict_one(model_name, text)
            print(f"   [{result['label']:10s}] ({result['score']:.2f}) {text[:50]}")
        print()
    print(f"可用模型: {list(clf.sessions.keys())}")
    print()


if __name__ == "__main__":
    main()
