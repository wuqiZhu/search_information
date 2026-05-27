#!/usr/bin/env python3
"""RAG 知识库索引构建脚本

使用方式：
    python scripts/build_rag_index.py                # 构建索引
    python scripts/build_rag_index.py --rebuild      # 强制重建索引
    python scripts/build_rag_index.py --query "华为"  # 测试检索
    python scripts/build_rag_index.py --ask "上周有哪些重要新闻？"  # 测试问答
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from analyzer.rag_retriever import RAGRetriever


def load_env():
    """加载 .env 文件"""
    env_path = project_root / '.env'
    if not env_path.exists():
        return
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value


def main():
    parser = argparse.ArgumentParser(description="RAG 知识库索引构建")
    parser.add_argument("--rebuild", action="store_true", help="强制重建索引")
    parser.add_argument("--query", type=str, help="测试检索查询")
    parser.add_argument("--ask", type=str, help="测试 RAG 问答")
    parser.add_argument("--kb-path", type=str, help="知识库路径")
    parser.add_argument("--top-k", type=int, default=5, help="返回结果数量")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    load_env()

    # 配置
    config = {
        "knowledge_base_path": args.kb_path or str(project_root / "knowledge_base" / "obsidian"),
        "vector_db_path": str(project_root / "knowledge_base" / "vectors"),
        "ai_api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "ai_api_base": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        "ai_model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
    }

    retriever = RAGRetriever(config)

    # 构建索引
    if args.query or args.ask:
        # 如果是查询模式，先确保索引存在
        count = retriever.index_knowledge_base(force_rebuild=False)
        print(f"\n索引文档数量: {count}")
    else:
        # 构建/重建索引
        print("\n=== 构建 RAG 知识库索引 ===\n")
        count = retriever.index_knowledge_base(force_rebuild=args.rebuild)
        print(f"\n✅ 索引构建完成: {count} 篇文档")

    # 测试检索
    if args.query:
        print(f"\n=== 检索: {args.query} ===\n")
        results = retriever.search(args.query, top_k=args.top_k)
        if not results:
            print("未找到相关文档")
        else:
            for i, r in enumerate(results):
                print(f"[{i+1}] (相关度: {r['score']}) {r['title']}")
                print(f"    分类: {r['category']} | 日期: {r['date']}")
                print(f"    摘要: {r['summary'][:100]}...")
                print()

    # 测试问答
    if args.ask:
        print(f"\n=== 问答: {args.ask} ===\n")
        result = retriever.ask(args.ask, top_k=args.top_k)
        print(f"回答:\n{result['answer']}")
        print(f"\n置信度: {result['confidence']:.3f}")
        if result['sources']:
            print(f"\n参考来源:")
            for i, s in enumerate(result['sources']):
                print(f"  [{i+1}] {s['title']} (相关度: {s['score']})")


if __name__ == '__main__':
    main()
