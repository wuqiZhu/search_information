# coding=utf-8
"""
市场情绪数据采集模块

从雪球和东方财富采集市场讨论热度和情绪数据，用于市场情绪指数计算。

数据源：
1. 雪球热帖 — 投资者讨论热度、情绪倾向
2. 东方财富股吧 — 个股/大盘讨论情绪
3. 龙虎榜数据 — 机构资金动向

免责声明：
本工具仅供个人学习和研究使用，不构成任何投资建议。
据此操作风险自担。基金投资有风险，过往业绩不代表未来表现。
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

import requests

logger = logging.getLogger(__name__)

POSITIVE_KEYWORDS = [
    '利好', '上涨', '增长', '突破', '新高', '反弹', '牛市', '盈利',
    '涨停', '大涨', '暴涨', '翻倍', '起飞', '爆发', '强势', '加仓',
    '降准', '降息', '刺激', '复苏', '回暖', '超预期', '业绩暴增',
]

NEGATIVE_KEYWORDS = [
    '利空', '下跌', '暴跌', '崩盘', '亏损', '风险', '熊市', '危机',
    '跌停', '大跌', '腰斩', '割肉', '逃命', '恐慌', '减仓', '清仓',
    '制裁', '暴雷', '违约', '退市', 'ST', '爆仓', '踩踏',
]


@dataclass
class SentimentItem:
    """情绪数据条目"""
    source: str
    title: str
    url: str = ""
    hot_value: int = 0
    comment_count: int = 0
    sentiment_score: float = 0.0
    crawl_time: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'source': self.source,
            'title': self.title,
            'url': self.url,
            'hot_value': self.hot_value,
            'comment_count': self.comment_count,
            'sentiment_score': self.sentiment_score,
            'crawl_time': self.crawl_time,
        }


@dataclass
class SentimentSummary:
    """情绪汇总"""
    source: str
    total_items: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    avg_score: float = 0.0
    hot_topics: List[str] = field(default_factory=list)
    crawl_time: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'source': self.source,
            'total_items': self.total_items,
            'positive_count': self.positive_count,
            'negative_count': self.negative_count,
            'neutral_count': self.neutral_count,
            'avg_score': round(self.avg_score, 4),
            'hot_topics': self.hot_topics[:10],
            'crawl_time': self.crawl_time,
        }


class XueqiuFetcher:
    """雪球数据采集器"""

    BASE_URL = "https://xueqiu.com"
    API_URL = "https://stock.xueqiu.com/v5/stock/hot_stock/list.json"

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://xueqiu.com/',
        'Accept': 'application/json',
    }

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def _get_cookie(self) -> str:
        try:
            resp = self.session.get(self.BASE_URL, timeout=self.timeout)
            return resp.headers.get('Set-Cookie', '')
        except Exception as e:
            logger.warning(f"获取雪球cookie失败: {e}")
            return ''

    def fetch_hot_stocks(self, count: int = 30) -> List[SentimentItem]:
        self._get_cookie()
        items = []
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            params = {
                'size': count,
                'order': 'desc',
                'order_by': 'follow7d',
                'type': 10,
                '_type': str(int(time.time() * 1000)),
            }
            resp = self.session.get(
                'https://stock.xueqiu.com/v5/stock/hot_stock/list.json',
                params=params,
                timeout=self.timeout,
            )
            data = resp.json()

            for stock in data.get('data', {}).get('items', []):
                name = stock.get('name', '')
                symbol = stock.get('symbol', '')
                follow = stock.get('follow7d', 0)

                score = self._calc_text_sentiment(name)
                items.append(SentimentItem(
                    source='xueqiu',
                    title=name,
                    url=f'https://xueqiu.com/S/{symbol}',
                    hot_value=follow,
                    sentiment_score=score,
                    crawl_time=now,
                ))
        except Exception as e:
            logger.error(f"雪球热股采集失败: {e}")

        return items

    def fetch_hot_posts(self, count: int = 20) -> List[SentimentItem]:
        self._get_cookie()
        items = []
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            resp = self.session.get(
                f'{self.BASE_URL}/statuses/hot/listV2.json',
                params={'since_id': -1, 'max_id': -1, 'size': count},
                timeout=self.timeout,
            )
            data = resp.json()

            for item in data.get('items', []):
                original = item.get('original_status', {})
                title = original.get('title', '') or original.get('description', '')
                if not title:
                    continue

                title = re.sub(r'<[^>]+>', '', title)[:200]
                retweet = original.get('retweet_count', 0)
                reply = original.get('reply_count', 0)
                like = original.get('like_count', 0)
                hot = retweet + reply + like

                score = self._calc_text_sentiment(title)
                items.append(SentimentItem(
                    source='xueqiu',
                    title=title,
                    url=original.get('target', ''),
                    hot_value=hot,
                    comment_count=reply,
                    sentiment_score=score,
                    crawl_time=now,
                ))
        except Exception as e:
            logger.error(f"雪球热帖采集失败: {e}")

        return items

    def _calc_text_sentiment(self, text: str) -> float:
        if not text:
            return 0.0
        pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
        neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
        total = pos + neg
        if total == 0:
            return 0.0
        return round((pos - neg) / total, 4)

    def summarize(self, items: List[SentimentItem]) -> SentimentSummary:
        if not items:
            return SentimentSummary(source='xueqiu', crawl_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        pos = sum(1 for i in items if i.sentiment_score > 0.1)
        neg = sum(1 for i in items if i.sentiment_score < -0.1)
        neu = len(items) - pos - neg
        avg = sum(i.sentiment_score for i in items) / len(items) if items else 0

        sorted_items = sorted(items, key=lambda x: x.hot_value, reverse=True)
        hot_topics = [i.title[:50] for i in sorted_items[:10]]

        return SentimentSummary(
            source='xueqiu',
            total_items=len(items),
            positive_count=pos,
            negative_count=neg,
            neutral_count=neu,
            avg_score=avg,
            hot_topics=hot_topics,
            crawl_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )


class EastmoneyFetcher:
    """东方财富股吧数据采集器"""

    GUBU_API = "https://guba.eastmoney.com/interface/GetData"

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://guba.eastmoney.com/',
        'Accept': 'application/json',
    }

    MARKET_CODES = {
        '上证指数': '1.000001',
        '深证成指': '0.399001',
        '创业板指': '0.399006',
        '科创50': '1.000688',
    }

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def fetch_market_posts(self, market_name: str = '上证指数',
                            count: int = 30) -> List[SentimentItem]:
        code = self.MARKET_CODES.get(market_name, '1.000001')
        items = []
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            url = f'https://guba.eastmoney.com/list,{code},f_{1}.html'
            resp = self.session.get(url, timeout=self.timeout)
            resp.encoding = 'utf-8'

            pattern = r'<a[^>]*class="post_title"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
            matches = re.findall(pattern, resp.text)

            for href, title in matches[:count]:
                title = re.sub(r'<[^>]+>', '', title).strip()
                if not title:
                    continue

                score = self._calc_text_sentiment(title)
                full_url = f'https://guba.eastmoney.com{href}' if href.startswith('/') else href

                items.append(SentimentItem(
                    source='eastmoney',
                    title=title,
                    url=full_url,
                    sentiment_score=score,
                    crawl_time=now,
                ))
        except Exception as e:
            logger.error(f"东方财富{market_name}股吧采集失败: {e}")

        return items

    def fetch_stock_posts(self, stock_code: str, count: int = 20) -> List[SentimentItem]:
        items = []
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            url = f'https://guba.eastmoney.com/list,{stock_code},f_{1}.html'
            resp = self.session.get(url, timeout=self.timeout)
            resp.encoding = 'utf-8'

            pattern = r'<a[^>]*class="post_title"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
            matches = re.findall(pattern, resp.text)

            for href, title in matches[:count]:
                title = re.sub(r'<[^>]+>', '', title).strip()
                if not title:
                    continue

                score = self._calc_text_sentiment(title)
                full_url = f'https://guba.eastmoney.com{href}' if href.startswith('/') else href

                items.append(SentimentItem(
                    source='eastmoney',
                    title=title,
                    url=full_url,
                    sentiment_score=score,
                    crawl_time=now,
                ))
        except Exception as e:
            logger.error(f"东方财富{stock_code}股吧采集失败: {e}")

        return items

    def fetch_all_markets(self, count_per_market: int = 20) -> List[SentimentItem]:
        all_items = []
        for name in self.MARKET_CODES:
            items = self.fetch_market_posts(name, count_per_market)
            all_items.extend(items)
            time.sleep(1)
        return all_items

    def _calc_text_sentiment(self, text: str) -> float:
        if not text:
            return 0.0
        pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
        neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
        total = pos + neg
        if total == 0:
            return 0.0
        return round((pos - neg) / total, 4)

    def summarize(self, items: List[SentimentItem]) -> SentimentSummary:
        if not items:
            return SentimentSummary(source='eastmoney', crawl_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        pos = sum(1 for i in items if i.sentiment_score > 0.1)
        neg = sum(1 for i in items if i.sentiment_score < -0.1)
        neu = len(items) - pos - neg
        avg = sum(i.sentiment_score for i in items) / len(items) if items else 0

        sorted_items = sorted(items, key=lambda x: x.hot_value, reverse=True)
        hot_topics = [i.title[:50] for i in sorted_items[:10]]

        return SentimentSummary(
            source='eastmoney',
            total_items=len(items),
            positive_count=pos,
            negative_count=neg,
            neutral_count=neu,
            avg_score=avg,
            hot_topics=hot_topics,
            crawl_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )


class SentimentCollector:
    """情绪数据聚合采集器"""

    def __init__(self, timeout: int = 15):
        self.xueqiu = XueqiuFetcher(timeout)
        self.eastmoney = EastmoneyFetcher(timeout)

    def collect_all(self) -> Dict[str, Any]:
        result = {
            'timestamp': datetime.now().isoformat(),
            'sources': {},
        }

        xq_stocks = self.xueqiu.fetch_hot_stocks(30)
        xq_posts = self.xueqiu.fetch_hot_posts(20)
        xq_all = xq_stocks + xq_posts
        xq_summary = self.xueqiu.summarize(xq_all)
        result['sources']['xueqiu'] = {
            'summary': xq_summary.to_dict(),
            'items': [i.to_dict() for i in xq_all[:30]],
        }

        time.sleep(2)

        em_items = self.eastmoney.fetch_all_markets(15)
        em_summary = self.eastmoney.summarize(em_items)
        result['sources']['eastmoney'] = {
            'summary': em_summary.to_dict(),
            'items': [i.to_dict() for i in em_items[:30]],
        }

        total_items = len(xq_all) + len(em_items)
        total_pos = xq_summary.positive_count + em_summary.positive_count
        total_neg = xq_summary.negative_count + em_summary.negative_count
        total_neu = xq_summary.neutral_count + em_summary.neutral_count

        if total_items > 0:
            xq_weight = len(xq_all) / total_items
            em_weight = len(em_items) / total_items
            weighted_score = xq_summary.avg_score * xq_weight + em_summary.avg_score * em_weight
        else:
            weighted_score = 0

        result['overall'] = {
            'total_items': total_items,
            'positive_count': total_pos,
            'negative_count': total_neg,
            'neutral_count': total_neu,
            'weighted_score': round(weighted_score, 4),
            'sentiment_level': self._score_to_level(weighted_score),
        }

        return result

    def _score_to_level(self, score: float) -> str:
        if score > 0.3:
            return '乐观'
        elif score > 0.1:
            return '偏乐观'
        elif score > -0.1:
            return '中性'
        elif score > -0.3:
            return '偏悲观'
        else:
            return '悲观'

    def to_news_items(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        news_items = []
        for source_name, source_data in data.get('sources', {}).items():
            for item in source_data.get('items', []):
                news_items.append({
                    'title': item['title'],
                    'source': item['source'],
                    'url': item.get('url', ''),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'category': '投资' if source_name == 'xueqiu' else '金融',
                    'sentiment_score': item.get('sentiment_score', 0),
                    'hot_value': item.get('hot_value', 0),
                })
        return news_items


if __name__ == '__main__':
    import argparse

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    parser = argparse.ArgumentParser(description='市场情绪数据采集')
    parser.add_argument('--xueqiu', action='store_true', help='仅采集雪球')
    parser.add_argument('--eastmoney', action='store_true', help='仅采集东方财富')
    parser.add_argument('--all', action='store_true', help='采集全部')
    parser.add_argument('--output', '-o', help='输出JSON文件路径')

    args = parser.parse_args()

    collector = SentimentCollector()

    if args.xueqiu:
        xq_stocks = collector.xueqiu.fetch_hot_stocks(30)
        xq_posts = collector.xueqiu.fetch_hot_posts(20)
        xq_all = xq_stocks + xq_posts
        summary = collector.xueqiu.summarize(xq_all)
        print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    elif args.eastmoney:
        em_items = collector.eastmoney.fetch_all_markets(15)
        summary = collector.eastmoney.summarize(em_items)
        print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    else:
        result = collector.collect_all()
        print(json.dumps(result['overall'], ensure_ascii=False, indent=2))
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"已保存到 {args.output}")
