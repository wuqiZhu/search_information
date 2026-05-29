# -*- coding: utf-8 -*-
"""RAG 知识库检索模块

将 Obsidian 知识库中的文章向量化，支持语义检索和问答。

使用方式：
    from analyzer.rag_retriever import RAGRetriever

    retriever = RAGRetriever(config)
    retriever.index_knowledge_base()  # 索引知识库
    results = retriever.search("华为最近裁员了吗？")  # 语义检索
    answer = retriever.ask("上周有哪些关于嵌入式的重要新闻？")  # RAG 问答
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class RAGRetriever:
    """RAG 知识库检索器"""

    def __init__(self, config: dict):
        """
        初始化 RAG 检索器

        Args:
            config: 配置字典，需包含：
                - knowledge_base_path: 知识库路径（Obsidian 目录）
                - vector_db_path: 向量数据库存储路径
                - ai_api_key: AI API 密钥
                - ai_api_base: AI API 基础 URL
                - ai_model: AI 模型名称
                - embedding_model: 嵌入模型（可选，默认用 TF-IDF）
        """
        self.kb_path = Path(config.get("knowledge_base_path", "./knowledge_base/obsidian"))
        self.vector_db_path = Path(config.get("vector_db_path", "./knowledge_base/vectors"))
        self.ai_api_key = config.get("ai_api_key", os.environ.get("DEEPSEEK_API_KEY", ""))
        self.ai_api_base = config.get("ai_api_base", os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"))
        self.ai_model = config.get("ai_model", os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))
        
        self._vector_db = None
        self._documents = []
        self._use_chromadb = False

    def _init_vector_db(self):
        """初始化向量数据库"""
        try:
            from analyzer.vector_db import VectorDB
            self._vector_db = VectorDB(
                persist_directory=str(self.vector_db_path),
                collection_name="knowledge_base"
            )
            if self._vector_db.collection:
                self._use_chromadb = True
                logger.info("ChromaDB向量数据库初始化成功")
            else:
                logger.warning("ChromaDB初始化失败，回退到TF-IDF模式")
        except ImportError:
            logger.warning("ChromaDB模块导入失败，使用TF-IDF模式")

    def index_knowledge_base(self, force_rebuild: bool = False) -> int:
        """
        索引知识库中的所有 Markdown 文件

        Args:
            force_rebuild: 是否强制重建索引

        Returns:
            索引的文档数量
        """
        if not self._vector_db:
            self._init_vector_db()

        if self._use_chromadb and self._vector_db:
            return self._index_with_chromadb(force_rebuild)
        else:
            return self._index_with_tfidf(force_rebuild)

    def _index_with_chromadb(self, force_rebuild: bool = False) -> int:
        """使用ChromaDB索引知识库"""
        if force_rebuild:
            logger.info("强制重建ChromaDB索引...")
            self._vector_db.clear()

        stats = self._vector_db.get_stats()
        if stats.get('total_count', 0) > 0 and not force_rebuild:
            logger.info(f"ChromaDB已有 {stats['total_count']} 篇文档，跳过索引")
            return stats['total_count']

        logger.info(f"开始索引知识库: {self.kb_path}")
        count = self._vector_db.import_from_obsidian(str(self.kb_path))
        logger.info(f"ChromaDB索引完成: {count} 篇文档")
        return count

    def _index_with_tfidf(self, force_rebuild: bool = False) -> int:
        """使用TF-IDF索引知识库"""
        index_file = self.vector_db_path / "index.json"

        if not force_rebuild and index_file.exists():
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._documents = data.get("documents", [])
                    logger.info(f"加载已有索引: {len(self._documents)} 篇文档")
                    return len(self._documents)
            except Exception as e:
                logger.warning(f"加载索引失败: {e}，将重建")

        self._documents = []
        for md_file in self.kb_path.rglob("*.md"):
            try:
                content = md_file.read_text(encoding='utf-8')
                doc = self._parse_markdown(content, str(md_file))
                if doc:
                    self._documents.append(doc)
            except Exception as e:
                logger.warning(f"解析文件失败 {md_file}: {e}")

        self.vector_db_path.mkdir(parents=True, exist_ok=True)
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump({
                "documents": self._documents,
                "built_at": datetime.now().isoformat(),
                "count": len(self._documents)
            }, f, ensure_ascii=False, indent=2)

        logger.info(f"TF-IDF索引构建完成: {len(self._documents)} 篇文档")
        return len(self._documents)

    def search(self, query: str, top_k: int = 5, min_score: float = 0.1) -> List[Dict[str, Any]]:
        """
        语义检索

        Args:
            query: 查询文本
            top_k: 返回结果数量
            min_score: 最低相关性分数

        Returns:
            检索结果列表
        """
        if not self._vector_db:
            self._init_vector_db()

        if self._use_chromadb and self._vector_db:
            return self._search_with_chromadb(query, top_k)
        else:
            return self._search_with_tfidf(query, top_k, min_score)

    def _search_with_chromadb(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """使用ChromaDB语义检索"""
        results = self._vector_db.search(query, n_results=top_k)
        
        formatted_results = []
        for item in results:
            metadata = item.get('metadata', {})
            formatted_results.append({
                'title': metadata.get('title', ''),
                'summary': item.get('content', '')[:200],
                'category': metadata.get('category', ''),
                'date': metadata.get('date', ''),
                'source': metadata.get('source', ''),
                'path': metadata.get('path', ''),
                'score': round(1 - item.get('distance', 0), 3),
                'id': item.get('id', '')
            })
        
        return formatted_results

    def _search_with_tfidf(self, query: str, top_k: int = 5, min_score: float = 0.1) -> List[Dict[str, Any]]:
        """使用TF-IDF检索"""
        if not self._documents:
            self.index_knowledge_base()

        if not self._documents:
            return []

        query_terms = self._tokenize(query)
        scores = []

        for i, doc in enumerate(self._documents):
            score = self._calculate_similarity(query_terms, doc)
            if score >= min_score:
                scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in scores[:top_k]:
            doc = self._documents[idx]
            results.append({
                "title": doc.get("title", ""),
                "summary": doc.get("summary", "")[:200],
                "category": doc.get("category", ""),
                "date": doc.get("date", ""),
                "score": round(score, 3),
                "source": doc.get("source", ""),
                "path": doc.get("path", ""),
            })

        return results

    def ask(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        """
        RAG 问答

        Args:
            question: 用户问题
            top_k: 检索的文档数量

        Returns:
            包含 answer 和 sources 的字典
        """
        results = self.search(question, top_k=top_k)

        if not results:
            return {
                "answer": "抱歉，知识库中没有找到相关信息。",
                "sources": [],
                "confidence": 0
            }

        context_parts = []
        for i, r in enumerate(results):
            context_parts.append(f"[{i+1}] {r['title']} ({r['date']}, {r['category']})\n{r['summary']}")

        context = "\n\n".join(context_parts)

        prompt = f"""基于以下知识库内容回答用户问题。如果知识库中没有相关信息，请如实说明。

