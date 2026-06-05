# -*- coding: utf-8 -*-
"""
ChromaDB 向量数据库模块

提供基于 ChromaDB 的语义向量检索能力，支持：
- 文档向量化存储
- 语义相似度搜索
- Obsidian 知识库批量导入
- 元数据过滤

免责声明：本工具仅供个人学习和研究使用，不构成任何投资建议。
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'vectordb'
)


class VectorDB:
    """ChromaDB 向量数据库封装"""

    def __init__(self, persist_directory: str = None, collection_name: str = "knowledge_base"):
        self.persist_directory = persist_directory or DEFAULT_PERSIST_DIR
        self.collection_name = collection_name
        self.collection = None
        self._client = None
        self._init_db()

    def _init_db(self):
        """初始化 ChromaDB 客户端和集合"""
        try:
            import chromadb
            from chromadb.config import Settings

            os.makedirs(self.persist_directory, exist_ok=True)

            self._client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(anonymized_telemetry=False)
            )

            self.collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )

            logger.info(f"ChromaDB 初始化成功: {self.persist_directory}, 集合: {self.collection_name}")

        except ImportError:
            logger.warning("chromadb 未安装，向量检索不可用。请运行: pip install chromadb")
            self.collection = None
        except Exception as e:
            logger.error(f"ChromaDB 初始化失败: {e}")
            self.collection = None

    def add_documents(self, documents: List[Dict[str, Any]]) -> int:
        """
        批量添加文档到向量数据库

        Args:
            documents: 文档列表，每项包含:
                - id: 唯一标识
                - content: 文档内容（用于向量化）
                - metadata: 元数据字典（title, category, date, source, path 等）

        Returns:
            成功添加的文档数量
        """
        if not self.collection:
            logger.error("ChromaDB 未初始化")
            return 0

        if not documents:
            return 0

        batch_size = 100
        total_added = 0

        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]

            ids = []
            contents = []
            metadatas = []

            for doc in batch:
                doc_id = doc.get('id', '')
                content = doc.get('content', '')

                if not doc_id or not content:
                    continue

                ids.append(str(doc_id))
                contents.append(content)

                metadata = doc.get('metadata', {})
                sanitized = {}
                for k, v in metadata.items():
                    if isinstance(v, (str, int, float, bool)):
                        sanitized[k] = v
                    else:
                        sanitized[k] = str(v)
                metadatas.append(sanitized)

            if ids:
                try:
                    self.collection.upsert(
                        ids=ids,
                        documents=contents,
                        metadatas=metadatas
                    )
                    total_added += len(ids)
                except Exception as e:
                    logger.error(f"ChromaDB 批量添加失败 (batch {i}): {e}")

        logger.info(f"ChromaDB 添加完成: {total_added}/{len(documents)} 篇文档")
        return total_added

    def search(self, query: str, n_results: int = 5,
               where: Dict = None) -> List[Dict[str, Any]]:
        """
        语义搜索

        Args:
            query: 查询文本
            n_results: 返回结果数量
            where: 元数据过滤条件

        Returns:
            结果列表，每项包含 id, content, distance, metadata
        """
        if not self.collection:
            logger.error("ChromaDB 未初始化")
            return []

        try:
            count = self.collection.count()
            if count == 0:
                return []

            n_results = min(n_results, count)

            kwargs = {
                "query_texts": [query],
                "n_results": n_results,
            }
            if where:
                kwargs["where"] = where

            results = self.collection.query(**kwargs)

            items = []
            if results and results['ids'] and results['ids'][0]:
                for j in range(len(results['ids'][0])):
                    item = {
                        'id': results['ids'][0][j],
                        'content': results['documents'][0][j] if results.get('documents') else '',
                        'distance': results['distances'][0][j] if results.get('distances') else 0,
                        'metadata': results['metadatas'][0][j] if results.get('metadatas') else {},
                    }
                    items.append(item)

            return items

        except Exception as e:
            logger.error(f"ChromaDB 搜索失败: {e}")
            return []

    def import_from_obsidian(self, kb_path: str) -> int:
        """
        从 Obsidian 知识库目录批量导入 Markdown 文件

        Args:
            kb_path: Obsidian 知识库根目录路径

        Returns:
            导入的文档数量
        """
        kb_dir = Path(kb_path)
        if not kb_dir.exists():
            logger.error(f"知识库目录不存在: {kb_path}")
            return 0

        md_files = list(kb_dir.rglob("*.md"))
        logger.info(f"找到 {len(md_files)} 个 Markdown 文件")

        documents = []
        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')
                if len(content.strip()) < 20:
                    continue

                title = md_file.stem
                rel_path = str(md_file.relative_to(kb_dir))

                category = ""
                parts = rel_path.split(os.sep)
                if len(parts) > 1:
                    category = parts[0]

                metadata = {
                    'title': title,
                    'path': rel_path,
                    'category': category,
                    'source': 'obsidian',
                    'file_size': len(content),
                }

                date_str = ""
                for line in content.split('\n')[:10]:
                    if 'date:' in line or '日期:' in line:
                        date_str = line.split(':', 1)[1].strip().strip('"').strip("'")
                        break
                if date_str:
                    metadata['date'] = date_str

                documents.append({
                    'id': rel_path,
                    'content': content,
                    'metadata': metadata,
                })

            except Exception as e:
                logger.warning(f"读取文件失败 {md_file}: {e}")

        if documents:
            return self.add_documents(documents)

        return 0

    def get_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        if not self.collection:
            return {'status': '未初始化', 'total_count': 0}

        try:
            count = self.collection.count()
            return {
                'status': '正常',
                'total_count': count,
                'collection_name': self.collection_name,
                'persist_directory': self.persist_directory,
            }
        except Exception as e:
            return {'status': f'错误: {e}', 'total_count': 0}

    def clear(self):
        """清空集合中的所有数据"""
        if not self.collection:
            return

        try:
            self._client.delete_collection(self.collection_name)
            self.collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB 集合已清空: {self.collection_name}")
        except Exception as e:
            logger.error(f"清空集合失败: {e}")

    def delete_by_path(self, path: str):
        """按路径删除文档"""
        if not self.collection:
            return

        try:
            results = self.collection.get(
                where={"path": path}
            )
            if results and results['ids']:
                self.collection.delete(ids=results['ids'])
                logger.info(f"已删除文档: {path}")
        except Exception as e:
            logger.error(f"删除文档失败 {path}: {e}")


if __name__ == '__main__':
    import argparse

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    parser = argparse.ArgumentParser(description='ChromaDB 向量数据库管理')
    parser.add_argument('--import-kb', type=str, help='从 Obsidian 知识库导入')
    parser.add_argument('--search', type=str, help='语义搜索')
    parser.add_argument('--stats', action='store_true', help='显示统计信息')
    parser.add_argument('--clear', action='store_true', help='清空数据库')
    parser.add_argument('--top-k', type=int, default=5, help='搜索结果数量')

    args = parser.parse_args()

    db = VectorDB()

    if args.import_kb:
        count = db.import_from_obsidian(args.import_kb)
        print(f"导入完成: {count} 篇文档")
    elif args.search:
        results = db.search(args.search, n_results=args.top_k)
        for i, r in enumerate(results):
            score = round(1 - r['distance'], 3)
            title = r['metadata'].get('title', '无标题')
            print(f"[{i+1}] {title} (相关度: {score})")
            print(f"    {r['content'][:100]}...")
    elif args.stats:
        import json
        print(json.dumps(db.get_stats(), ensure_ascii=False, indent=2))
    elif args.clear:
        db.clear()
        print("数据库已清空")
    else:
        import json
        print(json.dumps(db.get_stats(), ensure_ascii=False, indent=2))
