# -*- coding: utf-8 -*-
"""
语义搜索 API 服务

提供基于 ChromaDB 的语义搜索和 RAG 问答能力，运行在 5070 端口。

API 端点：
- POST /api/semantic-search — 语义搜索
- POST /api/rag-ask — RAG 问答
- GET  /api/stats — 数据库统计
- GET  /api/health — 健康检查

免责声明：本工具仅供个人学习和研究使用，不构成任何投资建议。
"""

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
# 确保能找到 analyzer 模块
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
KB_PATH = os.environ.get('KB_PATH', str(BASE_DIR / 'knowledge_base' / 'obsidian'))
VECTOR_DB_PATH = os.environ.get('VECTOR_DB_PATH', str(BASE_DIR / 'data' / 'vectordb'))

_vector_db = None
_rag_retriever = None


def get_vector_db():
    global _vector_db
    if _vector_db is None:
        try:
            from analyzer.vector_db import VectorDB
            _vector_db = VectorDB(
                persist_directory=VECTOR_DB_PATH,
                collection_name="knowledge_base"
            )
            logger.info(f"VectorDB 初始化完成: {VECTOR_DB_PATH}")
        except Exception as e:
            logger.error(f"VectorDB 初始化失败: {e}")
    return _vector_db


def get_rag_retriever():
    global _rag_retriever
    if _rag_retriever is None:
        try:
            from analyzer.rag_retriever import RAGRetriever
            config = {
                'knowledge_base_path': KB_PATH,
                'vector_db_path': VECTOR_DB_PATH,
            }
            _rag_retriever = RAGRetriever(config)
            logger.info("RAGRetriever 初始化完成")
        except Exception as e:
            logger.error(f"RAGRetriever 初始化失败: {e}")
    return _rag_retriever


def create_app():
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        logger.error("Flask 未安装，请运行: pip install flask")
        sys.exit(1)

    app = Flask(__name__)

    @app.route('/api/health', methods=['GET'])
    def health():
        db = get_vector_db()
        stats = db.get_stats() if db else {'status': '未初始化'}
        return jsonify({
            'status': 'ok',
            'vector_db': stats,
            'kb_path': KB_PATH,
        })

    @app.route('/api/stats', methods=['GET'])
    def stats():
        db = get_vector_db()
        if not db:
            return jsonify({'error': 'VectorDB 未初始化'}), 500
        return jsonify(db.get_stats())

    @app.route('/api/semantic-search', methods=['POST'])
    def semantic_search():
        try:
            data = request.get_json(force=True)
            query = data.get('query', '').strip()
            top_k = data.get('top_k', 10)

            if not query:
                return jsonify({'error': 'query 不能为空'}), 400

            db = get_vector_db()
            if not db:
                return jsonify({'error': 'VectorDB 未初始化'}), 500

            results = db.search(query, n_results=top_k)

            formatted = []
            for r in results:
                meta = r.get('metadata', {})
                formatted.append({
                    'id': r.get('id', ''),
                    'title': meta.get('title', ''),
                    'summary': r.get('content', '')[:300],
                    'category': meta.get('category', ''),
                    'date': meta.get('date', ''),
                    'source': meta.get('source', ''),
                    'path': meta.get('path', ''),
                    'score': round(1 - r.get('distance', 0), 3),
                })

            return jsonify({
                'query': query,
                'total': len(formatted),
                'results': formatted,
            })

        except Exception as e:
            logger.error(f"语义搜索失败: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/rag-ask', methods=['POST'])
    def rag_ask():
        try:
            data = request.get_json(force=True)
            question = data.get('question', '').strip()
            top_k = data.get('top_k', 5)

            if not question:
                return jsonify({'error': 'question 不能为空'}), 400

            retriever = get_rag_retriever()
            if not retriever:
                return jsonify({'error': 'RAGRetriever 未初始化'}), 500

            result = retriever.ask(question, top_k=top_k)

            return jsonify({
                'question': question,
                'answer': result.get('answer', ''),
                'sources': result.get('sources', []),
                'confidence': result.get('confidence', 0),
            })

        except Exception as e:
            logger.error(f"RAG问答失败: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/reindex', methods=['POST'])
    def reindex():
        try:
            db = get_vector_db()
            if not db:
                return jsonify({'error': 'VectorDB 未初始化'}), 500

            force = request.json.get('force', False) if request.json else False

            if force:
                db.clear()

            count = db.import_from_obsidian(KB_PATH)

            return jsonify({
                'status': 'ok',
                'indexed': count,
                'stats': db.get_stats(),
            })

        except Exception as e:
            logger.error(f"重建索引失败: {e}")
            return jsonify({'error': str(e)}), 500

    return app


def main():
    parser = argparse.ArgumentParser(description='语义搜索 API 服务')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    parser.add_argument('--port', type=int, default=5070, help='监听端口')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    args = parser.parse_args()

    logger.info(f"语义搜索 API 启动: {args.host}:{args.port}")
    logger.info(f"知识库路径: {KB_PATH}")
    logger.info(f"向量数据库路径: {VECTOR_DB_PATH}")

    db = get_vector_db()
    if db:
        stats = db.get_stats()
        logger.info(f"VectorDB 状态: {stats}")

        if stats.get('total_count', 0) == 0 and os.path.exists(KB_PATH):
            logger.info("知识库为空，开始索引...")
            count = db.import_from_obsidian(KB_PATH)
            logger.info(f"索引完成: {count} 篇文档")

    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
    main()