知识库内容：
{context}

用户问题：{question}

请用中文回答，简洁明了，引用信息时标注来源编号如 [1]。"""

        try:
            import urllib.request
            url = f"{self.ai_api_base}/chat/completions"
            payload = json.dumps({
                "model": self.ai_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000,
                "temperature": 0.3,
            }).encode('utf-8')

            req = urllib.request.Request(url, data=payload, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.ai_api_key}",
            })

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                answer = data["choices"][0]["message"]["content"]

                return {
                    "answer": answer,
                    "sources": results,
                    "confidence": results[0]["score"] if results else 0
                }
        except Exception as e:
            logger.error(f"AI 调用失败: {e}")
            return {
                "answer": f"AI 调用失败: {str(e)}",
                "sources": results,
                "confidence": 0
            }

    def _parse_markdown(self, content: str, path: str) -> Optional[Dict]:
        """解析 Markdown 文件"""
        lines = content.strip().split('\n')
        if not lines:
            return None

        title = ""
        summary = ""
        category = ""
        date = ""
        source = ""

        in_frontmatter = False
        for line in lines:
            if line.strip() == '---':
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                if line.startswith('title:'):
                    title = line.split(':', 1)[1].strip().strip('"')
                elif line.startswith('category:'):
                    category = line.split(':', 1)[1].strip().strip('"')
                elif line.startswith('date:'):
                    date = line.split(':', 1)[1].strip()
                elif line.startswith('source:'):
                    source = line.split(':', 1)[1].strip().strip('"')

        in_summary = False
        for line in lines:
            if '一句话总结' in line:
                in_summary = True
                continue
            if in_summary:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    summary = stripped[:300]
                    break
                if stripped.startswith('#'):
                    break

        if not title:
            for line in lines:
                if line.startswith('# '):
                    title = line[2:].strip()
                    break

        if not title:
            title = Path(path).stem

        return {
            "title": title,
            "summary": summary,
            "category": category,
            "date": date,
            "source": source,
            "path": path,
            "content": content[:2000],
        }

    def _tokenize(self, text: str) -> List[str]:
        """简单分词（中英文混合）"""
        import re
        english_words = re.findall(r'[a-zA-Z]+', text.lower())
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        bigrams = []
        for chars in chinese_chars:
            for i in range(len(chars) - 1):
                bigrams.append(chars[i:i+2])
        return english_words + bigrams

    def _calculate_similarity(self, query_terms: List[str], doc: Dict) -> float:
        """计算查询与文档的相似度"""
        doc_text = doc.get("title", "") + " " + doc.get("summary", "") + " " + doc.get("content", "")[:500]
        doc_terms = set(self._tokenize(doc_text))

        if not query_terms or not doc_terms:
            return 0

        matched = sum(1 for t in query_terms if t in doc_terms)
        score = matched / len(query_terms) if query_terms else 0

        title_terms = set(self._tokenize(doc.get("title", "")))
        title_matched = sum(1 for t in query_terms if t in title_terms)
        if title_matched > 0:
            score += 0.3 * (title_matched / len(query_terms))

        return min(score, 1.0)

    def get_stats(self) -> Dict[str, Any]:
        """获取检索器统计信息"""
        if not self._vector_db:
            self._init_vector_db()

        if self._use_chromadb and self._vector_db:
            return {
                'mode': 'chromadb',
                'available': True,
                **self._vector_db.get_stats()
            }
        else:
            return {
                'mode': 'tfidf',
                'available': True,
                'total_count': len(self._documents)
            }
